"""ESP32 firmware flash/reflash with safety gates.

Supports flashing both MicroPython and Marauder firmware to the ESP32
on the uConsole AIO board.  Includes battery-level checks, chip-id
validation, gpsd release/restore, and progress callbacks.
"""

import glob
import os
import subprocess
import time

from tui.esp32_detect import (
    Firmware,
    battery_ok,
    get_port,
    invalidate_cache,
    release_gpsd,
)

# ── Firmware binary paths ──────────────────────────────────────────

_MARAUDER_DIR = os.path.expanduser("~/marauder")
_MICROPYTHON_DIR = os.path.expanduser("~/esp32")

_MICROPYTHON_BIN = os.path.join(_MICROPYTHON_DIR, "micropython.bin")

# Marauder flash layout (app-only update at 0x10000)
_MARAUDER_OFFSET = "0x10000"

# Full flash from scratch (bootloader + partition table + OTA + app)
_MARAUDER_FULL_LAYOUT = [
    ("0x1000", "esp32_marauder.ino.bootloader.bin"),
    ("0x8000", "esp32_marauder.ino.partitions.bin"),
    ("0xe000", "boot_app0.bin"),
    ("0x10000", None),  # filled dynamically with latest firmware bin
]

_BACKUP_BIN = os.path.expanduser("~/esp32-backup.bin")

# Minimum battery to allow flash
_MIN_BATTERY_PCT = 20


# ── Helpers ────────────────────────────────────────────────────────

class FlashError(Exception):
    """Raised when a flash operation fails."""


def find_marauder_bin():
    """Return the path to the latest Marauder firmware .bin, or None."""
    pattern = os.path.join(_MARAUDER_DIR, "esp32_marauder_v*_esp32_lddb.bin")
    bins = sorted(glob.glob(pattern))
    return bins[-1] if bins else None


def find_micropython_bin():
    """Return the path to the MicroPython firmware .bin, or None."""
    if os.path.isfile(_MICROPYTHON_BIN):
        return _MICROPYTHON_BIN
    return None


def chip_id(port):
    """Run esptool chip_id and return (chip_type, mac) or raise FlashError."""
    try:
        result = subprocess.run(
            ["esptool.py", "--port", port, "chip_id"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        raise FlashError("esptool.py not found — install with: pip install esptool")
    except subprocess.TimeoutExpired:
        raise FlashError("esptool chip_id timed out (15s)")

    if result.returncode != 0:
        raise FlashError(f"esptool chip_id failed: {result.stderr.strip()}")

    chip_type = ""
    mac = ""
    for line in result.stdout.splitlines():
        if "Chip is" in line:
            chip_type = line.split("Chip is")[-1].strip()
        elif "MAC:" in line:
            mac = line.split("MAC:")[-1].strip()
    if not chip_type:
        raise FlashError("Could not determine chip type from esptool output")
    return chip_type, mac


def _restore_gpsd():
    """Re-enable gpsd after serial operations."""
    for unit in ("gpsd.socket", "gpsd.service"):
        subprocess.run(
            ["sudo", "systemctl", "start", unit],
            capture_output=True, timeout=10,
        )


# ── Flash operations ──────────────────────────────────────────────

def preflight(port=None, target=None):
    """Run all safety checks before flashing.

    Parameters
    ----------
    port : str or None
        Serial port path.
    target : Firmware
        Which firmware we intend to flash.

    Returns
    -------
    dict
        Keys: port, chip_type, mac, binary, target.

    Raises
    ------
    FlashError
        If any safety check fails.
    """
    # Battery gate
    if not battery_ok(_MIN_BATTERY_PCT):
        raise FlashError(
            f"Battery below {_MIN_BATTERY_PCT}% — plug in before flashing"
        )

    # Port gate
    port = port or get_port()
    if port is None:
        raise FlashError("No ESP32 serial port found")

    # Binary gate
    if target == Firmware.MARAUDER:
        binary = find_marauder_bin()
        if binary is None:
            raise FlashError(f"No Marauder firmware found in {_MARAUDER_DIR}")
    elif target == Firmware.MICROPYTHON:
        binary = find_micropython_bin()
        if binary is None:
            raise FlashError(f"micropython.bin not found in {_MICROPYTHON_DIR}")
    else:
        raise FlashError(f"Cannot flash target: {target}")

    # Release gpsd
    release_gpsd(port)

    # Chip validation
    chip_type, mac = chip_id(port)

    return {
        "port": port,
        "chip_type": chip_type,
        "mac": mac,
        "binary": binary,
        "target": target,
    }


def flash_marauder(port, binary, on_output=None):
    """Flash Marauder firmware (app-only at 0x10000).

    Parameters
    ----------
    port : str
        Serial device path.
    binary : str
        Path to the Marauder .bin file.
    on_output : callable or None
        Called with each line of esptool output for progress.

    Raises
    ------
    FlashError
        If esptool exits non-zero.
    """
    cmd = [
        "esptool.py", "--port", port, "--baud", "115200",
        "write_flash", _MARAUDER_OFFSET, binary,
    ]
    _run_flash(cmd, on_output)


def flash_micropython(port, binary, on_output=None):
    """Flash MicroPython firmware (full chip erase + write at 0x0).

    Parameters
    ----------
    port : str
        Serial device path.
    binary : str
        Path to the MicroPython .bin file.
    on_output : callable or None
        Called with each line of esptool output for progress.

    Raises
    ------
    FlashError
        If esptool exits non-zero.
    """
    # Erase flash first for clean MicroPython install
    erase_cmd = ["esptool.py", "--port", port, "erase_flash"]
    _run_flash(erase_cmd, on_output)

    # Write firmware at 0x0
    cmd = [
        "esptool.py", "--port", port, "--baud", "115200",
        "write_flash", "0x0", binary,
    ]
    _run_flash(cmd, on_output)


def _run_flash(cmd, on_output=None):
    """Execute an esptool command, streaming output to callback."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        raise FlashError("esptool.py not found")

    output_lines = []
    for line in proc.stdout:
        line = line.rstrip()
        output_lines.append(line)
        if on_output:
            on_output(line)

    proc.wait()
    if proc.returncode != 0:
        raise FlashError(
            f"esptool failed (exit {proc.returncode}): "
            + "\n".join(output_lines[-5:])
        )


def flash(target, port=None, on_output=None):
    """Full flash workflow: preflight → flash → invalidate cache.

    Parameters
    ----------
    target : Firmware
        MICROPYTHON or MARAUDER.
    port : str or None
        Serial device path (auto-detected if None).
    on_output : callable or None
        Progress callback (receives each output line).

    Returns
    -------
    dict
        Preflight info dict (port, chip_type, mac, binary, target).

    Raises
    ------
    FlashError
        On any failure.
    """
    info = preflight(port=port, target=target)

    if target == Firmware.MARAUDER:
        flash_marauder(info["port"], info["binary"], on_output)
    elif target == Firmware.MICROPYTHON:
        flash_micropython(info["port"], info["binary"], on_output)

    # Invalidate detection cache so next detect() re-probes
    invalidate_cache()

    return info
