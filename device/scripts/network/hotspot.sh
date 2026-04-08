#!/bin/bash
# Manual hotspot toggle for the uConsole.
# Usage: hotspot.sh [on|off|status|toggle]

set -euo pipefail

CONF_FILE="$HOME/.config/uconsole/hotspot.conf"
HOTSPOT_SSID="uConsole"
HOTSPOT_PASS="clockwork"
# Override from config file if present
if [ -f "$CONF_FILE" ]; then
    while IFS='=' read -r key val; do
        case "$key" in
            ssid) [ -n "$val" ] && HOTSPOT_SSID="$val" ;;
            pass) [ -n "$val" ] && HOTSPOT_PASS="$val" ;;
        esac
    done < "$CONF_FILE"
fi
HOTSPOT_BAND="bg"
CON_NAME="uConsole-Hotspot"
IFACE="wlan0"
LOG_TAG="hotspot"

log() { logger -t "$LOG_TAG" "$1"; }

is_hotspot_active() {
    nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep -q "^${CON_NAME}:${IFACE}"
}

start_hotspot() {
    if is_hotspot_active; then
        echo "Hotspot already active (SSID: ${HOTSPOT_SSID}, pass: ****)"
        return 0
    fi

    # Delete old hotspot connection if it exists
    nmcli con delete "$CON_NAME" 2>/dev/null || true

    nmcli device wifi hotspot \
        ifname "$IFACE" \
        con-name "$CON_NAME" \
        ssid "$HOTSPOT_SSID" \
        band "$HOTSPOT_BAND" \
        password "$HOTSPOT_PASS" 2>/dev/null

    log "Hotspot started (SSID: ${HOTSPOT_SSID})"
    echo "Hotspot ON (SSID: ${HOTSPOT_SSID}, pass: ****)"
}

stop_hotspot() {
    if ! is_hotspot_active; then
        echo "Hotspot not running"
        return 0
    fi

    nmcli con down "$CON_NAME" 2>/dev/null || true
    log "Hotspot stopped"
    echo "Hotspot OFF"

    # Try to reconnect to a known WiFi network
    sleep 2
    nmcli device wifi connect --wait 10 2>/dev/null || \
        nmcli device connect "$IFACE" 2>/dev/null || true
}

show_status() {
    if is_hotspot_active; then
        echo "Hotspot active (SSID: ${HOTSPOT_SSID}, pass: ****)"
    else
        echo "Hotspot off"
    fi
}

case "${1:-toggle}" in
    on|start)   start_hotspot ;;
    off|stop)   stop_hotspot ;;
    status)     show_status ;;
    toggle)
        if is_hotspot_active; then
            stop_hotspot
        else
            start_hotspot
        fi
        ;;
    *)
        echo "Usage: hotspot.sh [on|off|status|toggle]"
        exit 1
        ;;
esac
