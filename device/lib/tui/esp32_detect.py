"""ESP32 firmware detection handshake.

Probes the serial port (/dev/esp32 or /dev/ttyUSB0) to detect whether
the connected ESP32 is running MicroPython or Marauder firmware.

Results are cached for 30 seconds to avoid repeated handshakes.
"""

import enum
import os
import subprocess
import time

# ── Firmware enum ───────────────────────────────────────────────────


class Firmware(enum.Enum):
    MICROPYTHON = "micropython"
    MARAUDER = "marauder"
    BRUCE = "bruce"
    MIMICLAW = "mimiclaw"
    UNKNOWN = "unknown"


# ── Cache ───────────────────────────────────────────────────────────

_cache = {"firmware": None, "port": None, "timestamp": 0.0}
_CACHE_TTL = 30.0


def invalidate_cache():
    """Clear the cached detection result."""
    _cache["firmware"] = None
    _cache["port"] = None
    _cache["timestamp"] = 0.0


# ── Helpers ─────────────────────────────────────────────────────────

_PORTS = ["/dev/esp32", "/dev/ttyACM0", "/dev/ttyUSB0"]


def get_port():
    """Return the first available serial port path, or None."""
    for p in _PORTS:
        if os.path.exists(p):
            return p
    return None


def battery_ok(min_pct=20):
    """Return True if battery capacity >= *min_pct* %.

    Returns True if the sysfs file is unreadable (assume plugged in).
    """
    try:
        with open("/sys/class/power_supply/axp20x-battery/capacity") as f:
            return int(f.read().strip()) >= min_pct
    except (OSError, ValueError):
        return True


def release_gpsd(port_path):
    """Stop gpsd if it holds *port_path*.

    Uses ``fuser`` to check, then stops gpsd.socket and gpsd.service.
    Returns True if gpsd was released.
    """
    try:
        result = subprocess.run(
            ["fuser", port_path],
            capture_output=True, timeout=5,
        )
        if result.returncode != 0:
            return False  # nothing holds the port
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

    # Something holds the port — stop gpsd units
    for unit in ("gpsd.socket", "gpsd.service"):
        subprocess.run(
            ["sudo", "systemctl", "stop", unit],
            capture_output=True, timeout=10,
        )
    time.sleep(0.3)
    return True


# ── Detection ───────────────────────────────────────────────────────

def detect(port=None, timeout=2.0, force=None):
    """Detect which firmware the ESP32 is running.

    Parameters
    ----------
    port : str or None
        Serial device path.  Defaults to the first available port.
    timeout : float
        Serial read timeout in seconds.
    force : Firmware or None
        If set, skip probing and return this value immediately.

    Returns
    -------
    Firmware
        The detected (or forced / cached) firmware type.
    """
    if force is not None:
        return force

    port = port or get_port()
    if port is None:
        return Firmware.UNKNOWN

    # Return cached result if fresh and same port
    now = time.time()
    if (_cache["firmware"] is not None
            and _cache["port"] == port
            and (now - _cache["timestamp"]) < _CACHE_TTL):
        return _cache["firmware"]

    try:
        import serial as _pyserial
    except ImportError:
        return Firmware.UNKNOWN

    ser = None
    try:
        try:
            ser = _pyserial.Serial(port, 115200, timeout=timeout)
        except _pyserial.SerialException:
            # Port may be held by gpsd — try to release
            if release_gpsd(port):
                ser = _pyserial.Serial(port, 115200, timeout=timeout)
            else:
                return Firmware.UNKNOWN

        # Phase 1: MicroPython probe — Ctrl-C×2 interrupts running code
        ser.reset_input_buffer()
        ser.write(b"\x03\x03\r\n")
        time.sleep(0.5)
        raw = ser.read(ser.in_waiting or 1024)
        resp = raw.decode("utf-8", errors="replace")

        # Phase 2: MicroPython check
        if ">>>" in resp or "MicroPython" in resp:
            fw = Firmware.MICROPYTHON
            _update_cache(fw, port)
            return fw

        # Phase 2.5: MimiClaw — the ESP-IDF console auto-prints a "mimi>"
        # prompt after any newline, so the Phase 1 probe's response
        # already contains the marker. No extra round-trip needed.
        if "mimi>" in resp:
            fw = Firmware.MIMICLAW
            _update_cache(fw, port)
            return fw

        # Phase 3: Marauder probe — wake + info command
        # Marauder needs a newline wake-up, drain, then actual command
        ser.reset_input_buffer()
        ser.write(b"\r\n")
        time.sleep(0.3)
        ser.read(ser.in_waiting or 1024)  # drain wake response
        ser.write(b"info\r\n")
        time.sleep(1.5)
        raw2 = ser.read(ser.in_waiting or 4096)
        resp2 = raw2.decode("utf-8", errors="replace")

        # Phase 4: Marauder info response
        if "Marauder" in resp2 or "Firmware" in resp2:
            fw = Firmware.MARAUDER
            _update_cache(fw, port)
            return fw

        # Phase 5: no match
        fw = Firmware.UNKNOWN
        _update_cache(fw, port)
        return fw

    except _pyserial.SerialException:
        return Firmware.UNKNOWN
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def _update_cache(fw, port):
    """Store a detection result in the module cache."""
    _cache["firmware"] = fw
    _cache["port"] = port
    _cache["timestamp"] = time.time()


# ── Board variant heuristics ───────────────────────────────────────
#
# detect() answers "what firmware is currently running" — this answers
# "which build of WatchDogs firmware should we install on this chip".
# Same serial port, different question.  Returns a variant id that
# matches a row in esp32_flash._WATCHDOGS_VARIANTS, or None when we
# aren't confident enough to pick.
#
# Strategy (ordered, first hit wins):
#   1. If MARAUDER is currently running, parse its `info` output for
#      the HARDWARE_NAME string — it already tells us the board.
#   2. Fall back to esptool's chip detection via chip_id / flash_id.
#   3. Give up and return None so the picker shows the default.

_HARDWARE_NAME_TO_VARIANT = {
    "uConsole AIO ESP32-S3": "uconsole-aio-s3",
    "uConsole AIO ESP32-C5": "uconsole-aio-c5",
    # Add rows here as more boards get variants in esp32_flash.
}

_CHIP_TO_VARIANT = {
    # Fallback when the firmware didn't identify itself.  Only useful
    # when there's a single plausible board for a given chip family.
    "ESP32-S3": "uconsole-aio-s3",
    "ESP32-C5": "uconsole-aio-c5",
}


def detect_board_variant(port=None, timeout=2.0):
    """Best-effort guess at which WatchDogs board variant this chip is.

    Parameters
    ----------
    port : str or None
        Serial port.  Auto-detected if None.
    timeout : float
        Serial read timeout in seconds.

    Returns
    -------
    str or None
        Variant id (e.g. ``"uconsole-aio-s3"``) or None when uncertain.
    """
    port = port or get_port()
    if port is None:
        return None

    # Step 1 — ask the running firmware.  Only useful if Marauder-like
    # firmware is active; MicroPython / unknown boot won't match.
    name = _read_hardware_name(port, timeout)
    if name:
        for needle, variant in _HARDWARE_NAME_TO_VARIANT.items():
            if needle.lower() in name.lower():
                return variant

    # Step 2 — esptool chip identification.  Works regardless of fw
    # state because esptool resets into bootloader.
    chip = _read_chip_type(port)
    if chip:
        return _CHIP_TO_VARIANT.get(chip)

    return None


def _read_hardware_name(port, timeout):
    """Return the HARDWARE_NAME line from an `info` response, if any."""
    try:
        import serial as _pyserial
    except ImportError:
        return None
    try:
        ser = _pyserial.Serial(port, 115200, timeout=timeout)
    except _pyserial.SerialException:
        return None
    try:
        ser.reset_input_buffer()
        ser.write(b"\r\n")
        time.sleep(0.2)
        ser.read(ser.in_waiting or 1024)  # drain
        ser.write(b"info\r\n")
        time.sleep(1.2)
        raw = ser.read(ser.in_waiting or 4096)
    finally:
        try:
            ser.close()
        except Exception:
            pass
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        # Marauder prints `Hardware: uConsole AIO ESP32-S3`
        low = line.lower()
        if "hardware" in low and ":" in line:
            return line.split(":", 1)[1].strip()
    return None


def _read_chip_type(port):
    """Return a short chip-family string via esptool, or None."""
    try:
        result = subprocess.run(
            ["esptool.py", "--port", port, "chip_id"],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "Chip is" in line:
            after = line.split("Chip is", 1)[1].strip()
            return after.split()[0]
        if "Chip type:" in line:
            after = line.split("Chip type:", 1)[1].strip()
            return after.split()[0]  # "ESP32-S3"
    return None


def read_flash_size(port=None):
    """Return the chip's total flash size in bytes, or None on failure.

    Shells out to ``esptool flash_id`` and parses the "Detected flash
    size: 8MB" line.  Used by the Backup FW action so we dump the
    actual chip size instead of guessing 4MB/8MB/16MB by trial and
    error.
    """
    port = port or get_port()
    if port is None:
        return None
    try:
        result = subprocess.run(
            ["esptool.py", "--port", port, "flash_id"],
            capture_output=True, text=True, timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    units = {"KB": 1024, "MB": 1024 * 1024, "GB": 1024 * 1024 * 1024}
    for line in result.stdout.splitlines():
        low = line.lower()
        if "detected flash size" not in low:
            continue
        # "Detected flash size: 8MB"
        value = line.split(":", 1)[1].strip()
        for suffix, mult in units.items():
            if value.upper().endswith(suffix):
                try:
                    n = int(value[: -len(suffix)].strip())
                except ValueError:
                    return None
                return n * mult
    return None
