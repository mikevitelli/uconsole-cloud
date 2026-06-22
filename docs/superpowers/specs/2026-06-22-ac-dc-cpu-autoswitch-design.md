# AC/DC-aware CPU frequency auto-switching

**Date:** 2026-06-22
**Status:** PAUSED — review applied; resume blocked on GATE 0 (confirm udev fires
on AC plug/unplug) before writing the implementation plan
**Branch:** `feat/cpu-freq-scaling`

## Problem

The uConsole (CM5) browns out on battery. The CM5 draws roughly 2× the
transient current of the CM4, and the stock 1S boost board sags below 4.75 V
under load; once the rail sags far enough the AXP228 PMU I2C wedges and power is
cut. CPU turbo spikes (up to 2.4 GHz) are a significant contributor to those
transient draws.

We want the device to **cap CPU frequency low when running on battery** (to
flatten the current spikes) and **allow full speed when on AC** (where rail sag
is not a concern). The switch must be automatic, react to plugging/unplugging,
and be a feature users can opt into.

This is a runtime mitigation, not a cure. The full cure is a hardware power
path change (high-drain cells / 2S + buck). This feature reduces the frequency
of brownouts in the meantime and costs nothing on AC.

## Goals

- On **battery (DC)**: lock CPU to 1500/1500 MHz (no turbo).
- On **AC**: allow 1500/2400 MHz with the `ondemand` governor (idles cool at
  1.5 GHz, bursts to the stock 2.4 GHz ceiling on demand).
- Switch automatically on AC plug/unplug, and come up already capped at boot
  (steady-state; see the boot-coverage caveat under "Scope of brownout coverage").
- Ship as a package feature with a **TUI toggle, disabled by default**.
- Pure runtime / sysfs. No `config.txt` overclock, no reboot, fully reversible.

## Non-goals

- **No overclock above 2.4 GHz.** The stock kernel ceiling is 2.4 GHz
  (`cpuinfo_max_freq`). Going higher needs `config.txt` `arm_freq`/`over_voltage`
  + reboot, which is a *boot-time* setting that cannot be made conditional on
  power source — and would *worsen* the very brownouts we are fixing. Explicitly
  out of scope.
- No per-device custom frequency tuning UI. Two fixed states (DC / AC). Tunable
  values can be added later via a conf key if ever needed.
- No reverting of the current frequency when the feature is disabled (see Error
  handling).

## Scope of brownout coverage (honest limits)

This feature reliably addresses **in-use, steady-state** battery brownouts — the
documented failure mode where sustained multi-core load (e.g. 4-core `stress-ng`)
on battery sags the rail until the PMU cuts. On battery it pins the CPU at
1.5 GHz, removing the turbo-driven current spikes.

It gives only **best-effort** coverage of the *boot-time* current spike. The udev
rule fires at coldplug, which runs **after** the kernel has brought all four
cores online and systemd has begun launching services — i.e. after the worst
early-boot ramp. So the device comes up already capped for steady-state, but the
boot transient itself is largely past by the time the rule applies. The only
real lever for the boot spike is the `config.txt` `arm_freq`/`arm_boost` route,
which is deliberately out of scope (see Non-goals) because it cannot be made
power-source-conditional and would itself raise draw. The spec does **not**
promise boot-spike suppression.

## Existing building blocks (reused, not rebuilt)

- **`scripts/power/cpu-freq.sh`** — already does all sysfs min/max/preset writes,
  with a sudo-tee fallback when the path is not directly writable. This is the
  single source of truth for frequency writes; the new behavior is a verb on it,
  not a new script.
- **AC detection** — `/sys/class/power_supply/axp22x-ac/online` (`1` = AC,
  `0` = battery).
- **Marker-file toggle convention** — the package already ships
  `/etc/uconsole/wardrive-enabled` as a zero-byte opt-in marker. We follow the
  same convention for the enable flag.
- **udev** — the native event source for power-supply state changes.

### Pattern note (why not the `wifi-fallback.sh` dispatcher shape)

`wifi-fallback.sh` is the device's other event-reactive feature and uses a
self-installing dispatcher with `install`/`uninstall` verbs, a debounce cooldown
file, and a symlink-attack guard. Those exist because WiFi failover genuinely
flaps and needs runtime (re)install. CPU power switching has none of those
properties:

- Power transitions are human-paced (plugging a cable), seconds apart — no
  flapping, so **no debounce**.
- Frequency writes are idempotent — re-applying the same state is harmless.
- The `.deb` installs files — a self-installing udev rule would reinvent dpkg, so
  **no `install`/`uninstall` verbs**.
- The flag lives in root-owned `/etc` — **no symlink-attack guard** needed.

So we deliberately keep the proven *primitives* (udev events + marker-file
toggle) and drop the scaffolding that does not pay rent here.

## Design

### Components

1. **New verb `apply-power` in `scripts/power/cpu-freq.sh`**

   ```sh
   apply-power)
       # No-op unless the feature is enabled (marker file present).
       [ -e /etc/uconsole/cpu-auto-enabled ] || exit 0
       if [ "$(cat /sys/class/power_supply/axp22x-ac/online 2>/dev/null)" = 1 ]; then
           write_freq min 1500; write_freq max 2400   # AC: burst to 2.4
       else
           write_freq min 1500; write_freq max 1500   # battery: locked low
       fi ;;
   ```

   Reuses the existing `write_freq` helper (sudo-tee fallback). When invoked by
   udev it runs as root, so writes are direct. The **governor is not touched** —
   it stays at the system default `ondemand` (as do the existing `cpu-freq.sh`
   presets), which is what makes the AC 1500/2400 range burst on demand. On
   battery, min==max makes the governor moot.

2. **New verb `auto on|off|toggle|status` in `scripts/power/cpu-freq.sh`**

   - `on` — create `/etc/uconsole/cpu-auto-enabled`, then run `apply-power`
     immediately so state is correct without waiting for the next event.
   - `off` — remove the marker, then release the cap: set min→1500
     (`cpuinfo_min_freq`) and max→2400 (`cpuinfo_max_freq`). This is "remove the
     cap" semantics (back to stock range), not "restore a remembered state."
   - `toggle` — flip based on marker presence.
   - `status` — print enabled/disabled, current AC/DC source, current min/max.

   Marker writes use the same sudo-tee/`sudo rm` fallback as `write_freq` so the
   TUI (running as the user) can toggle without a new sudoers entry.

3. **New udev rule `system/etc/udev/rules.d/90-uconsole-cpu-power.rules`**

   ```
   # Narrow form — preferred IF the AC device emits the event (see gate below):
   KERNEL=="axp22x-ac", ACTION=="add|change", RUN+="/opt/uconsole/scripts/power/cpu-freq.sh apply-power"

   # Broad fallback — only if the battery device, not the AC device, drives it:
   # SUBSYSTEM=="power_supply", ACTION=="add|change", RUN+="/opt/uconsole/scripts/power/cpu-freq.sh apply-power"
   ```

   Matching **both `add` and `change`** is what gives correct boot state for
   free: udev coldplugs `add` events at boot (it does not emit `change` then), so
   matching only `change` would miss boot. With both matched, no separate
   oneshot service is required.

   When invoked by udev the script runs as **root**, so `write_freq` always takes
   the direct-write branch and never the `sudo tee` fallback (no password prompt,
   no sudoers entry needed in this path).

   > **⚠ UNVERIFIED — build-time gate (review item #3).** Whether the AXP AC
   > driver emits a udev event on plug/unplug was **not** confirmed on-device
   > (two capture attempts caught no cable toggle — `online` stayed `0`
   > throughout, so the cable was never switched, not that udev was silent).
   > Driver architecture *suggests* it does: `axp20x_ac_power` registers ACIN
   > plug-in/removal IRQs whose handlers call `power_supply_changed()`, which
   > emits a `change` uevent on `axp22x-ac`. **Before writing any code**, the
   > implementation plan's FIRST step must run
   > `udevadm monitor --udev --subsystem-match=power_supply` and physically
   > toggle the cable to establish:
   >   1. Does any udev event fire on plug/unplug? If **no** → udev is not a
   >      viable trigger; fall back to a polling timer (see below).
   >   2. If yes, which device emits it — `axp22x-ac` (use the narrow rule) or
   >      only `axp20x-battery` (use the broad rule, accept the extra exec).
   >
   > **Polling fallback (only if udev proves silent):** a `.timer` firing
   > `cpu-freq.sh apply-power` every ~15 s. `apply-power` is already idempotent,
   > so no other change is needed. Measured idle `power_supply` chatter is 0
   > events/12 s, so a 15 s poll is negligible. This is a documented contingency,
   > **not** to be built unless step 1 forces it.

4. **TUI toggle in `lib/tui/cpu_freq.py`**

   One row — "Auto (AC/DC scaling)" — showing on/off, that shells out to
   `cpu-freq.sh auto toggle` and refreshes from `cpu-freq.sh auto status`.

### Data flow

```
AC plug/unplug ─┐
boot coldplug  ─┴─> udev (SUBSYSTEM==power_supply, add|change)
                      └─> cpu-freq.sh apply-power
                            ├─ marker absent ─> exit 0 (no-op)
                            └─ marker present ─> read axp22x-ac/online
                                                  ├─ 1 -> write 1500/2400
                                                  └─ 0 -> write 1500/1500

TUI row ─> cpu-freq.sh auto {toggle,status} ─> marker file + immediate apply
```

### State

| State | Location | Meaning |
|-------|----------|---------|
| Feature enabled | `/etc/uconsole/cpu-auto-enabled` (presence) | opt-in marker, absent by default |
| Power source | `/sys/class/power_supply/axp22x-ac/online` | `1`=AC, `0`=battery (read-only) |
| Current freq | `/sys/.../cpu0/cpufreq/scaling_{min,max}_freq` | applied result |

### Default behavior

Disabled. On a fresh install the marker file is absent, so `apply-power` is an
instant no-op and the manual `cpu-freq.sh preset` picker behaves exactly as
today. The feature only ever touches frequencies after the user enables it in
the TUI.

## Error handling

- **Marker absent** — `apply-power` exits 0 before reading anything. Cheapest
  possible no-op.
- **AC sysfs unreadable** — `cat ... 2>/dev/null` yields empty, which is not
  `1`, so we fall through to the safe battery state (1500/1500). Failing safe
  toward the brownout-protective state is correct.
- **Disable while on battery** — `auto off` releases the cap to the stock range
  (1500/2400). Disabling the *capping* feature should not leave the CPU capped;
  releasing to the hardware range is the natural "off," and is not guessing a
  prior state (it's `cpuinfo_min`/`cpuinfo_max`). Note this permits turbo on
  battery again — that is the user's explicit choice to turn off brownout
  protection.
- **Concurrent events** — idempotent writes; no locking needed. Two back-to-back
  events just write the same values twice.

## Cleanup (separate task — NOT this branch)

- The dead `cpu-freq-cap.sh` (caps to 1.2 GHz, *below* the CM5's 1.5 GHz floor,
  so the write can never succeed — CM4-era cruft) was **verified absent from the
  canonical `device/` tree**. It exists only in `~/scripts/power/` and the
  `~/pkg/` backup repo, and was never packaged (the postinst already retires the
  related service). Deleting it is therefore a **separate `~/pkg` backup-repo
  commit**, out of scope for `feat/cpu-freq-scaling`. Listed here so it isn't
  lost, not as a step in this plan.

## Testing

- **GATE 0 — event source** (must pass before coding, per review #3):
  `udevadm monitor --udev --subsystem-match=power_supply` + physical cable
  toggle. Confirm an event fires and record which device emits it. Picks the
  narrow vs broad rule, or triggers the polling fallback.
- **Flag ON, unplug** → `scaling_max_freq` becomes 1500000.
- **Flag ON, plug in** → `scaling_max_freq` becomes 2400000 (governor stays the
  default `ondemand`, so it bursts under load).
- **All cores capped, not just cpu0** → read
  `cpu{1,2,3}/cpufreq/scaling_max_freq`; all should match cpu0 (policy0 spans
  cpu0–3, confirmed on-device).
- **Flag OFF** → cap released to 1500/2400 (stock range), and plug/unplug then
  changes nothing.
- **Boot on battery, flag ON** → comes up at 1500/1500 (verifies `add` match).
- **Boot on AC, flag ON** → comes up at 1500/2400.
- **`cpu-freq.sh auto status`** → reports correct enabled state and source.
- **TUI toggle does not prompt for a password** (sudo-tee/`rm` covered by the
  existing NOPASSWD policy).
- **Manual preset is transient when auto is ON** → after enabling auto, a manual
  `cpu-freq.sh preset` is overridden by the next power event. Document this; it
  is expected, not a bug.
- **Syntax gates** — `bash -n scripts/power/cpu-freq.sh`,
  `python3 -m py_compile lib/tui/cpu_freq.py`.
- **Manual udev re-trigger for testing** —
  `udevadm trigger --subsystem-match=power_supply`.

## Deployment

Canonical source is `~/uconsole-cloud/device/`. Build on `feat/cpu-freq-scaling`,
merge to `dev`, then `/publish` (dev→main, version bump, `.deb`, APT sign, push)
ships it to all users. Installed state is captured into the `~/pkg/` backup repo
separately. Feature is off by default, so shipping it changes no existing
device's behavior until explicitly enabled.
