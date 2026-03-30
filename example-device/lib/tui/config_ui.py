"""TUI module: config_ui"""

import curses
import subprocess
import time

from tui.framework import (
    COLOR_MAP,
    COLOR_NAMES,
    C_CAT,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_PICKER_PREV1,
    C_PICKER_PREV2,
    C_PICKER_PREV3,
    C_PICKER_SWATCH,
    C_SEL,
    C_STATUS,
    GP_A,
    GP_B,
    GP_X,
    GP_Y,
    THEMES,
    THEME_FOLDERS,
    TILE_PAIR_BASE,
    apply_theme,
    build_custom_theme,
    draw_separator,
    draw_status_bar,
    load_config,
    load_theme,
    load_view_mode,
    open_gamepad,
    read_gamepad,
    save_config,
    save_config_multi,
)


def run_custom_theme_picker(scr):
    """Pick primary and secondary colors for a custom theme."""
    cfg = load_config()
    pri_sel = COLOR_NAMES.index(cfg.get("custom_primary", "cyan"))
    sec_sel = COLOR_NAMES.index(cfg.get("custom_secondary", "magenta"))
    field = 0  # 0 = primary, 1 = secondary
    js = open_gamepad()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Custom Theme "
        scr.addnstr(0, 0, title.center(w), w,
                     curses.color_pair(C_HEADER) | curses.A_BOLD)
        draw_separator(scr, 1, w)

        # Primary color row
        pri_label = "  PRIMARY:    "
        sec_label = "  SECONDARY:  "

        y_pri = 3
        y_sec = 5

        pri_attr = curses.A_BOLD if field == 0 else curses.A_NORMAL
        sec_attr = curses.A_BOLD if field == 1 else curses.A_NORMAL

        scr.addnstr(y_pri, 0, pri_label, w,
                     curses.color_pair(C_CAT) | pri_attr)
        scr.addnstr(y_sec, 0, sec_label, w,
                     curses.color_pair(C_CAT) | sec_attr)

        # Draw color options for primary
        x = len(pri_label)
        for i, cname in enumerate(COLOR_NAMES):
            cval = COLOR_MAP[cname]
            curses.init_pair(C_PICKER_SWATCH, cval, -1)
            if i == pri_sel and field == 0:
                attr = curses.color_pair(C_PICKER_SWATCH) | curses.A_BOLD | curses.A_REVERSE
            elif i == pri_sel:
                attr = curses.color_pair(C_PICKER_SWATCH) | curses.A_BOLD | curses.A_UNDERLINE
            else:
                attr = curses.color_pair(C_PICKER_SWATCH)
            tag = f" {cname} "
            if x + len(tag) < w:
                scr.addnstr(y_pri, x, tag, w - x, attr)
            x += len(tag) + 1

        # Draw color options for secondary
        x = len(sec_label)
        for i, cname in enumerate(COLOR_NAMES):
            cval = COLOR_MAP[cname]
            curses.init_pair(C_PICKER_SWATCH, cval, -1)
            if i == sec_sel and field == 1:
                attr = curses.color_pair(C_PICKER_SWATCH) | curses.A_BOLD | curses.A_REVERSE
            elif i == sec_sel:
                attr = curses.color_pair(C_PICKER_SWATCH) | curses.A_BOLD | curses.A_UNDERLINE
            else:
                attr = curses.color_pair(C_PICKER_SWATCH)
            tag = f" {cname} "
            if x + len(tag) < w:
                scr.addnstr(y_sec, x, tag, w - x, attr)
            x += len(tag) + 1

        # Preview swatch
        y_prev = 8
        scr.addnstr(y_prev, 2, "PREVIEW:", w - 4,
                     curses.color_pair(C_CAT) | curses.A_BOLD)
        preview = build_custom_theme(COLOR_NAMES[pri_sel], COLOR_NAMES[sec_sel])
        curses.init_pair(C_PICKER_PREV1, preview["header"], -1)
        scr.addnstr(y_prev + 1, 4, "▸ Header / Item text", w - 6,
                     curses.color_pair(C_PICKER_PREV1) | curses.A_BOLD)
        curses.init_pair(C_PICKER_PREV2, preview["cat"], -1)
        scr.addnstr(y_prev + 2, 4, "  Category / Border", w - 6,
                     curses.color_pair(C_PICKER_PREV2))
        curses.init_pair(C_PICKER_PREV3, preview["sel_fg"], preview["sel_bg"])
        scr.addnstr(y_prev + 3, 4, "  Selected item     ", w - 6,
                     curses.color_pair(C_PICKER_PREV3) | curses.A_BOLD)

        bar = " ↑↓ Field │ ←→ Color │ A Apply │ B Back ".center(w)
        try:
            scr.addnstr(h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass

        scr.refresh()

        try:
            key = scr.getch()
        except curses.error:
            key = -1

        gp_action = None
        for btn in read_gamepad(js):
            if btn == GP_A:
                gp_action = "apply"
            elif btn == GP_B or btn == GP_Y:
                gp_action = "back"

        if key == -1 and gp_action is None:
            continue
        elif key == ord("q") or key == ord("Q") or gp_action == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            field = 0
        elif key == curses.KEY_DOWN or key == ord("j"):
            field = 1
        elif key == curses.KEY_LEFT or key == ord("h"):
            if field == 0:
                pri_sel = (pri_sel - 1) % len(COLOR_NAMES)
            else:
                sec_sel = (sec_sel - 1) % len(COLOR_NAMES)
        elif key == curses.KEY_RIGHT or key == ord("l"):
            if field == 0:
                pri_sel = (pri_sel + 1) % len(COLOR_NAMES)
            else:
                sec_sel = (sec_sel + 1) % len(COLOR_NAMES)
        elif key in (curses.KEY_ENTER, 10, 13) or gp_action == "apply":
            save_config_multi({
                "custom_primary": COLOR_NAMES[pri_sel],
                "custom_secondary": COLOR_NAMES[sec_sel],
                "theme": "custom",
            })
            apply_theme("custom")
            break

    apply_theme()
    if js:
        js.close()

def _draw_theme_tile(scr, y, x, tw, th, name, tile_idx, selected, active):
    """Draw a single theme tile with color preview swatch.

    Each tile gets its own 5 color pair slots (based on tile_idx) so
    curses doesn't retroactively repaint earlier tiles when a later
    tile re-initializes the same pair number.
    """
    if name == "custom":
        cfg = load_config()
        t = build_custom_theme(cfg.get("custom_primary", "cyan"),
                               cfg.get("custom_secondary", "magenta"))
    else:
        t = THEMES.get(name, THEMES["cyan"])

    maxh = scr.getmaxyx()[0]

    # Per-tile pair slots
    p_hdr = TILE_PAIR_BASE + tile_idx * 5
    p_cat = p_hdr + 1
    p_sel = p_hdr + 2
    p_brd = p_hdr + 3
    p_lbl = p_hdr + 4

    curses.init_pair(p_brd, t["border"], -1)
    curses.init_pair(p_hdr, t["header"], -1)
    curses.init_pair(p_cat, t["cat"],    -1)
    curses.init_pair(p_sel, t["sel_fg"], t["sel_bg"])
    curses.init_pair(p_lbl, t["header"], -1)

    # Border
    brd_attr = curses.color_pair(p_brd)
    if selected:
        brd_attr |= curses.A_BOLD | curses.A_REVERSE

    try:
        scr.addnstr(y, x, "╭" + "─" * (tw - 2) + "╮", tw, brd_attr)
        for row in range(1, th - 1):
            scr.addnstr(y + row, x, "│", 1, brd_attr)
            scr.addnstr(y + row, x + tw - 1, "│", 1, brd_attr)
        scr.addnstr(y + th - 1, x, "╰" + "─" * (tw - 2) + "╯", tw, brd_attr)
    except curses.error:
        pass

    # Color preview bar (row 1 inside tile) — header + cat swatches
    inner = tw - 4
    if inner > 0 and y + 1 < maxh - 1:
        half = max(1, inner // 2)
        try:
            scr.addnstr(y + 1, x + 2, "█" * half, half,
                         curses.color_pair(p_hdr) | curses.A_BOLD)
            scr.addnstr(y + 1, x + 2 + half, "█" * (inner - half), inner - half,
                         curses.color_pair(p_cat) | curses.A_BOLD)
        except curses.error:
            pass

    # Selection bar preview (row 2)
    if inner > 0 and y + 2 < maxh - 1:
        try:
            scr.addnstr(y + 2, x + 2, " sel " + " " * max(0, inner - 5), inner,
                         curses.color_pair(p_sel) | curses.A_BOLD)
        except curses.error:
            pass

    # Name label (row 3)
    if y + 3 < maxh - 1:
        label = name[:inner]
        if active:
            label = name[:max(1, inner - 2)] + " ●"
        try:
            scr.addnstr(y + 3, x + 2, label.center(inner), inner,
                         curses.color_pair(p_lbl) | curses.A_BOLD)
        except curses.error:
            pass

def run_theme_picker(scr):
    """In-TUI tiled theme picker with folder tabs."""
    current = load_theme()
    folder_idx = 0
    sel = 0
    # Find which folder the current theme is in
    for fi, (fname, fthemes) in enumerate(THEME_FOLDERS):
        if current in fthemes:
            folder_idx = fi
            sel = fthemes.index(current)
            break
    js = open_gamepad()

    TILE_W = 14
    TILE_H = 5

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Theme Picker "
        scr.addnstr(0, 0, title.center(w), w,
                     curses.color_pair(C_HEADER) | curses.A_BOLD)

        # Folder tabs
        tab_y = 2
        tab_x = 2
        for fi, (fname, _) in enumerate(THEME_FOLDERS):
            label = f" {fname} "
            if fi == folder_idx:
                attr = curses.color_pair(C_SEL) | curses.A_BOLD
            else:
                attr = curses.color_pair(C_ITEM)
            if tab_x + len(label) < w:
                try:
                    scr.addnstr(tab_y, tab_x, label, w - tab_x, attr)
                except curses.error:
                    pass
            tab_x += len(label) + 1

        draw_separator(scr, tab_y + 1, w)

        # Draw tiles in a grid
        folder_name, folder_themes = THEME_FOLDERS[folder_idx]
        content_y = tab_y + 3
        cols = max(1, (w - 2) // (TILE_W + 1))
        sel = min(sel, len(folder_themes) - 1)
        sel = max(0, sel)

        for i, tname in enumerate(folder_themes):
            row = i // cols
            col = i % cols
            ty = content_y + row * (TILE_H + 1)
            tx = 1 + col * (TILE_W + 1)
            if ty + TILE_H >= h - 2:
                break
            is_active = (tname == current)
            _draw_theme_tile(scr, ty, tx, TILE_W, TILE_H, tname, i, i == sel, is_active)

        bar = " ←→↑↓ Navigate │ [/]/X Folder │ A Apply │ B Back "
        if "custom" in folder_themes:
            bar = " ←→↑↓ Navigate │ [/]/X Folder │ A Edit │ B Back "
        try:
            scr.addnstr(h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass

        scr.refresh()

        try:
            key = scr.getch()
        except curses.error:
            key = -1

        gp_action = None
        for btn in read_gamepad(js):
            if btn == GP_A:
                gp_action = "apply"
            elif btn == GP_B or btn == GP_Y:
                gp_action = "back"
            elif btn == GP_X:
                gp_action = "next_folder"

        if key == -1 and gp_action is None:
            continue
        elif key == ord("q") or key == ord("Q") or key == 27 or gp_action == "back":
            break
        elif key == ord("\t") or key == curses.KEY_NPAGE or key == ord("]") or gp_action == "next_folder":
            folder_idx = (folder_idx + 1) % len(THEME_FOLDERS)
            sel = 0
        elif key == curses.KEY_BTAB or key == curses.KEY_PPAGE or key == ord("["):
            folder_idx = (folder_idx - 1) % len(THEME_FOLDERS)
            sel = 0
        elif key == curses.KEY_RIGHT or key == ord("l"):
            if sel + 1 < len(folder_themes):
                sel += 1
        elif key == curses.KEY_LEFT or key == ord("h"):
            if sel > 0:
                sel -= 1
        elif key == curses.KEY_DOWN or key == ord("j"):
            if sel + cols < len(folder_themes):
                sel += cols
        elif key == curses.KEY_UP or key == ord("k"):
            if sel - cols >= 0:
                sel -= cols
        elif key in (curses.KEY_ENTER, 10, 13) or gp_action == "apply":
            name = folder_themes[sel]
            if name == "custom":
                if js:
                    js.close()
                    js = None
                run_custom_theme_picker(scr)
                current = load_theme()
                js = open_gamepad()
            else:
                save_config("theme", name)
                apply_theme(name)
                current = name

    apply_theme()
    if js:
        js.close()

def run_bat_gauge_toggle(scr):
    """Toggle battery gauge mode: auto (vest when discharging, capacity when charging), vest-only, or capacity-only."""
    modes = ["auto", "vest", "capacity"]
    labels = {
        "auto": "auto (vest on battery, gauge on AC)",
        "vest": "voltage-estimated only",
        "capacity": "AXP228 fuel gauge only",
    }
    current = load_config().get("bat_gauge", "auto")
    idx = modes.index(current) if current in modes else 0
    new_mode = modes[(idx + 1) % len(modes)]
    save_config("bat_gauge", new_mode)
    h, w = scr.getmaxyx()
    draw_status_bar(scr, h, w, f"  ✓ Battery gauge: {labels[new_mode]}",
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    time.sleep(1)

def run_viewmode_toggle(scr):
    """Toggle between list and tile view. Returns new mode name to signal switch."""
    current = load_view_mode()
    new_mode = "tiles" if current == "list" else "list"
    save_config("view_mode", new_mode)
    h, w = scr.getmaxyx()
    draw_status_bar(scr, h, w, f"  ✓ Switching to {new_mode} view...",
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    time.sleep(0.5)
    return new_mode

def run_trackball_scroll_toggle(scr):
    """Toggle trackball scroll daemon (Select + trackball = scroll)."""
    import os
    svc = "trackball-scroll.service"
    svc_src = "/opt/uconsole/share/systemd/trackball-scroll.service"
    svc_dst = os.path.expanduser("~/.config/systemd/user/trackball-scroll.service")

    # Ensure service file is linked (disable removes it)
    if not os.path.exists(svc_dst) and os.path.exists(svc_src):
        os.makedirs(os.path.dirname(svc_dst), exist_ok=True)
        os.symlink(svc_src, svc_dst)
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       capture_output=True)

    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", svc],
            capture_output=True, text=True
        )
        enabled = result.stdout.strip() == "enabled"
    except Exception:
        enabled = False

    h, w = scr.getmaxyx()
    if enabled:
        subprocess.run(["systemctl", "--user", "stop", svc],
                       capture_output=True)
        subprocess.run(["systemctl", "--user", "disable", svc],
                       capture_output=True)
        draw_status_bar(scr, h, w, "  ✓ Trackball scroll: OFF",
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
    else:
        # Re-link if disable removed it
        if not os.path.exists(svc_dst) and os.path.exists(svc_src):
            os.symlink(svc_src, svc_dst)
            subprocess.run(["systemctl", "--user", "daemon-reload"],
                           capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", svc],
                       capture_output=True)
        subprocess.run(["systemctl", "--user", "start", svc],
                       capture_output=True)
        draw_status_bar(scr, h, w, "  ✓ Trackball scroll: ON (Fn + trackball)",
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    time.sleep(1)


# ── Native TUI tools ──────────────────────────────────────────────────────
