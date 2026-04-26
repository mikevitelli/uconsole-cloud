<div align="center">

<br/>

<img width="1280" height="640" alt="uconsole-cloud-open-graph-template" src="https://github.com/user-attachments/assets/aa03a58e-078d-4f02-b32f-d5d9b2c3c96e" />

<br/>

**Remote monitoring and management for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole).**

[![Live](https://img.shields.io/badge/live-uconsole.cloud-58a6ff?style=for-the-badge)](https://uconsole.cloud)

[![GitHub Release](https://img.shields.io/github/v/release/mikevitelli/uconsole-cloud?style=flat-square&color=58a6ff)](https://github.com/mikevitelli/uconsole-cloud/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/mikevitelli/uconsole-cloud/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/mikevitelli/uconsole-cloud/actions)
[![License](https://img.shields.io/github/license/mikevitelli/uconsole-cloud?style=flat-square&color=yellow)](LICENSE)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-v4-06b6d4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-black?style=flat-square&logo=vercel)](https://vercel.com)

</div>

---

## What is this?

A three-tier platform for managing the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole) — an RPi CM4 handheld Linux terminal running Debian Bookworm.

- **Device** — a `.deb` installs a curses TUI (9 categories, 53 native tools — FM radio, global ADS-B map, Marauder, Telegram, Watch Dogs Go, ROM launcher, and more), a Flask web dashboard, 46 management scripts, and systemd services.
- **Local network** — the webdash serves at `https://uconsole.local` via nginx + self-signed TLS + mDNS. No known WiFi? The device spins up a fallback AP (`uConsole`) so your phone or laptop can always reach it.
- **Cloud** — [uconsole.cloud](https://uconsole.cloud) is a Next.js app that shows live device telemetry, backup coverage, system inventory, and hardware info from anywhere. Fully optional — everything works offline.

Hardware-optional features (RTL-SDR, LoRa, GPS, RTC, ESP32) gracefully degrade when the [HackerGadgets AIO expansion](https://www.hackergadgets.com/) isn't installed.

---

## Screenshots

<div align="center">

<table>
<tr>
<td align="center" width="50%">

**Landing Page**

<img width="1239" height="872" alt="image" src="https://github.com/user-attachments/assets/e55515bd-d603-4675-950b-6d2afccaee56" />

*Sign in, install, link your device*

</td>
<td align="center" width="50%">

**Repo Linking**

<img width="1239" height="872" alt="image" src="https://github.com/user-attachments/assets/b02570ac-a365-4850-a8f7-63a27ac786df" />

*Auto-detects your uconsole backup repo*

</td>
</tr>
<tr>
<td align="center">

**Dashboard Overview**

<img width="1239" height="872" alt="image" src="https://github.com/user-attachments/assets/4dbcdb42-d82b-42c6-9d83-2d4020b7a394" />

*Backup coverage across 9 categories, repo stats*

</td>
<td align="center">

**Device Status**

<img width="1239" height="872" alt="image" src="https://github.com/user-attachments/assets/cfc6c6bc-8014-4594-866c-91f658991ed8" />

*Battery donut, CPU temp, memory, disk, WiFi, uptime, kernel*

</td>
</tr>
</table>

</div>

---

## Install

```bash
curl -s https://uconsole.cloud/install | sudo bash
uconsole setup
```

The bootstrap adds the GPG-signed APT repo and installs the `uconsole-cloud` package. `uconsole setup` walks through hardware detection, passwords, SSL certs, and optional cloud linking. `sudo apt upgrade` handles future updates.

---

## TUI (`console`)

```
SYSTEM   MONITOR   FILES   POWER   NETWORK   HARDWARE   TOOLS   GAMES   CONFIG
```

Curses launcher with gamepad + keyboard input, 9 categories, 50+ native tools, plus direct-run shell scripts. Highlights:

- **MONITOR** — 1-second live gauges for CPU, memory, disk, temperature, battery, network
- **HARDWARE** — GPS globe, FM radio, global ADS-B map with hi-res basemap fetch, ESP32 hub (Marauder, MicroPython, MimiClaw, Bruce flashing), Meshtastic mesh map
- **TOOLS** — git panel, notes, calculator, stopwatch, Telegram client, weather, Hacker News, uConsole forum
- **GAMES** — Watch Dogs Go (auto-installs on first launch), minesweeper, snake, tetris, 2048, ROM launcher
- **CONFIG** — theme picker, view mode, keybinds, push interval, Watch Dogs config

External programs (emulators, Watch Dogs Go) launch through a shared `tui.launcher` helper so a child crash can't signal the curses parent.

---

## uconsole CLI

```
uconsole setup       Interactive setup wizard
uconsole link        Link device to uconsole.cloud (code auth + QR)
uconsole push        Push status to cloud now
uconsole status      Show config, timer status, last push time
uconsole doctor      Diagnose services, SSL, nginx, connectivity
uconsole restore     Run restore.sh from backup repo
uconsole unlink      Remove cloud config and stop timer
uconsole update      Update via APT
uconsole logs [svc]  Tail systemd logs (default: webdash)
uconsole version
uconsole help
```

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Framework | Next.js 16 (App Router, Server Components, Server Actions) |
| Auth | NextAuth v5 (GitHub OAuth, JWT) |
| Data | Upstash Redis (device telemetry, device codes) |
| Backup data | GitHub REST API |
| CMS | Sanity v3 |
| Styling | Tailwind CSS v4 |
| Testing | Vitest 4 (frontend, 117 tests) + pytest (device, 1000+ tests) |
| Hosting | Vercel |
| CI/CD | GitHub Actions (.deb build, APT publish) |
| Device | Bash + Python, Flask webdash, curses TUI, systemd |
| Packaging | dpkg + APT (arm64, GPG-signed repo on Vercel CDN) |

---

## Security

| Protection | Implementation |
|------------|----------------|
| Auth | NextAuth v5 + GitHub OAuth, middleware-enforced on all API routes |
| Device auth | Bearer tokens (90-day UUIDs), rate-limited code generation (5/min/IP) |
| Input validation | Path traversal blocks, SHA regex, strict repo format validation |
| Headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy |
| Data isolation | Redis keys scoped by repo, device tokens scoped by user |
| Local TLS | Self-signed cert at `/etc/uconsole/ssl/` (generated at install) |
| Secrets | `status.env` is chmod 600, owned by device user |
| APT repo | GPG-signed `Release` files, key distributed via HTTPS |

Vulnerability disclosure: see [SECURITY.md](SECURITY.md).

---

## Local development

```bash
git clone https://github.com/mikevitelli/uconsole-cloud.git
cd uconsole-cloud
npm install

cp frontend/.env.example frontend/.env.local   # GITHUB_ID, AUTH_SECRET, UPSTASH_*

npm run dev            # frontend :3000, studio :3333
make test              # pytest + frontend + lint
make test-install      # .deb install verification in arm64 Docker
```

Branching: `dev` for active work (PRs target this), `main` for released state. `/publish` cuts a release.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor flow and testing layers.

---

## Documentation

- [Architecture and project layout](docs/ARCHITECTURE.md) — data flow diagrams, repo structure
- [API and telemetry](docs/API.md) — device payload schema, cloud routes
- [Self-hosting](docs/SELF-HOSTING.md) — run your own dashboard
- [Device linking](docs/DEVICE-LINKING.md) — auth flow detail
- [Release pipeline](docs/PIPELINE.md) — edit → /publish → end-user
- [Features overview](docs/FEATURES.md)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — especially from uConsole owners who can test device-side changes on real hardware.

---

<div align="center">

Built for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole).

</div>
