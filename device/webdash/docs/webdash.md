# Web Dashboard

The uConsole web dashboard is a Flask app (`device/webdash/app.py` in source; `/opt/uconsole/webdash/app.py` when installed) served behind an nginx reverse proxy with HTTPS and session-based authentication.

## Architecture

```
Phone/Browser  →  nginx (port 443, HTTPS)  →  Flask (127.0.0.1:8080)
```

- **nginx** handles TLS termination, serves error pages when webdash is down
- **Flask** handles authentication, serves the dashboard and API endpoints
- **webdash** binds to `127.0.0.1` only — never directly accessible from the network

## Access

| Device | URL |
|--------|-----|
| LAN (phone/laptop) | `https://<device-ip>` |
| uConsole locally | `https://127.0.0.1` |

- Login credentials are set during initial setup (see `uconsole-passwd` or set via env vars `WEBDASH_USER`, `WEBDASH_PASS`)
- Session cookie lasts 30 days

### iPhone Home Screen App

1. Open `https://<device-ip>` in Safari
2. Log in
3. Tap Share → Add to Home Screen
4. The `apple-mobile-web-app-capable` meta tag makes it run fullscreen

## SSL Certificates

Self-signed certificate, valid until **2036-03-20** (10 years).

### File locations

| File | Path | Backed up |
|------|------|-----------|
| Certificate (public) | `/etc/ssl/certs/uconsole.crt` | `system/ssl/uconsole.crt` (git tracked) |
| Private key | `/etc/ssl/private/uconsole.key` | `system/ssl/uconsole.key` (gitignored) |

### Generate new certificates

If the cert expires or you set up a new device:

```bash
# Generate a new self-signed cert (valid 10 years)
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/ssl/private/uconsole.key \
  -out /etc/ssl/certs/uconsole.crt \
  -subj "/CN=uconsole/O=uConsole/C=US"

# Restart nginx to pick up the new cert
sudo systemctl reload nginx

# Back up to repo
cp /etc/ssl/certs/uconsole.crt ~/system/ssl/
sudo cp /etc/ssl/private/uconsole.key ~/system/ssl/
sudo chown $USER:$USER ~/system/ssl/uconsole.key
chmod 600 ~/system/ssl/uconsole.key
```

After generating a new cert, you must re-trust it on all devices:

**iPhone:**
1. Download cert: `https://<uconsole-ip>/uconsole.crt`
2. Settings → General → VPN & Device Management → Install profile
3. Settings → General → About → Certificate Trust Settings → Enable full trust

**Mac:**
```bash
scp -P 2222 user@<device-ip>:~/uconsole.crt ~/Downloads/
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/Downloads/uconsole.crt
```

### Restore certs from backup

```bash
sudo cp ~/system/ssl/uconsole.crt /etc/ssl/certs/
sudo cp ~/system/ssl/uconsole.key /etc/ssl/private/
sudo chmod 644 /etc/ssl/certs/uconsole.crt
sudo chmod 600 /etc/ssl/private/uconsole.key
sudo systemctl reload nginx
```

## nginx Configuration

Config file: `/etc/nginx/sites-available/webdash`

- Listens on port 443 (HTTPS only)
- Proxies all requests to `127.0.0.1:8080`
- Custom error pages at `/etc/nginx/error-pages/` for 502, 503, 504
- Only accessible from your local network via UFW

### Error pages

When webdash is down, nginx serves themed error pages instead of the default ugly ones:

| Code | Message | When |
|------|---------|------|
| 502 | Dashboard Offline | webdash process not running |
| 503 | Dashboard Restarting | webdash temporarily unavailable |
| 504 | Dashboard Timed Out | webdash not responding in time |

## Webdash Service

```bash
# Status
sudo systemctl status uconsole-webdash

# Restart
sudo systemctl restart uconsole-webdash

# Logs
journalctl -u uconsole-webdash -f

# Manual run (for debugging)
python3 /opt/uconsole/webdash/app.py
```

## Authentication

Session-based auth with HMAC tokens stored in a cookie.

- Login page: `/login` (styled with animated uConsole GIF)
- Logout: `/logout` (clears session cookie)
- Unauthenticated requests redirect to `/login`
- Public paths (no auth required): `/login`, `/favicon.png`, `/apple-touch-icon.png`, `/uconsole.crt`, `/uConsole.gif`
- Cookie: `webdash_session`, 30-day expiry, httponly, secure, samesite=Lax

### Change credentials

Set credentials with the CLI helper (recommended):

```bash
sudo uconsole-passwd      # interactive prompt, writes hashed creds
```

Or via environment variables before starting webdash directly:

```bash
WEBDASH_USER=<your-user> WEBDASH_PASS=<your-pass> python3 /opt/uconsole/webdash/app.py
```

## Security Hardening (2026-03-22)

All changes made in one session:

| Layer | Change | Config |
|-------|--------|--------|
| Firewall | UFW: deny inbound, allow SSH 2222, allow LAN 443 | `sudo ufw status` |
| SSH | Port 2222, password auth, no root, max 3 tries | `/etc/ssh/sshd_config` |
| fail2ban | Bans IPs after 3 failed SSH attempts for 1hr | `/etc/fail2ban/jail.local` |
| AppArmor | Enabled (requires reboot to activate) | `/boot/firmware/cmdline.txt` |
| Bluetooth | Pairable disabled | `/etc/bluetooth/main.conf` |
| epmd | Stopped, disabled, masked (port 4369) | `systemctl status epmd` |
| webdash | Bound to localhost, behind nginx with auth | `/opt/uconsole/webdash/app.py` |
| nginx | HTTPS reverse proxy, custom error pages | `/etc/nginx/sites-available/webdash` |

### SSH access after hardening

```bash
ssh -p 2222 user@<device-ip>
```

## Troubleshooting

**Can't reach webdash from phone/laptop:**
- Check you're on the same WiFi network as the uConsole
- Check nginx: `sudo systemctl status nginx`
- Check webdash: `sudo systemctl status uconsole-webdash`
- Check firewall: `sudo ufw status`

**502 Bad Gateway:**
- webdash crashed or isn't running: `sudo systemctl restart uconsole-webdash`

**Cert warnings after regenerating:**
- You need to re-trust the cert on every device (see Generate new certificates above)

**Locked out of SSH:**
- Connect a keyboard/monitor directly to the uConsole
- Check `/etc/ssh/sshd_config` for issues
- Backup config at `/etc/ssh/sshd_config.bak`

**Login not working:**
- Clear cookies and retry
- Reset credentials with `sudo uconsole-passwd`
- Visit `/logout` first to clear stale session
