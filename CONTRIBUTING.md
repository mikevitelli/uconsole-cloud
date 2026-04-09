# Contributing

Thanks for your interest in uconsole-cloud! Contributions are welcome — especially from uConsole owners who can test on real hardware.

## Quick overview

This repo has two products in one:

1. **Cloud dashboard** (`frontend/`) — Next.js app at uconsole.cloud showing device telemetry
2. **Device package** (`device/`) — TUI, webdash, and 46 scripts installed via `.deb` on the uConsole

They share a repo because they ship together — the `.deb` is built from `device/` and hosted via the frontend's APT repo.

## Branching

| Branch | Purpose |
|--------|---------|
| `main` | Released state — tagged versions, deployed to Vercel + APT |
| `dev` | Active development — PRs target this branch, CI runs on push |

1. Fork the repo and create a branch from `dev` (not `main`)
2. Make your changes
3. Run tests (see below)
4. Open a pull request against `dev`

Do not open PRs against `main` — releases are merged from `dev` → `main` by maintainers.

## Setup

```bash
git clone https://github.com/mikevitelli/uconsole-cloud.git
cd uconsole-cloud
npm install
```

### Frontend development (cloud dashboard)

```bash
cp frontend/.env.example frontend/.env.local
# Fill in your credentials (see .env.example for details)
npm run dev        # frontend :3000, studio :3333
```

### Required environment variables

| Variable | Purpose |
|----------|---------|
| `GITHUB_ID` | GitHub OAuth app ID |
| `GITHUB_SECRET` | GitHub OAuth app secret |
| `AUTH_SECRET` | NextAuth JWT secret (`openssl rand -base64 33`) |
| `UPSTASH_REDIS_REST_URL` | Redis connection URL |
| `UPSTASH_REDIS_REST_TOKEN` | Redis auth token |
| `NEXT_PUBLIC_SANITY_PROJECT_ID` | Sanity CMS project ID (optional for dev) |

### Device development (TUI, webdash, scripts)

If you have a uConsole (or any arm64 Debian device):

```bash
# Edit source in device/
vim device/lib/tui/framework.py

# Deploy to device for testing
make install          # rsyncs device/ → /opt/uconsole/ and ~/pkg/

# Toggle between dev and package webdash
make dev-mode         # webdash runs from your repo checkout
make pkg-mode         # webdash runs from /opt/uconsole/ (installed .deb)
```

`make install` auto-restarts webdash if it's running. For TUI changes, just relaunch `console`.

If you don't have a uConsole, you can still run the Python tests and lint the shell scripts — they don't require hardware.

## Testing

The project has 4 test layers, from fast/local to slow/device-specific:

### 1. Source tests (runs anywhere, no hardware needed)

```bash
make test-device                    # 821 pytest tests + bash syntax + py_compile
make test-frontend                  # vitest + eslint + typecheck (requires Node 22)
make test                           # both of the above
```

What these catch: broken imports, missing scripts, menu/handler mismatches, shell syntax errors, TypeScript type errors, frontend regressions.

### 2. Docker install test (requires Docker, no hardware needed)

```bash
make test-install                   # builds .deb, installs in arm64 Debian Bookworm container
```

Runs 30+ tests in a fresh Debian container via QEMU arm64 emulation:
- Package installs cleanly
- postinst runs (User= substitution, SSL certs, default password, nginx, config)
- Upgrade preserves config and passwords
- Uninstall removes CLI/completion but keeps config
- Purge removes everything
- Reinstall after purge works

On Apple Silicon or arm64 Linux, this runs natively (~40s). On x86, QEMU emulates (~3 min).

To explore the container interactively:
```bash
sudo docker run --rm -it uconsole-test bash
```

### 3. End-to-end test (requires the real device)

```bash
make test-e2e                       # installs .deb, tests live system
```

Tests on the actual uConsole with real systemd, nginx, mDNS:
- Installs the .deb (prompts for confirmation)
- Runs `uconsole doctor`
- Tests default password login
- Tests password change + set-password guard
- Verifies mDNS (uconsole.local resolves)
- Verifies HTTPS (webdash responds)
- Tests CLI commands (version, help, logs)
- Verifies systemd services are running

Only runs on the device — requires sudo.

### 4. CI (automatic on every push)

GitHub Actions runs on every push to `dev` or `main`:

| Job | What | Time |
|-----|------|------|
| `ci` | shellcheck, pytest, bash syntax, lint, typecheck, vitest, Next.js build | ~90s |
| `install-test` | Docker arm64 install test via QEMU | ~2.5min |

The e2e test is NOT in CI (requires real hardware).

### Running a single test file

```bash
python3 -m pytest tests/test_tui_integrity.py -v    # one test file
python3 -m pytest tests/ -k "test_each_script"      # filter by name
npm test -w @uconsole/frontend -- --run src/__tests__/devicePaths.test.ts  # one frontend test
```

### When to run what

| Scenario | Command |
|----------|---------|
| Editing device Python/bash | `make test-device` |
| Editing frontend TypeScript | `make test-frontend` |
| Before opening a PR | `make test` |
| Changed packaging/postinst | `make test-install` |
| Before a release | `make test-install && make test-e2e` |

## Versioning

You don't need to manually bump versions during development.

- **Dev tree**: the TUI footer auto-derives the version from `git describe --tags`, showing something like `v0.1.7-dev` (next version after the last release tag)
- **Installed package**: reads the static `VERSION` file, showing the released version (e.g. `v0.1.6`)
- **Releases**: maintainers run `make release` which bumps `VERSION`, builds the `.deb`, signs the APT repo, commits, and tags

The `uconsole --version` CLI command shows `(dev)` when a dev.conf systemd drop-in is detected.

## Project layout

```
frontend/src/
├── app/            Pages, API routes, server actions
├── components/
│   ├── dashboard/  17 sections (DeviceStatus, BackupHistory, HardwarePanel, etc.)
│   └── viz/        7 visualizations (Sparkline, Donut, CalendarGrid, Treemap, etc.)
├── lib/            20 modules (auth, redis, github, types, utils, etc.)
└── __tests__/      10 test suites (parsing, security, validation, API)

device/
├── bin/            Entry points (console, webdash, uconsole-setup, uconsole-passwd)
├── lib/tui/        TUI modules — each file is a feature area:
│   ├── framework.py    Main loop, menus, categories, themes, gamepad
│   ├── monitor.py      Live system monitor
│   ├── network.py      WiFi switcher, hotspot, bluetooth
│   ├── tools.py        Git, notes, calculator, SSH bookmarks, etc.
│   ├── games.py        Minesweeper, snake, tetris, 2048, ROM launcher
│   ├── radio.py        GPS globe, FM radio
│   ├── marauder.py     ESP32 Marauder interface
│   ├── services.py     Systemd service/timer management
│   ├── config_ui.py    Theme picker, view mode, settings
│   ├── files.py        File browser
│   ├── esp32_detect.py Chip detection (utility, not a TUI handler)
│   └── esp32_flash.py  Firmware flashing (utility, not a TUI handler)
├── scripts/        46 shell scripts organized by category:
│   ├── system/     backup, restore, update, push-status
│   ├── power/      battery, charge, cpu-freq, discharge tests
│   ├── network/    wifi, hotspot, wifi-fallback
│   ├── radio/      sdr, lora, gps, esp32
│   └── util/       webdash-ctl, audit, storage, diskusage
├── webdash/        Flask app (app.py, templates, static)
└── share/          Default configs, systemd units, keybind snippets

packaging/
├── build-deb.sh    Build script — reads from device/, outputs .deb
├── control         Package metadata + dependencies
├── postinst        Post-install (SSL certs, user detection, nginx, systemd)
├── prerm           Pre-remove (stop services)
├── postrm          Post-remove (purge configs)
├── systemd/        7 unit files
├── nginx/          HTTPS reverse proxy config
└── scripts/        APT repo generation + GPG key setup
```

**Key patterns:**
- Dashboard sections are Server Components that fetch from Redis/GitHub on page load
- `lib/` modules handle all data access — components don't call APIs directly
- Visualization components are client-only (`'use client'`) for interactivity
- TUI modules export `run_*` functions that `framework.py` dispatches via menus
- Shell scripts are organized by category and referenced in menus with subdir prefixes (e.g. `power/battery.sh`)

## Code style

- TypeScript throughout, strict mode
- Server Components by default — only add `'use client'` when needed
- Tailwind CSS v4 for styling (GitHub-dark theme)
- TUI follows existing curses patterns — read `framework.py` before adding new features
- Shell scripts use `bash`, include a shebang, and must pass `bash -n`
- Battery/power scripts are **safety-critical** — always flag for manual review

## What to work on

- Check [open issues](https://github.com/mikevitelli/uconsole-cloud/issues) for bugs or feature requests
- See [FEATURES.md](FEATURES.md) for the roadmap
- See [CHANGELOG.md](CHANGELOG.md) "What's next" section for planned work
- If you have a uConsole, testing the device scripts and CLI is especially helpful

## Questions?

Open an issue. There's no Discord or mailing list — GitHub issues are the place.
