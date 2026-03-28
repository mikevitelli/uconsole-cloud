# uConsole Ecosystem

Bird's-eye view of all components, how they connect, and the data flowing between them.

## System Diagram

```
                           INTERNET
    ┌──────────────────────────────────────────────────────┐
    │                                                      │
    │   uconsole.cloud (Vercel/Next.js)                    │
    │   ┌────────────────────────────────────────────┐     │
    │   │  Remote Monitoring Dashboard               │     │
    │   │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │     │
    │   │  │ Device   │  │ Telemetry│  │ "Local   │ │     │
    │   │  │ Linking  │  │ Display  │  │ Shell    │ │     │
    │   │  │ /link    │  │ /dash    │  │  Hub"    │ │     │
    │   │  └────┬─────┘  └────┬─────┘  └────┬─────┘ │     │
    │   │       │              │              │       │     │
    │   │  ┌────┴──────────────┴──────────────┴────┐ │     │
    │   │  │  /api/device/push  (POST)             │ │     │
    │   │  │  Auth: Bearer <DEVICE_TOKEN>          │ │     │
    │   │  └────────────────┬──────────────────────┘ │     │
    │   │                   │                        │     │
    │   │  ┌────────────────▼──────────────────────┐ │     │
    │   │  │  Upstash Redis (telemetry store)      │ │     │
    │   │  └───────────────────────────────────────┘ │     │
    │   └────────────────────────────────────────────┘     │
    │                                                      │
    │   GitHub (<your-github-user>/uconsole)                       │
    │   ┌────────────────────────────────────────────┐     │
    │   │  Private repo — backup snapshots           │     │
    │   └────────────────────────────────────────────┘     │
    │                                                      │
    └──────────────────────────────────────────────────────┘
                        ▲           │
                        │           │ "Local Shell Hub"
          push-status   │           │ links user back to
          POST every    │           │ https://uconsole.local
          ~5min         │           │ (browser must be on
                        │           │  same LAN)
                        │           ▼
    ┌──────────────────────────────────────────────────────┐
    │                    LOCAL NETWORK                      │
    │                                                      │
    │  ┌───────────────────────────────────────────────┐   │
    │  │  uConsole Device  (Debian Bookworm / CM4)     │   │
    │  │                                               │   │
    │  │  ┌─────────────────────────────────────────┐  │   │
    │  │  │  nginx (port 443, HTTPS)                │  │   │
    │  │  │  Self-signed SSL: uconsole.crt/key      │  │   │
    │  │  │  SANs: uconsole.local, <device-ip>,    │  │   │
    │  │  │        127.0.0.1                        │  │   │
    │  │  │  Valid: 2026-03-22 → 2036-03-19         │  │   │
    │  │  └──────────────┬──────────────────────────┘  │   │
    │  │                 │ proxy_pass                   │   │
    │  │                 ▼                              │   │
    │  │  ┌─────────────────────────────────────────┐  │   │
    │  │  │  webdash.py  (Flask, port 8080)         │  │   │
    │  │  │                                         │  │   │
    │  │  │  Auth: username/password → HMAC token   │  │   │
    │  │  │                                         │  │   │
    │  │  │  Authenticated endpoints:               │  │   │
    │  │  │    /api/stats         system metrics     │  │   │
    │  │  │    /api/run/<script>  execute scripts    │  │   │
    │  │  │    /api/stream/<s>    SSE script output  │  │   │
    │  │  │    /api/wifi/*        wifi management    │  │   │
    │  │  │    /api/services      systemd control    │  │   │
    │  │  │    /api/wiki/<slug>   documentation      │  │   │
    │  │  │    /api/timers        schedule mgmt      │  │   │
    │  │  │    /terminal (ws)     xterm.js PTY       │  │   │
    │  │  │                                         │  │   │
    │  │  │  Public endpoints (no auth):            │  │   │
    │  │  │    /api/public/stats  local-only metrics │  │   │
    │  │  │    /uconsole.crt      cert download      │  │   │
    │  │  └──────────────┬──────────────────────────┘  │   │
    │  │                 │                              │   │
    │  │                 │ consumed by                  │   │
    │  │                 ▼                              │   │
    │  │  ┌─────────────────────────────────────────┐  │   │
    │  │  │  push-status.sh  (systemd timer)        │  │   │
    │  │  │                                         │  │   │
    │  │  │  1. Reads sensors/sysfs directly        │  │   │
    │  │  │  2. Checks webdash.service status       │  │   │
    │  │  │  3. POSTs JSON to uconsole.cloud API    │  │   │
    │  │  │  4. Auth: Bearer token from status.env  │  │   │
    │  │  └─────────────────────────────────────────┘  │   │
    │  │                                               │   │
    │  │  ┌─────────────────────────────────────────┐  │   │
    │  │  │  Other systemd services                 │  │   │
    │  │  │    uconsole-backup  (daily 3am → git)   │  │   │
    │  │  │    uconsole-update  (weekly Sun 4am)    │  │   │
    │  │  └─────────────────────────────────────────┘  │   │
    │  └───────────────────────────────────────────────┘   │
    │                                                      │
    │  ┌───────────────────────────────────────────────┐   │
    │  │  User's Phone / Laptop (browser)              │   │
    │  │    → https://uconsole.local (webdash)         │   │
    │  │    → https://uconsole.cloud (remote dash)     │   │
    │  └───────────────────────────────────────────────┘   │
    │                                                      │
    └──────────────────────────────────────────────────────┘
```

## Data Flows

### 1. Device Registration (one-time)

```
uConsole                         uconsole.cloud
   │                                  │
   │  $ uconsole setup                │
   │  generates device code ────────► │
   │                                  │
   │         user visits /link,       │
   │         enters device code       │
   │                                  │
   │  ◄──── issues DEVICE_TOKEN ───── │
   │                                  │
   │  writes ~/.config/uconsole/      │
   │         status.env (chmod 600)   │
   │    DEVICE_API_URL=https://...    │
   │    DEVICE_TOKEN=<uuid>           │
   │    DEVICE_REPO=<your-github-user>/...   │
```

### 2. Telemetry Push (every ~5 min)

```
push-status.sh                   uconsole.cloud
   │                                  │
   │  POST /api/device/push          │
   │  Authorization: Bearer <token>   │
   │  Content-Type: application/json  │
   │                                  │
   │  {                               │
   │    hostname, uptime, kernel,     │
   │    battery: {cap, V, mA, ...},   │
   │    cpu: {tempC, loadAvg, cores}, │
   │    memory: {total, used, avail}, │
   │    disk: {total, used, avail, %},│
   │    wifi: {ssid, dBm, quality,    │
   │           bitrate, ip},          │
   │    aio: {sdr, lora, gps, rtc},  │
   │    screen: {brightness, max},    │
   │    webdash: {running, port},     │  ──► stored in
   │    wifiFallback: {enabled, ap},  │      Upstash Redis
   │    collectedAt: "ISO-8601"       │
   │  }                               │
   │                                  │
   │  ◄──── HTTP 200 (ok)            │
   │  ◄──── HTTP 401 (bad token)     │
```

### 3. Local Webdash Access (LAN only)

```
Browser                  nginx (443)          webdash.py (8080)
   │                        │                       │
   │  GET https://          │                       │
   │  uconsole.local ──────►│                       │
   │                        │  proxy_pass ─────────►│
   │                        │                       │
   │  ◄── login page ──────│◄──────────────────────│
   │                        │                       │
   │  POST /api/login       │                       │
   │  {user, pass} ────────►│──────────────────────►│
   │                        │                       │
   │  ◄── Set-Cookie: ─────│◄── HMAC-SHA256 token ─│
   │      session=<hmac>    │    (30-day expiry)    │
   │                        │                       │
   │  GET /api/stats        │                       │
   │  Cookie: session ─────►│──────────────────────►│
   │  ◄── JSON metrics ────│◄──────────────────────│
```

### 4. Cloud → Local Bridge ("Local Shell Hub")

```
uconsole.cloud dashboard           User's Browser
   │                                    │
   │  telemetry shows                   │
   │  webdash.running = true            │
   │                                    │
   │  renders "Local Shell Hub" ───────►│
   │  link to https://uconsole.local    │
   │                                    │
   │  (user must be on same LAN         │
   │   as the uConsole device)          │
   │                                    │
   │                              opens webdash
   │                              in new tab
```

There is no tunnel, VPN, or relay. The cloud dashboard simply provides a convenience link back to the device's local HTTPS address. The user must be on the same network as the uConsole for the link to work.

### 5. Backup to GitHub (daily)

```
uConsole                             GitHub
   │                                    │
   │  uconsole-backup.timer (3am)       │
   │  → commits changed configs        │
   │  → git push origin main ─────────►│
   │                                    │
   │  (repo: <your-github-user>/uconsole,      │
   │   private)                         │
```

## SSL Certificate

| Field | Value |
|-------|-------|
| Type | Self-signed (CA=YES) |
| Subject | `CN=uconsole, O=uConsole, C=US` |
| SANs | `uconsole`, `uconsole.local`, `<device-ip>`, `127.0.0.1` |
| Valid from | 2026-03-22 |
| Valid until | 2036-03-19 |
| Key | RSA 2048-bit |
| Signature | SHA-256 |
| Cert file | `/etc/ssl/certs/uconsole.crt` (backup: `system/ssl/uconsole.crt`) |
| Key file | `/etc/ssl/private/uconsole.key` (backup: `system/ssl/uconsole.key`, gitignored) |
| Download | `https://uconsole.local/uconsole.crt` (public endpoint, no auth) |

Browser warnings are expected — the cert is self-signed, not expired. Trust it on your devices:
- **iPhone/iPad**: Download cert → Settings → Profile → Install → General → About → Certificate Trust Settings → enable
- **Mac**: Download cert → Keychain Access → import → double-click → Trust → Always Trust

## Component Summary

| Component | Location | Role |
|-----------|----------|------|
| **webdash.py** | `scripts/webdash.py` | Local web dashboard (Flask) — 60+ scripts, terminal, wiki |
| **nginx** | `/etc/nginx/sites-available/webdash` | HTTPS reverse proxy (TLS termination) |
| **push-status.sh** | `scripts/push-status.sh` | Telemetry reporter to cloud API |
| **uconsole.cloud** | Separate repo (`uconsole-cloud`) | Remote monitoring dashboard (Vercel/Next.js) |
| **Upstash Redis** | Cloud-hosted | Telemetry data store |
| **status.env** | `~/.config/uconsole/status.env` | Device auth token + API URL |
| **uconsole CLI** | External package | Device registration (`uconsole setup`) |
| **uconsole-backup** | systemd timer | Daily git backup to GitHub |
| **uconsole-update** | systemd timer | Weekly system update |
