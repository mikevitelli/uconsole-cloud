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

```bash
# Frontend (requires Node 22+)
npm test                                    # 117 vitest tests
npm run lint                                # ESLint
npx -w @uconsole/frontend tsc --noEmit     # typecheck

# Device (Python 3.9+, runs on any platform)
pip install pytest
python3 -m pytest tests/ -v                # 821 tests

# Shell scripts
find device/scripts -name "*.sh" -exec bash -n {} \;

# Python syntax
find device -name "*.py" -exec python3 -m py_compile {} \;

# Full build check
npm run build -w @uconsole/frontend
make build-deb                              # builds the .deb (arm64)
```

The Python test suite checks structural integrity — every menu entry resolves to a real script, every import resolves, every native tool handler exists, scripts have correct permissions and shebangs. It catches the class of bug where you rename a function and forget to update the menu that references it.

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
