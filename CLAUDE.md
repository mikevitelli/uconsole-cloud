# uconsole-cloud

Remote monitoring dashboard for ClockworkPi uConsole devices. Deployed at https://uconsole.cloud.

## Stack

- **Framework:** Next.js 16 (App Router, Server Components)
- **Auth:** NextAuth v5 beta + GitHub OAuth (scopes: repo, read:user)
- **Storage:** Upstash Redis (REST client, @upstash/redis)
- **CMS:** Sanity (landing page content)
- **Deploy:** Vercel (project: digital-counsel/uconsole-dashboard)
- **Testing:** Vitest (138 tests)

## Architecture

```
Phone (Safari PWA)
  → uconsole.cloud (Vercel, HTTPS)
    → Upstash Redis (device telemetry, persistent — no TTL)
    → GitHub API (backup repo: commits, packages, tree)

uConsole (every 5 min)
  → push-status.sh (systemd timer)
    → POST /api/device/push (Bearer token)
      → Redis: device:{repo}:status (overwritten each push, persists indefinitely)
```

## Key Directories

- `frontend/src/app/` — pages, API routes, manifest, layout
- `frontend/src/components/dashboard/` — 10 dashboard sections (DeviceStatus, BackupHistory, etc.)
- `frontend/src/components/viz/` — 7 visualization components (CalendarGrid, Donut, Sparkline, etc.)
- `frontend/src/lib/` — auth, redis, deviceCode, deviceToken, deviceStatus, github, rateLimit, utils
- `frontend/public/scripts/` — install-time copies of uconsole CLI and push-status.sh
- `packaging/` — .deb build system (build-deb.sh, DEBIAN files, systemd units, nginx, avahi)
- `studio/` — Sanity CMS workspace

## Branches

- `main` — production (auto-deploys to uconsole.cloud)
- `feat/device-code-auth` — active development branch (device auth, PWA, rate limiting, local hub link)
- `staging` — preview deployments
- `test/device-code-e2e` — e2e tests with dummy data (do NOT merge to main)
- `gif-animation` — merged, can be deleted

## Data Flow

- **Device → Cloud:** push-status.sh → POST /api/device/push (Bearer token) → Redis (persistent, no TTL)
- **Cloud → Browser:** Server Component reads Redis + GitHub API → renders dashboard (shows "offline" banner if data >15 min stale)
- **Setup:** uconsole setup → POST /api/device/code → user enters code at /link → device polls /api/device/poll/{secret} → gets token
- **Install:** curl -fsSL uconsole.cloud/install | bash → downloads CLI + push-status.sh

## Device Telemetry Payload

battery, cpu, memory, disk, wifi (including ip), aio board (sdr, lora, gps, rtc), screen, webdash (running, port), collectedAt

## Two Copies of push-status.sh

| Copy | Location | Purpose |
|------|----------|---------|
| Install copy | `frontend/public/scripts/push-status.sh` | Downloaded by curl installer for first-time setup |
| Canonical | `~/uconsole/scripts/push-status.sh` (device backup repo) | Used by systemd timer after restore |

Both must produce identical JSON schema. Edit canonical first, sync to install copy.

## Local Webdash Bridge

- webdash.py (Flask on 8080) is reverse-proxied through **nginx on HTTPS/443 with self-signed SSL**
- Dashboard shows "Local Shell Hub" link when `webdash.running && wifi.ip` in telemetry
- Link: `https://uconsole.local` (mDNS) with IP fallback
- WiFi fallback: device auto-creates AP "uConsole" when no known WiFi available — phone connects to AP to access webdash without internet

## API Routes

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/api/device/code` | POST | No | Generate device code (rate-limited 5/min/IP) |
| `/api/device/code/confirm` | POST | Yes | Confirm code, generate token |
| `/api/device/poll/[secret]` | GET | No | Poll for confirmation |
| `/api/device/push` | POST | Bearer | Accept device telemetry |
| `/api/device/status` | GET | Yes | Fetch cached status |
| `/api/github/*` | GET/POST | Yes | GitHub API proxy (repos, commits, create) |
| `/api/settings` | GET/POST/DELETE | Yes | User settings, repo linking |
| `/api/settings/regenerate-token` | POST | Yes | Regenerate device token |
| `/api/scripts/[name]` | GET | No | Serve allowlisted scripts |
| `/api/health` | GET | No | Redis health check |
| `/install` | GET | No | Bash installer script |

## Conventions

- Server Components by default, `'use client'` only for interactivity
- All request APIs are async (Next.js 16): `await cookies()`, `await headers()`
- Test with `npm run build && npm test` before pushing
- Push to staging for preview, merge to main for production
- Never commit .env files or tokens
- Device tokens are 90-day UUIDs, status.env is chmod 600

## Known Issues

- Vercel Deployment Protection blocks public device endpoints on preview URLs
- Preview OAuth needs separate GitHub app (uconsole-cloud-preview)
- fetchCommits limited to 50 (sufficient for now, bump when repo grows)

## Roadmap

- ~~Phase 2: mDNS/avahi, uconsole doctor, wifi-fallback telemetry~~ (done)
- ~~Phase 3: GitHub Device Flow (terminal-only auth + unified restore)~~ (done)
- ~~Phase 4: .deb packaging~~ (done — see `packaging/`)
- **Phase 5:** Client-side polling, alerts, device history, Tailscale
