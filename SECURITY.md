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
- The `.deb` package and its install/removal scripts
- Authentication and device token handling

## Known security considerations

- Device tokens are 90-day UUIDs stored in `status.env` (chmod 600)
- The local webdash uses a self-signed SSL certificate
- Device code auth is rate-limited to 5 requests per minute per IP
- All API routes require session auth except device push (Bearer token) and public endpoints
