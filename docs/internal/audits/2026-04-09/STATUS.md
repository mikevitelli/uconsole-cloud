# 2026-04-09 Audit — Status as of 2026-04-26 (v0.2.2 prep)

The 9 reports in this directory are a snapshot from when the project was at v0.1.7. We're now prepping **v0.2.2** (~3 weeks, ~100 commits later). Some items shipped, some are still open, some no longer apply.

This file is the index. The original reports stay for the reasoning and detail. **If you want to act on any item below, verify against current code first** — the audit is now ~17 days stale and the codebase has moved.

## v0.1.8 — Security hardening (`04-cli-webdash-security.md`)

| Item | Status | Notes |
|---|---|---|
| Webdash `/api/set-password` requires `_password_is_set()` | ✅ shipped | guard at `device/webdash/app.py:230` |
| `uconsole-setup` eval injection (lines 64, 73) | ✅ shipped (#45) | replaced with `printf -v` in v0.2.2 |
| `uconsole` CLI eval on env file | ✅ shipped (#46) | `read_env_value()` helper in v0.2.2 (covers cmd_link AND cmd_status) |
| `push-status.sh` source without validation | ✅ shipped (#47) | grep-based parser in v0.2.2 |
| `lora.sh` source user config | ✅ shipped | type-validated parser added in v0.2.2 (audit Must-Fix, no individual issue) |
| `set -euo pipefail` across scripts | ⚠️ partial (#49) | safety-critical PMU subset (charge, cpu-freq-cap, pmu-voltage-min) added in v0.2.2; remaining ~32 scripts deferred to v0.2.3 |
| `systemctl` timeouts in `config_ui.py` | ✅ shipped (#48) | all 7 calls now have `timeout=10` in v0.2.2 |
| `git describe` timeout in `framework.py:40` | ✅ N/A | `git describe` removed entirely; framework reads `VERSION` file directly |
| `hardware-detect.sh` writing to `/etc/` | ? | re-verify against current script |
| postinst `chgrp www-data` guard | ? | re-verify against current postinst |

## v0.1.9 — Install robustness (`02-install-funnel-audit.md`)

| Item | Status |
|---|---|
| `install.sh` architecture check | ❌ open — only a config-string mention of `arch=arm64`, no runtime check |
| `install.sh` GPG fingerprint verification | ❌ open |
| `install.sh` trap cleanup | ❌ open |
| `Dockerfile.test` upgrade test | ? — re-verify |
| `Dockerfile.test` uninstall/purge test | ? — re-verify |
| postinst `getent group www-data` guard | ? — re-verify |
| Test for false-positive script-path detection | ? — re-verify |

## v0.2.0 — Multi-device support (`03-multi-tenancy-research.md`)

We're past v0.2.0 in version numbering. Whether the multi-tenancy data model in this report was implemented vs. deferred needs a look at `frontend/src/app/api/` and the Redis schema. This is a substantial body of work — treat the report as a design proposal that may or may not match what shipped.

## v0.2.1 — Developer experience (`06-webdash-architecture.md` etc.)

| Item | Status |
|---|---|
| Webdash live reload in dev mode | ⚠️ partial — `make dev-mode` exists but no file watcher |
| Runtime tests for curses TUI | ❌ open — only AST-based static checks today |
| Flask route tests | ? — re-verify |
| CLI integration tests | ? — re-verify |
| Self-hosted arm64 runner | ❌ open — CI runs on GitHub-hosted x86 with Docker arm64 emulation |

## Other audit reports

| Report | Notes |
|---|---|
| `01-tui-scripts-audit.md` | TUI's been heavily refactored since (handler registry, ESP32 hub extraction, emoji icons). Most file-line refs are stale. |
| `05-tui-ux-research.md` | Research, not a backlog. Useful context if you're touching TUI UX. |
| `07-community-building.md` | Strategic. Status depends on what you've done with marketing/docs publicly. |
| `08-frontend-audit.md` | Re-verify against current `frontend/`. |

## How to use this index

If you're triaging "which audit items still need work":

1. Skim this file for the ❌ rows.
2. Open the corresponding report in this directory for the original reasoning.
3. Verify the issue still exists in current code (`grep`, look at the cited file:line).
4. Either fix it or add a one-line note here explaining why it's intentionally deferred.

If a category is mostly ✅ or N/A, the original report can probably be deleted in a future cleanup pass — but keeping it is cheap, and the reasoning is sometimes useful for future audits of the same area.
