# uconsole-cloud Project Roadmap

*Generated from deep audit on 2026-04-09 after v0.1.7 release*

## v0.1.8 — Security Hardening (CRITICAL)

These were found in the security audit and should be fixed before promoting the project.

### Must Fix
- [ ] **Webdash: password reset without auth** — `/api/set-password` is in `_PUBLIC_PATHS`, anyone on LAN can hijack. Add `_password_is_set()` guard. (`device/webdash/app.py:225-242`)
- [ ] **uconsole-setup: eval injection** — `ask()` uses `eval "$var=..."` on user input. Replace with `printf -v`. (`device/bin/uconsole-setup:64,73`)
- [ ] **CLI: eval on untrusted env file** — `eval "$(maybe_sudo cat status.env)"`. Parse with grep/cut instead. (`frontend/public/scripts/uconsole:134`)
- [ ] **push-status.sh: source without validation** — `source "$ENV_FILE"` executes arbitrary code. Use grep/cut. (`device/scripts/system/push-status.sh:14`)
- [ ] **lora.sh: source user config without validation** — same pattern. (`device/scripts/radio/lora.sh:46`)

### Should Fix
- [ ] Add `set -euo pipefail` to the 26 scripts that lack error handling (prioritize power/ scripts: `charge.sh`, `cpu-freq-cap.sh`, `pmu-voltage-min.sh`)
- [ ] Add timeouts to `systemctl` calls in `config_ui.py` (7 instances without timeout)
- [ ] Add timeout to `git describe` call in `framework.py:40`
- [ ] Fix `hardware-detect.sh` writing to `/etc/` without sudo
- [ ] Guard `chgrp www-data` in postinst for environments without www-data group

## v0.1.9 — Install Robustness

From the install funnel audit.

- [ ] **install.sh: add architecture check** — fail early on non-arm64 with clear message
- [ ] **install.sh: add GPG key fingerprint verification** after download
- [ ] **install.sh: add trap cleanup** — remove apt source on failure
- [ ] **Dockerfile.test: add upgrade test** — install v0.1.6, upgrade to v0.1.7, verify
- [ ] **Dockerfile.test: add uninstall/purge test** — verify prerm/postrm cleanup
- [ ] **postinst: guard www-data chgrp** with `getent group www-data` check
- [ ] **Test: add false-positive check** — intentionally break a script path and verify tests catch it

## v0.2.0 — Multi-Device Support

From the multi-tenancy research.

### Data Model
- [ ] Decouple device identity from repo — assign device IDs (`dev_` + 8-char random) during setup
- [ ] `user:{userId}` stores array of device IDs, not single repo
- [ ] Dashboard shows device selector for multi-device users
- [ ] Backward compatible — existing single-device users get one-element array

### Redis Efficiency
- [ ] Add TTL to `device:{id}:status` (48h) — stale devices auto-expire
- [ ] Delta compression — only push changed fields (est. 60-80% bandwidth reduction)
- [ ] Hourly aggregation — roll 5-min snapshots into hourly summaries after 24h
- [ ] Projected: ~2KB/device/push × 288 pushes/day × 30 days = ~17MB/device/month on Upstash free tier (200MB) supports ~11 devices with history

### Proposed Key Schema
```
user:{userId}                    → { devices: [...], defaultDevice: "..." }
device:{deviceId}:meta           → { name, repo, userId, linkedAt }
device:{deviceId}:status         → { ...full payload... }  TTL: 48h
device:{deviceId}:history:{date} → sorted set of hourly summaries
devicetoken:{uuid}               → { deviceId, userId }
```

## v0.2.1 — Developer Experience

- [ ] **Webdash live reload in dev mode** — watch file changes, auto-restart
- [ ] **Runtime tests** — curses TUI rendering tests with mock terminal
- [ ] **Flask route tests** — test webdash endpoints with test client
- [ ] **CLI integration tests** — test `uconsole doctor`, `uconsole status`, `uconsole logs`
- [ ] **Self-hosted runner** — optional arm64 CI on the device itself

## Backlog

### Scripts Quality
- [ ] Replace bare `except:` clauses in embedded Python within shell scripts (gps.sh, sdr.sh, battery-test.sh)
- [ ] Reduce 73 broad `except Exception: pass` in TUI modules — add logging for debugging
- [ ] Add trap handlers for temp file cleanup in scripts that create them
- [ ] Validate LoRa config file before sourcing
- [ ] Fix `network.sh` unbound variable with `${2:-}` pattern

### Testing
- [ ] Multi-user Docker test — two containers pushing simultaneously
- [ ] CI: add shellcheck to all device scripts (currently only install.sh and uconsole CLI)
- [ ] Test webdash session persistence across restarts
- [ ] Add test for `uconsole link` polling flow (mock API)

### Documentation
- [ ] API documentation (device push endpoint schema, error codes)
- [ ] Architecture diagram (device → Redis → dashboard data flow)
- [ ] Hardware compatibility matrix (which features need which hardware)

---

## Audit Reports (2026-04-09)

- [01-tui-scripts-audit.md](01-tui-scripts-audit.md) — Shell scripts + Python modules
- [02-install-funnel-audit.md](02-install-funnel-audit.md) — Install path, tests, CI
- [03-multi-tenancy-research.md](03-multi-tenancy-research.md) — Multi-device, Redis, data patterns
- [04-cli-webdash-security.md](04-cli-webdash-security.md) — Security review
