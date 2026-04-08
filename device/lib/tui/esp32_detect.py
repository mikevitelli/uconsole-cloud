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
