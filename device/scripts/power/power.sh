#!/bin/bash
# Power management for the uConsole
# Usage: power.sh reboot      Reboot the system
#        power.sh shutdown    Power off the system
#        power.sh status      Show current power state

source "$(dirname "$0")/lib.sh"

BACKLIGHT="/sys/class/backlight/backlight@0"

get_brightness() {
    cat "$BACKLIGHT/brightness" 2>/dev/null || echo "?"
}

get_max_brightness() {
    cat "$BACKLIGHT/max_brightness" 2>/dev/null || echo "9"
}

cmd_status() {
    section "Power Status"

    local brightness max_brightness
    brightness=$(get_brightness)
    max_brightness=$(get_max_brightness)

    if [ "$brightness" = "0" ]; then
        info "Screen: OFF"
    else
        info "Screen: ON (brightness $brightness/$max_brightness)"
    fi

    # battery (from lib.sh)
    read_battery
    info "Battery: ${BAT_CAPACITY}% ($BAT_STATUS)"

    # ac
    [ "$BAT_AC_ONLINE" = "1" ] && info "AC: connected" || info "AC: disconnected"

    # uptime
    local up_secs days hours mins
    up_secs=$(awk '{print int($1)}' /proc/uptime)
    days=$((up_secs / 86400))
    hours=$(( (up_secs % 86400) / 3600 ))
    mins=$(( (up_secs % 3600) / 60 ))
    if [ "$days" -gt 0 ]; then
        info "Uptime: ${days}d ${hours}h ${mins}m"
    else
        info "Uptime: ${hours}h ${mins}m"
    fi
}

cmd_reboot() {
    section "Reboot"
    warn "Rebooting in 3 seconds..."
    sleep 3
    sudo systemctl reboot
}

cmd_shutdown() {
    section "Shutdown"
    warn "Shutting down in 3 seconds..."
    sleep 3
    sudo systemctl poweroff
}

# ── main ──

case "${1:-}" in
    reboot)     cmd_reboot ;;
    shutdown)   cmd_shutdown ;;
    status)     cmd_status ;;
    *)
        echo "Usage: power.sh {reboot|shutdown|status}"
        echo ""
        echo "  reboot      Reboot (3s delay)"
        echo "  shutdown    Power off (3s delay)"
        echo "  status      Show power state"
        ;;
esac
