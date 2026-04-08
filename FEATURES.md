# Feature Map — uconsole ecosystem

## Legend
- [x] Done
- [ ] TODO
- [~] In progress (uncommitted)
- [D] Deferred (needs decision or device testing)

---

## Phase 1: MVP Polish ✅

### Cloud Dashboard (uconsole-cloud)
- [x] Device code auth flow (code generation, polling, confirmation)
- [x] Install script endpoint (`/install`)
- [x] CLI served via `/api/scripts/uconsole`
- [x] Landing page redesign (GIF hero, install command, sign in)
- [x] Auto-create backup repo from web UI
- [x] PWA manifest + Safari meta tags (standalone, dark, icons)
- [x] Rate limiting on /api/device/code (5/min/IP, Redis-based)
- [x] Webdash detection in telemetry (webdash.running, webdash.port)
- [x] Local Shell Hub link on dashboard (https://uconsole.local, IP fallback)
- [x] Calendar grid data fix (was showing only 30 days, now full year)
- [x] GitHub-style hover tooltips on calendar grid
- [x] GIF animation speed (8s → 1.2s per rotation)
- [x] Token file permissions (chmod 600 in CLI)
- [x] Documentation page at /docs (install, CLI, architecture, troubleshooting)
- [x] GitHub Actions release workflow (automated .deb builds + APT publishing)

### Device Scripts (uconsole backup repo)
- [x] push-status.sh: webdash detection added to telemetry payload
- [x] CLAUDE.md: comprehensive rewrite (Bookworm, security notes, architecture)

---

## Phase 2: Local Network & Discovery

### Cloud Dashboard
- [ ] WiFi fallback state in telemetry (`wifiFallback.enabled`, `wifiFallback.apName`)
- [ ] Smart offline messaging (infer AP mode when fallback enabled + gone silent)
- [ ] AP gateway IP in Local Shell Hub link (10.42.0.1 when in AP mode)
- [ ] Connection timeline (Redis sorted set of online/offline transitions)

### Device Scripts
- [x] avahi-daemon config in packaging (mDNS for uconsole.local)
- [x] `/etc/avahi/services/webdash.service` for service advertisement
- [ ] Push on reconnect (immediate push when wifi-fallback tears down AP)
- [x] `uconsole doctor` command (check timer, webdash, push, connectivity)
- [x] CLI: switch cron → systemd timer in setup
- [x] `uconsole restore` command (detect ~/uconsole, run restore.sh --yes)
- [ ] restore.sh step [10/10]: cloud connection guidance
- [x] Add avahi-daemon to package recommends
- [x] Webdash migrated to systemd service (from manual start)
- [x] Shared utility libraries (lib.sh, tui_lib.py)
- [x] Forum browser (ClockworkPi forum access from TUI)
- [x] Battery discharge test with configurable profiles
- [x] Marauder TUI integration (ESP32 serial interface)
- [x] Games category in TUI
- [x] Trackball scroll support in TUI

### UX Design Needed
- [ ] Offline/AP mode dashboard UX (what does the user see when device is in AP mode?)
- [ ] Local Shell Hub card design (prominence, positioning, information density)
- [ ] PWA behavior when switching between cloud and local (app-feel vs browser handoff)

---

## Phase 3: Terminal-Only Auth (Unified Setup)

### Cloud Dashboard
- [ ] API: accept GitHub Device Flow token registration
- [ ] API: return linked repo info on device registration

### Device Scripts
- [ ] `uconsole setup --github` (GitHub OAuth Device Flow, no second device needed)
- [ ] Direct GitHub auth → gets git access + registers with uconsole.cloud
- [ ] Detect backup repo from cloud settings
- [ ] Offer clone + restore in one flow
- [ ] Fallback: current device code flow via uconsole.cloud/link

### UX Design Needed
- [ ] Terminal setup flow (code display, waiting animation, success/failure states)
- [ ] Unified restore prompts (detect repo → offer restore → confirm)
- [ ] First-run experience (what happens after setup completes?)

---

## Phase 4: System Packaging (.deb) ✅

- [x] .deb package structure (packaging/, postinst, prerm, postrm)
- [x] Installs: uconsole CLI, push-status.sh, systemd services, avahi config
- [x] Post-install: config setup (services not auto-started, setup wizard handles that)
- [x] Host APT repo (GPG-signed, served from Vercel CDN at uconsole.cloud/apt/)
- [x] `uconsole update` uses apt
- [x] Package signing (GPG-signed Release files, key distributed via HTTPS)
- [x] `curl -s https://uconsole.cloud/install | sudo bash` bootstrap story
- [x] GitHub Actions release workflow (build .deb, publish to APT repo)
- [x] Makefile targets: build-deb, publish-apt, release, version bumps
- [x] device/ is the canonical source for self-contained builds

---

## Phase 5: Polish & Hardening

### Cloud Dashboard
- [ ] Client-side polling for live updates (useEffect + /api/device/status every 30-60s)
- [ ] Battery/temp alert thresholds (stored in Redis, shown on dashboard)
- [ ] Device history (last 24h of readings in Redis sorted set)
- [ ] Historical charts (battery over time, CPU temp trends)

### Device Scripts
- [ ] HMAC request signing on push payloads
- [ ] Token rotation (shorter TTL, auto-refresh on push)
- [x] webdash: password hashing (bcrypt, replaces plaintext comparison)
- [x] webdash: cryptographic session tokens (secrets.token_hex, replaces deterministic)
- [x] webdash: server-side session store with 30-day TTL
- [ ] console.py: confirmation before process kill
- [ ] Optional: Tailscale integration for HTTPS + remote webdash
- [ ] Optional: webdash basic auth for shared networks

---

## Cross-Cutting Concerns

### Repo Restructure (deferred)
- [D] Move .git from ~/uconsole/ to ~/ (eliminate symlinks)
- [D] Update restore.sh, systemd services, push-status.sh paths
- [D] This is incompatible with current symlink strategy — needs full design

### Nginx Config
- [x] nginx config included in packaging (packaging/nginx/uconsole-webdash)
- [x] Included in .deb install (sites-available, setup enables)

### Testing
- [ ] E2E tests for device code flow on staging
- [ ] Integration tests for push → Redis → dashboard read
- [ ] Test wifi-fallback flow on physical device

---

## Dependencies Between Phases

```
Phase 1 (MVP Polish) ✅ ─── shipped v0.1.0
    ↓
Phase 2 (Local Network) ─── device scripts mostly done, cloud UX remaining
    ↓
Phase 3 (Terminal Auth) ─── depends on Phase 2 mDNS (nice to have, not required)
    ↓
Phase 4 (.deb) ✅ ─── shipped v0.1.0, automated in v0.1.1
    ↓
Phase 5 (Polish) ─── security items partially done, cloud features remaining
```
