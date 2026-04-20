"""TUI module: Meshtastic mesh nodes map

Reuses the ADS-B basemap renderer and projection to plot nodes that
advertise a position. Data pulled from `meshtastic --host localhost --info`.
"""

import curses
import json
import math
import os
import re
import subprocess
import time

from tui.framework import (
    _tui_input_loop,
    close_gamepad,
    load_config,
    open_gamepad,
    save_config_multi,
)
from tui.adsb import (
    DEFAULT_LAYERS,
    ZOOM_LEVELS,
    _draw_basemap_canvas,
    _draw_cardinals,
    _draw_range_rings,
    _get_home,
    _project,
    _set_home_from_gps,
)
import tui_lib as tui

DEFAULT_ZOOM_INDEX = 7  # 250 nm — mesh spread is wider than aircraft
MESHTASTIC_HOST = os.environ.get("MESHTASTIC_HOST", "localhost")
CACHE_TTL_SEC = 30  # re-query nodes every 30s


def _fetch_nodes():
    """Run `meshtastic --info`, parse the 'Nodes in mesh' JSON block."""
    try:
        out = subprocess.run(
            ["meshtastic", "--host", MESHTASTIC_HOST, "--info"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "PATH": os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")},
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return [], "meshtastic CLI not available"
    m = re.search(r"Nodes in mesh:\s*(\{.*?\n\})", out, re.DOTALL)
    if not m:
        return [], "no NodeDB (daemon running?)"
    try:
        raw = json.loads(m.group(1))
    except json.JSONDecodeError:
        return [], "failed to parse NodeDB JSON"
    nodes = []
    for node in raw.values():
        u = node.get("user", {}) or {}
        p = node.get("position", {}) or {}
        if "latitude" not in p or "longitude" not in p:
            continue
        nodes.append({
            "id": u.get("id", "?"),
            "short": u.get("shortName", "?")[:4],
            "long": u.get("longName", ""),
            "hw": u.get("hwModel", ""),
            "lat": float(p["latitude"]),
            "lon": float(p["longitude"]),
            "alt": p.get("altitude", 0),
            "last_heard": node.get("lastHeard", 0),
            "battery": (node.get("deviceMetrics", {}) or {}).get("batteryLevel"),
            "hops": node.get("hopsAway"),
        })
    return nodes, None


def _distance_nm(lat1, lon1, lat2, lon2):
    """Great-circle distance in nautical miles."""
    R = 3440.065  # Earth radius in nm
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _age_label(last_heard):
    if not last_heard:
        return "?"
    age = int(time.time() - last_heard)
    if age < 60:
        return f"{age}s"
    if age < 3600:
        return f"{age // 60}m"
    if age < 86400:
        return f"{age // 3600}h"
    return f"{age // 86400}d"


def run_meshtastic_map(scr):
    """Live Meshtastic mesh map."""
    js = open_gamepad()
    scr.timeout(1000)
    tui.init_gauge_colors()

    _cfg = load_config()
    zoom_idx = int(_cfg.get("mesh_zoom_idx", DEFAULT_ZOOM_INDEX))
    zoom_idx = max(0, min(len(ZOOM_LEVELS) - 1, zoom_idx))
    show_labels = bool(_cfg.get("mesh_labels", True))
    show_overlay = bool(_cfg.get("mesh_overlay", True))

    nodes, err = [], None
    last_fetch = 0.0
    selected = 0

    while True:
        # Refresh node list periodically
        now = time.time()
        if now - last_fetch > CACHE_TTL_SEC:
            nodes, err = _fetch_nodes()
            last_fetch = now
            if nodes:
                selected = min(selected, len(nodes) - 1)

        h, w = scr.getmaxyx()
        scr.erase()

        dim = curses.color_pair(tui.C_DIM)
        hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
        warn = curses.color_pair(tui.C_WARN) | curses.A_BOLD
        sel_c = curses.color_pair(tui.C_SEL) | curses.A_BOLD
        map_attr = curses.color_pair(tui.C_HEADER)
        node_attr = curses.color_pair(tui.C_CAT) | curses.A_BOLD

        range_nm = ZOOM_LEVELS[zoom_idx]
        title = f"MESHTASTIC MAP  ({len(nodes)} nodes w/ pos)"
        tui.put(scr, 0, 1, title, w - 2, hdr)
        rng_s = f"range {range_nm}nm"
        tui.put(scr, 0, max(1, w - len(rng_s) - 1), rng_s, len(rng_s), dim)

        home_lat, home_lon = _get_home()
        if home_lat is None:
            msg = "No home location set."
            tui.put(scr, h // 2 - 1, max(1, (w - len(msg)) // 2), msg, w - 2, warn)
            hint = "Press H to set from GPS, or use HARDWARE → ADS-B → Set Home."
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

        map_x = 0
        map_y = 1
        map_w = w
        map_h = max(5, h - 3)

        canvas = tui.BrailleCanvas(map_w, map_h)
        active_layers = DEFAULT_LAYERS if show_overlay else 0
        if active_layers:
            _draw_basemap_canvas(canvas, home_lat, home_lon, range_nm, active_layers)
            _draw_range_rings(canvas, range_nm, 2)

        # Project & plot each node
        visible = []
        for n in nodes:
            px, py, dx, dy = _project(n["lat"], n["lon"], home_lat, home_lon, range_nm, canvas.pw, canvas.ph)
            if not (0 <= px < canvas.pw and 0 <= py < canvas.ph):
                continue
            # 3x3 filled square so nodes stand out
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    canvas.pixel(px + ox, py + oy)
            dist = _distance_nm(home_lat, home_lon, n["lat"], n["lon"])
            visible.append((dist, px, py, n))
        visible.sort(key=lambda t: t[0])

        canvas.blit(scr, map_y, map_x, map_attr)
        _draw_cardinals(scr, map_y, map_x, map_w, map_h, dim)

        # Node labels (short names next to dots)
        if show_labels:
            drawn = set()
            for dist, px, py, n in visible[:30]:
                cy = map_y + py // 4
                cx = map_x + px // 2 + 1
                key = (cy, cx)
                if key in drawn:
                    continue
                drawn.add(key)
                label = n["short"] or n["id"][-4:]
                if 0 <= cy < h - 1 and 0 <= cx < w - len(label) - 1:
                    tui.put(scr, cy, cx, label, min(len(label), w - cx - 1), node_attr)

        # Bottom status line + selected node details
        if visible:
            selected = selected % len(visible)
            dist, _, _, sel = visible[selected]
            line = f"{sel['short']:5s} {sel['long'][:24]:24s}  {sel['lat']:+.3f},{sel['lon']:+.3f}  {dist:.1f}nm  age={_age_label(sel['last_heard'])}"
            tui.put(scr, h - 2, 1, line, w - 2, sel_c)
        elif err:
            tui.put(scr, h - 2, 1, f"error: {err}", w - 2, warn)
        else:
            tui.put(scr, h - 2, 1, "no nodes with position yet — waiting for NodeInfo packets…", w - 2, dim)

        hints = "+/- zoom   j/k select   l labels   b basemap   h set home   r refresh   q quit"
        tui.put(scr, h - 1, 1, hints, w - 2, dim)
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key in (ord("q"), ord("Q")) or gp == "back":
            break
        elif key in (ord("+"), ord("="), curses.KEY_UP) or gp == "up":
            zoom_idx = max(0, zoom_idx - 1)
        elif key in (ord("-"), ord("_"), curses.KEY_DOWN) or gp == "down":
            zoom_idx = min(len(ZOOM_LEVELS) - 1, zoom_idx + 1)
        elif key in (ord("j"), curses.KEY_RIGHT) or gp == "right":
            if visible:
                selected = (selected + 1) % len(visible)
        elif key in (ord("k"), curses.KEY_LEFT) or gp == "left":
            if visible:
                selected = (selected - 1) % len(visible)
        elif key in (ord("l"), ord("L")):
            show_labels = not show_labels
        elif key in (ord("b"), ord("B")):
            show_overlay = not show_overlay
        elif key in (ord("h"), ord("H")):
            _set_home_from_gps(scr)
            scr.timeout(1000)
        elif key in (ord("r"), ord("R")):
            last_fetch = 0.0  # force refresh on next loop

    save_config_multi({
        "mesh_zoom_idx": zoom_idx,
        "mesh_labels": show_labels,
        "mesh_overlay": show_overlay,
    })
    close_gamepad(js)
