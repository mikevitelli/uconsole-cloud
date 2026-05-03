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
    """Return enriched radio info: [{phy, ifname, driver, label, ssid, soft_blocked}, ...]."""
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

    for r in radios:
        r["driver"] = _driver_for_phy(r["phy"])
        r["label"] = _label_for_driver(r["driver"])
        r["soft_blocked"] = blocked_by_phy.get(f"phy{r['phy']}", False)
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
        if onboard:
            _do("unblock", f"phy{onboard['phy']}")
        if ac1200:
            _do("unblock", f"phy{ac1200['phy']}")
    elif mode == "onboard":
        if onboard:
            _do("unblock", f"phy{onboard['phy']}")
        if ac1200:
            _do("block", f"phy{ac1200['phy']}")
    elif mode == "ac1200":
        if ac1200:
            _do("unblock", f"phy{ac1200['phy']}")
        if onboard:
            _do("block", f"phy{onboard['phy']}")

    save_mode(mode)
    needs_connect = (mode == "ac1200" and ac1200 is not None and not ac1200.get("ssid"))
    return {"ac1200_needs_connect": needs_connect}
