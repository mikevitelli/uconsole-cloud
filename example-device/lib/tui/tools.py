"""TUI module: tools"""

import curses
import json
import os
import re
import subprocess
import time

from tui.framework import (
    C_BORDER,
    C_CAT,
    C_DIM,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    _tui_input_loop,
    open_gamepad,
    wait_for_input,
)
import tui_lib as tui


def run_git_panel(scr):
    """Git repository status and quick actions."""
    js = open_gamepad()
    scr.timeout(100)
    scroll = 0

    def get_git_info():
        lines = []
        home = os.path.expanduser("~")
        try:
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"], timeout=3, cwd=home
            ).decode().strip()
            lines.append(f"Branch:   {branch}")
        except Exception:
            lines.append("Not a git repo")
            return lines

        try:
            status = subprocess.check_output(
                ["git", "status", "--short"], timeout=3, cwd=home
            ).decode().strip()
            if status:
                lines.append("")
                lines.append("── Changes ──")
                for l in status.splitlines()[:20]:
                    lines.append(f"  {l}")
            else:
                lines.append("Status:   clean")
        except Exception:
            pass

        try:
            try:
                ahead = subprocess.check_output(
                    ["git", "rev-list", "--count", "@{u}..HEAD"],
                    timeout=3, cwd=home, stderr=subprocess.DEVNULL
                ).decode().strip()
            except subprocess.CalledProcessError:
                ahead = "0"
            try:
                behind = subprocess.check_output(
                    ["git", "rev-list", "--count", "HEAD..@{u}"],
                    timeout=3, cwd=home, stderr=subprocess.DEVNULL
                ).decode().strip()
            except subprocess.CalledProcessError:
                behind = "0"
            lines.append(f"Remote:   ↑{ahead} ↓{behind}")
        except Exception:
            pass

        lines.append("")
        lines.append("── Recent Commits ──")
        try:
            log = subprocess.check_output(
                ["git", "log", "--oneline", "-10"], timeout=3, cwd=home
            ).decode().strip()
            for l in log.splitlines():
                lines.append(f"  {l}")
        except Exception:
            pass

        return lines

    lines = get_git_info()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Git Panel "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        view_h = h - 3
        for i in range(view_h):
            li = scroll + i
            if li >= len(lines):
                break
            line = lines[li]
            if line.startswith("──"):
                attr = curses.color_pair(C_CAT) | curses.A_BOLD
            elif line.startswith("Branch:") or line.startswith("Status:") or line.startswith("Remote:"):
                attr = curses.color_pair(C_STATUS) | curses.A_BOLD
            else:
                attr = curses.color_pair(C_ITEM)
            try:
                scr.addnstr(i + 1, 1, line[:w - 2], w - 2, attr)
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
            lines = get_git_info()
            scroll = 0

    if js:
        js.close()

def run_syslog_viewer(scr):
    """Live system log viewer (journalctl)."""
    js = open_gamepad()
    scr.timeout(500)
    lines = []
    paused = False

    def fetch_logs():
        try:
            out = subprocess.check_output(
                ["journalctl", "--no-pager", "-n", "100", "--output=short-iso"],
                timeout=5
            ).decode()
            return [re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', l) for l in out.splitlines()]
        except Exception:
            return ["(failed to read logs)"]

    lines = fetch_logs()
    scroll = max(0, len(lines) - 1)

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = f" System Log {'(paused)' if paused else '(live)'} "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        view_h = h - 3
        # Auto-scroll to bottom if not paused
        if not paused:
            scroll = max(0, len(lines) - view_h)

        for i in range(view_h):
            li = scroll + i
            if li >= len(lines):
                break
            line = lines[li][:w - 2]
            attr = curses.color_pair(C_ITEM)
            if "error" in line.lower() or "fail" in line.lower():
                attr = curses.color_pair(C_HEADER) | curses.A_BOLD
            elif "warn" in line.lower():
                attr = curses.color_pair(C_CAT)
            try:
                scr.addnstr(i + 1, 1, line, w - 2, attr)
            except curses.error:
                pass

        bar = " ↑↓ Scroll │ A Pause/Resume │ X Refresh │ B Back ".center(w)
        try:
            scr.addnstr(h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            if not paused:
                lines = fetch_logs()
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            paused = True
            scroll = max(0, scroll - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            scroll = min(max(0, len(lines) - view_h), scroll + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            paused = not paused
        elif gp == "refresh" or key == ord("r"):
            lines = fetch_logs()
            paused = False

    if js:
        js.close()
    scr.timeout(100)

def run_notes(scr):
    """Quick notes scratchpad — view and append."""
    js = open_gamepad()
    scr.timeout(100)
    notes_file = os.path.expanduser("~/notes.txt")
    scroll = 0

    def load_notes():
        try:
            return open(notes_file).read().splitlines()
        except FileNotFoundError:
            return ["(no notes yet — press A to add)"]

    lines = load_notes()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Quick Notes "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        view_h = h - 3
        for i in range(view_h):
            li = scroll + i
            if li >= len(lines):
                break
            try:
                scr.addnstr(i + 1, 1, lines[li][:w - 2], w - 2, curses.color_pair(C_ITEM))
            except curses.error:
                pass

        bar = " ↑↓ Scroll │ A Add Note │ X Refresh │ B Back ".center(w)
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
        elif gp == "refresh":
            lines = load_notes()
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            # Drop to input mode
            curses.echo()
            curses.curs_set(1)
            scr.move(h - 2, 1)
            scr.clrtoeol()
            scr.addnstr(h - 2, 1, "Note: ", 6, curses.color_pair(C_STATUS) | curses.A_BOLD)
            scr.refresh()
            try:
                note = scr.getstr(h - 2, 7, w - 10).decode("utf-8", errors="replace").strip()
                if note:
                    ts = time.strftime("%Y-%m-%d %H:%M")
                    with open(notes_file, "a") as f:
                        f.write(f"[{ts}] {note}\n")
                    lines = load_notes()
                    scroll = max(0, len(lines) - view_h)
            except Exception:
                pass
            curses.noecho()
            curses.curs_set(0)

    if js:
        js.close()

def run_ssh_bookmarks(scr):
    """SSH connection bookmarks from ~/.ssh/config."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0

    def parse_ssh_config():
        hosts = []
        config = os.path.expanduser("~/.ssh/config")
        if not os.path.isfile(config):
            return hosts
        current = {}
        for line in open(config):
            line = line.strip()
            if line.lower().startswith("host ") and "*" not in line:
                if current.get("name"):
                    hosts.append(current)
                current = {"name": line.split()[1], "hostname": "", "user": "", "port": "22"}
            elif current:
                low = line.lower()
                if low.startswith("hostname"):
                    current["hostname"] = line.split()[-1]
                elif low.startswith("user"):
                    current["user"] = line.split()[-1]
                elif low.startswith("port"):
                    current["port"] = line.split()[-1]
        if current.get("name"):
            hosts.append(current)
        return hosts

    hosts = parse_ssh_config()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = f" SSH Bookmarks ({len(hosts)}) "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        if not hosts:
            try:
                scr.addnstr(3, 4, "No hosts in ~/.ssh/config", w - 8, curses.color_pair(C_DIM))
            except curses.error:
                pass
        else:
            hdr = f"  {'NAME':<20} {'HOST':<25} {'USER':<15} {'PORT'}"
            try:
                scr.addnstr(1, 0, hdr, w, curses.color_pair(C_CAT) | curses.A_BOLD)
            except curses.error:
                pass
            sel = min(sel, max(0, len(hosts) - 1))
            for i, host in enumerate(hosts):
                if i + 2 >= h - 2:
                    break
                line = f"  {host['name']:<20} {host['hostname']:<25} {host['user']:<15} {host['port']}"
                attr = curses.color_pair(C_SEL) | curses.A_BOLD if i == sel else curses.color_pair(C_ITEM)
                marker = "▸" if i == sel else " "
                try:
                    scr.addnstr(i + 2, 0, f"{marker}{line}", w, attr)
                except curses.error:
                    pass

        bar = " ↑↓ Select │ A Connect │ B Back ".center(w)
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
            sel = min(len(hosts) - 1, sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if hosts and sel < len(hosts):
                name = hosts[sel]["name"]
                curses.endwin()
                os.system("clear")
                subprocess.run(["ssh", name])
                print("\n  Press any key to return...")
                wait_for_input()
                scr.refresh()
                curses.doupdate()

    if js:
        js.close()

def run_keybinds(scr):
    """Show keybind reference."""
    js = open_gamepad()
    scr.timeout(100)

    binds = [
        ("── Main Menu ──", ""),
        ("↑ / ↓ / k / j", "Navigate items"),
        ("← / → / h / l", "Switch category"),
        ("Enter / A", "Run selected"),
        ("B", "Previous category"),
        ("X / r", "Refresh"),
        ("Y / q", "Quit"),
        ("", ""),
        ("── Panel Viewer ──", ""),
        ("↑ / ↓ / k / j", "Scroll output"),
        ("PgUp / PgDn", "Page scroll"),
        ("A", "Scroll down"),
        ("X / r", "Re-run script"),
        ("B / q", "Back to menu"),
        ("", ""),
        ("── Stream Viewer ──", ""),
        ("X / r", "Re-run (when done)"),
        ("B / Y / q", "Stop / Back"),
        ("", ""),
        ("── Tile View ──", ""),
        ("↑ ↓ ← →", "Navigate tiles"),
        ("A / Enter", "Select / Drill in"),
        ("B / ESC", "Back to categories"),
        ("", ""),
        ("── Gamepad ──", ""),
        ("A (btn 1)", "Enter / Confirm"),
        ("B (btn 2)", "Back / Cancel"),
        ("X (btn 0)", "Refresh / Alt action"),
        ("Y (btn 3)", "Quit"),
        ("D-pad", "Arrow keys"),
    ]

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Keybind Reference "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        for i, (key_str, desc) in enumerate(binds):
            y = i + 2
            if y >= h - 2:
                break
            if key_str.startswith("──"):
                attr = curses.color_pair(C_CAT) | curses.A_BOLD
                try:
                    scr.addnstr(y, 2, key_str, w - 4, attr)
                except curses.error:
                    pass
            elif key_str:
                try:
                    scr.addnstr(y, 4, key_str, 20, curses.color_pair(C_ITEM) | curses.A_BOLD)
                    scr.addnstr(y, 26, desc, w - 28, curses.color_pair(C_DIM))
                except curses.error:
                    pass

        bar = " B Back ".center(w)
        try:
            scr.addnstr(h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == ord("q") or key == ord("Q") or gp == "back" or key in (curses.KEY_ENTER, 10, 13):
            break

    if js:
        js.close()

def run_stopwatch(scr):
    """Stopwatch with start/stop/reset."""
    js = open_gamepad()
    scr.timeout(100)
    running = False
    start_time = 0
    elapsed = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Stopwatch "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        # Calculate time
        if running:
            total = elapsed + (time.time() - start_time)
        else:
            total = elapsed

        mins = int(total // 60)
        secs = total % 60
        hrs = mins // 60
        mins = mins % 60

        time_str = f"{int(hrs):02d}:{int(mins):02d}:{secs:05.2f}"

        # Large centered display
        cy = h // 2 - 1
        cx = max(0, (w - len(time_str)) // 2)
        try:
            scr.addnstr(cy, cx, time_str, w,
                         curses.color_pair(C_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        status = "▶ RUNNING" if running else "⏸ STOPPED"
        sx = max(0, (w - len(status)) // 2)
        try:
            scr.addnstr(cy + 2, sx, status, w,
                         curses.color_pair(C_STATUS) if running else curses.color_pair(C_DIM))
        except curses.error:
            pass

        bar = " A Start/Stop │ X Reset │ B Back ".center(w)
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
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter" or key == ord(" "):
            if running:
                elapsed += time.time() - start_time
                running = False
            else:
                start_time = time.time()
                running = True
        elif gp == "refresh" or key == ord("r") or key == ord("x"):
            running = False
            elapsed = 0

    if js:
        js.close()

def run_calculator(scr):
    """Simple expression calculator."""
    js = open_gamepad()
    scr.timeout(100)
    history = []

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = " Calculator "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        # Show history
        start = max(0, len(history) - (h - 5))
        for i, (expr, result) in enumerate(history[start:]):
            y = i + 2
            if y >= h - 3:
                break
            try:
                scr.addnstr(y, 2, f"> {expr}", w - 4, curses.color_pair(C_DIM))
                scr.addnstr(y, 2 + len(expr) + 4, f"= {result}", w - len(expr) - 8,
                             curses.color_pair(C_STATUS) | curses.A_BOLD)
            except curses.error:
                pass

        bar = " A Enter expression │ X Clear │ B Back ".center(w)
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
        elif gp == "refresh":
            history.clear()
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            curses.echo()
            curses.curs_set(1)
            scr.move(h - 2, 1)
            scr.clrtoeol()
            scr.addnstr(h - 2, 1, "> ", 2, curses.color_pair(C_STATUS))
            scr.refresh()
            try:
                expr = scr.getstr(h - 2, 3, w - 6).decode("utf-8", errors="replace").strip()
                if expr:
                    try:
                        # Safe eval — only math
                        allowed = {"__builtins__": {}}
                        allowed.update({k: getattr(math, k) for k in dir(math) if not k.startswith("_")})
                        result = str(eval(expr, allowed))
                    except Exception as e:
                        result = f"error: {e}"
                    history.append((expr, result))
            except Exception:
                pass
            curses.noecho()
            curses.curs_set(0)

    if js:
        js.close()

def run_screenshot(scr):
    """Capture screenshot using scrot."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.expanduser(f"~/screenshot-{ts}.png")

    curses.endwin()
    time.sleep(0.3)  # Let curses release screen

    try:
        subprocess.run(["scrot", path], timeout=5)
        print(f"\n  ✓ Screenshot saved: {path}")
    except FileNotFoundError:
        print("\n  ✗ scrot not installed")
    except Exception as e:
        print(f"\n  ✗ Screenshot failed: {e}")

    print("\n  Press any key to return...")
    wait_for_input()
    scr.refresh()
    curses.doupdate()


def run_pomodoro(scr):
    """Pomodoro focus timer — 25min work / 5min break cycles."""
    js = open_gamepad()
    scr.timeout(100)
    running = False
    start_time = 0
    remaining = 25 * 60  # seconds remaining in current phase
    phase = "WORK"        # WORK, BREAK, LONG BREAK
    pomodoros = 0          # completed work sessions
    cycle_count = 0        # work sessions since last long break

    def phase_duration():
        if phase == "WORK":
            return 25 * 60
        elif phase == "LONG BREAK":
            return 15 * 60
        else:
            return 5 * 60

    def next_phase():
        nonlocal phase, remaining, cycle_count, pomodoros
        if phase == "WORK":
            pomodoros += 1
            cycle_count += 1
            if cycle_count >= 4:
                phase = "LONG BREAK"
                cycle_count = 0
            else:
                phase = "BREAK"
        else:
            phase = "WORK"
        remaining = phase_duration()
        curses.beep()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # Calculate remaining time
        if running:
            elapsed = time.time() - start_time
            display_rem = max(0, remaining - elapsed)
            if display_rem <= 0:
                remaining = 0
                running = False
                next_phase()
                display_rem = remaining
        else:
            display_rem = remaining

        mins = int(display_rem) // 60
        secs = int(display_rem) % 60
        time_str = f"{mins:02d}:{secs:02d}"

        # Phase color
        if phase == "WORK":
            phase_attr = curses.color_pair(C_STATUS) | curses.A_BOLD
        elif phase == "BREAK":
            phase_attr = curses.color_pair(C_CAT) | curses.A_BOLD
        else:
            phase_attr = curses.color_pair(C_HEADER) | curses.A_BOLD

        # Panel
        pw = min(40, w - 4)
        px = max(0, (w - pw) // 2)
        py = max(1, h // 2 - 5)

        tui.panel_top(scr, py, px, pw, title="Pomodoro")
        for row in range(1, 9):
            tui.panel_side(scr, py + row, px, pw)
        tui.panel_bot(scr, py + 9, px, pw)

        # Phase label
        tui.put(scr, py + 2, max(0, (w - len(phase)) // 2), phase, w, phase_attr)

        # Big centered countdown
        cx = max(0, (w - len(time_str)) // 2)
        tui.put(scr, py + 4, cx, time_str, w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)

        # Status
        status = "RUNNING" if running else "PAUSED"
        tui.put(scr, py + 6, max(0, (w - len(status)) // 2), status, w,
                curses.color_pair(C_STATUS) if running else curses.color_pair(C_DIM))

        # Pomodoro count
        count_str = f"Pomodoros: {pomodoros}"
        tui.put(scr, py + 8, max(0, (w - len(count_str)) // 2), count_str, w,
                curses.color_pair(C_ITEM))

        bar = " A Start/Pause | X Skip Phase | B Quit ".center(w)
        tui.put(scr, h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter" or key == ord(" "):
            if running:
                elapsed = time.time() - start_time
                remaining = max(0, remaining - elapsed)
                running = False
            else:
                start_time = time.time()
                running = True
        elif gp == "refresh" or key == ord("x"):
            if running:
                running = False
            next_phase()

    if js:
        js.close()


# Module-level cache for weather data
_weather_cache = {"data": None, "time": 0}


def run_weather(scr):
    """Weather dashboard — fetches from wttr.in."""
    js = open_gamepad()
    scr.timeout(100)
    last_fetch = _weather_cache["time"]
    data = _weather_cache["data"]
    error_msg = ""

    def fetch_weather():
        nonlocal data, error_msg, last_fetch
        try:
            out = subprocess.check_output(
                ["curl", "-s", "wttr.in/?format=j1"], timeout=10,
                stderr=subprocess.DEVNULL
            ).decode()
            parsed = json.loads(out)
            cur = parsed["current_condition"][0]
            data = {
                "temp_c": cur.get("temp_C", "?"),
                "feels_like": cur.get("FeelsLikeC", "?"),
                "humidity": cur.get("humidity", "?"),
                "wind_kmph": cur.get("windspeedKmph", "?"),
                "wind_dir": cur.get("winddir16Point", ""),
                "desc": cur.get("weatherDesc", [{}])[0].get("value", ""),
                "location": parsed.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", "Unknown"),
            }
            error_msg = ""
            last_fetch = time.time()
            _weather_cache["data"] = data
            _weather_cache["time"] = last_fetch
        except Exception:
            if data is None:
                error_msg = "No connection"

    # Fetch on entry if cache is stale (>5min) or empty
    if data is None or (time.time() - last_fetch) > 300:
        fetch_weather()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        if error_msg and data is None:
            tui.put(scr, 0, 0, " Weather ".center(w), w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
            tui.put(scr, h // 2, max(0, (w - len(error_msg)) // 2),
                    error_msg, w, curses.color_pair(C_DIM))
        elif data:
            # CURRENT panel
            pw = min(44, w - 4)
            px = max(0, (w - pw) // 2)
            py = 1

            tui.panel_top(scr, py, px, pw, title="CURRENT", detail=data["location"])
            for row in range(1, 5):
                tui.panel_side(scr, py + row, px, pw)
            tui.panel_bot(scr, py + 5, px, pw)

            big_temp = f"{data['temp_c']}°C"
            tui.put(scr, py + 2, max(0, (w - len(big_temp)) // 2), big_temp, w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
            tui.put(scr, py + 4, px + 3, data["desc"], pw - 6,
                    curses.color_pair(C_ITEM))

            # CONDITIONS panel
            cy = py + 7
            tui.panel_top(scr, cy, px, pw, title="CONDITIONS")
            for row in range(1, 6):
                tui.panel_side(scr, cy + row, px, pw)
            tui.panel_bot(scr, cy + 6, px, pw)

            details = [
                f"Feels Like:  {data['feels_like']}°C",
                f"Humidity:    {data['humidity']}%",
                f"Wind:        {data['wind_kmph']} km/h {data['wind_dir']}",
            ]
            for i, line in enumerate(details):
                tui.put(scr, cy + 2 + i, px + 3, line, pw - 6,
                        curses.color_pair(C_ITEM))

            age = int(time.time() - last_fetch)
            age_str = f"Updated {age}s ago"
            tui.put(scr, cy + 5, px + 3, age_str, pw - 6,
                    curses.color_pair(C_DIM))

        bar = " X Refresh | B Quit ".center(w)
        tui.put(scr, h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            # Auto-refresh every 5 minutes
            if time.time() - last_fetch > 300:
                fetch_weather()
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif gp == "refresh" or key == ord("x") or key == ord("r"):
            fetch_weather()

    if js:
        js.close()


def run_hackernews(scr):
    """Hacker News top stories browser."""
    js = open_gamepad()
    scr.timeout(100)
    stories = []
    sel = 0
    scroll = 0
    error_msg = ""

    def fetch_stories():
        nonlocal stories, error_msg
        try:
            out = subprocess.check_output(
                ["curl", "-s", "https://hacker-news.firebaseio.com/v0/topstories.json"],
                timeout=10, stderr=subprocess.DEVNULL
            ).decode()
            ids = json.loads(out)[:20]
            items = []
            for item_id in ids:
                try:
                    item_out = subprocess.check_output(
                        ["curl", "-s",
                         f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"],
                        timeout=5, stderr=subprocess.DEVNULL
                    ).decode()
                    item = json.loads(item_out)
                    items.append({
                        "title": item.get("title", "(no title)"),
                        "score": item.get("score", 0),
                        "by": item.get("by", "?"),
                        "descendants": item.get("descendants", 0),
                        "url": item.get("url", ""),
                    })
                except Exception:
                    continue
            stories = items
            error_msg = ""
        except Exception:
            if not stories:
                error_msg = "No connection"

    fetch_stories()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = f" Hacker News — Top {len(stories)} "
        tui.put(scr, 0, 0, title.center(w), w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)

        if error_msg and not stories:
            tui.put(scr, h // 2, max(0, (w - len(error_msg)) // 2),
                    error_msg, w, curses.color_pair(C_DIM))
        else:
            view_h = h - 3
            # Ensure selection is visible
            if sel < scroll:
                scroll = sel
            elif sel >= scroll + view_h:
                scroll = sel - view_h + 1

            for i in range(view_h):
                li = scroll + i
                if li >= len(stories):
                    break
                s = stories[li]
                marker = ">" if li == sel else " "
                line = f"{marker} {s['title']}"
                meta = f"  {s['score']}pts | {s['by']} | {s['descendants']} comments"
                attr = curses.color_pair(C_SEL) | curses.A_BOLD if li == sel else curses.color_pair(C_ITEM)
                meta_attr = curses.color_pair(C_SEL) if li == sel else curses.color_pair(C_DIM)
                y = 1 + i * 2
                if y >= h - 2:
                    break
                tui.put(scr, y, 1, line, w - 2, attr)
                if y + 1 < h - 2:
                    tui.put(scr, y + 1, 1, meta, w - 2, meta_attr)

            # Recalc view_h for 2-line items
            view_h = (h - 3) // 2

        bar = " Up/Down Select | A Open URL | X Refresh | B Quit ".center(w)
        tui.put(scr, h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(max(0, len(stories) - 1), sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if stories and sel < len(stories):
                url = stories[sel].get("url", "")
                if url:
                    browser = os.environ.get("BROWSER", "")
                    if browser:
                        curses.endwin()
                        subprocess.run([browser, url])
                        scr.refresh()
                        curses.doupdate()
                    else:
                        # Show URL for copying
                        tui.put(scr, h - 2, 1, f"URL: {url}", w - 2,
                                curses.color_pair(C_STATUS) | curses.A_BOLD)
                        scr.refresh()
                        # Wait for any key
                        _tui_input_loop(scr, js)
        elif gp == "refresh" or key == ord("x") or key == ord("r"):
            fetch_stories()
            sel = 0
            scroll = 0

    if js:
        js.close()


def run_mdviewer(scr):
    """Markdown note viewer — browse and read .md files."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0
    scroll = 0
    mode = "list"  # list or view
    view_lines = []
    view_scroll = 0
    view_title = ""

    def scan_md_files():
        dirs = [
            os.path.expanduser("~/notes"),
            os.path.expanduser("~/docs"),
            "/opt/uconsole/webdash/docs",
        ]
        files = []
        for d in dirs:
            if not os.path.isdir(d):
                continue
            try:
                for f in sorted(os.listdir(d)):
                    if f.endswith(".md"):
                        files.append(os.path.join(d, f))
            except OSError:
                continue
        return files

    def render_md(text):
        """Parse markdown into (line, attr) tuples."""
        lines = []
        in_code = False
        for raw in text.splitlines():
            if raw.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                lines.append((f"  {raw}", curses.color_pair(C_DIM)))
                continue
            stripped = raw.strip()
            if stripped.startswith("# "):
                lines.append((stripped[2:], curses.color_pair(C_HEADER) | curses.A_BOLD))
            elif stripped.startswith("## "):
                lines.append((stripped[3:], curses.color_pair(C_CAT) | curses.A_BOLD))
            elif stripped.startswith("### "):
                lines.append((stripped[4:], curses.color_pair(C_CAT)))
            elif stripped.startswith("- ") or stripped.startswith("* "):
                lines.append((f"  * {stripped[2:]}", curses.color_pair(C_ITEM)))
            elif stripped == "":
                lines.append(("", curses.color_pair(C_ITEM)))
            else:
                # Handle inline bold
                display = stripped
                attr = curses.color_pair(C_ITEM)
                if "**" in display:
                    display = display.replace("**", "")
                    attr = curses.color_pair(C_ITEM) | curses.A_BOLD
                if "`" in display:
                    display = display.replace("`", "")
                    attr = curses.color_pair(C_DIM)
                lines.append((display, attr))
        return lines

    md_files = scan_md_files()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        if mode == "list":
            title = f" Markdown Viewer ({len(md_files)} files) "
            tui.put(scr, 0, 0, title.center(w), w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)

            if not md_files:
                tui.put(scr, h // 2, 4, "No .md files found", w - 8,
                        curses.color_pair(C_DIM))
            else:
                view_h = h - 3
                if sel < scroll:
                    scroll = sel
                elif sel >= scroll + view_h:
                    scroll = sel - view_h + 1
                sel = min(sel, max(0, len(md_files) - 1))

                for i in range(view_h):
                    li = scroll + i
                    if li >= len(md_files):
                        break
                    fname = os.path.basename(md_files[li])
                    parent = os.path.basename(os.path.dirname(md_files[li]))
                    line = f"  {parent}/{fname}"
                    marker = ">" if li == sel else " "
                    attr = curses.color_pair(C_SEL) | curses.A_BOLD if li == sel else curses.color_pair(C_ITEM)
                    tui.put(scr, i + 1, 0, f"{marker}{line}", w, attr)

            bar = " Up/Down Select | A Open | B Quit ".center(w)
            tui.put(scr, h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
            scr.refresh()

            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None:
                continue
            if key == ord("q") or key == ord("Q") or gp == "back":
                break
            elif key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(max(0, len(md_files) - 1), sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                if md_files and sel < len(md_files):
                    try:
                        text = open(md_files[sel]).read()
                        view_lines = render_md(text)
                        view_title = os.path.basename(md_files[sel])
                        view_scroll = 0
                        mode = "view"
                    except Exception:
                        pass

        elif mode == "view":
            title = f" {view_title} "
            tui.put(scr, 0, 0, title.center(w), w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)

            view_h = h - 3
            for i in range(view_h):
                li = view_scroll + i
                if li >= len(view_lines):
                    break
                text, attr = view_lines[li]
                tui.put(scr, i + 1, 1, text, w - 2, attr)

            bar = " Up/Down/j/k Scroll | B Back ".center(w)
            tui.put(scr, h - 1, 0, bar, w, curses.color_pair(C_FOOTER))
            scr.refresh()

            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None:
                continue
            if key == ord("q") or key == ord("Q") or gp == "back":
                mode = "list"
            elif key == curses.KEY_UP or key == ord("k"):
                view_scroll = max(0, view_scroll - 1)
            elif key == curses.KEY_DOWN or key == ord("j"):
                view_scroll = min(max(0, len(view_lines) - view_h), view_scroll + 1)

    if js:
        js.close()
