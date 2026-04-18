"""TUI module: ADS-B aircraft map"""

import curses
import json
import math
import os
import subprocess
import time

from tui.framework import (
    C_BORDER,
    C_CAT,
    C_DIM,
    C_HEADER,
    C_ITEM,
    C_SEL,
    _tui_input_loop,
    close_gamepad,
    load_config,
    open_gamepad,
    save_config,
    save_config_multi,
)
import tui_lib as tui

ADSB_JSON = "/run/dump1090-mutability/aircraft.json"
_SERVICE = "dump1090-mutability"


def _ensure_dump1090():
    """Start dump1090 service if not already running. Returns True if we started it."""
    try:
        rc = subprocess.run(
            ["systemctl", "is-active", "--quiet", _SERVICE]
        ).returncode
        if rc == 0:
            return False
        subprocess.run(
            ["sudo", "-n", "systemctl", "start", _SERVICE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)  # let dump1090 begin writing aircraft.json
        return True
    except Exception:
        return False


def _stop_dump1090():
    """Stop dump1090 service."""
    try:
        subprocess.run(
            ["sudo", "-n", "systemctl", "stop", _SERVICE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
BASEMAP_GLOBAL = os.path.join(os.path.dirname(__file__), "adsb_basemap_global.json")
BASEMAP_LEGACY = os.path.join(os.path.dirname(__file__), "adsb_basemap.json")  # backwards compat
HIRES_CACHE_DIR = os.path.expanduser("~/.config/uconsole")
ZOOM_LEVELS = [2, 5, 10, 25, 50, 100, 150, 250]  # nautical miles, half-width
DEFAULT_ZOOM_INDEX = 6  # 150 nm
HEADING_ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]

# Layer bitmask
LAYER_COAST     = 1 << 0
LAYER_COUNTRIES = 1 << 1  # only present in hires bundles
LAYER_STATES    = 1 << 2  # only present in hires bundles
LAYER_LAKES     = 1 << 3  # hires
LAYER_RIVERS    = 1 << 4  # hires
LAYER_AIRPORTS  = 1 << 5
LAYER_RINGS     = 1 << 6
LAYER_CARDINALS = 1 << 7

LAYER_ALL = (LAYER_COAST | LAYER_COUNTRIES | LAYER_STATES | LAYER_LAKES |
             LAYER_RIVERS | LAYER_AIRPORTS | LAYER_RINGS | LAYER_CARDINALS)
LAYER_MINIMAL = LAYER_COAST | LAYER_RINGS | LAYER_CARDINALS
LAYER_PLANES_ONLY = 0
DEFAULT_LAYERS = LAYER_ALL

LAYER_PRESETS = [LAYER_ALL, LAYER_MINIMAL, LAYER_PLANES_ONLY]

LAYER_NAMES = [
    ("coastlines", LAYER_COAST),
    ("countries",  LAYER_COUNTRIES),
    ("states",     LAYER_STATES),
    ("lakes",      LAYER_LAKES),
    ("rivers",     LAYER_RIVERS),
    ("airports",   LAYER_AIRPORTS),
]


_BASEMAP = {"global": None, "hires": None, "hires_key": None}


def _hires_key(home_lat, home_lon):
    return f"{int(round(home_lat))}_{int(round(home_lon))}"


def _hires_path_for(key):
    return os.path.join(HIRES_CACHE_DIR, f"adsb_basemap_hires_{key}.json")


def _load_global_basemap():
    if _BASEMAP["global"] is not None:
        return _BASEMAP["global"]
    for path in (BASEMAP_GLOBAL, BASEMAP_LEGACY):
        try:
            with open(path) as f:
                data = json.load(f)
            # Normalize legacy format → layered schema
            if "layers" not in data:
                data = {"version": 0, "layers": {
                    "coastlines": data.get("coastlines", []),
                    "airports": data.get("airports", []),
                }}
            _BASEMAP["global"] = data
            return data
        except Exception:
            continue
    _BASEMAP["global"] = {"version": 0, "layers": {}}
    return _BASEMAP["global"]


def _load_hires_basemap(home_lat, home_lon):
    key = _hires_key(home_lat, home_lon)
    if _BASEMAP["hires_key"] == key:
        return _BASEMAP["hires"]
    _BASEMAP["hires_key"] = key
    path = _hires_path_for(key)
    try:
        with open(path) as f:
            _BASEMAP["hires"] = json.load(f)
    except Exception:
        _BASEMAP["hires"] = None
    return _BASEMAP["hires"]


def _iter_layer(layer_name, home_lat, home_lon):
    """Yield items from the named layer, hires preferred over global."""
    hires = _load_hires_basemap(home_lat, home_lon)
    if hires:
        items = hires.get("layers", {}).get(layer_name)
        if items:
            yield from items
            return
    g = _load_global_basemap()
    items = g.get("layers", {}).get(layer_name) or []
    yield from items


def _viewport_bbox(home_lat, home_lon, range_nm):
    """Return (lat_min, lat_max, lon_min, lon_max) padded for viewport diagonal."""
    pad = 1.5  # diagonal + safety
    dlat = (range_nm / 60.0) * pad
    dlon = (range_nm / (60.0 * max(0.2, math.cos(math.radians(home_lat))))) * pad
    return (home_lat - dlat, home_lat + dlat, home_lon - dlon, home_lon + dlon)


def _line_in_bbox(line, bbox):
    lat_min, lat_max, lon_min, lon_max = bbox
    for lon, lat in line:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


def _ll_to_px(lat, lon, home_lat, home_lon, range_nm, pw, ph):
    cx, cy = pw / 2.0, ph / 2.0
    scale = min(cx, cy) / range_nm
    dy_nm = (lat - home_lat) * 60.0
    dx_nm = (lon - home_lon) * 60.0 * math.cos(math.radians(home_lat))
    return int(cx + dx_nm * scale), int(cy - dy_nm * scale)


def _draw_line_layer(canvas, layer_name, home_lat, home_lon, range_nm, bbox):
    """Generic line-layer drawer with bbox cull."""
    pw, ph = canvas.pw, canvas.ph
    for line in _iter_layer(layer_name, home_lat, home_lon):
        if not _line_in_bbox(line, bbox):
            continue
        prev = None
        for lon, lat in line:
            px, py = _ll_to_px(lat, lon, home_lat, home_lon, range_nm, pw, ph)
            if prev is not None:
                canvas.line(prev[0], prev[1], px, py)
            prev = (px, py)


def _draw_airports_canvas(canvas, home_lat, home_lon, range_nm):
    pw, ph = canvas.pw, canvas.ph
    for ap in _iter_layer("airports", home_lat, home_lon):
        px, py = _ll_to_px(ap["lat"], ap["lon"], home_lat, home_lon, range_nm, pw, ph)
        if not (0 <= px < pw and 0 <= py < ph):
            continue
        canvas.set(px, py)
        canvas.set(px + 1, py)
        canvas.set(px - 1, py)
        canvas.set(px, py + 1)
        canvas.set(px, py - 1)


def _draw_basemap_canvas(canvas, home_lat, home_lon, range_nm, layers):
    """Draw enabled line layers + airport dots on the braille canvas."""
    bbox = _viewport_bbox(home_lat, home_lon, range_nm)
    if layers & LAYER_COUNTRIES:
        _draw_line_layer(canvas, "countries", home_lat, home_lon, range_nm, bbox)
    if layers & LAYER_STATES:
        _draw_line_layer(canvas, "states", home_lat, home_lon, range_nm, bbox)
    if layers & LAYER_LAKES:
        _draw_line_layer(canvas, "lakes", home_lat, home_lon, range_nm, bbox)
    if layers & LAYER_RIVERS:
        _draw_line_layer(canvas, "rivers", home_lat, home_lon, range_nm, bbox)
    if layers & LAYER_COAST:
        _draw_line_layer(canvas, "coastlines", home_lat, home_lon, range_nm, bbox)
    if layers & LAYER_AIRPORTS:
        _draw_airports_canvas(canvas, home_lat, home_lon, range_nm)


def _draw_airport_labels(scr, map_y, map_x, home_lat, home_lon, range_nm, pw, ph, attr):
    """Zoom-aware label density with greedy collision avoidance."""
    occupied = set()
    show_minor = range_nm <= 50
    for ap in _iter_layer("airports", home_lat, home_lon):
        rank = ap.get("rank", 0)
        if not show_minor and rank > 2:
            continue
        px, py = _ll_to_px(ap["lat"], ap["lon"], home_lat, home_lon, range_nm, pw, ph)
        if not (0 <= px < pw and 0 <= py < ph):
            continue
        cx_ch = map_x + px // 2
        cy_ch = map_y + py // 4
        lbl = ap.get("code") or ""
        if not lbl:
            continue
        # Collision: skip if any cell of label area is already taken
        cells = [(cy_ch, cx_ch + 1 + i) for i in range(len(lbl))]
        if any(c in occupied for c in cells):
            continue
        occupied.update(cells)
        tui.put(scr, cy_ch, cx_ch + 1, lbl, len(lbl), attr)


def _heading_arrow(track):
    if track is None:
        return "•"
    return HEADING_ARROWS[int(((track + 22.5) % 360) // 45)]


def _load_aircraft():
    try:
        with open(ADSB_JSON) as f:
            data = json.load(f)
        return data.get("aircraft", []), None
    except FileNotFoundError:
        return [], "no receiver data — is dump1090 running?"
    except Exception as e:
        return [], f"read error: {e}"


def _get_home():
    cfg = load_config()
    lat = cfg.get("adsb_home_lat")
    lon = cfg.get("adsb_home_lon")
    if lat is None or lon is None:
        return None, None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _project(ac_lat, ac_lon, home_lat, home_lon, range_nm, pw, ph):
    """Equirectangular projection → braille pixel coords. Returns (px, py, dx_nm, dy_nm)."""
    dy_nm = (ac_lat - home_lat) * 60.0
    dx_nm = (ac_lon - home_lon) * 60.0 * math.cos(math.radians(home_lat))
    cx, cy = pw / 2.0, ph / 2.0
    scale = min(cx, cy) / range_nm
    px = int(cx + dx_nm * scale)
    py = int(cy - dy_nm * scale)
    return px, py, dx_nm, dy_nm


RING_FRAC_PRESETS = {
    0: [],
    1: [1.0],
    2: [0.5, 1.0],
    3: [0.33, 0.66, 1.0],
    4: [0.25, 0.5, 0.75, 1.0],
}


def _draw_range_rings(canvas, range_nm, ring_count):
    pw, ph = canvas.pw, canvas.ph
    cx, cy = pw / 2.0, ph / 2.0
    scale = min(cx, cy) / range_nm
    for frac in RING_FRAC_PRESETS.get(ring_count, RING_FRAC_PRESETS[2]):
        r = range_nm * frac
        rpx = r * scale
        steps = max(48, int(rpx))
        prev = None
        for i in range(steps + 1):
            a = 2 * math.pi * i / steps
            x = int(cx + rpx * math.cos(a))
            y = int(cy + rpx * math.sin(a))
            if prev is not None:
                canvas.line(prev[0], prev[1], x, y)
            prev = (x, y)
    cix, ciy = int(cx), int(cy)
    canvas.line(cix - 3, ciy, cix + 3, ciy)
    canvas.line(cix, ciy - 3, cix, ciy + 3)


def _draw_cardinals(scr, y0, x0, map_w, map_h, attr):
    mid_x = x0 + map_w // 2
    mid_y = y0 + map_h // 2
    tui.put(scr, y0, mid_x, "N", 1, attr)
    tui.put(scr, y0 + map_h - 1, mid_x, "S", 1, attr)
    tui.put(scr, mid_y, x0, "W", 1, attr)
    tui.put(scr, mid_y, x0 + map_w - 1, "E", 1, attr)


def _draw_speed_vector(canvas, px, py, track, speed_kt, scale):
    """Draw a velocity vector = 1 minute of travel at current ground speed."""
    if track is None or speed_kt is None or speed_kt <= 0:
        return
    nm_per_min = speed_kt / 60.0
    length_px = int(nm_per_min * scale)
    length_px = max(3, min(length_px, 40))
    a = math.radians(track - 90)
    dxp = int(length_px * math.cos(a))
    dyp = int(length_px * math.sin(a))
    canvas.line(px, py, px + dxp, py + dyp)


def _set_home_from_gps(scr):
    h, w = scr.getmaxyx()
    scr.erase()
    dim = curses.color_pair(tui.C_DIM)
    hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
    ok = curses.color_pair(tui.C_OK) | curses.A_BOLD
    crit = curses.color_pair(tui.C_CRIT)
    tui.put(scr, 2, 2, "Setting ADS-B home from GPS…", w - 4, hdr)
    tui.put(scr, 4, 2, "Waiting up to 10s for a TPV fix.", w - 4, dim)
    scr.refresh()

    lat = lon = None
    proc = None
    try:
        proc = subprocess.Popen(
            ["gpspipe", "-w", "-n", "30", "-x", "10"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        for line in proc.stdout:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("class") == "TPV" and d.get("lat") is not None:
                lat = d.get("lat")
                lon = d.get("lon")
                break
    except FileNotFoundError:
        tui.put(scr, 6, 2, "gpspipe not found — install gpsd-clients", w - 4, crit)
        tui.put(scr, h - 1, 2, "press any key", w - 4, dim)
        scr.refresh()
        scr.timeout(-1)
        scr.getch()
        return
    finally:
        if proc and proc.poll() is None:
            try:
                proc.kill()
                proc.wait()
            except Exception:
                pass

    if lat is None:
        tui.put(scr, 6, 2, "No GPS fix available.", w - 4, crit)
    else:
        save_config_multi({"adsb_home_lat": lat, "adsb_home_lon": lon})
        tui.put(scr, 6, 2, f"Home set: {lat:.5f}, {lon:.5f}", w - 4, ok)

    tui.put(scr, h - 1, 2, "press any key", w - 4, dim)
    scr.refresh()
    scr.timeout(-1)
    scr.getch()


def run_adsb_set_home(scr):
    _set_home_from_gps(scr)


def run_adsb_map(scr):
    """Real-time ADS-B aircraft map using BrailleCanvas."""
    we_started = _ensure_dump1090()
    js = open_gamepad()
    scr.timeout(1000)
    tui.init_gauge_colors()

    selected = 0
    _cfg = load_config()
    zoom_idx = int(_cfg.get("adsb_zoom_idx", DEFAULT_ZOOM_INDEX))
    zoom_idx = max(0, min(len(ZOOM_LEVELS) - 1, zoom_idx))
    ring_count = int(_cfg.get("adsb_rings", 2))
    show_overlay = bool(_cfg.get("adsb_overlay", True))
    layers = int(_cfg.get("adsb_layers", DEFAULT_LAYERS))

    # Session-local fetch state (set by adsb_hires.fetch_in_background)
    fetch_state = {"status": "idle", "msg": "", "banner_dismissed": False}

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        dim = curses.color_pair(tui.C_DIM)
        hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
        bord = curses.color_pair(tui.C_BORDER) | curses.A_DIM
        warn = curses.color_pair(tui.C_WARN) | curses.A_BOLD
        crit = curses.color_pair(tui.C_CRIT)
        sel = curses.color_pair(tui.C_SEL) | curses.A_BOLD
        item = curses.color_pair(tui.C_ITEM)
        map_attr = curses.color_pair(tui.C_HEADER)

        range_nm = ZOOM_LEVELS[zoom_idx]
        tui.put(scr, 0, 1, "ADS-B LIVE MAP", w - 2, hdr)
        rng_s = f"range {range_nm}nm"
        tui.put(scr, 0, max(1, w - len(rng_s) - 1), rng_s, len(rng_s), dim)

        home_lat, home_lon = _get_home()
        if home_lat is None:
            msg = "No home location set."
            tui.put(scr, h // 2 - 1, max(1, (w - len(msg)) // 2), msg, w - 2, warn)
            hint = "Press H to set from GPS, or HARDWARE → ADS-B Map → Set Home."
            tui.put(scr, h // 2, max(1, (w - len(hint)) // 2), hint, w - 2, dim)
            tui.put(scr, h - 1, 1, "h set home   q back", w - 2, dim)
            scr.refresh()
            key, gp = _tui_input_loop(scr, js)
            if key in (ord("q"), ord("Q")) or gp == "back":
                break
            if key in (ord("h"), ord("H")):
                _set_home_from_gps(scr)
                scr.timeout(1000)
            continue

        aircraft, err = _load_aircraft()

        # Full-screen map: occupy entire terminal minus 1-row header and 1-row footer
        map_x = 0
        map_y = 1
        map_w = w
        map_h = max(5, h - 2)

        canvas = tui.BrailleCanvas(map_w, map_h)
        active_layers = layers if show_overlay else 0
        if active_layers:
            _draw_basemap_canvas(canvas, home_lat, home_lon, range_nm, active_layers)
        if show_overlay and (active_layers & LAYER_RINGS):
            _draw_range_rings(canvas, range_nm, ring_count)

        # Speed-vector scale (pixels per nm)
        _cx_tmp, _cy_tmp = canvas.pw / 2.0, canvas.ph / 2.0
        vec_scale = min(_cx_tmp, _cy_tmp) / range_nm

        visible = []
        for ac in aircraft:
            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue
            px, py, dx, dy = _project(lat, lon, home_lat, home_lon, range_nm, canvas.pw, canvas.ph)
            dist = math.sqrt(dx * dx + dy * dy)
            if not (0 <= px < canvas.pw and 0 <= py < canvas.ph):
                continue
            track = ac.get("track")
            spd = ac.get("speed")
            _draw_speed_vector(canvas, px, py, track, spd, vec_scale)
            visible.append({
                "hex": (ac.get("hex") or "------").upper(),
                "flight": (ac.get("flight") or "").strip() or "—",
                "alt": ac.get("altitude"),
                "spd": spd,
                "trk": track,
                "sqk": ac.get("squawk"),
                "dist": dist,
                "px": px,
                "py": py,
            })

        visible.sort(key=lambda a: a["dist"])
        if selected >= len(visible):
            selected = max(0, len(visible) - 1)

        # Braille map — full screen, no border
        for i, row in enumerate(canvas.render()):
            tui.put(scr, map_y + i, map_x, row, map_w, map_attr)

        if show_overlay and (active_layers & LAYER_AIRPORTS):
            _draw_airport_labels(scr, map_y, map_x, home_lat, home_lon, range_nm,
                                 canvas.pw, canvas.ph,
                                 curses.color_pair(tui.C_WARN) | curses.A_BOLD)
        if show_overlay and (active_layers & LAYER_CARDINALS):
            _draw_cardinals(scr, map_y, map_x, map_w, map_h, dim)

        # Plane position markers — unicode arrow char at each aircraft's cell
        plane_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
        sel_plane_attr = curses.color_pair(tui.C_SEL) | curses.A_BOLD | curses.A_REVERSE
        for i, ac in enumerate(visible):
            glyph = _heading_arrow(ac["trk"])
            cx_ch = map_x + ac["px"] // 2
            cy_ch = map_y + ac["py"] // 4
            if not (map_y <= cy_ch < map_y + map_h and map_x <= cx_ch < map_x + map_w):
                continue
            attr = sel_plane_attr if i == selected else plane_attr
            tui.put(scr, cy_ch, cx_ch, glyph, 1, attr)

        # Top status line: count + range (overlays row 0)
        count_s = f"{len(visible)} AC"
        tui.put(scr, 0, 1, count_s, len(count_s) + 1, hdr)
        if err:
            tui.put(scr, 0, len(count_s) + 3, err, w - len(count_s) - 5, crit)

        # Selected-aircraft HUD overlay, top-right corner
        if visible:
            ac = visible[selected]
            trk_s = f"{int(ac['trk']):03d}°{_heading_arrow(ac['trk'])}" if ac['trk'] is not None else "---°"
            spd_s = f"{int(ac['spd'])}kt" if isinstance(ac['spd'], (int, float)) else "---kt"
            alt_s = f"{int(ac['alt'])}ft" if isinstance(ac['alt'], (int, float)) else "---ft"
            hud_lines = [
                f" {ac['flight']:<8} ",
                f" {alt_s:>7} ",
                f" {spd_s:>7} ",
                f" {trk_s:>7} ",
                f" {ac['dist']:4.0f}nm  ",
            ]
            hud_w = max(len(s) for s in hud_lines)
            hud_x = max(0, w - hud_w - 1)
            for i, line in enumerate(hud_lines):
                attr = hdr if i == 0 else item
                tui.put(scr, 1 + i, hud_x, line, hud_w, attr)
            # selection indicator
            sel_s = f"[{selected + 1}/{len(visible)}]"
            tui.put(scr, 0, max(0, w - len(sel_s) - 1), sel_s, len(sel_s), dim)

        # Network/fetch warning banner (loud, dismissable with x)
        from tui import adsb_hires as _hires_mod
        _hires_mod.poll_fetch_state(fetch_state, home_lat, home_lon, _BASEMAP)
        if fetch_state["status"] == "error" and not fetch_state["banner_dismissed"]:
            banner = f"⚠ HI-RES FETCH FAILED: {fetch_state['msg']}  (x dismiss)"
            tui.put(scr, h - 2, 1, banner[: w - 2], w - 2, crit)
        elif fetch_state["status"] == "running":
            tui.put(scr, h - 2, 1, "⟳ fetching hi-res basemap…", w - 2, dim)
        elif fetch_state["status"] == "ok" and not fetch_state["banner_dismissed"]:
            tui.put(scr, h - 2, 1, "✓ hi-res basemap ready  (x dismiss)", w - 2,
                    curses.color_pair(tui.C_OK) | curses.A_BOLD)

        foot = "↑↓ sel  +/- zoom  l layers  r rings  o overlay  f hi-res  h home  q back"
        tui.put(scr, h - 1, 1, foot, w - 2, dim)

        scr.refresh()
        key, gp = _tui_input_loop(scr, js)
        if key in (ord("q"), ord("Q")) or gp == "back":
            break
        elif key == curses.KEY_UP or gp == "up":
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN or gp == "down":
            if visible:
                selected = min(len(visible) - 1, selected + 1)
        elif key in (ord("+"), ord("=")):
            zoom_idx = max(0, zoom_idx - 1)
            save_config("adsb_zoom_idx", zoom_idx)
        elif key in (ord("-"), ord("_")):
            zoom_idx = min(len(ZOOM_LEVELS) - 1, zoom_idx + 1)
            save_config("adsb_zoom_idx", zoom_idx)
        elif key in (ord("h"), ord("H")):
            _set_home_from_gps(scr)
            scr.timeout(1000)
        elif key in (ord("r"), ord("R")):
            ring_count = (ring_count + 1) % 5  # 0..4
            save_config("adsb_rings", ring_count)
        elif key in (ord("o"), ord("O")):
            show_overlay = not show_overlay
            save_config("adsb_overlay", show_overlay)
        elif key == ord("l"):
            # cycle layer presets (full / minimal / planes-only)
            try:
                idx = LAYER_PRESETS.index(layers)
            except ValueError:
                idx = -1
            layers = LAYER_PRESETS[(idx + 1) % len(LAYER_PRESETS)]
            save_config("adsb_layers", layers)
        elif key == ord("L"):
            from tui.adsb_layer_picker import run_layer_picker
            new_layers = run_layer_picker(scr, layers)
            if new_layers is not None:
                layers = new_layers
                save_config("adsb_layers", layers)
            scr.timeout(1000)
        elif key in (ord("f"), ord("F")):
            from tui import adsb_hires as _hires
            _hires.start_fetch(home_lat, home_lon, fetch_state)
        elif key in (ord("x"), ord("X")):
            fetch_state["banner_dismissed"] = True

    if js:
        close_gamepad(js)
    if we_started:
        _stop_dump1090()
    scr.timeout(100)


def run_adsb_table(scr):
    """Sorted table view of all visible aircraft."""
    we_started = _ensure_dump1090()
    js = open_gamepad()
    scr.timeout(1000)
    top = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(tui.C_DIM)
        hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
        item = curses.color_pair(tui.C_ITEM)
        crit = curses.color_pair(tui.C_CRIT)

        tui.put(scr, 0, 1, "ADS-B AIRCRAFT TABLE", w - 2, hdr)

        home_lat, home_lon = _get_home()
        aircraft, err = _load_aircraft()

        header_line = f"{'FLIGHT':8} {'HEX':7} {'ALT':>6} {'SPD':>4} {'TRK':>4} {'DIST':>7} {'SQK':>5}"
        tui.put(scr, 2, 1, header_line, w - 2, dim)

        rows = []
        for ac in aircraft:
            lat = ac.get("lat")
            lon = ac.get("lon")
            dist = None
            if lat is not None and lon is not None and home_lat is not None:
                dy_nm = (lat - home_lat) * 60.0
                dx_nm = (lon - home_lon) * 60.0 * math.cos(math.radians(home_lat))
                dist = math.sqrt(dx_nm * dx_nm + dy_nm * dy_nm)
            rows.append((
                (ac.get("flight") or "").strip() or "—",
                (ac.get("hex") or "------").upper(),
                ac.get("altitude"),
                ac.get("speed"),
                ac.get("track"),
                dist,
                ac.get("squawk") or "—",
            ))
        rows.sort(key=lambda r: (r[5] if r[5] is not None else 9e9))

        if err:
            tui.put(scr, 3, 1, err, w - 2, crit)

        avail = max(1, h - 5)
        for i, (fl, hx, alt, spd, trk, dist, sqk) in enumerate(rows[top:top + avail]):
            yy = 3 + i
            alt_s = f"{int(alt):6d}" if isinstance(alt, (int, float)) else "     —"
            spd_s = f"{int(spd):4d}" if isinstance(spd, (int, float)) else "   —"
            trk_s = f"{int(trk):4d}" if isinstance(trk, (int, float)) else "   —"
            dist_s = f"{dist:7.1f}" if dist is not None else "      —"
            line = f"{fl[:8]:8} {hx[:7]:7} {alt_s} {spd_s} {trk_s} {dist_s} {sqk:>5}"
            tui.put(scr, yy, 1, line, w - 2, item)

        tui.put(scr, h - 1, 1, f"{len(rows)} aircraft   ↑↓ scroll   q back", w - 2, dim)
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key in (ord("q"), ord("Q")) or gp == "back":
            break
        elif key == curses.KEY_UP or gp == "up":
            top = max(0, top - 1)
        elif key == curses.KEY_DOWN or gp == "down":
            top = max(0, min(max(0, len(rows) - 1), top + 1))

    if js:
        close_gamepad(js)
    if we_started:
        _stop_dump1090()
    scr.timeout(100)
