# TUI Battery / Power Config — Design

- **Date:** 2026-06-16
- **Status:** Draft (brainstormed, pending review)
- **Branch:** `feat/battery-config-tui`
- **Target release:** v0.4 (after v0.3.1 ships)

## 1. Motivation & framing

v0.3.1 **retired** the device-specific battery stack (`pmu-voltage-min`,
`cpu-freq-cap`, `low-battery-shutdown`, `axp-voff-shutdown`). That stack was
hardcoded (i2c bus 0, 2.9 V VOFF, 18650-tuned thresholds) and wrote the PMIC
over **raw `i2cset`** — non-persistent and bypassing every kernel guard.

This feature is the **safe, generic, configurable replacement**: a Power /
Battery section in the TUI config screen that drives battery behaviour from
per-user config through **sysfs + udev** (kernel-guarded, persistent), never
raw register pokes.

**Public mechanism, personal values.** The config UI ships in `uconsole-cloud`
for everyone. Each user's chosen values live in their own
`~/.config/uconsole/console.json`; defaults are **no-ops** (nothing changes
until a user opts in), so other people's varied builds are untouched. Builds
vary widely — CM4 vs CM5, 18650 vs 1S LiPo vs 2S 21700 conversions, weak vs
high-drain cells — so the design favours **maximum configurability with
guardrails** over abstracted-away simplicity.

## 2. Goals / non-goals

**Goals**
- Expose every *safely software-configurable* battery/power parameter the
  AXP228 + kernel actually support, with hard safety clamps.
- Chemistry/build profiles as presets that pre-fill knobs; a "Custom" profile
  unlocks individual editing.
- Persist settings across reboot via sysfs + udev (not raw i2c).
- Reintroduce graceful low-battery warn/shutdown as a **generic, config-driven,
  chemistry-aware** monitor (replacing the retired 18650-specific one).

**Non-goals (YAGNI / safety)**
- No raw register editor; no write access to charge target > 4.2 V, rail
  (DCDC/LDO) registers, or NTC/temperature-monitor disable.
- No hardware brownout cure (that's a 2S+buck conversion — out of scope).
- No backlight *driver*; we only optionally surface a battery-saver backlight
  cap if the existing brightness control is reusable (Phase 2 decision).

## 3. Background — what is actually software-configurable (verified on-device)

Kernel driver: `x-powers,axp221-battery-power-supply` at i2c `3-0034`
(`/sys/class/power_supply/axp20x-battery/`). Writable sysfs knobs confirmed
live on this device:

| sysfs node | current | kernel-enforced range | meaning |
|---|---|---|---|
| `voltage_max` | 4.20 V | **4.1 or 4.2 V only** (>4.2 → `-EINVAL`) | charge target → **longevity knob** |
| `constant_charge_current[_max]` | 900 mA | 300–2100 mA (150 mA step) | charge speed vs heat |
| `voltage_min` | 2.90 V | 2.6–3.3 V | ⚠ **fuel-gauge 0% reference only — NOT the hard cutoff** |
| `calibrate` | — | write `1` | gauge recalibration |

cpufreq (`/sys/devices/system/cpu/cpufreq/policy0/`, perm 644):
- `scaling_governor` ∈ {conservative, ondemand, userspace, powersave,
  performance, schedutil}
- `scaling_max_freq` / `scaling_min_freq` ∈ 1.5–2.4 GHz (100 MHz steps)

**Key research findings shaping the design** (sources in §9):
- The **4.1 V "Longevity" charge cap** ≈ **doubles cycle life** for ~10%
  capacity; kernel-guarded; *nobody in the ClockworkPi community does it* —
  novel but battery-science-sound. This is the standout feature.
- **`voltage_min` is only the gauge zero-point**, not over-discharge
  protection. Real protection = the **software graceful-shutdown threshold**.
- **Raw i2c writes don't persist and bypass kernel guards** → always use
  sysfs + udev.
- CM5 brownout is fundamentally **hardware boost-sag** (freezes < 3.8 V under
  ~2 A; ~3.18 V hard floor under load; CM5 ≈ 2× CM4 draw). Software only
  mitigates. **Backlight is a bigger lever than CPU** (1.94 W off vs 4.13 W
  max — a 2.1 W swing).
- Recommended graceful shutdown ≈ **3.4–3.5 V resting / ~15–20%**, biased up
  for aged/high-Ri packs; never below **3.0 V resting**.
- **Danger list (never expose):** charge target > 4.2 V, charge current > 2 A,
  rail (DCDC/LDO) registers, NTC-disable, any raw i2c.

## 4. Config schema (`console.json` → `battery.*`)

```jsonc
"battery": {
  "profile": "custom",          // 18650 | lipo_1s | li_2s | custom
  "chemistry": "lipo",          // liion | lipo
  "cells": 1,                   // 1 | 2  (per-cell ↔ pack voltage math)
  "capacity_mah": 3500,         // runtime estimate
  "voltage_display": "per_cell",// per_cell | pack
  "charge_limit_mv": 4200,      // 4100 | 4200            (→ voltage_max)
  "charge_current_ma": 900,     // 300–2000 (clamped)     (→ constant_charge_current)
  "warn_mv": 3550,              // per-cell resting
  "shutdown_mv": 3400,          // per-cell resting, clamp ≥3000 (research: ~3.4–3.5 V)
  "monitor_poll_s": 30,
  "monitor_hysteresis_mv": 80,
  "power_profile": "balanced",  // saver | balanced | performance | custom
  "governor": "ondemand",       // custom only
  "max_freq_khz": 2400000,      // custom only
  "min_freq_khz": 1500000,      // custom only
  "saver_backlight_pct": null,  // optional, null = off
  "voff_mv": null               // advanced, clamp 3000–3300, null = leave kernel default
}
```

All numeric fields are **clamped on write** (UI) *and* **re-validated by the
applier** (defence in depth). `null`/absent = no-op.

## 5. TUI layout (`config_ui.py` → new Power/Battery section)

```
POWER / BATTERY
 A · TELEMETRY (read-only)
     voltage (pack + per-cell) · current · charge % · state · draw(W) · est runtime · temp*
 B · BUILD PROFILE            ← presets pre-fill C–F; "Custom" unlocks all
     Profile · Chemistry · Cell count (1S/2S) · Capacity mAh · Voltage display
 C · CHARGE (sysfs, guarded)
     Charge limit: Full 4.2V · Longevity 4.1V        ⭐
     Max charge current: 300–2000 mA
 D · DISCHARGE PROTECTION (software monitor)
     Warn at (V/%) · Graceful shutdown (V/%) · [adv] poll · hysteresis
 E · PERFORMANCE / SAG (cpufreq)
     Power profile: Saver · Balanced · Performance · Custom
     [Custom] Governor · Max freq · Min freq
     [optional] Battery-saver backlight cap
 F · ADVANCED ⚠ (confirm-gated, clamped)
     Fuel-gauge floor (voltage_min) 3.0–3.3 V  "gauge ref, not a cutoff"
     Recalibrate gauge (→ sysfs calibrate)
     — no raw register editor
```

Follows existing `config_ui.py` picker patterns (gamepad nav, `load_config` /
`save_config`). Section appears via the standard feature-isolation path; a
device that can't read the AXP sysfs nodes hides the section gracefully.

### Profiles (presets)

| Profile | charge_limit | shutdown_mv (per-cell) | charge_current | notes |
|---|---|---|---|---|
| 18650 | 4200 | 3450 | 900 | high-Ri/low-drain → shutdown biased up for sag |
| 1S LiPo | 4200 | 3400 | 900 | default for stock-ish builds |
| 2S 21700 | 4200 | 3400 | configurable | `cells=2`; pack math ×2 |
| Custom | (unlocked) | (unlocked) | (unlocked) | all knobs editable |

Picking a profile pre-fills C–F; switching to Custom keeps current values and
unlocks editing. Per-cell values; the monitor multiplies by `cells` for pack
voltage. (Final preset numbers reviewed in implementation.)

## 6. Architecture — config → behaviour

```
TUI config_ui.py (runs as user)
  └ writes console.json (battery.*)
      └ privileged applier  [mechanism TBD — see §7]
          ├ C, F → regenerate /etc/udev/rules.d/99-uconsole-battery.rules
          │         (voltage_max, constant_charge_current[_max], voltage_min)
          │         + immediate sysfs write   → persists across reboot
          ├ D    → uconsole-low-battery monitor service reads thresholds
          │         (generic rewrite; polls sysfs voltage; warn + graceful poweroff)
          └ E    → perf applier sets scaling_governor + scaling_max/min_freq
```

**Components**
1. `tui/config_ui.py` — new Power/Battery section + pickers (Phase 1–3).
2. Config schema in `console.json` (§4).
3. **`uconsole-battery-apply`** helper — validates/clamps `battery.*`,
   regenerates the udev rule, writes sysfs live. Idempotent.
4. **`uconsole-low-battery` monitor** — generic, chemistry-aware rewrite of the
   retired service: reads `warn_mv`/`shutdown_mv`/`cells`, polls resting
   voltage with hysteresis, warns then graceful `poweroff`. Enabled by setup
   wizard.
5. **Perf applier** — governor + freq from config (systemd oneshot or folded
   into the helper).

## 7. Open question — privilege / apply path (resolve in writing-plans)

The TUI runs as the user; writing sysfs/udev needs root. Two candidates,
**to be decided after auditing existing repo sudo/helper conventions**
(`uconsole-passwd`, postinst, existing NOPASSWD entries):

- **A — sudo helper:** TUI calls `sudo uconsole-battery-apply` (single
  NOPASSWD entry). Simple, synchronous, easy to surface validation errors back
  to the UI. *Leaning this way* given existing `/opt/uconsole/bin` helper
  pattern.
- **B — systemd path-watch:** root unit watches `console.json`, re-applies on
  change. No sudo in TUI, fully decoupled, but async — harder to report apply
  errors in the UI.

## 8. Safety model

- **Hard clamps** (UI + applier): charge current ≤ 2000 mA; `voltage_min` ≥
  3.0 V; `shutdown_mv` ≥ 3.0 V resting; charge target ∈ {4.1, 4.2}; freq within
  the kernel's available list.
- **Confirm-gate** tier F.
- **Never exposed / never written:** charge target > 4.2 V, rail (DCDC/LDO)
  registers, NTC-disable, raw `i2cset`.
- `voltage_min` always labelled as the gauge reference, not a safety cutoff.
- Defaults are no-ops; an absent/`null` field changes nothing.
- Applier validates independently of the UI (never trust the config blindly).

## 9. Phasing

- **Phase 1 (safety core):** telemetry (A) + charge limit/current (C) +
  warn/shutdown monitor (D) + config schema + `uconsole-battery-apply` +
  monitor rewrite. Shippable on its own.
- **Phase 2 (sag):** power profiles + governor/freq (E); optional backlight cap.
- **Phase 3 (advanced):** build profiles incl. 2S/cell-count math (B) + VOFF +
  calibrate (F).

## 10. Testing

- Pure helpers (clamp/validate, profile→knob mapping, per-cell↔pack math,
  udev-rule generation) unit-tested with fixtures (matches existing
  `tui` fixture-backed test pattern).
- Applier dry-run mode (`--check`) asserts the generated udev rule + intended
  sysfs writes without touching hardware.
- Monitor: feed synthetic voltage series, assert warn/shutdown transitions and
  hysteresis.
- Manual on-device: confirm sysfs writes land, persist across reboot, and
  defaults are true no-ops.

## 11. Open items to resolve in the plan

- Privilege/apply mechanism (§7).
- Whether the uConsole wires an NTC to the AXP TS pin (affects whether any
  temp telemetry is real) — verify, don't assume.
- Whether the existing brightness control is reusable for the saver backlight
  cap (Phase 2).
- Final profile preset numbers (per-chemistry shutdown/charge defaults).
- 2S pack voltage math + display (Phase 3).

## 12. Sources

Kernel `drivers/power/supply/axp20x_battery.c`; AXP22X LKML patch series;
linux-sunxi AXP221/AXP209 register maps; forum.clockworkpi.com threads
(max-charging-current-axp228 #14139, cm5-building #16784 [Rex],
fixing-power-delivery-cm5 #19119, battery-benchmark #21722); Battery University
BU-501a/802c/808; github SuSonicTH/uConsole power measurements; assada power
gist. (Full per-claim citations captured in the brainstorming research pass.)
