"""TUI module: MimiClaw AI agent chat portal."""

import curses
import json
import os
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

MIMI_IP = "192.168.1.23"
WS_PORT = 18789
CHAT_ID = "tui_console"
FLASH_DIR = os.path.expanduser("~/mimiclaw-flash")


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

    ws_url = f"ws://{MIMI_IP}:{WS_PORT}/ws"
    js = open_gamepad()
    scr.timeout(100)

    messages = []
    input_buf = ""
    scroll = 0
    ws = None
    connected = False

    def connect_ws():
        nonlocal ws, connected
        try:
            ws = websocket.create_connection(ws_url, timeout=3)
            ws.settimeout(0.05)
            connected = True
            messages.append(("sys", f"Connected to MimiClaw at {MIMI_IP}"))
        except Exception as e:
            connected = False
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

    def wrap(width):
        lines = []
        usable = width - 4
        for role, text in messages:
            prefix = "> " if role == "you" else ("  " if role == "mimi" else "# ")
            wrapped = textwrap.wrap(text, usable - len(prefix)) or [""]
            for i, line in enumerate(wrapped):
                lines.append((role, (prefix if i == 0 else " " * len(prefix)) + line))
        return lines

    connect_ws()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        poll()

        status = "CONNECTED" if connected else "DISCONNECTED"
        title = f" MimiClaw Chat [{status}] "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        view_h = h - 4
        wrapped = wrap(w)
        visible_start = max(0, len(wrapped) - view_h) if scroll == 0 else max(0, scroll)

        for i in range(view_h):
            li = visible_start + i
            if li >= len(wrapped):
                break
            role, line = wrapped[li]
            if role == "you":
                attr = curses.color_pair(C_CAT) | curses.A_BOLD
            elif role == "mimi":
                attr = curses.color_pair(C_ITEM)
            else:
                attr = curses.color_pair(C_DIM)
            try:
                scr.addnstr(i + 1, 1, line[:w - 2], w - 2, attr)
            except curses.error:
                pass

        prompt = f"> {input_buf}"
        cursor_attr = curses.color_pair(C_SEL) | curses.A_BOLD
        try:
            scr.addnstr(h - 2, 1, prompt[:w - 2], w - 2, cursor_attr)
            cx = min(1 + len(prompt), w - 2)
            scr.addnstr(h - 2, cx, "_", 1, cursor_attr | curses.A_BLINK)
        except curses.error:
            pass

        bar = " Enter Send | Up/Down Scroll | X Reconnect | B Back "
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
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if input_buf.strip():
                send_msg(input_buf.strip())
                input_buf = ""
                scroll = 0
        elif key == curses.KEY_BACKSPACE or key == 127:
            input_buf = input_buf[:-1]
        elif key == curses.KEY_UP or key == ord("k"):
            total = len(wrap(w))
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
    """Raw serial monitor for MimiClaw on /dev/ttyACM0."""
    import serial as pyserial

    js = open_gamepad()
    scr.timeout(50)
    lines = []

    try:
        ser = pyserial.Serial("/dev/ttyACM0", 115200, timeout=0.05)
    except Exception as e:
        scr.erase()
        scr.addnstr(1, 1, f"Cannot open /dev/ttyACM0: {e}", 60, curses.color_pair(C_STATUS))
        scr.refresh()
        time.sleep(2)
        return

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

    ser.close()
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
    try:
        import serial as pyserial
    except ImportError as e:
        return [f"Error: {e}"]
    try:
        ser = pyserial.Serial("/dev/ttyACM0", 115200, timeout=2)
    except Exception as e:
        return [f"Error: {e}"]

    out = []
    try:
        # Wake prompt + drain any pending output
        ser.reset_input_buffer()
        ser.write(b"\r\n")
        time.sleep(0.2)
        ser.read(ser.in_waiting or 1024)

        for cmd, header in _STATUS_PROBES:
            out.append(header)
            ser.write(cmd)
            time.sleep(1.0)
            buf = b""
            # Drain until quiet for one poll cycle
            for _ in range(20):
                if ser.in_waiting:
                    buf += ser.read(ser.in_waiting)
                    time.sleep(0.1)
                else:
                    break
            for ln in buf.decode("utf-8", errors="replace").splitlines():
                ln = ln.rstrip()
                # Skip echoed command, empty lines, and the bare prompt
                if not ln or ln == cmd.decode().strip() or ln.strip() == "mimi>":
                    continue
                out.append(ln)
            out.append("")
    finally:
        ser.close()
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
