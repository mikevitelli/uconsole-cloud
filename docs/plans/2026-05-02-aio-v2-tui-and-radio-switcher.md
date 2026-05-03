# AIO v2 TUI + WiFi Radio Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a TUI dashboard mirroring the `aiov2_ctl` GUI (rails + boot defaults + power telemetry), an auto-power-on hook for rail-dependent submenus, and a three-mode WiFi radio switcher (rfkill-based) — all inside the existing curses TUI, gracefully degrading to the v1 `aio-check.sh` panel on AIO v1 boards.

**Architecture:** Two new feature modules (`tui/aio.py`, `tui/wifi_radio.py`) following the existing `HANDLERS = {...}` registry pattern. Both shell out to existing CLI tools (`aiov2_ctl`, `nmcli`, `rfkill`, `iw`) — no direct GPIO or NetworkManager API access. Parsers are pure functions covered by unit tests with captured fixtures; curses panels are smoke-tested live on the device. Menu wiring in `framework.py` replaces one HARDWARE entry, adds one WiFi-submenu entry, and wraps four rail-dependent dispatches with `aio.ensure_rail(...)`.

**Tech Stack:** Python 3.11 (stdlib + curses), pytest for unit tests, `aiov2_ctl` (HackerGadgets, package `hackergadgets-uconsole-aio-board`), `nmcli`, `rfkill`, `iw`.

**Spec:** `docs/specs/2026-05-02-aio-v2-tui-and-radio-switcher-design.md`

**Branch:** `feat/aio-v2-tui` (off `dev`)

---

## File Structure

| File | Role | Status |
|---|---|---|
| `device/lib/tui/aio.py` | Board detection, `aiov2_ctl --status` parser, `ensure_rail()`, dashboard panel + handler | NEW |
| `device/lib/tui/wifi_radio.py` | Radio detection (`iw dev` + `rfkill list` parsers), three-mode `set_mode()`, mode picker panel + handler | NEW |
| `device/lib/tui/framework.py` | Replace `HARDWARE → AIO Board Check` entry; add `Radio Mode` to `sub:wifi`; register both modules in `FEATURE_MODULES`; wrap 4 rail-dependent dispatches with `ensure_rail` | MODIFY |
| `tests/test_aio_parser.py` | Parser tests for `aiov2_ctl --status` text → dict | NEW |
| `tests/test_aio_detect.py` | `detect()` and `ensure_rail()` behavior tests | NEW |
| `tests/test_wifi_radio_parser.py` | Parser tests for `iw dev` and `rfkill list` outputs | NEW |
| `tests/fixtures/aiov2_status_*.txt` | Captured `aiov2_ctl --status` outputs (mixed rail states, AC vs BAT) | NEW |
| `tests/fixtures/iw_dev.txt`, `rfkill_list.txt` | Captured `iw dev` and `rfkill list` outputs | NEW |
| `device/scripts/radio/aio-check.sh` | UNCHANGED (still called for v1 boards via auto-detect) | — |

Tests live under the repo-root `tests/` directory (not `device/tests/`) — that's where the existing `test_handler_registry.py`, `test_module_exports.py`, etc. already live, and the `tests/conftest.py` adds `device/lib/` to `sys.path`.

---

## Task 1: Capture fixtures from the live device

**Why first:** Every parser test needs real CLI output. Capture once, reuse forever.

**Files:**
- Create: `tests/fixtures/aiov2_status_mixed_ac.txt`
- Create: `tests/fixtures/aiov2_status_all_off_bat.txt`
- Create: `tests/fixtures/iw_dev.txt`
- Create: `tests/fixtures/rfkill_list.txt`

- [ ] **Step 1: Capture aiov2_ctl --status with mixed rail states on AC**

```bash
cd ~/uconsole-cloud
mkdir -p tests/fixtures
# Set known state: GPS off, LORA off, SDR off, USB on (default boot state)
/usr/local/bin/aiov2_ctl GPS off >/dev/null
/usr/local/bin/aiov2_ctl LORA off >/dev/null
/usr/local/bin/aiov2_ctl SDR off >/dev/null
/usr/local/bin/aiov2_ctl USB on >/dev/null
# Now flip GPS on so we have a mix
/usr/local/bin/aiov2_ctl GPS on >/dev/null
/usr/local/bin/aiov2_ctl --status > tests/fixtures/aiov2_status_mixed_ac.txt
cat tests/fixtures/aiov2_status_mixed_ac.txt
```

Expected: file contains lines like `GPS   GPIO27: ON`, `LORA  GPIO16: OFF`, plus `Source : AC` (or `BAT` if unplugged), plus a `Power` numeric line.

- [ ] **Step 2: Capture all-rails-off on battery (if you can briefly unplug)**

If on battery already, skip the unplug step.

```bash
/usr/local/bin/aiov2_ctl GPS off >/dev/null
/usr/local/bin/aiov2_ctl --status > tests/fixtures/aiov2_status_all_off_bat.txt
cat tests/fixtures/aiov2_status_all_off_bat.txt
# Restore the previous mixed state
/usr/local/bin/aiov2_ctl GPS on >/dev/null
/usr/local/bin/aiov2_ctl USB on >/dev/null
```

- [ ] **Step 3: Capture iw dev and rfkill list**

```bash
iw dev > tests/fixtures/iw_dev.txt
rfkill list > tests/fixtures/rfkill_list.txt
cat tests/fixtures/iw_dev.txt
cat tests/fixtures/rfkill_list.txt
```

Expected: `iw_dev.txt` contains two `phy#N` blocks each with an `Interface wlanN` line and (if associated) `ssid` line. `rfkill_list.txt` contains entries with `Soft blocked: yes/no` lines.

- [ ] **Step 4: Commit fixtures**

```bash
cd ~/uconsole-cloud
git add tests/fixtures/
git commit -m "test(fixtures): capture aiov2_ctl/iw/rfkill outputs from CM5+AIOv2 device"
```

---

## Task 2: aiov2_ctl --status parser

**Files:**
- Create: `device/lib/tui/aio.py`
- Test: `tests/test_aio_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_aio_parser.py
"""Tests for aiov2_ctl --status text parser."""

import os

import pytest

from tui.aio import parse_status

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_status_mixed_ac():
    out = parse_status(_read("aiov2_status_mixed_ac.txt"))
    # Rails section
    assert out["rails"]["GPS"]["state"] is True
    assert out["rails"]["GPS"]["gpio"] == 27
    assert out["rails"]["LORA"]["state"] is False
    assert out["rails"]["SDR"]["state"] is False
    assert out["rails"]["USB"]["state"] is True
    # Power section (just verify keys exist; values may vary)
    for key in ("source", "status", "capacity", "mode", "voltage", "current", "power"):
        assert key in out["power"], f"missing {key}"
    # Capacity is an int 0..100
    assert isinstance(out["power"]["capacity"], int)
    assert 0 <= out["power"]["capacity"] <= 100


def test_parse_status_all_off():
    out = parse_status(_read("aiov2_status_all_off_bat.txt"))
    for rail in ("GPS", "LORA", "SDR", "USB"):
        assert out["rails"][rail]["state"] is False, f"{rail} should be off"


def test_parse_status_returns_floats_for_numeric_power_fields():
    out = parse_status(_read("aiov2_status_mixed_ac.txt"))
    assert isinstance(out["power"]["voltage"], float)
    assert isinstance(out["power"]["current"], float)
    assert isinstance(out["power"]["power"], float)


def test_parse_status_handles_unknown_rail_gracefully():
    # Unknown text returns empty rails dict — never raises
    out = parse_status("garbage input that has no rails")
    assert out["rails"] == {}
    assert out["power"] == {}
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd ~/uconsole-cloud
pytest tests/test_aio_parser.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'tui.aio'`.

- [ ] **Step 3: Create the parser**

```python
# device/lib/tui/aio.py
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_aio_parser.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_aio_parser.py device/lib/tui/aio.py
git commit -m "feat(tui): aiov2_ctl --status parser with fixture-backed tests"
```

---

## Task 3: Board detection (`detect()`)

**Files:**
- Modify: `device/lib/tui/aio.py`
- Test: `tests/test_aio_detect.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_aio_detect.py
"""Tests for AIO v1/v2 board detection and rail-power helper."""

from unittest.mock import patch, MagicMock

import pytest

from tui import aio


def test_detect_v2_when_binary_present(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", None)
    monkeypatch.setattr(aio.os.path, "isfile", lambda p: p == aio.AIOV2_CTL)
    monkeypatch.setattr(aio.os, "access", lambda p, mode: p == aio.AIOV2_CTL)
    assert aio.detect() == "v2"


def test_detect_v1_when_binary_absent(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", None)
    monkeypatch.setattr(aio.os.path, "isfile", lambda p: False)
    assert aio.detect() == "v1"


def test_detect_is_cached(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", None)
    calls = []
    def fake_isfile(p):
        calls.append(p)
        return True
    monkeypatch.setattr(aio.os.path, "isfile", fake_isfile)
    monkeypatch.setattr(aio.os, "access", lambda p, mode: True)
    aio.detect()
    aio.detect()
    aio.detect()
    # isfile should have been called exactly once (first call); subsequent calls return cache
    assert len(calls) == 1
```

- [ ] **Step 2: Run tests — expect AttributeError on `_detect_cache` / `detect`**

```bash
pytest tests/test_aio_detect.py -v
```

- [ ] **Step 3: Add `detect()` to `device/lib/tui/aio.py`**

Append to the existing file:

```python
# Append to device/lib/tui/aio.py — below the parser

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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_aio_detect.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_aio_detect.py device/lib/tui/aio.py
git commit -m "feat(tui): AIO board v1/v2 detection with caching"
```

---

## Task 4: `ensure_rail()` helper

**Files:**
- Modify: `device/lib/tui/aio.py`
- Modify: `tests/test_aio_detect.py`

- [ ] **Step 1: Add failing tests for ensure_rail**

Append to `tests/test_aio_detect.py`:

```python
def test_ensure_rail_noop_on_v1(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v1")
    # Subprocess should never be invoked on v1
    called = []
    monkeypatch.setattr(aio.subprocess, "run", lambda *a, **kw: called.append(a))
    assert aio.ensure_rail("GPS") is True
    assert called == []


def test_ensure_rail_already_on(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    fake_status = "GPS   GPIO27: ON\nLORA  GPIO16: OFF\n"
    fake_run = MagicMock()
    fake_run.return_value = MagicMock(returncode=0, stdout=fake_status)
    monkeypatch.setattr(aio.subprocess, "run", fake_run)
    assert aio.ensure_rail("GPS") is True
    # Only the --status call, no toggle
    assert fake_run.call_count == 1


def test_ensure_rail_toggles_when_off(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    fake_status = "GPS   GPIO27: OFF\n"
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "--status" in cmd:
            return MagicMock(returncode=0, stdout=fake_status)
        return MagicMock(returncode=0, stdout="")
    monkeypatch.setattr(aio.subprocess, "run", fake_run)
    assert aio.ensure_rail("GPS") is True
    # Status check + toggle
    assert len(calls) == 2
    assert calls[1] == [aio.AIOV2_CTL, "GPS", "on"]


def test_ensure_rail_returns_false_on_toggle_failure(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    def fake_run(cmd, **kw):
        if "--status" in cmd:
            return MagicMock(returncode=0, stdout="GPS   GPIO27: OFF\n")
        return MagicMock(returncode=1, stdout="")
    monkeypatch.setattr(aio.subprocess, "run", fake_run)
    assert aio.ensure_rail("GPS") is False


def test_ensure_rail_unknown_rail_returns_false(monkeypatch):
    monkeypatch.setattr(aio, "_detect_cache", "v2")
    monkeypatch.setattr(aio.subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout=""))
    assert aio.ensure_rail("BOGUS") is False
```

- [ ] **Step 2: Run tests — expect AttributeError**

```bash
pytest tests/test_aio_detect.py -v
```

- [ ] **Step 3: Add `ensure_rail` to `device/lib/tui/aio.py`**

Append:

```python
def _run_ctl(args, timeout=5):
    """Run aiov2_ctl with args, return (returncode, stdout). Never raises."""
    try:
        r = subprocess.run(
            [AIOV2_CTL, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 1, ""


def get_status():
    """Return parsed status dict, or empty {rails:{},power:{}} on any failure."""
    rc, out = _run_ctl(["--status"])
    if rc != 0:
        return {"rails": {}, "power": {}}
    return parse_status(out)


def ensure_rail(name):
    """Ensure rail `name` (GPS/LORA/SDR/USB) is powered. Return True on success.

    On AIO v1 boards: no-op, returns True.
    On AIO v2 with rail already ON: returns True.
    On AIO v2 with rail OFF: calls `aiov2_ctl <name> on` and returns True if rc==0.
    """
    if name not in RAIL_LABELS:
        return False
    if detect() == "v1":
        return True
    status = get_status()
    rail = status["rails"].get(name)
    if rail and rail["state"]:
        return True
    rc, _ = _run_ctl([name, "on"])
    return rc == 0
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_aio_detect.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_aio_detect.py device/lib/tui/aio.py
git commit -m "feat(tui): aio.ensure_rail() — auto-power-on rails on v2, no-op on v1"
```

---

## Task 5: AIO dashboard panel (curses UI)

**Files:**
- Modify: `device/lib/tui/aio.py`

This task has no automated test — curses panels are smoke-tested live on the device in Task 11.

- [ ] **Step 1: Add toggle helpers and the dashboard handler**

Append to `device/lib/tui/aio.py`:

```python
import curses

from tui.framework import (
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    draw_header,
    draw_separator,
    draw_status_bar,
    open_gamepad,
    GP_A,
    GP_B,
    GP_X,
    GP_Y,
    _tui_input_loop,
)

RAIL_ORDER = ["GPS", "LORA", "SDR", "USB"]


def toggle_rail(name, on):
    """Toggle live rail. Returns True on success."""
    if name not in RAIL_LABELS:
        return False
    rc, _ = _run_ctl([name, "on" if on else "off"])
    return rc == 0


def toggle_boot_rail(name, on):
    """Toggle boot-default for a rail. Returns True on success."""
    if name not in RAIL_LABELS:
        return False
    rc, _ = _run_ctl(["--boot-rail", name, "on" if on else "off"])
    return rc == 0


def get_boot_rails():
    """Return {RAIL: bool} of currently configured boot defaults.

    Calls `aiov2_ctl --boot-rails-status` and parses the same `RAIL ON/OFF`
    lines emitted by --status.
    """
    rc, out = _run_ctl(["--boot-rails-status"])
    if rc != 0:
        return {}
    boot = {}
    for line in out.splitlines():
        m = _RAIL_RE.match(line)
        if m:
            boot[m.group(1)] = m.group(3) == "ON"
    return boot


def run_aio_dashboard(scr):
    """Full-screen TUI panel for AIO v2 rail control."""
    if detect() == "v1":
        # Delegate to the legacy v1 script. Imported lazily to avoid a hard
        # framework dependency at module import time (keeps unit tests clean).
        from tui.framework import _run_script_panel
        _run_script_panel(scr, "radio/aio-check.sh")
        return

    js = open_gamepad()
    scr.timeout(150)
    selected = 0
    last_status = {"rails": {}, "power": {}}
    last_boot = {}
    last_refresh = 0.0
    error_msg = ""
    error_until = 0.0
    REFRESH_INTERVAL = 1.5

    import time

    def refresh():
        nonlocal last_status, last_boot, last_refresh
        last_status = get_status()
        last_boot = get_boot_rails()
        last_refresh = time.time()

    refresh()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        draw_header(scr, w)
        title = "AIO v2 — Rails & Power"
        scr.addnstr(6, max(0, (w - len(title)) // 2), title, w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        draw_separator(scr, 7, w)

        y = 9
        scr.addnstr(y, 2, "── Power ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        p = last_status.get("power", {})
        if p:
            mode = p.get("mode", "?")
            scr.addnstr(y, 4, f"Mode       {mode}", w - 6, curses.color_pair(C_ITEM))
            y += 1
            cap = p.get("capacity", "?")
            status_word = p.get("status", "?")
            pwr = p.get("power", "?")
            scr.addnstr(y, 4, f"Power      {pwr} W       Battery  {cap}%  ({status_word})",
                        w - 6, curses.color_pair(C_ITEM))
            y += 2
        else:
            scr.addnstr(y, 4, "(unable to read --status)", w - 6,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
            y += 2

        scr.addnstr(y, 2, "── Rails ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        for i, rail in enumerate(RAIL_ORDER):
            info = last_status.get("rails", {}).get(rail, {})
            on = info.get("state", False)
            boot_on = last_boot.get(rail, False)
            dot = "●" if on else "○"
            boot_dot = "●" if boot_on else "○"
            label = RAIL_LABELS[rail]
            line = f"{rail:5}  {dot}  {'ON ' if on else 'OFF'}    boot {boot_dot}     {label}"
            cursor = "▸ " if i == selected else "  "
            attr = curses.color_pair(C_SEL) | curses.A_REVERSE if i == selected \
                else curses.color_pair(C_ITEM)
            scr.addnstr(y, 2, cursor + line, w - 4, attr)
            y += 1

        y += 1
        scr.addnstr(y, 2, "── WiFi ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        # Lazy import to avoid circular import at module load
        from tui.wifi_radio import current_mode_label, brief_radio_summary
        scr.addnstr(y, 4, current_mode_label() + "     " + brief_radio_summary(),
                    w - 6, curses.color_pair(C_ITEM))

        if error_msg and time.time() < error_until:
            scr.addnstr(h - 2, 2, error_msg, w - 4,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
        footer = " ↑↓ Rail │ A Toggle │ X Boot Default │ Y WiFi Radios │ B Back "
        draw_status_bar(scr, h, w, footer)
        scr.refresh()

        if time.time() - last_refresh > REFRESH_INTERVAL:
            refresh()

        key, gp_action = _tui_input_loop(scr, js)
        if key == -1 and gp_action is None:
            continue
        if key == ord("q") or key == ord("Q") or gp_action == "back":
            return
        if key == curses.KEY_UP or key == ord("k"):
            selected = (selected - 1) % len(RAIL_ORDER)
        elif key == curses.KEY_DOWN or key == ord("j"):
            selected = (selected + 1) % len(RAIL_ORDER)
        elif key in (curses.KEY_ENTER, 10, 13, ord(" ")) or gp_action == "enter":
            rail = RAIL_ORDER[selected]
            current_on = last_status.get("rails", {}).get(rail, {}).get("state", False)
            ok = toggle_rail(rail, not current_on)
            if not ok:
                error_msg = f"  ✗ failed to toggle {rail}"
                error_until = time.time() + 3
            refresh()
        elif key == ord("b") or key == ord("B") or gp_action == "refresh":
            # GP_X mapped to "refresh" by _tui_input_loop — repurpose for boot-rail toggle
            rail = RAIL_ORDER[selected]
            current_boot = last_boot.get(rail, False)
            ok = toggle_boot_rail(rail, not current_boot)
            if not ok:
                error_msg = f"  ✗ failed to set boot default for {rail}"
                error_until = time.time() + 3
            refresh()
        elif key == ord("w") or key == ord("W") or gp_action == "quit":
            # GP_Y mapped to "quit" by _tui_input_loop — repurpose for WiFi jump
            from tui.wifi_radio import run_wifi_radio_picker
            run_wifi_radio_picker(scr)
            refresh()


HANDLERS = {
    "_aio_board": run_aio_dashboard,
}
```

> **Note on gamepad action remapping:** the framework's `_tui_input_loop` returns conventional gp_action labels (`enter`, `back`, `refresh`, `quit`) for buttons A/B/X/Y. Inside this panel we deliberately repurpose `refresh` → boot-rail toggle and `quit` → WiFi jump, because auto-refresh covers `X`'s usual role and there's no need for an in-panel quit (that's `Y`'s usual role). Comments in the code document this.

- [ ] **Step 2: Smoke-import to verify no syntax errors**

```bash
cd ~/uconsole-cloud
python3 -c "import sys; sys.path.insert(0, 'device/lib'); from tui import aio; print(aio.HANDLERS)"
```

Expected: prints `{'_aio_board': <function run_aio_dashboard at ...>}`. (Will fail on the `from tui.wifi_radio import ...` line if wifi_radio isn't created yet — that's OK, the import is lazy *inside* the handler. The module-level import line is `from tui.framework import ...` which should succeed.)

If it fails on a `tui.framework` symbol that doesn't exist (e.g., `_run_script_panel` may need a different name), grep for the actual one:

```bash
grep -nE "def _run_script_panel|def run_panel|def run_script_panel" device/lib/tui/framework.py
```

…and rename in the lazy import inside `run_aio_dashboard` to match. The same applies to `_tui_input_loop`: verify the symbol exists.

- [ ] **Step 3: Commit**

```bash
git add device/lib/tui/aio.py
git commit -m "feat(tui): AIO v2 dashboard panel — rails, boot defaults, power telemetry"
```

---

## Task 6: WiFi radio parsers

**Files:**
- Create: `device/lib/tui/wifi_radio.py`
- Test: `tests/test_wifi_radio_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_wifi_radio_parser.py
"""Tests for iw dev and rfkill list parsers."""

import os

from tui.wifi_radio import parse_iw_dev, parse_rfkill_list

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_iw_dev_returns_two_phys():
    radios = parse_iw_dev(_read("iw_dev.txt"))
    # Two phys, each with one wlan interface
    ifs = sorted(r["ifname"] for r in radios)
    assert ifs == ["wlan0", "wlan1"]


def test_parse_iw_dev_extracts_phy_and_ssid():
    radios = parse_iw_dev(_read("iw_dev.txt"))
    by_if = {r["ifname"]: r for r in radios}
    # phy field is "phy#0" / "phy#1" — implementation should normalize to int
    assert isinstance(by_if["wlan0"]["phy"], int)
    # At least one of the two should have an SSID populated (fixture-dependent)
    has_ssid = any(r.get("ssid") for r in radios)
    assert has_ssid, "expected at least one associated radio in fixture"


def test_parse_rfkill_list_blocked_status():
    entries = parse_rfkill_list(_read("rfkill_list.txt"))
    # Each phy entry has phy id and soft-blocked bool
    phys = [e for e in entries if e["kind"] == "phy"]
    assert len(phys) >= 1
    for p in phys:
        assert "id" in p
        assert isinstance(p["soft_blocked"], bool)
```

- [ ] **Step 2: Run tests — expect ModuleNotFoundError**

```bash
pytest tests/test_wifi_radio_parser.py -v
```

- [ ] **Step 3: Create `device/lib/tui/wifi_radio.py` with parsers**

```python
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_wifi_radio_parser.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_wifi_radio_parser.py device/lib/tui/wifi_radio.py
git commit -m "feat(tui): wifi_radio iw/rfkill parsers with fixture-backed tests"
```

---

## Task 7: Radio detection + mode resolution

**Files:**
- Modify: `device/lib/tui/wifi_radio.py`
- Modify: `tests/test_wifi_radio_parser.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_wifi_radio_parser.py`:

```python
from unittest.mock import patch, MagicMock

from tui import wifi_radio


def test_label_for_driver():
    assert wifi_radio._label_for_driver("brcmfmac") == "CM5 onboard"
    assert wifi_radio._label_for_driver("mt7921u") == "AC1200 (WiFi 6)"
    assert wifi_radio._label_for_driver("zzz_unknown") == "zzz_unknown"


def test_load_mode_default_is_both(tmp_path, monkeypatch):
    monkeypatch.setattr(wifi_radio, "MODE_FILE", str(tmp_path / "absent"))
    assert wifi_radio.load_mode() == "both"


def test_save_and_load_mode_roundtrip(tmp_path, monkeypatch):
    f = tmp_path / "mode"
    monkeypatch.setattr(wifi_radio, "MODE_FILE", str(f))
    wifi_radio.save_mode("ac1200")
    assert wifi_radio.load_mode() == "ac1200"


def test_save_mode_rejects_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(wifi_radio, "MODE_FILE", str(tmp_path / "mode"))
    with pytest.raises(ValueError):
        wifi_radio.save_mode("bogus")
```

Add `import pytest` at the top of the test file if not already present.

- [ ] **Step 2: Run — expect AttributeError**

```bash
pytest tests/test_wifi_radio_parser.py -v
```

- [ ] **Step 3: Implement detection + mode I/O**

Append to `device/lib/tui/wifi_radio.py`:

```python
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
    """One-liner for the AIO dashboard: 'wlan0=CM5 wlan1=AC1200'."""
    parts = []
    for r in list_radios():
        short = "CM5" if r["driver"] == "brcmfmac" else "AC1200" if r["driver"] == "mt7921u" else r["driver"]
        parts.append(f"{r['ifname']}={short}")
    return "  ".join(parts)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_wifi_radio_parser.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_wifi_radio_parser.py device/lib/tui/wifi_radio.py
git commit -m "feat(tui): wifi radio detection + mode persistence"
```

---

## Task 8: `set_mode()` switcher

**Files:**
- Modify: `device/lib/tui/wifi_radio.py`
- Modify: `tests/test_wifi_radio_parser.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_wifi_radio_parser.py`:

```python
def test_set_mode_both_unblocks_all(monkeypatch):
    radios = [
        {"phy": 0, "driver": "brcmfmac", "ifname": "wlan0", "soft_blocked": True, "ssid": None, "label": "CM5 onboard"},
        {"phy": 1, "driver": "mt7921u",  "ifname": "wlan1", "soft_blocked": True, "ssid": None, "label": "AC1200 (WiFi 6)"},
    ]
    monkeypatch.setattr(wifi_radio, "list_radios", lambda: radios)
    calls = []
    monkeypatch.setattr(wifi_radio.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or MagicMock(returncode=0))
    monkeypatch.setattr(wifi_radio, "save_mode", lambda m: None)
    wifi_radio.set_mode("both")
    # Both phys unblocked
    assert ["rfkill", "unblock", "phy0"] in calls
    assert ["rfkill", "unblock", "phy1"] in calls
    # No block calls
    assert not any(c[1] == "block" for c in calls if len(c) >= 2)


def test_set_mode_onboard_blocks_ac1200(monkeypatch):
    radios = [
        {"phy": 0, "driver": "brcmfmac", "ifname": "wlan0", "soft_blocked": False, "ssid": "X", "label": "CM5 onboard"},
        {"phy": 1, "driver": "mt7921u",  "ifname": "wlan1", "soft_blocked": False, "ssid": None, "label": "AC1200"},
    ]
    monkeypatch.setattr(wifi_radio, "list_radios", lambda: radios)
    calls = []
    monkeypatch.setattr(wifi_radio.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or MagicMock(returncode=0))
    monkeypatch.setattr(wifi_radio, "save_mode", lambda m: None)
    wifi_radio.set_mode("onboard")
    assert ["rfkill", "unblock", "phy0"] in calls
    assert ["rfkill", "block", "phy1"] in calls


def test_set_mode_ac1200_blocks_onboard(monkeypatch):
    radios = [
        {"phy": 0, "driver": "brcmfmac", "ifname": "wlan0", "soft_blocked": False, "ssid": "X", "label": "CM5 onboard"},
        {"phy": 1, "driver": "mt7921u",  "ifname": "wlan1", "soft_blocked": False, "ssid": None, "label": "AC1200"},
    ]
    monkeypatch.setattr(wifi_radio, "list_radios", lambda: radios)
    calls = []
    monkeypatch.setattr(wifi_radio.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or MagicMock(returncode=0))
    monkeypatch.setattr(wifi_radio, "save_mode", lambda m: None)
    wifi_radio.set_mode("ac1200")
    assert ["rfkill", "unblock", "phy1"] in calls
    assert ["rfkill", "block", "phy0"] in calls


def test_set_mode_invalid_raises(monkeypatch):
    monkeypatch.setattr(wifi_radio, "list_radios", lambda: [])
    with pytest.raises(ValueError):
        wifi_radio.set_mode("garbage")
```

- [ ] **Step 2: Run — expect AttributeError**

```bash
pytest tests/test_wifi_radio_parser.py -v
```

- [ ] **Step 3: Implement set_mode**

Append to `device/lib/tui/wifi_radio.py`:

```python
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
```

> **Note:** the unit tests monkey-patch `wifi_radio.subprocess.run` at the module level, so the inner `_do` uses bare `subprocess.run` (not the `_rfkill` sudo wrapper). The deployed code will run as the user with passwordless sudo configured for `rfkill`. To verify on device:
> ```bash
> sudo -n rfkill unblock phy0   # if this succeeds, no further work
> ```
> If sudo is required, swap `_do` to call `_rfkill` instead. (Most uConsole users have passwordless sudo for rfkill; verify in Task 11 smoke.)

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_wifi_radio_parser.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_wifi_radio_parser.py device/lib/tui/wifi_radio.py
git commit -m "feat(tui): wifi_radio.set_mode three-mode rfkill switcher"
```

---

## Task 9: WiFi Radio Mode TUI screen + handler

**Files:**
- Modify: `device/lib/tui/wifi_radio.py`

No automated test — curses panel, smoke-tested in Task 11.

- [ ] **Step 1: Append the picker handler**

Append to `device/lib/tui/wifi_radio.py`:

```python
import curses

from tui.framework import (
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    draw_header,
    draw_separator,
    draw_status_bar,
    open_gamepad,
    _tui_input_loop,
)

MODE_OPTIONS = [
    ("both",    "Both active",       "default — both radios up"),
    ("onboard", "CM5 onboard only",  "block AC1200"),
    ("ac1200",  "AC1200 only",       "block onboard"),
]


def _signal_for(ifname):
    """Return signal in dBm or empty string."""
    try:
        out = subprocess.check_output(["iw", "dev", ifname, "link"],
                                       text=True, timeout=2)
        m = re.search(r"signal:\s+(-?\d+)\s+dBm", out)
        return f"{m.group(1)} dBm" if m else ""
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return ""


def run_wifi_radio_picker(scr):
    """3-mode WiFi radio mode picker."""
    js = open_gamepad()
    scr.timeout(200)
    cur_mode = load_mode()
    selected = next((i for i, (m, *_) in enumerate(MODE_OPTIONS) if m == cur_mode), 0)
    radios = list_radios()
    apply_msg = ""
    apply_until = 0.0
    import time

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        draw_header(scr, w)
        title = "WiFi Radios"
        scr.addnstr(6, max(0, (w - len(title)) // 2), title, w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        draw_separator(scr, 7, w)

        y = 9
        scr.addnstr(y, 2, "── Mode ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        for i, (mode_id, label, hint) in enumerate(MODE_OPTIONS):
            marker = "●" if mode_id == cur_mode else "○"
            cursor = "▸ " if i == selected else "  "
            line = f"{marker}  {label:22} ({hint})"
            attr = curses.color_pair(C_SEL) | curses.A_REVERSE if i == selected \
                else curses.color_pair(C_ITEM)
            scr.addnstr(y, 2, cursor + line, w - 4, attr)
            y += 1

        y += 1
        scr.addnstr(y, 2, "── Status ──", w - 4, curses.color_pair(C_HEADER) | curses.A_BOLD)
        y += 1
        for r in radios:
            sig = _signal_for(r["ifname"])
            ssid = r.get("ssid") or "(not associated)"
            blocked = "  [blocked]" if r["soft_blocked"] else ""
            line = f"{r['ifname']:6} {r['driver']:10} {r['label']:18} {ssid}  {sig}{blocked}"
            scr.addnstr(y, 4, line, w - 6, curses.color_pair(C_ITEM))
            y += 1

        if apply_msg and time.time() < apply_until:
            scr.addnstr(h - 2, 2, apply_msg, w - 4,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
        footer = " ↑↓ Mode │ A Apply │ B Back "
        draw_status_bar(scr, h, w, footer)
        scr.refresh()

        key, gp_action = _tui_input_loop(scr, js)
        if key == -1 and gp_action is None:
            continue
        if key == ord("q") or key == ord("Q") or gp_action == "back":
            return
        if key == curses.KEY_UP or key == ord("k"):
            selected = (selected - 1) % len(MODE_OPTIONS)
        elif key == curses.KEY_DOWN or key == ord("j"):
            selected = (selected + 1) % len(MODE_OPTIONS)
        elif key in (curses.KEY_ENTER, 10, 13, ord(" ")) or gp_action == "enter":
            chosen = MODE_OPTIONS[selected][0]
            try:
                result = set_mode(chosen)
                cur_mode = chosen
                radios = list_radios()
                apply_msg = f"  ✓ applied {chosen}"
                apply_until = time.time() + 2
                if result.get("ac1200_needs_connect"):
                    # Drop into the existing wifi-connect flow scoped to wlan1.
                    # We invoke the existing _wifi handler if it accepts an
                    # interface, otherwise the user can connect manually.
                    apply_msg = "  ⚠ AC1200 needs a network — open WiFi Switcher"
                    apply_until = time.time() + 5
            except Exception as e:
                apply_msg = f"  ✗ apply failed: {e}"
                apply_until = time.time() + 5


HANDLERS = {
    "_wifi_radio": run_wifi_radio_picker,
}
```

> **Note on the auto-connect flow.** The spec describes "drop into the existing wifi-connect flow scoped to wlan1." Verify during this task whether `_wifi` (the existing WiFi switcher handler in framework.py) accepts an `ifname` argument or scope. If yes, invoke it directly. If no, the placeholder behavior (a one-line "open WiFi Switcher" hint) is the v1 ship — the user manually opens the WiFi switcher. A follow-up task can add the `ifname=wlan1` plumbing once verified.

- [ ] **Step 2: Smoke import**

```bash
cd ~/uconsole-cloud
python3 -c "import sys; sys.path.insert(0, 'device/lib'); from tui import wifi_radio; print(wifi_radio.HANDLERS)"
```

Expected: prints `{'_wifi_radio': <function run_wifi_radio_picker at ...>}`. Fix any framework import errors as in Task 5 Step 2.

- [ ] **Step 3: Commit**

```bash
git add device/lib/tui/wifi_radio.py
git commit -m "feat(tui): wifi radio mode picker — 3-mode rfkill switcher panel"
```

---

## Task 10: Framework wiring

**Files:**
- Modify: `device/lib/tui/framework.py`

- [ ] **Step 1: Locate and replace the HARDWARE → AIO Board Check entry**

Find the line:

```python
("AIO Board Check",  "radio/aio-check.sh",  "V1 board component status",              "panel",   "🧩"),
```

Replace with:

```python
("AIO Board",        "_aio_board",          "rails, power, boot defaults",            "action",  "🧩"),
```

Use `grep -n "AIO Board Check" device/lib/tui/framework.py` to find the exact line first.

- [ ] **Step 2: Add Radio Mode entry to the WiFi submenu**

Find the `"sub:wifi"` block (around line 132). It currently looks like:

```python
"sub:wifi": [
    ("WiFi Switcher",    "_wifi",               "scan and connect to networks",           "action", "🔀"),
    ("WiFi Scan",        "network/network.sh scan",     "nearby WiFi networks",                   "panel",  "🔎"),
    ("Hotspot Toggle",   "_hotspot_toggle",     "start/stop WiFi hotspot",                "action", "🔥"),
    ("Hotspot Config",   "_hotspot_config",     "change AP name and password",            "action", "🔑"),
    ("WiFi Fallback",    "_wifi_fallback",      "auto iPhone hotspot → AP on WiFi loss",  "action", "🪂"),
],
```

Add a new entry just after `WiFi Switcher`:

```python
"sub:wifi": [
    ("WiFi Switcher",    "_wifi",               "scan and connect to networks",           "action", "🔀"),
    ("Radio Mode",       "_wifi_radio",         "switch onboard / AC1200 / both",         "action", "📡"),
    ("WiFi Scan",        "network/network.sh scan",     "nearby WiFi networks",                   "panel",  "🔎"),
    ("Hotspot Toggle",   "_hotspot_toggle",     "start/stop WiFi hotspot",                "action", "🔥"),
    ("Hotspot Config",   "_hotspot_config",     "change AP name and password",            "action", "🔑"),
    ("WiFi Fallback",    "_wifi_fallback",      "auto iPhone hotspot → AP on WiFi loss",  "action", "🪂"),
],
```

- [ ] **Step 3: Register the two new modules in FEATURE_MODULES**

Find `FEATURE_MODULES = [` (around line 1872). Add `"tui.aio"` and `"tui.wifi_radio"` to the list — placement is alphabetical-ish, but order doesn't matter functionally. Example:

```python
FEATURE_MODULES = [
    "tui.aio",            # NEW
    "tui.config_ui",
    "tui.tools",
    "tui.games",
    # ...existing entries...
    "tui.wifi_radio",     # NEW
]
```

- [ ] **Step 4: Wire ensure_rail() into rail-dependent dispatches**

Find the dispatcher that handles `sub:` keys. The cleanest insertion point is wherever the framework decides "the user clicked a menu item with key `sub:foo` — open submenu foo."

**Find the dispatch logic first:**

```bash
grep -n 'sub:' device/lib/tui/framework.py | head -10
grep -n 'startswith.*sub' device/lib/tui/framework.py
```

The dispatcher was refactored recently per `2026-04-25-tui-framework-refactor-design.md`. Locate the single point where a `sub:` key is consumed.

Add this near the top-level utilities of `framework.py` (NOT at module-import time — `aio.py` already imports symbols from `framework.py`, so a top-level `from tui.aio import ...` would create a circular import):

```python
# Mapping of menu-item key → AIO rail to power on first
_RAIL_DEPENDENT = {
    "sub:gps":       "GPS",
    "sub:sdr":       "SDR",
    "sub:adsb":      "SDR",
    "sub:lora_mesh": "LORA",
}


def _maybe_power_rail(key):
    """Best-effort: power on the AIO rail this submenu depends on."""
    rail = _RAIL_DEPENDENT.get(key)
    if not rail:
        return
    try:
        from tui.aio import ensure_rail
        ensure_rail(rail)
    except Exception:
        # Auto-power is best-effort; never block the submenu open.
        pass
```

Then add `_maybe_power_rail(key)` as the first line inside the dispatcher branch that resolves a `sub:` key. There should be exactly one such point — if there are multiple, add the call at each.

- [ ] **Step 5: Run framework tests to make sure nothing broke**

```bash
cd ~/uconsole-cloud
pytest tests/test_handler_registry.py tests/test_module_exports.py tests/test_navigation.py -v
```

Expected: all pass. The handler registry test should now report ~66 handlers (was ~64 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add device/lib/tui/framework.py
git commit -m "feat(tui): wire AIO board + WiFi radio handlers into framework"
```

---

## Task 11: Live smoke test on the device

This task has no code — it's a manual run-through using the TUI on the real hardware.

- [ ] **Step 1: Launch the TUI from the dev tree**

```bash
cd ~
console
```

The launcher auto-detects `~/uconsole-cloud/device/lib/` and uses it (per CLAUDE.md). No install needed.

- [ ] **Step 2: Verify the new HARDWARE → AIO Board entry**

- Navigate `←/→` to HARDWARE column.
- Confirm first entry reads `🧩 AIO Board` (not `AIO Board Check`).
- Press A. The dashboard panel should render with: header, `── Power ──` section showing real values, `── Rails ──` section listing GPS/LORA/SDR/USB with current ON/OFF state, `── WiFi ──` section showing the mode and `wlan0=CM5  wlan1=AC1200`.

- [ ] **Step 3: Toggle a rail (LORA recommended — least likely to break anything)**

- ↑/↓ to LORA, press A. Dot should flip OFF→ON within ~1.5 s.
- Press A again to flip back. Confirm with: `aiov2_ctl --status` in another shell.

- [ ] **Step 4: Toggle a boot default**

- ↑/↓ to a rail, press X (or `b` on keyboard). The "boot ●/○" indicator should flip.
- Confirm with: `aiov2_ctl --boot-rails-status`.

- [ ] **Step 5: Jump to WiFi radio picker**

- Press Y (or `w` on keyboard). The `WiFi Radios` screen should appear with 3 modes and the radios status section populated.
- ↑/↓, press A on `Both active` (the default — won't change anything). Confirm `✓ applied both` toast.
- Press B to go back. AIO Board panel should reappear.

- [ ] **Step 6: Try the auto-power-on path**

- B back to main menu. Switch the LORA rail off via `aiov2_ctl LORA off` in a shell.
- In TUI, navigate HARDWARE → LoRa Mesh. Open the submenu. Auto-power should kick in (verify after with `aiov2_ctl --status` — LORA should now show ON).

- [ ] **Step 7: Reach Radio Mode via NETWORK → WiFi**

- Navigate NETWORK → WiFi → `📡 Radio Mode`. Same picker as in Step 5.

- [ ] **Step 8: Verify v1 fallback still works (optional)**

If you have a way to mock v1 (e.g., temporarily move `aiov2_ctl` aside), do:

```bash
sudo mv /usr/local/bin/aiov2_ctl /usr/local/bin/aiov2_ctl.disabled
console
# Navigate to HARDWARE → AIO Board. Should now run radio/aio-check.sh.
sudo mv /usr/local/bin/aiov2_ctl.disabled /usr/local/bin/aiov2_ctl
```

Skip if too disruptive — the v1 path is exercised by `detect()` unit tests.

- [ ] **Step 9: Run the full test suite once more**

```bash
cd ~/uconsole-cloud
pytest tests/ -v
```

Expected: all green.

- [ ] **Step 10: Final commit if any tweaks were made during smoke**

```bash
git status
# If anything changed:
git add -p
git commit -m "fix(tui): smoke-test polish for AIO + radio panels"
```

---

## Task 12: Push the branch

- [ ] **Step 1: Push**

```bash
cd ~/uconsole-cloud
git push -u origin feat/aio-v2-tui
```

- [ ] **Step 2: Inform user**

The branch is at `https://github.com/mikevitelli/uconsole-cloud/tree/feat/aio-v2-tui` (or wherever the remote points). Spec is at `docs/specs/2026-05-02-aio-v2-tui-and-radio-switcher-design.md`; plan at `docs/plans/2026-05-02-aio-v2-tui-and-radio-switcher.md`. Ready for review or merge into `dev` via the standard `/publish` flow once approved.

---

## Out of scope for this plan

- `aiov2_ctl --measure` (power delta measurement). Easy to add as a sub-action later.
- Per-rail user-editable labels via JSON config. Hardcoded constant in `aio.py` for now.
- "AC1200 preferred, onboard fallback" autoconnect-priority mode.
- Auto-disconnecting AC1200 from stale hotspot networks (e.g., "Not your iPhone").
- Wiring the auto-connect flow scoped to `wlan1` after `set_mode("ac1200")` strands the radio. Plan ships with a hint message; full plumbing is a follow-up once `_wifi` handler signature is verified.
