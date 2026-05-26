# CLI & Webdash Security Review

*Generated: 2026-04-09*

Now I have all the information I need for a comprehensive security review. Here is my report.

---

## Security Code Review Report

### Scope
- `/home/mikevitelli/uconsole-cloud/frontend/public/scripts/uconsole` (CLI)
- `/home/mikevitelli/uconsole-cloud/device/webdash/app.py` (Flask webdash)
- `/home/mikevitelli/uconsole-cloud/device/bin/uconsole-setup` (setup wizard)
- `/home/mikevitelli/uconsole-cloud/device/bin/webdash` (launcher)

---

### CRITICAL

**C1. Password reset without authentication -- anyone on the network can hijack webdash**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 225-242, 289-294
- `/api/set-password` is in `_PUBLIC_PATHS` (line 290), so the `require_auth` middleware skips it entirely.
- The handler `api_set_password()` (line 226) does NOT check `_password_is_set()`. Unlike `/setup-password` (line 220 checks and redirects), the POST endpoint accepts a new password from anyone at any time.
- **Impact:** Any unauthenticated user on the LAN can POST to `/api/set-password` with a new password, overwriting the existing hash in `config.json`, and receive a valid session cookie. This gives full webdash access including shell execution via the PTY terminal, script execution, WiFi control, and power management (reboot/shutdown).
- **Fix:** Add `if _password_is_set(): return redirect('/login')` at the top of `api_set_password()`, identical to the guard on `setup_password_page()`.

**C2. eval-based variable assignment in uconsole-setup is injectable**
- **File:** `/home/mikevitelli/uconsole-cloud/device/bin/uconsole-setup`, lines 64, 73
- The `ask()` helper uses `eval "$var=\"${input:-$default}\""`. If user input contains shell metacharacters (e.g., a SSID like `foo"; rm -rf /; echo "`), `eval` will execute it.
- In the setup wizard this is used for CPU frequency, shutdown voltage, hotspot SSID, backup schedule, and backup time inputs.
- **Impact:** Local privilege escalation. While the attacker needs interactive terminal access (limiting the blast radius), the code runs with the user's privileges and calls `sudo` for some operations.
- **Fix:** Replace `eval "$var=..."` with `printf -v "$var" '%s' "${input:-$default}"` which is assignment-only, no execution.

**C3. eval on untrusted env file content in the CLI**
- **File:** `/home/mikevitelli/uconsole-cloud/frontend/public/scripts/uconsole`, line 134
- `eval "$(maybe_sudo cat "${ENV_FILE}" 2>/dev/null)"` reads `status.env` and evaluates it as shell code. If an attacker can write to `/etc/uconsole/status.env` (or `~/.config/uconsole/status.env` in standalone mode), arbitrary commands run as the invoking user.
- The file is chmod 600 (good), but in standalone mode it's user-writable, and any process running as the user can modify it.
- **Impact:** Arbitrary code execution when `uconsole link` or `uconsole status` is run. The `cmd_status` function also uses `source "${ENV_FILE}"` (line 320), which is equivalent.
- **Fix:** Parse the file with `grep`/`sed` to extract specific known variables rather than executing it wholesale. E.g., `DEVICE_TOKEN=$(grep '^DEVICE_TOKEN=' "$ENV_FILE" | cut -d'"' -f2)`.

---

### WARNING

**W1. In-memory sessions are lost on restart -- no persistence**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 171-176
- `_active_sessions` is an in-memory dict. When the app restarts (deployments, crashes, the `_watch_and_reload` auto-restart on line 1529-1541), all sessions are invalidated. Users get logged out on every code change or service restart.
- The `_watch_and_reload` function calls `os.execv()` (line 1539) which replaces the process, losing all session state.
- Not exploitable, but a reliability issue that incentivizes long session durations.

**W2. Session memory leak -- expired sessions are never purged**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 171-186
- Expired sessions are only cleaned when a request happens to use that specific token (line 183-184). Sessions that are abandoned (browser closed, cookie cleared) accumulate in `_active_sessions` forever until process restart.
- Over 30 days of heavy use this could grow, though the dict values are tiny.
- **Fix:** Add a periodic sweep, or check all expired entries on each auth call.

**W3. No brute-force protection on login**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 198-215
- `/login` is in `_PUBLIC_PATHS` but has no rate limiting. The rate limiter (lines 256-286) only applies to `_LOCAL_ONLY_PATHS`. An attacker can attempt unlimited password guesses. bcrypt mitigates speed somewhat, but a 4-character minimum password (line 229) is very weak.
- **Fix:** Apply rate limiting to `/login` POST requests. Consider increasing minimum password length to 8.

**W4. X-Real-IP header spoofing for local-only endpoints**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 310, 802
- Local-only paths check `request.headers.get('X-Real-IP', request.remote_addr)`. When accessed through nginx, this is fine because nginx sets the header from `$remote_addr`. However, if a future configuration change binds Flask to `0.0.0.0`, or if another reverse proxy is placed in front, a remote attacker could send a crafted `X-Real-IP: 192.168.1.1` header to bypass the local-only restriction.
- Currently mitigated by Flask binding to `127.0.0.1` (line 1549).
- **Fix:** Use a proper trusted proxy mechanism (Flask's `ProxyFix` with explicit `x_for=1`) instead of raw header reading.

**W5. Non-atomic config file writes**
- **File:** `/home/mikevitelli/uconsole-cloud/frontend/public/scripts/uconsole`, lines 195-209
- `status.env` is written directly via `tee` or `cat >`. If the process is killed mid-write, the file is left truncated/corrupt. The CLI would then fail on next run, and the systemd timer would fail silently.
- Similarly in `app.py` line 143-145, `_save_user_conf()` writes directly to `config.json`.
- **Fix:** Write to a temp file and `mv` atomically: `tee "${ENV_FILE}.tmp" > /dev/null && mv "${ENV_FILE}.tmp" "${ENV_FILE}"`.

**W6. Self-update over HTTPS with no integrity verification**
- **File:** `/home/mikevitelli/uconsole-cloud/frontend/public/scripts/uconsole`, lines 392-396
- `cmd_update()` downloads scripts from `${BASE_URL}/api/scripts/` and immediately marks them executable. There is no checksum, signature, or pinned certificate verification. A MITM at the TLS layer (e.g., a corporate proxy or compromised CA) could inject malicious code.
- HTTPS provides baseline protection, but defense-in-depth would use signed checksums.
- **Fix:** Publish SHA-256 checksums alongside scripts and verify after download.

**W7. ini_set uses printf through sudo sh -c with unescaped values**
- **File:** `/home/mikevitelli/uconsole-cloud/device/bin/uconsole-setup`, line 106
- `sudo sh -c "printf '[%s]\n%s = %s\n' '$section' '$key' '$value' > '$file'"` embeds variables with single quotes inside a double-quoted string passed to `sh -c`. If `$value` contains a single quote, this breaks out of the quoting context.
- This is only hit when the config file doesn't exist and the default can't be copied (edge case), but it's a shell injection vector.
- **Fix:** Pass values as positional arguments to the inner shell: `sudo sh -c 'printf "[%s]\n%s = %s\n" "$1" "$2" "$3" > "$4"' _ "$section" "$key" "$value" "$file"`.

**W8. PTY sessions dict is not thread-safe**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 42, 83, 89, 104
- `_pty_sessions` is a plain dict accessed from multiple SocketIO event handlers and reader threads without locking. Concurrent connect/disconnect events could cause KeyError or race conditions.
- **Fix:** Use a `threading.Lock` to guard access to `_pty_sessions`.

**W9. Undefined variable `$PKG_BASE` in setup wizard**
- **File:** `/home/mikevitelli/uconsole-cloud/device/bin/uconsole-setup`, line 457
- `sudo cp "$CERT" "$PKG_BASE/webdash/uconsole.crt" 2>/dev/null || true` references `$PKG_BASE` which is never defined in the script. Under `set -u` this would be a fatal error, but the `|| true` silently swallows it. The cert copy never actually happens.
- **Fix:** Define `PKG_BASE="/opt/uconsole"` or use the correct variable.

---

### INFO

**I1. CSP allows unsafe-inline for scripts and styles**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 393-400
- `script-src 'self' 'unsafe-inline'` and `style-src 'self' 'unsafe-inline'` weaken the CSP. If an XSS vector is found, inline scripts can execute.
- **Suggestion:** Move to nonce-based CSP for scripts when feasible.

**I2. Password minimum length is 4 characters**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, line 229
- A 4-character minimum is very short. Combined with no login rate limiting (W3), this makes brute-force practical.
- **Suggestion:** Raise to at least 8 characters.

**I3. Polling loop uses fixed sleep without backoff**
- **File:** `/home/mikevitelli/uconsole-cloud/frontend/public/scripts/uconsole`, lines 177-294
- The device code polling loop sleeps 3 seconds between requests with no exponential backoff. If the server is slow or returns errors, the client hammers it at a constant rate for up to `$EXPIRES` seconds.
- The error status (line 284-287) is silently ignored with a no-op `:`.
- **Suggestion:** Implement exponential backoff (3s, 6s, 12s...) and log persistent errors.

**I4. The webdash launcher has no error handling**
- **File:** `/home/mikevitelli/uconsole-cloud/device/bin/webdash`, lines 1-4
- The entire launcher is `cd /opt/uconsole/webdash && exec python3 app.py "$@"`. No check that the directory or `app.py` exists. No `set -e`. If `/opt/uconsole/webdash` doesn't exist, cd fails silently and python3 runs in whatever the current directory is.
- **Fix:** Add `set -euo pipefail` and verify the target exists.

**I5. Unlink does not invalidate the cloud token**
- **File:** `/home/mikevitelli/uconsole-cloud/frontend/public/scripts/uconsole`, lines 349-379
- `cmd_unlink` removes the local config and stops timers, but does not call any API to invalidate the token server-side. The token remains valid in the cloud backend until it expires.
- **Suggestion:** Add an API call like `curl -X DELETE "${BASE_URL}/api/device/unlink" -H "Authorization: Bearer ${DEVICE_TOKEN}"` before deleting the local file.

**I6. json_val/json_num are brittle regex parsers**
- **File:** `/home/mikevitelli/uconsole-cloud/frontend/public/scripts/uconsole`, lines 27-36
- These functions use grep/sed to extract JSON values. They will fail on: escaped quotes in values, nested objects, values spanning multiple lines, null/boolean values, unicode escapes.
- If the server response changes format, these break silently (return empty string).
- **Suggestion:** Use `jq` with a fallback, or `python3 -c 'import json,sys; ...'`.

**I7. Rate limiter is in-memory and not thread-safe**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 256-286
- `_rate_buckets` is a plain dict with no locking, accessed from potentially concurrent request handlers (Flask with `threaded=True`). Under load, counts could be off.
- The rate limiter also never evicts old entries, growing unbounded over time (similar to W2).

**I8. SSE stream endpoint allows GET but scripts execute side effects**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, lines 1360-1392
- `/api/stream/<script>` uses GET method. While the allowed scripts list prevents arbitrary execution, some scripts like `power-reboot`, `backup-all`, `hotspot-start` have side effects. A GET request could be triggered by an img tag or prefetch.
- The run endpoint `/api/run/<script>` correctly uses POST (line 1344).
- **Suggestion:** Change `/api/stream/<script>` to accept POST only.

**I9. `allow_unsafe_werkzeug=True` in production**
- **File:** `/home/mikevitelli/uconsole-cloud/device/webdash/app.py`, line 1550
- This flag suppresses Werkzeug's warning about running in production without a production-ready server. Since nginx fronts this, the risk is mitigated, but it signals the code is not using a proper WSGI server (gunicorn/uwsgi).

**I10. Setup wizard cloud linking uses different API than CLI**
- **File:** `/home/mikevitelli/uconsole-cloud/device/bin/uconsole-setup`, lines 307-309
- The setup wizard posts to `/api/device/claim` while the CLI uses `/api/device/code` + `/api/device/poll`. The device code is locally generated with `secrets.token_hex(3)` (6 hex chars = 16M possibilities) rather than server-issued, and the claim endpoint returns a token directly. This is a weaker flow than the CLI's server-issued code approach.
- A brute-force of 6 hex characters is feasible (16M attempts).

---

### Summary of priority actions

1. **Fix C1 immediately** -- add `_password_is_set()` guard to `api_set_password()`. This is remotely exploitable by any LAN user.
2. **Fix C2 and C3** -- replace `eval` with safe alternatives in both `uconsole-setup` and the CLI.
3. **Add login rate limiting** (W3) to prevent brute-force against the 4-char minimum password.
4. **Fix the non-atomic writes** (W5) to prevent config corruption on crash.
5. **Change SSE streams to POST-only** (I8) to prevent CSRF-style triggering of side-effect scripts.