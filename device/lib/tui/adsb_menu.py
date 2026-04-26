"""TUI module: ADS-B menu helpers — layer picker entry + hi-res fetch entry."""

import curses
import time

import tui_lib as tui

from tui.framework import (
    C_CAT,
    C_DIM,
    load_config,
    save_config,
)


def run_adsb_layers(scr):
    """Pick which map layers ADSB renders. Persists to config."""
    from tui.adsb import DEFAULT_LAYERS
    from tui.adsb_layer_picker import run_layer_picker
    cfg = load_config()
    cur = int(cfg.get("adsb_layers", DEFAULT_LAYERS))
    new_mask = run_layer_picker(scr, cur)
    if new_mask is not None:
        save_config("adsb_layers", new_mask)


def run_adsb_fetch_hires(scr):
    """Menu wrapper for hi-res fetch — runs synchronously with progress in this screen."""
    from tui import adsb_hires
    cfg = load_config()
    home_lat = cfg.get("adsb_home_lat")
    home_lon = cfg.get("adsb_home_lon")
    h, w = scr.getmaxyx()
    scr.erase()
    dim = curses.color_pair(C_DIM)
    hdr = curses.color_pair(C_CAT) | curses.A_BOLD
    crit = curses.color_pair(tui.C_CRIT)
    if home_lat is None:
        tui.put(scr, 2, 2, "Set home location first.", w - 4, crit)
        tui.put(scr, h - 1, 2, "press any key", w - 4, dim)
        scr.refresh()
        scr.timeout(-1)
        scr.getch()
        return
    tui.put(scr, 1, 2, "FETCH HI-RES BASEMAP", w - 4, hdr)
    tui.put(scr, 3, 2, f"Region: {home_lat:.3f}, {home_lon:.3f}  (±5° lat, ±7° lon)", w - 4, dim)
    tui.put(scr, 4, 2, "Source: github.com/nvkelso/natural-earth-vector (1:10m)", w - 4, dim)
    tui.put(scr, 5, 2, "Layers: coastlines, countries, states, lakes, rivers, airports", w - 4, dim)
    tui.put(scr, 7, 2, "Background fetch — you can return to the map immediately.", w - 4, dim)
    tui.put(scr, 9, 2, "y = start fetch    n = cancel", w - 4, hdr)
    scr.refresh()
    scr.timeout(-1)
    while True:
        k = scr.getch()
        if k in (ord('y'), ord('Y')):
            state = {"status": "idle", "msg": "", "banner_dismissed": False}
            adsb_hires.start_fetch(home_lat, home_lon, state)
            tui.put(scr, 11, 2, "Fetch started in background. Returning to menu.",
                    w - 4, curses.color_pair(tui.C_OK) | curses.A_BOLD)
            scr.refresh()
            time.sleep(1)
            scr.timeout(100)
            return
        if k in (ord('n'), ord('N'), ord('q'), 27):
            scr.timeout(100)
            return


HANDLERS = {
    "_adsb_layers": run_adsb_layers,
    "_adsb_fetch_hires": run_adsb_fetch_hires,
}
