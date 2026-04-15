"""TUI module: watchdogs — Watch Dogs Go launcher with auto-install"""

import curses
import os
import re
import time

from tui.framework import (
    C_CAT,
    C_DIM,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    GP_A,
    GP_B,
    _tui_input_loop,
    close_gamepad,
    draw_status_bar,
    load_config,
    open_gamepad,
    run_confirm,
    save_config,
)
from tui.launcher import (
    clear_lock,
    default_watchdogs_install_path,
    detect_terminal,
    find_watchdogs_path,
    is_running,
    launch_gui,
    launch_in_terminal,
    write_lock,
)

LOCKFILE = "/tmp/watchdogs-go.lock"
DEFAULT_REPO_URL = "https://github.com/LOCOSP/WatchDogsGo.git"
DEFAULT_BRANCH = "main"

_SAFE_URL_RE = re.compile(r"^(https?://|git@)[A-Za-z0-9._~:/\-@%#?=+]+\.git$")


def _safe_repo_url(url):
    """True if url looks like a plain http(s)/ssh git URL (no flag injection)."""
    return bool(url) and bool(_SAFE_URL_RE.match(str(url)))


def _path_is_safe(p):
    """True if realpath p is inside $HOME or /opt/WatchDogsGo."""
    home = os.path.realpath(os.path.expanduser("~"))
    p = os.path.realpath(p)
    if p == home or p.startswith(home + os.sep):
        return True
    if p == "/opt/WatchDogsGo" or p.startswith("/opt/WatchDogsGo" + os.sep):
        return True
    return False


def _toast(scr, msg, attr=None, delay=2.0):
    """Flash a status-bar message for `delay` seconds."""
    try:
        h, w = scr.getmaxyx()
        if attr is None:
            attr = curses.color_pair(C_STATUS) | curses.A_BOLD
        draw_status_bar(scr, h, w, f"  {msg}", attr)
        scr.refresh()
        time.sleep(delay)
    except Exception:
        pass


def _shquote(s):
    """Minimal shell quoting for paths/URLs."""
    return "'" + str(s).replace("'", "'\\''") + "'"


def run_watchdogs(scr):
    """Launch Watch Dogs Go, installing it first if missing."""
    cfg = load_config()
    cfg_path = cfg.get("watchdogs_path")
    repo_url = cfg.get("watchdogs_repo_url", DEFAULT_REPO_URL)
    if not _safe_repo_url(repo_url):
        repo_url = DEFAULT_REPO_URL
    auto_update = bool(cfg.get("watchdogs_auto_update", False))

    # Already running? — Advisory check only. lxterminal double-forks so the
    # PID we record dies immediately. This guard remains useful if a future
    # wrapper script writes its own long-lived PID into LOCKFILE.
    try:
        if is_running(LOCKFILE):
            _toast(scr, "Watch Dogs Go already running", delay=3.0)
            return
    except Exception:
        # If lockfile probing fails, fall through and try to launch.
        pass

    # Resolve install path
    path = cfg_path or find_watchdogs_path() or default_watchdogs_install_path()
    if not path:
        _toast(scr, "Watch Dogs Go: cannot determine install path", delay=3.0)
        return

    path = os.path.realpath(os.path.expanduser(path))
    if not _path_is_safe(path):
        path = default_watchdogs_install_path()
        path = os.path.realpath(os.path.expanduser(path))
    run_sh = os.path.join(path, "run.sh")
    installed = os.path.isfile(run_sh)

    try:
        if not installed:
            if not run_confirm(scr, "Install Watch Dogs Go?  ~200MB, needs sudo"):
                return

            parent = os.path.dirname(path.rstrip("/")) or "."
            basename = os.path.basename(path.rstrip("/")) or "WatchDogsGo"
            cmd = (
                f"set -e; mkdir -p {_shquote(parent)} && "
                f"cd {_shquote(parent)} && "
                f"git clone -- {_shquote(repo_url)} {_shquote(basename)} && "
                f"cd {_shquote(basename)} && "
                f"chmod +x setup.sh run.sh && "
                f"./setup.sh && "
                f"sudo -E ./run.sh"
            )

            child = launch_in_terminal(
                ["bash", "-c", cmd],
                title="Watch Dogs Go — Install & Launch",
                hold=True,
            )
            # Don't persist path until a successful launch — the next launch
            # attempt will re-discover via find_watchdogs_path().

        else:
            parts = []
            if auto_update:
                parts.append("git pull --ff-only || true")
            parts.append("sudo -E ./run.sh")
            cmd = " && ".join(parts)

            child = launch_in_terminal(
                ["bash", "-c", cmd],
                cwd=path,
                title="Watch Dogs Go",
                hold=True,
            )

            # Path is known-valid in launch branch — persist for next time
            try:
                save_config("watchdogs_path", path)
            except Exception:
                pass

        # Lock is advisory: lxterminal double-forks so the recorded PID
        # dies immediately. is_running() above will only catch truly-running
        # state if a future wrapper script writes its own PID to LOCKFILE.

        _toast(scr, "Watch Dogs Go launched", delay=1.5)

    except RuntimeError as e:
        _toast(scr, f"Cannot launch: {str(e)[:60]}", delay=3.0)
    except FileNotFoundError:
        _toast(scr, "Watch Dogs Go: terminal emulator missing", delay=3.0)
    except Exception as e:
        _toast(scr, f"Watch Dogs Go: {str(e)[:60]}", delay=3.0)


# ── Config submenu ──────────────────────────────────────────────────────────


def run_watchdogs_config(scr):
    """Read-only config view for Watch Dogs Go.  A toggles auto-update, B back."""
    js = open_gamepad()
    scr.timeout(150)

    try:
        while True:
            cfg = load_config()
            path = (cfg.get("watchdogs_path")
                    or find_watchdogs_path()
                    or default_watchdogs_install_path()
                    or "(unset)")
            auto_update = bool(cfg.get("watchdogs_auto_update", False))
            repo_url = cfg.get("watchdogs_repo_url", DEFAULT_REPO_URL)
            if not _safe_repo_url(repo_url):
                repo_url = DEFAULT_REPO_URL
            installed = os.path.isfile(os.path.join(os.path.expanduser(path), "run.sh")) \
                if path and path != "(unset)" else False

            h, w = scr.getmaxyx()
            scr.erase()

            title = "Watch Dogs Go — Settings"
            scr.addnstr(1, max(0, (w - len(title)) // 2), title, w,
                        curses.color_pair(C_HEADER) | curses.A_BOLD)

            rows = [
                ("Install path", path),
                ("Status",       "installed" if installed else "not installed"),
                ("Auto-update",  "ON" if auto_update else "OFF"),
                ("Repo URL",     repo_url),
            ]

            y = 4
            for label, value in rows:
                line_label = f"  {label:<14}: "
                scr.addnstr(y, 2, line_label, w - 4,
                            curses.color_pair(C_CAT) | curses.A_BOLD)
                scr.addnstr(y, 2 + len(line_label), str(value),
                            max(1, w - 4 - len(line_label)),
                            curses.color_pair(C_ITEM))
                y += 1

            y += 1
            hint1 = "  [A] Toggle auto-update"
            hint2 = "  Edit ~/.console-config.json to change path / repo URL"
            scr.addnstr(y,     2, hint1, w - 4, curses.color_pair(C_DIM))
            scr.addnstr(y + 1, 2, hint2, w - 4, curses.color_pair(C_DIM))

            footer = "  [A] Toggle  [B/ESC] Back  "
            try:
                scr.addnstr(h - 1, 0, footer.ljust(w), w,
                            curses.color_pair(C_FOOTER))
            except curses.error:
                pass

            scr.refresh()

            key, gp_action = _tui_input_loop(scr, js)

            if key in (27, ord("q"), ord("Q")) or gp_action == "back":
                return
            if key in (ord("a"), ord("A"), ord("\n"), curses.KEY_ENTER) \
                    or gp_action == "select":
                save_config("watchdogs_auto_update", not auto_update)
                draw_status_bar(
                    scr, h, w,
                    f"  ✓ Auto-update: {'ON' if not auto_update else 'OFF'}",
                    curses.color_pair(C_STATUS) | curses.A_BOLD,
                )
                scr.refresh()
                time.sleep(0.6)
    finally:
        if js:
            close_gamepad(js)
        scr.timeout(100)
