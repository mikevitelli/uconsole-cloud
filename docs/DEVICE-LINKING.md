# Device Linking Flow

How a uConsole device gets linked to a user's uconsole.cloud account. See also `uconsole doctor` for diagnosing linking issues after setup.

## Overview

```
┌─────────────────────────┐         ┌─────────────────────────┐
│     uConsole (device)   │         │   uconsole.cloud        │
│                         │         │                         │
│  1. uconsole setup      │         │                         │
│     ↓                   │         │                         │
│  2. POST /api/device/   │ ──────→ │  3. Generate code +     │
│        code             │         │     secret (Redis,      │
│     ↓                   │         │     10-min TTL)         │
│  4. Display code        │         │                         │
│     "AB12-CD34"         │         │                         │
│     + QR to /link?code= │         │                         │
│                         │         │                         │
│  5. Poll every 2s:      │         │                         │
│     GET /api/device/    │ ──────→ │  (returns "pending")    │
│       poll/{secret}     │         │                         │
│                         │         │                         │
│                         │         │  ┌───────────────────┐  │
│                         │         │  │ User opens /link   │  │
│                         │         │  │ (or scans QR)      │  │
│                         │         │  │                    │  │
│                         │         │  │ 6. Types code      │  │
│                         │         │  │ 7. POST /api/      │  │
│                         │         │  │    device/code/    │  │
│                         │         │  │    confirm         │  │
│                         │         │  │    ↓               │  │
│                         │         │  │ 8. Generate token  │  │
│                         │         │  │    (UUID, 90-day   │  │
│                         │         │  │     TTL in Redis)  │  │
│                         │         │  │ 9. Mark code       │  │
│                         │         │  │    "confirmed"     │  │
│                         │         │  └───────────────────┘  │
│                         │         │                         │
│  10. Poll returns       │ ←────── │  status: "confirmed"    │
│      { deviceToken,     │         │  + cleanup both Redis   │
│        repo }           │         │    keys (single-use)    │
│     ↓                   │         │                         │
│  11. Write status.env:  │         │                         │
│      DEVICE_TOKEN=...   │         │                         │
│      DEVICE_REPO=...    │         │                         │
│      DEVICE_API_URL=... │         │                         │
│     ↓                   │         │                         │
│  12. Start systemd      │         │                         │
│      timer → pushes     │ ──────→ │  POST /api/device/push  │
│      status every 5min  │         │  (Bearer token)         │
│                         │         │                         │
└─────────────────────────┘         └─────────────────────────┘
```

## Prerequisites

Before linking, the user must:
1. Sign in at uconsole.cloud with GitHub
2. Link a backup repository (POST /api/settings with `{ repo: "owner/repo" }`)

The /link page checks for a linked repo and shows "Link Repository First" + RepoLinker if none exists.

## API Endpoints

### POST /api/device/code

Generates a new device code. Rate-limited to 5 requests per minute per IP.

No authentication required (called from device terminal before user is authenticated).

**Request:** Empty body

**Response (200):**
```json
{
  "code": "AB12-CD34",
  "secret": "550e8400-e29b-41d4-a716-446655440000",
  "expiresIn": 600
}
```

**Response (429):**
```json
{
  "error": "Too many requests. Try again later."
}
```
Headers: `Retry-After: <seconds>`

**Redis keys created:**
- `devicecode:{code}` → `{ secret, status: "pending", createdAt }` (TTL: 600s)
- `devicepoll:{secret}` → `{ status: "pending", code }` (TTL: 600s)

### GET /api/device/poll/{secret}

Device polls this endpoint every 2 seconds waiting for confirmation.

No authentication required. Secret is a UUID v4.

**Response (200, pending):**
```json
{
  "status": "pending"
}
```

**Response (200, confirmed):**
```json
{
  "status": "confirmed",
  "deviceToken": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "repo": "username/uconsole"
}
```

On confirmed response, both Redis keys (`devicecode:{code}` and `devicepoll:{secret}`) are deleted (single-use).

**Response (404):**
```json
{
  "error": "Not found or expired"
}
```

### POST /api/device/code/confirm

User confirms the code from the web UI. Requires session auth.

**Request:**
```json
{
  "code": "AB12-CD34"
}
```

**Response (200):**
```json
{
  "success": true,
  "repo": "username/uconsole"
}
```

**Response (400):**
```json
{
  "error": "Code not found or expired"
}
```

**What happens on confirm:**
1. Validates session (must be signed in)
2. Validates user has a linked repo
3. Generates a new device token (UUID v4, 90-day TTL) via `generateDeviceToken()`
4. Stores token in Redis at `devicetoken:{token}` → `{ userId, repo, createdAt }`
5. Updates user settings with token reference
6. Marks the code as "confirmed" in both Redis keys

### POST /api/device/push

Accepts telemetry from the device. Bearer token auth.

**Request headers:** `Authorization: Bearer {deviceToken}`

**Request body:** Device status JSON (see DeviceStatusPayload type)

**Response (200):**
```json
{
  "ok": true
}
```

**Token validation:** Looks up `devicetoken:{token}` in Redis, returns `{ userId, repo }` if valid.

### POST /api/settings/regenerate-token

Regenerates the device token. Requires session auth.

**Response (200):**
```json
{
  "ok": true,
  "deviceToken": "new-uuid-here"
}
```

Revokes the old token (deletes from Redis), generates a new one with fresh 90-day TTL.

## Token Lifecycle

### Creation
- Generated during code confirmation (POST /api/device/code/confirm)
- Also generated when linking a repo (POST /api/settings)
- UUID v4 format, cryptographically random

### Storage
- **Redis:** `devicetoken:{token}` → `{ userId, repo, createdAt }`, TTL 90 days
- **User settings (Redis):** `user:{userId}` includes `deviceToken` field (reference)
- **Device:** `~/.config/uconsole/status.env` file, chmod 600

### Rotation
- Manual via POST /api/settings/regenerate-token
- Old token is deleted from Redis before new one is created
- Device must be reconfigured with the new token (re-run `uconsole setup` or manual edit)

### Revocation
- On token regeneration (old token deleted)
- On repo unlink (DELETE /api/settings — deletes token and all user settings)
- Token naturally expires after 90 days (Redis TTL)

### Validation
- Every push request validates the token via `validateDeviceToken()`
- Simple Redis GET — if key exists and hasn't expired, token is valid
- Returns `{ userId, repo }` used to scope the Redis write

## Code Format

- 8 alphanumeric characters displayed as `XXXX-XXXX`
- Character set: `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no I, O, 0, 1 to avoid ambiguity)
- Generated using `crypto.getRandomValues()` — cryptographically random
- Case-insensitive on input (normalized to uppercase)

## Edge Cases

### Code expiry
- Codes expire after 10 minutes (Redis TTL)
- Device poll returns 404 after expiry
- Device CLI should handle this by generating a new code

### User cancellation
- If user closes the /link page without confirming, the code naturally expires
- No cleanup needed — Redis TTL handles it

### Re-linking
- User can link the same device multiple times
- Each confirmation generates a new token
- Old token remains valid until it expires (90 days) or is regenerated
- Multiple valid tokens can exist simultaneously for the same user/repo

### Already-confirmed code
- If a code is submitted twice, the second attempt gets "Code already used"
- The confirm endpoint checks `codeData.status !== "pending"`

### No repo linked
- /link page shows RepoLinker component instead of code form
- /api/device/code/confirm returns 400 "No repository linked"

### QR code shortcut
- Device generates QR code pointing to `https://uconsole.cloud/link?code=AB12-CD34`
- /link page accepts `?code=` query param to pre-fill the form
- User still needs to click "Confirm" (no auto-confirm from URL)

## Troubleshooting

### `uconsole doctor`

The doctor command checks all components of the linking and push pipeline:

- **Timer status** — is the systemd timer active and firing?
- **Cron conflicts** — warns if both a cron job and systemd timer exist (dual-fire)
- **Push connectivity** — can the device reach uconsole.cloud?
- **Token validity** — is `status.env` present and readable?
- **SSL certificate** — is the self-signed cert valid and has SANs?
- **Nginx** — is the reverse proxy running and serving the webdash?
- **Webdash** — is the Flask app running?

Run `uconsole doctor` after setup or whenever telemetry stops appearing in the dashboard.

### Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Device offline" in dashboard | Timer not running | `uconsole doctor`, then `uconsole setup` to re-enable |
| Push fails with 401 | Token expired (90-day TTL) | `uconsole link` to get a new token |
| Code expired during linking | Took >10 minutes | Run `uconsole link` again for a fresh code |
| Both cron and timer active | Legacy cron from older install | `uconsole doctor` detects this; `uconsole setup` cleans up |

## Proposed Improvements

### Token refresh on push
Currently tokens expire silently after 90 days. The push endpoint could extend the TTL on each successful push, effectively making the token auto-renewing as long as the device is actively pushing.

### Multiple device support
Currently one token per user. To support multiple devices, the token → device mapping should include a device identifier (hostname or hardware ID) and user settings should store an array of linked devices.

### Confirmation notification
The /link page redirects to the dashboard after confirmation but doesn't surface the token. The device already gets it via polling, but a "Device successfully linked" toast on the dashboard would improve UX.

### Code auto-fill from QR
The /link page could auto-submit when a valid `?code=` param is present (after user confirms with a button), reducing friction for QR scan flow.
