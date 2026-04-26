"""TUI module: MimiClaw AI agent chat portal."""

import curses
import datetime
import json
import os
import re
import textwrap
import time

from tui.framework import (
    C_CAT,
    C_DIM,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    _tui_input_loop,
    open_gamepad,
    run_confirm,
    run_stream,
)

WS_PORT = 18789
CHAT_ID = "tui_console"
FLASH_DIR = os.path.expanduser("~/mimiclaw-flash")
_IP_CACHE_FILE = os.path.expanduser("~/.config/uconsole/mimiclaw.json")
_WIFI_STATUS_IP_RE = re.compile(r"^\s*IP:\s*(\d+\.\d+\.\d+\.\d+)\s*$", re.MULTILINE)


def _load_cached_ip():
    """Return last-known IP from cache, or None if unreadable/absent."""
    try:
        with open(_IP_CACHE_FILE) as f:
            data = json.load(f)
        ip = data.get("ip")
        return ip if isinstance(ip, str) and ip and ip != "0.0.0.0" else None
    except (OSError, ValueError):
        return None


def _save_ip(ip, ssid=None):
    """Persist discovered IP (chmod 600). Silent on failure — cache is advisory."""
    try:
        os.makedirs(os.path.dirname(_IP_CACHE_FILE), exist_ok=True)
        payload = {
            "ip": ip,
            "ssid": ssid,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        tmp = _IP_CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _IP_CACHE_FILE)
    except OSError:
        pass


def _probe_ip_via_serial(port=None, timeout=2.0):
    """Ask MimiClaw for its current IP over serial. Returns IP string or None.

    Uses esp32_detect.open_ready so we don't fight the open-time chip
    reset on ESP32-S3 USB-Serial/JTAG.
    """
    from tui import esp32_detect
    ser, _fw = esp32_detect.open_ready(port=port, open_timeout=timeout)
    if ser is None:
        return None
    try:
        ser.reset_input_buffer()
        ser.write(b"wifi_status\r\n")
        time.sleep(1.0)
        buf = b""
        for _ in range(20):
            if ser.in_waiting:
                buf += ser.read(ser.in_waiting)
                time.sleep(0.1)
            else:
                break
        text = buf.decode("utf-8", errors="replace")
        m = _WIFI_STATUS_IP_RE.search(text)
        if not m:
            return None
        ip = m.group(1)
        return ip if ip != "0.0.0.0" else None
    finally:
        esp32_detect._close_fast(ser)


def _resolve_ip(prefer_fresh=False):
    """Return a usable MimiClaw IP, or None if device is offline / unreachable.

    Strategy: cache first (fast path), serial probe on miss or when caller
    explicitly asks for a fresh read (e.g. after a WS connect failure).
    Updates the cache whenever the serial probe returns a real IP.
    """
    if not prefer_fresh:
        cached = _load_cached_ip()
        if cached:
            return cached
    fresh = _probe_ip_via_serial()
    if fresh:
        _save_ip(fresh)
    return fresh


# ── WiFi config helpers ──────────────────────────────────────────────────

_WIFI_SCAN_LINE_RE = re.compile(
    r"\[(\d+)\]\s+SSID=(.*?)\s+RSSI=(-?\d+)\s+CH=(\d+)\s+Auth=(\d+)\s*$"
)
_WIFI_SAVED_RE = re.compile(r"WiFi credentials saved for SSID:\s*(.*?)\s*$",
                            re.MULTILINE)


def _wifi_scan_parse(raw):
    """Parse MimiClaw's `wifi_scan` output into a sorted list of networks.

    Returns list of dicts with keys: idx, ssid, rssi, ch, auth.
    Sorted by rssi descending. Empty SSIDs and duplicates dropped.
    """
    seen = set()
    nets = []
    for line in raw.splitlines():
        m = _WIFI_SCAN_LINE_RE.search(line)
        if not m:
            continue
        ssid = m.group(2).strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        nets.append({
            "idx": int(m.group(1)),
            "ssid": ssid,
            "rssi": int(m.group(3)),
            "ch": int(m.group(4)),
            "auth": int(m.group(5)),
        })
    nets.sort(key=lambda n: n["rssi"], reverse=True)
    return nets


def _format_apply_payload(ssid, password):
    """Build the `set_wifi` serial payload. Always quotes SSID.

    Rejects SSID or password containing \\r or \\n (would break the line
    protocol). Escapes embedded double-quotes via backslash.
    Returns bytes ready to write to the serial port.
    """
    for name, val in (("SSID", ssid), ("password", password or "")):
        if "\r" in val or "\n" in val:
            raise ValueError(f"{name} contains a newline — refusing")
    esc = (ssid or "").replace("\\", "\\\\").replace('"', '\\"')
    pw = password or ""
    return f'set_wifi "{esc}" {pw}\r\n'.encode("utf-8")


def _signal_bars(rssi):
    """Map RSSI (dBm) → 4-char block glyph, matches iwconfig-ish aesthetic."""
    if rssi >= -50:
        return "▂▄▆█"
    if rssi >= -60:
        return "▂▄▆_"
    if rssi >= -70:
        return "▂▄__"
    if rssi >= -80:
        return "▂___"
    return "____"


def _get_uconsole_wifi():
    """Read the currently-active uConsole WiFi (SSID, PSK). Returns tuple or None."""
    import subprocess
    try:
        name = subprocess.check_output(
            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"],
            text=True, timeout=3,
        )
        ssid = None
        for line in name.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[1] == "802-11-wireless":
                ssid = parts[0]
                break
        if not ssid:
            return None
        psk = subprocess.check_output(
            ["sudo", "-n", "nmcli", "-s", "-g",
             "802-11-wireless-security.psk", "connection", "show", ssid],
            text=True, timeout=3, stderr=subprocess.DEVNULL,
        ).strip()
        return (ssid, psk) if psk else None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def _serial_write_and_read(cmd, wait_secs=1.0, timeout=2.0):
    """One-shot serial write → read. Returns decoded response, or None on port error."""
    from tui import esp32_detect
    ser, _fw = esp32_detect.open_ready(open_timeout=timeout)
    if ser is None:
        return None
    try:
        ser.reset_input_buffer()
        ser.write(cmd)
        time.sleep(wait_secs)
        buf = b""
        for _ in range(int(wait_secs * 10) + 10):
            if ser.in_waiting:
                buf += ser.read(ser.in_waiting)
                time.sleep(0.1)
            else:
                break
        return buf.decode("utf-8", errors="replace")
    finally:
        esp32_detect._close_fast(ser)


def _apply_wifi_creds(scr, ssid, password):
    """Send set_wifi + restart, poll for reconnect. Returns (ok, ip_or_error)."""
    try:
        payload = _format_apply_payload(ssid, password)
    except ValueError as e:
        return False, str(e)

    from tui import esp32_detect
    ser, _fw = esp32_detect.open_ready(open_timeout=2)
    if ser is None:
        return False, "Serial port busy or chip silent. Close Serial Monitor and retry."

    try:
        # Step 1: set_wifi + wait for confirmation
        ser.reset_input_buffer()
        ser.write(payload)
        deadline = time.time() + 3.0
        saved_buf = ""
        while time.time() < deadline:
            if ser.in_waiting:
                saved_buf += ser.read(ser.in_waiting).decode(
                    "utf-8", "replace")
                if _WIFI_SAVED_RE.search(saved_buf):
                    break
            time.sleep(0.1)
        else:
            return False, "Timed out waiting for 'credentials saved' confirmation"
        # Step 2: restart
        ser.write(b"restart\r\n"); time.sleep(0.2)
    finally:
        esp32_detect._close_fast(ser)

    # Step 3: progress screen while device reboots (~10s boot + connect time)
    h, w = scr.getmaxyx()
    for i in range(10):
        scr.erase()
        msg = f"  Restarting MimiClaw …{'.' * (i % 4):<3}"
        try:
            scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                        curses.color_pair(C_HEADER) | curses.A_BOLD)
        except curses.error:
            pass
        scr.refresh()
        time.sleep(1.0)

    # Step 4: poll wifi_status up to 15s for a real IP
    deadline = time.time() + 15.0
    while time.time() < deadline:
        ip = _probe_ip_via_serial()
        if ip:
            _save_ip(ip, ssid=ssid)
            return True, ip
        elapsed = int(time.time() - deadline + 15)
        scr.erase()
        msg = f"  Waiting for WiFi connection … ({elapsed}/15s)"
        try:
            scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
        except curses.error:
            pass
        scr.refresh()
        time.sleep(2.0)

    return False, (f"Credentials saved but no IP after 25s. "
                   f"SSID may be wrong/out of range, or 5GHz-only.")


def _wifi_text_input(scr, prompt, y, masked=False, initial=""):
    """Single-line text input. Returns str, or None on cancel."""
    h, w = scr.getmaxyx()
    buf = initial
    reveal = False
    scr.timeout(-1)
    try:
        while True:
            line = prompt + (buf if not masked or reveal else "•" * len(buf))
            try:
                scr.addnstr(y, 2, " " * (w - 4), w - 4,
                            curses.color_pair(C_ITEM))
                scr.addnstr(y, 2, line[:w - 4], w - 4,
                            curses.color_pair(C_SEL) | curses.A_BOLD)
                if masked:
                    hint = " ⏎ submit · Esc cancel · Ctrl-R reveal "
                else:
                    hint = " ⏎ submit · Esc cancel "
                scr.addnstr(h - 1, 0, hint.center(w), w,
                            curses.color_pair(C_FOOTER))
            except curses.error:
                pass
            scr.refresh()
            k = scr.getch()
            if k in (27,):  # Esc
                return None
            if k in (10, 13, curses.KEY_ENTER):
                return buf
            if k in (curses.KEY_BACKSPACE, 127, 8):
                buf = buf[:-1]
            elif masked and k == 18:  # Ctrl-R
                reveal = not reveal
            elif 32 <= k < 127:
                buf += chr(k)
    finally:
        scr.timeout(100)


def _wifi_pick_from_scan(scr):
    """Run wifi_scan over serial, show picker. Returns chosen SSID or None."""
    h, w = scr.getmaxyx()
    scr.erase()
    msg = "  Scanning … (up to 6s)"
    try:
        scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    except curses.error:
        pass
    scr.refresh()

    raw = _serial_write_and_read(b"wifi_scan\r\n", wait_secs=6.0, timeout=8.0)
    if raw is None:
        return _wifi_msg_and_wait(scr, "Serial port busy. Close Serial Monitor and retry.")
    nets = _wifi_scan_parse(raw)
    if not nets:
        return _wifi_msg_and_wait(scr, "No networks found. Try Manual entry.")

    sel = 0
    scr.timeout(-1)
    try:
        while True:
            scr.erase()
            title = " Select network "
            try:
                scr.addnstr(0, 0, title.center(w), w,
                            curses.color_pair(C_HEADER) | curses.A_BOLD)
            except curses.error:
                pass
            for i, net in enumerate(nets[:h - 4]):
                marker = "▶" if i == sel else " "
                lock = "🔒" if net["auth"] != 0 else "  "
                bars = _signal_bars(net["rssi"])
                line = f" {marker} {bars}  {lock} {net['ssid'][:w - 20]}"
                attr = (curses.color_pair(C_SEL) | curses.A_BOLD
                        if i == sel else curses.color_pair(C_ITEM))
                try:
                    scr.addnstr(2 + i, 1, line, w - 2, attr)
                except curses.error:
                    pass
            hint = " ↑↓ select · ⏎ choose · Esc back "
            try:
                scr.addnstr(h - 1, 0, hint.center(w), w,
                            curses.color_pair(C_FOOTER))
            except curses.error:
                pass
            scr.refresh()
            k = scr.getch()
            if k in (27,):
                return None
            if k in (curses.KEY_UP, ord("k")):
                sel = (sel - 1) % len(nets)
            elif k in (curses.KEY_DOWN, ord("j")):
                sel = (sel + 1) % len(nets)
            elif k in (10, 13, curses.KEY_ENTER):
                return nets[sel]
    finally:
        scr.timeout(100)


def _wifi_msg_and_wait(scr, msg):
    """Show a centered message, wait for any key, return None."""
    h, w = scr.getmaxyx()
    scr.erase()
    try:
        scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
        scr.addnstr(h - 1, 0, " Press any key ".center(w), w,
                    curses.color_pair(C_FOOTER))
    except curses.error:
        pass
    scr.refresh()
    scr.timeout(-1)
    scr.getch()
    scr.timeout(100)
    return None


def run_mimiclaw_wifi(scr):
    """MimiClaw WiFi config panel — scan / copy / manual / disconnect."""
    h, w = scr.getmaxyx()
    scr.timeout(-1)
    options = [
        ("scan",       "Scan nearby networks"),
        ("copy",       "Copy from uConsole WiFi"),
        ("manual",     "Enter manually"),
        ("disconnect", "Disconnect"),
    ]
    sel = 0
    try:
        while True:
            ip = _load_cached_ip() or _probe_ip_via_serial()
            status = f"Current:  IP {ip}" if ip else "Current:  not connected"
            scr.erase()
            try:
                scr.addnstr(0, 0, " MimiClaw WiFi ".center(w), w,
                            curses.color_pair(C_HEADER) | curses.A_BOLD)
                scr.addnstr(2, 2, status, w - 4, curses.color_pair(C_DIM))
            except curses.error:
                pass
            for i, (_, label) in enumerate(options):
                marker = "▶" if i == sel else " "
                line = f" {marker}  {label}"
                attr = (curses.color_pair(C_SEL) | curses.A_BOLD
                        if i == sel else curses.color_pair(C_ITEM))
                try:
                    scr.addnstr(4 + i, 2, line, w - 4, attr)
                except curses.error:
                    pass
            hint = " ↑↓ select · ⏎ choose · Esc back "
            try:
                scr.addnstr(h - 1, 0, hint.center(w), w,
                            curses.color_pair(C_FOOTER))
            except curses.error:
                pass
            scr.refresh()
            k = scr.getch()
            if k in (27, ord("q"), ord("Q")):
                return
            if k in (curses.KEY_UP, ord("k")):
                sel = (sel - 1) % len(options)
            elif k in (curses.KEY_DOWN, ord("j")):
                sel = (sel + 1) % len(options)
            elif k in (10, 13, curses.KEY_ENTER):
                action = options[sel][0]
                if action == "scan":
                    net = _wifi_pick_from_scan(scr)
                    if net:
                        _wifi_apply_flow(scr, net["ssid"], open_net=(net["auth"] == 0))
                elif action == "copy":
                    creds = _get_uconsole_wifi()
                    if not creds:
                        _wifi_msg_and_wait(scr, "Could not read uConsole WiFi (sudo nmcli required)")
                        continue
                    ssid, psk = creds
                    if run_confirm(scr, f"Copy '{ssid}' to MimiClaw?"):
                        _wifi_apply_flow(scr, ssid, password=psk)
                elif action == "manual":
                    ssid = _wifi_text_input(scr, "SSID: ", h // 2 - 1)
                    if not ssid:
                        continue
                    pw = _wifi_text_input(scr, "Password: ", h // 2 + 1,
                                          masked=True)
                    if pw is None:
                        continue
                    _wifi_apply_flow(scr, ssid, password=pw)
                elif action == "disconnect":
                    if not run_confirm(scr, "Disconnect MimiClaw WiFi?"):
                        continue
                    _wifi_apply_flow(scr, "", password="")
    finally:
        scr.timeout(100)


def _wifi_apply_flow(scr, ssid, password=None, open_net=False):
    """Shared apply wrapper — prompts for password if needed, runs pipeline, reports."""
    h, w = scr.getmaxyx()
    if password is None and not open_net:
        pw = _wifi_text_input(scr, f"Password for {ssid}: ", h // 2,
                              masked=True)
        if pw is None:
            return
        password = pw
    if password is None:
        password = ""
    ok, result = _apply_wifi_creds(scr, ssid, password)
    msg = (f"Connected — IP {result}" if ok else f"Failed — {result}")
    _wifi_msg_and_wait(scr, msg)


def run_mimiclaw_settings(scr):
    """MimiClaw Settings subfold. Currently just WiFi; room for more."""
    # Delegated via SUBMENUS dict — see framework.py wiring. This stub
    # exists as an explicit entry point for future non-menu settings pages.
    run_mimiclaw_wifi(scr)


# ── Markdown rendering for chat messages ─────────────────────────────────
#
# Curses terminal, no Rich. Support the subset MimiClaw's LLM output actually
# uses: headings, bullet lists, blockquotes, fenced code blocks, inline
# **bold** and `code`. Returns a flat list of "rendered lines", where each
# line is a list of (text, attr) spans ready for curses.addnstr.

_MD_INLINE_RE = re.compile(r'\*\*([^*]+?)\*\*|`([^`]+?)`')


def _md_inline(line, base_attr):
    """Split a single line into (text, attr) spans for inline **bold**/`code`."""
    spans = []
    pos = 0
    for m in _MD_INLINE_RE.finditer(line):
        if m.start() > pos:
            spans.append((line[pos:m.start()], base_attr))
        if m.group(1):  # **bold**
            spans.append((m.group(1), base_attr | curses.A_BOLD))
        elif m.group(2):  # `code`
            spans.append((m.group(2), base_attr | curses.A_REVERSE))
        pos = m.end()
    if pos < len(line):
        spans.append((line[pos:], base_attr))
    return spans or [('', base_attr)]


def _md_render(text, width):
    """Render a markdown-ish message body into a list of line-span-lists."""
    rendered = []
    in_code = False
    for raw in text.split('\n'):
        # Fenced code block toggle
        if raw.lstrip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            for w in (textwrap.wrap(raw, width) or [raw or '']):
                rendered.append([(w, curses.A_REVERSE)])
            continue
        # Headings
        if raw.startswith('### '):
            rendered.append([(raw[4:], curses.A_BOLD | curses.A_UNDERLINE)])
            continue
        if raw.startswith('## '):
            rendered.append([(raw[3:], curses.A_BOLD)])
            continue
        if raw.startswith('# '):
            rendered.append([(raw[2:].upper(), curses.A_BOLD)])
            continue
        # Bullet list
        stripped = raw.lstrip()
        if stripped.startswith('- ') or stripped.startswith('* '):
            indent = len(raw) - len(stripped)
            body = stripped[2:]
            prefix = ' ' * indent + '• '
            wrapped = textwrap.wrap(body, max(1, width - len(prefix))) or [body]
            for i, w in enumerate(wrapped):
                pad = prefix if i == 0 else ' ' * len(prefix)
                rendered.append([(pad, 0), *_md_inline(w, 0)])
            continue
        # Blockquote
        if stripped.startswith('> '):
            body = stripped[2:]
            wrapped = textwrap.wrap(body, max(1, width - 2)) or [body]
            for w in wrapped:
                rendered.append([('│ ', curses.A_DIM),
                                 *_md_inline(w, curses.A_DIM)])
            continue
        # Blank line
        if not raw.strip():
            rendered.append([('', 0)])
            continue
        # Regular paragraph
        for w in (textwrap.wrap(raw, width) or [raw]):
            rendered.append(_md_inline(w, 0))
    return rendered


def run_mimiclaw_chat(scr):
    """Chat with MimiClaw AI agent over WebSocket."""
    try:
        import websocket
    except ImportError:
        # Fall back: websocket-client may be installed in a non-standard path
        import subprocess, sys
        site = subprocess.check_output(
            [sys.executable, "-c", "import site; print(site.getusersitepackages())"],
            text=True).strip()
        if site not in sys.path:
            sys.path.insert(0, site)
        import websocket

    js = open_gamepad()
    scr.timeout(100)

    messages = []
    input_buf = ""
    scroll = 0
    ws = None
    connected = False
    current_ip = None

    def connect_ws(prefer_fresh=False):
        """Try to connect; on failure, re-probe serial once and retry."""
        nonlocal ws, connected, current_ip
        current_ip = _resolve_ip(prefer_fresh=prefer_fresh)
        if not current_ip:
            connected = False
            messages.append(("sys",
                "Device offline — wifi_status reports no IP. "
                "Check WiFi credentials or run 'restart' over serial."))
            return
        try:
            ws = websocket.create_connection(
                f"ws://{current_ip}:{WS_PORT}/ws", timeout=3)
            ws.settimeout(0.05)
            connected = True
            messages.append(("sys", f"Connected to MimiClaw at {current_ip}"))
        except Exception as e:
            connected = False
            # First failure with a cached IP: cache may be stale — re-probe
            # once and retry before surfacing the error to the user.
            if not prefer_fresh:
                messages.append(("sys",
                    f"Cached IP {current_ip} unreachable — re-probing…"))
                connect_ws(prefer_fresh=True)
                return
            messages.append(("sys", f"Connection failed: {e}"))

    def send_msg(text):
        nonlocal connected
        if not connected or not ws:
            messages.append(("sys", "Not connected. Press X to reconnect."))
            return
        try:
            payload = json.dumps({"type": "message", "content": text, "chat_id": CHAT_ID})
            ws.send(payload)
            messages.append(("you", text))
        except Exception as e:
            messages.append(("sys", f"Send error: {e}"))
            connected = False

    def poll():
        if not connected or not ws:
            return
        try:
            raw = ws.recv()
            if raw:
                data = json.loads(raw)
                content = data.get("content", "")
                if content:
                    messages.append(("mimi", content))
        except Exception:
            pass

    def build_view(width):
        """Flatten all messages into (role, spans_or_label) lines.

        Each entry is one of:
          ("label", role, label_text)    — a role header line ("you" / "mimi")
          ("body",  role, spans)         — a wrapped body line (list of (text, attr))
          ("blank", None, None)          — spacer between turns
        """
        out = []
        body_width = width - 4  # 2-char indent + 2-char padding
        last_role = None
        for role, text in messages:
            if role == "sys":
                # Inline, one-line, dim with a bullet marker. No separator needed.
                for w in (textwrap.wrap(text, body_width) or [text]):
                    out.append(("body", "sys", [(w, 0)]))
                last_role = "sys"
                continue
            # Fresh turn separator between distinct user/agent turns.
            if last_role in ("you", "mimi"):
                out.append(("blank", None, None))
            label = "you" if role == "you" else "mimi"
            out.append(("label", role, label))
            if role == "mimi":
                for spans in _md_render(text, body_width):
                    out.append(("body", role, spans))
            else:
                for w in (textwrap.wrap(text, body_width) or [text]):
                    out.append(("body", role, [(w, 0)]))
            last_role = role
        return out

    def role_attr(role):
        if role == "you":
            return curses.color_pair(C_CAT) | curses.A_BOLD
        if role == "mimi":
            return curses.color_pair(C_STATUS) | curses.A_BOLD
        return curses.color_pair(C_DIM)

    connect_ws()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        poll()

        # Title bar — show IP when connected, "offline" otherwise.
        if connected and current_ip:
            title = f" MimiClaw — {current_ip} "
        elif current_ip:
            title = f" MimiClaw — {current_ip} (disconnected) "
        else:
            title = " MimiClaw — offline "
        try:
            scr.addnstr(0, 0, title.center(w), w,
                        curses.color_pair(C_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        view_h = h - 4
        view = build_view(w)
        visible_start = max(0, len(view) - view_h) if scroll == 0 else max(0, scroll)

        for i in range(view_h):
            li = visible_start + i
            if li >= len(view):
                break
            kind, role, payload = view[li]
            y = i + 1
            try:
                if kind == "label":
                    label = f"  {payload}"
                    scr.addnstr(y, 1, label, w - 2, role_attr(role))
                elif kind == "body":
                    x = 1
                    if role == "sys":
                        sys_prefix = "  · "
                        scr.addnstr(y, x, sys_prefix, 4,
                                    curses.color_pair(C_DIM))
                        x += len(sys_prefix)
                        base = curses.color_pair(C_DIM)
                    else:
                        indent = "    "
                        scr.addnstr(y, x, indent, len(indent),
                                    curses.color_pair(C_ITEM))
                        x += len(indent)
                        base = curses.color_pair(C_ITEM)
                    for text, attr in payload:
                        if x >= w - 1 or not text:
                            continue
                        take = min(len(text), w - 1 - x)
                        scr.addnstr(y, x, text[:take], take, base | attr)
                        x += take
                # "blank" draws nothing
            except curses.error:
                pass

        # Input box — visual boundary + prompt
        try:
            scr.addnstr(h - 3, 0, "─" * w, w, curses.color_pair(C_DIM))
        except curses.error:
            pass
        prompt_attr = curses.color_pair(C_CAT) | curses.A_BOLD
        try:
            scr.addnstr(h - 2, 1, "> ", 2, prompt_attr)
            scr.addnstr(h - 2, 3, input_buf[:w - 5], w - 5,
                        curses.color_pair(C_ITEM))
            cx = min(3 + len(input_buf), w - 2)
            scr.addnstr(h - 2, cx, "_", 1, prompt_attr | curses.A_BLINK)
        except curses.error:
            pass

        bar = " ⏎ send · ↑↓ scroll · X reconnect · B back "
        try:
            scr.addnstr(h - 1, 0, bar.center(w), w,
                        curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if input_buf.strip():
                send_msg(input_buf.strip())
                input_buf = ""
                scroll = 0
        elif key == curses.KEY_BACKSPACE or key == 127:
            input_buf = input_buf[:-1]
        elif key == curses.KEY_UP or key == ord("k"):
            total = len(build_view(w))
            scroll = max(0, (scroll or max(0, total - view_h)) - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            scroll = 0
        elif gp == "refresh":
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
            ws = None
            connected = False
            connect_ws()
        elif 32 <= key < 127:
            input_buf += chr(key)

    if ws:
        try:
            ws.close()
        except Exception:
            pass
    if js:
        js.close()


def run_mimiclaw_serial(scr):
    """Raw serial monitor for MimiClaw on /dev/esp32."""
    from tui import esp32_detect

    js = open_gamepad()
    scr.timeout(50)
    lines = []

    ser, _fw = esp32_detect.open_ready(open_timeout=0.05, ready_timeout=7.0)
    if ser is None:
        scr.erase()
        scr.addnstr(1, 1, "Cannot open ESP32 serial port", 60, curses.color_pair(C_STATUS))
        scr.refresh()
        time.sleep(2)
        return
    # readline() needs a short blocking timeout for the polling loop
    ser.timeout = 0.05

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        try:
            raw = ser.readline()
            if raw:
                text = raw.decode("utf-8", errors="replace").rstrip()
                if text:
                    lines.append(text)
                    if len(lines) > 2000:
                        lines = lines[-1000:]
        except Exception:
            pass

        title = " MimiClaw Serial "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        view_h = h - 2
        start = max(0, len(lines) - view_h)
        for i in range(view_h):
            li = start + i
            if li >= len(lines):
                break
            try:
                scr.addnstr(i + 1, 1, lines[li][:w - 2], w - 2, curses.color_pair(C_ITEM))
            except curses.error:
                pass

        bar = " B Back "
        try:
            scr.addnstr(h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == ord("q") or key == ord("Q") or gp == "back":
            break

    esp32_detect._close_fast(ser)
    if js:
        js.close()


_STATUS_PROBES = [
    (b"config_show\r\n", "── Agent Config ──"),
    (b"wifi_status\r\n", "── WiFi ──"),
    (b"heap_info\r\n",   "── Memory ──"),
]


def _query_mimiclaw_status():
    """Run the CLI status probes over serial; return a list of display lines.

    MimiClaw's ESP-IDF console has no single `status` command — aggregate
    `config_show` + `wifi_status` + `heap_info` to cover the menu's
    "agent status and WiFi info" intent.
    """
    from tui import esp32_detect
    ser, _fw = esp32_detect.open_ready(open_timeout=2)
    if ser is None:
        return ["Error: cannot open ESP32 serial port"]

    out = []
    try:
        ser.reset_input_buffer()
        for cmd, header in _STATUS_PROBES:
            out.append(header)
            ser.write(cmd)
            time.sleep(1.0)
            buf = b""
            for _ in range(20):
                if ser.in_waiting:
                    buf += ser.read(ser.in_waiting)
                    time.sleep(0.1)
                else:
                    break
            for ln in buf.decode("utf-8", errors="replace").splitlines():
                ln = ln.rstrip()
                if not ln or ln == cmd.decode().strip() or ln.strip() == "mimi>":
                    continue
                out.append(ln)
            out.append("")
    finally:
        esp32_detect._close_fast(ser)
    return out


def run_mimiclaw_status(scr):
    """Query MimiClaw status via serial CLI."""
    lines = _query_mimiclaw_status()

    js = open_gamepad()
    scr.timeout(100)
    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        title = " MimiClaw Status "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)
        for i, line in enumerate(lines[:h - 2]):
            try:
                scr.addnstr(i + 1, 1, line[:w - 2], w - 2, curses.color_pair(C_ITEM))
            except curses.error:
                pass
        bar = " B Back | X Refresh "
        try:
            scr.addnstr(h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif gp == "refresh":
            lines = _query_mimiclaw_status()
    if js:
        js.close()


def run_mimiclaw_flash(scr):
    """Flash MimiClaw firmware from ~/mimiclaw-flash/."""
    required = ["bootloader.bin", "partition-table.bin", "ota_data_initial.bin",
                "mimiclaw.bin", "spiffs.bin"]
    missing = [f for f in required if not os.path.isfile(os.path.join(FLASH_DIR, f))]
    if missing:
        js = open_gamepad()
        scr.timeout(100)
        scr.erase()
        scr.addnstr(1, 1, "Missing firmware files:", 40,
                     curses.color_pair(C_STATUS) | curses.A_BOLD)
        for i, f in enumerate(missing):
            scr.addnstr(2 + i, 3, f, 40, curses.color_pair(C_ITEM))
        scr.addnstr(3 + len(missing), 1, "SCP files to ~/mimiclaw-flash/ first.", 50,
                     curses.color_pair(C_DIM))
        scr.addnstr(5 + len(missing), 1, "Press any key.", 20, curses.color_pair(C_FOOTER))
        scr.refresh()
        scr.timeout(-1)
        scr.getch()
        if js:
            js.close()
        return

    if not run_confirm(scr, "Flash MimiClaw"):
        return

    cmd = (
        f"cd {FLASH_DIR} && python3 -m esptool --chip esp32s3 -p /dev/ttyACM0 -b 460800 "
        f"--before default-reset --after hard-reset write-flash "
        f"--flash-mode dio --flash-size 8MB --flash-freq 80m "
        f"0x0 bootloader.bin 0x8000 partition-table.bin 0xf000 ota_data_initial.bin "
        f"0x20000 mimiclaw.bin 0x420000 spiffs.bin"
    )
    run_stream(scr, cmd, "Flashing MimiClaw")


HANDLERS = {
    "_mimiclaw_chat":   run_mimiclaw_chat,
    "_mimiclaw_serial": run_mimiclaw_serial,
    "_mimiclaw_status": run_mimiclaw_status,
    "_mimiclaw_wifi":   run_mimiclaw_wifi,
}
