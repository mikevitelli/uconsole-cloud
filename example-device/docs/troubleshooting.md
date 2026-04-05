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
   Environment=PATH=/home/mikevitelli/.local/bin:/usr/local/bin:/usr/bin:/bin
   ```
4. Restart: `sudo systemctl daemon-reload && sudo systemctl restart uconsole-webdash`

## WiFi Fallback AP Not Starting

**Cause:** The NetworkManager dispatcher script (`wifi-fallback.sh`) isn't installed, or the hotspot connection profile is missing.

**Fix:**

1. Check if the dispatcher is installed: `ls /etc/NetworkManager/dispatcher.d/ | grep wifi-fallback`
2. Check if the hotspot profile exists: `nmcli connection show | grep uConsole`
3. Re-run `uconsole setup` to reconfigure the hotspot
4. Manually create the AP: `nmcli connection add type wifi ifname wlan0 con-name uConsole autoconnect no ssid uConsole`
