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
- [ ] avahi-daemon config in installer/restore (mDNS for uconsole.local)
- [ ] `/etc/avahi/services/webdash.service` for service advertisement
- [ ] Push on reconnect (immediate push when wifi-fallback tears down AP)
- [ ] `uconsole doctor` command (check timer, webdash, push, connectivity)
- [ ] CLI: switch cron → systemd timer in setup
- [ ] `uconsole restore` command (detect ~/uconsole, run restore.sh --yes)
- [ ] restore.sh step [10/10]: cloud connection guidance
- [ ] Add avahi-daemon to package manifest

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

## Phase 4: System Packaging (.deb)

- [ ] .deb package structure (debian/, postinst, prerm)
- [ ] Installs: uconsole CLI, push-status.sh, systemd services, avahi config
- [ ] Post-install: enables services, prompts for setup
- [ ] Host apt repo (GitHub Releases or Cloudsmith)
- [ ] `uconsole update` uses apt
- [ ] Package signing (GPG)

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
- [ ] webdash: password hashing (replace plaintext comparison)
- [ ] webdash: cryptographic session tokens (replace deterministic)
- [ ] webdash: server-side session invalidation
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
- [ ] Add nginx config to backup repo (currently not tracked)
- [ ] Include in restore.sh or installer

### Testing
- [ ] E2E tests for device code flow on staging
- [ ] Integration tests for push → Redis → dashboard read
- [ ] Test wifi-fallback flow on physical device

---

## Dependencies Between Phases

```
Phase 1 (MVP Polish) ─── no dependencies, ship now
    ↓
Phase 2 (Local Network) ─── depends on Phase 1 webdash telemetry
    ↓
Phase 3 (Terminal Auth) ─── depends on Phase 2 mDNS (nice to have, not required)
    ↓
Phase 4 (.deb) ─── depends on Phase 2 (avahi config) + Phase 3 (CLI finalized)
    ↓
Phase 5 (Polish) ─── independent, can start anytime after Phase 1
```
