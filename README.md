<div align="center">

<br/>

<img src="frontend/src/app/opengraph-image.png" alt="uConsole Cloud" width="400" />

<br/>

# uConsole Cloud

**Remote monitoring and management for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole).**

[![Live](https://img.shields.io/badge/live-uconsole.cloud-58a6ff?style=for-the-badge)](https://uconsole.cloud)

[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-v4-06b6d4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-black?style=flat-square&logo=vercel)](https://vercel.com)
[![Tests](https://img.shields.io/badge/tests-138%20passing-3fb950?style=flat-square)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

</div>

---

## What is this?

A three-tier platform for managing the ClockworkPi uConsole — a modular ARM handheld Linux terminal (RPi CM4, 5" IPS, QWERTY keyboard, Debian Bookworm).

**On your device:** a `.deb` package installs 40+ management scripts, a curses TUI, a Flask web dashboard with terminal access, and systemd services that push telemetry to the cloud every 5 minutes.

**On your local network:** the web dashboard runs at `https://uconsole.local` via nginx + self-signed TLS, accessible from any phone or laptop on the same WiFi. If no known network is available, the device creates a fallback AP ("uConsole") so you can always connect.

**In the cloud:** this Next.js app at [uconsole.cloud](https://uconsole.cloud) shows live device status, backup coverage, system inventory, and hardware info — from anywhere.

```
┌──────────────────────────────────────────────────────────────┐
│                      uconsole.cloud                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ Battery: 100% │  │ CPU: 34.0°C  │  │ WiFi: Big Parma    │ │
│  │ Charging      │  │ Load: 0.18   │  │ Signal: -57 dBm    │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ Mem: 1.5/3.8G │  │ Disk: 45%    │  │ SDR: RTL2838       │ │
│  │               │  │ 13G / 29G    │  │ LoRa: SX1262       │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
│                                                              │
│  ● Device offline — last seen 2h ago                         │
│                                                              │
│  ┌──── Backup Coverage ─────────────────────────────────┐    │
│  │  Shell configs   ● today   │  Desktop       ● 6d     │    │
│  │  System configs  ● today   │  Git/SSH       ● today  │    │
│  │  Packages (287)  ● today   │  GitHub CLI    ● today  │    │
│  │  Browser (12)    ● today   │  Scripts       ● today  │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  Backup History │ Packages │ Extensions │ Scripts │ Repo     │
└──────────────────────────────────────────────────────────────┘
```

### Features

- **Live device telemetry** — battery, CPU, memory, disk, WiFi, screen, AIO board — pushed every 5 minutes
- **Persistent status** — last-known data survives reboots and offline periods, with staleness indicators
- **Hardware manifest** — detects expansion module, SDR, LoRa, GPS, RTC, ESP32 at setup
- **Backup monitoring** — coverage across 9 categories, commit history with sparklines and calendar grid
- **System inventory** — packages, browser extensions, scripts manifest, repo tree
- **Local web dashboard** — HTTPS at `uconsole.local` via mDNS, with WiFi fallback AP
- **Same-network detection** — shows a direct link to the local dashboard when you're on the same WiFi
- **PWA** — installable on iOS/Android for quick access from your phone
- **Device code auth** — link devices with an 8-character code or QR scan, no typing passwords on tiny keyboards
- **APT repository** — `curl | sudo bash` adds the repo, `apt upgrade` handles future updates

### Optional hardware

The [HackerGadgets AIO expansion board](https://www.hackergadgets.com/) adds RTL-SDR, LoRa SX1262, GPS, and RTC to the uConsole. All radio features in the dashboard gracefully degrade when no AIO board is present — most users won't have one, and everything works without it.

---

## Getting started

### Install on your uConsole

```bash
curl -s https://uconsole.cloud/install | sudo bash
uconsole setup
```

This adds the APT repository, installs `uconsole-tools`, and walks you through hardware detection and cloud linking. Future updates arrive via `sudo apt upgrade`.

### What happens

1. **APT repo added** — GPG key + source list for `uconsole.cloud/apt`
2. **Package installed** — CLI, scripts, systemd services, nginx config, avahi mDNS
3. **`uconsole setup`** — detects hardware, generates SSL cert, sets passwords, optionally links to uconsole.cloud via device code auth
4. **Telemetry starts** — `push-status.sh` runs every 5 minutes via systemd timer
5. **Webdash starts** — Flask app at `:8080`, nginx reverse proxy at `:443`

Cloud linking is optional. Everything works 100% offline — the local webdash, TUI, and all management scripts run without internet.

---

## Architecture

```
uConsole (arm64, Debian)                 Cloud (Vercel)
┌──────────────────────────┐         ┌──────────────────────────┐
│                          │         │                          │
│  /opt/uconsole/          │         │  uconsole.cloud          │
│  ├── bin/                │         │                          │
│  │   ├── uconsole  CLI   │         │  Upstash Redis           │
│  │   └── console   TUI   │         │  (device:{repo}:status)  │
│  ├── scripts/            │         │         │                │
│  │   ├── system/         │         │         │                │
│  │   │   └── push-status ────→     │         ▼                │
│  │   ├── power/          │  POST   │  Next.js 16 SSR          │
│  │   ├── network/        │         │  ┌────────────────────┐  │
│  │   ├── radio/          │         │  │ Server Components  │  │
│  │   └── util/           │         │  │ + GitHub API proxy │  │
│  ├── webdash/            │         │  └────────────────────┘  │
│  │   └── webdash.py ◄──┐│         │         │                │
│  └── lib/               ││         │         ▼                │
│                    nginx ││         │    HTML stream           │
│                    :443  ││         │                          │
│                          ││         │  /apt/ (APT repository)  │
└──────────────────────────┘│         │  /install (bootstrap)    │
                            │         └──────────────────────────┘
  Phone / Browser           │
  ┌─────────────────┐       │
  │ uconsole.cloud   │ ◄─────── Vercel CDN
  │ uconsole.local   │ ◄──┘
  └─────────────────┘
```

**Device → Redis → Dashboard.** No polling from the browser. The device pushes; the dashboard reads on page load. Data persists indefinitely — the last-known status is always available.

---

## Device telemetry

`push-status.sh` collects from sysfs and procfs every 5 minutes:

| Category | Source | Metrics |
|----------|--------|---------|
| Battery | `/sys/class/power_supply/axp20x-battery/` | capacity, voltage, current, status, health |
| CPU | `/sys/class/thermal/`, `/proc/loadavg` | temperature, load average, core count |
| Memory | `/proc/meminfo` | total, used, available |
| Disk | `df` | total, used, available, percent |
| WiFi | `iwconfig wlan0` | SSID, signal dBm, quality, bitrate, IP |
| Screen | `/sys/class/backlight/` | brightness, max brightness |
| AIO Board | `lsusb`, `/dev/spidev4.0`, `/dev/ttyS0`, `i2cdetect` | SDR, LoRa, GPS fix, RTC sync |
| Hardware | `/etc/uconsole/hardware.json` | expansion module, component detection, system info |
| Webdash | `systemctl` | running, port |
| System | `hostname`, `uname`, `/proc/uptime` | hostname, kernel, uptime |

---

## uconsole CLI

```
uconsole setup     Interactive setup wizard (hardware detect, passwords, cloud link)
uconsole push      Push status now
uconsole status    Show config, timer status, last push
uconsole doctor    Diagnose services, SSL, nginx, connectivity
uconsole restore   Run restore.sh from backup repo
uconsole unlink    Remove cloud config and stop timer
uconsole update    Update via APT (or re-download scripts for curl installs)
uconsole help      Show all commands
```

---

## .deb package

The `uconsole-tools` package installs to `/opt/uconsole/` with organized subdirectories:

```
uconsole-tools_0.1.0_arm64.deb
├── /opt/uconsole/
│   ├── bin/                    uconsole CLI, console TUI launcher
│   ├── lib/                    tui_lib.py, lib.sh, shared modules
│   ├── scripts/
│   │   ├── system/             push-status, backup, restore, update, doctor, setup
│   │   ├── power/              battery, charge, power management (safety-critical)
│   │   ├── network/            wifi, hotspot, tailscale
│   │   ├── radio/              sdr, lora, gps, rtc (AIO board)
│   │   └── util/               everything else
│   ├── webdash/                Flask app, templates, static assets
│   └── share/                  themes, battery-data, esp32, default configs
├── /etc/uconsole/              uconsole.conf, hardware.json, ssl/
├── /etc/systemd/system/        7 unit files (not auto-enabled)
├── /etc/nginx/sites-available/ uconsole-webdash (not auto-enabled)
├── /etc/avahi/services/        mDNS advertisement
├── /usr/bin/uconsole           symlink → /opt/uconsole/bin/uconsole
└── /var/lib/uconsole/          runtime data (status.env, tokens)
```

Services are **not** auto-started on install — `uconsole setup` handles that after the interactive configuration wizard.

### Building

```bash
make build-deb          # → dist/uconsole-tools_0.1.0_arm64.deb
make publish-apt        # update APT repo in frontend/public/apt/
make release            # bump version, build, publish, commit + tag
```

---

## API routes

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/api/device/code` | POST | No | Generate device code (rate-limited 5/min/IP) |
| `/api/device/code/confirm` | POST | Session | Confirm code, generate device token |
| `/api/device/poll/[secret]` | GET | No | Poll for code confirmation |
| `/api/device/push` | POST | Bearer | Accept device telemetry |
| `/api/device/status` | GET | Session | Fetch cached status + online flag |
| `/api/github/*` | GET/POST | Session | GitHub API proxy (repos, commits, tree) |
| `/api/settings` | GET/POST/DELETE | Session | User settings, repo linking |
| `/api/settings/regenerate-token` | POST | Session | Regenerate device token |
| `/api/scripts/[name]` | GET | No | Serve allowlisted scripts |
| `/api/health` | GET | No | Redis health check |
| `/install` | GET | No | APT bootstrap script |
| `/apt/*` | GET | No | APT repository (Packages, Release, .deb files) |
| `/link` | Page | No | Device code entry (accepts `?code=` for QR) |

See [docs/DEVICE-LINKING.md](docs/DEVICE-LINKING.md) for the full device auth flow.

---

## Project structure

```
uconsole-cloud/
├── frontend/                       Next.js 16 app
│   ├── src/
│   │   ├── app/                    Pages, API routes, server actions
│   │   │   ├── page.tsx            Main dashboard (Server Component)
│   │   │   ├── link/page.tsx       Device code entry page
│   │   │   ├── install/route.ts    APT bootstrap script endpoint
│   │   │   ├── actions.ts          Server actions (sign in/out, unlink)
│   │   │   ├── manifest.ts         PWA manifest
│   │   │   └── api/                16 API routes
│   │   ├── components/
│   │   │   ├── dashboard/          17 dashboard sections
│   │   │   ├── viz/                7 visualization components
│   │   │   └── *.tsx               Shared UI (RepoLinker, DeviceCodeForm, etc.)
│   │   ├── lib/                    20 modules (auth, redis, github, device config, etc.)
│   │   └── __tests__/              138 tests (vitest)
│   ├── public/
│   │   ├── scripts/                Install-time copies of CLI + push-status.sh
│   │   ├── install.sh              APT bootstrap installer
│   │   └── apt/                    APT repository (generated, gitignored pool/dists)
│   └── next.config.ts              Security headers, image config
├── packaging/                      .deb build system
│   ├── build-deb.sh                Build script (reads VERSION, organized layout)
│   ├── control                     Package metadata + dependencies
│   ├── postinst                    Config setup (no auto-start)
│   ├── prerm                       Service teardown
│   ├── postrm                      Purge cleanup
│   ├── defaults/                   uconsole.conf.default
│   ├── systemd/                    7 unit files
│   ├── nginx/                      HTTPS reverse proxy config
│   ├── avahi/                      mDNS service advertisement
│   ├── scripts/                    generate-repo.sh, generate-gpg-key.sh
│   └── apt-repo/                   APT repository docs
├── docs/                           Architecture documentation
│   └── DEVICE-LINKING.md           Device auth flow (ASCII diagrams, API shapes)
├── studio/                         Sanity CMS workspace
├── Makefile                        build-deb, publish-apt, release, version bumps
├── VERSION                         Package version (semver)
└── package.json                    npm workspace root
```

---

## Security

| Protection | Implementation |
|------------|----------------|
| Auth | NextAuth v5 + GitHub OAuth, middleware-enforced on all API routes |
| Device auth | Bearer tokens (90-day UUIDs), rate-limited code generation (5/min/IP) |
| Input validation | Path traversal blocks, SHA regex, strict repo format validation |
| Headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy |
| Error handling | Typed GitHubError (401/403 surfaced), error boundary hides internals |
| Data isolation | Redis keys scoped by repo, device tokens scoped by user |
| Local TLS | Self-signed cert at `/etc/uconsole/ssl/` (generated at install) |
| Secrets | `status.env` is chmod 600, `/var/lib/uconsole/` is chmod 700 |
| APT repo | GPG-signed Release files, key distributed via HTTPS |

---

## Tech stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Framework | Next.js 16 | App Router, Server Components, Server Actions |
| Auth | NextAuth v5 | GitHub OAuth with JWT strategy |
| Data | Upstash Redis | Device telemetry (persistent), device codes (10-min TTL) |
| Backup data | GitHub REST API | Commits, tree, raw files, packages |
| CMS | Sanity v3 | Landing page and dashboard copy |
| Styling | Tailwind CSS v4 | GitHub-dark theme with CSS variables |
| Testing | Vitest 4 | 138 tests — parsing, security, API, validation |
| Hosting | Vercel | Auto-deploy from main, preview on PRs |
| Device | Bash + Python | 40+ scripts, Flask webdash, curses TUI, systemd services |
| Packaging | dpkg + APT | `.deb` for arm64, signed repository on Vercel |

---

## Local development

```bash
git clone https://github.com/mikevitelli/uconsole-cloud.git
cd uconsole-cloud
npm install

# Configure environment
cp frontend/.env.example frontend/.env.local
# Fill in: GITHUB_ID, GITHUB_SECRET, AUTH_SECRET,
#          UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN

npm run dev        # frontend :3000, studio :3333
npm test           # 138 tests
npm run build      # production build
```

### Makefile targets

```
make version       Print current version
make bump-patch    Bump patch version (0.1.0 → 0.1.1)
make bump-minor    Bump minor version (0.1.0 → 0.2.0)
make bump-major    Bump major version (0.1.0 → 1.0.0)
make build-deb     Build .deb package to dist/
make publish-apt   Update APT repo from latest .deb
make release       Bump + build + publish + commit + tag
make clean         Remove build artifacts
```

---

## Environments

| Environment | Domain | Trigger |
|-------------|--------|---------|
| Production | [`uconsole.cloud`](https://uconsole.cloud) | Push to `main` |
| Preview | `*.vercel.app` | PRs and branches |
| Local | `localhost:3000` | `npm run dev` |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — especially from uConsole owners who can test device-side changes on real hardware.

---

<div align="center">

Built for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole).

`89 source files · 138 tests · 16 API routes · 32 components · 40+ device scripts`

</div>
