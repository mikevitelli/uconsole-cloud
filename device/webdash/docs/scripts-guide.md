# Scripts Guide

## All Scripts

| Script | Description | Subcommands |
|--------|-------------|-------------|
| `battery.sh` | Battery analysis (AXP228 PMU) | *(default)* snapshot, `watch`, `log` |
| `cellhealth.sh` | Cell health diagnostics | *(default)* full test, `quick`, `log` |
| `charge.sh` | Set charge current | `300`, `500`, `900` (mA) |
| `cpu-freq-cap.sh` | Cap CPU at 1.2 GHz | — |
| `pmu-voltage-min.sh` | Lower undervoltage cutoff | — |
| `power.sh` | Power management | `status`, `reboot`, `shutdown` |
| `network.sh` | Network diagnostics | *(default)* overview, `speed`, `scan`, `ping`, `trace`, `watch`, `log` |
| `hotspot.sh` | WiFi hotspot toggle | `on`, `off`, `status`, `toggle` |
| `push-status.sh` | Push status to uconsole.cloud | — |
| `storage.sh` | Storage health and info | *(default)* overview, `devices`, `smart`, `usb`, `mount`, `temp` |
| `diskusage.sh` | Disk usage analysis | *(default)* overview, `big`, `dirs`, `clean` |
| `audit.sh` | Repo audit | *(default)* overview, `junk`, `clean`, `untracked`, `categories` |
| `backup.sh` | Backup manager | `all`, `git`, `gh`, `system`, `packages`, `desktop`, `browser`, `status` |
| `update.sh` | System updates | `all`, `apt`, `flatpak`, `firmware`, `repo`, `status`, `log`, `snapshot` |
| `crash-log.sh` | Boot and crash errors | — |
| `console` (binary in `/opt/uconsole/bin/`) | TUI command center — see [console-tui.md](console-tui.md) | — |
| `webdash` app at `/opt/uconsole/webdash/app.py` | Web dashboard (Flask) — see [webdash.md](webdash.md) | run via `systemctl --user start uconsole-webdash` |
| `webdash-info.sh` | Webdash status overview | — |
| `webdash-ctl.sh` | Webdash service control | `start`, `stop`, `restart`, `logs`, `config` |
| `aio-check.sh` | AIO V1 board check | — |
| `boot-check.sh` | Boot health check | — |

## Console TUI

The `console` command launches a full-screen TUI with 9 categories, 64 native handlers, gamepad support, and 30+ color themes. See [console-tui.md](console-tui.md) for full documentation.

## Web Dashboard

The web dashboard runs behind nginx with HTTPS and session-based auth. See [webdash.md](webdash.md) for full documentation.

### Quick Start

```bash
sudo systemctl start uconsole-webdash     # start via systemd
sudo systemctl stop uconsole-webdash      # stop
uconsole-passwd                            # change password
```

Access: `https://uconsole.local` (LAN only, login required)

## Backup Workflow

```bash
backup.sh all          # full backup + commit + push
backup.sh packages     # snapshot package managers
backup.sh system       # etc configs, hostname, fstab
backup.sh status       # check coverage
```

## Update Workflow

```bash
update.sh all          # apt + flatpak + firmware + repo sync
update.sh apt          # apt only
update.sh status       # check what's outdated
update.sh log          # show history
```

## Restore Workflow

On a fresh uConsole:

```bash
curl -s https://uconsole.cloud/install | sudo bash
cd uconsole
./restore.sh
```

The restore script symlinks configs, copies system files, and reinstalls packages.
