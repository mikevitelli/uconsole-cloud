"""TUI module: services"""

import curses
import os
import subprocess
import time

from tui.framework import (
    C_CAT,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_STATUS,
    SCRIPT_DIR,
    _tui_input_loop,
    draw_header,
    draw_status_bar,
    open_gamepad,
)


def run_cron_viewer(scr):
    """View crontab and systemd timers."""
    js = open_gamepad()
    scr.timeout(100)
    scroll = 0

    def get_cron_info():
        lines = []
        lines.append("── User Crontab ──")
        try:
            cron = subprocess.check_output(["crontab", "-l"], stderr=subprocess.DEVNULL, timeout=3).decode()
            if cron.strip():
                for l in cron.strip().splitlines():
                    lines.append(f"  {l}")
            else:
                lines.append("  (empty)")
        except Exception:
            lines.append("  (no crontab)")

        lines.append("")
        lines.append("── Systemd Timers ──")
        try:
            timers = subprocess.check_output(
                ["systemctl", "list-timers", "--no-pager", "--no-legend"],
                stderr=subprocess.DEVNULL, timeout=3
            ).decode()
            if timers.strip():
                for l in timers.strip().splitlines():
                    lines.append(f"  {l}")
            else:
                lines.append("  (none)")
        except Exception:
            lines.append("  (unavailable)")

        lines.append("")
        lines.append("── User Timers ──")
        try:
            utimers = subprocess.check_output(
                ["systemctl", "--user", "list-timers", "--no-pager", "--no-legend"],
                stderr=subprocess.DEVNULL, timeout=3
            ).decode()
            if utimers.strip():
                for l in utimers.strip().splitlines():
                    lines.append(f"  {l}")
            else:
                lines.append("  (none)")
        except Exception:
            pass

        return lines

    lines = get_cron_info()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Scheduled Tasks "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        view_h = h - 3
        for i in range(view_h):
            li = scroll + i
            if li >= len(lines):
                break
            line = lines[li][:w - 2]
            attr = curses.color_pair(C_CAT) | curses.A_BOLD if line.startswith("──") else curses.color_pair(C_ITEM)
            try:
                scr.addnstr(i + 1, 1, line, w - 2, attr)
            except curses.error:
                pass

        bar = " ↑↓ Scroll │ X Refresh │ B Back ".center(w)
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
            scroll = max(0, scroll - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            scroll = min(max(0, len(lines) - view_h), scroll + 1)
        elif gp == "refresh" or key == ord("r"):
            lines = get_cron_info()
            scroll = 0

    if js:
        js.close()

def run_webdash_config(scr):
    _run_config_editor(scr, "Webdash Login", WEBDASH_CONF,
                       [("Username", ""), ("Password", "")],
                       {"Username": "user", "Password": "pass"},
                       restart_cmd=["systemctl", "--user", "restart", "webdash.service"])


PUSH_INTERVALS = ["30s", "1min", "2min", "5min", "10min", "15min", "30min"]
STATUS_TIMER = os.path.expanduser("~/.config/systemd/user/uconsole-status.timer")

def run_push_interval(scr):
    """Change cloud status push frequency."""
    h, w = scr.getmaxyx()
    # read current
    current = "5min"
    try:
        with open(STATUS_TIMER) as f:
            for line in f:
                if line.strip().startswith("OnUnitActiveSec="):
                    current = line.strip().split("=", 1)[1]
    except FileNotFoundError:
        pass

    # show picker
    sel = PUSH_INTERVALS.index(current) if current in PUSH_INTERVALS else 3
    js = open_gamepad()
    scr.timeout(100)
    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        draw_header(scr, w)
        row = 6
        title = "Push Interval"
        scr.addnstr(row, 2, title, w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        row += 2
        for i, interval in enumerate(PUSH_INTERVALS):
            marker = " ● " if i == sel else "   "
            attr = curses.color_pair(C_HEADER) | curses.A_BOLD if i == sel else curses.color_pair(C_ITEM)
            scr.addnstr(row + i, 4, f"{marker}{interval}", w - 8, attr)
        hint = " ↑↓ Select  Enter Confirm  Esc Cancel "
        draw_status_bar(scr, h, w, hint, curses.color_pair(C_STATUS))
        scr.refresh()

        key, gp_action = _tui_input_loop(scr, js)
        if key == -1 and gp_action is None:
            continue
        if key == 27 or key == ord("q") or key == ord("Q") or gp_action == "back":
            if js:
                js.close()
            scr.timeout(100)
            return
        elif key == curses.KEY_UP or key == ord("k"):
            sel = (sel - 1) % len(PUSH_INTERVALS)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = (sel + 1) % len(PUSH_INTERVALS)
        elif key in (curses.KEY_ENTER, 10, 13) or gp_action == "enter":
            break

    if js:
        js.close()

    new_interval = PUSH_INTERVALS[sel]
    # update timer file
    try:
        timer_src = os.path.join(os.path.dirname(SCRIPT_DIR), "config", "systemd-user", "uconsole-status.timer")
        lines = []
        with open(timer_src) as f:
            for line in f:
                if line.strip().startswith("OnUnitActiveSec="):
                    lines.append(f"OnUnitActiveSec={new_interval}\n")
                else:
                    lines.append(line)
        with open(timer_src, "w") as f:
            f.writelines(lines)
        _pkg = os.path.isdir('/opt/uconsole/scripts')
        _sctl = ["sudo", "systemctl"] if _pkg else ["systemctl", "--user"]
        subprocess.run(_sctl + ["daemon-reload"], timeout=10, capture_output=True)
        subprocess.run(_sctl + ["restart", "uconsole-status.timer"], timeout=10, capture_output=True)
        msg = f"  ✓ Push interval set to {new_interval}"
    except Exception as e:
        msg = f"  ✗ Failed: {e}"

    draw_status_bar(scr, h, w, msg, curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    time.sleep(1.5)
