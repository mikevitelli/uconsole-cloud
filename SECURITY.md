# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability, please report it privately rather than opening a public issue.

**Email:** mike@uconsole.cloud

Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

I'll acknowledge receipt within 48 hours and aim to release a fix within 7 days for critical issues.

## Scope

This policy covers:

- The uconsole.cloud web application (Next.js frontend, API routes)
- The `uconsole` CLI and device scripts
- The `.deb` package and its install/removal scripts (postinst, prerm, postrm)
- Authentication and device token handling
- The APT repository and GPG signing infrastructure

## Security model

### Cloud (uconsole.cloud)

| Layer | Implementation |
|-------|----------------|
| Authentication | NextAuth v5 + GitHub OAuth, JWT strategy, middleware-enforced on all protected routes |
| Device auth | Bearer tokens (UUID v4, 90-day TTL in Redis), rate-limited code generation (5/min/IP) |
| Input validation | Path traversal blocks, SHA-1 regex, strict `owner/repo` format validation |
| HTTP headers | CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, strict Referrer-Policy, Permissions-Policy |
| Error handling | Typed `GitHubError` (401/403 surfaced to user), error boundary hides stack traces |
| Data isolation | Redis keys scoped by repo (`device:{repo}:status`), device tokens scoped by user |
| APT repository | GPG-signed Release files, public key distributed via HTTPS |

### Device (local)

| Layer | Implementation |
|-------|----------------|
| Webdash auth | bcrypt password hashing (python3-bcrypt), cryptographic session tokens (`secrets.token_hex`) |
| Session management | Server-side session store with 30-day TTL, session invalidation on password change |
| TLS | Self-signed certificate with SANs at `/etc/uconsole/ssl/` (generated during setup, Chrome-compatible) |
| Token storage | `status.env` is chmod 600, owned by the installing user |
| Services | Systemd units run as the installing user (not root), services not auto-enabled on install |
| Config | `/etc/uconsole/uconsole.conf` and `hardware.json` are conffiles (preserved on upgrade) |

### Known considerations

- Device tokens are 90-day UUIDs — they expire silently if the device stops pushing. Token refresh on push is a planned improvement (see FEATURES.md Phase 5).
- The local webdash uses a self-signed SSL certificate. Browsers will show a warning on first visit.
- Device code auth is rate-limited but codes are only 8 alphanumeric characters. The 10-minute TTL and single-use design mitigate brute-force risk.
- The install script (`curl | sudo bash`) is served over HTTPS from Vercel CDN. The script adds the GPG key and APT source — it does not run arbitrary code beyond that.
- Power scripts (`scripts/power/`) are safety-critical. Changes to battery charge/discharge logic require extra review.
