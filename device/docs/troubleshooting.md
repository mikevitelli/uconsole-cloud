# Troubleshooting

## iOS PWA Icon Shows as Letter Instead of Favicon

The uConsole dashboard uses a self-signed SSL certificate. iOS Safari won't load the favicon (or service worker) until you explicitly trust the certificate.

**Steps:**

1. Open Safari on your iPhone/iPad and navigate to `https://uconsole.local`
2. Accept the certificate warning ("This Connection Is Not Private" > "Show Details" > "visit this website")
3. Go to **Settings > General > About > Certificate Trust Settings**
4. Toggle **Enable Full Trust** for the `uconsole.local` certificate
5. Clear Safari data: **Settings > Safari > Clear History and Website Data**
6. Re-open `https://uconsole.local` in Safari
7. Tap the **Share** button > **Add to Home Screen**

The PWA icon should now show the uConsole favicon instead of a letter.

## Desktop is Bare After Reboot

**Cause:** The labwc autostart file at `~/.config/labwc/autostart` was overwritten and is missing the system default entries (pcmanfm, wf-panel, kanshi).

**Fix:** Ensure the file contains:

```
# System defaults
/usr/bin/lwrespawn /usr/bin/pcmanfm --desktop --profile LXDE-pi &
/usr/bin/lwrespawn /usr/bin/wf-panel-pi &
/usr/bin/kanshi &
/usr/bin/lxsession-xdg-autostart

# Workspace monitor
/opt/uconsole/bin/workspace-monitor >/dev/null 2>&1 &
```

The system defaults at `/etc/xdg/labwc/autostart` are overridden entirely when a user-level autostart exists. Both sets of entries must be present.

## Console Keybind Doesn't Work After apt upgrade

**Cause:** The `.deb` package installs to `/opt/uconsole/`. If you're developing with a local copy at `~/pkg/`, the installed version may be older.

**Fix:** The `console` entry point prefers `~/pkg/lib/` when it exists. If the keybind fails:

1. Check which framework is loaded: `python3 -c "import sys; sys.path.insert(0,'/opt/uconsole/lib'); from tui.framework import SCRIPT_DIR; print(SCRIPT_DIR)"`
2. If it shows `/opt/uconsole/scripts`, the dev tree isn't being found. Verify `~/pkg/lib/tui/framework.py` exists.
3. Run `uconsole update` to re-download the latest scripts from the package.

## Webdash Scripts Return Empty

**Cause:** The `SCRIPTS_DIR` in `app.py` can't find the script files, or a required tool isn't in the webdash service's PATH.

**Fix:**

1. Run `uconsole doctor` to verify all services are running
2. Check that `/opt/uconsole/scripts/` has subdirectories: `power/`, `network/`, `radio/`, `system/`, `util/`
3. For ESP32 commands (`esp32-info`, `esp32-flash`): ensure `esptool` is installed and in PATH. The webdash systemd service may need a PATH override:
   ```
   # /etc/systemd/system/uconsole-webdash.service.d/path.conf
   [Service]
   Environment=PATH=/home/<user>/.local/bin:/usr/local/bin:/usr/bin:/bin
   ```
4. Restart: `sudo systemctl daemon-reload && sudo systemctl restart uconsole-webdash`

## GPS Satellite Globe Shows "No Signal" Despite Having a Fix

**Cause:** gpsd switches the u-blox GPS module to native UBX binary protocol, which doesn't support satellite visibility messages on the AIO board's module.

**Fix:** Add the `-b` flag to gpsd to keep NMEA mode:

```bash
# Check current config
grep GPSD_OPTIONS /etc/default/gpsd

# Add -b if missing
sudo sed -i '/^GPSD_OPTIONS=/ s/"$/ -b"/' /etc/default/gpsd
sudo systemctl restart gpsd
```

The package installer adds `-b` automatically on install if gpsd and `/dev/ttyS0` are detected.

## LoRa SX1262 Not Detected / SPI Returns 0x00

**Cause:** The SX1262 is on SPI1 (`/dev/spidev1.0`), not the GPIO bit-banged SPI4. The `spi1-1cs` overlay must be loaded, and the chip needs a GPIO hardware reset.

**Fix:** `lora.sh` loads the overlay on demand. If manual testing:

```bash
# Load SPI1 overlay
sudo dtoverlay spi1-1cs

# Reset the chip (GPIO 25) and probe
python3 -c "
import subprocess, time, spidev
subprocess.run(['gpioset','-m','exit','gpiochip0','25=0'])
time.sleep(0.05)
subprocess.run(['gpioset','-m','exit','gpiochip0','25=1'])
time.sleep(0.1)
spi = spidev.SpiDev(); spi.open(1,0); spi.max_speed_hz=1000000; spi.mode=0
resp = spi.xfer2([0x1D,0x03,0x20,0x00,0x00])
print(f'Version: 0x{resp[-1]:02X}')  # expect 0x53 or 0x58
"

# Unload when done (avoids audio interference)
sudo dtoverlay -r spi1-1cs
```

**Note:** Do NOT add `spi1-1cs` to `/boot/firmware/config.txt` — SPI1 (GPIO 18-21) causes static on the PWM audio output (GPIO 12-13). The overlay is loaded/unloaded on demand.

## uConsole Won't Boot on Battery

**Cause:** The AXP228 PMU defaults to a 3.3V undervoltage cutoff (VOFF). 18650 cells sag below 3.3V during boot inrush current, and the PMU kills power before the OS starts.

**Fix:** Install the battery boot fix from the TUI:

```
Power > Power Config > Install Boot Fix
```

Or from the command line:

```bash
sudo bash /opt/uconsole/scripts/power/fix-battery-boot.sh install
```

This installs three layers: a udev rule, an initramfs hook (sets VOFF before heavy boot loads), and a shutdown service (persists VOFF through reboot). Check status with:

```bash
bash /opt/uconsole/scripts/power/fix-battery-boot.sh status
```

To revert: `sudo bash /opt/uconsole/scripts/power/fix-battery-boot.sh remove`

## WiFi Fallback AP Not Starting

**Cause:** The NetworkManager dispatcher script (`wifi-fallback.sh`) isn't installed, or the hotspot connection profile is missing.

**Fix:**

1. Check if the dispatcher is installed: `ls /etc/NetworkManager/dispatcher.d/ | grep wifi-fallback`
2. Check if the hotspot profile exists: `nmcli connection show | grep uConsole`
3. Re-run `uconsole setup` to reconfigure the hotspot
4. Manually create the AP: `nmcli connection add type wifi ifname wlan0 con-name uConsole autoconnect no ssid uConsole`
