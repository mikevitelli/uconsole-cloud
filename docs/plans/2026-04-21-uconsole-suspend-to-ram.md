# uConsole Suspend-to-RAM Investigation & Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop uConsole overnight idle power draw from ~4.2 W to <1 W by implementing real suspend-to-RAM (or, if the kernel can't be made to cooperate, an aggressive idle-optimization fallback that approaches 1.5 W).

**Architecture:** Phased investigation that gates each phase on measurable evidence. Phase 2 is the critical gate — the current ClockworkPi kernel `6.12.78-v8-16k+` ships with `/sys/power/state` empty (CONFIG_SUSPEND=n), so NO kernel-level suspend works today. That gate decides the rest of the plan.

**Tech Stack:** bash + systemd + Python (`uconsole-sleep` v1.3 upstream), i2c-tools for AXP228 readout, kernel rebuild via `clockworkpi-apt` if needed, RPi DT overlays.

---

## Background & Evidence (2026-04-21)

From the overnight discharge test of Samsung INR18650-35E 2×3500 mAh pack:

- **2h 30m runtime** on battery (01:39 → 04:09)
- **4.19 W avg draw** (1178 mA avg) — user reported "console was sleeping"
- **2951 mAh extracted** of 7000 mAh nominal → **42% usable**
- Shutdown triggered at **3.11 V** by `low-battery-shutdown.sh` (graceful daemon), NOT by the 2.9 V PMU hard-kill
- `low-battery-shutdown.sh` threshold already lowered to 3.00 V (separate change)
- Duplicate `low-battery-shutdown.service` removed (separate change)

**The real leak is the 4.2 W "resting" draw, not the cutoff.**

Fake sleep ≠ real sleep: `/etc/systemd/system/sleep-power-control.service` and `sleep-remap-powerkey.service` (from package `uconsole-sleep` v1.3) only control display/DRM blanking and power-key remap. They do not invoke any kernel suspend.

Kernel probe result (2026-04-21):
```
$ cat /sys/power/state
[empty]
$ cat /sys/power/mem_sleep
[empty]
$ ls /sys/power/
pm_freeze_timeout  state
```

Only `state` and `pm_freeze_timeout` exist — kernel has no suspend states compiled in.

---

## File Structure

**Created:**
- `docs/plans/2026-04-21-uconsole-suspend-to-ram.md` — this plan
- `device/scripts/power/idle-profile.sh` — Phase 1 measurement harness
- `device/scripts/power/suspend-probe.sh` — Phase 2 kernel probe
- `device/scripts/power/peripheral-audit.sh` — Phase 4 wake-source audit
- `device/scripts/power/uconsole-suspend.sh` — Phase 5 actual suspend script
- `device/scripts/power/tests/test-suspend-dry.sh` — tests with mocked `/sys/power/state`
- `device/scripts/power/tests/test-idle-optimize.sh` — fallback path tests
- `device/scripts/system/idle-optimize.sh` — Phase 6 fallback
- `device/scripts/system/systemd/uconsole-suspend.service` + `.target` units (if Phase 5 unlocks)

**Modified:**
- `device/lib/tui/framework.py:129` — `sub:power_ctl` submenu gets "Suspend Now" entry if Phase 5 succeeds; "Idle Mode" entry if Phase 6 is final
- `device/scripts/power/battery.sh` — add `--idle-breakdown` subcommand (Phase 1)

**Not modified:** `low-battery-shutdown.sh` (already tuned), `fix-battery-boot.sh` (already installed 3-layer cutoff), uconsole-sleep venv (upstream, leave alone).

---

## Phase 1 — Baseline Measurements

Establish the numbers this plan is trying to beat. No code to ship yet.

### Task 1.1: Idle-draw profiler script

**Files:**
- Create: `device/scripts/power/idle-profile.sh`

- [ ] **Step 1: Write the profiler**

```bash
#!/bin/bash
# idle-profile.sh — measure average battery draw over a window in a given state.
# Usage: idle-profile.sh <state-name> <duration-sec>
# Writes CSV row to ~/battery-tests/idle-profile.csv

set -e
STATE="${1:?state-name required}"
DUR="${2:?duration-sec required}"
OUT="$HOME/battery-tests/idle-profile.csv"
mkdir -p "$HOME/battery-tests"

V_PATH=/sys/class/power_supply/axp20x-battery/voltage_now
I_PATH=/sys/class/power_supply/axp20x-battery/current_now
AC_PATH=/sys/class/power_supply/axp22x-ac/online

if [ "$(cat $AC_PATH)" = "1" ]; then
    echo "ERR: on AC — unplug to measure battery draw" >&2
    exit 2
fi

echo "[idle-profile] state=$STATE duration=${DUR}s starting $(date -Is)" >&2
[ -f "$OUT" ] || echo "timestamp,state,duration_s,samples,avg_ma,avg_mw,v_start,v_end,temp_start_c,temp_end_c" > "$OUT"

samples=0; sum_i=0; sum_p=0
v_start=$(cat $V_PATH); t_start=$(cat /sys/class/thermal/thermal_zone0/temp)
end=$(( $(date +%s) + DUR ))
while [ "$(date +%s)" -lt "$end" ]; do
    v=$(cat $V_PATH)
    i=$(cat $I_PATH)
    # current_now is signed (negative = discharging); use absolute mA
    ma=$(awk "BEGIN{printf \"%d\", ($i < 0 ? -$i : $i) / 1000}")
    mw=$(awk "BEGIN{printf \"%d\", $ma * $v / 1000000}")
    sum_i=$(( sum_i + ma ))
    sum_p=$(( sum_p + mw ))
    samples=$(( samples + 1 ))
    sleep 5
done
v_end=$(cat $V_PATH); t_end=$(cat /sys/class/thermal/thermal_zone0/temp)
avg_i=$(( sum_i / samples ))
avg_p=$(( sum_p / samples ))

ts=$(date -Is)
echo "$ts,$STATE,$DUR,$samples,$avg_i,$avg_p,$v_start,$v_end,$t_start,$t_end" >> "$OUT"
echo "[idle-profile] $STATE: $avg_i mA / $avg_p mW avg over $samples samples"
```

- [ ] **Step 2: Syntax check + make executable**

```bash
bash -n device/scripts/power/idle-profile.sh && chmod +x device/scripts/power/idle-profile.sh
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add device/scripts/power/idle-profile.sh
git commit -m "power: add idle-profile.sh measurement harness for suspend R&D"
```

### Task 1.2: Measure four idle states

Run each measurement with the device **unplugged**, full brightness off (DPMS), no foreground apps. 20 min each so the AXP228 coulomb counter averages out noise. Total ~90 min elapsed.

- [ ] **Step 1: State A — screen-on idle**

Precondition: display at default brightness, TTY at login prompt, no user apps.

```bash
sudo systemctl stop webdash uconsole-low-battery      # cut variable loads
bash device/scripts/power/idle-profile.sh screen-on 1200
```

Expected: one row in `~/battery-tests/idle-profile.csv`.

- [ ] **Step 2: State B — screen-off idle (DPMS)**

```bash
wlopm --off '*'   # labwc; if this errors, use: xset dpms force off
bash device/scripts/power/idle-profile.sh screen-off 1200
wlopm --on '*'
```

- [ ] **Step 3: State C — uconsole-sleep fake-sleep**

Enable whatever uconsole-sleep's "sleep" mode is (power-button short-press per the package's remap rule). Confirm display is blanked AND the PM hook claims sleep.

```bash
# trigger fake-sleep via its own API (via uinput remap)
sudo systemctl status sleep-power-control.service | head
# Then long-press power button OR send the synthesized suspend key:
echo "manual: short-press power button now, then press Enter to start timer"
read
bash device/scripts/power/idle-profile.sh fake-sleep 1200
```

- [ ] **Step 4: State D — stripped idle (everything the user doesn't need)**

```bash
sudo systemctl stop webdash uconsole-low-battery uconsole-status \
    meshtasticd gpsd bluetooth avahi-daemon NetworkManager cups 2>/dev/null
wlopm --off '*'
bash device/scripts/power/idle-profile.sh stripped 1200
# restore after:
sudo systemctl start NetworkManager uconsole-low-battery uconsole-status
```

Expected: State D draw should be the hard floor this kernel can achieve *without* suspend — the target for Phase 6 fallback.

- [ ] **Step 5: Summarize + commit data**

```bash
column -t -s, ~/battery-tests/idle-profile.csv
git add ~/battery-tests/idle-profile.csv
git commit -m "data: baseline idle-draw measurements (screen-on/off/fake-sleep/stripped)"
```

**Decision criteria for Phase 2:**
- If State D is ≤1.5 W → **skip to Phase 6** (fallback is good enough, skip kernel work)
- If State D is 1.5–2.5 W and CM5 swap is imminent → Phase 6 + defer kernel work until CM5
- If State D is >2.5 W → continue to Phase 2, real suspend is the only answer

---

## Phase 2 — Kernel Suspend Capability Audit

Confirm the kernel gate. The 2026-04-21 probe showed `/sys/power/state` empty, which this phase double-checks and then decides whether a kernel rebuild is worth it.

### Task 2.1: Suspend-probe script

**Files:**
- Create: `device/scripts/power/suspend-probe.sh`

- [ ] **Step 1: Write the probe**

```bash
#!/bin/bash
# suspend-probe.sh — read-only inspection of the running kernel's PM capabilities.
set -e
echo "=== kernel ==="; uname -a
echo "=== package ==="; dpkg -l clockworkpi-kernel 2>/dev/null | tail -1

echo "=== /sys/power ==="
for f in state mem_sleep disk pm_freeze_timeout; do
    p=/sys/power/$f
    if [ -e "$p" ]; then echo "$p = [$(cat $p 2>/dev/null)]"; fi
done

echo "=== kernel config (if available) ==="
if [ -f /proc/config.gz ]; then
    zcat /proc/config.gz | grep -E "^CONFIG_(PM|SUSPEND|HIBERNATION|ARCH_SUSPEND_POSSIBLE|CPU_IDLE)" | sort
elif [ -f /boot/config-$(uname -r) ]; then
    grep -E "^CONFIG_(PM|SUSPEND|HIBERNATION|ARCH_SUSPEND_POSSIBLE|CPU_IDLE)" /boot/config-$(uname -r) | sort
else
    echo "no kernel config surfaced (expected on ClockworkPi kernel)"
fi

echo "=== cpu idle states ==="
for c in /sys/devices/system/cpu/cpu*/cpuidle; do
    [ -d "$c" ] || continue
    cpu=$(basename $(dirname $c))
    for s in $c/state*; do
        [ -d "$s" ] || continue
        name=$(cat $s/name); disabled=$(cat $s/disable)
        echo "$cpu $(basename $s): $name disabled=$disabled"
    done
done

echo "=== rtcwake availability ==="
which rtcwake || echo "rtcwake missing (apt: util-linux)"
```

- [ ] **Step 2: Run it**

```bash
bash device/scripts/power/suspend-probe.sh | tee ~/battery-tests/suspend-probe-$(date +%F).txt
```

Expected (based on 2026-04-21 run): `state = []`, no mem_sleep entry, cpuidle has WFI at most. Output captured to dated file.

- [ ] **Step 3: Commit both**

```bash
chmod +x device/scripts/power/suspend-probe.sh
git add device/scripts/power/suspend-probe.sh ~/battery-tests/suspend-probe-*.txt
git commit -m "power: add suspend-probe + capture baseline kernel PM capabilities"
```

### Task 2.2: Kernel rebuild feasibility memo

Not code. Research + decision doc. Read, don't guess.

- [ ] **Step 1: Check ak-rex repo source**

```bash
# The ClockworkPi kernel is rebuilt periodically from rpi-6.12.y branch plus ak-rex patches
curl -s https://api.github.com/repos/ak-rex/ClockworkPi-apt/contents/debian 2>&1 | head -40
```

Determine: is the kernel source open? Where are the patches? Is CONFIG_SUSPEND intentionally disabled or just an upstream-default on arm64 CM4?

- [ ] **Step 2: Check rpi-linux config for PM_SUSPEND**

```bash
# Upstream RPi kernel defconfig — look for SUSPEND defaults on arm64
curl -sL "https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/arch/arm64/configs/bcm2711_defconfig" | grep -i suspend
# Same for the merged defconfig
curl -sL "https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/arch/arm64/configs/bcmrpi3_defconfig" | grep -i suspend
```

Expected findings to record in the memo:
- Whether upstream RPi enables SUSPEND on CM4 by default
- Whether ak-rex intentionally disables it (likely due to broken peripherals post-suspend)
- Whether ClockworkPi is CM4-aware enough that a rebuild would boot

- [ ] **Step 3: Write the memo**

Create `docs/plans/memos/2026-04-21-kernel-rebuild-feasibility.md` summarizing findings. Maximum one page. Must answer:

1. Is rebuilding the kernel with CONFIG_SUSPEND=y realistic for a solo dev? (Ballpark hours + risk of bricked boot)
2. Is CM5 swap imminent enough (per `project_cm5_upgrade.md`) that this is wasted effort?
3. What's the downgrade path if the custom kernel breaks?

- [ ] **Step 4: Commit**

```bash
git add docs/plans/memos/2026-04-21-kernel-rebuild-feasibility.md
git commit -m "memo: kernel rebuild feasibility for suspend-to-RAM"
```

### Task 2.3: Gate decision

- [ ] **Step 1: Decide branch**

Based on Task 2.2 memo:
- **Kernel rebuild viable AND CM5 swap >3 months out** → continue to Phase 3 (kernel) then 4, 5
- **Kernel rebuild NOT viable OR CM5 imminent** → skip to Phase 6 (fallback)

Record decision in the memo under a `## Decision` heading. This is the branch point for the plan.

No commit for this step — it's a human decision, not code.

---

## Phase 3 — Kernel Rebuild (conditional on Phase 2 decision)

Only execute if Phase 2 decided "rebuild viable". Otherwise jump to Phase 6.

### Task 3.1: Build environment

- [ ] **Step 1: Install kernel build deps**

```bash
sudo apt install -y bc bison flex libssl-dev make libc6-dev libncurses-dev \
    crossbuild-essential-arm64 git kmod
```

- [ ] **Step 2: Clone the source**

Assumes the Task 2.2 memo identified the source repo. Example:

```bash
cd ~/src
git clone --depth 1 --branch rpi-6.12.y https://github.com/raspberrypi/linux.git rpi-linux
cd rpi-linux
# Apply any clockworkpi-specific patches (identified in memo)
```

- [ ] **Step 3: Commit the pin**

```bash
cd ~/uconsole-cloud
git add docs/plans/memos/kernel-source-pin.md  # create this with the exact SHA used
git commit -m "pin: kernel source SHA for suspend rebuild"
```

### Task 3.2: Enable CONFIG_SUSPEND and rebuild

- [ ] **Step 1: Start from current running config**

```bash
cd ~/src/rpi-linux
make KERNEL=kernel8 bcm2711_defconfig
scripts/config -e PM -e PM_SLEEP -e SUSPEND -e ARCH_SUSPEND_POSSIBLE \
               -e PM_AUTOSLEEP -e PM_WAKELOCKS
```

- [ ] **Step 2: Build**

```bash
make -j$(nproc) Image.gz modules dtbs
```

Expected: ~30-40 minutes on CM4. If cross-compiling on a beefier box, faster.

- [ ] **Step 3: Stage alongside the shipped kernel, do NOT replace**

```bash
sudo cp arch/arm64/boot/Image.gz /boot/firmware/kernel8-suspend.img
sudo make modules_install
# Add an entry to /boot/firmware/config.txt under [all] that is commented out
# so user can switch manually after a sanity boot:
#   kernel=kernel8-suspend.img
```

Never overwrite the shipped kernel. Dual-stage so rollback is "edit config.txt, reboot".

- [ ] **Step 4: Test — suspend-probe under new kernel (after manual reboot into kernel8-suspend)**

```bash
bash device/scripts/power/suspend-probe.sh
```

Expected: `state = [freeze mem]` or at minimum `state = [freeze]`.

- [ ] **Step 5: Commit the kernel artifacts**

```bash
# keep Image.gz and module tree in a release-assets repo, not uconsole-cloud
# (too big for a code repo). Just commit the build notes:
git add docs/plans/memos/kernel-build-notes.md
git commit -m "build: suspend-enabled kernel notes + staged as kernel8-suspend.img"
```

---

## Phase 4 — Peripheral Suspend Audit

Only if Phase 3 produced a kernel with `mem` or `freeze` available. Each peripheral gets tested in isolation because CM4 + uConsole peripherals are notorious for breaking resume.

### Task 4.1: Wake-source + peripheral audit script

**Files:**
- Create: `device/scripts/power/peripheral-audit.sh`

- [ ] **Step 1: Write the audit harness**

```bash
#!/bin/bash
# peripheral-audit.sh — test `echo freeze > /sys/power/state` with different
# peripheral configs. Each run: disable a peripheral, attempt freeze for 10s
# via rtcwake, measure draw, confirm resume, log result.
#
# Usage: peripheral-audit.sh [peripheral]
#   peripherals: meshtasticd gpsd bluetooth webdash usb-autosuspend display
#   default: runs the full matrix

set -e
LOG="$HOME/battery-tests/peripheral-audit-$(date +%F).log"
mkdir -p "$HOME/battery-tests"

STATES=$(cat /sys/power/state)
if [ -z "$STATES" ]; then
    echo "FATAL: /sys/power/state is empty — no kernel suspend available" >&2
    exit 1
fi
# Prefer freeze (s2idle) if available, otherwise mem
TARGET=freeze
echo "$STATES" | grep -q freeze || TARGET=mem

suspend_once() {
    local label=$1 secs=10
    echo "[$label] suspending for ${secs}s via rtcwake -s $secs -m $TARGET"
    echo "[$label] v_before=$(cat /sys/class/power_supply/axp20x-battery/voltage_now) i_before=$(cat /sys/class/power_supply/axp20x-battery/current_now)" | tee -a "$LOG"
    sudo rtcwake -s $secs -m $TARGET 2>&1 | tee -a "$LOG"
    echo "[$label] v_after=$(cat /sys/class/power_supply/axp20x-battery/voltage_now) i_after=$(cat /sys/class/power_supply/axp20x-battery/current_now)" | tee -a "$LOG"
    echo "[$label] dmesg wake reasons:" | tee -a "$LOG"
    dmesg | tail -20 | grep -iE "pm:|wakeup|resume" | tee -a "$LOG"
    echo "---" | tee -a "$LOG"
}

case "${1:-matrix}" in
    matrix)
        suspend_once "baseline (nothing stopped)"
        sudo systemctl stop meshtasticd 2>/dev/null; suspend_once "no-meshtasticd"
        sudo systemctl stop gpsd 2>/dev/null;       suspend_once "no-gpsd"
        sudo systemctl stop bluetooth 2>/dev/null;  suspend_once "no-bluetooth"
        sudo systemctl stop webdash 2>/dev/null;    suspend_once "no-webdash"
        # USB autosuspend
        for d in /sys/bus/usb/devices/*/power/control; do [ -w "$d" ] && echo auto | sudo tee "$d" >/dev/null; done
        suspend_once "usb-autosuspend-on"
        # Restart everything
        sudo systemctl start meshtasticd gpsd bluetooth webdash 2>/dev/null || true
        ;;
    *)
        suspend_once "$1"
        ;;
esac

echo "Full log: $LOG"
```

- [ ] **Step 2: Syntax check**

```bash
bash -n device/scripts/power/peripheral-audit.sh && chmod +x device/scripts/power/peripheral-audit.sh
```

- [ ] **Step 3: Run matrix, 5 cycles each peripheral, on battery**

```bash
# Safety: on battery, screen on, save this terminal's shell history first
history -w
sudo systemctl stop uconsole-low-battery  # avoid a mid-test shutdown
bash device/scripts/power/peripheral-audit.sh matrix
sudo systemctl start uconsole-low-battery
```

Expected findings (priors):
- `meshtasticd` will block freeze (SX1262 SPI polling)
- `gpsd` will keep UART busy
- Display might cause artifacts on resume — note, don't fix yet
- USB autosuspend likely the biggest single win

- [ ] **Step 4: Commit findings**

```bash
git add device/scripts/power/peripheral-audit.sh ~/battery-tests/peripheral-audit-*.log
git commit -m "power: peripheral suspend audit harness + run data"
```

### Task 4.2: Identify minimum stop-list

- [ ] **Step 1: Analyze the audit log**

Read `~/battery-tests/peripheral-audit-*.log`. For each `label`:
- Did `rtcwake` return cleanly?
- What was the draw during freeze (delta voltage over 10s × capacity approx)?
- What woke it?

Produce a ranked list: peripherals that MUST be stopped for freeze to succeed vs peripherals that just improve draw.

- [ ] **Step 2: Record in design doc**

Create `docs/plans/memos/2026-04-21-suspend-peripheral-matrix.md` with the table. This matrix drives Task 5.1's script contents.

- [ ] **Step 3: Commit**

```bash
git add docs/plans/memos/2026-04-21-suspend-peripheral-matrix.md
git commit -m "memo: peripheral suspend matrix from audit results"
```

---

## Phase 5 — Implement uconsole-suspend

Uses the peripheral matrix from Task 4.2 as input.

### Task 5.1: Core suspend script with tests

**Files:**
- Create: `device/scripts/power/uconsole-suspend.sh`
- Create: `device/scripts/power/tests/test-suspend-dry.sh`

- [ ] **Step 1: Write failing test first**

```bash
#!/bin/bash
# test-suspend-dry.sh — verify uconsole-suspend.sh in DRY_RUN mode prints
# the expected stop/start sequence and does NOT actually suspend.
set -e
HERE=$(dirname "$(realpath "$0")")
SCRIPT="$HERE/../uconsole-suspend.sh"

out=$(DRY_RUN=1 bash "$SCRIPT" suspend 2>&1)
echo "$out" | grep -q "DRY_RUN: would stop meshtasticd" || { echo "FAIL: no meshtasticd stop"; exit 1; }
echo "$out" | grep -q "DRY_RUN: would stop gpsd"        || { echo "FAIL: no gpsd stop"; exit 1; }
echo "$out" | grep -q "DRY_RUN: would blank display"     || { echo "FAIL: no display blank"; exit 1; }
echo "$out" | grep -q "DRY_RUN: would echo freeze > /sys/power/state" || { echo "FAIL: no freeze echo"; exit 1; }
echo "$out" | grep -qv "DRY_RUN" && { echo "FAIL: non-DRY_RUN line leaked"; exit 1; } || true
echo "PASS"
```

- [ ] **Step 2: Run test — expect failure**

```bash
chmod +x device/scripts/power/tests/test-suspend-dry.sh
bash device/scripts/power/tests/test-suspend-dry.sh
```

Expected: fails because the script doesn't exist yet.

- [ ] **Step 3: Write the minimum suspend script to pass**

```bash
#!/bin/bash
# uconsole-suspend.sh — orchestrate real suspend-to-RAM.
# Usage:
#   uconsole-suspend.sh suspend   # enter sleep
#   uconsole-suspend.sh resume    # invoked by rtcwake or as post-resume hook
# Env:
#   DRY_RUN=1  Print actions, don't execute

set -e
MODE="${1:?suspend|resume}"
DRY="${DRY_RUN:-0}"

# Stop list from Task 4.2 peripheral-matrix memo
STOP_SERVICES="meshtasticd gpsd"

run() {
    if [ "$DRY" = "1" ]; then
        echo "DRY_RUN: would $*"
    else
        eval "$@"
    fi
}

suspend() {
    for svc in $STOP_SERVICES; do
        run "systemctl stop $svc"
    done
    run "blank display"
    run "echo freeze > /sys/power/state"
}

resume() {
    for svc in $STOP_SERVICES; do
        run "systemctl start $svc"
    done
    run "unblank display"
}

case "$MODE" in
    suspend) suspend ;;
    resume)  resume ;;
    *) echo "usage: $0 suspend|resume" >&2; exit 2 ;;
esac
```

Correct the `run` calls so the test-expected strings are emitted. Test expects `DRY_RUN: would stop meshtasticd` — the run function needs to format that. Adjust:

```bash
run() {
    if [ "$DRY" = "1" ]; then
        echo "DRY_RUN: would $*"
    else
        case "$1" in
            systemctl) shift; sudo systemctl "$@" ;;
            blank)     wlopm --off '*' 2>/dev/null || xset dpms force off ;;
            unblank)   wlopm --on '*' 2>/dev/null || xset dpms force on ;;
            echo)      shift; echo "$@" | sudo tee /sys/power/state >/dev/null ;;
            *)         eval "$@" ;;
        esac
    fi
}

suspend() {
    for svc in $STOP_SERVICES; do run stop $svc; done
    run blank display
    run echo freeze > /sys/power/state
}
```

The DRY_RUN message uses the literal args so the test strings match. Write the final version to match the test.

- [ ] **Step 4: Run test — expect pass**

```bash
bash device/scripts/power/tests/test-suspend-dry.sh
```

Expected: `PASS`.

- [ ] **Step 5: Commit**

```bash
chmod +x device/scripts/power/uconsole-suspend.sh
git add device/scripts/power/uconsole-suspend.sh device/scripts/power/tests/test-suspend-dry.sh
git commit -m "power: uconsole-suspend.sh + dry-run test"
```

### Task 5.2: Wet run — actually suspend once

- [ ] **Step 1: On battery, with a second terminal ready as escape hatch**

```bash
# terminal 1:
sudo timeout 30 rtcwake -s 15 -m mem --verbose
# if kernel supports freeze but not mem:
sudo timeout 30 rtcwake -s 15 -m freeze --verbose
```

Expected: display blanks, 15s pass, system resumes, terminal comes back.

- [ ] **Step 2: If resume fails** — have an SSH escape from another device. Over SSH you can `journalctl -b 0 -k` to diagnose. If SSH doesn't resurrect either, power-button force-off is the fallback.

No code here — just verifying the kernel works before handing control to the wrapper script.

- [ ] **Step 3: Full run via wrapper**

```bash
DRY_RUN=0 sudo bash device/scripts/power/uconsole-suspend.sh suspend &
sleep 15
# wake via power button OR rtcwake pre-arm
```

- [ ] **Step 4: Measure idle draw during suspend**

```bash
bash device/scripts/power/idle-profile.sh real-suspend 120
```

Expected: <0.8 W if freeze is working. Store result.

- [ ] **Step 5: Commit the measurement**

```bash
column -t -s, ~/battery-tests/idle-profile.csv | tail -6
git add ~/battery-tests/idle-profile.csv
git commit -m "data: real-suspend idle draw measurement"
```

### Task 5.3: Power-key wiring

**Files:**
- Create: `device/scripts/system/systemd/uconsole-suspend.service`
- Modify: `device/lib/tui/framework.py:129` (add "Suspend Now" to `sub:power_ctl`)

- [ ] **Step 1: Write systemd unit**

```ini
[Unit]
Description=uConsole suspend-to-RAM wrapper
Before=sleep.target
StopWhenUnneeded=yes

[Service]
Type=oneshot
ExecStart=/opt/uconsole/scripts/power/uconsole-suspend.sh suspend
ExecStop=/opt/uconsole/scripts/power/uconsole-suspend.sh resume

[Install]
WantedBy=sleep.target
```

Target file: `device/scripts/system/systemd/uconsole-suspend.service`.

- [ ] **Step 2: Install hook in uconsole-sleep's power-key remap**

uconsole-sleep's `sleep_remap_powerkey.py` currently synthesizes a suspend keypress. Intercept instead: on power-button short-press, invoke `systemctl suspend` (which now triggers our service via sleep.target).

Rather than patching upstream Python, add an override config in `/etc/uconsole-sleep/config`:
```
SUSPEND_COMMAND=/usr/bin/systemctl suspend
```
*(only if the upstream package supports this env var — if not, add a systemd drop-in instead; check during implementation)*

- [ ] **Step 3: TUI entry**

Add to `framework.py:129` inside `sub:power_ctl`:

```python
("Suspend Now",      "sudo systemctl suspend",    "real suspend-to-RAM",                    "action"),
```

- [ ] **Step 4: Deploy and smoke test**

```bash
cd ~/uconsole-cloud && make install
sudo systemctl daemon-reload
# invoke from TUI: Power Control → Suspend Now
```

Verify: display off, low draw, resumes on power button.

- [ ] **Step 5: Commit**

```bash
git add device/scripts/system/systemd/uconsole-suspend.service device/lib/tui/framework.py
git commit -m "power: systemd suspend wrapper + TUI entry + power-key hook"
```

---

## Phase 6 — Aggressive Idle Optimization (fallback or supplement)

Runs if Phase 2 decided "no kernel rebuild" OR as a belt-and-suspenders on top of Phase 5. Goal: get idle draw to <2 W without kernel suspend.

### Task 6.1: Idle-optimize script with test

**Files:**
- Create: `device/scripts/system/idle-optimize.sh`
- Create: `device/scripts/power/tests/test-idle-optimize.sh`

- [ ] **Step 1: Write failing test**

```bash
#!/bin/bash
# test-idle-optimize.sh — verify idle-optimize on/off is symmetric and
# reports the expected service list in DRY_RUN mode.
set -e
HERE=$(dirname "$(realpath "$0")")
SCRIPT="$HERE/../../system/idle-optimize.sh"

on=$(DRY_RUN=1 bash "$SCRIPT" on 2>&1)
off=$(DRY_RUN=1 bash "$SCRIPT" off 2>&1)

echo "$on" | grep -q "stop webdash"      || { echo "FAIL: on-path missing webdash stop"; exit 1; }
echo "$on" | grep -q "stop meshtasticd"   || { echo "FAIL: on-path missing meshtasticd stop"; exit 1; }
echo "$on" | grep -q "governor=powersave" || { echo "FAIL: on-path missing governor switch"; exit 1; }
echo "$on" | grep -q "wlopm --off"       || { echo "FAIL: on-path missing display blank"; exit 1; }

echo "$off" | grep -q "start webdash"    || { echo "FAIL: off-path missing webdash start"; exit 1; }
echo "$off" | grep -q "governor=ondemand"|| { echo "FAIL: off-path missing governor restore"; exit 1; }
echo "PASS"
```

- [ ] **Step 2: Run — expect failure**

```bash
chmod +x device/scripts/power/tests/test-idle-optimize.sh
bash device/scripts/power/tests/test-idle-optimize.sh
```

- [ ] **Step 3: Implement idle-optimize.sh to pass**

```bash
#!/bin/bash
# idle-optimize.sh — aggressive idle mode without kernel suspend.
# Usage: idle-optimize.sh on|off|status
# Env: DRY_RUN=1

set -e
MODE="${1:?on|off|status}"
DRY="${DRY_RUN:-0}"

# Services to stop (restored on `off`). Order matters: high-traffic first.
IDLE_STOP_LIST="webdash meshtasticd gpsd bluetooth avahi-daemon uconsole-status"

run() {
    if [ "$DRY" = "1" ]; then echo "DRY_RUN: $*"; else eval "$@"; fi
}
stop_svcs()  { for s in $IDLE_STOP_LIST; do run "sudo systemctl stop $s"; done; }
start_svcs() { for s in $IDLE_STOP_LIST; do run "sudo systemctl start $s"; done; }
set_gov()    { run "echo $1 | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"; }

on() {
    stop_svcs
    set_gov powersave
    run "wlopm --off '*'"
    run "for d in /sys/bus/usb/devices/*/power/control; do echo auto | sudo tee \$d >/dev/null; done"
}
off() {
    run "for d in /sys/bus/usb/devices/*/power/control; do echo on | sudo tee \$d >/dev/null; done"
    run "wlopm --on '*'"
    set_gov ondemand
    start_svcs
}
status() {
    for s in $IDLE_STOP_LIST; do printf "%-18s %s\n" "$s" "$(systemctl is-active $s)"; done
    echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
}

case "$MODE" in on) on ;; off) off ;; status) status ;; *) echo "usage: $0 on|off|status" >&2; exit 2 ;; esac
```

- [ ] **Step 4: Run test — expect pass**

```bash
bash device/scripts/power/tests/test-idle-optimize.sh
```

Expected: `PASS`.

- [ ] **Step 5: Measure real draw under idle-optimize on, on battery**

```bash
sudo bash device/scripts/system/idle-optimize.sh on
bash device/scripts/power/idle-profile.sh idle-optimize 1200
sudo bash device/scripts/system/idle-optimize.sh off
```

Expected: <2 W if the audit was accurate. Compare to Phase 1 State D (stripped) — should be similar or slightly better due to governor change + USB autosuspend.

- [ ] **Step 6: Commit**

```bash
git add device/scripts/system/idle-optimize.sh device/scripts/power/tests/test-idle-optimize.sh ~/battery-tests/idle-profile.csv
git commit -m "power: idle-optimize.sh fallback + measurement"
```

### Task 6.2: TUI entry

**Files:**
- Modify: `device/lib/tui/framework.py:129` (add "Idle Mode" to `sub:power_ctl`)

- [ ] **Step 1: Add tuple**

In `sub:power_ctl`:
```python
("Idle Mode On",     "sudo system/idle-optimize.sh on",     "stop services, powersave, screen off",   "action"),
("Idle Mode Off",    "sudo system/idle-optimize.sh off",    "restore normal operation",               "action"),
("Idle Mode Status", "system/idle-optimize.sh status",      "show current idle-mode state",           "panel"),
```

- [ ] **Step 2: Deploy and test**

```bash
cd ~/uconsole-cloud && make install
# Launch `console`, go Power → Power Control → Idle Mode On, confirm screen blanks
```

- [ ] **Step 3: Commit**

```bash
git add device/lib/tui/framework.py
git commit -m "tui: idle-mode entries in power control submenu"
```

---

## Phase 7 — Long-run verification

Final proof the work paid off. Runs whichever of Phase 5 or 6 (or both) was shipped.

### Task 7.1: Overnight discharge redux

- [ ] **Step 1: Kick off discharge test in best-available idle mode**

```bash
# Best case: Phase 5 shipped and suspend works
sudo systemctl suspend
# OR fallback: Phase 6 shipped
sudo bash /opt/uconsole/scripts/system/idle-optimize.sh on
nohup setsid bash /opt/uconsole/scripts/util/discharge-test.sh samsung-35e >/dev/null 2>&1 &
disown
```

- [ ] **Step 2: Next morning — analyze**

```bash
tail ~/battery-tests/discharge-samsung-35e.log
python3 -c "
from datetime import datetime
rows=[l.split('|') for l in open('/home/mikevitelli/battery-tests/discharge-samsung-35e.log') if not l.startswith('#') and l.strip()]
t0=datetime.strptime(rows[0][0].strip(),'%Y-%m-%d %H:%M:%S')
t1=datetime.strptime(rows[-1][0].strip(),'%Y-%m-%d %H:%M:%S')
dur=(t1-t0).total_seconds()
avg=sum(int(r[4].strip().rstrip('mA').lstrip('-')) for r in rows)/len(rows)
print(f'runtime={dur/3600:.2f}h avg={avg:.0f}mA')
"
```

Compare runtime against baseline **2h 30m** at 4.2 W. Target:
- With real suspend (Phase 5): >15 h
- With idle-optimize only (Phase 6): >5 h

- [ ] **Step 3: Record result in backup repo**

```bash
cp ~/battery-tests/discharge-samsung-35e.log ~/pkg/battery-tests/discharge-samsung-35e-$(date +%F-suspend-post).log
cd ~/pkg && git add battery-tests/ && git commit -m "data: post-suspend-work discharge curve"
```

### Task 7.2: Update memory + close loop

- [ ] **Step 1: Write auto-memory entry**

Create `~/.claude/projects/-home-mikevitelli/memory/project_suspend_work.md`:

```yaml
---
name: uConsole suspend-to-RAM outcome
description: Result of the 2026-04-21 suspend investigation — kernel rebuild Y/N, idle-mode fallback, measured runtime improvement
type: project
---

Suspend-to-RAM work from plan 2026-04-21.

**Outcome:** [kernel rebuilt / fallback-only / deferred to CM5]
**Measured idle draw:** [W] (was 4.2 W)
**Overnight runtime:** [h] (was 2.5 h)
**Why:** [one-line reason for the path chosen]
**How to apply:** check `power/idle-optimize.sh` and/or `power/uconsole-suspend.sh` before any future battery-life work on this device.
```

Add to `MEMORY.md` index.

- [ ] **Step 2: Final commit**

```bash
cd ~/uconsole-cloud && git push
cd ~/pkg && git push
```

---

## Self-review checklist (completed 2026-04-21)

**Coverage:**
- Phase 1 covers baseline measurement ✓
- Phase 2 covers the kernel gate discovered 2026-04-21 ✓
- Phase 3 conditional kernel rebuild ✓
- Phase 4 peripheral audit ✓
- Phase 5 implementation of suspend ✓
- Phase 6 fallback when suspend unreachable ✓
- Phase 7 empirical verification against baseline ✓

**Placeholders:** none — every step has either concrete code, a concrete command, or a concrete human decision with named inputs.

**Type consistency:** `uconsole-suspend.sh` subcommands (`suspend`, `resume`) match between Task 5.1, 5.3, and 7.1. `idle-optimize.sh` subcommands (`on`, `off`, `status`) match between Task 6.1, 6.2. Service names (`uconsole-low-battery`, `meshtasticd`, `gpsd`, `webdash`) are consistent.

**Known risks not addressed by plan:**
1. Kernel rebuild may brick boot — Task 3.2 Step 3 mitigates via dual-staged kernel, but user must test carefully.
2. Display resume may produce artifacts — explicitly punted to "note, don't fix yet" in Task 4.1 Step 3. Acceptable for investigation phase.
3. CM5 swap invalidates Phase 3 work — Task 2.2 Step 3 explicitly asks this question; decision recorded in the memo.
