<div align="center">

<br/>

<img width="1280" height="640" alt="uconsole-cloud-open-graph-template" src="https://github.com/user-attachments/assets/aa03a58e-078d-4f02-b32f-d5d9b2c3c96e" />

<br/>

**A complete software stack for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole) — TUI, web dashboard, and optional cloud telemetry.**

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

The [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole) is a handheld Linux terminal built around a Raspberry Pi CM4 or CM5 — a tiny keyboard, a 5" widescreen panel, a battery, and an expansion bay. Out of the box it's a stock Debian Bookworm install with a few ClockworkPi-specific tweaks. This repo turns it into a daily driver.

**uconsole-cloud** is a three-tier stack:

- **Device** — a Debian `.deb` installs a curses TUI (`console`), a Flask web dashboard (`webdash`), an offline CLI AI agent (`uconsole-ai`), 50+ management scripts, and a handful of systemd units. Nothing leaves the device by default.
- **Local network** — webdash serves at `https://uconsole.local` via nginx, self-signed TLS, and mDNS. When no known WiFi is in range, the device spins up a fallback AP (`uConsole` / `clockwork`) so your phone or laptop can always reach it.
- **Cloud (optional)** — [uconsole.cloud](https://uconsole.cloud) is a Next.js dashboard that shows device telemetry, backup coverage, and hardware inventory from anywhere. Auth via GitHub OAuth, telemetry stored in Upstash Redis, opt-in per device.

Hardware-optional features (RTL-SDR, LoRa, GPS, RTC, ESP32, dual-radio AC1200 WiFi) gracefully degrade when the [HackerGadgets AIO board](https://www.hackergadgets.com/) isn't installed. Everything works on both **AIO v1** and **AIO v2**, on both **CM4** and **CM5**.

This is the public software half of a two-repo setup. The companion repo, `mikevitelli/uconsole` (private), captures the full installed device state — configs, dotfiles, WiFi profiles, SSH keys, package manifests — as a backup/restore reference.

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

The bootstrap adds the GPG-signed APT repo and installs the `uconsole-cloud` package. `uconsole setup` walks through hardware detection, passwords, SSL cert generation, and optional cloud linking. From there, `sudo apt upgrade` handles future updates like any other Debian package.

---

## TUI (`console`)

```
SYSTEM   MONITOR   FILES   POWER   NETWORK   HARDWARE   TOOLS   GAMES   CONFIG
```

A curses launcher with full gamepad + keyboard input, organized into 9 categories backed by 23 feature modules. Each module is import-isolated, so a broken module hides only its own menu entry — the rest of the TUI keeps working.

Highlights from across the categories:

- **MONITOR** — 1-second live gauges for CPU, memory, disk, temperature, battery, and network; hostname-aware header, configurable refresh rate
- **POWER** — battery health curves tuned for Samsung INR18650-35E cells, CPU frequency caps, PMU voltage floor, low-battery shutdown
- **NETWORK** — WiFi connect/scan/hotspot/iPhone-tether, WiFi Radio Mode picker (CM5 onboard / AC1200 / both), antenna array braille ribbon monitor for the MT7921 2x2 chains
- **HARDWARE** — AIO v2 rail dashboard (GPS / LoRa / SDR / USB power gating + telemetry), GPS globe, FM radio, global ADS-B map with hi-res basemap fetch (powered by readsb + viewadsb), Meshtastic mesh map (SX1262 LoRa, with the TCXO init fix that was missing upstream), ESP32 hub for Marauder / MicroPython / MimiClaw firmware flashing and chat
- **TOOLS** — git panel, notes, calculator, stopwatch, Telegram client (tdlib), weather, Hacker News, uConsole forum browser, offline AI agent shell (`uconsole-ai`)
- **GAMES** — Watch Dogs Go (auto-installs on first launch), minesweeper, snake, tetris, 2048, ROM launcher with crash-safe detached spawn
- **CONFIG** — theme picker, view mode, keybinds, cloud push interval, Watch Dogs config

External programs (emulators, Watch Dogs Go, terminal apps) launch through a shared `tui.launcher` helper, so a child crash can never signal the curses parent.

---

## Subsystem highlights

**Offline AI agent** — `uconsole-ai` is a stdlib-only Python CLI that talks to a local Ollama daemon (default model `qwen2.5:7b`). It has `run_bash`, `read_file`, `write_file`, and `list_dir` tools, with confirmation prompts on mutating commands. System prompt is built from `CLAUDE.md` so the model has the device's full context. Works fully offline.

**MimiClaw chat portal** — a TUI client for the MimiClaw ESP32 AI gadget. Serial-based IP auto-discovery (no static config), WebSocket chat on port 18789, markdown rendering, WiFi config panel that can copy credentials from the host uConsole or scan and enter manually.

**ESP32 Marauder + wardrive (beta)** — full Marauder control over serial: scan/select/attack workflow with live braille RSSI waveforms, GPS-tagged AP capture, OSM street overlay via Overpass API, MapLibre GL replay viewer in webdash.

**Meshtastic** — wrapper aligned to the canonical Meshtastic CLI, packet listener that filters into one-line summaries, full mesh-map visualization in the TUI. Ships with the SX1262 init fixes (TCXO control, image-rejection cal, DIO2-as-RF-switch) that AIO v1 boards need to actually transmit.

**ADS-B** — migrated from the legacy `dump1090-mutability` to the actively-maintained `readsb` + `viewadsb`. Global layered basemap with hi-res fetch, layer picker, home picker, antenna-location sync.

**Antenna Array monitor** — live braille ribbon for the AC1200 MT7921 2x2 chains. Per-chain RSSI on top/bottom traces with the band between them filled and colored by the A−B delta — flaky u.FL connectors show up as the ribbon fattening and going red.

**Battery + power hygiene** — battery-safety units (opt-in, default off), AC-gated apt upgrades, CPU frequency caps, PMU voltage floor tuning, low-battery shutdown thresholds calibrated for INR18650-35E cells.

**WiFi suite** — connect / scan / hotspot / iPhone-tether, plus `wifi-fallback.sh` (NetworkManager dispatcher that auto-creates the `uConsole` AP when no known network is around, tears it down when one appears) and the dual-radio mode picker for boards running both CM5 onboard WiFi and AC1200.

---

## `uconsole` CLI

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

Tab completion is installed under `/usr/share/bash-completion/completions/`.

---

## Hardware target

- **Compute:** ClockworkPi uConsole with RPi CM4 or CM5 (CM5 + AIO v2 + AC1200 verified)
- **OS:** Debian Bookworm, aarch64
- **Required:** nothing beyond stock — the package degrades cleanly without expansion hardware
- **Supported peripherals:**
  - HackerGadgets AIO v1 / v2 expansion (auto-detected)
  - SX1262 LoRa over SPI1 (Meshtastic + raw LoRa)
  - RTL-SDR USB dongles (ADS-B, FM radio)
  - GPS over UART (gpsd)
  - ESP32 / ESP32-S3 over USB serial (Marauder, MicroPython, MimiClaw)
  - MT7921-based AC1200 dual-band WiFi card
- **PCIe NVMe:** the project documents the `dtparam=pciex1_gen=2` derate required for the SN770M on the CM5 carrier — Gen 3 is unstable on the uConsole's PCIe routing.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend framework | Next.js 16 (App Router, Server Components, Server Actions) |
| Auth | NextAuth v5 (GitHub OAuth, JWT) |
| Data | Upstash Redis (device telemetry, device codes) |
| Backup data source | GitHub REST API |
| CMS | Sanity v3 |
| Styling | Tailwind CSS v4 |
| Testing | Vitest 4 (frontend) + pytest (device, ~1000 tests) |
| Hosting | Vercel |
| CI/CD | GitHub Actions (.deb build, APT publish, arm64 install test via QEMU) |
| Device | Bash + Python 3, Flask webdash, curses TUI, systemd user + system units |
| Packaging | dpkg + APT (arm64, GPG-signed `Release` files, repo hosted on Vercel CDN) |

---

## Security

| Protection | Implementation |
|------------|----------------|
| Cloud auth | NextAuth v5 + GitHub OAuth, middleware-enforced on all API routes |
| Device auth | Bearer tokens (90-day UUIDs), rate-limited code generation (5/min/IP) |
| Push endpoint | Rate-limited + size-capped + shape-checked at `/api/device/push` |
| Input validation | Path traversal blocks, SHA regex, strict repo format validation, device-pushed `wifi.ip` validated before href interpolation |
| Headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy |
| Data isolation | Redis keys scoped by repo, device tokens scoped by user |
| Local TLS | Self-signed cert at `/etc/uconsole/ssl/` (generated at install) |
| Local secrets | `status.env` is chmod 600, owned by the device user |
| APT repo | GPG-signed `Release` files, key distributed via HTTPS |
| Shell hardening | `eval`/`source` of config files replaced with typed parsers; safety-critical PMU scripts run under `set -euo pipefail` |
| CI | Third-party Actions pinned by SHA, workflow permissions locked down |

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

**Branching:** `dev` for active work (PRs target this), `main` for released state. Tagged releases are cut by merging `dev` → `main`, bumping `VERSION`, and running `make build-deb publish-apt`.

**Working on the device package without packaging:** edit in `device/lib/`. The `console` launcher auto-detects `~/uconsole-cloud/device/lib/` and runs straight from the source tree — no `make install` needed for day-to-day TUI work. To force the deployed `/opt/uconsole/` copy, use `console-pkg` or `UCONSOLE_PKG_ONLY=1 console`. To point at an arbitrary tree, `UCONSOLE_DEV_LIB=/path console`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor flow.

---

## Documentation

- [Architecture and project layout](docs/ARCHITECTURE.md) — data flow diagrams, repo structure
- [API and telemetry](docs/API.md) — device payload schema, cloud routes
- [Self-hosting](docs/SELF-HOSTING.md) — run your own dashboard
- [Device linking](docs/DEVICE-LINKING.md) — auth flow detail
- [Release pipeline](docs/PIPELINE.md) — edit → `/publish` → end-user
- [Features overview](docs/FEATURES.md)
- [Changelog](CHANGELOG.md)

---

## Related repos

- **[mikevitelli/uconsole](https://github.com/mikevitelli/uconsole)** (private) — full device backup: dotfiles, WiFi profiles, SSH keys, apt manifests, RetroPie layout, hardware driver snapshots. Captures the installed state of the device for restore.
- **HackerGadgets AIO** — expansion board this software supports ([hackergadgets.com](https://www.hackergadgets.com/))
- **ClockworkPi** — the upstream hardware ([clockworkpi.com](https://www.clockworkpi.com/))

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — especially from uConsole owners who can test device-side changes on real hardware.

## License

[MIT](LICENSE).

---

<div align="center">

Built for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole).

</div>
