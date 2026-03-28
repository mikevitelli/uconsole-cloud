# Networking

## WiFi Configuration

- **Interface**: `wlan0` (TP-Link external USB adapter)
- **Manager**: NetworkManager
- **Antenna**: External (ant2)

## Current Network

Check with `scripts/network.sh` or the web dashboard.

Typical output:
- SSID, band, signal strength (dBm), quality, bit rate
- IP address, gateway, DNS, MAC address

## Subcommands

```
network.sh           # connection overview
network.sh speed     # download/upload speed test
network.sh scan      # nearby WiFi networks
network.sh ping      # latency test (default: 1.1.1.1)
network.sh trace     # traceroute
network.sh log       # append entry to ~/network.log
```

## SSH Access

- **Port**: 2222 (non-default for security)
- **Config**: `/etc/ssh/sshd_config`
- **Root login**: disabled
- **Max auth tries**: 3

### Connecting from Mac

Add to `~/.ssh/config` on the Mac:

```
Host uconsole
    HostName <device-ip>
    User <your-username>
    Port 2222
```

Then connect with:

```bash
ssh uconsole
```

### Key-Based Auth (recommended)

To skip password prompts, copy your Mac's SSH key:

```bash
ssh-copy-id -p 2222 uconsole
```

Once keys are set up, you can disable password auth on the server by setting `PasswordAuthentication no` in `/etc/ssh/sshd_config` and restarting sshd.

## Troubleshooting

- **No WiFi**: Check `nmcli device status`, restart NetworkManager
- **Slow speeds**: Check signal quality, try `network.sh scan` for less congested channels
- **Driver issues**: TP-Link driver is in `drivers/` directory
