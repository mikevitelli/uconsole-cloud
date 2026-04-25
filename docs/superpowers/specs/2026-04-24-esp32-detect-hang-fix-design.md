# ESP32 firmware detection: fix indefinite hang on TUI connect

**Status:** Draft
**Author:** mike
**Date:** 2026-04-24
**Branch:** `dev`
**Affected files (primary):** `device/lib/tui/esp32_detect.py`
**Related:** `device/lib/tui/marauder.py`, `device/lib/tui/mimiclaw.py`, `device/lib/tui/esp32_flash.py`

## Problem

The TUI's ESP32 hub displays "Detecting ESP32 firmware..." indefinitely. Reproduces 100% on the current `dev` branch with the AIO-board ESP32-S3 (USB ID `303a:1001`, exposed as `/dev/esp32 → /dev/ttyACM0`) running the in-house MimiClaw build (ESP-IDF v5.5.2, compiled 2026-04-21).

A bare-metal repro outside the TUI hangs identically:

```python
from tui import esp32_detect
esp32_detect.detect(timeout=2.5)   # never returns
```

A step-by-step probe shows the hang occurs between `ser.write(b"\x03\x03\r\n")` (the Phase-1 MicroPython interrupt) and the subsequent `time.sleep(0.5)` — i.e. inside `write()` / kernel TX drain. With an 8-second hard timeout, the test exits 124; with no timeout it hangs forever.

A passive-listen probe (open the port, read 2 s, write nothing) succeeds and dumps **54,537 bytes** of ESP-IDF boot output, beginning at the ROM bootloader entry vector:

```
entry 0x403c8948
I (29) boot: ESP-IDF v5.5.2 2nd stage bootloader
I (29) boot: compile time Apr 21 2026 21:15:04
I (30) boot: Multicore bootloader
I (31) boot: chip revision: v0.2
…
```

So: **opening `/dev/esp32` is resetting the chip every time**, and `detect()` writes to the OUT endpoint while the chip is still mid-boot, blocking until the kernel's TX buffer drains — which never completes within any reasonable timeout because the device-side USB peripheral isn't servicing OUT until the application is up.

## Root cause

Two compounding issues, plus a missing safety net:

### 1. Open-time control-line pulse triggers a chip reset

`esp32_detect.detect()` opens the port with the default pyserial constructor:

```python
ser = serial.Serial(port, 115200, timeout=timeout)
```

This opens with **DTR=True, RTS=True** by default. On the AIO-board ESP32-S3 — which uses the ESP32-S3's **built-in USB-Serial/JTAG peripheral** (not a separate USB-UART converter) — those control-line transitions are observed by the chip and trigger a reset.

This is a **hardware-level limitation specific to the ESP32-S3**:

> "Later versions of the USB-serial-JTAG peripheral (the one in the C6 and iirc H2) have a function that can [disable host-driven reset], but the S3 doesn't."
> — Espressif staff response on the official forum ([esp32.com t=37208](https://www.esp32.com/viewtopic.php?t=37208), summarised via [search](https://esp32.com/viewtopic.php?t=43163))

The kconfig symbol that disables this on later chips (`CONFIG_USB_SERIAL_JTAG_USB_UART_CHIP_RST_DIS`, surfaced via `idf.py menuconfig`) is **not available on ESP32-S3 silicon** — there is no firmware-side fix we can ship in MimiClaw to make this go away. The fix has to be on the host.

The pyserial behaviour is documented and known: opening with the constructor toggles DTR/RTS regardless of the `dsrdtr` argument — it is only suppressed by setting the properties **before** `open()`:

> "Setting `ser.dtr = 0` (or `None`) before opening the port and then calling `ser.open()` works. … `dsrdtr=False` in the constructor does toggle the control line(s) despite the False value."
> — pyserial issue [#124](https://github.com/pyserial/pyserial/issues/124)

### 2. `detect()` writes immediately after open, with no settling delay

Even with the reset accepted as unavoidable, `detect()` proceeds straight to `ser.write(b"\x03\x03\r\n")` ~zero time after `open()` returns. The chip is still in ROM bootloader / 2nd-stage boot at that point and the USB-OUT endpoint isn't draining, so the host's `write()` call waits on `tcdrain()` indefinitely.

The boot dump itself (54 KB / ~2 s) is **identifying information we are throwing away**: ESP-IDF prints `boot: ESP-IDF v5.5.2`, the application banner contains `mimi>` for MimiClaw or `MicroPython` for upython, etc. We can match firmware on the passive boot log without writing a single byte.

### 3. No wall-clock cap on the probe

There is no overall timeout in `detect()`. The TUI shows "Detecting…" forever when phase 1 hangs, with no path to recover except killing `console`. This is the proximate user-visible defect; (1) and (2) are why the hang exists in the first place.

## Goals / non-goals

**Goals**

- `detect()` returns in **≤500 ms** in the typical (settled, idle) case.
- `detect()` returns in **≤5 s** in the worst case (cold open, full boot dump), never hangs.
- Detection still correctly distinguishes MicroPython, Marauder, MimiClaw, Bruce, Unknown.
- Open the port without resetting the chip when possible; when not possible, recover gracefully.
- Same `Firmware` enum, same public API (`detect`, `get_port`, `invalidate_cache`, `detect_board_variant`, `read_flash_size`) — call sites in `marauder.py`, `mimiclaw.py`, `esp32_flash.py`, `radio.py` are unchanged.

**Non-goals**

- Modifying MimiClaw firmware (no S3-side fix exists; we don't own the Marauder or upython builds).
- Touching the flash module (`esp32_flash.py`) — esptool already handles its own reset sequencing.
- Generalising the host-side workaround to other USB-UART chips. The AIO is the only board in scope.

## Design

A four-layer fix in `esp32_detect.py`. Each layer is independently useful; together they kill the hang.

### Layer A — Open without pulsing control lines (canonical pyserial idiom)

Replace the one-line `Serial(...)` call with the deferred-open form, setting `dtr` / `rts` to `False` **before** opening:

```python
def _open_quiet(port, timeout):
    """Open *port* at 115200 8N1 without pulsing DTR/RTS.

    Avoids the spurious chip-reset that the default Serial(...) call
    triggers on ESP32-S3 USB-Serial/JTAG (303a:1001), which has no
    firmware-side disable for host-driven reset.
    """
    ser = _pyserial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = timeout
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser
```

This eliminates the reset on **every open after the first**, because `stty -hupcl` (Layer B) prevents the close-time DTR drop that would otherwise re-arm the reset. The very first open after a fresh USB enumeration may still reset, because the kernel's `cdc_acm` may briefly assert DTR before pyserial's `ser.dtr = False` takes effect — Linux gives no atomic "open with these modem-control bits already cleared" syscall ([codegenes.net](https://www.codegenes.net/blog/how-to-open-serial-port-in-linux-without-changing-any-pin/)). Layers C and D handle that case.

### Layer B — Disable hangup-on-close on the tty

Run once per `detect()` invocation, idempotent and cheap:

```python
def _disable_hupcl(port):
    """Tell the kernel not to drop DTR when the port is closed.

    Without this, every Serial.close() re-asserts the reset line on
    next open, undoing Layer A.  Safe to call repeatedly; -hupcl
    persists for the lifetime of the cdc_acm device node.
    """
    subprocess.run(
        ["stty", "-F", port, "-hupcl"],
        capture_output=True, timeout=2,
    )
```

`stty -hupcl` is the standard fix for "Arduino resets when I close the serial monitor" and applies equally to ESP32 USB-CDC ([Arduino forum t=28248](https://forum.arduino.cc/t/disable-auto-reset-by-serial-connection/28248), [esp32.com t=4988](https://esp32.com/viewtopic.php?t=4988)). It is non-destructive — the next USB unplug/replug cycle resets the flag.

We do **not** also persist this via udev rules in this change. If we later want it always-on we can add a one-liner to `system/udev/99-esp32.rules`; deferring that to a follow-up to keep this PR small.

### Layer C — Drain-and-identify before writing

After opening, read for up to ~300 ms of "silence window" (no new bytes for 300 ms) before doing anything else. Match firmware identifiers against this passive output **first**, since a chip that just reset is loudly self-identifying:

```python
_BOOT_PATTERNS = [
    (re.compile(rb"mimi>"),                    Firmware.MIMICLAW),
    (re.compile(rb"MicroPython"),              Firmware.MICROPYTHON),
    (re.compile(rb">>> "),                     Firmware.MICROPYTHON),
    (re.compile(rb"Marauder", re.IGNORECASE),  Firmware.MARAUDER),
    (re.compile(rb"Bruce",    re.IGNORECASE),  Firmware.BRUCE),
]

def _passive_identify(ser, max_total=2.0, silence=0.30):
    """Read until *silence* seconds elapse with no new bytes, capped at
    *max_total* seconds total.  Return the first matching Firmware
    enum value, or None if nothing matched."""
    deadline = time.monotonic() + max_total
    last_recv = time.monotonic()
    buf = bytearray()
    while time.monotonic() < deadline:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            last_recv = time.monotonic()
            for pat, fw in _BOOT_PATTERNS:
                if pat.search(buf):
                    return fw
        elif time.monotonic() - last_recv >= silence:
            return None
        else:
            time.sleep(0.02)
    return None
```

In the common cold-open case this returns `MIMICLAW` within ~1.5 s purely from the boot banner — without writing a byte to a chip that wouldn't accept it anyway.

### Layer D — Active probe, with overall wall-clock cap

If passive ID didn't match, fall back to the existing two-phase probe (Ctrl-C × 2 for MicroPython, then `info\r\n` for Marauder), but:

- Wrap the entire `detect()` in a **single `time.monotonic()` budget** of 5 s (default; configurable via the existing `timeout` arg as `timeout * 2`-ish, see below).
- Each individual `read`/`write` carries its own short pyserial timeout (300 ms write timeout via `ser.write_timeout = 0.3`, 1 s read timeout) so a stuck call surfaces as `serial.SerialTimeoutException` and we can fall through to UNKNOWN instead of hanging.
- On any `SerialTimeoutException` or `SerialException`, return `Firmware.UNKNOWN` and **invalidate the cache** so the next call retries (instead of pinning a bad result for 30 s).

The existing `timeout=2.0` parameter changes meaning slightly: it becomes the per-phase timeout rather than the only timeout. The total wall-clock cap is `max(5.0, timeout * 2.5)`. Call sites pass either no value or `2.0`, both of which behave identically to today in the success case.

### Cache behaviour

Unchanged for hits. For the new `UNKNOWN` outcome from a timeout/exception, we **do not** cache — so a transient hang doesn't pin a 30-second window of failure. A successful identification (any of the four real firmware values) caches as today.

### Public API

No signature changes. New private helpers (`_open_quiet`, `_disable_hupcl`, `_passive_identify`, `_with_deadline`) live in the same module. The `Firmware` enum, `detect()`, `get_port()`, `invalidate_cache()`, `detect_board_variant()`, `read_flash_size()` keep the same call shape.

## Testing

Unit tests live in `device/tests/tui/test_esp32_detect.py` (currently 30 tests per the project memory). New / updated coverage:

- `test_open_quiet_sets_dtr_rts_before_open` — assert that on the mocked `Serial`, the property assignments to `dtr` and `rts` happen before `open()`.
- `test_disable_hupcl_invokes_stty` — confirm the `stty -F <port> -hupcl` call shape.
- `test_passive_identify_matches_mimiclaw_banner` — feed the captured 54 KB boot dump through `_passive_identify`, expect `Firmware.MIMICLAW`.
- `test_passive_identify_matches_micropython_prompt` — `>>> ` triggers MICROPYTHON.
- `test_passive_identify_returns_none_on_silence` — empty stream with 300 ms silence returns None within budget.
- `test_detect_wall_clock_cap` — mock a hung write, assert `detect()` returns `UNKNOWN` within 5.5 s (not 30 s, not infinite).
- `test_detect_does_not_cache_unknown_from_timeout` — after a timeout-induced UNKNOWN, the cache must allow re-probing on the next call.
- Existing tests for cached MicroPython, cached Marauder, port-not-found, gpsd-release path: unchanged, must still pass.

Manual on-device verification:

1. With ESP32 plugged in and idle: `python3 -c "from tui import esp32_detect; print(esp32_detect.detect())"` returns `Firmware.MIMICLAW` in <1 s.
2. From the TUI: ESP32 hub opens to the MimiClaw submenu without the spinner getting stuck.
3. Pull the USB lead, run the same probe: returns `Firmware.UNKNOWN` in <100 ms (port-not-found path, unchanged).
4. Hold the chip in reset (touch RESET pad), run the probe: returns `Firmware.UNKNOWN` in ≤5 s, does not hang.
5. Smoke `marauder.py` and `mimiclaw.py` paths once detection succeeds — connect, read a frame, disconnect — to confirm Layers A+B don't break anything downstream that *expected* the reset (none should; both submenus issue their own write commands as the first interaction).

## Rollout

- Land on `dev` as one commit titled `fix(esp32): kill detect() hang via no-pulse open + boot-log identify`.
- No version bump on its own — bundle into the next `/publish` cycle along with whatever else queues up. Version is currently `0.2.1`; this would land as the next patch.
- Backwards compatible: same module API, same enum, same caching semantics for successful detection.
- No changes to udev rules, systemd units, or other scripts in this PR. (Optional follow-up: persistent `-hupcl` via udev `RUN+="…"` if we want to remove the per-call `stty` shell-out.)

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| `stty -F /dev/esp32 -hupcl` requires the user to be in the `dialout`/`plugdev` group. | Already true on this device (verified: `crw-rw-rw- … plugdev`). Failure is non-fatal — `subprocess.run(..., capture_output=True)` swallows it, and Layer A still helps even without -hupcl. |
| Boot-log pattern matches inside arbitrary user data (e.g. someone names a SSID "MicroPython"). | Patterns match only the boot/banner window (first 2 s after open). Unsolicited matches in steady-state user data cannot occur because we exit `_passive_identify` at the silence boundary. |
| `_passive_identify` returns the wrong firmware if two banners happen to overlap (theoretically possible if a user reflashed mid-boot). | First-match-wins ordering is conservative: MIMICLAW and MICROPYTHON are checked before Marauder, matching the most distinctive identifiers first. Worst case: wrong submenu opens, user backs out and retries. |
| Some future MimiClaw build silently changes the `mimi>` prompt. | Pattern lives in one place (`_BOOT_PATTERNS`), single-line edit. We own the mimiclaw firmware; banner is unlikely to change without our knowledge. |

## References

- [pyserial issue #124 — DTR/RTS toggle on open](https://github.com/pyserial/pyserial/issues/124)
- [pyserial 3.5 API docs — Serial properties](https://pyserial.readthedocs.io/en/latest/pyserial_api.html)
- [Espressif forum t=37208 — ESP32-S3 cannot disable USB-JTAG RTS reset](https://www.esp32.com/viewtopic.php?t=37208)
- [Espressif forum t=43163 — CHIP_RST_DIS works on C6, not S3](https://esp32.com/viewtopic.php?t=43163)
- [ESP-IDF docs — USB Serial/JTAG console (ESP32-S3)](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/usb-serial-jtag-console.html)
- [Arduino forum t=28248 — disable auto-reset by serial connection](https://forum.arduino.cc/t/disable-auto-reset-by-serial-connection/28248)
- [Arduino forum t=1217801 — ESP32-C3 reboots on serial close (same root cause)](https://forum.arduino.cc/t/problem-with-esp32-c3-rebooting-when-closing-the-serial-port/1217801)
- [ESP-IDF issue #13075 — DTR/RTS reset on close](https://github.com/espressif/esp-idf/issues/13075)
- [codegenes.net — opening a Linux serial port without changing pins](https://www.codegenes.net/blog/how-to-open-serial-port-in-linux-without-changing-any-pin/)
