"""TUI module: radio"""

import curses
import json
import math
import os
import struct
import subprocess
import time
import threading

from tui.framework import (
    C_BORDER,
    C_CAT,
    C_DIM,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    _gp_set_cooldown,
    _tui_input_loop,
    close_gamepad,
    entry,
    open_gamepad,
    read_gamepad,
    run_confirm,
)
import tui_lib as tui


def run_gps_globe(scr):
    """Wireframe globe showing GPS satellites in 3D space."""

    js = open_gamepad()
    scr.timeout(200)
    tui.init_gauge_colors()

    rot_angle = 0.0   # globe rotation (auto-spin)
    tilt = 0.35        # viewing tilt (radians)

    # Background GPS polling — never blocks the render loop
    _sky_cache = {"sky": {}, "tpv": {}, "error": None}
    _gps_proc = [None]  # mutable ref for nested scope

    def _poll_gps():
        """Start or check a non-blocking gpspipe process."""
        proc = _gps_proc[0]
        if proc is None or proc.poll() is not None:
            # Parse output from finished process
            if proc is not None:
                sky = {}
                tpv = {}
                try:
                    out = proc.stdout.read()
                    for line in out.splitlines():
                        try:
                            d = json.loads(line)
                        except Exception:
                            continue
                        if d.get("class") == "SKY":
                            sky = d
                        elif d.get("class") == "TPV":
                            tpv = d
                    _sky_cache["sky"] = sky
                    _sky_cache["tpv"] = tpv
                    _sky_cache["error"] = None
                except Exception:
                    pass
            # Launch new gpspipe (short window, non-blocking)
            try:
                _gps_proc[0] = subprocess.Popen(
                    ["gpspipe", "-w", "-n", "10", "-x", "3"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                _sky_cache["error"] = None
            except FileNotFoundError:
                _sky_cache["error"] = "gpspipe not found — install gpsd-clients"
                _gps_proc[0] = None
            except Exception:
                _sky_cache["error"] = "Cannot connect to gpsd"
                _gps_proc[0] = None

    def get_sky():
        """Return cached satellite data (never blocks)."""
        _poll_gps()
        return _sky_cache["sky"], _sky_cache["tpv"], _sky_cache.get("error")

    def project_sphere(az_deg, el_deg, cx, cy, radius, rot, tilt_r):
        """Project azimuth/elevation to 2D screen coords on a wireframe globe.
        az: 0-360 (North=0, clockwise), el: 0-90 (horizon=0, zenith=90)
        Returns (px, py) in braille pixel coords or None if on back face."""
        az = math.radians(az_deg - 90)  # rotate so North is up
        el = math.radians(el_deg)

        # Satellite position on unit sphere (az=longitude, el=latitude from equator)
        x = math.cos(el) * math.cos(az + rot)
        y = math.cos(el) * math.sin(az + rot)
        z = math.sin(el)

        # Apply tilt (rotate around X axis)
        y2 = y * math.cos(tilt_r) - z * math.sin(tilt_r)
        z2 = y * math.sin(tilt_r) + z * math.cos(tilt_r)

        if y2 < -0.05:  # behind the globe
            return None

        # Orthographic projection
        px = int(cx + x * radius)
        py = int(cy - z2 * radius)
        return (px, py)

    def draw_globe(canvas, cx, cy, radius, rot, tilt_r):
        """Draw wireframe globe with latitude/longitude lines."""
        # Equator and latitude circles
        for lat_deg in range(-60, 90, 30):
            lat = math.radians(lat_deg)
            prev = None
            for i in range(73):
                lon = math.radians(i * 5)
                x = math.cos(lat) * math.cos(lon + rot)
                y = math.cos(lat) * math.sin(lon + rot)
                z = math.sin(lat)
                y2 = y * math.cos(tilt_r) - z * math.sin(tilt_r)
                z2 = y * math.sin(tilt_r) + z * math.cos(tilt_r)
                if y2 >= -0.05:
                    px = int(cx + x * radius)
                    py = int(cy - z2 * radius)
                    if prev:
                        canvas.line(prev[0], prev[1], px, py)
                    prev = (px, py)
                else:
                    prev = None

        # Longitude meridians
        for lon_deg in range(0, 360, 30):
            lon = math.radians(lon_deg)
            prev = None
            for i in range(37):
                lat = math.radians(-90 + i * 5)
                x = math.cos(lat) * math.cos(lon + rot)
                y = math.cos(lat) * math.sin(lon + rot)
                z = math.sin(lat)
                y2 = y * math.cos(tilt_r) - z * math.sin(tilt_r)
                z2 = y * math.sin(tilt_r) + z * math.cos(tilt_r)
                if y2 >= -0.05:
                    px = int(cx + x * radius)
                    py = int(cy - z2 * radius)
                    if prev:
                        canvas.line(prev[0], prev[1], px, py)
                    prev = (px, py)
                else:
                    prev = None

    def draw_satellite(canvas, px, py, used):
        """Draw a satellite marker — larger cross for used, dot for unused."""
        canvas.set(px, py)
        if used:
            for d in range(1, 3):
                canvas.set(px + d, py)
                canvas.set(px - d, py)
                canvas.set(px, py + d)
                canvas.set(px, py - d)
        else:
            canvas.set(px + 1, py)
            canvas.set(px - 1, py)

    tick = 0
    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # ── Fetch satellite data ──
        sky, tpv, gps_err = get_sky()
        sats = sky.get("satellites", [])
        used_sats = [s for s in sats if s.get("used")]
        unused_sats = [s for s in sats if not s.get("used")]
        fix_mode = tpv.get("mode", 0)
        lat = tpv.get("lat")
        lon = tpv.get("lon")

        # ── Header ──
        grp = curses.color_pair(tui.C_BORDER) | curses.A_DIM
        hdr_attr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
        ok_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
        warn_attr = curses.color_pair(tui.C_WARN) | curses.A_BOLD
        crit_attr = curses.color_pair(tui.C_CRIT)
        dim_attr = curses.color_pair(tui.C_DIM)

        tui.put(scr, 0, 1, "GPS SATELLITE VIEW", w - 2, hdr_attr)

        if gps_err:
            tui.put(scr, 1, 1, gps_err, w - 2, crit_attr)
        elif not sats:
            searching = "Searching" + "." * (tick % 4)
            tui.put(scr, 1, 1, f"No Signal — {searching}", w - 2, warn_attr)
        else:
            fix_str = {0: "No Fix", 1: "No Fix", 2: "2D Fix", 3: "3D Fix"}.get(fix_mode, "?")
            fix_attr = ok_attr if fix_mode >= 3 else warn_attr if fix_mode == 2 else crit_attr
            status_line = f"{fix_str}  {len(used_sats)}/{len(sats)} sats"
            if lat is not None and lon is not None:
                status_line += f"  {lat:.4f},{lon:.4f}"
            tui.put(scr, 1, 1, status_line, w - 2, fix_attr)

        # ── Globe dimensions ──
        globe_ch = max(8, (h - 6))          # char rows for globe
        globe_cw = max(20, min(w - 2, globe_ch * 4))  # char cols (wider for aspect ratio)
        sat_radius = 1.15  # satellites orbit slightly outside the globe

        canvas = tui.BrailleCanvas(globe_cw, globe_ch)
        cx = canvas.pw // 2
        cy = canvas.ph // 2
        radius = min(cx - 4, cy - 2)

        # Draw the wireframe globe
        draw_globe(canvas, cx, cy, radius, rot_angle, tilt)

        # ── Plot satellites ──
        sat_labels = []  # (screen_y, screen_x, label, color) for overlay after braille render
        orbit_r = radius * sat_radius

        for sat in sats:
            az = sat.get("az", 0)
            el = sat.get("el", 0)
            used = sat.get("used", False)
            prn = sat.get("PRN", sat.get("prn", "?"))
            ss = sat.get("ss", 0)

            pos = project_sphere(az, el, cx, cy, orbit_r, rot_angle, tilt)
            if pos is None:
                continue

            px, py = pos
            draw_satellite(canvas, px, py, used)

            # Compute char position for PRN label
            char_x = px // 2
            char_y = py // 4
            if 0 <= char_x < globe_cw and 0 <= char_y < globe_ch:
                col = tui.C_OK if ss >= 30 else tui.C_WARN if ss >= 15 else tui.C_CRIT
                sat_labels.append((char_y, char_x, str(prn), col, used))

        # ── Render globe ──
        rows = canvas.render()
        globe_x = max(1, (w - globe_cw) // 2)
        start_y = 3

        for i, row_str in enumerate(rows):
            if start_y + i >= h - 3:
                break
            tui.put(scr, start_y + i, globe_x, row_str, globe_cw, grp)

        # ── Overlay satellite PRN labels ──
        for char_y, char_x, prn_str, col, used in sat_labels:
            sy = start_y + char_y
            sx = globe_x + char_x + 1
            if 0 < sy < h - 3 and 0 < sx < w - len(prn_str) - 1:
                attr = curses.color_pair(col)
                if used:
                    attr |= curses.A_BOLD
                tui.put(scr, sy, sx, prn_str, len(prn_str) + 1, attr)

        # ── Legend ──
        leg_y = h - 3
        if leg_y > start_y + 2:
            tui.put(scr, leg_y, 1, "╶", 1, grp)
            tui.put(scr, leg_y, 2, "┼", 1, curses.color_pair(tui.C_OK) | curses.A_BOLD)
            tui.put(scr, leg_y, 3, " used  ", 7, dim_attr)
            tui.put(scr, leg_y, 10, "·", 1, curses.color_pair(tui.C_WARN))
            tui.put(scr, leg_y, 11, " unused  ", 9, dim_attr)
            tui.put(scr, leg_y, 20, "SNR:", 4, dim_attr)
            tui.put(scr, leg_y, 25, "▓30+", 4, curses.color_pair(tui.C_OK))
            tui.put(scr, leg_y, 30, " ▒15+", 5, curses.color_pair(tui.C_WARN))
            tui.put(scr, leg_y, 36, " ░<15", 5, curses.color_pair(tui.C_CRIT))

        # ── Footer ──
        foot = "q Back"
        tui.put(scr, h - 1, 1, foot, w - 2, dim_attr)

        scr.refresh()
        rot_angle += 0.04  # slow auto-rotation
        tick += 1

        key, gp = _tui_input_loop(scr, js)
        if key == ord("q") or key == ord("Q") or gp == "back":
            break

    # Clean up background gpspipe
    if _gps_proc[0] and _gps_proc[0].poll() is None:
        _gps_proc[0].kill()
        _gps_proc[0].wait()
    if js:
        js.close()
    scr.timeout(100)


# ── FM Radio TUI ─────────────────────────────────────────────────────

BIG_DIGITS = {
    "0": ["█▀▀█", "█  █", "█  █", "█  █", "█▄▄█"],
    "1": [" ▀█ ", "  █ ", "  █ ", "  █ ", " ▄█▄"],
    "2": ["█▀▀█", "   █", "█▀▀ ", "█   ", "█▄▄█"],
    "3": ["█▀▀█", "   █", " ▀▀█", "   █", "█▄▄█"],
    "4": ["█  █", "█  █", "█▄▄█", "   █", "   █"],
    "5": ["█▀▀█", "█   ", "█▀▀█", "   █", "█▄▄█"],
    "6": ["█▀▀█", "█   ", "█▀▀█", "█  █", "█▄▄█"],
    "7": ["█▀▀█", "   █", "  █ ", " █  ", " █  "],
    "8": ["█▀▀█", "█  █", "█▀▀█", "█  █", "█▄▄█"],
    "9": ["█▀▀█", "█  █", "█▀▀█", "   █", "█▄▄█"],
    ".": ["    ", "    ", "    ", "    ", " ▄  "],
    " ": ["    ", "    ", "    ", "    ", "    "],
}

FM_PRESET_FILE = os.path.expanduser("~/.config/uconsole/fm-presets.conf")

def _fm_load_presets():
    """Load FM presets from config file."""
    presets = []
    if os.path.exists(FM_PRESET_FILE):
        try:
            with open(FM_PRESET_FILE) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        freq_s, name = line.split("=", 1)
                        try:
                            presets.append((float(freq_s), name.strip()))
                        except ValueError:
                            pass
        except OSError:
            pass
    return presets

def _fm_save_presets(presets):
    """Save FM presets to config file."""
    os.makedirs(os.path.dirname(FM_PRESET_FILE), exist_ok=True)
    with open(FM_PRESET_FILE, "w") as f:
        f.write("# FM Radio Presets\n")
        for freq, name in sorted(presets):
            f.write(f"{freq}={name}\n")

def _fm_stop(rtl_proc, aplay_proc):
    """Kill rtl_fm + aplay pipeline safely."""
    for proc in [rtl_proc, aplay_proc]:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

def _fm_reader(rtl_proc, aplay_proc, audio_h, wave_samples, lock, stop_event):
    """Daemon thread: tee PCM from rtl_fm to aplay + compute audio metrics."""
    CHUNK = 2048  # bytes = 1024 16-bit samples
    while not stop_event.is_set():
        try:
            data = rtl_proc.stdout.read(CHUNK)
        except Exception:
            break
        if not data:
            break
        # Forward to aplay
        try:
            aplay_proc.stdin.write(data)
            aplay_proc.stdin.flush()
        except (BrokenPipeError, OSError):
            break
        # Compute RMS and capture waveform samples
        try:
            samples = struct.unpack(f"<{len(data) // 2}h", data)
            rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0
            with lock:
                tui.push(audio_h, rms, 120)
                wave_samples.clear()
                wave_samples.extend(samples[-160:])
        except Exception:
            pass

def _fm_start(freq, squelch, gain):
    """Start rtl_fm + aplay pipeline. Returns (rtl_proc, aplay_proc, thread, stop_event)."""
    gain_args = ["-g", str(gain)] if gain != "auto" else []
    rtl_cmd = [
        "rtl_fm", "-M", "wbfm", "-f", f"{freq}M",
        "-r", "48000", "-E", "deemp",
        "-l", str(squelch),
    ] + gain_args + ["-"]
    rtl_proc = subprocess.Popen(
        rtl_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    aplay_proc = subprocess.Popen(
        ["aplay", "-r", "48000", "-f", "S16_LE", "-t", "raw", "-c", "1", "-q"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    audio_h = tui.make_history()
    wave_samples = []
    lock = threading.Lock()
    stop_event = threading.Event()
    reader_t = threading.Thread(
        target=_fm_reader,
        args=(rtl_proc, aplay_proc, audio_h, wave_samples, lock, stop_event),
        daemon=True,
    )
    reader_t.start()
    return rtl_proc, aplay_proc, reader_t, stop_event, audio_h, wave_samples, lock

def run_fm_radio(scr):
    """FM Radio receiver with waveform display and tuning controls."""
    js = open_gamepad()
    scr.timeout(100)
    tui.init_gauge_colors()

    # ── State ──
    freq = 101.1
    playing = False
    gain = "auto"
    squelch = 0
    volume = 80
    scanning = False
    scan_dir = 1
    scan_timer = 0
    preset_overlay = False
    freq_input = ""
    presets = _fm_load_presets()

    # Pipeline state
    rtl_proc = aplay_proc = reader_t = stop_event = None
    audio_h = tui.make_history()
    wave_samples = []
    lock = threading.Lock()

    def start_radio():
        nonlocal rtl_proc, aplay_proc, reader_t, stop_event, audio_h, wave_samples, lock, playing
        if rtl_proc:
            stop_event.set()
            _fm_stop(rtl_proc, aplay_proc)
        rtl_proc, aplay_proc, reader_t, stop_event, audio_h, wave_samples, lock = \
            _fm_start(freq, squelch, gain)
        playing = True

    def stop_radio():
        nonlocal rtl_proc, aplay_proc, playing
        if stop_event:
            stop_event.set()
        _fm_stop(rtl_proc, aplay_proc)
        rtl_proc = aplay_proc = None
        playing = False

    tick = 0
    try:
        while True:
            h, w = scr.getmaxyx()
            scr.erase()

            # ── Read audio data ──
            cur_rms = 0.0
            cur_wave = []
            with lock:
                if audio_h:
                    cur_rms = audio_h[-1]
                cur_wave = list(wave_samples)
            cur_audio_h = list(audio_h)

            # ── Colors ──
            hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
            val = curses.color_pair(tui.C_HEADER) | curses.A_BOLD
            grp = curses.color_pair(tui.C_BORDER) | curses.A_DIM
            dim = curses.color_pair(tui.C_DIM)
            ok = curses.color_pair(tui.C_OK) | curses.A_BOLD
            warn = curses.color_pair(tui.C_WARN) | curses.A_BOLD
            crit = curses.color_pair(tui.C_CRIT)

            pw = w - 2  # panel width
            gw = pw - 4  # graph width
            y = 0

            # ── Header ──
            status_str = "PLAYING" if playing else "SCANNING" if scanning else "STOPPED"
            status_col = ok if playing else warn if scanning else dim
            freq_str = freq_input if freq_input else f"{freq:.1f}"
            header = f"FM RADIO"
            tui.put(scr, y, 1, header, w - 2, hdr)
            mhz_str = f"{freq_str} MHz"
            tui.put(scr, y, w - len(mhz_str) - len(status_str) - 5, mhz_str, len(mhz_str), val)
            tui.put(scr, y, w - len(status_str) - 2, status_str, len(status_str), status_col)
            y += 1

            # ── Big Frequency Display ──
            if h > 16:
                tui.panel_top(scr, y, 0, pw + 2, "FREQUENCY", f"{freq_str} MHz")
                y += 1
                digit_str = f"{freq:.1f}"
                # Render big digits centered
                total_w = len(digit_str) * 5
                dx = max(2, (pw - total_w) // 2)
                for row_i in range(5):
                    tui.panel_side(scr, y, 0, pw + 2)
                    line = ""
                    for ch_c in digit_str:
                        glyph = BIG_DIGITS.get(ch_c, BIG_DIGITS[" "])
                        line += glyph[row_i] + " "
                    tui.put(scr, y, dx, line, pw - 2, val)
                    y += 1
                tui.panel_bot(scr, y, 0, pw + 2)
                y += 1
            else:
                # Compact: just show freq in header
                pass

            # ── Tuning Dial ──
            if y < h - 10:
                tui.panel_top(scr, y, 0, pw + 2, "TUNING")
                y += 1
                tui.panel_side(scr, y, 0, pw + 2)
                dial_w = gw - 8
                if dial_w > 10:
                    tuning_pct = (freq - 87.5) / (108.0 - 87.5) * 100
                    pos = int(dial_w * tuning_pct / 100)
                    bar = "░" * pos + "█" + "░" * (dial_w - pos - 1)
                    tui.put(scr, y, 2, " 88 ", 4, dim)
                    tui.put(scr, y, 6, bar, dial_w, ok)
                    tui.put(scr, y, 6 + dial_w, " 108", 4, dim)
                y += 1
                tui.panel_bot(scr, y, 0, pw + 2)
                y += 1

            # ── Audio Waveform ──
            wave_rows = max(3, min(6, (h - y - 6)))
            if y < h - 6:
                rms_str = f"RMS: {int(cur_rms)}" if playing else ""
                tui.panel_top(scr, y, 0, pw + 2, "AUDIO", rms_str)
                y += 1
                if cur_wave and playing:
                    rows = tui.make_waveform(cur_wave, gw, wave_rows)
                elif cur_audio_h and playing:
                    rows = tui.make_area(cur_audio_h, gw, wave_rows, max_val=8000)
                else:
                    # Flat line when stopped
                    c = tui.BrailleCanvas(gw, wave_rows)
                    mid = c.ph // 2
                    for px in range(c.pw):
                        c.set(px, mid)
                    rows = c.render()
                for row_str in rows:
                    tui.panel_side(scr, y, 0, pw + 2)
                    tui.put(scr, y, 2, row_str, gw, ok if playing else dim)
                    y += 1
                tui.panel_bot(scr, y, 0, pw + 2)
                y += 1

            # ── Signal Meter ──
            if y < h - 3:
                sig_pct = min(100, int(cur_rms / 80)) if playing else 0
                sig_label = "STRONG" if sig_pct > 70 else "FAIR" if sig_pct > 30 else "WEAK" if sig_pct > 5 else "---"
                tui.panel_top(scr, y, 0, pw + 2, "SIGNAL", sig_label)
                y += 1
                tui.panel_side(scr, y, 0, pw + 2)
                bar, col = tui.gauge_bar(sig_pct, gw, (30, 70))
                tui.put(scr, y, 2, bar, gw, curses.color_pair(col))
                y += 1
                tui.panel_bot(scr, y, 0, pw + 2)
                y += 1

            # ── Status Line ──
            if y < h - 1:
                gain_str = f"GAIN {gain}"
                squelch_str = f"SQ {squelch}"
                vol_str = f"VOL {volume}%"
                mode_str = "WBFM"
                status = f" {gain_str}  {squelch_str}  {vol_str}  {mode_str}  48kHz "
                tui.put(scr, h - 2, 1, status, w - 2, dim)

            # ── Footer / Keybinds ──
            if freq_input:
                foot = f" Type freq: {freq_input}_ (Enter confirm, Esc cancel) "
            elif scanning:
                foot = " SCANNING... (any key to stop) "
            else:
                foot = " SPC play  ←→ tune  ↑↓ coarse  s scan  p presets  g gain  +/- vol  q quit "
            tui.put(scr, h - 1, 1, foot, w - 2, curses.color_pair(tui.C_FOOTER) if not scanning else warn)

            # ── Preset Overlay ──
            if preset_overlay and presets:
                ow = min(40, w - 4)
                oh = min(len(presets) + 4, h - 4)
                oy = max(0, (h - oh) // 2)
                ox = max(0, (w - ow) // 2)
                try:
                    win = curses.newwin(oh, ow, oy, ox)
                    win.border()
                    win.addnstr(1, (ow - 10) // 2, "FM PRESETS", 10, hdr)
                    for i, (pf, pn) in enumerate(presets[:9]):
                        label = f" {i + 1}. {pf:5.1f}  {pn}"
                        attr = val if abs(pf - freq) < 0.05 else dim
                        win.addnstr(2 + i, 2, label[:ow - 4], ow - 4, attr)
                    hint = "1-9 select  a add  Esc close"
                    win.addnstr(oh - 2, max(1, (ow - len(hint)) // 2), hint, ow - 2, dim)
                    win.refresh()
                except curses.error:
                    pass

            scr.refresh()
            tick += 1

            # ── Scan Logic ──
            if scanning and playing:
                scan_timer -= 1
                if scan_timer <= 0:
                    freq = round(freq + scan_dir * 0.2, 1)
                    if freq > 108.0:
                        freq = 87.5
                    if freq < 87.5:
                        freq = 108.0
                    start_radio()
                    scan_timer = 8  # ~0.8s per channel

            # ── Input ──
            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None:
                continue

            # Any key cancels scan
            if scanning and key != -1:
                scanning = False
                continue

            # Preset overlay input
            if preset_overlay:
                if key == 27:  # Esc
                    preset_overlay = False
                elif ord("1") <= key <= ord("9"):
                    idx = key - ord("1")
                    if idx < len(presets):
                        freq = presets[idx][0]
                        preset_overlay = False
                        if playing:
                            start_radio()
                elif key == ord("a"):
                    # Add current freq as preset
                    name = f"FM {freq:.1f}"
                    presets.append((freq, name))
                    _fm_save_presets(presets)
                elif key == ord("p") or gp == "back":
                    preset_overlay = False
                continue

            # Direct frequency entry mode
            if freq_input:
                if key == 27:  # Esc
                    freq_input = ""
                elif key in (curses.KEY_ENTER, 10, 13):
                    try:
                        nf = float(freq_input)
                        if 87.5 <= nf <= 108.0:
                            freq = round(nf, 1)
                            if playing:
                                start_radio()
                    except ValueError:
                        pass
                    freq_input = ""
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    freq_input = freq_input[:-1]
                elif (ord("0") <= key <= ord("9")) or key == ord("."):
                    if len(freq_input) < 7:
                        freq_input += chr(key)
                continue

            # Start digit entry
            if ord("0") <= key <= ord("9"):
                freq_input = chr(key)
                continue

            # Quit
            if key == ord("q") or key == ord("Q") or gp == "back":
                break

            # Play/Stop
            if key == ord(" ") or gp == "enter":
                if playing:
                    stop_radio()
                else:
                    start_radio()

            # Fine tune ±0.1
            elif key == curses.KEY_RIGHT or key == ord("l"):
                freq = min(108.0, round(freq + 0.1, 1))
                if playing:
                    start_radio()
            elif key == curses.KEY_LEFT or key == ord("h"):
                freq = max(87.5, round(freq - 0.1, 1))
                if playing:
                    start_radio()

            # Coarse tune ±1.0
            elif key == curses.KEY_UP or key == ord("k"):
                freq = min(108.0, round(freq + 1.0, 1))
                if playing:
                    start_radio()
            elif key == curses.KEY_DOWN or key == ord("j"):
                freq = max(87.5, round(freq - 1.0, 1))
                if playing:
                    start_radio()

            # Scan
            elif key == ord("s"):
                scanning = True
                scan_dir = 1
                scan_timer = 0
                if not playing:
                    start_radio()
            elif key == ord("S"):
                scanning = True
                scan_dir = -1
                scan_timer = 0
                if not playing:
                    start_radio()

            # Gain cycle
            elif key == ord("g"):
                gains = ["auto", 0, 10, 20, 30, 40, 50]
                idx = gains.index(gain) if gain in gains else 0
                gain = gains[(idx + 1) % len(gains)]
                if playing:
                    start_radio()

            # Volume
            elif key == ord("+") or key == ord("="):
                volume = min(150, volume + 5)
                subprocess.Popen(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            elif key == ord("-"):
                volume = max(0, volume - 5)
                subprocess.Popen(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

            # Presets
            elif key == ord("p"):
                preset_overlay = not preset_overlay

    finally:
        if rtl_proc or aplay_proc:
            if stop_event:
                stop_event.set()
            _fm_stop(rtl_proc, aplay_proc)
        if js:
            js.close()
        scr.timeout(100)
