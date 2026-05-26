"""TUI module: files"""

import curses
import os

from tui.framework import (
    C_CAT,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    _tui_input_loop,
    open_gamepad,
)


def run_file_browser(scr):
    """Simple file browser with directory navigation."""
    js = open_gamepad()
    scr.timeout(100)
    cwd = os.path.expanduser("~")
    sel = 0
    scroll = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = f" {cwd} "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        try:
            entries = sorted(os.listdir(cwd))
            entries = [".."] + entries
        except PermissionError:
            entries = [".. (permission denied)"]

        # Build display lines
        items = []
        for e in entries:
            path = os.path.join(cwd, e) if e != ".." else os.path.dirname(cwd)
            if e == "..":
                items.append(("↑ ..", "", "dir"))
            elif os.path.isdir(os.path.join(cwd, e)):
                items.append((f"◆ {e}/", "", "dir"))
            else:
                try:
                    sz = os.path.getsize(os.path.join(cwd, e))
                    if sz > 1024 * 1024:
                        szs = f"{sz / (1024*1024):.1f}M"
                    elif sz > 1024:
                        szs = f"{sz // 1024}K"
                    else:
                        szs = f"{sz}B"
                except OSError:
                    szs = "?"
                items.append((f"  {e}", szs, "file"))

        sel = min(sel, max(0, len(items) - 1))
        view_h = h - 3

        if sel < scroll:
            scroll = sel
        elif sel >= scroll + view_h:
            scroll = sel - view_h + 1

        for i in range(view_h):
            idx = scroll + i
            if idx >= len(items):
                break
            name, size, ftype = items[idx]
            y = i + 1
            if idx == sel:
                attr = curses.color_pair(C_SEL) | curses.A_BOLD
            elif ftype == "dir":
                attr = curses.color_pair(C_CAT)
            else:
                attr = curses.color_pair(C_ITEM)
            marker = "▸" if idx == sel else " "
            try:
                scr.addnstr(y, 0, f" {marker} {name}", w - 10, attr)
                if size:
                    scr.addnstr(y, w - 8, size.rjust(6), 6, attr)
            except curses.error:
                pass

        bar = " ↑↓ Navigate │ A Open │ B Back ".center(w)
        try:
            scr.addnstr(h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            # Go up or exit
            parent = os.path.dirname(cwd)
            if parent != cwd:
                cwd = parent
                sel = 0
                scroll = 0
            else:
                break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(items) - 1, sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if items:
                name, _, ftype = items[sel]
                if sel == 0:  # ..
                    cwd = os.path.dirname(cwd)
                    sel = 0
                    scroll = 0
                elif ftype == "dir":
                    dirname = name.replace("◆ ", "").rstrip("/")
                    cwd = os.path.join(cwd, dirname)
                    sel = 0
                    scroll = 0

    if js:
        js.close()


HANDLERS = {
    "_filebrowser": run_file_browser,
}
