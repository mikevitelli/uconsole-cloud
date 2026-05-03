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
#           ssid Big Parma
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
