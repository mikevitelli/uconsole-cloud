"""TUI module: AIO v2 board control + power dashboard.

Wraps the `aiov2_ctl` CLI from the hackergadgets-uconsole-aio-board package.
On AIO v1 boards (where aiov2_ctl is absent) this module's dashboard
handler delegates to the legacy radio/aio-check.sh panel.
"""

import os
import re
import shutil
import subprocess

AIOV2_CTL = "/usr/local/bin/aiov2_ctl"

RAIL_LABELS = {
    "GPS":  "uBlox NEO",
    "LORA": "SX1262",
    "SDR":  "RTL-SDR",
    "USB":  "AC1200 + ESP32",
}

# Rail line: "GPS   GPIO27: ON"
_RAIL_RE = re.compile(r"^\s*(GPS|LORA|SDR|USB)\s+GPIO(\d+):\s+(ON|OFF)\s*$")
# Power-section line: "Voltage   : 4.16 V"  or  "Capacity  : 89%"
_KV_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.+?)\s*$")

# Map the labels aiov2_ctl emits to our snake-case keys
_KEY_MAP = {
    "Source":    "source",
    "Status":    "status",
    "Capacity":  "capacity",
    "Direction": "direction",
    "Mode":      "mode",
    "Voltage":   "voltage",
    "Current":   "current",
    "Power":     "power",
}


def parse_status(text):
    """Parse `aiov2_ctl --status` text output.

    Returns:
        {
            "rails": {"GPS": {"gpio": 27, "state": True}, ...},
            "power": {"source": "AC", "capacity": 89, "voltage": 4.16, ...},
        }
    Unknown / malformed input yields empty dicts; the function never raises.
    """
    rails = {}
    power = {}
    for raw_line in text.splitlines():
        m = _RAIL_RE.match(raw_line)
        if m:
            rails[m.group(1)] = {"gpio": int(m.group(2)), "state": m.group(3) == "ON"}
            continue
        m = _KV_RE.match(raw_line)
        if not m:
            continue
        label, value = m.group(1), m.group(2)
        key = _KEY_MAP.get(label)
        if key is None:
            continue
        if key == "capacity":
            # "89%" → 89
            try:
                power[key] = int(value.rstrip("%").strip())
            except ValueError:
                continue
        elif key in ("voltage", "current", "power"):
            # "4.16 V" → 4.16
            try:
                power[key] = float(value.split()[0])
            except (ValueError, IndexError):
                continue
        else:
            power[key] = value
    return {"rails": rails, "power": power}


# ---------------------------------------------------------------------------
# Board detection
# ---------------------------------------------------------------------------

_detect_cache = None


def detect():
    """Return 'v2' if the AIO v2 control binary is present and executable, else 'v1'.

    Cached for the lifetime of the process.
    """
    global _detect_cache
    if _detect_cache is not None:
        return _detect_cache
    if os.path.isfile(AIOV2_CTL) and os.access(AIOV2_CTL, os.X_OK):
        _detect_cache = "v2"
    else:
        _detect_cache = "v1"
    return _detect_cache
