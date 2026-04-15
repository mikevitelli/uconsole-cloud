"""Basemap info / debug screen for ADS-B."""

import curses
import os

from tui.framework import _tui_input_loop, close_gamepad, load_config, open_gamepad
from tui.adsb import (
    BASEMAP_GLOBAL,
    BASEMAP_LEGACY,
    _load_global_basemap,
    _load_hires_basemap,
)
from tui.adsb_hires import cache_path_for, cache_exists
import tui_lib as tui


def _fmt_size(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.2f} MB"


def run_basemap_info(scr):
    js = open_gamepad()
    scr.timeout(-1)
    try:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(tui.C_DIM)
        hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
        item = curses.color_pair(tui.C_ITEM)
        ok = curses.color_pair(tui.C_OK) | curses.A_BOLD
        warn = curses.color_pair(tui.C_WARN) | curses.A_BOLD

        tui.put(scr, 1, 2, "ADS-B BASEMAP INFO", w - 4, hdr)

        cfg = load_config()
        home_lat = cfg.get("adsb_home_lat")
        home_lon = cfg.get("adsb_home_lon")

        y = 3
        tui.put(scr, y, 2, "Home:", 8, dim)
        if home_lat is None:
            tui.put(scr, y, 10, "(not set)", w - 12, warn)
        else:
            tui.put(scr, y, 10, f"{home_lat:.4f}, {home_lon:.4f}", w - 12, item)
        y += 2

        # Global bundle
        tui.put(scr, y, 2, "Global bundle:", 16, hdr)
        y += 1
        for path in (BASEMAP_GLOBAL, BASEMAP_LEGACY):
            if os.path.exists(path):
                tui.put(scr, y, 4, os.path.basename(path), w - 6, item)
                tui.put(scr, y, 4 + 36, _fmt_size(os.path.getsize(path)), 12, dim)
                y += 1
        g = _load_global_basemap()
        for name, items in g.get("layers", {}).items():
            tui.put(scr, y, 6, f"- {name}: {len(items)}", w - 8, dim)
            y += 1
        y += 1

        # Hi-res cache
        tui.put(scr, y, 2, "Hi-res cache:", 16, hdr)
        y += 1
        if home_lat is None:
            tui.put(scr, y, 4, "(home not set)", w - 6, warn)
            y += 1
        else:
            cp = cache_path_for(home_lat, home_lon)
            if cache_exists(home_lat, home_lon):
                tui.put(scr, y, 4, os.path.basename(cp), w - 6, ok)
                tui.put(scr, y, 4 + 36, _fmt_size(os.path.getsize(cp)), 12, dim)
                y += 1
                hires = _load_hires_basemap(home_lat, home_lon)
                if hires:
                    for name, items in hires.get("layers", {}).items():
                        tui.put(scr, y, 6, f"- {name}: {len(items)}", w - 8, dim)
                        y += 1
            else:
                tui.put(scr, y, 4, "(no cache for this region)", w - 6, warn)
                y += 1
                tui.put(scr, y, 4, f"would write to: {os.path.basename(cp)}", w - 6, dim)
                y += 1

        tui.put(scr, h - 1, 2, "press any key", w - 4, dim)
        scr.refresh()
        scr.getch()
    finally:
        if js:
            close_gamepad(js)
        scr.timeout(100)
