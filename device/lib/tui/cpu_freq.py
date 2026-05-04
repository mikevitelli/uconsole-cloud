"""TUI module: CPU frequency min/max picker for uConsole (CM5).

Two-column picker (MIN / MAX) across the CM5's 10 frequency steps
(1.5–2.4 GHz) plus four hotkey presets.  Shells out to cpu-freq.sh
for all writes so sudo rules stay consistent with the CLI.
"""

import curses
import os
import subprocess
import time

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
    SCRIPT_DIR,
)

# ── sysfs paths ────────────────────────────────────────────────────────────

_CPUFREQ = "/sys/devices/system/cpu/cpu0/cpufreq"
_PATH_MIN = os.path.join(_CPUFREQ, "scaling_min_freq")
_PATH_MAX = os.path.join(_CPUFREQ, "scaling_max_freq")
_PATH_GOV = os.path.join(_CPUFREQ, "scaling_governor")
_PATH_CUR = os.path.join(_CPUFREQ, "scaling_cur_freq")
_PATH_AVAIL = os.path.join(_CPUFREQ, "scaling_available_frequencies")

_CPU_FREQ_SH = os.path.join(SCRIPT_DIR, "power", "cpu-freq.sh")

# Fallback freq list if sysfs is absent (e.g. in CI / dev machine)
_DEFAULT_FREQS_MHZ = [1500, 1600, 1700, 1800, 1900, 2000, 2100, 2200, 2300, 2400]

PRESETS = [
    ("P", "battery",     "Battery",     "1500/1500"),
    ("O", "balanced",    "Balanced",    "1500/2000"),
    ("E", "performance", "Performance", "1800/2400"),
    ("M", "max",         "Max",         "2400/2400"),
]

REFRESH_INTERVAL = 1.5


# ── sysfs helpers ─────────────────────────────────────────────────────────

def _read_khz(path):
    """Read a kHz value from sysfs; return 0 on failure."""
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def _read_str(path):
    """Read a string value from sysfs; return '' on failure."""
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _load_available_freqs():
    """Return sorted list of available frequencies in MHz."""
    raw = _read_str(_PATH_AVAIL)
    if not raw:
        return list(_DEFAULT_FREQS_MHZ)
    try:
        khz_list = [int(x) for x in raw.split() if x]
        mhz_list = sorted(set(k // 1000 for k in khz_list))
        return mhz_list if mhz_list else list(_DEFAULT_FREQS_MHZ)
    except ValueError:
        return list(_DEFAULT_FREQS_MHZ)


def _read_state():
    """Return (governor, min_mhz, max_mhz, cur_mhz) from sysfs."""
    gov = _read_str(_PATH_GOV) or "unknown"
    min_mhz = _read_khz(_PATH_MIN) // 1000
    max_mhz = _read_khz(_PATH_MAX) // 1000
    cur_mhz = _read_khz(_PATH_CUR) // 1000
    return gov, min_mhz, max_mhz, cur_mhz


# ── subprocess helpers ────────────────────────────────────────────────────

def _run_cpu_freq(*args, timeout=8):
    """Run cpu-freq.sh with args.  Return (rc, stderr_or_stdout_on_err)."""
    cmd = [_CPU_FREQ_SH, *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return r.returncode, (r.stderr or r.stdout).strip()
        return 0, ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return 1, str(e)


# ── curses panel ──────────────────────────────────────────────────────────

def run_cpu_freq_panel(scr):
    """Full-screen TUI panel for CPU frequency min/max control."""
    js = open_gamepad()
    scr.timeout(150)

    freqs = _load_available_freqs()
    n_freqs = len(freqs)

    selected_col = 0       # 0 = MIN column, 1 = MAX column
    selected_idx = 0       # index into freqs[]

    gov, min_mhz, max_mhz, cur_mhz = _read_state()
    last_refresh = time.time()

    error_msg = ""
    error_until = 0.0

    def refresh():
        nonlocal gov, min_mhz, max_mhz, cur_mhz, last_refresh
        gov, min_mhz, max_mhz, cur_mhz = _read_state()
        last_refresh = time.time()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # ── chrome ──
        draw_header(scr, w)
        title = "CPU Frequency"
        scr.addnstr(6, max(0, (w - len(title)) // 2), title, w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        draw_separator(scr, 7, w)

        y = 9

        # ── Current state section ──
        scr.addnstr(y, 2, "── Current ──", w - 4,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        cur_line = (f"Governor  {gov:<12}  "
                    f"Min  {min_mhz} MHz    "
                    f"Max  {max_mhz} MHz    "
                    f"Cur  {cur_mhz} MHz")
        scr.addnstr(y, 4, cur_line, w - 6, curses.color_pair(C_ITEM))
        y += 2

        # ── Picker section ──
        scr.addnstr(y, 2, "── Set freq ──", w - 4,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1

        # Column header row
        col0_x = 4
        col1_x = 22
        preset_x = 40
        hdr_attr = curses.color_pair(C_HEADER) | curses.A_BOLD
        scr.addnstr(y, col0_x, "MIN", w - col0_x, hdr_attr)
        scr.addnstr(y, col1_x, "MAX", w - col1_x, hdr_attr)
        scr.addnstr(y, preset_x, "Presets", w - preset_x, hdr_attr)
        y += 1

        for i, mhz in enumerate(freqs):
            # --- MIN column ---
            dot0 = "●" if mhz == min_mhz else " "
            cursor0 = "▸ " if (selected_col == 0 and i == selected_idx) else "  "
            item0 = f"{cursor0}{mhz} MHz  {dot0}"
            attr0 = (curses.color_pair(C_SEL) | curses.A_REVERSE
                     if selected_col == 0 and i == selected_idx
                     else curses.color_pair(C_ITEM))
            scr.addnstr(y, col0_x, item0, col1_x - col0_x - 1, attr0)

            # --- MAX column ---
            dot1 = "●" if mhz == max_mhz else " "
            cursor1 = "▸ " if (selected_col == 1 and i == selected_idx) else "  "
            item1 = f"{cursor1}{mhz} MHz  {dot1}"
            attr1 = (curses.color_pair(C_SEL) | curses.A_REVERSE
                     if selected_col == 1 and i == selected_idx
                     else curses.color_pair(C_ITEM))
            scr.addnstr(y, col1_x, item1, preset_x - col1_x - 1, attr1)

            # --- Preset column (only first 4 rows) ---
            if i < len(PRESETS):
                key, _name, label, vals = PRESETS[i]
                preset_line = f"[{key}] {label:<12} {vals}"
                scr.addnstr(y, preset_x, preset_line, w - preset_x - 2,
                            curses.color_pair(C_ITEM))

            y += 1

        # ── Error / status line ──
        if error_msg and time.time() < error_until:
            scr.addnstr(h - 2, 2, error_msg, w - 4,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)

        footer = " ↑↓ Freq │ ← → Column │ A Apply │ B Back │ P/O/E/M Preset "
        draw_status_bar(scr, h, w, footer)
        scr.refresh()

        # ── Auto-refresh ──
        if time.time() - last_refresh > REFRESH_INTERVAL:
            refresh()

        # ── Input ──
        key, gp_action = _tui_input_loop(scr, js, map_y_quit=True)
        if key == -1 and gp_action is None:
            continue

        # Back / quit
        if (key in (ord("q"), ord("Q"), ord("b"), ord("B"),
                    curses.KEY_BACKSPACE, 127)
                or gp_action == "back"):
            return

        # Navigation
        elif key == curses.KEY_UP or key == ord("k"):
            selected_idx = (selected_idx - 1) % n_freqs

        elif key == curses.KEY_DOWN or key == ord("j"):
            selected_idx = (selected_idx + 1) % n_freqs

        elif key == curses.KEY_LEFT or key == ord("h"):
            selected_col = 0

        elif key == curses.KEY_RIGHT or key == ord("l"):
            selected_col = 1

        # Apply selected frequency
        elif key in (curses.KEY_ENTER, 10, 13, ord(" "), ord("a"), ord("A")) or gp_action == "enter":
            mhz = freqs[selected_idx]
            rail = "min" if selected_col == 0 else "max"
            rc, err = _run_cpu_freq(rail, str(mhz))
            if rc != 0:
                error_msg = f"  ✗ cpu-freq.sh {rail} {mhz}: {err}"
                error_until = time.time() + 3
            refresh()

        # Presets
        elif key in (ord("p"), ord("P")):
            rc, err = _run_cpu_freq("preset", "battery")
            if rc != 0:
                error_msg = f"  ✗ preset battery: {err}"
                error_until = time.time() + 3
            refresh()

        elif key in (ord("o"), ord("O")):
            rc, err = _run_cpu_freq("preset", "balanced")
            if rc != 0:
                error_msg = f"  ✗ preset balanced: {err}"
                error_until = time.time() + 3
            refresh()

        elif key in (ord("e"), ord("E")):
            rc, err = _run_cpu_freq("preset", "performance")
            if rc != 0:
                error_msg = f"  ✗ preset performance: {err}"
                error_until = time.time() + 3
            refresh()

        elif key in (ord("m"), ord("M")):
            rc, err = _run_cpu_freq("preset", "max")
            if rc != 0:
                error_msg = f"  ✗ preset max: {err}"
                error_until = time.time() + 3
            refresh()


HANDLERS = {
    "_cpu_freq": run_cpu_freq_panel,
}
