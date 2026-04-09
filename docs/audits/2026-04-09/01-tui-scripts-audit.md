# TUI Scripts & Python Modules Audit

*Generated: 2026-04-09*

Now I have enough data to produce the comprehensive audit. Let me compile the findings.

---

Here is the comprehensive audit report covering all 38 shell scripts (plus 5 lib.sh files) and 13 Python TUI modules.

---

## AUDIT REPORT: device/scripts/ and device/lib/tui/

### Syntax Check: All 43 shell scripts pass `bash -n`. All 13 Python modules import cleanly.

---

## CRITICAL (will crash or lose data)

### C1. `restore.sh` uses `local` outside a function (lines 177, 196)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/system/restore.sh`

The `local` keyword appears inside an if-block at the top level of the script (not inside a function). While bash tolerates this, it is a no-op (the variable is already global). This is not technically a crash bug in bash, but it *will* crash in strict POSIX `sh` and is semantically misleading. Under `set -e`, a `local` assignment that fails (e.g., command substitution error) behaves differently inside vs outside a function.

### C2. `discharge-test.sh` uses `--no-gpg-sign` in git commit (line 165)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/util/discharge-test.sh`

The `push_to_github()` function runs `git commit --no-gpg-sign` which bypasses GPG signing. This contradicts the CLAUDE.md convention. If the repo requires signed commits, this will silently produce unsigned commits pushed automatically every 15 minutes.

### C3. `hardware-detect.sh` writes to `/etc/uconsole/hardware.json` without sudo (line 225)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/util/hardware-detect.sh`

The script writes `echo "$json" > "$OUT_FILE"` where `OUT_FILE="/etc/uconsole/hardware.json"` (line 37). This will fail with "Permission denied" unless the script is run as root or the directory is world-writable. The `--json` flag works around this, but the default path will crash for non-root users.

### C4. `network.sh` passes unset `$2` to cmd_ping/cmd_trace (lines 224-225)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/network/network.sh`

The case statement passes `"$2"` to `cmd_ping` and `cmd_trace`, but if the user runs `network.sh ping` without a host argument, `$2` is empty. The functions handle this with defaults, but `set -euo pipefail` (if added) would cause an "unbound variable" crash since the script doesn't use `${2:-}`.

### C5. `push-status.sh` sources `status.env` without validation (line 14)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/system/push-status.sh`

The script runs `source "$ENV_FILE"` which executes arbitrary code from the env file. If status.env is corrupted or contains unexpected shell commands, they will execute in the context of the push-status cron job. The file is chmod 600 (per CLAUDE.md), but there's no validation of contents before sourcing.

### C6. `lora.sh` sources user config file without validation (line 46)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/radio/lora.sh`

`source "$LORA_CONF"` executes arbitrary shell code from `~/.config/uconsole/lora.conf`. A malformed or tampered config file could execute arbitrary commands.

---

## WARNING (bad practice, could cause issues)

### W1. 26 of 38 scripts lack `set -e` or `set -euo pipefail`
The following scripts have no error handling flags: `network.sh`, `wifi-fallback.sh` (has it as NM dispatcher but not in the sourced-from mode), `wifi.sh` (missing, but has flock), `battery.sh`, `cellhealth.sh`, `charge.sh`, `cpu-freq-cap.sh`, `fix-voltage-cutoff.sh` (has it), `low-battery-shutdown.sh`, `pmu-voltage-min.sh`, `power.sh`, `aio-check.sh`, `backup.sh`, `push-status.sh` (has it), `restore.sh`, `update.sh`, `audit.sh`, `boot-check.sh`, `config.sh`, `console.sh`, `crash-log.sh`, `dashboard.sh`, `discharge-test.sh`, `diskusage.sh`, `storage.sh`, `webdash-ctl.sh`, `webdash-info.sh`, `webdash.sh`.

Note: Some scripts (like backup.sh, dashboard.sh) intentionally run multiple commands that may fail individually, so `set -e` would need careful adoption. But scripts like `charge.sh`, `cpu-freq-cap.sh`, `pmu-voltage-min.sh` should definitely have it since they write to safety-critical sysfs paths.

### W2. Bare `except:` clauses in embedded Python within shell scripts
**Files:** `battery-test.sh` (line 248), `gps.sh` (lines 48, 79, 142, 200, 242, 266), `sdr.sh` (line 134)

These catch all exceptions including KeyboardInterrupt and SystemExit. Should use `except Exception:` at minimum.

### W3. `except Exception:` used broadly in TUI modules (73 instances)
The Python TUI modules heavily use `except Exception:` with pass/continue. While this is common for TUI code that must not crash, some of these silently swallow real errors:
- `tools.py` (13 instances), `monitor.py` (14 instances), `framework.py` (14 instances)
- These make debugging difficult when things go wrong.

### W4. Multiple subprocess calls in Python without timeout
**Files and lines:**
- `config_ui.py` lines 389, 393, 403, 405, 413, 415, 417 -- systemctl calls without timeout
- `framework.py` line 40 -- `git describe` without timeout
- `framework.py` line 1115 -- `subprocess.run(cmd)` with no timeout (runs shell scripts interactively, but user might expect it to hang)
- `tools.py` line 417 -- `subprocess.run(["ssh", name])` without timeout (interactive, intentional)
- `tools.py` line 984 -- `subprocess.run([browser, url])` without timeout (interactive, intentional)
- `games.py` line 1397 -- `subprocess.run()` launching emulator without timeout (interactive, intentional)

The interactive ones are expected. The systemctl calls in `config_ui.py` and the `git describe` in `framework.py` should have timeouts.

### W5. `battery-test.sh` stress test creates orphaned background busy-loop processes (lines 438-444)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/power/battery-test.sh`

The `cmd_stress()` function spawns per-core busy loops (`while :; do :; done &`) inside a subshell, then `disown`s the subshell. The inner loops are children of the subshell, not of the main script. If the subshell is killed via `stop`, the inner `while :; do :; done` processes may not be killed because they are in separate process groups. The `cmd_stop()` function only kills the PID in `.stress.pid` (the subshell), not the grandchild busy loops.

However, `cellhealth.sh` has a proper approach: it uses `dd | md5sum` for CPU load (which responds to signals) and has a `trap cleanup_load EXIT INT TERM`.

### W6. `boot-check.sh` uses `bc` without checking if it's installed (line 10)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/util/boot-check.sh`

`echo "scale=3; $VOLTAGE_MV / 1000" | bc` will fail if `bc` is not installed. The similar calculation in other scripts uses `awk` which is always available. This is the only script using `bc`.

### W7. `discharge-test.sh` runs `git push origin main` from `$HOME` (line 166)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/util/discharge-test.sh`

The `push_to_github()` function does `cd "$HOME"` then `git add/commit/push`. This assumes `$HOME` is a git repo, but the repo is actually a subdirectory. If there's no git repo at `$HOME`, this will silently fail (errors redirected to `/dev/null`). The discharge log file may never actually get pushed.

### W8. `esp32.sh` and `esp32-marauder.sh` use inline Python with unsanitized variables
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/radio/esp32.sh` (lines 51-66)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/radio/esp32-marauder.sh` (line 44-69)

Variables like `$SERIAL_PORT`, `$BAUD`, and `$cmd` are interpolated directly into Python heredocs. A serial port path or command containing single quotes or Python special characters could break or inject code. The `marauder_cmd()` function passes `$cmd` unsanitized (line 46: `cmd, wait = sys.argv[1], ... sys.argv[3]`). Actually this one is safe since it uses `sys.argv`. But `esp32.sh`'s `serial_cmd()` (line 57) interpolates `$cmd` directly into a Python string `s.write(b'$cmd\r\n')` -- a command containing a single quote would break Python syntax.

### W9. `gps.sh` passes JSON through triple-quoted Python string literals
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/radio/gps.sh` (multiple locations)

JSON from gpspipe is passed like `json.loads('''$json''')`. If the JSON contains triple quotes (`'''`), this will break. While unlikely from gpsd, it's fragile.

### W10. No cleanup of `.tracking.pid` on GPS track crash
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/radio/gps.sh` (lines 126-161)

The GPX tracking background process writes its PID to `.tracking.pid` but has no trap handler. If the tracking subshell crashes, the PID file remains and the GPX file may be missing its closing tags (`</trkseg></trk></gpx>`). The `cmd_stop()` function handles the normal case but not crashes.

### W11. lib.sh symlinks point to `/opt/uconsole/lib/lib.sh` which is the installed path
All 5 `lib.sh` files in the script subdirectories are symlinks to `/opt/uconsole/lib/lib.sh`. This means the scripts in the repo only work if the package is installed. For development/testing from the repo checkout, they would need to point to `../../lib/lib.sh`. This is a conscious design choice but worth noting.

### W12. `webdash.sh` kills processes by pattern matching (line 10)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/util/webdash.sh`

`pkill -f "python3.*webdash.py"` could match unrelated Python processes whose command line happens to contain "webdash.py" (e.g., a text editor with the file open).

---

## INFO (style/improvement suggestions)

### I1. Network/battery log writes without locking
`network.sh` appends to `~/network.log` and `battery.sh` appends to `~/battery.log` without flock. If two instances run concurrently (unlikely but possible with cron), log entries could interleave. Low risk since append operations on Linux are typically atomic for small writes.

### I2. Hardcoded WiFi connection names
**Files:** `wifi.sh` (lines 18-20), `wifi-fallback.sh` (line 33)
- `IPHONE_CON="Not Your iPhone"`
- `HOME_CON="Big Parma"`
- `OFFICE_CON="Digital Counsel"`

These are hardcoded. Consider reading from a config file (hotspot.sh already does this pattern with `$CONF_FILE`).

### I3. Hardcoded IFACE="wlan0" in multiple scripts
Network scripts (`hotspot.sh`, `wifi.sh`, `wifi-fallback.sh`, `network.sh`, `dashboard.sh`, `push-status.sh`) all hardcode `IFACE="wlan0"`. This is fine for the uConsole's single WiFi interface but could be centralized in lib.sh or a config.

### I4. `charge.sh` lacks `set -euo pipefail` (safety-critical script)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/power/charge.sh`

This script writes to sysfs to set battery charge current. Per CLAUDE.md: "Battery/power/charge scripts are safety-critical." The arithmetic on line 21 (`ua=$(($1 * 1000))`) would fail silently with non-numeric input without `set -e`.

### I5. `cpu-freq-cap.sh` and `pmu-voltage-min.sh` are very minimal
These 11 and 30 line scripts respectively lack shebangs comments, error handling flags, and logging. They write to critical sysfs paths.

### I6. `cellhealth.sh` has outdated cell info hardcoded (lines 24-27)
The comments reference "Nitecore NL1834" as the installed cells, but memory notes indicate Samsung INR18650-35E 3500mAh cells were installed on 2026-03-29. The `CELL_MODEL`, `CELL_CAPACITY`, and `CELL_INSTALL_DATE` variables are stale.

### I7. All `lib.sh` copies are identical (symlinks to same file)
This is correct behavior -- the per-directory `lib.sh` files are all symlinks to the same `/opt/uconsole/lib/lib.sh`. Good.

### I8. No TODO/FIXME/HACK comments found in Python TUI modules
Clean codebase.

### I9. `dashboard.sh` intentionally word-splits `$args` (line 192)
**File:** `/home/mikevitelli/uconsole-cloud/device/scripts/util/dashboard.sh`

`bash "$script" $args` is intentionally unquoted to allow multiple arguments. This is documented with a comment. Acceptable but a potential source of glob expansion issues if the user types `*` as an arg.

### I10. `push-status.sh` AIO ESP32 detection runs a script with 5s timeout (line 145)
This adds up to 5 seconds to every status push (every 5 minutes). If the ESP32 is not present, the timeout still runs. Consider checking for `/dev/esp32` before invoking the script.

### I11. Hardware detection handles missing hardware gracefully
`aio-check.sh`, `push-status.sh`, and `hardware-detect.sh` all properly use `2>/dev/null || true` patterns, `lsusb` checks, and `-e` file tests before accessing optional hardware (SDR, GPS, LoRa, ESP32, RTC). Good practice.

### I12. `config.sh` INI parser whitespace trimming uses wrong syntax (lines 36-37)
The patterns `${line##[[:space:]]}` and `${line%%[[:space:]]}` only strip a single character of whitespace, not all leading/trailing whitespace. Should be `${line##*([[:space:]])}` with `extglob`, or use `sed`/`awk`. In practice this likely works because most INI files don't have leading spaces, but it's technically incorrect.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 6 |
| WARNING | 12 |
| INFO | 12 |

**Key strengths of the codebase:**
- All scripts pass `bash -n` syntax check
- All Python modules import cleanly with no errors
- No bare `except:` clauses in Python modules (all use `except Exception:` or more specific)
- No TODO/FIXME/HACK comments left behind
- Good hardware detection patterns -- scripts gracefully handle missing SDR/GPS/LoRa/ESP32
- Lock file handling in `wifi.sh` and `wifi-fallback.sh` is solid (flock, XDG_RUNTIME_DIR, symlink checks)
- `cellhealth.sh` has proper trap cleanup for its CPU load test
- Security hardening from the March audit is evident (wifi-fallback.sh state dir validation, hotspot.sh config parsing)

**Highest priority items to address:**
1. C3: `hardware-detect.sh` /etc write without sudo
2. C5/C6: Config file sourcing without validation (push-status.sh, lora.sh)
3. W1: Add `set -euo pipefail` to safety-critical power scripts (`charge.sh`, `cpu-freq-cap.sh`, `pmu-voltage-min.sh`)
4. W5: Stress test orphaned process cleanup in `battery-test.sh`
5. W6: Replace `bc` with `awk` in `boot-check.sh`
6. W4: Add timeout to systemctl calls in `config_ui.py`