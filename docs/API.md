# API and telemetry

## Device telemetry payload

`push-status.sh` collects from sysfs and procfs on each tick:

| Category | Source | Metrics |
|----------|--------|---------|
| Battery | `/sys/class/power_supply/axp20x-battery/` | capacity, voltage, current, status, health |
| CPU | `/sys/class/thermal/`, `/proc/loadavg` | temperature, load average, core count |
| Memory | `/proc/meminfo` | total, used, available |
| Disk | `df` | total, used, available, percent |
| WiFi | `iwconfig wlan0` | SSID, signal dBm, quality, bitrate, IP |
| Screen | `/sys/class/backlight/` | brightness, max brightness |
| AIO Board | `lsusb`, `/dev/spidev4.0`, `i2cdetect` | SDR, LoRa, GPS fix, RTC sync |
| Hardware | `/etc/uconsole/hardware.json` | expansion module, component detection |
| Webdash | `systemctl` | running, port |
| System | `hostname`, `uname`, `/proc/uptime` | hostname, kernel, uptime |

The full payload is POSTed to `/api/device/push` with a `Bearer <device_token>` header. Cached in Upstash Redis keyed by `user:device`.

## Cloud routes

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/api/device/code` | POST | No | Generate device code (rate-limited 5/min/IP) |
| `/api/device/code/confirm` | POST | Session | Confirm code, issue device token |
| `/api/device/poll/[secret]` | GET | No | Poll for code confirmation |
| `/api/device/push` | POST | Bearer | Accept device telemetry |
| `/api/device/status` | GET | Session | Fetch cached status + online flag |
| `/api/github/*` | GET/POST | Session | GitHub API proxy |
| `/api/settings` | GET/POST/DELETE | Session | User settings, repo linking |
| `/api/scripts/[name]` | GET | No | Serve allowlisted scripts |
| `/api/health` | GET | No | Redis health check |
| `/install` | GET | No | APT bootstrap script |
| `/apt/*` | GET | No | GPG-signed APT repository |

See [DEVICE-LINKING.md](DEVICE-LINKING.md) for the full device auth flow (code generation → confirmation → token issuance).
