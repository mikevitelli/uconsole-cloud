<div align="center">

<br/>

<img src="frontend/src/app/opengraph-image.png" alt="uConsole Cloud" width="400" />

<br/>

# uConsole Cloud

**Real-time device telemetry and backup monitoring for the ClockworkPi uConsole.**

[![Live](https://img.shields.io/badge/live-uconsole.cloud-58a6ff?style=for-the-badge)](https://uconsole.cloud)

[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-v4-06b6d4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-black?style=flat-square&logo=vercel)](https://vercel.com)
[![Tests](https://img.shields.io/badge/tests-106%20passing-3fb950?style=flat-square)]()

</div>

---

## What is this?

A dashboard that turns your uConsole into a connected device. Sign in with GitHub, link your backup repo, and get:

- **Live device status** pushed every 5 minutes from the device itself
- **Backup health monitoring** across 9 system categories
- **Full system inventory** — packages, extensions, scripts, configs

```
┌─────────────────────────────────────────────────────────────┐
│                    uconsole.cloud                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Battery: 100%│  │ CPU: 34.0°C  │  │ WiFi: Big Parma   │  │
│  │ Charging     │  │ Load: 0.18   │  │ Signal: -57 dBm   │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Mem: 1.5/3.8G│  │ Disk: 45%    │  │ SDR: RTL2838      │  │
│  │              │  │ 13G / 29G    │  │ LoRa: SX1262      │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
│                                                             │
│  ┌──── Backup Coverage ────────────────────────────────┐   │
│  │  Shell configs   ● today    │  Desktop      ● 6d    │   │
│  │  System configs  ● today    │  Git/SSH      ● today │   │
│  │  Packages (287)  ● today    │  GitHub CLI   ● today │   │
│  │  Browser (12)    ● today    │  Scripts      ● today │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──── Backup History (30d sparkline) ─────────────────┐   │
│  │  ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▃█                   │   │
│  │  23 backups · 62 files · latest Mar 15              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Packages │ Extensions │ Scripts │ Repo Structure           │
└─────────────────────────────────────────────────────────────┘
```

## How it works

```
uConsole (Debian, aarch64)            Cloud (Vercel)
┌──────────────────────┐          ┌──────────────────────┐
│                      │          │                      │
│  push-status.sh ─────────────→ │  Upstash Redis       │
│  (cron, every 5min)  │  POST   │  (device:repo:status)│
│                      │         │         │             │
│  backup.sh ──────────────────→ │         ▼             │
│  (git push)          │  git    │  GET /api/device/     │
│                      │         │  GET /api/github/     │
└──────────────────────┘         │         │             │
                                 │         ▼             │
  Browser (you)                  │  Next.js 16 SSR       │
  ┌────────────┐                 │  ┌────────────────┐   │
  │            │ ◄───────────────│  │ Server         │   │
  │ uconsole   │    HTML stream  │  │ Components     │   │
  │ .cloud     │                 │  └────────────────┘   │
  └────────────┘                 └──────────────────────┘
```

**Device → Redis → Dashboard.** No intermediary servers, no polling. The device pushes; the dashboard reads.

## Data collected

The `push-status.sh` script collects from sysfs and procfs every 5 minutes:

| Category | Source | Metrics |
|----------|--------|---------|
| Battery | `/sys/class/power_supply/axp20x-battery/` | capacity, voltage, current, status, health |
| CPU | `/sys/class/thermal/`, `/proc/loadavg` | temperature, load average (1/5/15), core count |
| Memory | `/proc/meminfo` | total, used, available |
| Disk | `df` | total, used, available, percent |
| WiFi | `iwconfig wlan0` | SSID, signal dBm, quality, bitrate, IP |
| Screen | `/sys/class/backlight/` | brightness, max brightness |
| AIO Board | `lsusb`, `/dev/spidev4.0`, `/dev/ttyS0`, `i2cdetect` | SDR (RTL2838), LoRa (SX1262), GPS fix, RTC sync |
| System | `hostname`, `uname`, `/proc/uptime` | hostname, kernel, uptime |

## Device setup

On your uConsole:

```bash
# 1. Get the script
mkdir -p ~/scripts
# (copy push-status.sh from this repo, or SCP from your workstation)

# 2. Configure credentials
mkdir -p ~/.config/uconsole
nano ~/.config/uconsole/status.env
# UPSTASH_REST_URL=https://your-redis.upstash.io
# UPSTASH_REST_TOKEN=your-token
# DEVICE_REPO=youruser/uconsole

# 3. Test it
bash ~/scripts/push-status.sh

# 4. Automate (every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * /bin/bash $HOME/scripts/push-status.sh >> $HOME/.config/uconsole/push-status.log 2>&1") | crontab -
```

## Project structure

```
uconsole-dashboard/
├── frontend/                    Next.js 16 app
│   ├── src/
│   │   ├── app/                 Pages, API routes, server actions
│   │   │   ├── actions.ts       Sign in, sign out, unlink (server actions)
│   │   │   ├── error.tsx        Error boundary
│   │   │   ├── page.tsx         Main dashboard page
│   │   │   └── api/
│   │   │       ├── auth/        NextAuth handlers
│   │   │       ├── device/      Device status endpoint
│   │   │       ├── github/      GitHub API proxy (commits, repos)
│   │   │       ├── raw/         Raw file proxy
│   │   │       └── settings/    User settings CRUD
│   │   ├── components/
│   │   │   ├── dashboard/       8 dashboard sections
│   │   │   ├── viz/             Charts (Sparkline, Donut, Treemap, StatusGrid)
│   │   │   └── ui/             Primitives (Spinner, ConfirmButton)
│   │   ├── lib/
│   │   │   ├── auth.ts          NextAuth v5 config
│   │   │   ├── github.ts        GitHub API client
│   │   │   ├── redis.ts         Upstash Redis client
│   │   │   ├── deviceStatus.ts  Device status reader
│   │   │   ├── utils.ts         Shared utilities
│   │   │   └── types.ts         Domain types
│   │   ├── middleware.ts        Auth guard (all /api/* routes)
│   │   └── __tests__/           106 tests (vitest)
│   ├── next.config.ts           Security headers, image config
│   └── vitest.config.ts
├── studio/                      Sanity CMS
└── package.json                 npm workspace root
```

## Security

This codebase has been through three rounds of security audit. Hardening includes:

| Protection | Implementation |
|------------|----------------|
| Auth | NextAuth v5 + GitHub OAuth, middleware-enforced on all API routes |
| Input validation | Path traversal blocks, SHA format regex, strict repo format regex |
| Headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy |
| Error handling | GitHubError class (401/403 surfaced), production error boundary hides internals |
| Data isolation | Redis keys scoped by user ID, device keys scoped by repo name |
| Session | 90-day TTL with rolling refresh, optional accessToken typed correctly |
| Rate limits | GitHub API errors surfaced, pagination capped at 1000 repos |

## Tech stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Framework | Next.js 16 | App Router, Server Components, Server Actions |
| Auth | NextAuth v5 | GitHub OAuth with JWT strategy |
| Device data | Upstash Redis | Device status (15-min TTL per push) |
| Backup data | GitHub REST API | Commits, tree, raw files |
| CMS | Sanity v3 | Dashboard copy, landing page content |
| Styling | Tailwind CSS v4 | GitHub-dark theme with CSS variables |
| Testing | Vitest | 106 tests — parsing, security, API, validation |
| Hosting | Vercel | Auto-deploy from main, preview on PRs |

## Local development

```bash
git clone https://github.com/mikevitelli/uconsole-dashboard.git
cd uconsole-dashboard
npm install

# Configure (see .env.example or Vercel dashboard)
cp frontend/.env.example frontend/.env.local
# Fill in: GITHUB_ID, GITHUB_SECRET, AUTH_SECRET, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN

npm run dev        # frontend :3000, studio :3333
npm test           # 106 tests
npm run build      # production build
```

## Environments

| Environment | Domain | Trigger |
|-------------|--------|---------|
| Production | [`uconsole.cloud`](https://uconsole.cloud) | Push to `main` |
| Preview | `*.vercel.app` | PRs & branches |
| Local | `localhost:3000` | `npm run dev` |

---

<div align="center">

Built for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole).

`49 source files · 106 tests · 7 API routes · 21 components`

</div>
