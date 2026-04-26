"""TUI module: ADS-B menu helpers — layer picker, hi-res fetch, feeder toggle."""

import curses
import subprocess
import time

import tui_lib as tui

from tui.framework import (
    C_CAT,
    C_DIM,
    load_config,
    save_config,
)

FEEDER_SERVICE = "readsb"


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


def _feeder_state():
    """Return (active, enabled) booleans for the readsb service."""
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", FEEDER_SERVICE]
    ).returncode == 0
    enabled = subprocess.run(
        ["systemctl", "is-enabled", "--quiet", FEEDER_SERVICE]
    ).returncode == 0
    return active, enabled


def _feeder_aircraft_count():
    """Read /run/readsb/aircraft.json and return aircraft count, or None on error."""
    import json
    try:
        with open(f"/run/{FEEDER_SERVICE}/aircraft.json") as f:
            return len((json.load(f) or {}).get("aircraft", []))
    except Exception:
        return None


def run_adsb_feeder(scr):
    """Toggle the readsb ADS-B feeder service on/off. Holds the RTL-SDR exclusively."""
    h, w = scr.getmaxyx()
    dim = curses.color_pair(C_DIM)
    hdr = curses.color_pair(C_CAT) | curses.A_BOLD
    ok_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
    crit = curses.color_pair(tui.C_CRIT)

    msg = ""
    scr.timeout(-1)
    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        active, enabled = _feeder_state()
        count = _feeder_aircraft_count() if active else None

        tui.put(scr, 1, 2, "ADS-B FEEDER (readsb)", w - 4, hdr)

        state_text = "RUNNING" if active else "STOPPED"
        state_attr = ok_attr if active else crit
        tui.put(scr, 3, 2, f"Status:  {state_text}", w - 4, state_attr)
        boot_text = "starts at boot" if enabled else "disabled at boot"
        tui.put(scr, 4, 2, f"Boot:    {boot_text}", w - 4, dim)
        if active and count is not None:
            tui.put(scr, 5, 2, f"Tracking: {count} aircraft", w - 4, dim)

        tui.put(scr, 7, 2, "Holds the RTL-SDR exclusively while running.", w - 4, dim)
        tui.put(scr, 8, 2, "Stop it before using FM, rtl_433, scan, or other SDR tools.", w - 4, dim)

        row = 10
        if active:
            tui.put(scr, row,     2, "s = stop          (frees the SDR)",            w - 4, hdr)
            tui.put(scr, row + 1, 2, "r = restart       (re-read /etc/default/readsb)", w - 4, hdr)
        else:
            tui.put(scr, row, 2, "s = start         (claims the SDR)", w - 4, hdr)
        tui.put(scr, row + 2, 2, "b = toggle boot autostart", w - 4, hdr)
        tui.put(scr, row + 4, 2, "q = back", w - 4, dim)

        if msg:
            tui.put(scr, h - 2, 2, msg, w - 4, ok_attr)

        scr.refresh()
        k = scr.getch()
        if k in (ord('q'), ord('Q'), 27):
            scr.timeout(100)
            return
        if k in (ord('s'), ord('S')):
            action = "stop" if active else "start"
            r = subprocess.run(
                ["sudo", "-n", "systemctl", action, FEEDER_SERVICE],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                msg = f"  ✓ readsb {action}ed"
                time.sleep(0.4)  # let the state settle before redraw
            else:
                msg = f"  ✗ {action} failed — {(r.stderr or '').strip()[:60]}"
        elif k in (ord('r'), ord('R')) and active:
            r = subprocess.run(
                ["sudo", "-n", "systemctl", "restart", FEEDER_SERVICE],
                capture_output=True, text=True,
            )
            msg = "  ✓ readsb restarted" if r.returncode == 0 else f"  ✗ restart failed"
            time.sleep(0.4)
        elif k in (ord('b'), ord('B')):
            action = "disable" if enabled else "enable"
            r = subprocess.run(
                ["sudo", "-n", "systemctl", action, FEEDER_SERVICE],
                capture_output=True, text=True,
            )
            msg = f"  ✓ boot autostart {action}d" if r.returncode == 0 else f"  ✗ {action} failed"


HANDLERS = {
    "_adsb_layers": run_adsb_layers,
    "_adsb_fetch_hires": run_adsb_fetch_hires,
    "_adsb_feeder": run_adsb_feeder,
}
