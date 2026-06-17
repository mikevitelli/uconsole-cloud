"""TUI module: battery_config — Power/Battery configuration screen.

Curses front-end over ``battery_lib`` (all logic/telemetry lives there).
Phase 1: live telemetry + editable charge limit/current and warn/shutdown
thresholds + build-profile preset.  Persists to ``console.json`` ``battery.*``;
the privileged sysfs/udev applier is a separate plan item (shown as a dry-run).
"""

import curses
import time

from tui.framework import (
    C_CAT,
    C_HEADER,
    C_ITEM,
    C_STATUS,
    close_gamepad,
    draw_header,
    draw_status_bar,
    open_gamepad,
    _tui_input_loop,
)
from tui import battery_lib as bl


def _draw(scr, cfg, tele, sel, rows, msg):
    h, w = scr.getmaxyx()
    scr.erase()
    draw_header(scr, w)
    y = 4

    def line(text, attr, indent=2):
        nonlocal y
        if y < h - 1:
            scr.addnstr(y, indent, text, w - indent - 1, attr)
        y += 1

    cells = cfg["cells"]
    cat = curses.color_pair(C_CAT) | curses.A_BOLD
    item = curses.color_pair(C_ITEM)
    dim = curses.color_pair(C_ITEM) | curses.A_DIM
    selattr = curses.color_pair(C_HEADER) | curses.A_BOLD | curses.A_REVERSE

    # A — telemetry (live)
    line("A · TELEMETRY", cat)
    v = tele["voltage"]
    pc = ("  (%.2f/cell)" % (v / cells)) if v and cells > 1 else ""
    line("  voltage     %s%s" % ("%.3f V" % v if v else "—", pc), dim)
    line("  charge      %s%%  ·  %s  ·  %s" % (
        tele["capacity"], tele["status"],
        "%.1f W" % tele["power"] if tele["power"] else "—"), dim)
    y += 1

    # editable tiers B–D
    cur_cat = None
    for i, (key, label, kind) in enumerate(rows):
        meta = _ROW_CAT[key]
        if meta != cur_cat:
            line(meta, cat)
            cur_cat = meta
        val = _fmt(cfg, key)
        marker = "▸ " if i == sel else "  "
        attr = selattr if i == sel else item
        star = "  ★" if key == "charge_limit_mv" and cfg[key] == 4100 else ""
        line("%s%-15s %s%s" % (marker, label, val, star), attr)
    y += 1
    line("E · PERFORMANCE / SAG    (Phase 2)", dim)
    line("F · ADVANCED ⚠           (Phase 3)", dim)

    hint = msg or " ↑↓ field   ←→ adjust   ⏎ cycle   S save   Esc back "
    draw_status_bar(scr, h, w, hint, curses.color_pair(C_STATUS))
    scr.refresh()


_ROW_CAT = {
    "profile": "B · BUILD PROFILE",
    "capacity_mah": "B · BUILD PROFILE",
    "charge_limit_mv": "C · CHARGE  (sysfs, kernel-guarded)",
    "charge_current_ma": "C · CHARGE  (sysfs, kernel-guarded)",
    "warn_mv": "D · DISCHARGE PROTECTION",
    "shutdown_mv": "D · DISCHARGE PROTECTION",
}


def _fmt(cfg, key):
    cells = cfg["cells"]
    if key == "profile":
        return bl.PROFILE_LABELS.get(cfg["profile"], cfg["profile"])
    if key == "capacity_mah":
        return "%d mAh  (%dS)" % (cfg["capacity_mah"], cells)
    if key == "charge_limit_mv":
        return "Longevity 4.1V" if cfg[key] == 4100 else "Full 4.2V"
    if key == "charge_current_ma":
        return "%d mA" % cfg[key]
    if key in ("warn_mv", "shutdown_mv"):
        return "%.2f V/cell  (%d mV)" % (cfg[key] / 1000.0, cfg[key])
    return str(cfg.get(key))


def run_battery_config(scr):
    """Power/Battery config screen (Phase 1)."""
    cfg = bl.load_battery_cfg()
    rows = bl.editable_rows()
    sel = 0
    msg = None
    js = open_gamepad()
    scr.timeout(1000)  # refresh telemetry ~1/s
    try:
        while True:
            tele = bl.read_telemetry()
            _draw(scr, cfg, tele, sel, rows, msg)
            msg = None
            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None:
                continue
            if key in (27, ord("q"), ord("Q"), ord("b"), ord("B")) or gp == "back":
                return
            rkey = rows[sel][0]
            if key in (curses.KEY_UP, ord("k")) or gp == "up":
                sel = (sel - 1) % len(rows)
            elif key in (curses.KEY_DOWN, ord("j")) or gp == "down":
                sel = (sel + 1) % len(rows)
            elif key in (curses.KEY_LEFT, ord("h")) or gp == "left":
                cfg = bl.bump_value(cfg, rkey, -1)
            elif key in (curses.KEY_RIGHT, ord("l")) or gp == "right":
                cfg = bl.bump_value(cfg, rkey, +1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "a":
                cfg = bl.cycle_value(cfg, rkey)
            elif key in (ord("s"), ord("S")):
                saved = bl.save_battery_cfg(cfg)
                cfg = bl.load_battery_cfg()
                cfg.update(saved)
                msg = "  ✓ saved to console.json — apply via uconsole-battery-apply (Phase 1 plan)"
    finally:
        close_gamepad(js)
        scr.timeout(100)


HANDLERS = {"_battery_config": run_battery_config}
