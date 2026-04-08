"""TUI module: Marauder ESP32 WiFi/BLE attack toolkit.

Controls an ESP32 running Marauder firmware over serial (/dev/esp32).
Scan -> Select -> Attack workflow with live braille RSSI waveforms.
"""

import curses
import re
import threading
import time

from tui.framework import (
    C_BORDER,
    C_CAT,
    C_DIM,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    _gp_set_cooldown,
    _tui_input_loop,
    close_gamepad,
    draw_tile_grid,
    open_gamepad,
    read_gamepad,
)
import tui_lib as tui

# Gauge colors from tui_lib (initialized by tui.init_gauge_colors())
C_OK = tui.C_OK
C_WARN = tui.C_WARN
C_CRIT = tui.C_CRIT

# ── Serial output parsers ────────────────────────────────────────────

_RE_AP = re.compile(
    r'^(-?\d+)\s+Ch:\s+(\d+)\s+([0-9A-Fa-f:]{17})\s+ESSID:\s+(.*?)\s*$')
_RE_LIST_AP = re.compile(
    r'^\[(\d+)\]\[CH:(\d+)\]\s+(.*?)\s+(-?\d+)(\s+\(selected\))?\s*$')
_RE_DEAUTH = re.compile(
    r'^(-?\d+)\s+Ch:\s+(\d+)\s+([0-9A-Fa-f:]{17})\s+->\s+([0-9A-Fa-f:]{17})')
_RE_PROBE = re.compile(
    r'^(-?\d+)\s+Ch:\s+(\d+)\s+Client:\s+([0-9A-Fa-f:]{17})\s+Requesting:\s+(.*)')
_RE_EAPOL = re.compile(r'^Received EAPOL:\s+([0-9A-Fa-f:]{17})')
_RE_CRED = re.compile(r'^u:\s+(.*?)\s+p:\s+(.*)')

# BLE serial output parsers
_RE_BLE = re.compile(
    r'(-?\d+)\s+BLE:\s+([0-9A-Fa-f:]{17})\s*(?:Name:\s*(.*))?')
_RE_BLE_TYPE = re.compile(
    r'Type:\s+(\w+)\s+RSSI:\s+(-?\d+)\s+MAC:\s+([0-9A-Fa-f:]{17})'
    r'(?:\s+Name:\s*(.*))?')
_RE_SKIM = re.compile(
    r'(?:Potential\s+)?[Ss]kimmer.*?RSSI:\s+(-?\d+)\s+MAC:\s+([0-9A-Fa-f:]{17})')

_IDLE, _SCANNING, _ATTACKING = 0, 1, 2

# Module-level selected AP targets — avoids reliance on Marauder's
# flaky select -a command.  Updated by _wifi_scan's stop/attack flow.
_selected_targets = []


# ── Serial Connection ────────────────────────────────────────────────

class _Conn:
    """Thread-safe serial wrapper for ESP32 Marauder."""

    PORTS = ["/dev/esp32", "/dev/ttyUSB0"]
    BAUD = 115200

    def __init__(self):
        self.port = None
        self.lines = []
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self.state = _IDLE
        self.dev_path = ""
        self.ok = False

    def connect(self):
        try:
            import serial as _pyserial
        except ImportError:
            return False
        for dev in self.PORTS:
            try:
                self.port = _pyserial.Serial(dev, self.BAUD, timeout=0.1)
                self.dev_path = dev
                self._stop.clear()
                self._ready.clear()
                self._thread = threading.Thread(target=self._reader, daemon=True)
                self._thread.start()
                self._ready.wait(timeout=1)  # block until reader is running
                self.ok = True
                # Reset Marauder state: stop any pending scan, wake, drain
                self.port.write(b"\r\n")
                time.sleep(0.2)
                self.port.write(b"stopscan\r\n")
                time.sleep(0.5)
                self.port.reset_input_buffer()
                self.clear()
                return True
            except Exception:
                continue
        return False

    def close(self):
        if self.state != _IDLE:
            self.send("stopscan")
            time.sleep(0.2)
            self.state = _IDLE
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self.port:
            try:
                self.port.close()
            except Exception:
                pass
        self.port = None
        self.ok = False

    def send(self, cmd):
        if self.port and self.port.is_open:
            try:
                self.port.write(f"{cmd}\n".encode())
            except Exception:
                self.ok = False

    def clear(self):
        with self.lock:
            self.lines.clear()

    def snap(self):
        with self.lock:
            return list(self.lines)

    def drain(self):
        with self.lock:
            s = list(self.lines)
            self.lines.clear()
            return s

    def stop_scan(self):
        self.send("stopscan")
        self.state = _IDLE

    def _reader(self):
        buf = b""
        self._ready.set()
        while not self._stop.is_set():
            try:
                if self.port and self.port.is_open and self.port.in_waiting:
                    buf += self.port.read(self.port.in_waiting)
                    while b'\r\n' in buf:
                        raw, buf = buf.split(b'\r\n', 1)
                        # Strip nulls and non-printable bytes
                        raw = bytes(b for b in raw if 0x20 <= b < 0x7f)
                        ln = raw.decode(errors='replace').strip()
                        if not ln or ln in ('> ', '>'):
                            continue
                        if ln.startswith('#'):
                            continue
                        # Strip leading prompt from async output
                        if ln.startswith('> '):
                            ln = ln[2:]
                        if not ln:
                            continue
                        # Drop garbage lines from MAC errors etc.
                        if 'Failed to set' in ln:
                            continue
                        # Drop truncated ESSID fragments
                        if ln.startswith('D: ') and 'Ch:' not in ln:
                            continue
                        with self.lock:
                            self.lines.append(ln)
                            if len(self.lines) > 4000:
                                del self.lines[:2000]
                else:
                    time.sleep(0.02)
            except Exception:
                time.sleep(0.1)


_inst = None


def _get_conn():
    """Get or create Marauder serial connection."""
    global _inst
    if _inst and _inst.ok:
        try:
            if _inst.port and _inst.port.is_open:
                return _inst
        except Exception:
            pass
    _inst = _Conn()
    return _inst if _inst.connect() else None


# ── Helpers ──────────────────────────────────────────────────────────

def _rssi_color(rssi):
    """Color pair ID for RSSI. Green > -50, Yellow > -70, Red below."""
    return tui.C_OK if rssi > -50 else tui.C_WARN if rssi > -70 else tui.C_CRIT


def _rssi_bar(rssi, width=10):
    """RSSI gauge bar. -30=full, -90=empty."""
    pct = max(0, min(100, int((rssi + 90) * 100 / 60)))
    f = int(width * pct / 100)
    return "\u2588" * f + "\u2591" * (width - f)


def _confirm(scr, title, msg):
    """Centered confirmation dialog. Returns True on confirm."""
    h, w = scr.getmaxyx()
    bw, bh = min(48, w - 4), 7
    by, bx = (h - bh) // 2, (w - bw) // 2
    wrn = curses.color_pair(C_CRIT) | curses.A_BOLD
    hdr_a = curses.color_pair(C_HEADER) | curses.A_BOLD

    tui.panel_top(scr, by, bx, bw, title)
    for r in range(1, bh - 1):
        tui.panel_side(scr, by + r, bx, bw)
        tui.put(scr, by + r, bx + 2, " " * (bw - 4), bw - 4, curses.color_pair(C_DIM))
    tui.panel_bot(scr, by + bh - 1, bx, bw)
    tui.put(scr, by + 2, bx + 4, msg[:bw - 8], bw - 8, wrn)
    tui.put(scr, by + 4, bx + 4, "[A/Y] CONFIRM", 13, hdr_a)
    tui.put(scr, by + 4, bx + 20, "[B/N] Cancel", 12, curses.color_pair(C_DIM))
    scr.refresh()

    scr.timeout(-1)
    while True:
        k = scr.getch()
        if k in (ord('a'), ord('A'), ord('y'), ord('Y'), 10, 13):
            scr.timeout(100)
            return True
        if k in (ord('b'), ord('B'), ord('n'), ord('N'), ord('q'), 27):
            scr.timeout(100)
            return False


# ── Main Menu ────────────────────────────────────────────────────────

_MENU = [
    ("WiFi Scan",       "Scan access points and stations",       "◎"),
    ("WiFi Attack",     "Deauth, beacon, probe, rickroll, CSA",  "☠"),
    ("Sniffers",        "Deauth, PMKID, beacon, probe, raw",    "◈"),
    ("BLE Tools",       "Scan, spam, AirTag, Flipper, skimmers", "⚑"),
    ("Signal Monitor",  "Live RSSI braille waveforms",           "⣿"),
    ("Evil Portal",     "Captive portal credential capture",     "⚠"),
    ("Network Recon",   "Join network, ping, ARP, port scan",   "⌗"),
    ("Device",          "Info, settings, MAC spoof, reboot",     "⚙"),
    ("Raw Console",     "Direct serial I/O",                     "⌨"),
]


def run_marauder(scr):
    """Marauder ESP32 WiFi/BLE attack toolkit."""
    tui.init_gauge_colors()
    js = open_gamepad()
    scr.timeout(100)
    sel, status = 0, ""
    mrd = _get_conn()
    cols = 1

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        if mrd and mrd.ok:
            st = ["IDLE", "SCANNING", "ATTACKING"][mrd.state]
            hdr = f" MARAUDER  {st}  {mrd.dev_path} "
            if _selected_targets:
                names = ", ".join(t["essid"] for t in _selected_targets)
                hdr = f" MARAUDER  {st}  \u25c9 {len(_selected_targets)} AP: {names} "
            tui.put(scr, 0, 0, hdr.center(w), w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        else:
            tui.put(scr, 0, 0,
                    " MARAUDER  NOT CONNECTED ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        # Tile grid
        tiles = [{"name": n, "desc": d, "icon": ic} for n, d, ic in _MENU]
        content_y = 2
        content_h = h - content_y - 3
        cols, _rows = draw_tile_grid(scr, content_y, w, content_h, tiles, sel)

        if status:
            tui.put(scr, h - 2, 1, status[:w - 2], w - 2,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        tui.put(scr, h - 1, 0,
                " \u2191\u2193\u2190\u2192 Navigate \u2502 A Enter \u2502 B Back ".center(w),
                w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - cols)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(_MENU) - 1, sel + cols)
        elif key == curses.KEY_LEFT or key == ord("h"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_RIGHT or key == ord("l"):
            sel = min(len(_MENU) - 1, sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if not mrd or not mrd.ok:
                status = "ESP32 not connected \u2014 check /dev/esp32"
                continue
            status = ""
            fn = _get_menu_fns().get(sel)
            if fn:
                result = fn(scr, mrd)
                if result == "attack":
                    _wifi_attack(scr, mrd)
                # Flush stale B press from sub-view exit
                read_gamepad(js)
                curses.flushinp()
                _gp_set_cooldown(0.5)
                scr.timeout(100)

    if mrd:
        mrd.close()
    if js:
        read_gamepad(js)  # flush lingering B press
        close_gamepad(js)
    curses.flushinp()
    _gp_set_cooldown(0.5)
    scr.timeout(100)


# ── WiFi Scan ────────────────────────────────────────────────────────

def _wifi_scan(scr, mrd):
    """Live AP scanner with RSSI bars and target selection."""
    js = open_gamepad()
    scr.timeout(200)
    aps = []
    sel, scroll = 0, 0
    scanning = False
    t0 = time.time()

    def start():
        nonlocal scanning, t0
        aps.clear()
        # Fully reset Marauder state — stop, clear stale APs, then scan
        mrd.send("stopscan")
        time.sleep(0.3)
        mrd.send("clearlist -a")
        time.sleep(0.3)
        mrd.drain()
        mrd.clear()
        mrd.send("scanap")
        mrd.state = _SCANNING
        scanning = True
        t0 = time.time()

    def _save_targets():
        """Save selected APs to module-level _selected_targets.

        Also attempts Marauder select -a, but Signal Monitor
        uses _selected_targets directly (not Marauder's state).
        """
        global _selected_targets
        selected = [a for a in aps if a.get("selected")]
        _selected_targets = [
            {"essid": a["essid"], "bssid": a["bssid"],
             "ch": a["ch"], "rssi": a["rssi"],
             "hist": tui.make_history(120)}
            for a in selected
        ]
        if not selected:
            return
        # Best-effort Marauder select (needed for attacks)
        time.sleep(0.5)
        mrd.drain()
        for i, a in enumerate(aps):
            if a.get("selected"):
                mrd.send(f"select -a {i}")
                time.sleep(0.15)
        mrd.drain()

    def stop():
        nonlocal scanning
        mrd.stop_scan()
        scanning = False
        _save_targets()

    start()

    while True:
        for ln in mrd.drain():
            m = _RE_AP.match(ln)
            if m:
                bssid = m.group(3)
                existing = next((a for a in aps if a["bssid"] == bssid), None)
                if existing:
                    existing["rssi"] = int(m.group(1))
                else:
                    aps.append({
                        "rssi": int(m.group(1)), "ch": int(m.group(2)),
                        "bssid": bssid,
                        "essid": m.group(4).strip() or "(hidden)",
                        "selected": False,
                    })

        h, w = scr.getmaxyx()
        scr.erase()
        val = curses.color_pair(C_ITEM)
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        elapsed = int(time.time() - t0) if scanning else 0
        n_sel = sum(1 for a in aps if a.get("selected"))
        detail = f"{len(aps)} APs"
        if n_sel:
            detail += f"  {n_sel} selected"
        if scanning:
            detail += f"  {elapsed}s"
        tui.panel_top(scr, 0, 0, w,
                      "AP SCAN" if scanning else "AP LIST", detail)

        tui.panel_side(scr, 1, 0, w)
        tui.put(scr, 1, 2, f"  {'RSSI':<12} {'CH':>3}  {'BSSID':<18} ESSID",
                w - 4, curses.color_pair(C_CAT) | curses.A_BOLD)
        tui.panel_side(scr, 2, 0, w)
        tui.put(scr, 2, 2, "\u2500" * (w - 4), w - 4, dim)

        vis = h - 6
        if aps:
            sel = min(sel, len(aps) - 1)
            if sel < scroll:
                scroll = sel
            if sel >= scroll + vis:
                scroll = sel - vis + 1

        for i in range(vis):
            y = 3 + i
            idx = scroll + i
            tui.panel_side(scr, y, 0, w)
            if idx >= len(aps):
                continue
            ap = aps[idx]
            is_sel = idx == sel
            mk = "\u25b8" if is_sel else " "
            ck = "\u25c9" if ap.get("selected") else "\u25cb"
            rssi = ap["rssi"]
            bar = _rssi_bar(rssi, 8)
            col = _rssi_color(rssi)
            attr = curses.color_pair(C_SEL) | curses.A_BOLD if is_sel else val

            tui.put(scr, y, 1, f"{mk}{ck}", 2, attr)
            tui.put(scr, y, 4, bar, 8, curses.color_pair(col))
            tui.put(scr, y, 13, f"{rssi:>4}", 4,
                    curses.color_pair(col) | curses.A_BOLD)
            tui.put(scr, y, 18, f"{ap['ch']:>3}", 3, dim)
            tui.put(scr, y, 22, ap["bssid"], 17, dim)
            ew = max(1, w - 42)
            tui.put(scr, y, 40, ap["essid"][:ew], ew, attr)

        if not aps:
            tui.panel_side(scr, 3, 0, w)
            msg = "Scanning..." if scanning else "No APs found. Press S to scan."
            tui.put(scr, 3, 4, msg, w - 8, dim)

        # Status hint
        tui.panel_side(scr, h - 3, 0, w)
        if n_sel and not scanning:
            hint = f"  {n_sel} AP(s) selected. X \u2192 Attack \u2502 B Back"
            tui.put(scr, h - 3, 2, hint[:w - 4], w - 4,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        tui.panel_bot(scr, h - 2, 0, w)

        if scanning:
            foot = " \u2191\u2193 Nav \u2502 A Select \u2502 X Stop scan \u2502 B Back "
        elif n_sel:
            foot = " \u2191\u2193 Nav \u2502 A Select \u2502 X Attack \u2502 D Details \u2502 S Rescan \u2502 B Back "
        else:
            foot = " \u2191\u2193 Nav \u2502 A Select \u2502 D Details \u2502 S Rescan \u2502 B Back "
        tui.put(scr, h - 1, 0, foot.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if scanning:
                stop()
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(max(0, len(aps) - 1), sel + 1)
        elif key == ord(" ") or key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            # A button / Enter / Space = toggle selection
            if aps and sel < len(aps):
                aps[sel]["selected"] = not aps[sel]["selected"]
        elif key == ord("x") or key == ord("X") or gp == "refresh":
            if scanning:
                stop()
            elif n_sel:
                # X when APs selected = select + attack
                _save_targets()
                if js:
                    close_gamepad(js)
                scr.timeout(100)
                return "attack"
            elif aps and sel < len(aps):
                # X when no selection = show AP details
                mrd.clear()
                mrd.send(f"info -a {sel}")
                time.sleep(0.5)
                info = mrd.drain()
                bw = min(50, w - 4)
                bh = min(len(info) + 3, h - 4)
                by, bx = (h - bh) // 2, (w - bw) // 2
                tui.panel_top(scr, by, bx, bw, aps[sel]["essid"])
                for ri, ln in enumerate(info[:bh - 3]):
                    tui.panel_side(scr, by + 1 + ri, bx, bw)
                    tui.put(scr, by + 1 + ri, bx + 2, ln[:bw - 4], bw - 4, val)
                tui.panel_bot(scr, by + bh - 1, bx, bw)
                scr.refresh()
                scr.timeout(-1)
                scr.getch()
                scr.timeout(200)
        elif key == ord("d") or key == ord("D"):
            # D = details (moved from X)
            if not scanning and aps and sel < len(aps):
                mrd.clear()
                mrd.send(f"info -a {sel}")
                time.sleep(0.5)
                info = mrd.drain()
                bw = min(50, w - 4)
                bh = min(len(info) + 3, h - 4)
                by, bx = (h - bh) // 2, (w - bw) // 2
                tui.panel_top(scr, by, bx, bw, aps[sel]["essid"])
                for ri, ln in enumerate(info[:bh - 3]):
                    tui.panel_side(scr, by + 1 + ri, bx, bw)
                    tui.put(scr, by + 1 + ri, bx + 2, ln[:bw - 4], bw - 4, val)
                tui.panel_bot(scr, by + bh - 1, bx, bw)
                scr.refresh()
                scr.timeout(-1)
                scr.getch()
                scr.timeout(200)
        elif key == ord("s") or key == ord("S"):
            if not scanning:
                start()

    if js:
        close_gamepad(js)
    scr.timeout(100)
    return None


# ── WiFi Attack ──────────────────────────────────────────────────────

_ATTACKS = [
    ("Deauth",        "attack -t deauth",     "Disconnect clients from selected APs", "⚡"),
    ("Deauth (tgt)",  "attack -t deauth -c",  "Target specific selected clients",     "⚡"),
    ("Beacon List",   "attack -t beacon -l",  "Broadcast SSIDs from SSID list",       "📡"),
    ("Beacon Random", "attack -t beacon -r",  "Random SSID beacon flood",             "⁂"),
    ("Beacon Clone",  "attack -t beacon -a",  "Clone selected AP beacons",            "◎"),
    ("Probe Flood",   "attack -t probe",      "Probe request flood",                  "⟫"),
    ("Rickroll",      "attack -t rickroll",    "Rickroll SSID beacon spam",            "♪"),
    ("CSA",           "attack -t csa",         "Channel Switch Announcement",          "⇋"),
    ("SAE",           "attack -t sae",         "WPA3 SAE flood",                       "⚿"),
]


def _wifi_attack(scr, mrd):
    """WiFi attack launcher with confirmation dialog."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0
    cols = 1
    attacking = False
    status = ""

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        st = "ATTACKING" if attacking else "SELECT"
        tui.put(scr, 0, 0,
                f" WIFI ATTACK  {st} ".center(w),
                w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        if not attacking:
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _ATTACKS]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)
        else:
            dim = curses.color_pair(C_DIM) | curses.A_DIM
            tui.put(scr, 2, 2, f"Running: {_ATTACKS[sel][0]}",
                    w - 4, curses.color_pair(C_CRIT) | curses.A_BOLD)
            for i, ln in enumerate(mrd.snap()[-(h - 6):]):
                y = 4 + i
                if y >= h - 3:
                    break
                tui.put(scr, y, 2, ln[:w - 4], w - 4, dim)

        if status:
            tui.put(scr, h - 2, 1, status[:w - 2], w - 2,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        foot = (" X Stop \u2502 B Back " if attacking
                else " \u2191\u2193\u2190\u2192 Navigate \u2502 A Launch \u2502 B Back ")
        tui.put(scr, h - 1, 0, foot.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if attacking:
                mrd.stop_scan()
                attacking = False
            break
        elif not attacking:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(_ATTACKS) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(_ATTACKS) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                name, cmd, _desc, _ic = _ATTACKS[sel]
                if _confirm(scr, "ATTACK", f"Launch {name}?"):
                    mrd.clear()
                    mrd.send(cmd)
                    mrd.state = _ATTACKING
                    attacking = True
                    status = f"Running: {name}"
                    time.sleep(0.3)
                    for ln in mrd.drain():
                        if "don't have any" in ln.lower() or "list is empty" in ln.lower():
                            status = ln
                            mrd.stop_scan()
                            attacking = False
                            break
        elif (key == ord("x") or key == ord("X")) and attacking:
            mrd.stop_scan()
            attacking = False
            status = "Attack stopped"

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Sniffers ─────────────────────────────────────────────────────────

_SNIFFERS = [
    ("Deauth",       "sniffdeauth",     "Detect deauth/disassoc frames",     "⚡"),
    ("PMKID",        "sniffpmkid",      "Capture EAPOL/PMKID handshakes",    "⚿"),
    ("PMKID+Deauth", "sniffpmkid -d",   "Active PMKID with forced deauth",   "⚿"),
    ("Beacon",       "sniffbeacon",      "All beacon frames (live feed)",      "◈"),
    ("Probe",        "sniffprobe",       "Probe requests from clients",       "⟫"),
    ("Raw",          "sniffraw",         "Raw 802.11 frame capture",          "▤"),
    ("Pwnagotchi",   "sniffpwn",         "Detect nearby pwnagotchis",        "☺"),
    ("SAE",          "sniffsae",         "WPA3 SAE commit frames",            "⚿"),
    ("Pineapple",    "sniffpinescan",    "Detect WiFi Pineapple APs",        "⚠"),
]


def _sniffers(scr, mrd):
    """Sniffer selector then streaming capture view."""
    js = open_gamepad()
    scr.timeout(200)
    sel = 0
    cols = 1
    sniffing = False
    log = []
    pkt = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not sniffing:
            tui.put(scr, 0, 0,
                    " SNIFFERS  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _SNIFFERS]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)
            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))
        else:
            for ln in mrd.drain():
                pkt += 1
                if _RE_DEAUTH.match(ln):
                    log.append(("CRIT", ln))
                elif _RE_EAPOL.match(ln):
                    log.append(("OK", f"*** {ln} ***"))
                elif _RE_PROBE.match(ln):
                    log.append(("WARN", ln))
                elif "Pwnagotchi" in ln:
                    log.append(("OK", ln))
                else:
                    log.append(("DIM", ln))
                if len(log) > 2000:
                    del log[:1000]

            name = _SNIFFERS[sel][0]
            tui.panel_top(scr, 0, 0, w, f"SNIFF {name.upper()}", f"{pkt} packets")

            vis = h - 4
            start = max(0, len(log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start + i
                if idx < len(log):
                    tag, text = log[idx]
                    if tag == "CRIT":
                        attr = curses.color_pair(C_CRIT)
                    elif tag == "OK":
                        attr = curses.color_pair(C_OK) | curses.A_BOLD
                    elif tag == "WARN":
                        attr = curses.color_pair(C_WARN)
                    else:
                        attr = dim
                    tui.put(scr, y, 2, text[:w - 4], w - 4, attr)

            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if sniffing:
                mrd.stop_scan()
                sniffing = False
            else:
                break
        elif not sniffing:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(_SNIFFERS) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(_SNIFFERS) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                mrd.clear()
                mrd.send(_SNIFFERS[sel][1])
                mrd.state = _SCANNING
                sniffing = True
                log.clear()
                pkt = 0
        else:
            if key == ord("x") or key == ord("X") or gp == "refresh":
                mrd.stop_scan()
                sniffing = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── BLE Tools ────────────────────────────────────────────────────────

_BLE = [
    ("Scan AirTags",    "sniffbt -t airtag",   "Detect Apple AirTags",          "⚠"),
    ("Scan Flippers",   "sniffbt -t flipper",  "Detect Flipper Zero devices",   "◈"),
    ("Scan Flock",      "sniffbt -t flock",    "Google Find My trackers",       "◈"),
    ("Scan Meta",       "sniffbt -t meta",     "Meta/Facebook BLE devices",     "◈"),
    ("Detect Skimmers", "sniffskim",           "Card skimmer BLE detection",    "⚠"),
    ("Spam All",        "blespam -t all",      "Apple+Samsung+Windows+Flipper", "☠"),
    ("Spam Apple",      "blespam -t apple",    "Apple notification spam",       "☠"),
    ("Spam Samsung",    "blespam -t samsung",  "Samsung BLE spam",              "☠"),
    ("Spam Windows",    "blespam -t windows",  "Windows Swift Pair spam",       "☠"),
    ("Spam Flipper",    "blespam -t flipper",  "Flipper Zero BLE spam",         "☠"),
]


def _ble_parse(ln, devices, now):
    """Parse a single BLE serial line, update *devices* dict (keyed by MAC)."""
    dtype, rssi, mac, name = None, None, None, ""

    m = _RE_SKIM.search(ln)
    if m:
        rssi, mac = int(m.group(1)), m.group(2).upper()
        dtype = "Skimmer"
    if not dtype:
        m = _RE_BLE_TYPE.search(ln)
        if m:
            kw = m.group(1).capitalize()
            rssi, mac = int(m.group(2)), m.group(3).upper()
            name = (m.group(4) or "").strip()
            dtype = {"Airtag": "AirTag", "Flipper": "Flipper",
                     "Flock": "Flock", "Meta": "Meta"}.get(kw, kw)
    if not dtype:
        m = _RE_BLE.search(ln)
        if m:
            rssi, mac = int(m.group(1)), m.group(2).upper()
            name = (m.group(3) or "").strip()
            dtype = "BLE"

    if dtype is None or mac is None:
        return

    # Infer type from keywords when generic BLE
    if dtype == "BLE":
        ll = ln.lower()
        if "airtag" in ll:
            dtype = "AirTag"
        elif "flipper" in ll:
            dtype = "Flipper"
        elif "skimmer" in ll or "potential" in ll:
            dtype = "Skimmer"

    pct = max(0, min(100, int((rssi + 100) * 100 / 100)))

    if mac in devices:
        dev = devices[mac]
        dev["rssi"] = rssi
        dev["last_seen"] = now
        if name:
            dev["name"] = name
        if dtype != "BLE":
            dev["type"] = dtype
        tui.push(dev["history"], pct)
    else:
        hist = tui.make_history(120)
        tui.push(hist, pct)
        devices[mac] = {
            "type": dtype,
            "mac": mac,
            "name": name,
            "rssi": rssi,
            "last_seen": now,
            "history": hist,
        }


def _ble(scr, mrd):
    """BLE scan and spam tools with real-time dashboard."""
    js = open_gamepad()
    scr.timeout(200)
    menu_sel = 0
    cols = 1
    active = False
    is_spam = False
    devices = {}          # MAC -> device dict
    dev_sel = 0           # cursor in device list
    scan_start = 0.0
    spam_log = []

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not active:
            # ── Menu mode ────────────────────────────────────────────
            tui.put(scr, 0, 0,
                    " BLE TOOLS  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _BLE]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, menu_sel)
            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))

        elif is_spam:
            # ── Spam mode: simple raw log ────────────────────────────
            for ln in mrd.drain():
                spam_log.append(ln)
                if len(spam_log) > 2000:
                    del spam_log[:1000]

            sname = _BLE[menu_sel][0]
            tui.panel_top(scr, 0, 0, w, f"BLE {sname.upper()}",
                          "broadcasting")
            vis = h - 4
            start_i = max(0, len(spam_log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start_i + i
                if idx < len(spam_log):
                    tui.put(scr, y, 2, spam_log[idx][:w - 4], w - 4, dim)
                elif i == vis // 2 and not spam_log:
                    tui.put(scr, y, 2, "Broadcasting... (silent mode)",
                            w - 4, dim)
            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        else:
            # ── Live BLE Dashboard ───────────────────────────────────
            now = time.time()

            # Parse incoming lines
            for ln in mrd.drain():
                _ble_parse(ln, devices, now)

            # Expire stale devices (>30s)
            stale = [m for m, d in devices.items()
                     if now - d["last_seen"] > 30]
            for m in stale:
                del devices[m]

            # Sort by RSSI (strongest first)
            dev_list = sorted(devices.values(),
                              key=lambda d: d["rssi"], reverse=True)

            # Clamp cursor
            if dev_list:
                dev_sel = max(0, min(dev_sel, len(dev_list) - 1))
            else:
                dev_sel = 0

            elapsed = int(now - scan_start)
            el_m, el_s = elapsed // 60, elapsed % 60

            # Graph panel height
            GR = 4
            # Alert bar
            skimmer_alert = None
            airtag_alert = None
            for d in dev_list:
                if d["type"] == "Skimmer":
                    if skimmer_alert is None or d["rssi"] > skimmer_alert:
                        skimmer_alert = d["rssi"]
                if d["type"] in ("AirTag", "Flock"):
                    if airtag_alert is None or d["rssi"] > airtag_alert:
                        airtag_alert = d["rssi"]
            has_alert = skimmer_alert is not None or airtag_alert is not None

            # Layout: hdr(1) + col_hdr(1) + device_rows + alert(0-1)
            #         + graph_hdr(1) + graph(GR) + graph_bot(1) + footer(1)
            bot_fixed = GR + 3 + (1 if has_alert else 0)
            list_rows = max(1, h - 3 - bot_fixed)

            # ── Device List panel ────────────────────────────────────
            scan_name = _BLE[menu_sel][0]
            tui.panel_top(scr, 0, 0, w, f"BLE {scan_name.upper()}",
                          f"{len(dev_list)} devices  {el_m}:{el_s:02d}")

            # Column header
            hdr_y = 1
            tui.panel_side(scr, hdr_y, 0, w)
            col_type = 9
            col_sig = 10
            col_rssi = 6
            col_age = 5
            hdr_txt = (f" {'TYPE':<{col_type}}"
                       f"{'SIGNAL':<{col_sig}}"
                       f"{'RSSI':>{col_rssi}}"
                       f"  {'MAC':<17}"
                       f"  {'AGE':>{col_age}}")
            tui.put(scr, hdr_y, 1, hdr_txt[:w - 2], w - 2,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)

            # Scrolling window
            scroll_off = 0
            if dev_sel >= list_rows:
                scroll_off = dev_sel - list_rows + 1
            visible_devs = dev_list[scroll_off:scroll_off + list_rows]

            for i, d in enumerate(visible_devs):
                y = 2 + i
                if y >= h - 1:
                    break
                tui.panel_side(scr, y, 0, w)

                real_idx = scroll_off + i
                is_selected = (real_idx == dev_sel)

                # Row color by type
                if d["type"] == "Skimmer":
                    row_attr = curses.color_pair(C_CRIT) | curses.A_BOLD
                elif d["type"] in ("AirTag", "Flipper", "Flock"):
                    row_attr = curses.color_pair(C_WARN)
                else:
                    row_attr = curses.color_pair(C_OK)

                if is_selected:
                    row_attr |= curses.A_REVERSE

                sig_bar = _rssi_bar(d["rssi"], 8)
                age = int(now - d["last_seen"])
                age_s = f"{age}s" if age < 60 else f"{age // 60}m"

                dname = d["name"] or d["type"]
                row = (f" {dname:<{col_type}}"
                       f"{sig_bar:<{col_sig}}"
                       f"{d['rssi']:>{col_rssi}}"
                       f"  {d['mac']:<17}"
                       f"  {age_s:>{col_age}}")
                tui.put(scr, y, 1, row[:w - 2], w - 2, row_attr)

            # Fill remaining list rows
            for i in range(len(visible_devs), list_rows):
                y = 2 + i
                if y >= h - 1:
                    break
                tui.panel_side(scr, y, 0, w)

            # ── Alert bar ────────────────────────────────────────────
            alert_y = 2 + list_rows
            if has_alert and alert_y < h - 1:
                tui.panel_side(scr, alert_y, 0, w)
                if skimmer_alert is not None:
                    amsg = f" \u26a0 Potential skimmer detected! {skimmer_alert}dBm"
                    tui.put(scr, alert_y, 1, amsg[:w - 2], w - 2,
                            curses.color_pair(C_CRIT) | curses.A_BOLD)
                elif airtag_alert is not None:
                    amsg = f" \u26a0 AirTag nearby {airtag_alert}dBm"
                    tui.put(scr, alert_y, 1, amsg[:w - 2], w - 2,
                            curses.color_pair(C_WARN) | curses.A_BOLD)
                alert_y += 1

            # ── Signal History panel (selected device) ───────────────
            graph_y = alert_y
            if dev_list and dev_sel < len(dev_list):
                sel_dev = dev_list[dev_sel]
                sig_detail = f"{sel_dev['rssi']}dBm  {sel_dev['mac']}"
                tui.panel_top(scr, graph_y, 0, w,
                              f"{sel_dev['type']} SIGNAL", sig_detail,
                              detail_pair=(curses.color_pair(
                                  _rssi_color(sel_dev["rssi"]))
                                  | curses.A_BOLD))
                graph_y += 1

                gw = w - 4
                if len(sel_dev["history"]) > 1:
                    col = _rssi_color(sel_dev["rssi"])
                    for row_str in tui.make_area(sel_dev["history"],
                                                 gw, GR):
                        if graph_y >= h - 1:
                            break
                        tui.panel_side(scr, graph_y, 0, w)
                        tui.put(scr, graph_y, 2, row_str, gw,
                                curses.color_pair(col))
                        graph_y += 1
                else:
                    for _ in range(GR):
                        if graph_y >= h - 1:
                            break
                        tui.panel_side(scr, graph_y, 0, w)
                        tui.put(scr, graph_y, 2, "waiting for data...",
                                gw, dim)
                        graph_y += 1
                if graph_y < h - 1:
                    tui.panel_bot(scr, graph_y, 0, w)
            else:
                tui.panel_top(scr, graph_y, 0, w, "SIGNAL", "no device")
                graph_y += 1
                for _ in range(GR):
                    if graph_y >= h - 1:
                        break
                    tui.panel_side(scr, graph_y, 0, w)
                    tui.put(scr, graph_y, 2, "no devices found",
                            w - 4, dim)
                    graph_y += 1
                if graph_y < h - 1:
                    tui.panel_bot(scr, graph_y, 0, w)

            tui.put(scr, h - 1, 0,
                    " \u2191\u2193 Nav \u2502 X Stop \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if active:
                mrd.stop_scan()
                active = False
                is_spam = False
            else:
                break
        elif not active:
            if key == curses.KEY_UP or key == ord("k"):
                menu_sel = max(0, menu_sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                menu_sel = min(len(_BLE) - 1, menu_sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                menu_sel = max(0, menu_sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                menu_sel = min(len(_BLE) - 1, menu_sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                name, cmd, _desc, _ic = _BLE[menu_sel]
                if "spam" in cmd and not _confirm(scr, "BLE SPAM",
                                                  f"Start {name}?"):
                    continue
                mrd.clear()
                mrd.send(cmd)
                mrd.state = _SCANNING
                active = True
                is_spam = "spam" in cmd
                devices.clear()
                dev_sel = 0
                scan_start = time.time()
                spam_log.clear()
        else:
            if key == ord("x") or key == ord("X") or gp == "refresh":
                mrd.stop_scan()
                active = False
                is_spam = False
            elif not is_spam:
                # Device list navigation (scan mode only)
                if key == curses.KEY_UP or key == ord("k"):
                    dev_sel = max(0, dev_sel - 1)
                elif key == curses.KEY_DOWN or key == ord("j"):
                    dev_sel = dev_sel + 1

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Signal Monitor ───────────────────────────────────────────────────

def _sigmon(scr, mrd):
    """Live RSSI waveforms per selected AP using braille area graphs."""
    js = open_gamepad()
    scr.timeout(500)

    # Use module-level targets saved by WiFi Scan (reliable)
    # instead of Marauder's flaky select -a state
    targets = list(_selected_targets)  # shallow copy

    if not targets:
        h, w = scr.getmaxyx()
        scr.erase()
        tui.panel_top(scr, 0, 0, w, "SIGNAL MONITOR", "no targets")
        tui.panel_side(scr, 2, 0, w)
        tui.put(scr, 2, 4,
                "No APs selected. Use WiFi Scan to select targets first.",
                w - 8, curses.color_pair(C_DIM))
        tui.panel_bot(scr, 4, 0, w)
        tui.put(scr, h - 1, 0, " B Back ".center(w), w,
                curses.color_pair(C_FOOTER))
        scr.refresh()
        scr.timeout(-1)
        scr.getch()
        if js:
            close_gamepad(js)
        scr.timeout(100)
        return

    mrd.clear()
    mrd.send("sniffbeacon")
    mrd.state = _SCANNING

    GR = 3

    while True:
        for ln in mrd.drain():
            m = _RE_AP.match(ln)
            if m:
                bssid = m.group(3)
                rssi = int(m.group(1))
                essid = m.group(4).strip()
                for t in targets:
                    if t["bssid"] == bssid or t["essid"] == essid:
                        t["bssid"] = bssid
                        t["rssi"] = rssi
                        tui.push(t["hist"], rssi)

        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        tui.panel_top(scr, 0, 0, w, "SIGNAL MONITOR",
                      f"{len(targets)} targets  sniffbeacon")

        y = 1
        gw = w - 6

        for t in targets:
            if y + GR + 2 >= h - 2:
                break

            rssi = t["rssi"]
            col = _rssi_color(rssi)
            bar = _rssi_bar(rssi, 8)

            tui.panel_top(scr, y, 1, w - 2, t["essid"][:20],
                          f"{bar} {rssi}dBm  Ch{t['ch']}",
                          detail_pair=curses.color_pair(col) | curses.A_BOLD)
            y += 1

            if len(t["hist"]) > 1:
                scaled = tui.make_history(120)
                for v in t["hist"]:
                    pct = max(0, min(100, int((v + 90) * 100 / 60)))
                    tui.push(scaled, pct)
                for row_str in tui.make_area(scaled, gw, GR):
                    tui.panel_side(scr, y, 1, w - 2)
                    tui.put(scr, y, 3, row_str, gw, curses.color_pair(col))
                    y += 1
            else:
                for _ in range(GR):
                    tui.panel_side(scr, y, 1, w - 2)
                    tui.put(scr, y, 3, "waiting for beacons...", gw, dim)
                    y += 1

            tui.panel_bot(scr, y, 1, w - 2)
            y += 1

        tui.put(scr, h - 1, 0,
                " X Stop \u2502 B Back ".center(w), w,
                curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key in (ord("q"), ord("Q"), ord("x"), ord("X")) or gp == "back":
            mrd.stop_scan()
            break

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Evil Portal ──────────────────────────────────────────────────────

def _portal(scr, mrd):
    """Evil portal / karma with credential capture stream."""
    js = open_gamepad()
    scr.timeout(200)
    active = False
    creds = []
    log = []
    sel = 0
    items = [
        ("Evil Portal",  "evilportal -c start", "Default captive portal", "⚠"),
        ("Karma Attack", "karma -p 0",          "Respond to all probes",  "◎"),
    ]

    cols = 1

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not active:
            tui.put(scr, 0, 0,
                    " EVIL PORTAL  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in items]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)

            if creds:
                # Show captured creds below tiles
                cy = h - 3
                for i, (u, p) in enumerate(creds[-2:]):
                    if cy - 1 - i < content_y + content_h:
                        break
                tui.put(scr, h - 2, 1,
                        f"{len(creds)} cred(s) captured"[:w - 2], w - 2,
                        curses.color_pair(C_OK) | curses.A_BOLD)

            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))
        else:
            for ln in mrd.drain():
                m = _RE_CRED.match(ln)
                if m:
                    creds.append((m.group(1), m.group(2)))
                    log.append(("CRIT", f"CAPTURED  u={m.group(1)}  p={m.group(2)}"))
                elif "client connected" in ln.lower():
                    log.append(("WARN", ln))
                elif "Evil Portal READY" in ln:
                    log.append(("OK", ln))
                else:
                    log.append(("DIM", ln))
                if len(log) > 1000:
                    del log[:500]

            tui.panel_top(scr, 0, 0, w, "EVIL PORTAL  ACTIVE",
                          f"{len(creds)} creds captured")
            vis = h - 4
            start_i = max(0, len(log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start_i + i
                if idx < len(log):
                    tag, text = log[idx]
                    if tag == "CRIT":
                        attr = curses.color_pair(C_CRIT) | curses.A_BOLD
                    elif tag == "OK":
                        attr = curses.color_pair(C_OK)
                    elif tag == "WARN":
                        attr = curses.color_pair(C_WARN)
                    else:
                        attr = dim
                    tui.put(scr, y, 2, text[:w - 4], w - 4, attr)
            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if active:
                mrd.stop_scan()
                active = False
            else:
                break
        elif not active:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(items) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(items) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                name, cmd, _desc, _ic = items[sel]
                if _confirm(scr, "PORTAL", f"Start {name}?"):
                    mrd.clear()
                    mrd.send(cmd)
                    mrd.state = _ATTACKING
                    active = True
                    log.clear()
        else:
            if key == ord("x") or key == ord("X"):
                mrd.stop_scan()
                active = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Network Recon ────────────────────────────────────────────────────

_NETRECON = [
    ("Ping Scan",  "pingscan",         "ICMP sweep (requires WiFi join)",  "⌗"),
    ("ARP Scan",   "arpscan",          "ARP sweep for local hosts",        "⌗"),
    ("ARP Full",   "arpscan -f",       "Full ARP scan (slower)",           "⌗"),
    ("Port SSH",   "portscan -s ssh",  "Scan for SSH (port 22)",           "⚿"),
    ("Port HTTP",  "portscan -s http", "Scan for HTTP (port 80)",          "◎"),
    ("Port HTTPS", "portscan -s https","Scan for HTTPS (port 443)",        "⚿"),
    ("Port RDP",   "portscan -s rdp",  "Scan for RDP (port 3389)",         "◎"),
    ("List IPs",   "list -i",          "Show discovered IPs",              "▤"),
]


def _netrecon(scr, mrd):
    """Network recon: ping, ARP, port scan."""
    js = open_gamepad()
    scr.timeout(200)
    sel = 0
    cols = 1
    active = False
    log = []

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not active:
            tui.put(scr, 0, 0,
                    " NETWORK RECON  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _NETRECON]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)
            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))
        else:
            for ln in mrd.drain():
                log.append(ln)
                if len(log) > 1000:
                    del log[:500]
            name = _NETRECON[sel][0]
            tui.panel_top(scr, 0, 0, w, f"RECON {name.upper()}",
                          f"{len(log)} results")
            vis = h - 4
            start_i = max(0, len(log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start_i + i
                if idx < len(log):
                    tui.put(scr, y, 2, log[idx][:w - 4], w - 4,
                            curses.color_pair(C_ITEM))
            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if active:
                mrd.stop_scan()
                active = False
            else:
                break
        elif not active:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(_NETRECON) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(_NETRECON) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                mrd.clear()
                mrd.send(_NETRECON[sel][1])
                mrd.state = _SCANNING
                active = True
                log.clear()
        else:
            if key == ord("x") or key == ord("X"):
                mrd.stop_scan()
                active = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Device Info ──────────────────────────────────────────────────────

_DEV = [
    ("Device Info",     "info",            "Chip, firmware, MAC, SD card",    "⚙"),
    ("Settings",        "settings",        "View Marauder settings",          "⚙"),
    ("Random AP MAC",   "randapmac",       "Randomize AP MAC address",        "⇋"),
    ("Random STA MAC",  "randstamac",      "Randomize station MAC address",   "⇋"),
    ("Clear AP List",   "clearlist -a",    "Clear scanned APs",               "▤"),
    ("Clear STA List",  "clearlist -c",    "Clear scanned stations",          "▤"),
    ("Clear SSID List", "clearlist -s",    "Clear SSID list",                 "▤"),
    ("LED Rainbow",     "led -p rainbow",  "Rainbow LED mode",                "⁂"),
    ("LED Off",         "led -s 000000",   "Turn off LED",                    "⁂"),
    ("Reboot",          "reboot",          "Restart ESP32",                   "⚡"),
]


def _device(scr, mrd):
    """Device info, settings, MAC spoofing, reboot."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0
    cols = 1
    output = []
    status = ""

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        tui.put(scr, 0, 0,
                f" DEVICE  {mrd.dev_path} ".center(w),
                w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        tiles = [{"name": n, "desc": d, "icon": ic}
                 for n, _cmd, d, ic in _DEV]
        content_y = 2
        content_h = h - content_y - 3
        cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                     tiles, sel)

        if output:
            oy = h - 3
            for i, ln in enumerate(output[-2:]):
                if oy + i >= h - 2:
                    break
                tui.put(scr, oy + i, 2, ln[:w - 4], w - 4, dim)

        if status:
            tui.put(scr, h - 2, 1, status[:w - 2], w - 2,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        tui.put(scr, h - 1, 0,
                " \u2191\u2193\u2190\u2192 Navigate \u2502 A Run \u2502 B Back ".center(w),
                w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - cols)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(_DEV) - 1, sel + cols)
        elif key == curses.KEY_LEFT or key == ord("h"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_RIGHT or key == ord("l"):
            sel = min(len(_DEV) - 1, sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            name, cmd, _desc, _ic = _DEV[sel]
            if name == "Reboot":
                if not _confirm(scr, "REBOOT", "Reboot ESP32?"):
                    continue
            mrd.clear()
            mrd.send(cmd)
            status = f"Sent: {cmd}"
            time.sleep(0.5)
            output = mrd.drain()
            if name == "Reboot":
                status = "ESP32 rebooting..."
                mrd.ok = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Raw Console ──────────────────────────────────────────────────────

def _console(scr, mrd):
    """Direct serial terminal for raw Marauder commands."""
    js = open_gamepad()
    scr.timeout(100)
    log = []
    cmd_buf = ""
    mrd.clear()

    while True:
        for ln in mrd.drain():
            log.append(ln)
            if len(log) > 2000:
                del log[:1000]

        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM
        grn = curses.color_pair(C_OK)

        tui.panel_top(scr, 0, 0, w, "SERIAL CONSOLE", mrd.dev_path)

        vis = h - 5
        start_i = max(0, len(log) - vis)
        for i in range(vis):
            y = 1 + i
            tui.panel_side(scr, y, 0, w)
            idx = start_i + i
            if idx < len(log):
                tui.put(scr, y, 2, log[idx][:w - 4], w - 4, grn)

        tui.panel_side(scr, h - 3, 0, w)
        tui.put(scr, h - 3, 2, "\u2500" * (w - 4), w - 4, dim)
        tui.panel_side(scr, h - 2, 0, w)
        prompt = f"> {cmd_buf}_"
        tui.put(scr, h - 2, 2, prompt[:w - 4], w - 4,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
        tui.panel_bot(scr, h - 1, 0, w)
        tui.put(scr, h - 1, 2, " ESC Back ", 10, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == 27 or gp == "back":
            break
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if cmd_buf:
                log.append(f"> {cmd_buf}")
                mrd.send(cmd_buf)
                cmd_buf = ""
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            cmd_buf = cmd_buf[:-1]
        elif 32 <= key < 127:
            cmd_buf += chr(key)

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Menu → function dispatch (index-synced with _MENU) ─────────────

_MENU_FNS = None

def _get_menu_fns():
    """Lazy-init menu dispatch dict so forward refs are resolved."""
    global _MENU_FNS
    if _MENU_FNS is None:
        _MENU_FNS = {
            0: _wifi_scan,
            1: _wifi_attack,
            2: _sniffers,
            3: _ble,
            4: _sigmon,
            5: _portal,
            6: _netrecon,
            7: _device,
            8: _console,
        }
    return _MENU_FNS
