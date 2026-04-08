"""TUI module: network"""

import curses
import os
import re
import subprocess
import threading
import time

from tui.framework import (
    C_CAT,
    C_DIM,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    SCRIPT_DIR,
    _tui_input_loop,
    draw_status_bar,
    open_gamepad,
)


def run_wifi_switcher(scr):
    """Scan and connect to WiFi networks."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0
    networks = []
    scanning = True

    def scan():
        nonlocal networks, scanning
        scanning = True
        try:
            out = subprocess.check_output(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "dev", "wifi", "list", "--rescan", "yes"],
                timeout=15
            ).decode()
            seen = set()
            nets = []
            for line in out.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 4 and parts[0] and parts[0] not in seen:
                    seen.add(parts[0])
                    nets.append({
                        "ssid": parts[0],
                        "signal": parts[1],
                        "security": parts[2],
                        "active": parts[3] == "yes",
                    })
            networks = sorted(nets, key=lambda n: (-int(n["signal"] or 0)))
        except Exception:
            networks = []
        scanning = False

    # Initial scan in background
    threading.Thread(target=scan, daemon=True).start()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " WiFi Networks " + ("(scanning...)" if scanning else f"({len(networks)} found)")
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        hdr = f"  {'SSID':<30} {'SIG':>4} {'SECURITY':<15} {'STATUS'}"
        try:
            scr.addnstr(1, 0, hdr, w, curses.color_pair(C_CAT) | curses.A_BOLD)
        except curses.error:
            pass

        sel = min(sel, max(0, len(networks) - 1))
        view_h = h - 4
        for i in range(view_h):
            if i >= len(networks):
                break
            n = networks[i]
            sig = int(n["signal"] or 0)
            bars = "█" * (sig // 25) + "░" * (4 - sig // 25)
            active = "◉ connected" if n["active"] else ""
            line = f"  {n['ssid']:<30} {bars} {n['security']:<15} {active}"
            attr = curses.color_pair(C_SEL) | curses.A_BOLD if i == sel else curses.color_pair(C_ITEM)
            marker = "▸" if i == sel else " "
            try:
                scr.addnstr(i + 2, 0, f"{marker}{line}", w, attr)
            except curses.error:
                pass

        bar = " ↑↓ Select │ A Connect │ X Rescan │ B Back ".center(w)
        try:
            scr.addnstr(h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(networks) - 1, sel + 1)
        elif gp == "refresh" or key == ord("r"):
            threading.Thread(target=scan, daemon=True).start()
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if networks and sel < len(networks):
                ssid = networks[sel]["ssid"]
                draw_status_bar(scr, h, w, f"  Connecting to {ssid}...",
                                curses.color_pair(C_STATUS) | curses.A_BOLD)
                scr.refresh()
                try:
                    subprocess.run(["nmcli", "dev", "wifi", "connect", ssid],
                                   capture_output=True, timeout=15)
                    draw_status_bar(scr, h, w, f"  ✓ Connected to {ssid}")
                except Exception:
                    draw_status_bar(scr, h, w, f"  ✗ Failed to connect to {ssid}",
                                    curses.color_pair(C_HEADER) | curses.A_BOLD)
                scr.refresh()
                time.sleep(1.5)
                threading.Thread(target=scan, daemon=True).start()

    if js:
        js.close()

def run_hotspot_toggle(scr):
    """Toggle hotspot on/off."""
    h, w = scr.getmaxyx()
    script = os.path.join(SCRIPT_DIR, "hotspot.sh")
    try:
        result = subprocess.check_output(
            ["bash", script, "toggle"],
            text=True, timeout=10
        ).strip()
        msg = f"  ✓ {result}"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        msg = f"  ✗ Hotspot toggle failed: {e}"

    draw_status_bar(scr, h, w, msg, curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    time.sleep(1.5)

def _tui_form(scr, title, fields):
    """Show a centered form window with labeled fields. Returns dict of values or None if cancelled.
    fields: list of (label, default_value) tuples.
    """
    h, w = scr.getmaxyx()
    # Form dimensions
    form_w = min(50, w - 4)
    form_h = len(fields) * 3 + 5  # title + fields + buttons + border
    start_y = max(0, (h - form_h) // 2)
    start_x = max(0, (w - form_w) // 2)
    input_w = form_w - 6

    win = curses.newwin(form_h, form_w, start_y, start_x)
    win.keypad(True)

    values = [list(default) for _, default in fields]
    cur_field = 0

    while True:
        win.erase()
        win.border()
        # Title
        win.addnstr(1, (form_w - len(title)) // 2, title, form_w - 2,
                     curses.color_pair(C_HEADER) | curses.A_BOLD)

        for i, (label, _) in enumerate(fields):
            y = 3 + i * 3
            win.addnstr(y, 3, label, form_w - 6, curses.color_pair(C_CAT) | curses.A_BOLD)
            # Input box
            val_str = "".join(values[i])
            if i == cur_field:
                win.addnstr(y + 1, 3, ">" + val_str + "_", input_w,
                            curses.color_pair(C_HEADER))
            else:
                win.addnstr(y + 1, 3, " " + val_str, input_w,
                            curses.color_pair(C_ITEM))

        hint_y = form_h - 2
        hint = "Tab: next  Enter: save  Esc: cancel"
        win.addnstr(hint_y, (form_w - len(hint)) // 2, hint, form_w - 2,
                     curses.color_pair(C_STATUS))

        win.refresh()
        ch = win.getch()

        if ch == 27:  # Esc
            del win
            scr.touchwin()
            scr.refresh()
            return None
        elif ch == 9:  # Tab
            cur_field = (cur_field + 1) % len(fields)
        elif ch in (curses.KEY_ENTER, 10, 13):
            result = {}
            for i, (label, _) in enumerate(fields):
                result[label] = "".join(values[i])
            del win
            scr.touchwin()
            scr.refresh()
            return result
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if values[cur_field]:
                values[cur_field].pop()
        elif ch == curses.KEY_UP:
            cur_field = (cur_field - 1) % len(fields)
        elif ch == curses.KEY_DOWN:
            cur_field = (cur_field + 1) % len(fields)
        elif 32 <= ch <= 126:
            values[cur_field].append(chr(ch))

def _read_conf(path):
    """Read key=value config file into dict."""
    d = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    d[k] = v
    except FileNotFoundError:
        pass
    return d

def _write_conf(path, d):
    """Write dict as key=value config file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        for k, v in d.items():
            f.write(f"{k}={v}\n")


_UCONSOLE_CONF_DIR = os.path.join(os.path.expanduser('~'), '.config', 'uconsole')
HOTSPOT_CONF = os.path.join(_UCONSOLE_CONF_DIR, 'hotspot.conf')
WEBDASH_CONF = os.path.join(_UCONSOLE_CONF_DIR, 'webdash.conf')

def _run_config_editor(scr, title, conf_path, fields, key_map, restart_cmd=None):
    """Generic config editor: show form, save to conf file, optionally restart a service.
    fields: list of (label, default) for _tui_form
    key_map: dict mapping field label -> config key
    restart_cmd: optional list for subprocess.run after saving
    """
    h, w = scr.getmaxyx()
    result = _tui_form(scr, title, fields)
    if not result or any(not result.get(label) for label, _ in fields):
        draw_status_bar(scr, h, w, "  ✗ Cancelled", curses.color_pair(C_STATUS) | curses.A_BOLD)
        scr.refresh()
        time.sleep(1.5)
        return

    conf = _read_conf(conf_path)
    for label, conf_key in key_map.items():
        conf[conf_key] = result[label]
    _write_conf(conf_path, conf)

    msg = f"  ✓ {title} saved"
    if restart_cmd:
        try:
            subprocess.run(restart_cmd, timeout=10, capture_output=True)
            msg += " (restarted)"
        except Exception:
            msg += " (restart manually)"

    draw_status_bar(scr, h, w, msg, curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    time.sleep(1.5)

def run_hotspot_config(scr):
    _run_config_editor(scr, "Hotspot Config", HOTSPOT_CONF,
                       [("AP Name", ""), ("AP Password", "")],
                       {"AP Name": "ssid", "AP Password": "pass"})

def run_wifi_fallback(scr):
    """Toggle WiFi fallback dispatcher on/off."""
    h, w = scr.getmaxyx()
    script = os.path.join(SCRIPT_DIR, "wifi-fallback.sh")
    if not os.path.isfile(script):
        msg = f"  ✗ Script not found: {script}"
        draw_status_bar(scr, h, w, msg, curses.color_pair(C_STATUS) | curses.A_BOLD)
        scr.refresh()
        time.sleep(1.5)
        return
    try:
        result = subprocess.check_output(
            ["bash", script, "toggle"],
            text=True, timeout=10
        ).strip()
        # Strip ANSI codes for curses display
        clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', result)
        msg = f"  {clean}"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        msg = f"  ✗ WiFi fallback toggle failed: {e}"

    draw_status_bar(scr, h, w, msg, curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    time.sleep(1.5)

def run_bluetooth(scr):
    """Bluetooth device manager."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0

    def get_devices():
        devs = []
        try:
            paired = subprocess.check_output(
                ["bluetoothctl", "devices", "Paired"], timeout=5
            ).decode().strip().splitlines()
            for line in paired:
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    mac = parts[1]
                    name = parts[2]
                    # Check connection
                    try:
                        info = subprocess.check_output(
                            ["bluetoothctl", "info", mac], timeout=3
                        ).decode()
                        connected = "Connected: yes" in info
                    except Exception:
                        connected = False
                    devs.append({"mac": mac, "name": name, "paired": True, "connected": connected})
        except Exception:
            pass
        return devs

    devices = get_devices()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = f" Bluetooth Devices ({len(devices)} paired) "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        sel = min(sel, max(0, len(devices) - 1))

        if not devices:
            try:
                scr.addnstr(3, 4, "No paired devices found", w - 8, curses.color_pair(C_DIM))
                scr.addnstr(4, 4, "Use 'bluetoothctl' to pair new devices", w - 8, curses.color_pair(C_DIM))
            except curses.error:
                pass
        else:
            for i, dev in enumerate(devices):
                if i + 2 >= h - 2:
                    break
                status = "◉ connected" if dev["connected"] else "○ paired"
                line = f"  {dev['name']:<30} {dev['mac']}  {status}"
                attr = curses.color_pair(C_SEL) | curses.A_BOLD if i == sel else curses.color_pair(C_ITEM)
                marker = "▸" if i == sel else " "
                try:
                    scr.addnstr(i + 2, 0, f"{marker}{line}", w, attr)
                except curses.error:
                    pass

        bar = " ↑↓ Select │ A Connect/Disconnect │ X Refresh │ B Back ".center(w)
        try:
            scr.addnstr(h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(devices) - 1, sel + 1)
        elif gp == "refresh":
            devices = get_devices()
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if devices and sel < len(devices):
                dev = devices[sel]
                action = "disconnect" if dev["connected"] else "connect"
                draw_status_bar(scr, h, w, f"  {action.title()}ing {dev['name']}...")
                scr.refresh()
                try:
                    subprocess.run(["bluetoothctl", action, dev["mac"]],
                                   capture_output=True, timeout=10)
                except Exception:
                    pass
                time.sleep(1)
                devices = get_devices()

    if js:
        js.close()
