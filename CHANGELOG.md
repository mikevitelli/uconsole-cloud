# Changelog

## v0.2.1

Push Interval improvements.

### Added
- **Push Interval → off** — new option in CONFIG that disables the
  `uconsole-status.timer` user-scope systemd timer (`systemctl --user
  disable --now`), letting users opt out of cloud telemetry pushes
  entirely without uninstalling the package. Reversible — picking any
  interval from `30s` to `30min` re-enables the timer.

### Changed
- **Push Interval moved from SERVICES to CONFIG** — the entry now lives
  alongside other persistent preferences (theme, view mode, keybinds)
  rather than under one-off service controls.

## v0.2.0 (2026-04-15)

Watch Dogs Go TUI launcher, ADS-B global basemap, Telegram TUI client,
shared detached-spawn helper, and ROM Launcher crash fix.

### Added
- **Watch Dogs Go launcher** (`tui.watchdogs`) — new GAMES entry with
  install-on-first-run flow, config page under CONFIG (install path,
  auto-update, repo URL), smart path detection ($WATCHDOGS_HOME → ~/python
  → ~/ → ~/git → /opt), and auto-detected terminal emulator for the
  install window (lxterminal/foot/kitty/xterm/alacritty/xfce4/gnome-terminal).
- **`tui.launcher`** — shared detached-spawn helper used by Watch Dogs Go
  and the ROM Launcher. `launch_gui()` for GUI apps (retroarch, mgba,
  gearboy), `launch_in_terminal()` for TTY-needing commands. Uses
  `start_new_session=True` + DEVNULL stdio so child exit/crash cannot
  propagate signals to the curses parent. PID lockfile helper with
  stale cleanup and symlink-safe atomic write via `tempfile.mkstemp`.
- **ADS-B global basemap** (from feature/adsb-global-basemap) — global
  layered basemap (`adsb_basemap_global.json`), hi-res fetch
  (`adsb_hires.py`), layer picker, home picker, basemap info panel.
  New builder script `scripts/build_adsb_basemap.py` and planning doc.
- **Telegram TUI client** (`tui.telegram`) — terminal chat client using
  the official `tg` CLI with tdlib. New installer `install-tdlib.sh`
  and validator `validate-telegram.sh` under `device/scripts/system/`.
  Wired into the TOOLS section and covered by 682 lines of tests.

### Changed
- **GAMES section ordering** — Watch Dogs Go now appears first, above
  Minesweeper/Snake/Tetris/2048/ROM Launcher.
- **`_get_native_tools()`** wraps the watchdogs import in try/except so
  a broken submodule can no longer brick the entire native-tools
  registry; falls back to a stub on import failure.

### Fixed
- **ROM Launcher crash-on-close** (`tui.games.run_romlauncher`) — removed
  the `curses.endwin()` + blocking `subprocess.run()` pattern that
  invalidated the curses state, causing `scr.refresh()` / `curses.doupdate()`
  to crash when the emulator exited. Now uses a detached `Popen` with
  the same hardened kwargs as `launch_gui`, closes the gamepad fd
  before spawning (prevents /dev/input/js0 race), normalizes ROM path
  to absolute, and draws a launch toast before returning so the user
  sees success/failure feedback.
- **webdash 502 in dev mode** — `app.py` now adds `device/lib/` to the
  `sys.path` search list, so running webdash directly from the source
  tree (via the `dev.conf` drop-in) can find `ascii_logos.py`. Installed
  `/opt/uconsole` mode was unaffected.
- **Login page banner** — hardcoded "uConsole" ASCII now reads
  "uConsole.local", matching the dashboard's randomized pool.

### Security
- **Path allowlist** for `find_watchdogs_path` — `realpath` + home/opt
  prefix check blocks malicious `$WATCHDOGS_HOME` redirects.
- **Terminal allowlist** for `$WATCHDOGS_TERMINAL` — basename must match
  `KNOWN_TERMINALS`; executable file check required.
- **git clone injection** — install flow uses `git clone --` + repo URL
  regex allowlist (`^(https?://|git@)…\.git$`) with silent fallback to
  the default LOCOSP/WatchDogsGo upstream.
- **Lockfile hardening** — atomic `tempfile.mkstemp` with per-process
  suffix, 0o600 perms, stale-PID cleanup; no symlink follow, no retry
  on collision.

### Tests
- 997 tests passing (up from 946). New test-suite fixes:
  - `test_native_tools.py`: allow `from tui import <submodule>` style
    imports (module objects skipped for the callable assertion);
    orphan-module check extended to match the alternate import form;
    `launcher.py` exempted as a helper library.
- `install-tdlib.sh` and `validate-telegram.sh` moved under
  `device/scripts/system/` to satisfy the script-subdirectory check.

---

## v0.1.7 (2026-04-08)

CLI logs command, tab completion, test targets, and CLI refactor.

### Added
- `uconsole logs [service] [-f]` — show service logs, defaults to webdash, supports follow mode
- Tab completion for all CLI commands + logs service names (installed to /usr/share/bash-completion/completions/)
- `make test` / `make test-device` / `make test-frontend` — unified test targets
- `make dev-mode` / `make pkg-mode` in CONTRIBUTING docs
- Dynamic dev version from `git describe` — TUI footer shows `v0.1.7-dev` automatically
- `make test-install` — Docker-based install verification (18 tests on Debian Bookworm arm64)
- ARM64 Docker install test in CI via QEMU emulation

### Changed
- `uconsole doctor` shows dev.conf override status (informational `[--]` marker)
- `uconsole doctor` references `uconsole logs` in error hints
- CI runs full pytest suite (821 tests) instead of just TUI integrity, plus shell syntax checks

### Refactored
- CLI: extracted `maybe_sudo()`, `run_journalctl()`, `manage_timer()`, `get_push_script()`, `service_to_unit()` — reduced INSTALL_MODE branches from 24 to ~10
- Completion script follows Debian policy (`/usr/share/bash-completion/completions/`)
- `make bump-*` auto-syncs `device/VERSION` from root `VERSION`

### Fixed
- Dynamic `sub:esp32` submenu exempted from static reference check in tests
- postinst tolerates missing systemd (Docker/chroot installs)
- Bash completion installed to `/usr/share/bash-completion/completions/` (Debian policy)
- Frontend devicePaths test updated for CLI refactor

---

## What's next (v0.1.8+)

- **ESP32 smart detection** — flexible chip detection, CFW compatibility
- **Runtime tests** — curses TUI, Flask webdash, CLI integration tests
- **Database abstraction** — support self-hosted Redis alongside Upstash
- **CI on device** — self-hosted arm64 runner (optional)

---

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
