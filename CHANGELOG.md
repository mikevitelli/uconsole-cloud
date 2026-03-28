# Changelog

## v0.1.0 (2026-03-28)

First public release.

### Device Package (`uconsole-cloud`)
- 40+ management scripts organized by category (system, power, network, radio, util)
- Curses TUI with 8 categories and 14 native tools (FM Radio, GPS globe, live monitor, file browser, etc.)
- Flask web dashboard with terminal access, live stats, script execution, PWA support
- Interactive setup wizard (hardware detection, bcrypt passwords, SSL certs, cloud linking)
- `uconsole` CLI: setup, link, push, status, doctor, restore, unlink, update, version
- Systemd services run as the installing user (not root)
- Self-signed TLS with SANs (Chrome-compatible)
- WiFi fallback AP when no known network available
- Optional AIO board support (RTL-SDR, LoRa, GPS, RTC) — graceful degradation

### Cloud Dashboard (`uconsole.cloud`)
- Live device telemetry (battery, CPU, memory, disk, WiFi, AIO board)
- Persistent status — survives reboots, shows staleness indicators
- Backup coverage across 9 categories with sparklines and calendar grid
- Package inventory, browser extensions, scripts manifest, repo tree
- Hardware manifest panel
- Device code auth (8-character code + QR scan)
- Same-network detection with direct local webdash link
- PWA installable on iOS/Android
- GPG-signed APT repository hosted on Vercel
- `curl -s https://uconsole.cloud/install | sudo bash` install story
- Documentation page at /docs

### Security
- bcrypt password hashing (replaces plaintext)
- Cryptographic session tokens (secrets.token_hex)
- Server-side session store with 30-day TTL
- Rate-limited device code generation (5/min/IP)
- CSP, X-Frame-Options, nosniff, strict Referrer-Policy
- Redis keys scoped by repo, device tokens scoped by user
