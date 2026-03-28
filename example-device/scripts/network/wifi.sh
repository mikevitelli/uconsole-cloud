#!/bin/bash
# Quick WiFi management for the uConsole.
# Usage: wifi.sh              Show current connection status
#        wifi.sh iphone       Connect to iPhone hotspot
#        wifi.sh home         Connect to home WiFi
#        wifi.sh scan         Scan for nearby networks
#        wifi.sh ip           Show IP and gateway (for webdash URL)

source "$(dirname "$0")/lib.sh"

command -v nmcli >/dev/null 2>&1 || { err "nmcli not found"; exit 1; }
nmcli general status >/dev/null 2>&1 || { err "NetworkManager is not running"; exit 1; }

exec 200>"${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/wifi.sh.lock"
flock -n 200 || { err "Another wifi.sh instance is running"; exit 1; }

IFACE="wlan0"
IPHONE_CON="MyHotspot"
HOME_CON="MyNetwork"
OFFICE_CON="OfficeWiFi"

# ── helpers ──

wifi_state() {
    nmcli -t -f TYPE,STATE device status 2>/dev/null | grep '^wifi:' | head -1 | cut -d: -f2
}

active_connection() {
    nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | sed -n "s/:${IFACE}$//p"
}

wait_for_ip() {
    local tries=0
    while [ "$tries" -lt 15 ]; do
        local ip
        ip=$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
        if [ -n "$ip" ]; then
            echo "$ip"
            return 0
        fi
        sleep 1
        tries=$((tries + 1))
    done
    return 1
}

# Wait for a specific SSID to appear in scan results.
# iPhone hotspots only broadcast when the hotspot screen is open,
# and take several seconds to become visible after opening it.
wait_for_ssid() {
    local ssid="$1" max_wait="${2:-30}"
    local elapsed=0
    info "Waiting for '${ssid}' to appear (up to ${max_wait}s)..."
    info "Tip: open Settings > Personal Hotspot on iPhone"
    while [ "$elapsed" -lt "$max_wait" ]; do
        nmcli device wifi rescan 2>/dev/null || true
        sleep 3
        elapsed=$((elapsed + 3))
        if nmcli -t -f SSID device wifi list 2>/dev/null | grep -qxF "$ssid"; then
            ok "Found '${ssid}' after ${elapsed}s"
            return 0
        fi
        info "  scanning... (${elapsed}s)"
    done
    warn "'${ssid}' not found after ${max_wait}s — will try connecting anyway"
    return 1
}

connect_to() {
    local con_name="$1"
    local label="$2"
    local is_hotspot="${3:-false}"

    section "Connect to ${label}"

    # Drop current connection
    local active
    active=$(active_connection)
    if [ -n "$active" ] && [ "$active" != "$con_name" ]; then
        info "Dropping ${active}..."
        nmcli con down "$active" 2>/dev/null || true
        sleep 1
    fi

    # For iPhone hotspot, wait for the SSID to appear before connecting.
    # iPhone only broadcasts when the hotspot settings screen is open.
    if [ "$is_hotspot" = true ]; then
        local ssid
        ssid=$(nmcli -t -f connection.id,802-11-wireless.ssid con show "$con_name" 2>/dev/null \
               | grep '^802-11-wireless.ssid:' | cut -d: -f2-)
        [ -z "$ssid" ] && ssid="$con_name"
        wait_for_ssid "$ssid" 30
    else
        info "Scanning..."
        nmcli device wifi rescan 2>/dev/null || true
        sleep 2
    fi

    # Force connect — retry up to 5 times (more for flaky hotspots)
    local max_attempts=5
    [ "$is_hotspot" = false ] && max_attempts=3
    local attempt=1
    while [ "$attempt" -le "$max_attempts" ]; do
        info "Attempt ${attempt}/${max_attempts}: connecting to ${label}..."
        if nmcli con up "$con_name" --wait 20 >/dev/null 2>&1; then
            ok "Connected to ${label}"
            local ip
            if ip=$(wait_for_ip); then
                ok "IP: ${ip}"
                info "Webdash: http://uconsole.local:8080"
            fi
            # Reclaim mDNS hostname after network change
            sudo -n systemctl restart avahi-daemon 2>/dev/null || true
            return 0
        fi
        warn "Attempt ${attempt} failed"
        nmcli device wifi rescan 2>/dev/null || true
        sleep 3
        attempt=$((attempt + 1))
    done

    err "Could not connect after ${max_attempts} attempts"
    if [ "$is_hotspot" = true ]; then
        info "Make sure the iPhone hotspot screen is open and in range"
        info "Also try: Settings > Personal Hotspot > Allow Others to Join"
    else
        info "Make sure the network is available and in range"
    fi
    return 1
}

# ── commands ──

cmd_status() {
    section "WiFi Status"

    local state active ip gw
    state=$(wifi_state)
    active=$(active_connection)

    if [ -n "$active" ]; then
        ok "Connected to: ${active}"
        ip=$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
        gw=$(ip route show default dev "$IFACE" 2>/dev/null | awk '{print $3}')
        [ -n "$ip" ] && info "IP: ${ip}"
        [ -n "$gw" ] && info "Gateway: ${gw}"
        info "Webdash: http://uconsole.local:8080"
    else
        err "Disconnected (state: ${state})"
        info "Run 'wifi.sh iphone' or 'wifi.sh home' to connect"
    fi
}

cmd_scan() {
    section "WiFi Scan"
    nmcli device wifi rescan 2>/dev/null || true
    sleep 2
    nmcli -f SSID,SIGNAL,BARS,SECURITY device wifi list 2>/dev/null
}

cmd_priority() {
    section "Autoconnect Priorities"

    local fmt="  %-25s %4s   %s\n"
    printf "%b${fmt}%b" "$BOLD" "CONNECTION" "PRI" "AUTOCONNECT" "$RESET"
    echo "  ────────────────────────────────────────"

    while IFS=: read -r name autocon pri; do
        # skip non-wifi and loopback
        local type
        type=$(nmcli -t -f connection.type con show "$name" 2>/dev/null | cut -d: -f2)
        [ "$type" != "802-11-wireless" ] && continue

        local label=""
        case "$name" in
            "$HOME_CON")    label="(home)" ;;
            "$OFFICE_CON")  label="(office)" ;;
            "$IPHONE_CON")  label="(iPhone)" ;;
        esac

        local status_color="$GREEN"
        [ "$autocon" = "no" ] && status_color="$RED"

        printf "  %-25s %b%4s%b   %b%-3s%b  %b%s%b\n" \
            "$name" "$CYAN" "${pri:-0}" "$RESET" "$status_color" "$autocon" "$RESET" "$DIM" "$label" "$RESET"
    done < <(nmcli -t -f NAME,AUTOCONNECT,AUTOCONNECT-PRIORITY con show 2>/dev/null)
    echo ""
    info "Higher priority = preferred when multiple are in range"
}

cmd_ip() {
    local ip gw
    ip=$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
    gw=$(ip route show default dev "$IFACE" 2>/dev/null | awk '{print $3}')
    if [ -n "$ip" ]; then
        echo "$ip"
        [ -n "$gw" ] && info "Gateway: ${gw}"
        info "Webdash: http://uconsole.local:8080"
    else
        err "No IP on ${IFACE}"
        exit 1
    fi
}

# ── main ──

case "${1:-}" in
    iphone|phone|i)
        connect_to "$IPHONE_CON" "iPhone" true
        ;;
    home|h)
        connect_to "$HOME_CON" "Home WiFi"
        ;;
    office|o)
        connect_to "$OFFICE_CON" "Office WiFi"
        ;;
    scan|s)
        cmd_scan
        ;;
    ip)
        cmd_ip
        ;;
    priority|p)
        cmd_priority
        ;;
    help|-h|--help)
        echo "Usage: wifi.sh [command]"
        echo ""
        echo "  (none)       Show connection status"
        echo "  iphone, i    Connect to iPhone hotspot"
        echo "  home, h      Connect to home WiFi"
        echo "  office, o    Connect to office WiFi"
        echo "  scan, s      Scan nearby networks"
        echo "  ip           Show current IP and webdash URL"
        echo "  priority, p  Show autoconnect priorities"
        echo "  help         Show this help"
        ;;
    *)
        cmd_status
        ;;
esac
