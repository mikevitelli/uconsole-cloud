"""ESP32 firmware detection handshake.

Probes the serial port (/dev/esp32 or /dev/ttyUSB0) to detect whether
the connected ESP32 is running MicroPython or Marauder firmware.

Results are cached for 30 seconds to avoid repeated handshakes.
"""

import enum
import os
import re
import subprocess
import time

# ── Pyserial loader ─────────────────────────────────────────────────
#
# Module-level slot rather than a per-call import so tests can swap in
# a fake via monkeypatch.setattr.  The first real call hits
# _serial_module() which imports lazily — keeps the module loadable
# on hosts without pyserial installed (e.g. CI matrix workers).

_pyserial = None


def _serial_module():
    """Return the pyserial module, importing on first use.

    Raises ImportError to the caller if pyserial isn't available.
    """
    global _pyserial
    if _pyserial is None:
        import serial as _mod
        _pyserial = _mod
    return _pyserial


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


# ── Quiet open ──────────────────────────────────────────────────────
#
# Default Serial(...) constructor opens with DTR=True, RTS=True, which
# the ESP32-S3 USB-Serial/JTAG peripheral interprets as a reset.  S3
# silicon has no firmware-side disable for this (CHIP_RST_DIS only
# exists on C6/H2).  Workaround: construct empty, set dtr/rts False as
# properties, then open().  See pyserial issue #124.


def _open_quiet(port, timeout):
    """Open *port* at 115200 8N1 without pulsing DTR/RTS.

    Returns the open Serial object.  Caller owns close() — prefer
    _close_fast() over a bare close() when the device might be hung.
    """
    pyserial = _serial_module()
    ser = pyserial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = timeout
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def _close_fast(ser):
    """Close *ser* without waiting for kernel TX buffer to drain.

    pyserial's Serial.close() calls tcdrain() to wait for outgoing
    bytes to flush to the device.  When the device is hung (e.g.
    ESP32 in a boot loop), tcdrain blocks forever.  This helper
    discards both kernel buffers first via tcflush(), then closes.
    Falls back to a raw fd close if pyserial's close still blocks.
    """
    if ser is None:
        return
    try:
        ser.reset_output_buffer()
    except Exception:
        pass
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    try:
        ser.close()
    except Exception:
        # Last resort: bypass pyserial entirely
        try:
            import os as _os
            fd = ser.fd if hasattr(ser, "fd") else ser.fileno()
            _os.close(fd)
        except Exception:
            pass


def _disable_hupcl(port):
    """Run `stty -F <port> -hupcl` to suppress close-time DTR drop.

    Without this, every Serial.close() drops DTR which on next open
    re-arms the chip reset, undoing _open_quiet().  Best-effort: any
    failure (missing stty, permissions, timeout) is swallowed because
    Layer A still helps without -hupcl.
    """
    try:
        subprocess.run(
            ["stty", "-F", port, "-hupcl"],
            capture_output=True, timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass


# ── Passive identification ──────────────────────────────────────────
#
# A chip that just reset is loudly self-identifying — ESP-IDF prints
# "boot:" lines, the application prints its banner, MicroPython prints
# ">>> ", etc.  Match against the first ~2s of unsolicited output
# before we send any bytes.  This is the typical-case fast path AND
# the safety net for chips that aren't ready to accept writes yet.
#
# Order matters: more specific patterns first so e.g. a MimiClaw boot
# log that mentions "Marauder" inside a wifi scan result still matches
# MIMICLAW.

_BOOT_PATTERNS = (
    (re.compile(rb"mimi>"),                    Firmware.MIMICLAW),
    (re.compile(rb"MicroPython"),              Firmware.MICROPYTHON),
    (re.compile(rb">>> "),                     Firmware.MICROPYTHON),
    (re.compile(rb"Marauder", re.IGNORECASE),  Firmware.MARAUDER),
    (re.compile(rb"Bruce",    re.IGNORECASE),  Firmware.BRUCE),
)


def _passive_identify(ser, max_total=2.0, silence=0.30):
    """Read up to *max_total* seconds and return matched Firmware or None.

    Returns the first matching pattern from the boot-log buffer, or
    None if either (a) *silence* seconds pass with no new bytes, or
    (b) *max_total* seconds elapse.  Polls in_waiting every 20 ms so a
    fast match returns quickly.

    Does not write anything to *ser*.  Caller owns ser.close().
    """
    deadline = time.monotonic() + max_total
    last_recv = time.monotonic()
    buf = bytearray()
    while True:
        now = time.monotonic()
        if now >= deadline:
            return None
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            last_recv = now
            for pattern, fw in _BOOT_PATTERNS:
                if pattern.search(buf):
                    return fw
        elif now - last_recv >= silence:
            return None
        else:
            time.sleep(0.02)


# ── Detection ───────────────────────────────────────────────────────
#
# Flow:
#   1. Resolve port; honor cache for hits.
#   2. stty -hupcl on the port so subsequent close()/open() cycles
#      don't re-arm the chip reset.
#   3. Open with _open_quiet (DTR/RTS False before open()).
#   4. Passive probe — read the boot log, match identifiers without
#      writing.  Typical case returns here in <1.5s.
#   5. If passive yields nothing, run a bounded active probe with a
#      hard wall-clock deadline.  Per-call write_timeout protects us
#      from a hung TX endpoint.
#   6. UNKNOWN results are NOT cached, so a transient failure doesn't
#      pin a 30s window of misery.

def detect(port=None, timeout=2.0, force=None):
    """Detect which firmware the ESP32 is running.

    Parameters
    ----------
    port : str or None
        Serial device path.  Defaults to the first available port.
    timeout : float
        Per-phase read timeout in seconds.  The overall wall-clock
        deadline is ``max(5.0, timeout * 2.5)``.
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

    now = time.time()
    if (_cache["firmware"] is not None
            and _cache["port"] == port
            and (now - _cache["timestamp"]) < _CACHE_TTL):
        return _cache["firmware"]

    try:
        pyserial = _serial_module()
    except ImportError:
        return Firmware.UNKNOWN

    overall_deadline = time.monotonic() + max(5.0, timeout * 2.5)

    _disable_hupcl(port)

    ser = None
    try:
        try:
            ser = _open_quiet(port, timeout=timeout)
        except pyserial.SerialException:
            if release_gpsd(port) and time.monotonic() < overall_deadline:
                try:
                    ser = _open_quiet(port, timeout=timeout)
                except pyserial.SerialException:
                    return Firmware.UNKNOWN
            else:
                return Firmware.UNKNOWN

        # Layer C: passive ID from boot log.
        passive_budget = max(0.1, min(2.0, overall_deadline - time.monotonic()))
        fw = _passive_identify(ser, max_total=passive_budget, silence=0.30)
        if fw is not None:
            _update_cache(fw, port)
            return fw

        # Layer D: bounded active probe.  Defends against per-call hangs
        # via a short write_timeout and the overall deadline.
        try:
            ser.write_timeout = 0.5
        except Exception:
            pass

        fw = _active_probe(ser, overall_deadline)
        if fw != Firmware.UNKNOWN:
            _update_cache(fw, port)
        return fw

    except pyserial.SerialException:
        return Firmware.UNKNOWN
    except getattr(pyserial, "SerialTimeoutException", Exception):
        return Firmware.UNKNOWN
    finally:
        _close_fast(ser)


def _active_probe(ser, deadline):
    """Send wake + info; return Firmware or UNKNOWN, never raising past
    *deadline*.

    Each write/read pair is short and bounded; we re-check the deadline
    between phases so a slow chip can't push us past the budget.
    """
    pyserial = _serial_module()
    SerialTimeoutException = getattr(
        pyserial, "SerialTimeoutException", Exception,
    )

    def time_left():
        return deadline - time.monotonic()

    try:
        if time_left() <= 0:
            return Firmware.UNKNOWN

        # Phase 1: MicroPython interrupt + Marauder wake
        ser.reset_input_buffer()
        try:
            ser.write(b"\x03\x03\r\n")
        except SerialTimeoutException:
            return Firmware.UNKNOWN
        time.sleep(min(0.4, max(0.1, time_left())))
        raw = ser.read(ser.in_waiting or 1024)
        resp = raw.decode("utf-8", errors="replace")
        if ">>>" in resp or "MicroPython" in resp:
            return Firmware.MICROPYTHON
        if "mimi>" in resp:
            return Firmware.MIMICLAW
        if "Marauder" in resp:
            return Firmware.MARAUDER

        if time_left() <= 0:
            return Firmware.UNKNOWN

        # Phase 2: Marauder `info` query
        ser.reset_input_buffer()
        try:
            ser.write(b"\r\n")
        except SerialTimeoutException:
            return Firmware.UNKNOWN
        time.sleep(min(0.2, max(0.05, time_left())))
        ser.read(ser.in_waiting or 1024)
        try:
            ser.write(b"info\r\n")
        except SerialTimeoutException:
            return Firmware.UNKNOWN
        time.sleep(min(1.0, max(0.1, time_left())))
        raw2 = ser.read(ser.in_waiting or 4096)
        resp2 = raw2.decode("utf-8", errors="replace")

        if "Marauder" in resp2 or "Firmware" in resp2:
            return Firmware.MARAUDER
        if "mimi>" in resp2:
            return Firmware.MIMICLAW

        return Firmware.UNKNOWN
    except pyserial.SerialException:
        return Firmware.UNKNOWN


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
        pyserial = _serial_module()
    except ImportError:
        return None
    try:
        ser = _open_quiet(port, timeout=timeout)
    except pyserial.SerialException:
        return None
    try:
        try:
            ser.write_timeout = 0.5
        except Exception:
            pass
        ser.reset_input_buffer()
        try:
            ser.write(b"\r\n")
        except getattr(pyserial, "SerialTimeoutException", Exception):
            return None
        time.sleep(0.2)
        ser.read(ser.in_waiting or 1024)  # drain
        try:
            ser.write(b"info\r\n")
        except getattr(pyserial, "SerialTimeoutException", Exception):
            return None
        time.sleep(1.2)
        raw = ser.read(ser.in_waiting or 4096)
    finally:
        _close_fast(ser)
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
