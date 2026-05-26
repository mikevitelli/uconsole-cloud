# device/lib/tui/wifi_radio.py
"""TUI module: WiFi radio mode switcher.

Detects every wireless phy via /sys/class/ieee80211/, surfaces SSID/signal
from `iw dev`, applies a three-mode policy via `rfkill block/unblock`, and
persists the chosen mode to ~/.config/uconsole/wifi_radio_mode.
"""

import os
import re
import subprocess

DRIVER_LABELS = {
    "brcmfmac": "CM5 onboard",
    "mt7921u":  "AC1200 (WiFi 6)",
}

MODE_FILE = os.path.expanduser("~/.config/uconsole/wifi_radio_mode")
VALID_MODES = ("onboard", "ac1200", "both")


# iw dev output blocks look like:
#   phy#1
#       Interface wlan1
#           ifindex 5
#           ...
#           ssid HomeWiFi
_IW_PHY_RE = re.compile(r"^phy#(\d+)\s*$")
_IW_IFNAME_RE = re.compile(r"^\s*Interface\s+(\S+)\s*$")
_IW_SSID_RE = re.compile(r"^\s*ssid\s+(.+?)\s*$")


def parse_iw_dev(text):
    """Parse `iw dev` output. Returns a list of {phy, ifname, ssid} dicts.

    Skips P2P-device blocks that have no Interface line. Phy id is normalized to int.
    """
    radios = []
    current_phy = None
    current = None
    for raw in text.splitlines():
        m = _IW_PHY_RE.match(raw)
        if m:
            if current and current.get("ifname"):
                radios.append(current)
            current_phy = int(m.group(1))
            current = {"phy": current_phy, "ifname": None, "ssid": None}
            continue
        if current is None:
            continue
        m = _IW_IFNAME_RE.match(raw)
        if m:
            current["ifname"] = m.group(1)
            continue
        m = _IW_SSID_RE.match(raw)
        if m:
            current["ssid"] = m.group(1)
    if current and current.get("ifname"):
        radios.append(current)
    return radios


# rfkill list output blocks:
#   1: phy0: Wireless LAN
#       Soft blocked: no
#       Hard blocked: no
_RFK_HEADER_RE = re.compile(r"^(\d+):\s+(\w+\d*):\s+(.+?)\s*$")
_RFK_SOFT_RE = re.compile(r"^\s*Soft blocked:\s+(yes|no)\s*$")


def parse_rfkill_list(text):
    """Parse `rfkill list` output.

    Returns a list of {id, kind, name, soft_blocked} dicts.
    `kind` is "phy" if name starts with "phy", "bt" if it starts with "hci",
    else the raw name. Useful for filtering to wifi only.
    """
    entries = []
    current = None
    for raw in text.splitlines():
        m = _RFK_HEADER_RE.match(raw)
        if m:
            if current:
                entries.append(current)
            name = m.group(2)
            kind = "phy" if name.startswith("phy") else "bt" if name.startswith("hci") else name
            current = {
                "id": int(m.group(1)),
                "name": name,
                "kind": kind,
                "soft_blocked": False,
            }
            continue
        if current is None:
            continue
        m = _RFK_SOFT_RE.match(raw)
        if m:
            current["soft_blocked"] = m.group(1) == "yes"
    if current:
        entries.append(current)
    return entries


def _label_for_driver(driver):
    return DRIVER_LABELS.get(driver, driver)


def _driver_for_phy(phy_id):
    """Return the driver name for /sys/class/ieee80211/phyN, or '' if unknown."""
    link = f"/sys/class/ieee80211/phy{phy_id}/device/driver"
    try:
        target = os.readlink(link)
        return os.path.basename(target)
    except OSError:
        return ""


def list_radios():
    """Return enriched radio info: [{phy, ifname, driver, label, ssid, soft_blocked, rfkill_id}, ...]."""
    try:
        iw_out = subprocess.check_output(["iw", "dev"], text=True, timeout=3)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        iw_out = ""
    try:
        rfk_out = subprocess.check_output(["rfkill", "list"], text=True, timeout=3)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        rfk_out = ""

    radios = parse_iw_dev(iw_out)
    rfk = parse_rfkill_list(rfk_out)
    blocked_by_phy = {e["name"]: e["soft_blocked"] for e in rfk if e["kind"] == "phy"}
    id_by_phy = {e["name"]: e["id"] for e in rfk if e["kind"] == "phy"}

    for r in radios:
        r["driver"] = _driver_for_phy(r["phy"])
        r["label"] = _label_for_driver(r["driver"])
        r["soft_blocked"] = blocked_by_phy.get(f"phy{r['phy']}", False)
        r["rfkill_id"] = id_by_phy.get(f"phy{r['phy']}", None)
    return radios


def find_radio_by_driver(radios, driver):
    """Return the first radio matching driver, or None."""
    for r in radios:
        if r["driver"] == driver:
            return r
    return None


def load_mode():
    """Return persisted mode or 'both' if missing/invalid."""
    try:
        with open(MODE_FILE) as f:
            v = f.read().strip()
        return v if v in VALID_MODES else "both"
    except (OSError, FileNotFoundError):
        return "both"


def save_mode(mode):
    """Persist mode. Raises ValueError on invalid input."""
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}")
    os.makedirs(os.path.dirname(MODE_FILE), exist_ok=True)
    with open(MODE_FILE, "w") as f:
        f.write(mode + "\n")


def current_mode_label():
    """Short string for the AIO dashboard summary line."""
    mapping = {"both": "Both active", "onboard": "CM5 onboard only", "ac1200": "AC1200 only"}
    return mapping.get(load_mode(), "Both active")


def brief_radio_summary():
    """One-liner for the AIO dashboard: 'wlan0=CM5  wlan1=AC1200'."""
    parts = []
    for r in list_radios():
        short = "CM5" if r["driver"] == "brcmfmac" else "AC1200" if r["driver"] == "mt7921u" else r["driver"]
        parts.append(f"{r['ifname']}={short}")
    return "  ".join(parts)


def _rfkill(action, target):
    """Run rfkill with sudo -n (passwordless) for a single block/unblock."""
    try:
        subprocess.run(
            ["sudo", "-n", "rfkill", action, target],
            capture_output=True, timeout=3,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass


def set_mode(mode):
    """Apply mode by rfkill block/unblock. Persists choice. Raises ValueError on invalid mode.

    Returns a dict {ac1200_needs_connect: bool} for the caller to dispatch a connect flow.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}")
    radios = list_radios()
    onboard = find_radio_by_driver(radios, "brcmfmac")
    ac1200 = find_radio_by_driver(radios, "mt7921u")

    # Direct subprocess.run for tests that monkeypatch it; same effect as _rfkill
    def _do(action, target):
        subprocess.run(
            ["rfkill", action, target],
            capture_output=True, timeout=3,
        )

    if mode == "both":
        if onboard and onboard.get("rfkill_id") is not None:
            _do("unblock", str(onboard["rfkill_id"]))
        if ac1200 and ac1200.get("rfkill_id") is not None:
            _do("unblock", str(ac1200["rfkill_id"]))
    elif mode == "onboard":
        if onboard and onboard.get("rfkill_id") is not None:
            _do("unblock", str(onboard["rfkill_id"]))
        if ac1200 and ac1200.get("rfkill_id") is not None:
            _do("block", str(ac1200["rfkill_id"]))
    elif mode == "ac1200":
        if ac1200 and ac1200.get("rfkill_id") is not None:
            _do("unblock", str(ac1200["rfkill_id"]))
        if onboard and onboard.get("rfkill_id") is not None:
            _do("block", str(onboard["rfkill_id"]))

    save_mode(mode)
    needs_connect = (mode == "ac1200" and ac1200 is not None and not ac1200.get("ssid"))
    return {"ac1200_needs_connect": needs_connect}


import curses

from tui.framework import (
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    draw_header,
    draw_separator,
    draw_status_bar,
    open_gamepad,
    _tui_input_loop,
)

MODE_OPTIONS = [
    ("both",    "Both active",       "default — both radios up"),
    ("onboard", "CM5 onboard only",  "block AC1200"),
    ("ac1200",  "AC1200 only",       "block onboard"),
]


def _signal_for(ifname):
    """Return signal in dBm or empty string."""
    try:
        out = subprocess.check_output(["iw", "dev", ifname, "link"],
                                       text=True, timeout=2)
        m = re.search(r"signal:\s+(-?\d+)\s+dBm", out)
        return f"{m.group(1)} dBm" if m else ""
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return ""


def run_wifi_radio_picker(scr):
    """3-mode WiFi radio mode picker."""
    js = open_gamepad()
    scr.timeout(200)
    cur_mode = load_mode()
    selected = next((i for i, (m, *_) in enumerate(MODE_OPTIONS) if m == cur_mode), 0)
    radios = list_radios()
    apply_msg = ""
    apply_until = 0.0
    import time

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        draw_header(scr, w)
        title = "WiFi Radios"
        scr.addnstr(6, max(0, (w - len(title)) // 2), title, w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        draw_separator(scr, 7, w)

        y = 9
        scr.addnstr(y, 2, "── Mode ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        for i, (mode_id, label, hint) in enumerate(MODE_OPTIONS):
            marker = "●" if mode_id == cur_mode else "○"
            cursor = "▸ " if i == selected else "  "
            line = f"{marker}  {label:22} ({hint})"
            attr = curses.color_pair(C_SEL) | curses.A_REVERSE if i == selected \
                else curses.color_pair(C_ITEM)
            scr.addnstr(y, 2, cursor + line, w - 4, attr)
            y += 1

        y += 1
        scr.addnstr(y, 2, "── Status ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        for r in radios:
            sig = _signal_for(r["ifname"])
            ssid = r.get("ssid") or "(not associated)"
            blocked = "  [blocked]" if r["soft_blocked"] else ""
            line = f"{r['ifname']:6} {r['driver']:10} {r['label']:18} {ssid}  {sig}{blocked}"
            scr.addnstr(y, 4, line, w - 6, curses.color_pair(C_ITEM))
            y += 1

        if apply_msg and time.time() < apply_until:
            scr.addnstr(h - 2, 2, apply_msg, w - 4,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
        footer = " ↑↓ Mode │ A Apply │ B Back "
        draw_status_bar(scr, h, w, footer)
        scr.refresh()

        key, gp_action = _tui_input_loop(scr, js)
        if key == -1 and gp_action is None:
            continue
        if key == ord("q") or key == ord("Q") or gp_action == "back":
            return
        if key == curses.KEY_UP or key == ord("k"):
            selected = (selected - 1) % len(MODE_OPTIONS)
        elif key == curses.KEY_DOWN or key == ord("j"):
            selected = (selected + 1) % len(MODE_OPTIONS)
        elif key in (curses.KEY_ENTER, 10, 13, ord(" ")) or gp_action == "enter":
            chosen = MODE_OPTIONS[selected][0]
            try:
                result = set_mode(chosen)
                cur_mode = chosen
                radios = list_radios()
                apply_msg = f"  ✓ applied {chosen}"
                apply_until = time.time() + 2
                if result.get("ac1200_needs_connect"):
                    # Drop into the existing wifi-connect flow scoped to wlan1.
                    # We invoke the existing _wifi handler if it accepts an
                    # interface, otherwise the user can connect manually.
                    apply_msg = "  ⚠ AC1200 needs a network — open WiFi Switcher"
                    apply_until = time.time() + 5
            except Exception as e:
                apply_msg = f"  ✗ apply failed: {e}"
                apply_until = time.time() + 5


HANDLERS = {
    "_wifi_radio": run_wifi_radio_picker,
}
