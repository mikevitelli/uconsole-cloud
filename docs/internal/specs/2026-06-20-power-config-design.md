# uConsole Power / Battery Config — v2 Design

**Status:** Architecture draft, awaiting on-device verification before implementation
**Branch:** `feat/power-config` (off `dev`)
**Target:** webdash/TUI `v0.4`
**Date:** 2026-06-20

**Device:** ClockworkPi uConsole, CM5, X-Powers **AXP228** PMU (binds via the `axp22x`/AXP223 path in mainline `axp20x_battery.c`), addr **0x34**, **1S LiPo** on HackerGadgets battery board (high-discharge, high-capacity). Previous pack: 2× Nitecore NL1834 18650 — all 18650-specific tuning is retired.

> This doc was reviewed by three independent senior-engineer passes (PMIC/register, battery chemistry, power-delivery/root-cause). Their corrections are folded in. **Two claims could not be settled off-device and are gated in §2. Do not implement past the gate until they're resolved on hardware.**

---

## 0. Repo topology (read first)

Power code is split across two repos that are **not** in sync:

| Repo / branch | Role | Power code |
|---|---|---|
| **`uconsole-cloud` @ `dev`** (canonical) | live device code | `device/scripts/power/*` (`cpu-freq.sh`, `power.sh`, `battery.sh`, `charge.sh`, `cellhealth.sh`, `low-battery-shutdown.sh`, `lib.sh`), `device/lib/tui/*` (`cpu_freq.py`, `config_ui.py`, `framework.py`), `device/scripts/system/udev/*.rules` |
| **`mikevitelli/uconsole`** | `.deb` packaging | `pkg/**` + the `battery_lib.py` / `battery-config-design.html` prototype (exists ONLY here) |

**This work lands in `uconsole-cloud@dev`.** The `battery_lib.py` prototype must be ported into `device/lib/tui/` and wired into the existing `config_ui`/framework; the packaging repo consumes it as a build artifact, not a divergent copy.

---

## 1. The problem, stated honestly

Random under-load power-offs on CM5. The user has a healthy high-C 1S LiPo, so weak-battery is ruled out. The root cause is **power-delivery marginality**: CM5 peaks near ~5A on the 5V rail (≈2× CM4) on a CM4-era mainboard with a marginal TPS61178 boost stage and undersized bulk capacitance.

**What software can and cannot do (this framing supersedes the earlier draft):**

- **The brownout is most likely a 5V-rail collapse downstream of the TPS61178, NOT a battery-side undervoltage.** A healthy LiPo barely leaves 3.7–3.9V under a 5A transient; the SoC's 5V/3.3V input sags and the CM5 resets while the *cell* is nowhere near any cutoff. **This must be measured before any V_OFF change is sold as a brownout fix (§2, §8).**
- Software **cannot** fix a sagging 5V rail. It can only (a) protect the cells with a graceful shutdown, and (b) shrink the current spikes that cause the sag.
- The durable fix is **hardware**: bulk capacitance on the **5V / CM5-input rail** (out of scope here; §7). Note the much-cited **C513 220µF mod is a *different* cap** — it's on the USB-A switch output and fixes USB-insertion dropouts, not random non-USB power-offs.

### 1.1 Confirmed defects in the current code (cleanup, valid regardless of the gates)

| # | Defect | Effect |
|---|--------|--------|
| D1 | The V_OFF cutoff sysfs node is **disputed** (`voltage_min` vs `voltage_min_design`) — the two source reviews disagree. | We do not actually know if the shipped cutoff write works. **Gate G1.** |
| D2 | `fix-voltage-cutoff.sh` writes its live `echo` to one node and its udev rule to the *other* — internally inconsistent whichever node is right. | Cutoff (if it works at all) doesn't persist across reboot. |
| D3 | Raw `i2cset -y 0 0x34 0x31` uses **bus 0**; AXP228 bus is **unverified** (likely 3). | Raw layers are likely no-ops. **Gate G2.** Resolved by going sysfs-only (§4) — kills the bus dependency. |
| D4 | `charge.sh` caps charge at 900mA; schema clamps 2000mA; comments claim "HW caps at 900". The "900mA HW cap" is **fiction** — PMU register max is **2.55A** and the kernel applies **no battery-safety clamp**. | Inconsistent, and the schema invites an unsafe value (§5.2, §3 safety). |
| D5 | 18650/Nitecore constants hardcoded in `low-battery-shutdown.sh` (3.05/2.95V), `cellhealth.sh` (NL1834 model, curve, 2-cell math), docs. | **LiPo-unsafe thresholds running now (§3 #1).** |
| D6 | Two contradictory philosophies in-tree (sysfs-only vs raw i2cset; `voltage_min` as "gauge ref" vs as the cutoff). | No coherent cutoff path. Resolve after G1. |
| D7 | udev rule duplicated 5× in packaging repo + **2×** in cloud `dev` (`99-uconsole-battery.rules` + duplicate `99-uconsole-charging.rules`), all writing the same (possibly wrong) node. | Drift across two repos. |

---

## 2. Pre-flight verification gates (BLOCKING — resolve on-device before implementing §4/§6 cutoff work)

These cost nothing and decide which of the design's claims are real. Run with the device on.

**G1 — which sysfs node actually programs V_OFF (reg 0x31)?**
```
ls /sys/class/power_supply/axp20x-battery/ | grep voltage_min
for n in voltage_min voltage_min_design; do printf "%s = " "$n"; cat /sys/class/power_supply/axp20x-battery/$n 2>&1; done
# write 2.9V to whichever exists, then read the register back:
echo 2900000 | sudo tee /sys/class/power_supply/axp20x-battery/<node>
sudo i2cget -y <bus> 0x34 0x31      # expect bits[2:0] = 0b011 if it took
```
The node whose write flips reg 0x31 bits[2:0] is the real cutoff node. Use it everywhere; delete writes to the other. (Source reviews split: one read the driver as exposing `voltage_min`, the other as `voltage_min_design`. The device is authoritative.)

**G2 — which i2c bus is the AXP228 on?**
```
i2cdetect -l ; for b in 0 1 3; do echo "bus $b:"; sudo i2cdetect -y $b 2>/dev/null | grep -n 34; done
ls -l /sys/class/power_supply/axp20x-battery/device   # authoritative: which adapter the driver bound to
```
(Going sysfs-only per §4 makes the bus irrelevant for the cutoff; G2 only matters if a raw-i2c escalation is ever added.)

**G3 — is the brownout on the cell or the 5V rail?** (decides whether V_OFF is even relevant)
```
vcgencmd get_throttled        # bit 0x1 = undervolt now, 0x10000 = undervolt occurred
# log cell voltage at 10 Hz during a stress run, then inspect after the next drop:
for i in $(seq 1 600); do printf "%s %s\n" "$(cat /sys/class/power_supply/axp20x-battery/voltage_now)" "$(vcgencmd measure_clock arm)"; sleep 0.1; done | tee ~/brownout-trace.log
# hammer: stress -c4 + brightness max + radio burst
```
If the cell never approaches 3.0–3.3V while a power-off / `0x10000` occurs, **V_OFF is exonerated** and L1 is not your brownout fix (it's only a cell backstop). Proper version: DC scope on cell / TPS61178 5V-out / CM5 5V-in simultaneously, trigger on falling edge.

**G4 — is there a real NTC/thermistor?** (blocks any charge-current increase)
```
cat /sys/class/power_supply/axp20x-battery/temp   # plausible, varying value = real NTC
```
No NTC ⇒ no over-temp protection ⇒ charge current stays conservative regardless of UI.

---

## 3. Protection model — three layers (L2 is primary; L1 demoted)

| Layer | Mechanism | Role | 1S LiPo value | Notes |
|-------|-----------|------|---------------|-------|
| **L1 — HW cutoff (V_OFF)** | AXP228 reg 0x31 via the **verified** sysfs node (G1), persisted by one udev rule | **Cell backstop only**, NOT the brownout fix. Hard PMU kill with no clean-shutdown window. | **3.0V** (`0b100`) | Raised from the earlier 2.9V: 2.9V *resting* is in the LiPo damage region (vendor floor 3.0V). 3.0V still rides sub-second transient sags (daemon polls every 30s, needs 3 confirmations). |
| **L2 — Software graceful shutdown** | `low-battery-shutdown.sh`, thresholds from `console.json battery.*` | **PRIMARY protection.** Clean `sync` + `poweroff` before the cell is stressed. | **3.40V** graceful / **3.30V** immediate | Live daemon still ships 3.05/2.95V (18650) — **must change in the same commit that adopts the LiPo (§3 #1, blocker).** |
| **L3 — Warn** | UI/notify only | heads-up | **3.55V** | — |

**Encoding (confirmed, AXP228 datasheet REG31H):** V_OFF = 2.6V + bits[2:0]×0.1V. 3.0V = `0b100`, 2.9V = `0b011`. Bits[7:3] are wakeup/restart control (bit6 = soft-restart, self-clearing) — if any raw-i2c path is ever used it **must** be read-modify-write on `GENMASK(2,0)`, never a blind byte write. The kernel `regmap_update_bits` path is already safe; prefer it.

### Safety blockers (act regardless of the gates)
1. **`low-battery-shutdown.sh` runs 18650 thresholds on the LiPo today.** 3.05V graceful is a *loaded* reading; under a 5A transient a LiPo can sag 200–350mV, so the cell can sit below its 3.0V structural floor before anything stops it. Set 3.40/3.30V, read from config. **Highest priority.**
2. **L1 at 3.0V, not 2.9V** (above).
3. **Charge current stays 900mA default; do NOT raise the clamp to 2000mA** until the pack's rated max charge C-rate is known AND G4 confirms an NTC. PMU max is 2.55A with no kernel safety clamp; no temp sensing = no over-temp protection.

---

## 4. Cutoff mechanism — decision

**Single path: write the *verified* V_OFF node (G1) via one generated udev rule. Drop every raw-`i2cset` / initramfs / shutdown-service layer.**

- Removes the bus-number landmine (D3/G2) entirely.
- The raw layers today are no-ops (bus 0), so deleting them loses nothing currently working.
- The AXP228 register holds its value until a true power-cycle; udev re-applies on device-add each boot.

**Escalation (documented, not built):** the only case udev can't cover is a cold-boot inrush sag before udev runs (register resets to default on full power-off). Unlikely on a fresh 1S LiPo (boot-inrush sag was an aging-18650 symptom). If observed, add **one** initramfs premount layer using read-modify-write on the **G2-verified** bus. Not before.

---

## 5. Profile model (1S LiPo primary)

All thresholds derive from the active profile; no cell-model constants in code. 1S = PMU senses per-cell.

### 5.1 Profiles
| key | label | chem | cells | charge_limit_mv | charge_current_ma | warn_mv | shutdown_mv | voff_mv (L1) |
|-----|-------|------|-------|-----------------|-------------------|---------|-------------|--------------|
| `lipo_1s` ⭐ | 1S LiPo | lipo | 1 | 4200 (expose 4100 "longevity") | **900** (until §5.3) | 3550 | 3400 | **3000** |
| `18650` | 2× 18650 | liion | 1* | 4200 | 900 | 3600 | 3450 | 3000 |
| `li_2s` | 2S | liion | 2 | 4200 | 900 | 3550 | 3400 | 3000 |
| `custom` | Custom | — | — | unchanged | unchanged | unchanged | unchanged | unchanged |

⭐ default. `*` 18650 pack is 2 physical cells, PMU-sensed as 1S.

### 5.2 Hard clamps (schema-enforced)
- `charge_current_ma`: **300–900** for now. Do **not** widen to 2000 until §5.3 + G4. (Register min is 300mA; <300 silently rounds up.)
- `charge_limit_mv` (`voltage_max`): **{4100, 4200} only** — kernel/driver policy for axp22x rejects others with `-EINVAL`. (HW reg supports more; the driver doesn't expose them.)
- `shutdown_mv` (L2): **3300–3700**, never below 3.3V for LiPo.
- `warn_mv` (L3): **3300–3900**.
- `voff_mv` (L1): **3000–3300**. Floor raised to 3000 (was 3000 in `battery_lib`, but spec text said 2900 — reconciled to **3000**, the LiPo vendor floor). The `battery_lib` prototype's existing 3000 floor is now correct; fix the spec/HTML text that said 2900.

### 5.3 Charge current — OPEN, blocks any clamp increase
Set `lipo_1s.charge_current_ma` to the pack's manufacturer max charge rate (typically 0.5C). Needs the HackerGadgets pack's rated capacity + max charge C-rate. Until then: 900mA default, clamp ceiling 900, UI note "verify against your pack." Raising charge current also requires G4 (NTC present) and, ideally, temp-derating.

---

## 6. Component changes (after gates pass)

### 6.1 Single source of truth (cross-repo)
- Canonical = `uconsole-cloud@dev device/`. Land logic/scripts here; packaging repo consumes as a build artifact. Document the one-way sync direction. **D7.**
- **One** udev rule generated by `battery_lib.gen_udev_rule()`. Delete all hand-maintained copies: packaging repo's 5 and cloud `dev`'s 2 (incl. the duplicate `99-uconsole-charging.rules`).

### 6.2 `battery_lib.py` (port into `device/lib/tui/`)
- `gen_udev_rule()`: write the **G1-verified** V_OFF node (don't hardcode `voltage_min_design` — that's the disputed claim).
- Default profile `lipo_1s`; `voff_mv` default 3000 for non-custom profiles. (Note: `DEFAULTS.voff_mv=None` ⇒ udev omits the V_OFF line out-of-box ⇒ L1 off until opt-in. Acceptable since L1 is only a backstop, but make it explicit in the UI.)
- Drop the "voltage_min is a gauge ref, never raw i2cset" docstring claims pending G1/D6 resolution; state the chosen model.

### 6.3 Scripts
- `low-battery-shutdown.sh`: read thresholds from config; default 3.40/3.30V. **Ship in the LiPo-adoption commit (blocker).**
- `fix-voltage-cutoff.sh`: live `echo` and udev rule both target the **same G1-verified** node; tighten read-back to `-eq` (step is 0.1V, the 2900000–2910000 window comment is wrong); update 18650 comments.
- `charge.sh`: floor 300mA (match register), ceiling stays 900 until §5.3; delete the false "HW caps at 900" comment.
- `cellhealth.sh`: parameterize cell model/capacity/curve from config; fix `CELL_COUNT=1` (IR + per-pack math currently assume 2 cells → ~2× wrong on 1S); fall back to kernel gauge `capacity` until a LiPo curve is characterized; rewrite the "replace both 18650s" advice. Verify the `calibrate` sysfs attr exists before advising it (likely ENOENT on mainline).
- Delete `axp-voff-hook` / `axp-voff-premount` / `axp-voff-shutdown.service` (§4) unless the cold-boot escalation is justified — and rebuild on the G2-verified bus if so.

### 6.4 Spike mitigation — reuse existing `cpu-freq.sh`, don't reinvent
`cpu-freq.sh` (presets `battery` 1500/1500, `balanced` 1500/2000, `performance` 1800/2400, `max` 2400/2400) + `cpu_freq.py` already exist.
- `battery.power_profile` maps to a `cpu-freq.sh preset`. **Capping the *ceiling* (max) is what reduces brownouts** (smaller current step the boost must service); pinning the floor high just wastes power/heat. So the useful lever is a lowered max, not the 1500/1500 lock per se. `balanced` default.
- The TUI calls/displays `cpu-freq.sh` state; no duplicate frequency logic.
- **Never** ship overclock / `over_voltage` / `force_turbo` / `usb_max_current_enable` on battery — they raise draw and worsen brownouts.
- If sub-1500MHz spike reduction is wanted, first verify the CM5 kernel exposes lower OPPs (`scaling_available_frequencies`).

---

## 7. Out of scope (hardware — documented, not implemented)
- **The real brownout fix:** bulk capacitance on the **5V / CM5-input rail**, sized from the G3/scope sag measurement. Reference designator not yet published by the community.
- **C513 100µF → 220µF tantalum (10V, 3528):** fixes **USB-insertion** dropouts specifically — a *different* failure from random non-USB power-offs. Cheap, proven, worth doing, but don't expect it to fix the random case.
- **Thermal mod** (rear M.2 heatsink or riser + thin pad): rule out heat-masquerading-as-brownout *before* crediting any electrical fix.
- **EEPROM:** confirm `POWER_OFF_ON_HALT=1` (fixes the won't-power-off latch; not a brownout cure). Leave `PSU_MAX_CURRENT` unset on battery.

## 8. Verification & rollout
1. **Gates G1–G4 (§2)** — blocking. Resolve on-device first.
2. Land the **safety fixes** (L2 3.40/3.30, L1 3.0V, charge stays 900) — correct regardless of gate outcomes; these can ship first.
3. After G1: collapse the cutoff path to the verified node + one udev rule; delete raw/duplicate layers.
4. After G3: decide whether L1/V_OFF stays framed as a backstop (likely) or whether effort moves to the 5V-rail cap + cpu-freq ceiling.
5. Reboot-persistence check: the verified node reads the set value and reg 0x31 bits[2:0] match after a cold boot.
6. Catch any brownout with `brownout-recover.sh` to classify threshold-trip vs wedged-bus.

## 9. Open questions
- **G1:** which sysfs node programs V_OFF? (blocks cutoff code)
- **G3:** cell or 5V rail? (decides whether V_OFF is relevant at all)
- **G4:** real NTC present? (blocks charge-current increase)
- 1S LiPo rated capacity + max charge C-rate (§5.3).
- Characterize a 1S LiPo discharge curve for `cellhealth.sh`, or rely on the kernel gauge `capacity`?

---

### Confidence
- **Confirmed (primary source):** REG31H V_OFF encoding; bits[7:3] are control/RMW-sensitive; axp22x driver limits `voltage_max` to {4.1, 4.2}V; PMU charge-current register max 2.55A with no kernel safety clamp.
- **Disputed / device-gated:** which sysfs node writes V_OFF (G1); i2c bus number (G2); whether the brownout is cell- or 5V-rail-side (G3).
- **Engineering inference (not a published scope trace):** the brownout is a 5V-rail transient collapse — strongly argued from boost topology + CM5 draw, to be confirmed by G3.
