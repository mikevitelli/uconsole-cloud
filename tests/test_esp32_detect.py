"""Tests for tui.esp32_detect.

Covers the four-layer fix for the indefinite-hang bug:
  A. _open_quiet — open serial without pulsing DTR/RTS
  B. _disable_hupcl — stty -hupcl on the tty
  C. _passive_identify — match firmware from boot-log without writing
  D. detect() wall-clock cap and UNKNOWN cache semantics
"""

import time
import types
from unittest.mock import MagicMock, patch

import pytest

# conftest.py adds device/lib to sys.path
from tui import esp32_detect
from tui.esp32_detect import Firmware


# ── Shared fakes ──────────────────────────────────────────────────────


class FakeSerial:
    """Minimal pyserial.Serial stand-in.

    Records the order of property assignments and method calls so tests
    can assert that dtr/rts were set BEFORE open().  Supports a scripted
    rx_chunks queue read out by `read()` / `in_waiting`.
    """

    def __init__(self, rx_chunks=None, write_blocks=False):
        self.events = []  # ordered list of (op, value) tuples
        self._port = None
        self._baudrate = None
        self._timeout = None
        self._write_timeout = None
        self._dtr = True   # pyserial default
        self._rts = True   # pyserial default
        self.is_open = False
        self._rx = list(rx_chunks or [])
        self._cursor = 0
        self.writes = []
        self._write_blocks = write_blocks

    # ── properties ────────────────────────────────────────────────
    @property
    def port(self): return self._port
    @port.setter
    def port(self, v):
        self._port = v
        self.events.append(("port", v))

    @property
    def baudrate(self): return self._baudrate
    @baudrate.setter
    def baudrate(self, v):
        self._baudrate = v
        self.events.append(("baudrate", v))

    @property
    def timeout(self): return self._timeout
    @timeout.setter
    def timeout(self, v):
        self._timeout = v
        self.events.append(("timeout", v))

    @property
    def write_timeout(self): return self._write_timeout
    @write_timeout.setter
    def write_timeout(self, v):
        self._write_timeout = v
        self.events.append(("write_timeout", v))

    @property
    def dtr(self): return self._dtr
    @dtr.setter
    def dtr(self, v):
        self._dtr = v
        self.events.append(("dtr", v))

    @property
    def rts(self): return self._rts
    @rts.setter
    def rts(self, v):
        self._rts = v
        self.events.append(("rts", v))

    @property
    def in_waiting(self):
        if self._cursor >= len(self._rx):
            return 0
        return len(self._rx[self._cursor])

    # ── methods ──────────────────────────────────────────────────
    def open(self):
        self.is_open = True
        self.events.append(("open", None))

    def close(self):
        self.is_open = False
        self.events.append(("close", None))

    def reset_input_buffer(self):
        self.events.append(("reset_input_buffer", None))

    def write(self, data):
        if self._write_blocks:
            # Real pyserial: when write_timeout is set, write() raises
            # SerialTimeoutException after that long if the OS can't
            # accept the bytes.  We model that here so detect()'s
            # write_timeout=0.5 actually fires.
            if self._write_timeout is not None:
                time.sleep(self._write_timeout)
                # Use the patched module's exception so detect's except clause matches
                exc_cls = getattr(esp32_detect._pyserial,
                                  "SerialTimeoutException", Exception)
                raise exc_cls("simulated kernel TX hang")
            time.sleep(10)  # legacy: blocks the test
        self.writes.append(data)
        self.events.append(("write", data))
        return len(data)

    def flush(self):
        self.events.append(("flush", None))

    def read(self, n=1):
        # Pop the next chunk, ignoring n (simplification — tests pass
        # in_waiting-shaped chunks)
        if self._cursor >= len(self._rx):
            return b""
        chunk = self._rx[self._cursor]
        self._cursor += 1
        return chunk


@pytest.fixture(autouse=True)
def _clear_cache():
    """Detection cache leaks between tests; nuke it."""
    esp32_detect.invalidate_cache()
    yield
    esp32_detect.invalidate_cache()


# ── Layer A: _open_quiet ──────────────────────────────────────────────


class TestOpenQuiet:
    """`_open_quiet` opens a serial port without pulsing DTR/RTS.

    Pyserial's default `Serial(port, baud, timeout=t)` constructor opens
    immediately with DTR=True, RTS=True, which on ESP32-S3 USB-Serial/JTAG
    triggers a chip reset.  The fix is to construct empty, set dtr/rts
    to False as properties, then call `open()`.  Verified by issue
    https://github.com/pyserial/pyserial/issues/124.
    """

    def test_sets_dtr_false_before_open(self, monkeypatch):
        fake = FakeSerial()
        # Patch the module's serial.Serial class so detect uses our fake
        fake_serial_module = types.SimpleNamespace(
            Serial=lambda: fake,
            SerialException=Exception,
            SerialTimeoutException=Exception,
        )
        monkeypatch.setattr(esp32_detect, "_pyserial", fake_serial_module, raising=False)

        esp32_detect._open_quiet("/dev/esp32", timeout=1.0)

        # Find the index of the dtr=False event and the open event
        ops = [e[0] for e in fake.events]
        assert "dtr" in ops, "dtr property never set"
        assert "open" in ops, "open() never called"
        assert ops.index("dtr") < ops.index("open"), \
            f"dtr must be set BEFORE open(); got order {ops}"
        # And the value set must be False (not True)
        dtr_event = next(e for e in fake.events if e[0] == "dtr")
        assert dtr_event[1] is False, f"dtr should be False, got {dtr_event[1]}"

    def test_sets_rts_false_before_open(self, monkeypatch):
        fake = FakeSerial()
        fake_serial_module = types.SimpleNamespace(
            Serial=lambda: fake,
            SerialException=Exception,
            SerialTimeoutException=Exception,
        )
        monkeypatch.setattr(esp32_detect, "_pyserial", fake_serial_module, raising=False)

        esp32_detect._open_quiet("/dev/esp32", timeout=1.0)

        ops = [e[0] for e in fake.events]
        assert "rts" in ops
        assert ops.index("rts") < ops.index("open")
        rts_event = next(e for e in fake.events if e[0] == "rts")
        assert rts_event[1] is False

    def test_assigns_port_baudrate_timeout(self, monkeypatch):
        fake = FakeSerial()
        fake_serial_module = types.SimpleNamespace(
            Serial=lambda: fake,
            SerialException=Exception,
            SerialTimeoutException=Exception,
        )
        monkeypatch.setattr(esp32_detect, "_pyserial", fake_serial_module, raising=False)

        esp32_detect._open_quiet("/dev/esp32", timeout=2.5)

        assert fake.port == "/dev/esp32"
        assert fake.baudrate == 115200
        assert fake.timeout == 2.5
        assert fake.is_open is True


# ── Layer B: _disable_hupcl ───────────────────────────────────────────


class TestDisableHupcl:
    """`_disable_hupcl` shells out to `stty -F <port> -hupcl`.

    Without -hupcl, every Serial.close() drops DTR, which on next open
    re-arms the chip reset — defeating Layer A.  Reference:
    https://forum.arduino.cc/t/disable-auto-reset-by-serial-connection/28248
    """

    def test_invokes_stty_with_correct_args(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(esp32_detect.subprocess, "run", fake_run)

        esp32_detect._disable_hupcl("/dev/esp32")

        assert len(calls) == 1, f"expected 1 stty call, got {len(calls)}"
        cmd, kwargs = calls[0]
        assert cmd == ["stty", "-F", "/dev/esp32", "-hupcl"]
        # Must not block forever if stty hangs
        assert kwargs.get("timeout") is not None
        # Don't crash the TUI on stty failure
        assert kwargs.get("capture_output") is True

    def test_swallows_stty_failure(self, monkeypatch):
        """If stty errors out (missing binary, perms), do NOT raise."""
        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("stty not found")

        monkeypatch.setattr(esp32_detect.subprocess, "run", fake_run)

        # Must not raise — Layer A still works without -hupcl
        esp32_detect._disable_hupcl("/dev/esp32")

    def test_swallows_stty_timeout(self, monkeypatch):
        """If stty times out, do NOT raise."""
        def fake_run(cmd, **kwargs):
            raise subprocess_module.TimeoutExpired(cmd, 2)

        import subprocess as subprocess_module
        monkeypatch.setattr(esp32_detect.subprocess, "run", fake_run)

        esp32_detect._disable_hupcl("/dev/esp32")


# ── Layer C: _passive_identify ────────────────────────────────────────


# Real boot-log fragment captured from the AIO ESP32-S3 running
# MimiClaw on 2026-04-24 — used as fixture data.
MIMICLAW_BOOT_LOG = (
    b"entry 0x403c8948\r\n"
    b"I (29) boot: ESP-IDF v5.5.2 2nd stage bootloader\r\n"
    b"I (29) boot: compile time Apr 21 2026 21:15:04\r\n"
    b"I (32) boot: chip revision: v0.2\r\n"
    b"I (45) cpu_start: Project name:     mimiclaw\r\n"
    b"I (50) cpu_start: App version:      v0.4.1\r\n"
    b"I (200) main_task: Started on CPU0\r\n"
    b"\r\nMimiClaw ready.\r\n"
    b"mimi> "
)

MICROPYTHON_PROMPT = b"\r\nMicroPython v1.22.0 on 2026-01-15; ESP32S3 module\r\n>>> "

MARAUDER_BANNER = (
    b"\r\nESP32 Marauder v1.11.0\r\n"
    b"Hardware: uConsole AIO ESP32-S3\r\n"
    b"> "
)


class TestPassiveIdentify:
    """`_passive_identify` reads the boot log without writing.

    Returns the first matching Firmware enum, or None on silence
    window expiry.  Caps total wait at max_total seconds.
    """

    def _make_ser(self, chunks):
        return FakeSerial(rx_chunks=chunks)

    def test_matches_mimiclaw_banner(self, monkeypatch):
        # Speed up: fake monotonic returns ascending values quickly so
        # the silence-window logic still works without real waiting
        ser = self._make_ser([MIMICLAW_BOOT_LOG])
        result = esp32_detect._passive_identify(
            ser, max_total=2.0, silence=0.30,
        )
        assert result == Firmware.MIMICLAW

    def test_matches_micropython_prompt(self, monkeypatch):
        ser = self._make_ser([MICROPYTHON_PROMPT])
        result = esp32_detect._passive_identify(ser, max_total=2.0, silence=0.30)
        assert result == Firmware.MICROPYTHON

    def test_matches_micropython_triple_chevron(self, monkeypatch):
        # Some MicroPython builds drop the banner and show only ">>> "
        ser = self._make_ser([b"junk text\r\n>>> "])
        result = esp32_detect._passive_identify(ser, max_total=2.0, silence=0.30)
        assert result == Firmware.MICROPYTHON

    def test_matches_marauder_banner(self, monkeypatch):
        ser = self._make_ser([MARAUDER_BANNER])
        result = esp32_detect._passive_identify(ser, max_total=2.0, silence=0.30)
        assert result == Firmware.MARAUDER

    def test_returns_none_on_silence(self, monkeypatch):
        """No data + silence window expires → return None within budget."""
        ser = self._make_ser([])  # empty rx
        t0 = time.monotonic()
        result = esp32_detect._passive_identify(ser, max_total=2.0, silence=0.20)
        elapsed = time.monotonic() - t0
        assert result is None
        # Should return within ~silence + small jitter, well under max_total
        assert elapsed < 1.0, f"silence detection took too long: {elapsed:.2f}s"

    def test_returns_none_on_unrelated_data(self, monkeypatch):
        """Garbage bytes that don't match any pattern → None."""
        ser = self._make_ser([b"random hex 0xdeadbeef\r\n"])
        result = esp32_detect._passive_identify(ser, max_total=1.0, silence=0.20)
        assert result is None

    def test_max_total_caps_runtime(self, monkeypatch):
        """If chunks keep dribbling in but no match, cap at max_total."""
        # Stream a slow drip of unmatched bytes
        chunks = [b"."] * 100
        ser = self._make_ser(chunks)
        t0 = time.monotonic()
        result = esp32_detect._passive_identify(ser, max_total=0.5, silence=10.0)
        elapsed = time.monotonic() - t0
        assert result is None
        assert elapsed < 1.0, f"max_total cap not enforced: {elapsed:.2f}s"

    def test_mimi_match_beats_marauder_when_both_present(self, monkeypatch):
        """If two banners overlap (theoretical), match the more specific one first."""
        # MimiClaw output that also contains the substring "Marauder"
        # (e.g. someone names their AP "Marauder") shouldn't mis-route
        # to Marauder when the mimi> prompt is present.
        ser = self._make_ser([MIMICLAW_BOOT_LOG + b"\r\nSSID list: Marauder-net\r\n"])
        result = esp32_detect._passive_identify(ser, max_total=2.0, silence=0.30)
        assert result == Firmware.MIMICLAW


# ── Layer D: detect() integration / wall-clock cap / cache ────────────


class TestDetect:
    """Integration tests for the rewired detect() top-level function."""

    def _patch_pyserial(self, monkeypatch, fake):
        mod = types.SimpleNamespace(
            Serial=lambda: fake,
            SerialException=Exception,
            SerialTimeoutException=Exception,
        )
        monkeypatch.setattr(esp32_detect, "_pyserial", mod, raising=False)

    def _patch_port_exists(self, monkeypatch, port="/dev/esp32"):
        monkeypatch.setattr(
            esp32_detect.os.path, "exists",
            lambda p: p == port,
        )

    def _patch_stty_noop(self, monkeypatch):
        monkeypatch.setattr(
            esp32_detect.subprocess, "run",
            lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""),
        )

    def test_returns_unknown_when_no_port(self, monkeypatch):
        monkeypatch.setattr(esp32_detect.os.path, "exists", lambda p: False)
        assert esp32_detect.detect() == Firmware.UNKNOWN

    def test_returns_force_value_without_probing(self, monkeypatch):
        # If force= is set, no I/O should happen at all
        called = {"opened": False}

        def boom():
            called["opened"] = True
            raise AssertionError("must not open serial when force= is set")

        monkeypatch.setattr(
            esp32_detect, "_pyserial",
            types.SimpleNamespace(Serial=boom, SerialException=Exception,
                                  SerialTimeoutException=Exception),
            raising=False,
        )

        result = esp32_detect.detect(force=Firmware.MIMICLAW)
        assert result == Firmware.MIMICLAW
        assert called["opened"] is False

    def test_passive_path_identifies_mimiclaw(self, monkeypatch):
        """detect() returns the firmware spotted in the passive boot log."""
        self._patch_port_exists(monkeypatch)
        self._patch_stty_noop(monkeypatch)
        fake = FakeSerial(rx_chunks=[MIMICLAW_BOOT_LOG])
        self._patch_pyserial(monkeypatch, fake)

        result = esp32_detect.detect()
        assert result == Firmware.MIMICLAW
        # And no writes were attempted
        assert fake.writes == [], f"unexpected writes: {fake.writes}"

    def test_caches_successful_detection(self, monkeypatch):
        """A successful detect should be cached for the next call."""
        self._patch_port_exists(monkeypatch)
        self._patch_stty_noop(monkeypatch)
        fake = FakeSerial(rx_chunks=[MIMICLAW_BOOT_LOG])
        self._patch_pyserial(monkeypatch, fake)

        first = esp32_detect.detect()
        # Replace fake with one that would error if opened — should
        # not be touched because cache is valid
        broken = FakeSerial(rx_chunks=[])

        def boom():
            raise AssertionError("cache miss — Serial should not be reopened")

        monkeypatch.setattr(
            esp32_detect, "_pyserial",
            types.SimpleNamespace(Serial=boom, SerialException=Exception,
                                  SerialTimeoutException=Exception),
            raising=False,
        )

        second = esp32_detect.detect()
        assert first == second == Firmware.MIMICLAW

    def test_does_not_cache_unknown_from_silence(self, monkeypatch):
        """A null result must not pin the cache — next call retries."""
        self._patch_port_exists(monkeypatch)
        self._patch_stty_noop(monkeypatch)

        # First call: silent serial → UNKNOWN
        fake1 = FakeSerial(rx_chunks=[])
        self._patch_pyserial(monkeypatch, fake1)
        first = esp32_detect.detect(timeout=0.3)
        assert first == Firmware.UNKNOWN

        # Second call: chip woke up, returns mimi banner → MIMICLAW
        fake2 = FakeSerial(rx_chunks=[MIMICLAW_BOOT_LOG])
        self._patch_pyserial(monkeypatch, fake2)
        second = esp32_detect.detect(timeout=0.3)
        assert second == Firmware.MIMICLAW, \
            "UNKNOWN must not be cached or we'd return UNKNOWN again"

    def test_wall_clock_cap_on_hung_write(self, monkeypatch):
        """A hung write() in the active probe must not hang detect()."""
        self._patch_port_exists(monkeypatch)
        self._patch_stty_noop(monkeypatch)
        # Silent rx so passive identify returns None and we fall to active probe
        # Then write blocks for 10s — detect must give up well before that.
        fake = FakeSerial(rx_chunks=[], write_blocks=True)
        self._patch_pyserial(monkeypatch, fake)

        t0 = time.monotonic()
        result = esp32_detect.detect(timeout=0.3)
        elapsed = time.monotonic() - t0

        assert result == Firmware.UNKNOWN
        # Total budget is generous: passive (≤ silence) + active probe with
        # whatever budget remains.  Hard ceiling: well under the 10s write hang.
        assert elapsed < 5.0, f"detect() exceeded wall-clock cap: {elapsed:.2f}s"

    def test_closes_serial_on_passive_success(self, monkeypatch):
        """ser.close() must always be called, even on the fast path."""
        self._patch_port_exists(monkeypatch)
        self._patch_stty_noop(monkeypatch)
        fake = FakeSerial(rx_chunks=[MIMICLAW_BOOT_LOG])
        self._patch_pyserial(monkeypatch, fake)

        esp32_detect.detect()
        assert fake.is_open is False, "Serial port was leaked"

    def test_closes_serial_on_silence(self, monkeypatch):
        """ser.close() must be called even when nothing matched."""
        self._patch_port_exists(monkeypatch)
        self._patch_stty_noop(monkeypatch)
        fake = FakeSerial(rx_chunks=[])
        self._patch_pyserial(monkeypatch, fake)

        esp32_detect.detect(timeout=0.3)
        assert fake.is_open is False

    def test_invokes_disable_hupcl(self, monkeypatch):
        """detect() should call _disable_hupcl on the resolved port."""
        self._patch_port_exists(monkeypatch)
        stty_calls = []
        monkeypatch.setattr(
            esp32_detect.subprocess, "run",
            lambda cmd, **kw: stty_calls.append(cmd) or MagicMock(returncode=0),
        )
        fake = FakeSerial(rx_chunks=[MIMICLAW_BOOT_LOG])
        self._patch_pyserial(monkeypatch, fake)

        esp32_detect.detect()

        assert any(
            cmd == ["stty", "-F", "/dev/esp32", "-hupcl"]
            for cmd in stty_calls
        ), f"stty -hupcl was not invoked; calls were {stty_calls}"


# ── _close_fast ───────────────────────────────────────────────────────


class CloseHangingSerial(FakeSerial):
    """Models an ESP32 in a boot loop: close() blocks waiting on tcdrain.

    `_close_fast` should call reset_output_buffer first to discard
    pending TX, so close() never has to drain.
    """

    def __init__(self):
        super().__init__()
        self.close_blocks_unless_flushed = True
        self.flushed = False

    def reset_output_buffer(self):
        self.flushed = True
        self.events.append(("reset_output_buffer", None))

    def close(self):
        if self.close_blocks_unless_flushed and not self.flushed:
            time.sleep(10)  # simulates tcdrain hang
        self.is_open = False
        self.events.append(("close", None))


class TestCloseFast:
    def test_flushes_output_then_closes(self):
        ser = CloseHangingSerial()
        ser.is_open = True

        t0 = time.monotonic()
        esp32_detect._close_fast(ser)
        elapsed = time.monotonic() - t0

        assert ser.flushed is True
        assert ser.is_open is False
        assert elapsed < 1.0, f"_close_fast was slow: {elapsed:.2f}s"

    def test_handles_none(self):
        # No exception even when called with None
        esp32_detect._close_fast(None)

    def test_handles_close_raise(self):
        """If close() raises, _close_fast should swallow it."""
        ser = CloseHangingSerial()
        ser.is_open = True
        ser.close = lambda: (_ for _ in ()).throw(OSError("fd already closed"))

        # Must not raise
        esp32_detect._close_fast(ser)


# ── _wait_for_ready ──────────────────────────────────────────────────


# Real boot output captured 2026-04-25 from the just-flashed mimi chip
# (post-flash session).  Includes the full path from ROM bootloader
# through ESP-IDF init to the application's "ready" line.
MIMI_FULL_BOOT = (
    b"ESP-ROM:esp32s3-20210327\r\n"
    b"Build:Mar 27 2021\r\n"
    b"rst:0x15 (USB_UART_CHIP_RESET),boot:0x8 (SPI_FAST_FLASH_BOOT)\r\n"
    b"...\r\n"
    b"I (5750) wifi: Scanning nearby APs...\r\n"
    b"I (5752) mimi: All services started!\r\n"
    b"I (5752) mimi: MimiClaw ready. Type 'help' for CLI commands.\r\n"
    b"I (5752) main_task: Returned from app_main()\r\n"
    b"\r\nmimi> "
)


class TestWaitForReady:
    """`_wait_for_ready(ser, fw, timeout)` reads the boot stream and
    returns True once the firmware-specific ready marker shows up,
    or False if *timeout* elapses first."""

    def test_mimiclaw_ready_marker_matches(self):
        ser = FakeSerial(rx_chunks=[MIMI_FULL_BOOT])
        ok = esp32_detect._wait_for_ready(ser, Firmware.MIMICLAW, timeout=3.0)
        assert ok is True

    def test_mimiclaw_prompt_alone_matches(self):
        # Sometimes we miss the banner but catch the prompt alone
        ser = FakeSerial(rx_chunks=[b"\r\nmimi> "])
        ok = esp32_detect._wait_for_ready(ser, Firmware.MIMICLAW, timeout=3.0)
        assert ok is True

    def test_micropython_prompt_matches(self):
        ser = FakeSerial(rx_chunks=[b"MicroPython 1.22\r\n>>> "])
        ok = esp32_detect._wait_for_ready(ser, Firmware.MICROPYTHON, timeout=3.0)
        assert ok is True

    def test_marauder_banner_matches(self):
        # Marauder's banner contains the literal "ESP32 Marauder" string
        ser = FakeSerial(rx_chunks=[
            b"\r\nESP32 Marauder v1.11.0\r\nHardware: uConsole AIO ESP32-S3\r\n"
        ])
        ok = esp32_detect._wait_for_ready(ser, Firmware.MARAUDER, timeout=3.0)
        assert ok is True

    def test_marauder_prompt_matches(self):
        # `> ` at the start of a line is the prompt; should match too
        ser = FakeSerial(rx_chunks=[b"some boot output\r\n> "])
        ok = esp32_detect._wait_for_ready(ser, Firmware.MARAUDER, timeout=3.0)
        assert ok is True

    def test_returns_false_when_no_marker_in_budget(self):
        # Boot log without a ready marker — never reaches the prompt
        ser = FakeSerial(rx_chunks=[
            b"ESP-ROM bootloader output but never finishes\r\n" * 20
        ])
        t0 = time.monotonic()
        ok = esp32_detect._wait_for_ready(ser, Firmware.MIMICLAW, timeout=0.5)
        elapsed = time.monotonic() - t0
        assert ok is False
        assert elapsed < 1.0, f"timeout not enforced: {elapsed:.2f}s"

    def test_unknown_firmware_returns_true_immediately(self):
        # No marker known for UNKNOWN — caller already knows it can't
        # run commands, so just succeed without waiting.  Returning
        # False would be misleading; True with no wait keeps callers
        # uniform.
        ser = FakeSerial(rx_chunks=[])
        t0 = time.monotonic()
        ok = esp32_detect._wait_for_ready(ser, Firmware.UNKNOWN, timeout=3.0)
        elapsed = time.monotonic() - t0
        assert ok is True
        assert elapsed < 0.1

    def test_returns_quickly_when_marker_already_in_buffer(self):
        # If the ready marker is in the very first chunk, we should
        # return immediately, not wait for the full timeout
        ser = FakeSerial(rx_chunks=[MIMI_FULL_BOOT])
        t0 = time.monotonic()
        esp32_detect._wait_for_ready(ser, Firmware.MIMICLAW, timeout=10.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.5, f"slow even with marker present: {elapsed:.2f}s"


class TestIdentifyOrReady:
    """`_identify_or_ready(ser, timeout)` — single-pass watch for any
    firmware's ready marker.  Returns matched Firmware or UNKNOWN."""

    def test_matches_mimiclaw(self):
        ser = FakeSerial(rx_chunks=[MIMI_FULL_BOOT])
        assert esp32_detect._identify_or_ready(ser, timeout=2.0) == Firmware.MIMICLAW

    def test_matches_micropython(self):
        ser = FakeSerial(rx_chunks=[b"junk\r\n>>> "])
        assert esp32_detect._identify_or_ready(ser, timeout=2.0) == Firmware.MICROPYTHON

    def test_returns_unknown_on_timeout(self):
        ser = FakeSerial(rx_chunks=[b"unrelated noise\r\n"])
        t0 = time.monotonic()
        result = esp32_detect._identify_or_ready(ser, timeout=0.4)
        elapsed = time.monotonic() - t0
        assert result == Firmware.UNKNOWN
        assert elapsed < 1.0

    def test_returns_unknown_on_silence(self):
        ser = FakeSerial(rx_chunks=[])
        t0 = time.monotonic()
        result = esp32_detect._identify_or_ready(ser, timeout=0.3)
        elapsed = time.monotonic() - t0
        assert result == Firmware.UNKNOWN
        assert elapsed < 0.5


# ── open_ready ───────────────────────────────────────────────────────


class TestOpenReady:
    """`open_ready(port=, ready_timeout=)` returns (Serial, Firmware) for
    a fully-booted chip ready to accept commands, or (None, UNKNOWN)
    on failure.  Convenience wrapper combining _open_quiet + identify
    + _wait_for_ready.
    """

    def _patch_pyserial(self, monkeypatch, fake):
        mod = types.SimpleNamespace(
            Serial=lambda: fake,
            SerialException=Exception,
            SerialTimeoutException=Exception,
        )
        monkeypatch.setattr(esp32_detect, "_pyserial", mod, raising=False)

    def _patch_port(self, monkeypatch, port="/dev/esp32"):
        monkeypatch.setattr(esp32_detect.os.path, "exists", lambda p: p == port)

    def _patch_stty(self, monkeypatch):
        monkeypatch.setattr(
            esp32_detect.subprocess, "run",
            lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""),
        )

    def test_returns_serial_and_fw_when_ready(self, monkeypatch):
        self._patch_port(monkeypatch)
        self._patch_stty(monkeypatch)
        fake = FakeSerial(rx_chunks=[MIMI_FULL_BOOT])
        self._patch_pyserial(monkeypatch, fake)

        ser, fw = esp32_detect.open_ready(ready_timeout=2.0)

        assert fw == Firmware.MIMICLAW
        assert ser is fake
        assert ser.is_open is True
        # Caller is responsible for closing
        ser.close()

    def test_returns_none_unknown_when_no_port(self, monkeypatch):
        monkeypatch.setattr(esp32_detect.os.path, "exists", lambda p: False)
        ser, fw = esp32_detect.open_ready()
        assert ser is None
        assert fw == Firmware.UNKNOWN

    def test_returns_serial_unknown_when_chip_silent(self, monkeypatch):
        """Silent chip → identify returns UNKNOWN, ser is still returned
        in case caller wants the raw handle (e.g. for esptool reflash).
        """
        self._patch_port(monkeypatch)
        self._patch_stty(monkeypatch)
        fake = FakeSerial(rx_chunks=[])
        self._patch_pyserial(monkeypatch, fake)

        ser, fw = esp32_detect.open_ready(ready_timeout=0.3)
        assert fw == Firmware.UNKNOWN
        assert ser is fake  # caller decides what to do
        ser.close()

    def test_open_ready_full_mimi_boot(self, monkeypatch):
        """End-to-end: full mimi boot stream → identifies MIMICLAW."""
        self._patch_port(monkeypatch)
        self._patch_stty(monkeypatch)
        fake = FakeSerial(rx_chunks=[MIMI_FULL_BOOT])
        self._patch_pyserial(monkeypatch, fake)

        ser, fw = esp32_detect.open_ready(ready_timeout=2.0)

        assert fw == Firmware.MIMICLAW
        assert ser is fake
        ser.close()
