"""TUI module: launcher — detached external-process spawn helper"""

import os
import shlex
import shutil
import subprocess
import tempfile

# (basename, exec_flag, title_flag_or_None)
# NOTE: alacritty requires -e to be the last flag — title flag must be inserted BEFORE -e.
KNOWN_TERMINALS = [
    ("lxterminal", "-e", "--title"),
    ("foot", "--", "--title"),
    ("kitty", "--", "--title"),
    ("xterm", "-e", "-T"),
    ("alacritty", "-e", "--title"),
    ("xfce4-terminal", "-e", "--title"),
    ("gnome-terminal", "--", "--title"),
]

_TERM_NAMES = [t[0] for t in KNOWN_TERMINALS]


def detect_terminal() -> str:
    """Return path to a terminal emulator, or empty string if none found."""
    env_term = os.environ.get("WATCHDOGS_TERMINAL", "").strip()
    if env_term:
        env_base = os.path.basename(env_term)
        if env_base in _TERM_NAMES:
            if os.path.isfile(env_term) and os.access(env_term, os.X_OK):
                return env_term
            found = shutil.which(env_base)
            if found:
                return found
        # Not allowlisted or not executable — fall through

    # Walk up the process tree
    try:
        pid = os.getppid()
        for _ in range(32):
            if pid <= 1:
                break
            try:
                with open(f"/proc/{pid}/comm", "r") as f:
                    comm = f.read().strip()
            except (ProcessLookupError, PermissionError, FileNotFoundError):
                break
            if comm in _TERM_NAMES:
                found = shutil.which(comm)
                if found:
                    return found
            try:
                with open(f"/proc/{pid}/stat", "r") as f:
                    stat = f.read()
                # ppid is field 4, but comm may contain spaces in parens
                rparen = stat.rfind(")")
                fields = stat[rparen + 2:].split()
                pid = int(fields[1])
            except (ProcessLookupError, PermissionError, FileNotFoundError, ValueError, IndexError):
                break
    except Exception:
        pass

    env_terminal = os.environ.get("TERMINAL", "").strip()
    if env_terminal:
        found = shutil.which(env_terminal)
        if found:
            return found

    for name in ["lxterminal", "foot", "kitty", "xterm"]:
        found = shutil.which(name)
        if found:
            return found

    return ""


def _is_safe_path(resolved):
    home = os.path.realpath(os.path.expanduser("~"))
    if resolved.startswith(home + os.sep) or resolved == home:
        return True
    if resolved == "/opt/WatchDogsGo" or resolved.startswith("/opt/WatchDogsGo" + os.sep):
        return True
    return False


def find_watchdogs_path() -> str:
    """Return first existing WatchDogsGo path (containing run.sh), or empty."""
    candidates = [
        os.environ.get("WATCHDOGS_HOME", ""),
        "~/python/WatchDogsGo",
        "~/WatchDogsGo",
        "~/git/WatchDogsGo",
        "/opt/WatchDogsGo",
    ]
    for p in candidates:
        if not p:
            continue
        expanded = os.path.expanduser(p)
        if not os.path.isfile(os.path.join(expanded, "run.sh")):
            continue
        resolved = os.path.realpath(expanded)
        if not _is_safe_path(resolved):
            continue
        return expanded
    return ""


def default_watchdogs_install_path() -> str:
    """Canonical WatchDogsGo install location."""
    return os.path.expanduser("~/python/WatchDogsGo")


def launch_gui(cmd, cwd=None) -> subprocess.Popen:
    """Spawn a detached GUI process (no terminal wrapper)."""
    if isinstance(cmd, str):
        raise TypeError("cmd must be a list (argv form), not a string")
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def launch_in_terminal(cmd, cwd=None, title=None, hold=True) -> subprocess.Popen:
    """Spawn cmd inside a detected terminal emulator, detached."""
    if isinstance(cmd, str):
        raise TypeError("cmd must be a list (argv form), not a string")

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise RuntimeError("no display available (headless session)")

    term_path = detect_terminal()
    if not term_path:
        raise RuntimeError("no terminal emulator found")

    term_base = os.path.basename(term_path)
    exec_flag = "-e"
    title_flag = None
    for name, ef, tf in KNOWN_TERMINALS:
        if name == term_base:
            exec_flag = ef
            title_flag = tf
            break

    payload = f"cd {shlex.quote(cwd)} && " if cwd else ""
    payload += " ".join(shlex.quote(a) for a in cmd)
    if hold:
        payload += "; read -p 'Press Enter to close...'"

    final_argv = [term_path, exec_flag, "bash", "-c", payload]
    if title_flag and title:
        final_argv.insert(1, title_flag)
        final_argv.insert(2, title)

    return subprocess.Popen(
        final_argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def is_running(lockfile_path) -> bool:
    """True if lockfile exists and PID inside is alive. Cleans up stale locks."""
    if not os.path.exists(lockfile_path):
        return False
    try:
        with open(lockfile_path, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        clear_lock(lockfile_path)
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        clear_lock(lockfile_path)
        return False
    except PermissionError:
        # Process exists but not ours
        return True
    except OSError:
        clear_lock(lockfile_path)
        return False


def write_lock(lockfile_path, pid) -> None:
    """Atomically write pid to lockfile_path.

    Raises FileExistsError if the destination already exists; caller is
    responsible for clearing stale locks via clear_lock().
    """
    if os.path.lexists(lockfile_path):
        raise FileExistsError(lockfile_path)
    fd, tmp = tempfile.mkstemp(
        prefix=os.path.basename(lockfile_path) + ".",
        suffix=".tmp",
        dir=os.path.dirname(lockfile_path) or ".",
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"{pid}\n")
        os.replace(tmp, lockfile_path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def clear_lock(lockfile_path) -> None:
    """Remove lockfile, suppressing FileNotFoundError."""
    try:
        os.unlink(lockfile_path)
    except FileNotFoundError:
        pass
