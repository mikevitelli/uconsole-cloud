"""TUI module: camera — chafa ASCII/braille viewfinder, photo, live feed (IMX219).

Self-contained (own camera plumbing) so a fault here can only ever hide the
Camera menu, never break the rest of the TUI. The IMX219 on this device is
mounted at 90°, so the upright rotation (a 90°-CW transpose) is baked into the
ffmpeg producer; rotation is live-cyclable.

The Preview does NOT reinvent a braille converter — it shells out to **chafa**.
A long-lived `rpicam-vid --codec mjpeg | ffmpeg -update 1` writes the latest
frame to tmpfs (/dev/shm), and each render runs chafa against that file. Because
chafa renders one image then exits and curses can't parse its ANSI, the preview
SUSPENDS curses and drives a fullscreen loop, restoring the TUI cleanly on quit.

Output mode is the highest-fidelity the terminal supports: **sixel** (foot) or
**kitty** pixel graphics — real pixels, far more defined than character art —
falling back to chafa **color blocks** then **braille**. Cycle with 'm'.

  Preview:  q Back   m mode (sixel/color/braille)   r rotate   +/- fps
"""
import curses
import datetime
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import tty

from tui.framework import _tui_input_loop, open_gamepad
import tui_lib as tui

FPS_OPTS = [5, 8, 10, 12, 15]
ROTATIONS = ["cw", "ccw", "180", "none"]
PHOTO_W, PHOTO_H = 3280, 2464    # full IMX219 8MP still
PICTURES = os.path.expanduser("~/Pictures")
SHM_FRAME = "/dev/shm/uconsole-cam.jpg"
CAP_W, CAP_H = 640, 480          # MJPEG capture size feeding chafa


# ── Availability ─────────────────────────────────────────────────────────
_CAM_AVAIL = None


def _have(cmd):
    return shutil.which(cmd) is not None


def camera_available():
    """True if rpicam reports at least one camera. Cached after first call."""
    global _CAM_AVAIL
    if _CAM_AVAIL is None:
        try:
            out = subprocess.run(["rpicam-hello", "--list-cameras"],
                                 capture_output=True, text=True, timeout=8).stdout
            _CAM_AVAIL = any(re.match(r"\s*\d+\s*:", ln) for ln in out.splitlines())
        except Exception:
            _CAM_AVAIL = False
    return _CAM_AVAIL


# ── Frame producer (MJPEG → tmpfs, rotation baked in) ────────────────────
class CameraProducer:
    """One long-lived `rpicam-vid --codec mjpeg | ffmpeg -update 1` pipeline that
    keeps the freshest frame at SHM_FRAME. ffmpeg applies the upright transpose
    and the preview fps, decoupling capture from chafa's render rate."""

    def __init__(self, rotate="cw", fps=12, width=CAP_W, height=CAP_H):
        self.rotate, self.fps = rotate, fps
        self.width, self.height = width, height
        self.proc = None

    def _vf(self):
        chain = {"cw": "transpose=1", "ccw": "transpose=2",
                 "180": "transpose=1,transpose=1", "none": ""}.get(self.rotate, "transpose=1")
        fps = f"fps={self.fps}"
        return f"{chain},{fps}" if chain else fps

    def start(self):
        cmd = (f"rpicam-vid -t 0 -n --codec mjpeg --width {self.width} "
               f"--height {self.height} --framerate {self.fps} -o - 2>/dev/null | "
               f"ffmpeg -loglevel quiet -f mjpeg -i - -vf {self._vf()} "
               f"-update 1 -y {SHM_FRAME}")
        try:
            self.proc = subprocess.Popen(["bash", "-lc", cmd],
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         start_new_session=True)
        except Exception:
            self.proc = None

    def stop(self):
        if self.proc:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(os.getpgid(self.proc.pid), sig)
                    self.proc.wait(timeout=2)
                    break
                except Exception:
                    continue
        self.proc = None
        try:
            if os.path.exists(SHM_FRAME):
                os.remove(SHM_FRAME)
        except OSError:
            pass

    def restart(self, rotate=None, fps=None):
        if rotate is not None:
            self.rotate = rotate
        if fps is not None:
            self.fps = fps
        self.stop()
        self.start()


# ── Output modes ─────────────────────────────────────────────────────────
# Pixel-graphics modes (sixel/kitty) render REAL pixels — far more defined than
# any character art. Character modes (color blocks / braille) are the portable
# fallback. _detect_graphics() picks the best the terminal supports.
MODE_LABELS = {"sixels": "sixel ·hi-def", "kitty": "kitty ·hi-def",
               "color": "color blocks", "braille": "braille"}


def _detect_graphics():
    """Return 'kitty', 'sixels', or None for the current terminal."""
    if os.environ.get("KITTY_WINDOW_ID") or "kitty" in os.environ.get("TERM", ""):
        return "kitty"
    term = os.environ.get("TERM", "")
    # terminals with native sixel support
    if any(t in term for t in ("foot", "mlterm", "wezterm", "contour", "yaft",
                               "sixel", "st-")):
        return "sixels"
    return None


def _modes():
    gfx = _detect_graphics()
    return ([gfx] if gfx else []) + ["color", "braille"]


def chafa_args(mode, cols, rows, fill=False):
    # fill -> stretch to the whole screen (distorts a portrait source);
    # otherwise fit preserving aspect + center (full height, side bars).
    size = ["-s", f"{cols}x{rows}"] + (["--stretch"] if fill else ["-C", "on"])
    if mode in ("sixels", "kitty"):
        return ["-f", mode, "--dither", "ordered", "-w", "9"] + size
    if mode == "color":
        return ["-f", "symbols", "-c", "full", "--symbols", "block+half+space",
                "--color-space", "din99d", "--dither", "ordered",
                "--dither-grain", "2x2", "-w", "3"] + size
    # braille (mono)
    return ["-f", "symbols", "-c", "none", "--fg-only", "--symbols", "braille",
            "--dither", "ordered", "--threshold", "0.55", "-w", "4"] + size


# ── ASCII Preview (suspend curses, fullscreen chafa loop) ────────────────
def run_ascii_preview(scr):
    js = open_gamepad()        # opened only so a stray gamepad read can't error elsewhere
    try:
        if not camera_available():
            _no_camera(scr, js)
            return
        if not (_have("chafa") and _have("rpicam-vid") and _have("ffmpeg")):
            _missing_tools(scr, js)
            return
        _chafa_loop(scr)
    finally:
        if js:
            js.close()


def _chafa_loop(scr):
    rot_idx, fps_idx = 0, 3                        # fps_idx 3 -> 12fps
    modes = _modes()
    mode_idx = 0                                   # default = best available (gfx if any)
    fill = False                                   # f toggles fit <-> fill(fullscreen)
    producer = CameraProducer(rotate=ROTATIONS[rot_idx], fps=FPS_OPTS[fps_idx])
    producer.start()

    curses.def_prog_mode()                        # save curses state
    curses.endwin()                               # hand the terminal back to the shell
    fd = sys.stdin.fileno()
    old_term = termios.tcgetattr(fd)
    tty.setcbreak(fd)                             # single-key reads, Ctrl-C still works
    sys.stdout.write("\033[?25l\033[2J")          # hide cursor, clear once
    sys.stdout.flush()
    prev_size = None
    try:
        while True:
            mode = modes[mode_idx]
            gfx = mode in ("sixels", "kitty")
            cols, rows = shutil.get_terminal_size((80, 24))
            view_rows = max(1, rows - 1)
            buf = b"\033[2J\033[H" if (cols, rows) != prev_size else b"\033[H"
            prev_size = (cols, rows)
            if os.path.exists(SHM_FRAME) and os.path.getsize(SHM_FRAME) > 0:
                try:
                    out = subprocess.run(["chafa", *chafa_args(mode, cols, view_rows, fill),
                                          SHM_FRAME], capture_output=True, timeout=4).stdout
                except Exception:
                    out = b""
                # char modes: erase rows a shorter frame would leave behind.
                # graphics: the equal-size image overwrites; don't erase (would
                # clip the image) — resize handles ghosting via the clear above.
                buf += out + (b"" if gfx else b"\033[J")
            else:
                buf += "waiting for camera…\033[J".encode()
            status = (f"\033[{rows};1H\033[7m {MODE_LABELS.get(mode, mode)} · "
                      f"{'fill' if fill else 'fit'} · {FPS_OPTS[fps_idx]}fps · "
                      f"rot:{ROTATIONS[rot_idx]}   "
                      f"q quit  m mode  f fit/fill  r rotate  +/- fps \033[0m")
            sys.stdout.buffer.write(buf)
            sys.stdout.write(status)
            sys.stdout.flush()

            timeout = max(0.03, 1.0 / FPS_OPTS[fps_idx])
            if select.select([fd], [], [], timeout)[0]:
                ch = sys.stdin.read(1).lower()
                if ch == "q":
                    break
                elif ch == "m":
                    mode_idx = (mode_idx + 1) % len(modes)
                    prev_size = None              # force a clear on mode switch
                elif ch == "f":
                    fill = not fill
                    prev_size = None              # force a clear on fit/fill switch
                elif ch == "r":
                    rot_idx = (rot_idx + 1) % len(ROTATIONS)
                    producer.restart(rotate=ROTATIONS[rot_idx])
                elif ch in "+=" and fps_idx < len(FPS_OPTS) - 1:
                    fps_idx += 1
                    producer.restart(fps=FPS_OPTS[fps_idx])
                elif ch in "-_" and fps_idx > 0:
                    fps_idx -= 1
                    producer.restart(fps=FPS_OPTS[fps_idx])
    finally:
        producer.stop()
        sys.stdout.write("\033[?25h\033[2J\033[H")    # show cursor, clear
        sys.stdout.flush()
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
        except Exception:
            pass
        curses.reset_prog_mode()                      # restore curses
        scr.clear()
        scr.refresh()


# ── Photo capture ───────────────────────────────────────────────────────
_PIL_ROT = None


def _pil_rot_map():
    global _PIL_ROT
    if _PIL_ROT is None:
        from PIL import Image
        _PIL_ROT = {"cw": Image.Transpose.ROTATE_270,    # 270° CCW == 90° CW
                    "ccw": Image.Transpose.ROTATE_90,
                    "180": Image.Transpose.ROTATE_180}
    return _PIL_ROT


def capture_photo(rotate="cw"):
    """Snap a full-res still, rotate to upright via PIL, save to ~/Pictures.
    Returns (path, None) on success or (None, error_message)."""
    try:
        os.makedirs(PICTURES, exist_ok=True)
    except OSError as e:
        return None, str(e)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(PICTURES, f"cam_{ts}.jpg")
    fd, tmp = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        r = subprocess.run(["rpicam-still", "-n", "-t", "800",
                            "--width", str(PHOTO_W), "--height", str(PHOTO_H),
                            "-o", tmp], capture_output=True, timeout=30)
        if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            msg = (r.stderr.decode(errors="replace")[-200:] if r.stderr else
                   "capture failed")
            return None, msg.strip() or "capture failed"
        try:
            from PIL import Image
            img = Image.open(tmp)
            tmap = _pil_rot_map()
            if rotate in tmap:
                img = img.transpose(tmap[rotate])
            img.save(out, quality=92)
        except Exception:
            shutil.move(tmp, out)       # save unrotated rather than lose the shot
        return out, None
    except subprocess.TimeoutExpired:
        return None, "capture timed out"
    except Exception as e:
        return None, str(e)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


# ── Live feed (fullscreen ffplay, curses suspended) ─────────────────────
def _feed_env():
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("LIBCAMERA_LOG_LEVELS", "*:ERROR")
    return env


def run_live_feed(scr, rotate="cw"):
    """Suspend curses and run the low-latency rpicam-vid | ffplay pipeline."""
    if not camera_available():
        return _no_camera(scr)
    if not (_have("rpicam-vid") and _have("ffplay")):
        return _missing_tools(scr)
    vf = {"cw": "transpose=1", "ccw": "transpose=2",
          "180": "transpose=1,transpose=1", "none": "null"}.get(rotate, "transpose=1")
    w, h, fps = 1280, 960, 30
    cmd = (f"rpicam-vid -t 0 --codec yuv420 --width {w} --height {h} "
           f"--framerate {fps} -n -o - | ffplay -hide_banner -loglevel error "
           f"-f rawvideo -pixel_format yuv420p -video_size {w}x{h} -framerate {fps} "
           f"-fflags nobuffer -flags low_delay -framedrop -avioflags direct "
           f"-vf {vf} -i -")
    curses.endwin()
    try:
        print("\nLaunching live preview… press q (or close the window) to return.\n",
              flush=True)
        subprocess.run(["bash", "-lc", cmd], env=_feed_env())
    except Exception:
        pass
    finally:
        scr.clear()
        scr.refresh()


# ── Shared small curses screens ──────────────────────────────────────────
def _wait_key(scr, js):
    scr.timeout(150)
    while True:
        key, gp = _tui_input_loop(scr, js)
        if key not in (-1, curses.ERR) or gp in ("back", "enter", "quit"):
            return


def _message(scr, js, title, lines, color):
    own = js is None
    if own:
        js = open_gamepad()
    scr.erase()
    h, w = scr.getmaxyx()
    tui.put(scr, 1, 1, title, w - 2, curses.color_pair(tui.C_CAT) | curses.A_BOLD)
    for i, (txt, attr) in enumerate(lines):
        tui.put(scr, 3 + i, 1, txt, w - 2, attr)
    tui.put(scr, h - 1, 1, "any key Back", w - 2, curses.color_pair(tui.C_FOOTER))
    scr.refresh()
    _wait_key(scr, js)
    if own and js:
        js.close()


def _no_camera(scr, js=None):
    _message(scr, js, "CAMERA", [
        ("No camera detected.", curses.color_pair(tui.C_CRIT) | curses.A_BOLD),
        ("Check: rpicam-hello --list-cameras", curses.color_pair(tui.C_DIM)),
    ], tui.C_CRIT)


def _missing_tools(scr, js=None):
    _message(scr, js, "CAMERA", [
        ("Required tool missing.", curses.color_pair(tui.C_CRIT) | curses.A_BOLD),
        ("Needs: chafa, rpicam-apps, ffmpeg/ffplay", curses.color_pair(tui.C_DIM)),
    ], tui.C_CRIT)


# ── Photo screen ─────────────────────────────────────────────────────────
def run_photo(scr):
    """Capture a still and show where it was saved."""
    js = open_gamepad()
    try:
        tui.init_gauge_colors()
    except Exception:
        pass
    try:
        if not camera_available():
            _no_camera(scr, js)
            return
        h, w = scr.getmaxyx()
        hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
        scr.erase()
        tui.put(scr, 1, 1, "CAMERA — Photo", w - 2, hdr)
        tui.put(scr, 3, 1, "📸 capturing full-res still…", w - 2,
                curses.color_pair(tui.C_WARN) | curses.A_BOLD)
        tui.put(scr, h - 1, 1, "please wait", w - 2, curses.color_pair(tui.C_FOOTER))
        scr.refresh()

        path, err = capture_photo(rotate="cw")
        scr.erase()
        tui.put(scr, 1, 1, "CAMERA — Photo", w - 2, hdr)
        if path:
            tui.put(scr, 3, 1, "✓ saved", w - 2,
                    curses.color_pair(tui.C_OK) | curses.A_BOLD)
            tui.put(scr, 4, 1, path, w - 2, curses.color_pair(tui.C_DIM))
        else:
            tui.put(scr, 3, 1, "✗ capture failed", w - 2,
                    curses.color_pair(tui.C_CRIT) | curses.A_BOLD)
            tui.put(scr, 4, 1, (err or "")[:w - 3], w - 2, curses.color_pair(tui.C_DIM))
        tui.put(scr, h - 1, 1, "any key Back", w - 2, curses.color_pair(tui.C_FOOTER))
        scr.refresh()
        _wait_key(scr, js)
    finally:
        if js:
            js.close()


def run_feed(scr):
    run_live_feed(scr, rotate="cw")


HANDLERS = {
    "_camera_ascii": run_ascii_preview,
    "_camera_photo": run_photo,
    "_camera_feed": run_feed,
}
