# 06 Webdash Architecture

*Generated: 2026-04-09*

I now have a comprehensive understanding of the entire webdash architecture. Here is my analysis:

---

## Webdash Flask App -- Architecture Review and Improvement Recommendations

### File: `/home/mikevitelli/uconsole-cloud/device/webdash/app.py` (1553 lines)

The total webdash codebase is approximately 4000 lines across 4 files: `app.py` (1553), `dashboard.js` (1713), `dashboard_body.html` (532), `style.css` (556). The app itself is a self-contained system, not a 4300-line monolith, so it is more manageable than the question implied.

---

### 1. Architecture Review

**Current structure:**
- Single `app.py` with 46 route decorators, 27 subprocess calls, 6 global mutable state variables (`_pty_sessions`, `_active_sessions`, `_rate_buckets`, `_prev_cpu`, `_esp32_data`, `_gps_data`, `_sdr_data`, `_lora_data`)
- One JS file (1713 lines) handling all panels, visualization, formatting, polling
- Templates use Jinja2 with a base/body split
- Behind nginx (HTTPS/443) reverse proxy to localhost:8080
- Deployment: Flask dev server with `threaded=True`, or SocketIO with `async_mode='threading'`

**Assessment:** At 1553 lines, `app.py` is at the upper limit of a single-file Flask app, but not catastrophically so. The code is logically grouped (auth, system stats, script execution, sensor push endpoints, config endpoints, wiki CRUD, wifi management). The real concern is that it mixes several distinct responsibilities: authentication, hardware monitoring, script orchestration, sensor data ingestion, wiki CMS, wifi management, terminal emulation, and timer configuration.

**Recommended refactor -- Flask Blueprints:**

| Blueprint | Lines (est.) | Responsibility |
|-----------|-------------|----------------|
| `auth` | ~120 | Login, logout, password setup, session management |
| `system` | ~200 | `/api/stats`, `/api/processes`, `/api/logs`, `/api/connections`, `/api/services` |
| `scripts` | ~100 | `/api/run/<script>`, `/api/stream/<script>`, ALLOWED_SCRIPTS dict |
| `config` | ~200 | Brightness, timezone, port, git-remote, timers |
| `sensors` | ~150 | ESP32, GPS, SDR, LoRa push/read endpoints |
| `wiki` | ~60 | Wiki CRUD |
| `wifi` | ~80 | Scan, connect, disconnect |
| `battery_test` | ~60 | Battery test chart/start |
| `terminal` | ~80 | PTY SocketIO handlers |

Shared utilities (`read_sysfs`, `_script()`, `_systemctl()`, `ANSI_RE`, `get_stats()`) would go in a `utils.py`.

**Effort: Medium (2-3 days).** The refactor is mostly mechanical -- move functions to blueprint files, register them in `app.py`. Risk is low since routes and logic don't share much state except for the global sensor data dicts, which can be moved to a shared module.

---

### 2. Security Hardening

**What is already done well:**
- bcrypt password hashing (with fallback error if bcrypt not installed)
- Server-side session store with expiry (`_active_sessions` dict with 30-day TTL)
- HttpOnly, Secure, SameSite=Lax cookies
- Rate limiting on public endpoints (30 req/60s per IP)
- Local-only restriction on sensor push endpoints (`_is_local_ip` check)
- CSP header with `default-src 'self'`
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`
- Script execution uses an allowlist (`ALLOWED_SCRIPTS` dict), not user-supplied paths

**Gaps and recommendations:**

**(a) CSRF protection -- HIGH priority**
There is zero CSRF protection. All state-mutating POST endpoints (`/api/run/<script>`, `/api/config/*`, `/api/wifi/connect`, `/api/set-password`, `/api/wiki/<slug>`) rely solely on session cookies. A malicious page could trigger `power-reboot` or `power-shutdown` via a cross-origin POST.

**Fix:** Add Flask-WTF or a lightweight custom CSRF token. For the JSON API endpoints, the simplest approach is a custom header check (e.g., require `X-Requested-With: XMLHttpRequest` or a `X-CSRF-Token` header that matches a cookie value -- the "double-submit cookie" pattern). This works because CORS prevents cross-origin requests from setting custom headers.

**Effort: Small (half day).** Add a `@app.before_request` check that all POST/PUT/DELETE requests must include a custom header. Update all `fetch()` calls in `dashboard.js` to include it.

**(b) Session memory leak**
`_active_sessions` is an in-memory dict that is never cleaned up. Expired sessions accumulate until the process restarts. Over 30 days at typical usage, this is negligible, but it is unbounded.

**Fix:** Add a periodic cleanup in `_is_authenticated()` or a background thread that prunes expired tokens. **Effort: Small (1 hour).**

**(c) Rate limit memory leak**
`_rate_buckets` is never pruned. Each unique IP address creates an entry that persists forever.

**Fix:** Prune entries older than `_RATE_WINDOW` during `_check_rate_limit()`. **Effort: Small (30 min).**

**(d) Rate limiting on auth endpoints**
The login endpoint (`/login`) is in `_PUBLIC_PATHS` and exempt from rate limiting. A brute-force attack on the password is feasible.

**Fix:** Apply the rate limiter to `/login` POST specifically, with a tighter limit (e.g., 5 attempts per minute). **Effort: Small (1 hour).**

**(e) CSP should tighten `'unsafe-inline'`**
Both `script-src` and `style-src` allow `'unsafe-inline'`. Since the JS and CSS are in external files, the inline allowance weakens CSP considerably.

**Fix:** Move any remaining inline styles/scripts to external files, then add nonces or remove `'unsafe-inline'`. This is harder because of the inline event handlers (`onclick`) in `dashboard_body.html`. **Effort: Medium (1-2 days)** -- requires refactoring onclick handlers to `addEventListener` in JS.

**(f) `api_stream` is GET with no CSRF**
The SSE endpoint `/api/stream/<script>` uses GET, which means it can be triggered by an `<img>` tag or `EventSource` from any page. The script execution fires on a GET request, which is architecturally wrong (GET should be safe/idempotent).

**Fix:** Change to POST-initiated streaming (return a job ID, then poll/SSE for output), or at minimum add a token parameter. **Effort: Medium (1 day).**

**How comparable projects handle this:**
- **Home Assistant:** Token-based auth (long-lived access tokens + short-lived session tokens), CSRF via `X-HA-Access` header, rate limiting via auth provider.
- **Pi-hole admin:** Session-based with PHP `session_id`, CSRF token in forms, no API token auth (weakness).
- **Cockpit:** Uses PAM authentication, system-level sessions with polkit authorization, full CSP with nonces, CSRF via cockpit-specific origin checking.

---

### 3. Performance

**Current deployment model:**
- Flask dev server (`app.run(threaded=True)`) or Flask-SocketIO with `async_mode='threading'`
- `allow_unsafe_werkzeug=True` in production
- Behind nginx reverse proxy

**Bottlenecks identified:**

**(a) Subprocess calls on every request**
`get_stats()` calls `iwconfig` and `ip` via subprocess on every `/api/stats` poll (default: every 5 seconds from the dashboard). `api_public_stats()` is even heavier -- it calls `lsusb`, `hwclock`, `systemctl` in addition to `get_stats()`.

**Fix:** Cache `get_stats()` output with a 2-3 second TTL. WiFi info changes rarely. The `_prev_cpu` delta calculation already needs periodic sampling, so a caching decorator would naturally fit.

**Effort: Small (2 hours).** Use `functools.lru_cache` with a time-based wrapper, or a simple `_cache` dict with TTL.

**(b) Gzip compression on every response**
The `compress_response` after-request handler gzips every response > 500 bytes in Python. This is CPU-expensive on a CM4.

**Fix:** Let nginx handle gzip compression (`gzip on; gzip_types application/json text/html text/css application/javascript;`). Remove the Python gzip middleware entirely. nginx's gzip is implemented in C and is significantly faster.

**Effort: Small (30 min).** Add nginx gzip config, remove `compress_response`.

**(c) Flask dev server in production**
The `allow_unsafe_werkzeug=True` flag is a red flag. Werkzeug's threaded server is not designed for production. Under load (e.g., multiple SSE streams + WebSocket connections + API polls), it will block.

**Fix:** Switch to **gunicorn with gevent workers**: `gunicorn -w 2 -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker app:app`. This gives proper concurrency for both HTTP and WebSocket. On a CM4 (4 cores, 4GB or 8GB RAM), 2-4 workers is appropriate.

**Effort: Medium (half day).** Install gunicorn+gevent, update the systemd service file, test SocketIO compatibility.

**(d) SSE streaming blocks a thread**
Each `/api/stream/<script>` connection holds a thread for the entire duration of the script (up to 300 seconds). With Werkzeug's threaded server, this limits concurrency severely.

**Fix:** With gunicorn+gevent, this becomes a green thread and no longer blocks. Alternatively, use `subprocess.Popen` with non-blocking I/O and gevent-compatible polling.

**(e) WiFi scan has a hardcoded `time.sleep(2)`**
Line 1281: `import time; time.sleep(2)` -- this blocks the thread for 2 seconds on every WiFi scan request.

**Fix:** Make the scan async or at minimum document why the sleep is needed (nmcli rescan is async). With gevent, this becomes non-blocking naturally.

---

### 4. PWA Improvements

**Current PWA state:**
- `manifest.json` is dynamically generated (standalone display, black theme, one icon)
- Service worker (`/sw.js`) precaches favicon and manifest, network-first for API/auth, cache-first for static assets
- No push notifications, no offline mode, no background sync

**Recommendations:**

**(a) Offline dashboard shell**
Cache the main dashboard HTML, CSS, and JS in the service worker. When offline, show the last-known stats with a "connection lost" banner (the `setConnected(false)` path already exists).

**Effort: Small (half day).** Update `PRECACHE` in the service worker to include `/`, `/static/css/style.css`, `/static/js/dashboard.js`. Add an offline fallback that renders cached stats.

**(b) Push notifications for battery alerts**
Use the Web Push API to notify when battery drops below a threshold. This requires:
- A push subscription endpoint on the server
- VAPID keys for push authentication
- A background check that triggers push when battery < 10% or temperature > 80C

**Effort: Large (2-3 days).** Requires `pywebpush` on the server, subscription management, a monitoring loop. High value for mobile use cases.

**(c) Better manifest**
The current manifest has a single 180x180 icon. PWAs need multiple sizes (48, 72, 96, 128, 144, 192, 512) and a maskable icon for Android adaptive icons. Also missing: `description`, `categories`, `screenshots` (for install prompt), `shortcuts` (quick actions from home screen long-press).

**Effort: Small (2 hours).** Generate icon sizes from the existing favicon.png, add manifest fields.

**(d) Background sync for script results**
Use the Background Sync API to queue script executions when offline and run them when connectivity is restored.

**Effort: Medium (1 day).** Useful but niche -- the device is the server, so "offline" means the phone lost WiFi to the device, and queuing commands for later is risky.

**(e) App shortcuts**
Add `shortcuts` to `manifest.json` for quick access to common actions: Battery, WiFi Scan, Reboot.

**Effort: Small (30 min).** Just manifest entries pointing to anchor URLs or query params that auto-open panels.

---

### 5. API Design

**Current pattern:**
- 46 route decorators, mixing REST-like CRUD (`/api/wiki/<slug>` with GET/POST/DELETE) with RPC-style endpoints (`/api/run/<script>`, `/api/stream/<script>`)
- Script execution uses a flat allowlist of 80+ named scripts mapped to shell commands
- Sensor data uses push/pull pairs (`/api/esp32/push` POST, `/api/esp32` GET)

**Assessment:** The current design is actually quite reasonable for a local dashboard. The `ALLOWED_SCRIPTS` dict with the `/api/run/<name>` and `/api/stream/<name>` endpoints is a clean pattern -- it is a controlled RPC interface, not arbitrary command execution. Adding a new script is a one-line dict entry.

**However, it could be improved:**

**(a) Group scripts with metadata**
Instead of a flat dict, structure `ALLOWED_SCRIPTS` with categories, labels, and dangerous flags:

```python
ALLOWED_SCRIPTS = {
    'battery': {
        'cmd': _script('power', 'battery.sh'),
        'category': 'power',
        'label': 'Battery Snapshot',
        'dangerous': False,
        'stream': True,
    },
    'power-reboot': {
        'cmd': _script('power', 'power.sh', 'reboot'),
        'category': 'power',
        'label': 'Reboot',
        'dangerous': True,
        'stream': False,
    },
}
```

This enables: a `/api/scripts` endpoint that returns available scripts with metadata, client-side category rendering from server data, and server-side confirmation requirements for dangerous operations.

**Effort: Medium (1 day).** Refactor the dict, add a `/api/scripts` endpoint, update the client.

**(b) Versioned API prefix**
No versioning currently. If the API evolves, old clients break silently.

**Fix:** Prefix all API routes with `/api/v1/`. Keep `/api/stats` as a redirect for backward compatibility.

**Effort: Small (1-2 hours)** with blueprints (just set `url_prefix='/api/v1'`).

**(c) Sensor push endpoints are repetitive**
The four push/read endpoint pairs (ESP32, GPS, SDR, LoRa) are copy-pasted with identical logic. 

**Fix:** A generic sensor registry:
```python
_sensors = {}  # name -> {data, last_seen, ttl}

@app.route('/api/sensor/<name>/push', methods=['POST'])
def sensor_push(name): ...

@app.route('/api/sensor/<name>')
def sensor_read(name): ...
```

**Effort: Small (1 hour).** Eliminates 80 lines of duplicate code.

**(d) Pagination for logs/processes**
No pagination on `/api/logs/<source>` or `/api/processes`. Currently hardcoded to 80 lines and 15 processes.

**Fix:** Accept `?lines=N&offset=M` query params. **Effort: Small (30 min).**

---

### Summary -- Prioritized Roadmap

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 1 | CSRF protection (double-submit cookie) | Small | Critical security fix |
| 2 | Rate limit on `/login` POST | Small | Prevents brute-force |
| 3 | Move gzip to nginx | Small | Free CPU on CM4 |
| 4 | Cache `get_stats()` with TTL | Small | Reduces subprocess overhead |
| 5 | Fix `/api/stream` from GET to POST | Small | Security + correctness |
| 6 | Prune `_active_sessions` and `_rate_buckets` | Small | Memory leak fix |
| 7 | Offline PWA shell | Small | Better mobile UX |
| 8 | Better manifest (icons, shortcuts) | Small | Better install experience |
| 9 | Consolidate sensor endpoints | Small | Code quality |
| 10 | Switch to gunicorn+gevent | Medium | Production-grade concurrency |
| 11 | Blueprint refactor | Medium | Maintainability |
| 12 | Script metadata registry | Medium | API quality, enables dynamic UI |
| 13 | Remove `'unsafe-inline'` from CSP | Medium | Defense-in-depth |
| 14 | Push notifications for battery | Large | High-value mobile feature |