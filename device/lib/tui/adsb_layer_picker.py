"""Popup picker to toggle individual ADS-B map layers."""

import curses

from tui.framework import _tui_input_loop, close_gamepad, open_gamepad
from tui.adsb import (
    LAYER_AIRPORTS,
    LAYER_CARDINALS,
    LAYER_COAST,
    LAYER_COUNTRIES,
    LAYER_LAKES,
    LAYER_RINGS,
    LAYER_RIVERS,
    LAYER_STATES,
)
import tui_lib as tui


LAYERS = [
    ("Coastlines",    LAYER_COAST),
    ("Countries",     LAYER_COUNTRIES),
    ("States/Prov.",  LAYER_STATES),
    ("Lakes",         LAYER_LAKES),
    ("Rivers",        LAYER_RIVERS),
    ("Airports",      LAYER_AIRPORTS),
    ("Range Rings",   LAYER_RINGS),
    ("N/S/E/W",       LAYER_CARDINALS),
]


def run_layer_picker(scr, current):
    """Modal picker. Returns new layer mask, or None if cancelled."""
    selected = 0
    mask = current
    js = open_gamepad()
    scr.timeout(-1)
    try:
        while True:
            h, w = scr.getmaxyx()
            scr.erase()
            dim = curses.color_pair(tui.C_DIM)
            hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
            item = curses.color_pair(tui.C_ITEM)
            sel = curses.color_pair(tui.C_SEL) | curses.A_BOLD | curses.A_REVERSE
            ok = curses.color_pair(tui.C_OK) | curses.A_BOLD

            tui.put(scr, 1, 2, "MAP LAYERS", w - 4, hdr)
            tui.put(scr, 2, 2, "space toggle   enter save   q cancel", w - 4, dim)

            for i, (name, bit) in enumerate(LAYERS):
                on = bool(mask & bit)
                box = "[x]" if on else "[ ]"
                line = f"  {box}  {name}"
                attr = sel if i == selected else (ok if on else item)
                tui.put(scr, 4 + i, 2, line, w - 4, attr)

            scr.refresh()
            key, gp = _tui_input_loop(scr, js)
            if key in (ord("q"), ord("Q"), 27) or gp == "back":
                return None
            elif key == curses.KEY_UP or gp == "up":
                selected = (selected - 1) % len(LAYERS)
            elif key == curses.KEY_DOWN or gp == "down":
                selected = (selected + 1) % len(LAYERS)
            elif key == ord(" "):
                mask ^= LAYERS[selected][1]
            elif key in (curses.KEY_ENTER, 10, 13):
                return mask
    finally:
        if js:
            close_gamepad(js)
        scr.timeout(100)
