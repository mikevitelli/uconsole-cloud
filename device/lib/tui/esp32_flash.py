"""ESP32 firmware flash/reflash with safety gates.

Supports flashing both MicroPython and Marauder firmware to the ESP32
on the uConsole AIO board.  Includes battery-level checks, chip-id
validation, gpsd release/restore, and progress callbacks.
"""

import glob
import hashlib
import os
import subprocess
import time

from tui.esp32_detect import (
    Firmware,
    battery_ok,
    get_port,
    invalidate_cache,
    read_flash_size,
    release_gpsd,
)

# ── Firmware binary paths ──────────────────────────────────────────

_MARAUDER_DIR = os.path.expanduser("~/marauder")
_MARAUDER_S3_DIR = os.path.join(_MARAUDER_DIR, "s3")
_MICROPYTHON_DIR = os.path.expanduser("~/esp32")
_WATCHDOGS_DIR = os.path.expanduser("~/watchdogs-fw")

_MICROPYTHON_BIN = os.path.join(_MICROPYTHON_DIR, "micropython.bin")

# Marauder flash layout (app-only update at 0x10000)
_MARAUDER_OFFSET = "0x10000"

# Full flash from scratch — ESP32 original (bootloader at 0x1000)
_MARAUDER_FULL_LAYOUT = [
    ("0x1000", "esp32_marauder.ino.bootloader.bin"),
    ("0x8000", "esp32_marauder.ino.partitions.bin"),
    ("0xe000", "boot_app0.bin"),
    ("0x10000", None),  # filled dynamically with latest firmware bin
]

# Full flash from scratch — ESP32-S3 (bootloader at 0x0)
_MARAUDER_S3_FULL_LAYOUT = [
    ("0x0", "esp32_marauder.ino.bootloader.bin"),
    ("0x8000", "esp32_marauder.ino.partitions.bin"),
    ("0xe000", "boot_app0.bin"),
    ("0x10000", None),  # filled dynamically with latest firmware bin
]

_BACKUP_BIN = os.path.expanduser("~/esp32-backup.bin")

# Minimum battery to allow flash
_MIN_BATTERY_PCT = 20

# ── WatchDogs firmware distribution ────────────────────────────────
#
# Firmware binaries aren't bundled in the .deb — they're fetched on
# demand from a GitHub release the first time a user picks a variant
# that isn't already cached in ~/watchdogs-fw/.  One cache dir, one
# registry of variants, one download helper.

_WATCHDOGS_REPO = os.environ.get(
    "WDG_FW_REPO", "mikevitelli/uconsole-watchdogs-fw")
_WATCHDOGS_TAG = os.environ.get("WDG_FW_TAG", "latest")

# Variant registry.  Each entry is:
#   id: (display name, release asset filename, chip family)
#
# ``chip family`` matches the short chip string returned by
# ``esp32_detect._read_chip_type`` (e.g. "ESP32-S3", "ESP32-C5").
# Adding a new row is the only change needed to register a board —
# the TUI picker, the downloader, and the auto-detect all derive
# their behavior from this dict.
_WATCHDOGS_VARIANTS = {
    "uconsole-aio-s3": (
        "uConsole AIO ESP32-S3",
        "watchdogs-uconsole-aio-s3.bin",
        "ESP32-S3",
    ),
    "uconsole-aio-c5": (
        "uConsole AIO ESP32-C5",
        "watchdogs-uconsole-aio-c5.bin",
        "ESP32-C5",
    ),
    "esp32-s3-devkitc-1": (
        "ESP32-S3 DevKitC-1 (generic)",
        "watchdogs-esp32-s3-devkitc-1.bin",
        "ESP32-S3",
    ),
}

# Default variant when detection hasn't narrowed it down.  The hub
# can override by passing an explicit variant to preflight().
_WATCHDOGS_DEFAULT_VARIANT = "uconsole-aio-s3"


# ── Helpers ────────────────────────────────────────────────────────

class FlashError(Exception):
    """Raised when a flash operation fails."""


def find_marauder_bin():
    """Return the path to the latest Marauder firmware .bin, or None.

    Checks the S3 custom build directory first (~/marauder/s3/build/),
    then falls back to prebuilt binaries in ~/marauder/.
    """
    # S3 custom HWCDC build
    s3_bin = os.path.join(_MARAUDER_S3_DIR, "build", "esp32_marauder.ino.bin")
    if os.path.isfile(s3_bin):
        return s3_bin
    # Prebuilt LDDB binaries
    pattern = os.path.join(_MARAUDER_DIR, "esp32_marauder_v*_esp32_lddb.bin")
    bins = sorted(glob.glob(pattern))
    return bins[-1] if bins else None


def find_micropython_bin():
    """Return the path to the MicroPython firmware .bin, or None."""
    if os.path.isfile(_MICROPYTHON_BIN):
        return _MICROPYTHON_BIN
    return None


def list_watchdogs_variants(chip=None):
    """Return registered WatchDogs firmware variants.

    Parameters
    ----------
    chip : str or None
        If given (e.g. ``"ESP32-S3"``), only return variants whose
        chip family matches.  ``None`` returns all variants.

    Returns
    -------
    list of (variant_id, display_name) tuples
        In insertion order — the first entry is the default/highlighted
        choice in the TUI picker.
    """
    out = []
    for vid, (disp, _asset, cfam) in _WATCHDOGS_VARIANTS.items():
        if chip is not None and cfam != chip:
            continue
        out.append((vid, disp))
    return out


def _watchdogs_cache_path(variant):
    """Return the local path a given variant would be cached at."""
    info = _WATCHDOGS_VARIANTS.get(variant)
    if info is None:
        raise FlashError(f"Unknown WatchDogs variant: {variant}")
    return os.path.join(_WATCHDOGS_DIR, info[1])


def find_watchdogs_bin(variant=None):
    """Return the path to a cached WatchDogs firmware .bin, or None.

    Parameters
    ----------
    variant : str or None
        Variant id (see ``list_watchdogs_variants``).  If None, returns
        the first variant that happens to be cached, or falls back to
        a generic ``esp32_watchdogs.bin``/``esp32_watchdogs_v*.bin``
        drop-in name.
    """
    if variant is not None:
        path = _watchdogs_cache_path(variant)
        return path if os.path.isfile(path) else None

    # No variant specified — check the registry in order, then legacy
    # drop-in names (so sideloading still works).
    for vid, (_disp, asset, _cfam) in _WATCHDOGS_VARIANTS.items():
        path = os.path.join(_WATCHDOGS_DIR, asset)
        if os.path.isfile(path):
            return path
    single = os.path.join(_WATCHDOGS_DIR, "esp32_watchdogs.bin")
    if os.path.isfile(single):
        return single
    pattern = os.path.join(_WATCHDOGS_DIR, "esp32_watchdogs_v*.bin")
    bins = sorted(glob.glob(pattern))
    return bins[-1] if bins else None


class FetchCancelled(FlashError):
    """Raised when the download is cancelled via the cancel_event."""


_FETCH_RETRIES = 3
_FETCH_BACKOFF = (1.0, 2.0, 4.0)  # seconds between attempts


def fetch_watchdogs_bin(variant, tag=None, on_progress=None,
                        cancel_event=None):
    """Download a WatchDogs firmware variant from GitHub Releases.

    Streams straight to disk to keep RAM usage flat.  Retries transient
    network errors up to 3× with exponential backoff.  Can be cancelled
    mid-download by setting ``cancel_event`` from another thread; the
    partial file is cleaned up and ``FetchCancelled`` is raised.

    Parameters
    ----------
    variant : str
        Variant id from ``_WATCHDOGS_VARIANTS``.
    tag : str or None
        Release tag.  Defaults to ``_WATCHDOGS_TAG`` (``latest``).
    on_progress : callable or None
        Called as ``on_progress(bytes_done, total_bytes_or_None)``.
    cancel_event : threading.Event or None
        If set while the download is in flight, the download aborts.

    Returns
    -------
    str
        Path to the downloaded .bin.

    Raises
    ------
    FetchCancelled
        If ``cancel_event`` was set during the download.
    FlashError
        On any other network / HTTP / IO failure.  Caller should fall
        back to ``find_watchdogs_bin()`` for a sideloaded file.
    """
    info = _WATCHDOGS_VARIANTS.get(variant)
    if info is None:
        raise FlashError(f"Unknown WatchDogs variant: {variant}")
    _disp, asset = info[0], info[1]
    tag = tag or _WATCHDOGS_TAG

    if tag == "latest":
        url = (f"https://github.com/{_WATCHDOGS_REPO}"
               f"/releases/latest/download/{asset}")
    else:
        url = (f"https://github.com/{_WATCHDOGS_REPO}"
               f"/releases/download/{tag}/{asset}")

    os.makedirs(_WATCHDOGS_DIR, exist_ok=True)
    dest = os.path.join(_WATCHDOGS_DIR, asset)
    tmp = dest + ".part"

    last_err = None
    for attempt in range(_FETCH_RETRIES):
        if cancel_event is not None and cancel_event.is_set():
            _safe_unlink(tmp)
            raise FetchCancelled("Download cancelled")
        try:
            _download_stream(url, tmp, on_progress, cancel_event)
            break
        except FetchCancelled:
            _safe_unlink(tmp)
            raise
        except FlashError as exc:
            last_err = exc
            # 4xx (other than 408/429) shouldn't be retried — missing
            # asset isn't going to appear if we try again.
            if "Download failed (4" in str(exc) and \
                    "408" not in str(exc) and "429" not in str(exc):
                _safe_unlink(tmp)
                raise
            if attempt == _FETCH_RETRIES - 1:
                _safe_unlink(tmp)
                raise
            delay = _FETCH_BACKOFF[min(attempt, len(_FETCH_BACKOFF) - 1)]
            # Sleep in small slices so cancellation stays responsive.
            slept = 0.0
            while slept < delay:
                if cancel_event is not None and cancel_event.is_set():
                    _safe_unlink(tmp)
                    raise FetchCancelled("Download cancelled")
                time.sleep(0.1)
                slept += 0.1
    else:
        _safe_unlink(tmp)
        raise last_err or FlashError("Download failed")

    os.replace(tmp, dest)

    # Verify against SHASUMS256.txt from the same release, if present.
    # A missing sums file is tolerated (prints a warning); a mismatch
    # deletes the download and raises.
    try:
        _verify_watchdogs_sha256(tag, asset, dest)
    except FlashError:
        _safe_unlink(dest)
        raise

    return dest


def _download_stream(url, tmp, on_progress, cancel_event):
    """Stream *url* into *tmp*, reporting progress and honoring cancel.

    Raised exceptions normalised to ``FlashError`` / ``FetchCancelled``
    so the retry loop has one error model to handle.
    """
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        url, headers={"User-Agent": "uconsole-tui"})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        raise FlashError(
            f"Download failed ({exc.code}) for {url}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FlashError(f"Network error: {exc}")

    try:
        total = resp.getheader("Content-Length")
        total = int(total) if total and total.isdigit() else None
        done = 0
        chunk = 64 * 1024
        with open(tmp, "wb") as f:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise FetchCancelled("Download cancelled")
                try:
                    buf = resp.read(chunk)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    raise FlashError(f"Read error mid-stream: {exc}")
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if on_progress:
                    on_progress(done, total)
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _verify_watchdogs_sha256(tag, asset, path):
    """Check *path* against the SHASUMS256.txt manifest for *tag*.

    Silently returns if the manifest is missing from the release — a
    release that doesn't publish sums is treated as "integrity is the
    publisher's problem" rather than a hard failure.  Any positive
    mismatch raises FlashError.
    """
    import urllib.request
    import urllib.error

    if tag == "latest":
        sums_url = (f"https://github.com/{_WATCHDOGS_REPO}"
                    f"/releases/latest/download/SHASUMS256.txt")
    else:
        sums_url = (f"https://github.com/{_WATCHDOGS_REPO}"
                    f"/releases/download/{tag}/SHASUMS256.txt")
    try:
        req = urllib.request.Request(
            sums_url, headers={"User-Agent": "uconsole-tui"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            manifest = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return  # No sums file published — tolerate.
        raise FlashError(f"Couldn't fetch SHASUMS256.txt ({exc.code})")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FlashError(f"Network error fetching SHASUMS256.txt: {exc}")

    expected = None
    for line in manifest.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == asset:
            expected = parts[0].lower()
            break
    if expected is None:
        return  # Sums file didn't list this asset — tolerate.

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise FlashError(
            f"SHA-256 mismatch for {asset}: "
            f"expected {expected[:16]}…, got {actual[:16]}…"
        )


def _safe_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def clear_watchdogs_cache():
    """Delete every cached WatchDogs firmware binary.

    Returns the list of removed paths.  Never raises — files that
    can't be deleted are silently skipped.
    """
    removed = []
    if not os.path.isdir(_WATCHDOGS_DIR):
        return removed
    for name in os.listdir(_WATCHDOGS_DIR):
        if not name.endswith(".bin"):
            continue
        path = os.path.join(_WATCHDOGS_DIR, name)
        try:
            os.unlink(path)
            removed.append(path)
        except OSError:
            pass
    return removed


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
        elif "Chip type:" in line:
            chip_type = line.split("Chip type:")[-1].strip()
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

def preflight(port=None, target=None, variant=None, on_fetch_progress=None,
              cancel_event=None):
    """Run all safety checks before flashing.

    Parameters
    ----------
    port : str or None
        Serial port path.
    target : Firmware
        Which firmware we intend to flash.
    variant : str or None
        For ``Firmware.BRUCE``, the board variant id.  Ignored for
        other targets.  Defaults to ``_WATCHDOGS_DEFAULT_VARIANT``.
    on_fetch_progress : callable or None
        Progress callback for the on-demand WatchDogs download.

    Returns
    -------
    dict
        Keys: port, chip_type, mac, binary, target, variant.

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
    elif target == Firmware.BRUCE:
        wd_variant = variant or _WATCHDOGS_DEFAULT_VARIANT
        binary = find_watchdogs_bin(wd_variant)
        if binary is None:
            # Not cached yet — fetch from the release mirror.
            try:
                binary = fetch_watchdogs_bin(
                    wd_variant, on_progress=on_fetch_progress,
                    cancel_event=cancel_event)
            except FetchCancelled:
                raise
            except FlashError as exc:
                # Fall back to any sideloaded drop-in file before giving up.
                fallback = find_watchdogs_bin()
                if fallback is None:
                    raise FlashError(
                        f"{exc} "
                        f"(you can drop a .bin in {_WATCHDOGS_DIR} manually)"
                    )
                binary = fallback
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
        "variant": variant if target == Firmware.BRUCE else None,
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


def flash_watchdogs(port, binary, on_output=None):
    """Flash WatchDogs (Bruce + WDGWars) firmware.

    Bruce release binaries are merged images (bootloader + partitions +
    app in one file) that get written at 0x0, not app-only.  If the
    binary is smaller than 1 MB we treat it as app-only and fall back
    to the Marauder 0x10000 offset.
    """
    size = os.path.getsize(binary)
    offset = _MARAUDER_OFFSET if size < 1_000_000 else "0x0"
    cmd = [
        "esptool.py", "--port", port, "--baud", "460800",
        "write_flash", offset, binary,
    ]
    _run_flash(cmd, on_output)


def backup_flash(port=None, dest=None, on_output=None):
    """Dump the current ESP32 flash to a local .bin file.

    Parameters
    ----------
    port : str or None
        Serial device path (auto-detected if None).
    dest : str or None
        Output path. Defaults to ``~/esp32-backup-<timestamp>.bin``.
    on_output : callable or None
        Progress callback (receives each esptool output line).

    Returns
    -------
    str
        Path to the written backup file.

    Raises
    ------
    FlashError
        If no port found or esptool fails.
    """
    port = port or get_port()
    if port is None:
        raise FlashError("No ESP32 serial port found")

    release_gpsd(port)

    if dest is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        dest = os.path.expanduser(f"~/esp32-backup-{ts}.bin")

    # Ask the chip how big its flash actually is so we don't under- or
    # over-read.  Falls back to a downward sweep if detection fails.
    size_bytes = read_flash_size(port)
    if size_bytes:
        sizes = [f"0x{size_bytes:x}"]
    else:
        sizes = ["0x1000000", "0x800000", "0x400000", "0x200000"]  # 16/8/4/2MB

    last_err = None
    for size in sizes:
        cmd = [
            "esptool.py", "--port", port, "--baud", "460800",
            "read_flash", "0x0", size, dest,
        ]
        try:
            _run_flash(cmd, on_output)
            return dest
        except FlashError as exc:
            last_err = exc
            continue
    raise FlashError(
        f"read_flash failed at every candidate size: {last_err}"
    )


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


def flash(target, port=None, on_output=None, variant=None,
          on_fetch_progress=None, cancel_event=None):
    """Full flash workflow: preflight → flash → invalidate cache.

    Parameters
    ----------
    target : Firmware
        MICROPYTHON, MARAUDER, or WATCHDOGS.
    port : str or None
        Serial device path (auto-detected if None).
    on_output : callable or None
        Progress callback (receives each esptool output line).
    variant : str or None
        For ``Firmware.BRUCE``, which board variant to install.
        Ignored for other targets.
    on_fetch_progress : callable or None
        Download-progress callback used only for on-demand WatchDogs
        firmware fetches.

    Returns
    -------
    dict
        Preflight info dict (port, chip_type, mac, binary, target, variant).

    Raises
    ------
    FlashError
        On any failure.
    """
    info = preflight(port=port, target=target, variant=variant,
                     on_fetch_progress=on_fetch_progress,
                     cancel_event=cancel_event)

    if target == Firmware.MARAUDER:
        flash_marauder(info["port"], info["binary"], on_output)
    elif target == Firmware.MICROPYTHON:
        flash_micropython(info["port"], info["binary"], on_output)
    elif target == Firmware.BRUCE:
        flash_watchdogs(info["port"], info["binary"], on_output)

    # Invalidate detection cache so next detect() re-probes
    invalidate_cache()

    return info
