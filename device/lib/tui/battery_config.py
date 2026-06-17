"""TUI module: battery_config — Power/Battery configuration screen.

Curses front-end over ``battery_lib`` (all logic/telemetry lives there).
Lives under POWER → Power Config.  Phase 1: live telemetry + editable charge
limit/current and warn/shutdown thresholds + build-profile preset.  Persists to
``console.json`` ``battery.*``; the privileged sysfs/udev applier is a separate
plan item (the screen shows live hardware state vs pending config).
"""

import curses

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


# category each editable row sits under, + per-field hint shown when selected
_ROW_CAT = {
    "profile": ("B · BUILD PROFILE", "cycle through 18650 / 1S LiPo / 2S / Custom"),
    "capacity_mah": ("B · BUILD PROFILE", "pack capacity for runtime estimate — 500–20000 mAh"),
    "charge_limit_mv": ("C · CHARGE  (sysfs, kernel-guarded)",
                        "⏎ toggle  ·  Longevity 4.1V ≈ 2× cycle life for ~10% capacity"),
    "charge_current_ma": ("C · CHARGE  (sysfs, kernel-guarded)",
                          "max charge current — 300–2000 mA, 150 mA step"),
    "warn_mv": ("D · DISCHARGE PROTECTION", "low-battery warning — per-cell resting, 3100–3900 mV"),
    "shutdown_mv": ("D · DISCHARGE PROTECTION", "graceful shutdown — per-cell resting, clamp ≥3000 mV"),
}
_ADJUSTABLE = {"capacity_mah", "charge_current_ma", "warn_mv", "shutdown_mv"}


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
        return "%.2f V/cell" % (cfg[key] / 1000.0)
    return str(cfg.get(key))


def _bar(pct, width=22):
    pct = max(0, min(100, pct or 0))
    fill = round(width * pct / 100)
    return "█" * fill + "░" * (width - fill)


def _draw(scr, cfg, base, tele, sel, rows, msg):
    h, w = scr.getmaxyx()
    scr.erase()
    draw_header(scr, w)
    y = [4]
    cat = curses.color_pair(C_CAT) | curses.A_BOLD
    item = curses.color_pair(C_ITEM)
    dim = curses.color_pair(C_ITEM) | curses.A_DIM
    acc = curses.color_pair(C_HEADER) | curses.A_BOLD
    selattr = curses.color_pair(C_HEADER) | curses.A_BOLD | curses.A_REVERSE

    def line(text, attr, indent=2):
        if y[0] < h - 2:
            scr.addnstr(y[0], indent, text, w - indent - 1, attr)
        y[0] += 1

    cells = cfg["cells"]
    v = tele["voltage"]

    # A — live telemetry with charge bar
    line("A · TELEMETRY", cat)
    pct = tele["capacity"]
    charging = "Charging" in (tele["status"] or "")
    bar_attr = acc if charging else (item if (pct or 0) > 20 else
                                     curses.color_pair(C_ITEM) | curses.A_BOLD)
    line("  [%s] %s%%" % (_bar(pct), pct if pct is not None else "—"), bar_attr)
    pc = ("  (%.2f/cell)" % (v / cells)) if v and cells > 1 else ""
    line("  %s%s   %s%s   %s" % (
        "%.3f V" % v if v else "—", pc,
        "⚡ " if charging else "", tele["status"],
        "%.1f W" % tele["power"] if tele["power"] else ""), dim)
    # live hardware state vs pending config
    line("  live: charge≤%s · target %s · VOFF %s" % (
        "%dmA" % tele["charge_current_ma"] if tele["charge_current_ma"] else "?",
        "%.2fV" % tele["voltage_max"] if tele["voltage_max"] else "?",
        "%.2fV" % tele["voltage_min"] if tele["voltage_min"] else "?"), dim)
    y[0] += 1

    # editable tiers B–D
    cur_cat = None
    hint = None
    for i, (key, label, _kind) in enumerate(rows):
        meta_cat, meta_hint = _ROW_CAT[key]
        if meta_cat != cur_cat:
            line(meta_cat, cat)
            cur_cat = meta_cat
        selected = (i == sel)
        if selected:
            hint = meta_hint
        val = _fmt(cfg, key)
        if selected and key in _ADJUSTABLE:
            shown = "◂ %s ▸" % val
        elif selected:
            shown = "[ %s ]" % val
        else:
            shown = val
        star = "  ★" if key == "charge_limit_mv" and cfg[key] == 4100 else ""
        marker = "▸ " if selected else "  "
        attr = selattr if selected else item
        line("%s%-15s %s%s" % (marker, label, shown, star), attr)
    y[0] += 1
    line("E · PERFORMANCE / SAG    (Phase 2)", dim)
    line("F · ADVANCED ⚠           (Phase 3)", dim)

    # status: unsaved marker + per-field hint
    dirty = cfg != base
    if msg:
        status = msg
    elif hint:
        status = ("  ● unsaved   " if dirty else "  ") + hint
    else:
        status = "  ↑↓ field   ←→ adjust   ⏎ cycle   S save   Esc back"
    draw_status_bar(scr, h, w, status[:w - 1], curses.color_pair(C_STATUS) |
                    (curses.A_BOLD if dirty and not msg else 0))
    scr.refresh()


def run_battery_config(scr):
    """Power/Battery config screen (Phase 1)."""
    base = bl.load_battery_cfg()
    cfg = dict(base)
    rows = bl.editable_rows()
    sel = 0
    msg = None
    msg_ttl = 0
    js = open_gamepad()
    scr.timeout(1000)  # refresh telemetry ~1/s
    try:
        while True:
            tele = bl.read_telemetry()
            _draw(scr, cfg, base, tele, sel, rows, msg)
            if msg:
                msg_ttl -= 1
                if msg_ttl <= 0:
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
                base = bl.load_battery_cfg()
                base.update(saved)
                cfg = dict(base)
                msg = "  ✓ saved — apply via uconsole-battery-apply (next plan item)"
                msg_ttl = 3
    finally:
        close_gamepad(js)
        scr.timeout(100)


HANDLERS = {"_battery_config": run_battery_config}
