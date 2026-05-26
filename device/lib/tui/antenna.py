"""TUI module: antenna array monitor (MT7921 / AC1200 2x2).

Live per-chain braille ribbon view. Chain A is the top trace, B the bottom,
and the band between them is filled and colored by the A-B delta — a marginal
connector shows up as the ribbon fattening and going red. Self-contained
(own parsers) so a fault here can only ever hide this one menu entry.

  q Back    +/- refresh rate    b on-demand BLE scan (ble1 RX test)
"""
import curses
import os
import re
import subprocess
import threading
import time
from collections import deque

from tui.framework import _tui_input_loop, open_gamepad
import tui_lib as tui

DBM_FLOOR, DBM_CEIL = -90, -20
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


# ── Pure parsers / helpers ──────────────────────────────────────────────
def parse_station_dump(text):
    out = {"bssid": None, "signal": None, "chains": [], "nss": None, "mcs": None,
           "rx_bitrate": None, "tx_bitrate": None,
           "tx_retries": None, "tx_failed": None, "last_ack": None}
    m = re.search(r"Station ([0-9a-fA-F:]{17})", text)
    if m:
        out["bssid"] = m.group(1)
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("signal:"):
            nums = re.findall(r"-?\d+", line)
            if nums:
                out["signal"] = int(nums[0])
            br = re.search(r"\[([^\]]+)\]", line)
            out["chains"] = ([int(x) for x in re.findall(r"-?\d+", br.group(1))]
                             if br else ([out["signal"]] if out["signal"] is not None else []))

    def num(pat, cast=int):
        mm = re.search(pat, text)
        return cast(mm.group(1)) if mm else None
    out["rx_bitrate"] = num(r"rx bitrate:\s*([\d.]+)", float)
    out["tx_bitrate"] = num(r"tx bitrate:\s*([\d.]+)", float)
    out["tx_retries"] = num(r"tx retries:\s*(\d+)")
    out["tx_failed"] = num(r"tx failed:\s*(\d+)")
    out["last_ack"] = num(r"last ack signal:\s*(-?\d+)")
    out["nss"] = num(r"NSS (\d+)")
    out["mcs"] = num(r"MCS (\d+)")
    return out


def chain_delta(chains):
    if len(chains) < 2:
        return None
    return float(abs(chains[0] - chains[1]))


def balance_status(delta):
    """Widened thresholds — diversity antennas normally differ a few dB."""
    if delta <= 6:
        return ("balanced", "ok")
    if delta <= 12:
        return ("drifting", "warn")
    return ("check connector", "bad")


def signal_severity(dbm):
    if dbm >= -55:
        return "ok"
    if dbm >= -67:
        return "warn"
    return "bad"


def parse_txpower_sku(text):
    peak_raw, vht80 = 0, []
    for raw in text.splitlines():
        if "(tmac)" not in raw:
            continue
        after = raw.split(":", 1)[1] if ":" in raw else ""
        vals = [int(x) for x in re.findall(r"\d+", after)]
        if vals:
            peak_raw = max(peak_raw, max(vals))
        if "VHT80 (tmac)" in raw:
            vht80 = vals
    return {"peak_dbm": peak_raw / 2 if peak_raw else None,
            "vht80_tmac_dbm": [v / 2 for v in vht80]}


def parse_link(text):
    if "Not connected" in text:
        return {"connected": False}
    out = {"connected": True, "bssid": None, "ssid": None, "signal": None, "freq": None}
    m = re.search(r"Connected to ([0-9a-fA-F:]{17})", text)
    if m:
        out["bssid"] = m.group(1)
    m = re.search(r"SSID:\s*(.+)", text)
    if m:
        out["ssid"] = m.group(1).strip()
    m = re.search(r"signal:\s*(-?\d+)", text)
    if m:
        out["signal"] = int(m.group(1))
    m = re.search(r"freq:\s*(\d+)", text)
    if m:
        out["freq"] = int(m.group(1))
    return out


def parse_iw_info(text):
    out = {"channel": None, "freq": None, "width": None, "ssid": None}
    m = re.search(r"channel (\d+) \((\d+) MHz\)", text)
    if m:
        out["channel"], out["freq"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"width:\s*(\d+) MHz", text)
    if m:
        out["width"] = int(m.group(1))
    m = re.search(r"^\s*ssid (.+)$", text, re.M)
    if m:
        out["ssid"] = m.group(1).strip()
    return out


def parse_hci_info(text):
    up = bool(re.search(r"\bUP\b", text)) and not re.search(r"\bDOWN\b", text)
    ver = re.search(r"HCI Version:\s*([\d.]+)", text)
    man = re.search(r"Manufacturer:\s*([^,(\n]+)", text)
    return {"up": up, "version": ver.group(1) if ver else None,
            "manufacturer": man.group(1).strip() if man else None}


def parse_ble_scan(text):
    devs = {}
    for line in text.splitlines():
        m = re.search(r"Device ([0-9A-Fa-f:]{17})", line)
        if not m:
            continue
        mac = m.group(1)
        d = devs.setdefault(mac, {"mac": mac, "name": None, "rssi": None})
        r = re.search(r"RSSI:\s*(-?\d+)", line)
        if r:
            d["rssi"] = int(r.group(1))
            continue
        rest = line.split(mac, 1)[1].strip()
        nm = re.match(r"Name:\s*(.+)", rest)
        if nm:
            d["name"] = nm.group(1).strip()
            continue
        tag = re.match(r"\[(\w+)\]", line)
        if tag and tag.group(1) == "NEW" and rest and rest != mac.replace(":", "-"):
            d["name"] = rest
    return sorted(devs.values(), key=lambda d: (d["rssi"] is None, -(d["rssi"] or 0)))


def smooth(values, alpha=0.35):
    """Exponential moving average — tames per-poll RSSI jitter."""
    out, s = [], None
    for v in values:
        s = v if s is None else alpha * v + (1 - alpha) * s
        out.append(s)
    return out


def autorange(*series, pad=0.15, min_span=10.0):
    vals = [v for s in series for v in s]
    if not vals:
        return (-80.0, -30.0)
    lo, hi = min(vals), max(vals)
    if hi - lo < min_span:
        mid = (hi + lo) / 2
        lo, hi = mid - min_span / 2, mid + min_span / 2
    p = (hi - lo) * pad
    return (max(DBM_FLOOR, lo - p), min(DBM_CEIL, hi + p))


def _ribbon_rows(hist_a, hist_b, cw, ch, lo, hi):
    """Fill the braille band between the two chain traces."""
    c = tui.BrailleCanvas(cw, ch)
    da, db = list(hist_a)[-c.pw:], list(hist_b)[-c.pw:]
    n = min(len(da), len(db))
    da, db = da[-n:], db[-n:]

    def ym(v):
        if hi == lo:
            return c.ph // 2
        return max(0, min(c.ph - 1, round((hi - v) / (hi - lo) * (c.ph - 1))))
    for i in range(n):
        ya, yb = ym(da[i]), ym(db[i])
        for py in range(min(ya, yb), max(ya, yb) + 1):
            c.set(i, py)
    return c.render()


# ── Data gathering ──────────────────────────────────────────────────────
def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return ""


def iface_phy(iface):
    try:
        return os.path.basename(os.readlink(f"/sys/class/net/{iface}/phy80211"))
    except OSError:
        return None


def read_txpower_sku(iface):
    phy = iface_phy(iface)
    if not phy:
        return {}
    path = f"/sys/kernel/debug/ieee80211/{phy}/mt76/txpower_sku"
    try:
        with open(path) as f:
            return parse_txpower_sku(f.read())
    except (OSError, PermissionError):
        return {}


def operstate(iface):
    try:
        with open(f"/sys/class/net/{iface}/operstate") as f:
            return f.read().strip()
    except OSError:
        return None


def detect_iface(preferred="wlan1"):
    if os.path.exists(f"/sys/class/net/{preferred}/phy80211"):
        return preferred
    base = "/sys/class/net"
    try:
        for name in sorted(os.listdir(base)):
            if os.path.exists(f"{base}/{name}/phy80211"):
                return name
    except OSError:
        pass
    return preferred


def hci_blocks(text):
    blocks, cur, name = [], [], None
    for line in text.splitlines():
        m = re.match(r"(hci\d+):", line)
        if m:
            if name:
                blocks.append((name, "\n".join(cur)))
            name, cur = m.group(1), [line]
        elif name:
            cur.append(line)
    if name:
        blocks.append((name, "\n".join(cur)))
    return blocks


def find_usb_bt():
    text = _run(["hciconfig", "-a"])
    chosen = None
    for name, block in hci_blocks(text):
        info = parse_hci_info(block)
        bd = re.search(r"BD Address:\s*([0-9A-Fa-f:]{17})", block)
        info.update(hci=name, bd=bd.group(1) if bd else None,
                    usb=("Bus: USB" in block))
        if info["usb"]:
            return info
        chosen = chosen or info
    return chosen


def ble_scan(ctrl_bd=None, timeout=6):
    """Timed LE discovery; powers the controller on first."""
    try:
        proc = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
        if ctrl_bd:
            proc.stdin.write(f"select {ctrl_bd}\n")
        proc.stdin.write("power on\n")
        proc.stdin.write("scan on\n")
        proc.stdin.flush()
        time.sleep(timeout)
        proc.stdin.write("scan off\nexit\n")
        proc.stdin.flush()
        out, _ = proc.communicate(timeout=5)
        return parse_ble_scan(out)
    except Exception:
        return []


def gather(iface, txcache, bt):
    st = parse_station_dump(_run(["iw", "dev", iface, "station", "dump"]))
    info = parse_iw_info(_run(["iw", "dev", iface, "info"]))
    conns = []
    for dev, label in [("wlan0", "onboard"), (iface, "AC1200")]:
        if not os.path.exists(f"/sys/class/net/{dev}"):
            continue
        link = parse_link(_run(["iw", "dev", dev, "link"]))
        conns.append({"dev": dev, "label": label, "link": link,
                      "operstate": operstate(dev)})
    return {"st": st, "info": info, "conns": conns, "tx": txcache, "bt": bt}


def _real_power(tx, mcs):
    if not tx:
        return "needs sudo"
    vht = tx.get("vht80_tmac_dbm") or []
    if vht and mcs is not None and mcs < len(vht):
        return f"~{vht[mcs]:.0f}dBm@mcs{mcs}"
    if tx.get("peak_dbm"):
        return f"~{tx['peak_dbm']:.0f}dBm pk"
    return "—"


# ── Render ──────────────────────────────────────────────────────────────
def _sev_attr(sev, bold=True):
    pair = {"ok": tui.C_OK, "warn": tui.C_WARN, "bad": tui.C_CRIT}.get(sev, tui.C_DIM)
    a = curses.color_pair(pair)
    return a | curses.A_BOLD if bold else a


def _draw(scr, iface, state, ui, frame):
    scr.erase()
    h, w = scr.getmaxyx()
    st, info, tx, bt = state["st"], state["info"], state["tx"], state["bt"]
    hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
    dim = curses.color_pair(tui.C_DIM)
    y = 0

    tui.put(scr, y, 1, f"ANTENNA ARRAY — {iface} / MT7921U", w - 2, hdr)
    y += 1
    tui.put(scr, y, 1, f"AP {info.get('ssid') or '—'}  ch{info.get('channel')} "
            f"{info.get('freq')}MHz {info.get('width')}M  NSS {st.get('nss')}",
            w - 2, dim)
    y += 1
    sig = st.get("signal")
    if sig is not None:
        tui.put(scr, y, 1, f"link {sig} dBm", 13, _sev_attr(signal_severity(sig)))
        tui.put(scr, y, 14, f"rx {st.get('rx_bitrate')} / tx {st.get('tx_bitrate')} "
                f"Mbit/s", w - 16, dim)
    else:
        tui.put(scr, y, 1, "no link", 12, _sev_attr("bad"))
    y += 2

    a, b = ui["hist_a"], ui["hist_b"]
    if len(a) and len(b):
        sa, sb = smooth(list(a)), smooth(list(b))
        lo, hi = autorange(sa, sb)
        delta = abs(sa[-1] - sb[-1])
        label, sev = balance_status(delta)
        cw = max(8, w - 9)
        rows = _ribbon_rows(sa, sb, cw, 4, lo, hi)
        n = len(rows)
        for i, r in enumerate(rows):
            tag = (f"{hi:>4.0f} ┤" if i == 0 else
                   f"{lo:>4.0f} ┤" if i == n - 1 else "     │")
            tui.put(scr, y, 0, f"{tag} {r}", w - 2, _sev_attr(sev, bold=False))
            if i == 0:
                tui.put(scr, y, w - 2, "A", 1, _sev_attr(sev))
            elif i == n - 1:
                tui.put(scr, y, w - 2, "B", 1, _sev_attr(sev))
            y += 1
        da, db = sa[-1], sb[-1]
        mark = {"ok": "✓", "warn": "⚠", "bad": "✗"}[sev]
        tui.put(scr, y, 1, f"A {da:>5.0f} dBm   B {db:>5.0f} dBm   "
                f"Δ {delta:>4.1f} dB  {mark} {label}", w - 2, _sev_attr(sev))
        y += 1
    elif len(a):
        tui.put(scr, y, 1, "single chain (NSS 1) — no A/B delta", w - 2,
                _sev_attr("warn"))
        y += 1
    else:
        tui.put(scr, y, 1, "no per-chain data (not associated)", w - 2, dim)
        y += 1
    y += 1

    tui.put(scr, y, 1, f"TX retries {st.get('tx_retries')} failed "
            f"{st.get('tx_failed')}  ACK {st.get('last_ack')}  "
            f"real {_real_power(tx, st.get('mcs'))}", w - 2, dim)
    y += 2

    tui.put(scr, y, 1, "Connections", w - 2, hdr)
    y += 1
    for con in state["conns"]:
        link = con["link"]
        if link.get("connected"):
            s = link.get("signal")
            txt = f"▲ {link.get('ssid')}  {s} dBm"
            attr = _sev_attr(signal_severity(s), bold=False) if s is not None else dim
        else:
            note = ("antenna disconnected" if con["dev"] == "wlan0"
                    else con["operstate"] or "down")
            txt, attr = f"DOWN ({note})", dim
        tui.put(scr, y, 1, f"{con['dev']:6} {con['label']:8}", 16, dim)
        tui.put(scr, y, 17, txt, w - 18, attr)
        y += 1
    if bt:
        st_txt = (f"UP  {bt.get('manufacturer')} {bt.get('version')}"
                  if bt.get("up") else "DOWN")
        tui.put(scr, y, 1, f"{'ble1':6} {bt.get('hci', 'hci?'):8}", 16, dim)
        tui.put(scr, y, 17, st_txt, w - 18,
                _sev_attr("ok" if bt.get("up") else "bad", bold=False))
        y += 1

    if ui["ble_scanning"]:
        tui.put(scr, y, 1, f"BLE RX  {SPIN[frame % len(SPIN)]} discovering…",
                w - 2, _sev_attr("warn"))
        y += 1
    elif ui["ble"] is not None:
        measured = [d for d in ui["ble"] if d["rssi"] is not None]
        tui.put(scr, y, 1, f"BLE RX: {len(measured)} w/ RSSI, "
                f"{len(ui['ble']) - len(measured)} seen", w - 2,
                curses.color_pair(tui.C_CAT))
        y += 1
        for d in measured[: max(0, h - y - 2)]:
            tui.put(scr, y, 3, f"{d['rssi']:>4} dBm  {d['name'] or d['mac']}",
                    w - 4, _sev_attr(signal_severity(d["rssi"])))
            y += 1

    tui.put(scr, h - 1, 1, "q Back   b BLE scan", w - 2,
            curses.color_pair(tui.C_FOOTER))
    scr.refresh()


def _start_ble_scan(ui, bt):
    if ui["ble_scanning"]:
        return
    ui["ble_scanning"] = True
    ctrl = bt.get("bd") if bt else None

    def worker():
        ui["ble"] = ble_scan(ctrl, timeout=ui["ble_timeout"])
        ui["ble_scanning"] = False

    threading.Thread(target=worker, daemon=True).start()


def run_antenna_array(scr):
    """Live per-chain antenna ribbon monitor (MT7921 2x2)."""
    js = open_gamepad()
    try:
        tui.init_gauge_colors()
    except Exception:
        pass
    iface = detect_iface()
    ui = {"ble_timeout": 6,
          "hist_a": deque(maxlen=200), "hist_b": deque(maxlen=200),
          "ble": None, "ble_scanning": False}
    txcache = read_txpower_sku(iface)
    bt = find_usb_bt()
    frame = 0
    try:
        while True:
            if frame % 12 == 0:
                bt = find_usb_bt()
                if not txcache.get("vht80_tmac_dbm"):
                    txcache = read_txpower_sku(iface)
            state = gather(iface, txcache, bt)
            chains = state["st"].get("chains", [])
            if chains:
                ui["hist_a"].append(chains[0])
            if len(chains) >= 2:
                ui["hist_b"].append(chains[1])
            _draw(scr, iface, state, ui, frame)

            scr.timeout(250)  # always fast — no user rate control
            key, gp = _tui_input_loop(scr, js)
            if key in (ord("q"), ord("Q"), 27) or gp == "back":
                break
            elif key == ord("b"):
                _start_ble_scan(ui, bt)
            frame += 1
    finally:
        if js:
            js.close()
        scr.timeout(100)


HANDLERS = {"_antenna_array": run_antenna_array}
