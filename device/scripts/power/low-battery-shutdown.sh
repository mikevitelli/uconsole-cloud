#!/bin/bash
# Graceful low-battery shutdown daemon
# Monitors battery voltage and triggers clean shutdown before PMU hard cutoff
#
# The AXP228 PMU hard-kills power at 2.9V (V_OFF). This script shuts down
# cleanly at 3.2V, giving the OS time to flush writes and unmount filesystems.
#
# Usage:
#   low-battery-shutdown.sh          Run in foreground (for systemd)
#   low-battery-shutdown.sh status   Show current voltage and threshold

THRESHOLD_UV=3050000   # 3.05V — trigger graceful shutdown (Nitecore NL1834 has ~15% at 3.1V)
CRITICAL_UV=2950000    # 2.95V — skip warning delay, shutdown immediately (PMU hard-kills at 2.9V)
POLL_INTERVAL=30       # seconds between checks
CONFIRM_COUNT=3        # require N consecutive readings below threshold (avoids transient sag)
VOLTAGE_PATH="/sys/class/power_supply/axp20x-battery/voltage_now"
AC_PATH="/sys/class/power_supply/axp22x-ac/online"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') low-battery: $1"; }

cmd_status() {
    local voltage_uv ac_online voltage_v threshold_v
    voltage_uv=$(cat "$VOLTAGE_PATH" 2>/dev/null || echo 0)
    ac_online=$(cat "$AC_PATH" 2>/dev/null || echo 0)
    voltage_v=$(awk "BEGIN {printf \"%.3f\", $voltage_uv / 1000000}")
    threshold_v=$(awk "BEGIN {printf \"%.1f\", $THRESHOLD_UV / 1000000}")

    echo "Voltage:   ${voltage_v}V"
    echo "Threshold: ${threshold_v}V"
    echo "AC power:  $([ "$ac_online" = "1" ] && echo "connected" || echo "disconnected")"

    if [ "$ac_online" = "1" ]; then
        echo "Status:    safe (on AC)"
    elif [ "$voltage_uv" -le "$THRESHOLD_UV" ]; then
        echo "Status:    LOW — would trigger shutdown"
    else
        local headroom=$((voltage_uv - THRESHOLD_UV))
        local headroom_mv=$((headroom / 1000))
        echo "Status:    OK (${headroom_mv}mV above threshold)"
    fi
}

cmd_daemon() {
    log "started — threshold=${THRESHOLD_UV}uV, poll=${POLL_INTERVAL}s, confirm=${CONFIRM_COUNT}"

    local low_count=0

    while true; do
        sleep "$POLL_INTERVAL"

        # skip check if on AC power
        local ac_online
        ac_online=$(cat "$AC_PATH" 2>/dev/null || echo "0")
        if [ "$ac_online" = "1" ]; then
            low_count=0
            continue
        fi

        local voltage_uv
        voltage_uv=$(cat "$VOLTAGE_PATH" 2>/dev/null || echo "0")

        # critical — skip confirmation, shutdown now
        if [ "$voltage_uv" -gt 0 ] && [ "$voltage_uv" -le "$CRITICAL_UV" ]; then
            log "CRITICAL ${voltage_uv}uV — immediate shutdown"
            wall "Battery critical ($(awk "BEGIN {printf \"%.2f\", $voltage_uv / 1000000}")V) — shutting down NOW"
            sync
            systemctl poweroff
            exit 0
        fi

        # below threshold — increment counter
        if [ "$voltage_uv" -gt 0 ] && [ "$voltage_uv" -le "$THRESHOLD_UV" ]; then
            low_count=$((low_count + 1))
            log "low voltage ${voltage_uv}uV (${low_count}/${CONFIRM_COUNT})"

            if [ "$low_count" -ge "$CONFIRM_COUNT" ]; then
                log "SHUTDOWN — ${low_count} consecutive readings below ${THRESHOLD_UV}uV"
                wall "Battery low ($(awk "BEGIN {printf \"%.2f\", $voltage_uv / 1000000}")V) — shutting down in 10s"
                sleep 10
                sync
                systemctl poweroff
                exit 0
            fi
        else
            # voltage recovered (transient sag or AC plugged in)
            if [ "$low_count" -gt 0 ]; then
                log "voltage recovered to ${voltage_uv}uV — reset counter"
            fi
            low_count=0
        fi
    done
}

case "${1:-}" in
    status) cmd_status ;;
    *)      cmd_daemon ;;
esac
