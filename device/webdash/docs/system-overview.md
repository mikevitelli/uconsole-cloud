# System Overview

## Hardware

- **Device**: Clockwork Pi uConsole (handheld Linux terminal)
- **SoC**: Raspberry Pi CM4 (aarch64)
- **Kernel**: 5.10.17-v8+ (PREEMPT, custom Clockwork build)
- **RAM**: 3.7 GB
- **Storage**: 32GB SD card (SK32G, mfg 11/2023)
- **Battery**: AXP228 PMU, Li-Po
- **WiFi**: TP-Link external adapter (wlan0)
- **Display**: Built-in LCD with backlight control
- **Audio**: DevTerm audio patch (systemd service)
- **Cooling**: CM4 fan daemon (temperature-controlled)

## OS

- **Distribution**: Debian 11 (Bullseye)
- **Desktop**: GNOME (GDM display manager)
- **Architecture**: aarch64 (ARM 64-bit)

## Storage Layout

| Mount | Device | Size | Filesystem |
|-------|--------|------|------------|
| `/` | /dev/mmcblk0p2 | 30G | ext4 |
| `/boot` | /dev/mmcblk0p1 | 253M | vfat |

## Key Services

- `bluetooth` — Bluetooth stack
- `docker` — Container runtime
- `cups` — Print service
- `cron` — Scheduled tasks
- `flatpak-system-helper` — Flatpak app support
- `devterm-audio-patch` — Audio speaker fix
- `devterm-fan-temp-daemon` — Fan speed control
- `gdm` — GNOME Display Manager
- `avahi-daemon` — mDNS/DNS-SD
- `containerd` — Container runtime (Docker backend)
