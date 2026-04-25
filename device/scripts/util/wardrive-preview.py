#!/usr/bin/env python3
"""Preview the TUI War Drive map.

Two modes:

    **Synthetic** (default) — simulates a random-walk GPS fix with
    injected AP sightings. Good for aesthetic iteration.

    **Replay** (`--csv PATH`) — loads a real wardrive-*.csv from a
    past outdoor session and renders it on the map. Either shows
    everything at once (static) or plays through chronologically
    at accelerated speed (`--speed N`). Use this to look at your
    data without going outside.

Examples:

    # Synthetic random walk around Manhattan LES
    wardrive-preview.py

    # Replay a real session, static (all points visible)
    wardrive-preview.py --csv ~/esp32/marauder-logs/wardrive-20260418T204129.csv

    # Replay the most recent real session with 30x time compression
    wardrive-preview.py --csv latest --speed 30

    # Override the synthetic start point
    wardrive-preview.py 40.73 -73.99

During replay:
    Space / X   pause/resume timeline
    + / -       speed up / slow down
    R           restart from beginning
    S           toggle streets
    C           clear (synthetic mode only)
    Q / Esc     quit
"""

import argparse
import csv
import curses
import glob
import math
import os
import random
import sys
import time
from datetime import datetime


# Add package + dev paths so we pick up the same modules the TUI uses.
_PKG_LIB = '/opt/uconsole/lib'
_DEV_LIB = os.path.expanduser('~/uconsole-cloud/device/lib')
for _p in (_DEV_LIB, _PKG_LIB):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import tui_lib as tui
from tui.framework import (
    C_BORDER, C_CAT, C_DIM, C_FOOTER, C_HEADER, C_ITEM,
    C_STATUS, _tui_input_loop, open_gamepad, close_gamepad,
)
from tui.marauder import (
    _OsmStreetFetcher, _draw_wardrive_map,
    _resolve_wardrive_csv, load_wardrive_csv, _wardrive_replay_loop,
)
C_OK = tui.C_OK  # re-exported from tui_lib


ESSID_POOL = [
    "Spectrum_3f21", "Verizon_8A2B1C", "ATTu6RdbYs", "NETGEAR42",
    "Starbucks WiFi", "TMOBILE-6C30", "xfinitywifi", "eero",
    "NYC_Free_WiFi", "SpectrumSetup-83", "Not your iPhone",
    "FBI Surveillance Van", "LANdlord", "PrettyFly_WiFi",
    "(hidden)", "dlink-AB12", "TP-Link_4821",
]


def random_walk_step(lat, lon, bearing, step_m=2.0):
    """Advance one step (~2m) in the current bearing; jitter the bearing."""
    bearing += random.gauss(0, 0.15)
    lon_scale = math.cos(math.radians(lat))
    dlat = (step_m * math.cos(bearing)) / 111320.0
    dlon = (step_m * math.sin(bearing)) / (111320.0 * lon_scale)
    return lat + dlat, lon + dlon, bearing


# CLI-friendly aliases for backward compat with older invocations.
_resolve_csv_path = _resolve_wardrive_csv
load_csv_session = load_wardrive_csv


def scatter_nearby_ap(lat, lon, max_offset_m=30):
    off = random.uniform(0, max_offset_m)
    theta = random.uniform(0, 2 * math.pi)
    lon_scale = math.cos(math.radians(lat))
    dlat = (off * math.cos(theta)) / 111320.0
    dlon = (off * math.sin(theta)) / (111320.0 * lon_scale)
    bssid = ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))
    essid = random.choice(ESSID_POOL)
    return {
        "first_ts": time.time(),
        "last_seen": time.time(),
        "best_rssi": random.randint(-80, -45),
        "ch": random.choice([1, 1, 6, 6, 6, 11, 11, 36, 44, 149]),
        "essid": essid,
        "bssid": bssid,
        "lat": lat + dlat,
        "lon": lon + dlon,
    }


def _draw_header(scr, w, title, detail, mode_label):
    tui.panel_top(scr, 0, 0, w, title, detail,
                  title_pair=curses.color_pair(C_OK) | curses.A_BOLD)
    tui.panel_side(scr, 1, 0, w)
    tui.put(scr, 1, 2, mode_label[:w - 4], w - 4,
            curses.color_pair(C_DIM) | curses.A_DIM)


def _draw_footer(scr, h, w, hint):
    tui.panel_bot(scr, h - 2, 0, w)
    tui.put(scr, h - 1, 0, hint.center(w), w, curses.color_pair(C_FOOTER))


def run_synthetic(scr, start_lat, start_lon, show_header):
    tui.init_gauge_colors()
    js = open_gamepad()
    scr.timeout(100)

    fetcher = _OsmStreetFetcher()
    fetcher.start()
    fetcher.update_position(start_lat, start_lon)
    for _ in range(10):
        time.sleep(0.2)
        if fetcher.get_streets(): break

    lat, lon = start_lat, start_lon
    bearing = random.uniform(0, 2 * math.pi)
    track = []
    seen = {}
    t0 = time.time()
    last_step = 0.0
    last_ap = 0.0
    streets_on = True
    paused = False
    zoom = 1.0
    pan_lat_off = 0.0
    pan_lon_off = 0.0

    try:
        while True:
            now = time.time()
            if not paused and now - last_step > 0.35:
                lat, lon, bearing = random_walk_step(lat, lon, bearing)
                track.append((now, lat, lon))
                fetcher.update_position(lat, lon)
                last_step = now
                if random.random() < 0.30:
                    ap = scatter_nearby_ap(lat, lon)
                    seen[ap["bssid"]] = ap
            if not paused and now - last_ap > 0.6 and seen:
                ap = random.choice(list(seen.values()))
                ap["best_rssi"] = max(-90, min(-35,
                    ap["best_rssi"] + random.gauss(0, 2)))
                ap["last_seen"] = now
                last_ap = now

            gps_state = {"mode": 3, "lat": lat, "lon": lon, "alt": 15.0,
                         "speed": 1.3 if not paused else 0.0,
                         "sats_used": 8, "sats_seen": 14,
                         "eph": 8.5, "ts": now, "error": None}

            h, w = scr.getmaxyx()
            scr.erase()
            if show_header:
                elapsed = int(now - t0)
                badge = ("\u25cf SIMULATING" if not paused
                         else "\u2016 PAUSED")
                detail = (f"{len(seen)} APs  "
                          f"{elapsed // 60}:{elapsed % 60:02d}")
                _draw_header(scr, w,
                             f"WAR DRIVE PREVIEW  {badge}", detail,
                             f"pos {lat:.5f},{lon:.5f}  "
                             f"streets:{'on' if streets_on else 'off'}  "
                             f"(synthetic)")
                content_y, content_h = 2, h - 4
            else:
                content_y, content_h = 0, h - 1

            street_data = fetcher.get_streets() if streets_on else None
            _draw_wardrive_map(scr, content_y, content_h, w,
                               list(seen.values()), track, gps_state,
                               streets=street_data,
                               zoom=zoom,
                               pan_offset=(pan_lat_off, pan_lon_off))

            _draw_footer(scr, h, w,
                f" {'X Resume' if paused else 'X Pause'} \u2502 "
                f"\u2190\u2191\u2193\u2192 Pan \u2502 [ ] Zoom \u2502 "
                f"0 Reset \u2502 S Streets \u2502 C Clear \u2502 Q Quit ")
            scr.refresh()

            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None: continue
            if key in (ord('q'), ord('Q'), 27) or gp == "back":
                break
            if key in (ord('x'), ord('X')) or gp == "refresh":
                paused = not paused
            if key in (ord('s'), ord('S')):
                streets_on = not streets_on
            if key in (ord('c'), ord('C')):
                track.clear(); seen.clear()
            # Zoom + pan
            step = 0.001 / max(0.2, zoom)
            if key == curses.KEY_UP:
                pan_lat_off += step
            elif key == curses.KEY_DOWN:
                pan_lat_off -= step
            elif key == curses.KEY_LEFT:
                pan_lon_off -= step
            elif key == curses.KEY_RIGHT:
                pan_lon_off += step
            elif key in (ord(']'), ord('+'), ord('=')):
                zoom = min(zoom * 1.25, 16.0)
            elif key in (ord('['), ord('-'), ord('_')):
                zoom = max(zoom / 1.25, 0.2)
            elif key in (ord('0'), curses.KEY_HOME):
                zoom = 1.0
                pan_lat_off = 0.0
                pan_lon_off = 0.0
    finally:
        fetcher.stop()
        if js: close_gamepad(js)


def run_replay(scr, csv_path, speed, show_header, start_static):
    """Thin wrapper around the shared replay loop in tui.marauder."""
    _wardrive_replay_loop(scr, csv_path, speed=speed,
                          start_static=start_static, show_header=show_header)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lat", nargs="?", type=float, default=40.7141,
                    help="Synthetic mode: center latitude "
                         "(default: Manhattan LES)")
    ap.add_argument("lon", nargs="?", type=float, default=-73.9928,
                    help="Synthetic mode: center longitude")
    ap.add_argument("--csv", metavar="PATH",
                    help="Replay a real wardrive CSV instead of "
                         "synthesizing. Accepts full path, filename in "
                         "~/esp32/marauder-logs/, 'latest', or a session "
                         "stamp like '20260418T204129'.")
    ap.add_argument("--speed", type=float, default=30.0,
                    help="Replay speed multiplier (default 30x). "
                         "Ignored in --static mode.")
    ap.add_argument("--static", action="store_true",
                    help="Replay mode: render the whole session at once "
                         "instead of timeline playback.")
    ap.add_argument("--quiet", action="store_true",
                    help="Skip the header panel (show only the map)")
    args = ap.parse_args()

    os.environ.setdefault("ESCDELAY", "25")

    if args.csv:
        path = _resolve_csv_path(args.csv)
        curses.wrapper(lambda s: run_replay(
            s, path, args.speed, not args.quiet, args.static))
    else:
        curses.wrapper(lambda s: run_synthetic(
            s, args.lat, args.lon, not args.quiet))


if __name__ == "__main__":
    main()
