# Changelog

## v0.1.6 (2026-04-08)

Developer experience and diagnostics.

### Added
- `make dev-mode` / `make pkg-mode` — toggle webdash between dev tree and installed package
- `make install` copies the `uconsole` CLI wrapper and auto-restarts webdash if running
- `uconsole doctor` verifies webdash actually responds (catches crash loops)
- `uconsole doctor` checks avahi-daemon and uconsole.local mDNS resolution
- `uconsole --version` shows `(dev)` suffix when dev.conf drop-in is active
- `Ctrl+`` keybind for console TUI shipped with install (injected into labwc rc.xml)
- Dev vs package version display — footer shows `v0.1.6-dev` from dev tree, `v0.1.6` from package
- `console-pkg` wrapper and `UCONSOLE_PKG_ONLY` env var for testing the installed version
- `.console-config.json.example` with default TUI preferences
- Self-hosting documentation in README

### Fixed
- `build-deb.sh` symlink chmod warnings silenced (skip symlinks)
- `make install` uses consistent `RSYNC_EXCLUDE` variable across all targets
- Dynamic `sub:esp32` submenu exempted from static reference check

### Refactored
- `postinst`: extracted `get_real_user()` / `get_real_home()` — replaces 3 inconsistent inline user detections
- `Makefile`: shared `RSYNC_EXCLUDE` variable for all rsync calls

### Testing
- ESP32 utility modules (`esp32_detect`, `esp32_flash`) exempted from `run_*` handler check
- 821 tests passing, 0 failures

---

## What's next (v0.1.7+)

- **ESP32 smart detection** — flexible chip detection, multi-firmware flash support, CFW compatibility
- **Runtime tests** — curses TUI rendering tests, Flask webdash route tests, CLI integration tests
- **uconsole CLI refactor** — extract path resolution into shared helper, reduce 24 `INSTALL_MODE` branches
- **Database abstraction** — support self-hosted Redis (ioredis) alongside Upstash REST API
- **Webdash improvements** — live reload in dev mode, better error pages
- **CI on device** — arm64 test runner for device-side tests (pytest + bash)

---

## v0.1.5 (2026-04-08)

Canonical source restructure, dev workflow, and TUI polish.

### Changed
- **Canonical source**: `example-device/` renamed to `device/` — this is now the source of truth for the device package, not a copy
- **Branching**: `dev`/`main` workflow — `dev` for active work, `main` for released state only
- **Default view**: TUI default view mode changed from list to tiles
- **CI**: triggers on `dev` branch instead of `staging`
- **build-deb.sh**: reads from `device/` by default instead of `~/uconsole/pkg`

### Added
- `make install` target — rsyncs `device/` to `/opt/uconsole/` and `~/pkg/` for rapid dev iteration
- Version number displayed in TUI footer on all screens (tiles, list, submenus, panel, stream, process manager)
- `device/VERSION` file for dev-tree version display

### Fixed
- **postinst**: `User=UCONSOLE_USER` substitution when `SUDO_USER` is unset — falls back to `logname`, then first non-root user (UID >= 1000). Previously left the placeholder in systemd units, causing crash loop.
- **rsync**: removed `--delete` from `~/pkg/` sync to preserve backup-only files (configs, package manifests, SSH keys, WiFi connections)

---

## v0.1.4 (2026-04-06)

Security hardening release. Backfills the full security audit from 2026-04-04 that was missed in v0.1.3.

### Security
- Webdash: bind to 127.0.0.1 (localhost only), CORS whitelist, PTY auth gate, rate-limited public APIs, security headers
- Scripts: mask hotspot password in output, curl timeouts (push-status, speed test), crash-log uses XDG_RUNTIME_DIR
- Systemd: PrivateTmp, ProtectSystem=strict, NoNewPrivileges on webdash service

### Added
- Workspace-monitor C extension (Wayland protocol for active workspace tracking)
- Updated trackball-scroll.py

### Fixed
- Sanitized device source (formerly example-device): removed SSH keys, pulse cookie, GitHub repo list, device-specific configs from published package
- Test assertions updated for SCRIPT_DIR refactor

---

## v0.1.3 (2026-04-05)

Docs expansion, security fixes, and path architecture refactor.

### Security
- AST-based calculator replaces eval() in TUI
- PID range guard (2-4194304) in process killer

### Added
- Docs page: scripts (46), TUI modules (12), webdash API (46 routes), services, troubleshooting
- Dashboard overview section in README

### Fixed
- Console entry point uses _PKG_ROOT relative path (dev tree priority)
- SCRIPT_DIR uses _PKG_ROOT resolution (no ~/scripts shadowing)
- _resolve_cmd doubled subdir bug (util/util/webdash-info.sh)
- Release workflow: contents:write permission

---

## v0.1.2 (2026-04-04)

Script path architecture and TUI test suite.

### Added
- TUI test suite (798 pytest tests)
- Script path architecture: all 147 menu entries use subdir prefixes (power/, network/, radio/, system/, util/)
- _webdash_config wired as native tool

### Fixed
- SCRIPT_DIR uses _PKG_ROOT instead of ~/scripts fallback
- Console entry point resolves lib relative to package root
- Move TUI config to ~/.config/uconsole/ (permission denied in package mode)

---

## v0.1.1 (2026-04-03)

Bug fixes and release automation.

### Device Package
- Fix: move cron cleanup before re-link prompt during setup (avoids stale cron entries)
- Fix: improve `uconsole doctor` dual-fire warning (clearer messaging when both cron and timer exist)
- Fix: GPG key import in install script — add `--batch --yes` to dearmor for non-interactive installs

### Cloud Dashboard
- GitHub Actions release workflow for automated `.deb` builds and APT repo publishing
- Fix: APT repository headers (correct MIME types, cache control)

### Device Scripts
- Marauder TUI integration (ESP32 Marauder serial interface)
- Battery discharge test expansion with configurable profiles
- Forum browser (ClockworkPi forum access from TUI)
- Trackball scroll support in TUI
- Games category in TUI
- Webdash migrated to systemd service (from manual start)
- Shared utility libraries (`lib.sh`, `tui_lib.py`)

---

## v0.1.0 (2026-03-28)

First public release.

### Device Package (`uconsole-cloud`)
- 40+ management scripts organized by category (system, power, network, radio, util)
- Curses TUI with 8 categories and 14 native tools (FM Radio, GPS globe, live monitor, file browser, etc.)
- Flask web dashboard with terminal access, live stats, script execution, PWA support
- Interactive setup wizard (hardware detection, bcrypt passwords, SSL certs, cloud linking)
- `uconsole` CLI: setup, link, push, status, doctor, restore, unlink, update, version
- Systemd services run as the installing user (not root)
- Self-signed TLS with SANs (Chrome-compatible)
- WiFi fallback AP when no known network available
- Optional AIO board support (RTL-SDR, LoRa, GPS, RTC) — graceful degradation

### Cloud Dashboard (`uconsole.cloud`)
- Live device telemetry (battery, CPU, memory, disk, WiFi, AIO board)
- Persistent status — survives reboots, shows staleness indicators
- Backup coverage across 9 categories with sparklines and calendar grid
- Package inventory, browser extensions, scripts manifest, repo tree
- Hardware manifest panel
- Device code auth (8-character code + QR scan)
- Same-network detection with direct local webdash link
- PWA installable on iOS/Android
- GPG-signed APT repository hosted on Vercel
- `curl -s https://uconsole.cloud/install | sudo bash` install story
- Documentation page at /docs

### Security
- bcrypt password hashing (replaces plaintext)
- Cryptographic session tokens (secrets.token_hex)
- Server-side session store with 30-day TTL
- Rate-limited device code generation (5/min/IP)
- CSP, X-Frame-Options, nosniff, strict Referrer-Policy
- Redis keys scoped by repo, device tokens scoped by user
