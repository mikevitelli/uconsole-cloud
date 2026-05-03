"""TUI module: AIO v2 board control + power dashboard.

Wraps the `aiov2_ctl` CLI from the hackergadgets-uconsole-aio-board package.
On AIO v1 boards (where aiov2_ctl is absent) this module's dashboard
handler delegates to the legacy radio/aio-check.sh panel.
"""

import os
import re
import subprocess

AIOV2_CTL = "/usr/local/bin/aiov2_ctl"

RAIL_LABELS = {
    "GPS":  "uBlox NEO",
    "LORA": "SX1262",
    "SDR":  "RTL-SDR",
    "USB":  "AC1200",
}

# Rail line: "GPS   GPIO27: ON"
_RAIL_RE = re.compile(r"^\s*(GPS|LORA|SDR|USB)\s+GPIO(\d+):\s+(ON|OFF)\s*$")
# Power-section line: "Voltage   : 4.16 V"  or  "Capacity  : 89%"
_KV_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.+?)\s*$")

# Map the labels aiov2_ctl emits to our snake-case keys
_KEY_MAP = {
    "Source":    "source",
    "Status":    "status",
    "Capacity":  "capacity",
    "Direction": "direction",
    "Mode":      "mode",
    "Voltage":   "voltage",
    "Current":   "current",
    "Power":     "power",
}


def parse_status(text):
    """Parse `aiov2_ctl --status` text output.

    Returns:
        {
            "rails": {"GPS": {"gpio": 27, "state": True}, ...},
            "power": {"source": "AC", "capacity": 89, "voltage": 4.16, ...},
        }
    Unknown / malformed input yields empty dicts; the function never raises.
    """
    rails = {}
    power = {}
    for raw_line in text.splitlines():
        m = _RAIL_RE.match(raw_line)
        if m:
            rails[m.group(1)] = {"gpio": int(m.group(2)), "state": m.group(3) == "ON"}
            continue
        m = _KV_RE.match(raw_line)
        if not m:
            continue
        label, value = m.group(1), m.group(2)
        key = _KEY_MAP.get(label)
        if key is None:
            continue
        if key == "capacity":
            # "89%" → 89
            try:
                power[key] = int(value.rstrip("%").strip())
            except ValueError:
                continue
        elif key in ("voltage", "current", "power"):
            # "4.16 V" → 4.16
            try:
                power[key] = float(value.split()[0])
            except (ValueError, IndexError):
                continue
        else:
            power[key] = value
    return {"rails": rails, "power": power}


# ---------------------------------------------------------------------------
# Board detection
# ---------------------------------------------------------------------------

_detect_cache = None


def detect():
    """Return 'v2' if the AIO v2 control binary is present and executable, else 'v1'.

    Cached for the lifetime of the process.
    """
    global _detect_cache
    if _detect_cache is not None:
        return _detect_cache
    if os.path.isfile(AIOV2_CTL) and os.access(AIOV2_CTL, os.X_OK):
        _detect_cache = "v2"
    else:
        _detect_cache = "v1"
    return _detect_cache


# ---------------------------------------------------------------------------
# Rail control helpers
# ---------------------------------------------------------------------------

def _run_ctl(args, timeout=5):
    """Run aiov2_ctl with args, return (returncode, stdout). Never raises."""
    try:
        r = subprocess.run(
            [AIOV2_CTL, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 1, ""


def get_status():
    """Return parsed status dict, or empty {rails:{},power:{}} on any failure."""
    rc, out = _run_ctl(["--status"])
    if rc != 0:
        return {"rails": {}, "power": {}}
    return parse_status(out)


def ensure_rail(name):
    """Ensure rail `name` (GPS/LORA/SDR/USB) is powered. Return True on success.

    On AIO v1 boards: no-op, returns True.
    On AIO v2 with rail already ON: returns True.
    On AIO v2 with rail OFF: calls `aiov2_ctl <name> on` and returns True if rc==0.
    """
    if name not in RAIL_LABELS:
        return False
    if detect() == "v1":
        return True
    status = get_status()
    rail = status["rails"].get(name)
    if rail and rail["state"]:
        return True
    rc, _ = _run_ctl([name, "on"])
    return rc == 0


# ---------------------------------------------------------------------------
# Curses dashboard panel
# ---------------------------------------------------------------------------

import curses

from tui.framework import (
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    draw_header,
    draw_separator,
    draw_status_bar,
    open_gamepad,
    _tui_input_loop,
)

RAIL_ORDER = ["GPS", "LORA", "SDR", "USB"]


def toggle_rail(name, on):
    """Toggle live rail. Returns True on success."""
    if name not in RAIL_LABELS:
        return False
    rc, _ = _run_ctl([name, "on" if on else "off"])
    return rc == 0


def toggle_boot_rail(name, on):
    """Toggle boot-default for a rail. Returns True on success."""
    if name not in RAIL_LABELS:
        return False
    rc, _ = _run_ctl(["--boot-rail", name, "on" if on else "off"])
    return rc == 0


def get_boot_rails():
    """Return {RAIL: bool} of currently configured boot defaults.

    Calls `aiov2_ctl --boot-rails-status` and parses the same `RAIL ON/OFF`
    lines emitted by --status.
    """
    rc, out = _run_ctl(["--boot-rails-status"])
    if rc != 0:
        return {}
    boot = {}
    for line in out.splitlines():
        m = _RAIL_RE.match(line)
        if m:
            boot[m.group(1)] = m.group(3) == "ON"
    return boot


def run_aio_dashboard(scr):
    """Full-screen TUI panel for AIO v2 rail control."""
    if detect() == "v1":
        # Delegate to the legacy v1 script. Imported lazily to avoid a hard
        # framework dependency at module import time (keeps unit tests clean).
        from tui.framework import run_panel
        run_panel(scr, "radio/aio-check.sh", "AIO Board Check")
        return

    js = open_gamepad()
    scr.timeout(150)
    selected = 0
    last_status = {"rails": {}, "power": {}}
    last_boot = {}
    last_refresh = 0.0
    error_msg = ""
    error_until = 0.0
    REFRESH_INTERVAL = 1.5

    import time

    def refresh():
        nonlocal last_status, last_boot, last_refresh
        last_status = get_status()
        last_boot = get_boot_rails()
        last_refresh = time.time()

    refresh()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        draw_header(scr, w)
        title = "AIO v2 — Rails & Power"
        scr.addnstr(6, max(0, (w - len(title)) // 2), title, w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        draw_separator(scr, 7, w)

        y = 9
        scr.addnstr(y, 2, "── Power ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        p = last_status.get("power", {})
        if p:
            mode = p.get("mode", "?")
            scr.addnstr(y, 4, f"Mode       {mode}", w - 6, curses.color_pair(C_ITEM))
            y += 1
            cap = p.get("capacity", "?")
            status_word = p.get("status", "?")
            pwr = p.get("power", "?")
            scr.addnstr(y, 4, f"Power      {pwr} W       Battery  {cap}%  ({status_word})",
                        w - 6, curses.color_pair(C_ITEM))
            y += 2
        else:
            scr.addnstr(y, 4, "(unable to read --status)", w - 6,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
            y += 2

        scr.addnstr(y, 2, "── Rails ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        for i, rail in enumerate(RAIL_ORDER):
            info = last_status.get("rails", {}).get(rail, {})
            on = info.get("state", False)
            boot_on = last_boot.get(rail, False)
            dot = "●" if on else "○"
            boot_dot = "●" if boot_on else "○"
            label = RAIL_LABELS[rail]
            line = f"{rail:5}  {dot}  {'ON ' if on else 'OFF'}    boot {boot_dot}     {label}"
            cursor = "▸ " if i == selected else "  "
            attr = curses.color_pair(C_SEL) | curses.A_REVERSE if i == selected \
                else curses.color_pair(C_ITEM)
            scr.addnstr(y, 2, cursor + line, w - 4, attr)
            y += 1

        y += 1
        scr.addnstr(y, 2, "── WiFi ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        # Lazy import: wifi_radio may not be loaded yet (forward dependency)
        try:
            from tui.wifi_radio import current_mode_label, brief_radio_summary
            wifi_line = current_mode_label() + "     " + brief_radio_summary()
        except ImportError:
            wifi_line = "(WiFi info unavailable)"
        scr.addnstr(y, 4, wifi_line, w - 6, curses.color_pair(C_ITEM))

        if error_msg and time.time() < error_until:
            scr.addnstr(h - 2, 2, error_msg, w - 4,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
        footer = " ↑↓ Rail │ A Toggle │ X Boot Default │ Y WiFi Radios │ B Back "
        draw_status_bar(scr, h, w, footer)
        scr.refresh()

        if time.time() - last_refresh > REFRESH_INTERVAL:
            refresh()

        key, gp_action = _tui_input_loop(scr, js, map_y_quit=True)
        if key == -1 and gp_action is None:
            continue
        if key == ord("q") or key == ord("Q") or gp_action == "back":
            return
        if key == curses.KEY_UP or key == ord("k"):
            selected = (selected - 1) % len(RAIL_ORDER)
        elif key == curses.KEY_DOWN or key == ord("j"):
            selected = (selected + 1) % len(RAIL_ORDER)
        elif key in (curses.KEY_ENTER, 10, 13, ord(" ")) or gp_action == "enter":
            rail = RAIL_ORDER[selected]
            current_on = last_status.get("rails", {}).get(rail, {}).get("state", False)
            ok = toggle_rail(rail, not current_on)
            if not ok:
                error_msg = f"  ✗ failed to toggle {rail}"
                error_until = time.time() + 3
            refresh()
        elif key == ord("b") or key == ord("B") or gp_action == "refresh":
            # GP_X mapped to "refresh" by _tui_input_loop — repurpose for boot-rail toggle
            rail = RAIL_ORDER[selected]
            current_boot = last_boot.get(rail, False)
            ok = toggle_boot_rail(rail, not current_boot)
            if not ok:
                error_msg = f"  ✗ failed to set boot default for {rail}"
                error_until = time.time() + 3
            refresh()
        elif key == ord("w") or key == ord("W") or gp_action == "quit":
            # GP_Y mapped to "quit" by _tui_input_loop — repurpose for WiFi jump
            from tui.wifi_radio import run_wifi_radio_picker
            run_wifi_radio_picker(scr)
            refresh()


HANDLERS = {
    "_aio_board": run_aio_dashboard,
}
