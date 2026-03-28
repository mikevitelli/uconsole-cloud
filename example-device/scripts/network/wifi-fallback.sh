#!/bin/bash
# WiFi fallback dispatcher for the uConsole.
# Toggleable NetworkManager dispatcher that handles reconnection and mDNS.
#
# Fallback chain (on connectivity loss):
#   1. Try iPhone hotspot (wait for SSID, retry up to 3x)
#   2. If iPhone not found → start local AP (hotspot.sh on)
#   3. AP gives phone→uConsole LAN for webdash, no internet
#
# Usage (direct):
#   wifi-fallback.sh              Show status
#   wifi-fallback.sh on|enable    Enable fallback dispatcher
#   wifi-fallback.sh off|disable  Disable fallback dispatcher
#   wifi-fallback.sh toggle       Toggle on/off
#   wifi-fallback.sh log          Show recent fallback log entries
#   wifi-fallback.sh install      Symlink into NetworkManager dispatcher.d
#   wifi-fallback.sh uninstall    Remove symlink
#
# Usage (NetworkManager dispatcher — called automatically):
#   wifi-fallback.sh <interface> <action>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/wifi-fallback"
STATE_FILE="$STATE_DIR/enabled"
COOLDOWN_FILE="$STATE_DIR/last_action"
COOLDOWN_SECS=30
IFACE="wlan0"
LOG_TAG="wifi-fallback"
DISPATCHER_LINK="/etc/NetworkManager/dispatcher.d/90-wifi-fallback"
IPHONE_CON="MyHotspot"
HOTSPOT_SCRIPT="$SCRIPT_DIR/hotspot.sh"
IPHONE_SSID_WAIT=15
IPHONE_RETRIES=3

# ── helpers ──

log() { logger -t "$LOG_TAG" "$1"; }

is_enabled() { [ -L "$STATE_FILE" ] && { log "ERROR: state file is symlink"; return 1; }; [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE" 2>/dev/null)" = "1" ]; }

cooldown_ok() {
    [ ! -f "$COOLDOWN_FILE" ] && return 0
    local last now
    last=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
    [[ "$last" =~ ^[0-9]+$ ]] || last=0
    now=$(date +%s)
    [ $((now - last)) -ge $COOLDOWN_SECS ]
}

stamp_cooldown() {
    mkdir -p "$STATE_DIR"
    [ -L "$COOLDOWN_FILE" ] && { log "ERROR: cooldown file is symlink"; return 1; }
    date +%s > "$COOLDOWN_FILE"
}

active_connection() {
    nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep ":${IFACE}$" | cut -d: -f1
}

try_iphone_hotspot() {
    log "trying iPhone hotspot (wait ${IPHONE_SSID_WAIT}s for SSID, ${IPHONE_RETRIES} retries)"

    # Get the SSID for this connection profile
    local ssid
    ssid=$(nmcli -t -f 802-11-wireless.ssid con show "$IPHONE_CON" 2>/dev/null \
           | sed 's/^802-11-wireless.ssid://')
    [ -z "$ssid" ] && ssid="$IPHONE_CON"

    # Wait for SSID to appear (iPhone only broadcasts when hotspot screen is open)
    local elapsed=0
    while [ "$elapsed" -lt "$IPHONE_SSID_WAIT" ]; do
        nmcli device wifi rescan 2>/dev/null || true
        sleep 3
        elapsed=$((elapsed + 3))
        if nmcli -t -f SSID device wifi list 2>/dev/null | grep -qxF "$ssid"; then
            log "iPhone SSID found after ${elapsed}s"
            break
        fi
    done

    # Try connecting with retries
    local attempt=1
    while [ "$attempt" -le "$IPHONE_RETRIES" ]; do
        log "iPhone connect attempt ${attempt}/${IPHONE_RETRIES}"
        if nmcli con up "$IPHONE_CON" --wait 15 2>/dev/null; then
            log "connected to iPhone hotspot"
            return 0
        fi
        nmcli device wifi rescan 2>/dev/null || true
        sleep 2
        attempt=$((attempt + 1))
    done

    log "iPhone hotspot failed after ${IPHONE_RETRIES} attempts"
    return 1
}

# ── universal fallback chain ──
# Called on any disconnect or connectivity loss.
# 1. iPhone hotspot  2. Saved networks  3. AP mode
run_fallback_chain() {
    # Kill AP if running (frees wlan0)
    if [ -x "$HOTSPOT_SCRIPT" ] && nmcli -t -f NAME con show --active 2>/dev/null | grep -q "^Hotspot"; then
        log "stopping AP to free wlan0"
        bash "$HOTSPOT_SCRIPT" off 2>/dev/null || true
        sleep 2
    fi

    nmcli device wifi rescan 2>/dev/null || true
    sleep 2

    # Step 1: iPhone hotspot (cellular)
    if try_iphone_hotspot; then
        return 0
    fi

    # Step 2: Any saved network (NM picks by priority)
    log "trying saved networks"
    if nmcli device connect "$IFACE" --wait 15 2>/dev/null; then
        local con
        con=$(active_connection)
        log "connected to saved network: ${con:-unknown}"
        return 0
    fi

    # Step 3: No networks available — log and stop
    log "no networks available — use hotspot toggle to start AP manually"
}

# ── NetworkManager dispatcher mode ──
# NM passes: $1=interface $2=action

dispatch() {
    local iface="$1" action="$2"

    # Prevent concurrent event races
    local lock_file="$STATE_DIR/.lock"
    [ "$(id -u)" -eq 0 ] && lock_file="/run/wifi-fallback.lock"
    exec 9>"$lock_file"
    flock -n 9 || return 0

    # Only act on wlan0
    [ "$iface" = "$IFACE" ] || return 0

    # When running as root (dispatcher mode), verify STATE_DIR is safe
    if [ "$(id -u)" -eq 0 ]; then
        if [ -L "$STATE_DIR" ]; then
            log "ERROR: STATE_DIR is a symlink — refusing to continue"
            return 1
        fi
        local dir_owner
        dir_owner=$(stat -c %U "$STATE_DIR" 2>/dev/null)
        local expected_owner
        expected_owner=$(whoami 2>/dev/null || echo "root")
        if [ "${dir_owner:-}" != "$expected_owner" ] && [ "${dir_owner:-}" != "root" ]; then
            log "ERROR: STATE_DIR not owned by $expected_owner (owner: ${dir_owner:-unknown})"
            return 1
        fi
    fi

    # Bail if disabled
    is_enabled || return 0

    case "$action" in
        down)
            log "wlan0 disconnected — running fallback chain"
            cooldown_ok || return 0
            stamp_cooldown
            run_fallback_chain
            ;;
        up)
            local con
            con=$(active_connection)
            con="${con//[^a-zA-Z0-9 ._-]/}"
            log "wlan0 connected: ${con:-unknown}"
            # Reclaim mDNS hostname after any network change
            if [ "$(id -u)" -eq 0 ]; then
                systemctl restart avahi-daemon 2>/dev/null || true
            else
                sudo -n systemctl restart avahi-daemon 2>/dev/null || true
            fi
            ;;
        connectivity-change)
            local state
            state=$(nmcli -t -f CONNECTIVITY general 2>/dev/null | head -1)
            [ "$state" = "none" ] || return 0
            cooldown_ok || return 0

            # If something is still connected, don't fight it
            local active
            active=$(active_connection)
            [ -z "$active" ] || return 0

            log "connectivity lost — running fallback chain"
            stamp_cooldown
            run_fallback_chain
            ;;
    esac
}

# ── direct subcommands ──

# Source lib.sh only for direct invocation (not dispatcher mode)
source_lib() {
    if [ -f "$SCRIPT_DIR/lib.sh" ]; then
        source "$SCRIPT_DIR/lib.sh"
    fi
}

cmd_status() {
    source_lib
    section "WiFi Fallback"
    if is_enabled; then
        ok "Fallback: enabled"
    else
        err "Fallback: disabled"
    fi
    if [ -L "$DISPATCHER_LINK" ]; then
        ok "Dispatcher: installed"
    else
        warn "Dispatcher: not installed (run: wifi-fallback.sh install)"
    fi
    if [ -f "$COOLDOWN_FILE" ]; then
        local last elapsed
        last=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
        elapsed=$(( $(date +%s) - last ))
        info "Last action: ${elapsed}s ago"
    fi
}

cmd_enable() {
    source_lib
    mkdir -p "$STATE_DIR"
    echo "1" > "$STATE_FILE"
    log "fallback enabled"
    ok "WiFi fallback enabled"
}

cmd_disable() {
    source_lib
    mkdir -p "$STATE_DIR"
    echo "0" > "$STATE_FILE"
    log "fallback disabled"
    ok "WiFi fallback disabled"
}

cmd_toggle() {
    if is_enabled; then
        cmd_disable
    else
        cmd_enable
    fi
}

cmd_log() {
    source_lib
    section "WiFi Fallback Log"
    journalctl -t "$LOG_TAG" --no-pager -n 25 2>/dev/null || \
        warn "No log entries found"
}

cmd_install() {
    source_lib
    local self
    self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

    # Validate that self resolves within the expected scripts directory
    case "$self" in
        /opt/uconsole/scripts/*|/home/*/scripts/*)
            ;;
        *)
            err "Refusing to install: script path '$self' is outside expected directories"
            return 1
            ;;
    esac

    # Check if a regular file (not symlink) already exists at the destination
    if [ -e "$DISPATCHER_LINK" ] && [ ! -L "$DISPATCHER_LINK" ]; then
        err "Regular file already exists at $DISPATCHER_LINK — refusing to overwrite"
        return 1
    fi

    if [ -L "$DISPATCHER_LINK" ]; then
        ok "Already installed at $DISPATCHER_LINK"
        return 0
    fi
    sudo ln -sf "$self" "$DISPATCHER_LINK"
    sudo chmod +x "$DISPATCHER_LINK"
    ok "Installed dispatcher: $DISPATCHER_LINK -> $self"
    log "dispatcher installed"
}

cmd_uninstall() {
    source_lib
    if [ ! -L "$DISPATCHER_LINK" ]; then
        warn "No dispatcher symlink at $DISPATCHER_LINK"
        return 0
    fi
    sudo rm -f "$DISPATCHER_LINK"
    ok "Removed dispatcher symlink"
    log "dispatcher uninstalled"
}

# ── main ──

# Detect dispatcher mode: NM calls with exactly 2 positional args
# where $1 looks like an interface name and $2 is a known NM action
if [ $# -eq 2 ]; then
    case "$2" in
        up|down|pre-up|pre-down|connectivity-change|dhcp4-change|dhcp6-change|hostname|reapply)
            dispatch "$1" "$2"
            exit 0
            ;;
    esac
fi

# Direct invocation mode
case "${1:-}" in
    on|enable)    cmd_enable ;;
    off|disable)  cmd_disable ;;
    toggle)       cmd_toggle ;;
    log)          cmd_log ;;
    install)      cmd_install ;;
    uninstall)    cmd_uninstall ;;
    help|-h|--help)
        echo "Usage: wifi-fallback.sh [command]"
        echo ""
        echo "  (none)       Show status"
        echo "  on|enable    Enable fallback dispatcher"
        echo "  off|disable  Disable fallback dispatcher"
        echo "  toggle       Toggle on/off"
        echo "  log          Show recent log entries"
        echo "  install      Symlink into NM dispatcher.d"
        echo "  uninstall    Remove dispatcher symlink"
        ;;
    *)            cmd_status ;;
esac
