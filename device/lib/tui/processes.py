"""TUI module: process manager."""

import curses
import os
import signal
import subprocess
import time

from tui.framework import (
    C_CAT,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    _footer_bar,
    _tui_input_loop,
    close_gamepad,
    draw_status_bar,
    open_gamepad,
)


def run_process_manager(scr):
    """Interactive process viewer with kill support."""
    js = open_gamepad()
    scr.timeout(2000)
    sel = 0
    sort_by = "cpu"  # "cpu" or "mem"

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = f" Process Manager (sort: {sort_by}) "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        try:
            sf = "--sort=-%cpu" if sort_by == "cpu" else "--sort=-rss"
            out = subprocess.check_output(
                ["ps", "aux", sf], timeout=3
            ).decode()
            lines = out.splitlines()
            header = lines[0] if lines else ""
            procs = lines[1:] if len(lines) > 1 else []
        except Exception:
            procs = []
            header = ""

        try:
            scr.addnstr(1, 1, header[:w - 2], w - 2, curses.color_pair(C_CAT) | curses.A_BOLD)
        except curses.error:
            pass

        view_h = h - 4
        sel = min(sel, max(0, len(procs) - 1))

        for i in range(view_h):
            if i >= len(procs):
                break
            attr = curses.color_pair(C_SEL) | curses.A_BOLD if i == sel else curses.color_pair(C_ITEM)
            marker = "▸" if i == sel else " "
            try:
                scr.addnstr(i + 2, 0, f" {marker} {procs[i][:w - 4]}", w, attr)
            except curses.error:
                pass

        bar = _footer_bar(" ↑↓ Select │ A Kill │ X Sort │ B Back ", w)
        try:
            scr.addnstr(h - 1, 0, bar.ljust(w), w, curses.color_pair(C_FOOTER))
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
            sel = min(len(procs) - 1, sel + 1)
        elif gp == "refresh" or key == ord("x") or key == ord("X"):
            sort_by = "mem" if sort_by == "cpu" else "cpu"
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if procs and sel < len(procs):
                pid = procs[sel].split()[1] if len(procs[sel].split()) > 1 else None
                if pid and pid.isdigit() and 2 <= int(pid) <= 4194304:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        draw_status_bar(scr, h, w, f"  ✓ Sent SIGTERM to PID {pid}")
                    except ProcessLookupError:
                        draw_status_bar(scr, h, w, f"  ✗ Process {pid} not found")
                    except PermissionError:
                        draw_status_bar(scr, h, w, f"  ✗ Permission denied for PID {pid}")
                    scr.refresh()
                    time.sleep(1)

    if js:
        close_gamepad(js)
    scr.timeout(100)


HANDLERS = {
    "_processes": run_process_manager,
}
