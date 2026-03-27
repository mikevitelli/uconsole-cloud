<div align="center">

<br/>

<img src="frontend/src/app/opengraph-image.png" alt="uConsole Cloud" width="400" />

<br/>

# uConsole Cloud

**Remote monitoring and management for the ClockworkPi uConsole.**

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

A cloud dashboard and device management platform for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole). Sign in with GitHub, install on your device, and get:

- **Live device telemetry** — battery, CPU, memory, disk, WiFi, AIO board — pushed every 5 minutes
- **Persistent status** — last-known data survives device going offline, with stale indicators
- **Backup monitoring** — coverage across 9 categories, history with sparklines
- **Local web dashboard** — HTTPS webdash at `uconsole.local` via mDNS, with WiFi fallback AP
- **System inventory** — packages, browser extensions, scripts, repo structure
- **PWA** — installable on iOS/Android for quick access
- **Device code auth** — link devices with a 6-character code or QR scan
- **.deb packaging** — two-command install: `apt install` + `uconsole setup`

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

## Architecture

```
uConsole (arm64, Debian)                 Cloud (Vercel)
┌──────────────────────────┐         ┌──────────────────────────┐
│                          │         │                          │
│  push-status.sh ──────────────→    │  Upstash Redis           │
│  (systemd timer, 5 min)  │  POST  │  (device:{repo}:status)  │
│                          │        │         │                │
│  backup.sh ───────────────────→   │         ▼                │
│  (git push)              │  git   │  Next.js 16 SSR          │
│                          │        │  ┌────────────────────┐  │
│  webdash.py ◄──┐         │        │  │ Server Components  │  │
│  (Flask:8080)  │ nginx   │        │  │ + GitHub API proxy │  │
│                │ :443    │        │  └────────────────────┘  │
└────────────────┘         │        │         │                │
                           │        │         ▼                │
  Phone / Browser          │        │    HTML stream           │
  ┌─────────────────┐      │        │                          │
  │ uconsole.cloud   │ ◄────────────│                          │
  │ uconsole.local   │ ◄──┘        └──────────────────────────┘
  └─────────────────┘
```

**Device → Redis → Dashboard.** No polling from the browser. The device pushes; the dashboard reads on page load. Data persists across device reboots — the last-known status is always available.

## Getting started

### Option A: .deb package (recommended)

```bash
# On the uConsole
sudo dpkg -i uconsole-cloud-tools_0.1.0_arm64.deb
sudo apt-get install -f    # resolve dependencies
uconsole setup             # scan QR or enter code at uconsole.cloud/link
```

### Option B: curl installer

```bash
# On the uConsole
curl -fsSL https://uconsole.cloud/install | bash
uconsole setup
```

Both methods install the `uconsole` CLI, `push-status.sh`, and configure a systemd timer for automatic telemetry pushes.

## Device telemetry

The `push-status.sh` script collects from sysfs and procfs every 5 minutes:

| Category | Source | Metrics |
|----------|--------|---------|
| Battery | `/sys/class/power_supply/axp20x-battery/` | capacity, voltage, current, status, health |
| CPU | `/sys/class/thermal/`, `/proc/loadavg` | temperature, load average, core count |
| Memory | `/proc/meminfo` | total, used, available |
| Disk | `df` | total, used, available, percent |
| WiFi | `iwconfig wlan0` | SSID, signal dBm, quality, bitrate, IP |
| Screen | `/sys/class/backlight/` | brightness, max brightness |
| AIO Board | `lsusb`, `/dev/spidev4.0`, `/dev/ttyS0`, `i2cdetect` | SDR, LoRa, GPS fix, RTC sync |
| Webdash | `systemctl` | running, port |
| System | `hostname`, `uname`, `/proc/uptime` | hostname, kernel, uptime |

## uconsole CLI

```
uconsole setup     Link device via code auth (QR + manual entry)
uconsole push      Push status now
uconsole status    Show config, timer status, last push
uconsole doctor    Diagnose services, SSL, nginx, connectivity
uconsole restore   Run restore.sh from backup repo
uconsole unlink    Remove config and stop timer
uconsole update    Re-download scripts (or upgrade .deb)
uconsole help      Show all commands
```

The CLI auto-detects whether it was installed via `.deb` (system paths at `/opt/uconsole/`) or curl (user paths at `~/`).

## .deb package

The `packaging/` directory builds a `.deb` for arm64 that includes all scripts, systemd services, nginx config, avahi mDNS, and the CLI:

```
uconsole-cloud-tools_0.1.0_arm64.deb
├── /opt/uconsole/scripts/     28 management scripts + CLI
├── /usr/bin/uconsole          symlink → /opt/uconsole/scripts/uconsole
├── /etc/systemd/system/       7 unit files (webdash, status, backup, update)
├── /etc/nginx/sites-available/uconsole-webdash
└── /etc/avahi/services/       mDNS advertisement
```

Build from the Mac:

```bash
cd uconsole-cloud
bash packaging/build-deb.sh
scp build/*.deb uconsole:/tmp/
```

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
| `/install` | GET | No | Bash installer script |
| `/link` | Page | No | Device code entry (accepts `?code=` for QR) |

## Project structure

```
uconsole-cloud/
├── frontend/                       Next.js 16 app
│   ├── src/
│   │   ├── app/                    Pages, API routes, server actions
│   │   │   ├── page.tsx            Main dashboard (Server Component)
│   │   │   ├── link/page.tsx       Device code entry page
│   │   │   ├── install/route.ts    Bash installer endpoint
│   │   │   ├── actions.ts          Server actions (sign in/out, unlink)
│   │   │   ├── manifest.ts         PWA manifest
│   │   │   └── api/                16 API routes
│   │   ├── components/
│   │   │   ├── dashboard/          12 dashboard sections
│   │   │   ├── viz/                7 visualization components
│   │   │   └── *.tsx               Shared UI (RepoLinker, CopyCommand, etc.)
│   │   ├── lib/                    14 modules (auth, redis, github, etc.)
│   │   └── __tests__/              138 tests (vitest)
│   ├── public/scripts/             Install-time copies of CLI + push-status.sh
│   └── next.config.ts              Security headers, image config
├── packaging/                      .deb build system
│   ├── build-deb.sh                Build script (runs on Mac)
│   ├── control                     Package metadata + dependencies
│   ├── postinst                    SSL cert gen, service setup
│   ├── prerm                       Service teardown
│   ├── systemd/                    7 unit files
│   ├── nginx/                      HTTPS reverse proxy config
│   └── avahi/                      mDNS service advertisement
├── studio/                         Sanity CMS workspace
└── package.json                    npm workspace root
```

## Security

| Protection | Implementation |
|------------|----------------|
| Auth | NextAuth v5 + GitHub OAuth, middleware-enforced on all API routes |
| Device auth | Bearer tokens (90-day UUIDs), rate-limited code generation |
| Input validation | Path traversal blocks, SHA regex, strict repo format validation |
| Headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy |
| Error handling | Typed GitHubError (401/403 surfaced), error boundary hides internals |
| Data isolation | Redis keys scoped by repo, device tokens scoped by user |
| Local TLS | Self-signed cert for uconsole.local (generated at install) |
| Secrets | `status.env` is chmod 600, `/var/lib/uconsole/` is chmod 700 |

## Tech stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Framework | Next.js 16 | App Router, Server Components, Server Actions |
| Auth | NextAuth v5 | GitHub OAuth with JWT strategy |
| Data | Upstash Redis | Device telemetry (persistent), device codes (10-min TTL) |
| Backup data | GitHub REST API | Commits, tree, raw files, packages |
| CMS | Sanity v3 | Landing page and dashboard copy |
| Styling | Tailwind CSS v4 | GitHub-dark theme with CSS variables |
| Testing | Vitest | 138 tests — parsing, security, API, validation |
| Hosting | Vercel | Auto-deploy from main, preview on PRs |
| Device | Bash + Python | 28 scripts, Flask webdash, systemd services |

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

## Environments

| Environment | Domain | Trigger |
|-------------|--------|---------|
| Production | [`uconsole.cloud`](https://uconsole.cloud) | Push to `main` |
| Preview | `*.vercel.app` | PRs and branches |
| Local | `localhost:3000` | `npm run dev` |

---

<div align="center">

Built for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole).

`66 source files · 138 tests · 16 API routes · 27 components · 28 device scripts`

</div>
