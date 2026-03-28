"""TUI module: tools"""

import curses
import os
import re
import subprocess
import time

from tui.framework import (
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


# ── Tile drawing ───────────────────────────────────────────────────────────

TILE_W_MIN = 22
TILE_H = 5

CAT_ICONS = {
    "SYSTEM": "⚙",
    "MONITOR": "◉",
    "FILES": "▤",
    "POWER": "⚡",
    "NETWORK": "◎",
    "HARDWARE": "⌁",
    "TOOLS": "★",
    "CONFIG": "☰",
}

CAT_DESCS = {
    "SYSTEM": "updates, backups, webdash, timers",
    "MONITOR": "real-time CPU, RAM, temp, and logs",
    "FILES": "file browser, audits, disk and storage",
    "POWER": "battery, cell health, charging, PMU",
    "NETWORK": "WiFi, Bluetooth, SSH, diagnostics",
    "HARDWARE": "AIO board, GPS, SDR, LoRa, ESP32",
    "TOOLS": "git, notes, calculator, stopwatch",
    "CONFIG": "theme, view mode, keybinds",
}
