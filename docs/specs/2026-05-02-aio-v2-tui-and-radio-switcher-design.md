# AIO v2 TUI + WiFi Radio Switcher — Design

**Date:** 2026-05-02
**Status:** Spec
**Branch:** `dev`
**Scope:** `device/lib/tui/aio.py` (new), `device/lib/tui/wifi_radio.py` (new), `device/lib/tui/framework.py` (menu wiring + auto-power dispatch)

## Why

The CM5 swap (2026-05-02) brought the HackerGadgets AIO v2 board, which power-gates four peripherals (GPS, LORA, SDR, USB) behind GPIO rails. Default boot state is rails-off. Today the TUI assumes those peripherals are always powered — opening `LoRa Mesh` with the LORA rail off silently fails. The user has a working desktop GUI for rail control (`aiov2_ctl --gui` from the `hackergadgets-uconsole-aio-board` package) but no TUI equivalent.

Same upgrade also added an AC1200 (MediaTek MT7921 USB) WiFi 6 module that lives alongside the CM5 onboard Broadcom radio. Two radios, no UI to pick which one is primary.

Goal: TUI controls that mirror the AIO v2 GUI (rails + boot defaults + power telemetry), an auto-power-on hook so rail-dependent submenus "just work," and a three-mode WiFi radio switcher. Must remain usable on AIO v1 hardware.

## What

### 1. Board detection (`aio.detect()`)
error     /home/mikevitelli/.npm/_logs/2026-04-13T02_06_44_961Z-debug-0.log
Returns `"v2"` if `/usr/local/bin/aiov2_ctl` exists and is executable, else `"v1"`. Cached for the lifetime of the TUI process. No per-render re-checks.

### 2. AIO dashboard panel (v2 only)

New module `lib/tui/aio.py`. Full-screen TUI panel rendered from `aiov2_ctl --status` output (parser handles the existing fixed text format: four `FEATURE GPIO_n: ON|OFF` lines plus labelled `Source / Status / Capacity / Mode / Voltage / Current / Power` fields). Auto-refresh every 1.5 s while focused; immediate re-render after any toggle.

Renders inside the standard TUI chrome — global `HEADER` art at top, centered title row in `C_HEADER | A_BOLD`, `draw_separator`, sectioned content, `draw_status_bar` at the bottom. No outer ASCII box.

Layout (showing only the panel-specific content, between header and status bar):

```
                        AIO v2 — Rails & Power
─────────────────────────────────────────────────────────────

  ── Power ──
    Mode       AC powering system + battery
    Power      3.86 W       Battery  89%  (Charging)

  ── Rails ──
  ▸ GPS    ●  ON     boot ●     uBlox NEO
    LORA   ○  OFF    boot ○     SX1262
    SDR    ○  OFF    boot ○     RTL-SDR
    USB    ●  ON     boot ●     AC1200

  ── WiFi ──
    Both active     wlan0=CM5 onboard     wlan1=AC1200
```

Footer (replaces global `FOOTER_HELP` while panel is focused):

```
 ↑↓ Rail │ A Toggle │ X Boot Default │ Y WiFi Radios │ B Back
```

Input model — gamepad-first, with keyboard fallbacks:

| Action | Gamepad | Keyboard |
|---|---|---|
| Move selection up/down between the 4 rails | ↑ / ↓ | ↑ / ↓ |
| Toggle the selected rail (live) | `GP_A` | Enter / Space |
| Toggle the selected rail's boot default | `GP_X` | `b` |
| Jump to WiFi Radio Mode screen (Section 4) | `GP_Y` | `w` |
| Back | `GP_B` | `q` / Backspace |

Both `GP_A` (toggle live) and `GP_X` (boot default) use optimistic UI: flip the indicator dot immediately, revert + show one-line error in `C_STATUS` color above the footer on non-zero exit. The next 1.5 s refresh re-syncs from truth.

Selected row uses the existing `C_SEL` reverse-video pair (same as menus). On/off dots use `C_STATUS` (green) for `●` and the muted `C_ITEM` for `○`.

No safety guard on USB toggle — the row label (`AC1200`) makes the cost visible. The internal USB-C is single-occupancy: AC1200 *or* ESP32, not both. Currently AC1200; swap requires editing the constant.

Per-rail "what's plugged in here" labels are hardcoded as a constant in `aio.py`:

```python
RAIL_LABELS = {
    "GPS":  "uBlox NEO",
    "LORA": "SX1262",
    "SDR":  "RTL-SDR",
    "USB":  "AC1200",  # currently AC1200; swap to "ESP32" if you re-cable
}
```

If hardware ever changes per rail, edit the constant. Not worth a config file yet.

### 3. Auto-power-on helper

`aio.ensure_rail(name)` — called by framework dispatch before entering rail-dependent menu items.

- v1 board: no-op, returns `True`.
- v2, rail already ON: returns `True`.
- v2, rail OFF: runs `aiov2_ctl name on`. On success, flashes one-line toast at top of next screen (`↑ powered on GPS rail`). Returns `True`.
- v2, toggle failed: returns `False`. Caller proceeds anyway (degrades gracefully).

Mappings (wired in `framework.py` action dispatcher, not inside the submenu modules):

| Menu entry           | Rail to ensure |
|----------------------|----------------|
| `GPS Receiver` submenu (`sub:gps`) | `GPS` |
| `SDR Radio` submenu (`sub:sdr`) | `SDR` |
| `ADS-B Map` submenu (`sub:adsb`) | `SDR` |
| `LoRa Mesh` submenu (`sub:lora_mesh`) | `LORA` |
| `ESP32` action (`_esp32_hub`) | none — internal USB-C is currently AC1200, not ESP32; if user re-cables to ESP32 they toggle USB themselves |
| `Watch Dogs Go` game (`_watchdogs`) | none — sometimes-fun, not daily-use |

### 4. WiFi radio switcher (`wifi_radio.py`)

New module. Three responsibilities:

**Detect both radios.** Walk `/sys/class/ieee80211/phy*`, map driver to friendly name:
- `brcmfmac` → "CM5 onboard"
- `mt7921u` → "AC1200 (WiFi 6)"
- anything else → driver string verbatim

Returns `[{phy, ifname, driver, label, ssid, soft_blocked, rfkill_id}]`. `ssid` from `iw dev`; `soft_blocked` and `rfkill_id` from `rfkill list`. `rfkill_id` is the numeric id from `rfkill list` (util-linux rfkill rejects device-name identifiers like `phy0` — must use numeric ID). `None` if the radio isn't in rfkill list. (Per-row signal strength is fetched separately by the picker via `iw dev <ifname> link` — kept out of `list_radios` because it requires a per-iface subprocess call.)

**Three-mode switcher.** `set_mode(mode)` where `mode ∈ {"onboard", "ac1200", "both"}`:
- `onboard`: `rfkill unblock <onboard.rfkill_id>` + `rfkill block <ac1200.rfkill_id>`.
- `ac1200`: inverse. If AC1200 has no active connection after unblock, drop into the existing wifi-connect flow (from `network/wifi.sh`) scoped to `wlan1`.
- `both`: `rfkill unblock` for each radio's `rfkill_id`. No further action.

Mode persists to `~/.config/uconsole/wifi_radio_mode` (single-line text file, content is one of `onboard|ac1200|both`) so the dashboard shows the chosen mode on next launch. NetworkManager itself has no state for this — rfkill is the source of truth at runtime; the file is presentational only.

If `network/wifi.sh` has no `--ifname` flag for scoping to `wlan1`, the implementation either adds one or shells `nmcli device wifi connect ... ifname wlan1` directly. To verify during planning.

**TUI screen** at `NETWORK → WiFi → Radio Mode`. Same chrome conventions as the AIO panel — global header, centered title, `draw_separator`, `draw_status_bar`. Panel-specific content:

```
                          WiFi Radios
─────────────────────────────────────────────────────────────

  ── Mode ──
  ▸ ●  Both active            (default — both radios up)
    ○  CM5 onboard only       (block AC1200)
    ○  AC1200 only            (block onboard)

  ── Status ──
    wlan0  brcmfmac    CM5 onboard       Big Parma  -54 dBm
    wlan1  mt7921u     AC1200 (WiFi 6)   Not your iPhone -71
```

Footer:

```
 ↑↓ Mode │ A Apply │ B Back
```

Input model:

| Action | Gamepad | Keyboard |
|---|---|---|
| Move selection up/down between the 3 modes | ↑ / ↓ | ↑ / ↓ |
| Apply the selected mode | `GP_A` | Enter / Space |
| Back | `GP_B` | `q` / Backspace |

Currently-active mode shows `●`, others show `○`. Selected row uses `C_SEL`. After `Apply`, if the chosen mode strands AC1200 with no connection, the existing wifi-connect flow (gamepad-driven SSID picker) takes over scoped to `wlan1`, then returns here.

Switching is brute-force rfkill, not NetworkManager `autoconnect-priority`. Rfkill is legible — the disabled radio literally doesn't exist while blocked, so behavior is predictable. Priority-based "AC1200 preferred, onboard fallback" is deferred until both radios are actively used in production.

### 5. Menu wiring (`framework.py`)

HARDWARE column — replace existing entry:
```python
# was:
("AIO Board Check", "radio/aio-check.sh", "V1 board component status", "panel", "🧩"),
# becomes:
("AIO Board",       "_aio_board",         "rails, power, boot defaults", "action", "🧩"),
```

`_aio_board` handler dispatches: v2 → new dashboard from `aio.py`; v1 → existing `radio/aio-check.sh` panel run as a stream-output action. `aio-check.sh` itself is unchanged.

`WiFi` submenu (under NETWORK) — add one entry:
```python
("Radio Mode", "_wifi_radio", "switch onboard / AC1200 / both", "action", "📡"),
```

Action dispatcher gets a small switch that wraps the rail-dependent entries with `aio.ensure_rail(...)` per the table in Section 3.

## Files

| File | Change | Approx LOC |
|---|---|---|
| `device/lib/tui/aio.py` | NEW. `detect()`, `ensure_rail()`, dashboard panel, `aiov2_ctl --status` parser. | ~250 |
| `device/lib/tui/wifi_radio.py` | NEW. Radio detection, three-mode switcher, TUI screen, `iw dev` and `rfkill list` parsers. | ~200 |
| `device/lib/tui/framework.py` | Replace HARDWARE entry, add `_aio_board` and `_wifi_radio` handlers, wire `ensure_rail()` into 4 submenu dispatches. | ~30-line diff |
| `device/scripts/radio/aio-check.sh` | No change — still called for v1 boards via auto-detect. | 0 |

## Failure model

- **`aiov2_ctl` missing on a "v2" path.** Detection requires the binary to exist, so this can't happen. If the binary is removed at runtime, next refresh fails the parser, dashboard shows `! aiov2_ctl --status failed` and stops auto-refreshing.
- **Toggle subprocess fails.** Optimistic UI revert + one-line error at the bottom of the panel. Next refresh re-syncs from truth.
- **`ensure_rail` fails.** Returns `False`, the caller proceeds anyway and the user sees whatever broken state the underlying tool produces. This matches today's behavior (the TUI already assumes rails are on); we're not making it worse.
- **rfkill block of currently-active radio drops user's connection.** Expected behavior of the chosen mode. The screen makes the trade explicit before "apply."
- **Radio-mode switch when neither radio is connected after rfkill.** User lands in the `network/wifi.sh` connect flow on the surviving interface. Existing flow handles "no networks found."
- **v1 board with `aiov2_ctl` somehow installed** (manual install, no actual v2 board). Dashboard renders but rail toggles return errors because the GPIO pins aren't wired. Acceptable — out-of-spec configuration.

## Testing

Unit tests for the two parsers (`aiov2_ctl --status` text → dict, `iw dev` text → radio list) using fixture strings captured from the live device. Live-test the interactive TUI on the device — `console` is fast to relaunch.

No tests for `set_mode` or `ensure_rail` (subprocess wrappers, exercised by manual smoke).

## Out of scope

- `aiov2_ctl --measure FEATURE` (power delta measurement). The GUI doesn't surface it; we don't either. Easy to add as a sub-action later.
- Per-rail user-editable labels via JSON config. Hardcoded constant for now.
- "AC1200 preferred, onboard fallback" autoconnect-priority mode. Defer until both radios are in active use.
- `/dev` skill integration (live install + test on device). Standard publish flow handles it.
