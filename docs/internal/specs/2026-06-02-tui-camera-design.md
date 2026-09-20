# TUI Camera Feature — Design

**Date:** 2026-06-02
**Status:** Approved (subject to change) — ASCII Preview to be built first.
**Hardware:** uConsole CM5, IMX219 on HackerGadgets CSI2 adapter, mounted at **90°** (live-feed correction = `transpose=1` / 90° CW). See `~/csi-camera-notes.md`.

## Goal
Add a camera feature to the uConsole TUI (`console`) with three items, built in order:
1. **ASCII Preview** — live braille viewfinder rendered in-curses (centerpiece, first).
2. **Photo** — snap a rotated still to `~/Pictures/`.
3. **Live Preview** — fullscreen low-latency `ffplay` feed (curses suspended).

## Menu placement
Submenu under the **HARDWARE** category.
- `framework.py`: add `("Camera", "sub:camera", "ASCII preview, photo, live feed", "submenu", "📷")` to HARDWARE items.
- New `SUBMENUS["sub:camera"]`:
  - `("ASCII Preview", "_camera_ascii", "live braille viewfinder", "action", "📷")`
  - `("Live Preview",  "_camera_feed",  "fullscreen low-latency feed", "action", "🎥")`
  - `("Photo",         "_camera_photo", "snap a still to ~/Pictures",  "action", "📸")`
- Add `"tui.camera"` to `FEATURE_MODULES`.

## Module: `tui/camera.py`
Self-contained / import-isolated (a fault only hides the camera menu). Exports
`HANDLERS = {"_camera_ascii": ..., "_camera_feed": ..., "_camera_photo": ...}`.

### Camera availability
`rpicam-hello --list-cameras` parsed once (cached). If no camera, each screen shows
"No camera detected" rather than erroring. Menu always present (module imports fine).

### Component 1 — ASCII Preview (`_camera_ascii`)  *(revised 2026-06-02 — chafa-based)*
Hand-rolled braille "needed work"; replaced with **chafa 1.12.4** (installed), per research
(both subagents tested on-device). chafa renders one image then exits and curses can't parse its
ANSI, so the preview **suspends curses and runs a fullscreen chafa loop**, restoring on quit.
- **CameraProducer**: one long-lived `rpicam-vid -t 0 -n --codec mjpeg --width 640 --height 480
  --framerate F -o - | ffmpeg -loglevel quiet -f mjpeg -i - -vf <transpose>,fps=F -update 1 -y
  /dev/shm/uconsole-cam.jpg`. The **upright 90° rotation is baked into ffmpeg's transpose** (cw=
  transpose=1); fps + rotation changes `restart()` the pipeline. tmpfs frame = no flash writes
  (brownout-safe). Killed via process-group (`start_new_session=True` + `os.killpg`).
- **Render loop** (curses suspended via `def_prog_mode`/`endwin`, stdin in `tty.setcbreak`):
  each iteration runs `chafa` against the tmpfs frame, captures stdout, writes
  `\033[H` + output + `\033[J` (cursor-home overdraw — flicker-free, no `--clear`), plus a reverse-
  video status line. `select()` polls stdin: **q** quit, **m** mode (braille/color), **r** rotate,
  **+/-** fps. `finally:` restores termios, cursor, `reset_prog_mode`, refresh.
- **chafa flags** (verified present in 1.12.4): braille = `-f symbols -c none --fg-only --symbols
  braille --dither ordered --threshold 0.55 -w 4 -s WxH -C on`; color = `--symbols block+half+space
  --color-space din99d --dither ordered --dither-grain 2x2 -w 3 …`.
- Per-frame chafa ≈14ms on this Pi → fork-per-frame fine at ~10–12 fps; real cap is capture/decode.

### Component 2 — Photo (`_camera_photo`)
`rpicam-still` to a temp file → **PIL** `transpose(ROTATE_270)` (= 90° CW; `rpicam-still --rotation`
can't do 90°) → save `~/Pictures/cam_YYYYMMDD_HHMMSS.jpg` → curses confirmation with the path.
PIL 12.2.0 already installed.

### Component 3 — Live Preview (`_camera_feed`)
Suspend curses → run the validated pipeline **inline** (package-portable, not `~/cam-feed.sh`):
`rpicam-vid -t 0 --codec yuv420 --width 1280 --height 960 --framerate 30 -n -o - | ffplay
-f rawvideo -pixel_format yuv420p -video_size 1280x960 -framerate 30 -fflags nobuffer
-flags low_delay -framedrop -avioflags direct -vf transpose=1 -i -` → restore curses on exit.
Needs the user's Wayland env (runs under labwc).

## Reuse / deps
Reuses `BrailleCanvas`, `framework._tui_input_loop` / `open_gamepad` / `put` / color pairs.
**No new dependencies** (rpicam, ffplay, PIL present; numpy intentionally avoided — not installed,
conversion stays pure-Python at modest grid + low fps).

## Testing
`python3 -m py_compile`; unit test `frame_to_braille` (gradient → expected dot density);
then launch `console` → HARDWARE → Camera and visually confirm (GPU preview can't be hosted from
the agent shell — user verifies on-device).

## Out of scope (later)
Record video, timelapse, MJPEG/RTSP network stream, motion→cloud alert, QR scan, object detection,
configurable rotation for other mounts.
