"""Manual home location picker for ADS-B map — text entry + preset metros."""

import curses

from tui.framework import (
    _tui_input_loop,
    close_gamepad,
    load_config,
    open_gamepad,
    save_config_multi,
)
import tui_lib as tui


PRESETS = [
    ("NYC", "New York",      40.7128,  -74.0060),
    ("LAX", "Los Angeles",   33.9416, -118.4085),
    ("ORD", "Chicago",       41.9742,  -87.9073),
    ("LHR", "London",        51.4700,   -0.4543),
    ("NRT", "Tokyo",         35.7720,  140.3929),
    ("SYD", "Sydney",       -33.9399,  151.1753),
    ("DXB", "Dubai",         25.2532,   55.3657),
    ("FRA", "Frankfurt",     50.0379,    8.5622),
]


def _draw(scr, lat_str, lon_str, field, preset_idx, status):
    h, w = scr.getmaxyx()
    scr.erase()
    dim = curses.color_pair(tui.C_DIM)
    hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
    item = curses.color_pair(tui.C_ITEM)
    sel = curses.color_pair(tui.C_SEL) | curses.A_BOLD | curses.A_REVERSE
    ok = curses.color_pair(tui.C_OK) | curses.A_BOLD
    crit = curses.color_pair(tui.C_CRIT)

    tui.put(scr, 1, 2, "ADS-B HOME — MANUAL ENTRY", w - 4, hdr)
    tui.put(scr, 2, 2, "Type lat/lon, or pick a preset below.", w - 4, dim)

    lat_attr = sel if field == 0 else item
    lon_attr = sel if field == 1 else item
    tui.put(scr, 4, 4, "Latitude  : ", 14, dim)
    tui.put(scr, 4, 18, f"[ {lat_str:<14} ]", 20, lat_attr)
    tui.put(scr, 5, 4, "Longitude : ", 14, dim)
    tui.put(scr, 5, 18, f"[ {lon_str:<14} ]", 20, lon_attr)

    tui.put(scr, 7, 2, "PRESETS:", w - 4, hdr)
    for i, (code, name, lat, lon) in enumerate(PRESETS):
        attr = sel if (field == 2 and i == preset_idx) else item
        line = f"  {code}  {name:<12}  {lat:>8.3f}, {lon:>9.3f}"
        tui.put(scr, 8 + i, 4, line, w - 6, attr)

    tui.put(scr, h - 3, 2, status, w - 4,
            ok if status.startswith("Saved") else crit if status.startswith("Error") else dim)
    tui.put(scr, h - 1, 2,
            "Tab next field   ←→ edit/preset   Enter save   q cancel",
            w - 4, dim)
    scr.refresh()


def _validate(lat_str, lon_str):
    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except ValueError:
        return None, None, "Error: not a number"
    if not (-90 <= lat <= 90):
        return None, None, "Error: lat must be -90..90"
    if not (-180 <= lon <= 180):
        return None, None, "Error: lon must be -180..180"
    return lat, lon, ""


def run_home_picker(scr):
    cfg = load_config()
    lat_str = f"{float(cfg.get('adsb_home_lat', 40.7128)):.4f}"
    lon_str = f"{float(cfg.get('adsb_home_lon', -74.0060)):.4f}"
    field = 0  # 0=lat, 1=lon, 2=presets
    preset_idx = 0
    status = ""

    js = open_gamepad()
    scr.timeout(-1)
    try:
        while True:
            _draw(scr, lat_str, lon_str, field, preset_idx, status)
            key, gp = _tui_input_loop(scr, js)
            if key in (ord("q"), ord("Q"), 27) or gp == "back":
                return
            elif key == ord("\t") or key == curses.KEY_DOWN or gp == "down":
                if field < 2:
                    field += 1
                else:
                    preset_idx = min(len(PRESETS) - 1, preset_idx + 1)
            elif key == curses.KEY_UP or gp == "up":
                if field == 2 and preset_idx > 0:
                    preset_idx -= 1
                elif field == 2:
                    field = 1
                elif field > 0:
                    field -= 1
            elif key == curses.KEY_BTAB:
                field = max(0, field - 1)
            elif key in (curses.KEY_ENTER, 10, 13):
                if field == 2:
                    code, name, lat, lon = PRESETS[preset_idx]
                    save_config_multi({"adsb_home_lat": lat, "adsb_home_lon": lon})
                    status = f"Saved: {code} {lat:.4f}, {lon:.4f}"
                    lat_str = f"{lat:.4f}"
                    lon_str = f"{lon:.4f}"
                else:
                    lat, lon, err = _validate(lat_str, lon_str)
                    if err:
                        status = err
                    else:
                        save_config_multi({"adsb_home_lat": lat, "adsb_home_lon": lon})
                        status = f"Saved: {lat:.4f}, {lon:.4f}"
            elif field in (0, 1):
                target = lat_str if field == 0 else lon_str
                if key in (curses.KEY_BACKSPACE, 127, 8):
                    target = target[:-1]
                elif 32 <= key < 127:
                    ch = chr(key)
                    if ch in "0123456789.-":
                        target = target + ch
                if field == 0:
                    lat_str = target
                else:
                    lon_str = target
    finally:
        if js:
            close_gamepad(js)
        scr.timeout(100)


def run_home_picker_action(scr):
    run_home_picker(scr)


HANDLERS = {
    "_adsb_home_picker": run_home_picker_action,
}
