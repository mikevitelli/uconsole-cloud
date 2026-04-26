# Feature map

Current state of the uconsole-cloud platform as of v0.2.1. For the full release log, see [CHANGELOG.md](../CHANGELOG.md). For active design work, see `docs/plans/` and `docs/specs/`.

## Shipped

### Cloud dashboard (uconsole.cloud)

- GitHub OAuth login (NextAuth v5, JWT)
- Device code linking flow (code → confirm → token, rate-limited)
- Live device telemetry from Upstash Redis (battery, CPU, memory, disk, WiFi, AIO board, hardware)
- Backup repo coverage across 9 categories (sparklines, calendar grid)
- Local Shell Hub link when webdash is detected on the device
- PWA manifest + Safari standalone meta tags
- GPG-signed APT repo at `/apt/` (served via Vercel CDN)
- `/install` bootstrap endpoint
- Documentation page at `/docs` (install, CLI, architecture, troubleshooting)
- GitHub Actions release workflow (.deb build + APT publish on tag)

### Device CLI (`uconsole`)

- `setup` — interactive wizard (hardware detect, passwords, SSL, cloud link)
- `link` — code-auth flow with QR display
- `push` — manual telemetry push
- `status` — config + timer state + last push
- `doctor` — service / SSL / nginx / connectivity / cron-vs-timer-conflict diagnosis
- `restore` — runs `restore.sh --yes` from backup repo
- `unlink` — removes cloud config, stops timer
- `update` — `apt upgrade` wrapper
- `logs [svc]` — tail journal for a service
- `version`, `help`

### Device TUI (`console`)

9 categories, 64 native handlers, plus direct-run shell scripts. Each feature module owns its handlers via a `HANDLERS = {"_foo": fn}` dict; framework.py walks `FEATURE_MODULES` and merges them.

- **SYSTEM** — Updates, Backups, Webdash control, Cron/Timer viewer
- **MONITOR** — 1-second live gauges, process manager, system logs, crash log
- **FILES** — file browser, audit (junk/untracked/categories), disk usage, storage
- **POWER** — battery status, cell health, battery test, power control, hardware config
- **NETWORK** — iPhone hotspot connect, WiFi switcher, diagnostics, Bluetooth, SSH bookmarks
- **HARDWARE** — AIO board check, GPS receiver (with globe), SDR radio, ADS-B map (global low-res basemap + on-demand hi-res fetch + layer picker), LoRa Mesh / Meshtastic mesh map, ESP32 hub (firmware detect, MicroPython/Marauder/MimiClaw/Bruce flashing, wardrive, MimiClaw chat)
- **TOOLS** — git panel, notes, calculator, stopwatch, pomodoro, weather, Hacker News, uConsole forum, Telegram client (tg + tdlib), markdown viewer, screenshot
- **GAMES** — Watch Dogs Go (auto-installs from GitHub on first run), minesweeper, snake, tetris, 2048, ROM launcher (Game Boy / N64)
- **CONFIG** — TUI theme (30+), view mode, keybinds, battery gauge, trackball scroll, push interval, Watch Dogs config

External GUI programs (emulators, Watch Dogs Go) launch through `tui.launcher` with `start_new_session=True` + `DEVNULL` stdio so child crashes can't disturb the curses parent.

### Webdash (local)

- Flask app at `/opt/uconsole/webdash/app.py`, behind nginx HTTPS on `:443`
- Mounted at `https://uconsole.local` via avahi/mDNS
- Bcrypt password hashing, cryptographic session tokens, 30-day server-side session store
- 60+ scripts runnable from the panel
- Live monitor via SSE (1s push while panel open)
- Documentation wiki served at `/docs` (these very pages)
- Crash log viewer, timer scheduling, config management

### Packaging

- `.deb` for arm64 (Debian Bookworm)
- GPG-signed APT repo, key distributed via HTTPS
- `curl -s https://uconsole.cloud/install | sudo bash` bootstrap
- postinst handles SSL cert generation, user detection, nginx config, systemd unit setup
- prerm/postrm clean up cleanly on uninstall/purge
- Docker arm64 install test in CI (verifies install, upgrade, uninstall, purge, reinstall)
- `uconsole update` uses APT
- `make build-deb`, `make publish-apt`, `make release`, `/publish` slash command

### Network resilience

- WiFi fallback dispatcher — auto-creates uConsole AP when no known WiFi available, tears it down when one returns
- mDNS service advertisement (`/etc/avahi/services/webdash.service`)
- nginx error pages for webdash-down states (502/503/504)

## Active design

| Area | Status | Reference |
|------|--------|-----------|
| Suspend-to-RAM | Plan written, blocked on kernel rebuild (CONFIG_SUSPEND=n in stock CM4 kernel) | [`docs/plans/2026-04-21-uconsole-suspend-to-ram.md`](plans/2026-04-21-uconsole-suspend-to-ram.md) |

## Open issues

Tracked on [GitHub Issues](https://github.com/mikevitelli/uconsole-cloud/issues). Notable open security and robustness items from the 2026-04-09 audit:

- [#45](https://github.com/mikevitelli/uconsole-cloud/issues/45) — Replace `eval`-based variable assignment in `uconsole-setup` with `printf -v`
- [#46](https://github.com/mikevitelli/uconsole-cloud/issues/46) — `uconsole` CLI `eval`s env file content; parse explicitly
- [#47](https://github.com/mikevitelli/uconsole-cloud/issues/47) — `push-status.sh` sources env file every 5 min; parse explicitly
- [#48](https://github.com/mikevitelli/uconsole-cloud/issues/48) — Add `timeout=` to `systemctl` calls in `config_ui.py` to prevent TUI freeze
- [#49](https://github.com/mikevitelli/uconsole-cloud/issues/49) — Roll out `set -euo pipefail` to remaining 32 of 47 bash scripts

For the full audit triage, see [`docs/audits/2026-04-09/STATUS.md`](audits/2026-04-09/STATUS.md).

## Backlog (future considerations)

Cloud dashboard:
- WiFi fallback state in telemetry (`wifiFallback.enabled`, `wifiFallback.apName`)
- Smart offline messaging — infer AP mode when fallback enabled + device gone silent
- AP gateway IP in Local Shell Hub (10.42.0.1) when device is in AP mode
- Connection timeline (Redis sorted set of online/offline transitions)
- Battery/temperature alert thresholds
- Historical charts (battery over time, CPU temp trends)
- Multi-device support — one user → many uConsoles, device selector

Device:
- HMAC request signing on push payloads
- Device token rotation (shorter TTL, auto-refresh)
- Optional Tailscale integration (HTTPS + remote webdash via tailnet)
- Optional webdash basic auth for shared networks
- `uconsole setup --github` (GitHub Device Flow → no second device for linking)

Repo / DX:
- E2E tests for device code flow on staging
- Integration tests for push → Redis → dashboard read
- Self-hosted arm64 CI runner on the device itself

These are ideas, not commitments. PRs welcome — see [CONTRIBUTING.md](../CONTRIBUTING.md).
