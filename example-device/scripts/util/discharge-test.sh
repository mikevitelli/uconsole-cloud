#!/bin/bash
# Overnight battery discharge test
# Logs battery stats every 30s, pushes to GitHub every 15 minutes
# Run: nohup bash scripts/discharge-test.sh &

source "$(dirname "$0")/lib.sh"

LOG_FILE="$HOME/discharge-test.log"
PUSH_INTERVAL=900  # 15 minutes in seconds
SAMPLE_INTERVAL=30

last_push=$(date +%s)

header="timestamp | capacity% | vest% | voltage_V | current_mA | power_mW | status | cpu_temp_C | uptime_s"

# Start fresh log
echo "# Discharge Test — started $(date '+%Y-%m-%d %H:%M:%S')" > "$LOG_FILE"
echo "# Cells: Nitecore NL1834 3400mAh x2" >> "$LOG_FILE"
echo "# $header" >> "$LOG_FILE"

log_entry() {
    read_battery
    local temp
    temp=$(awk '{printf "%.1f", $0/1000}' /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "?")
    local up
    up=$(awk '{print int($1)}' /proc/uptime)

    # voltage-based capacity estimate — Nitecore NL1834 measured curve (2026-03-27)
    local vest
    if [ "$BAT_VOLTAGE_UA" -le 3000000 ]; then
        vest=0
    elif [ "$BAT_VOLTAGE_UA" -ge 4050000 ]; then
        vest=100
    else
        vest=$(awk "BEGIN {
            v = $BAT_VOLTAGE_UA / 1000000
            if (v < 3.1) printf \"%d\", (v - 3.0) / 0.1 * 15
            else if (v < 3.2) printf \"%d\", 15 + (v - 3.1) / 0.1 * 35
            else if (v < 3.3) printf \"%d\", 50 + (v - 3.2) / 0.1 * 10
            else if (v < 3.4) printf \"%d\", 60 + (v - 3.3) / 0.1 * 10
            else if (v < 3.6) printf \"%d\", 70 + (v - 3.4) / 0.2 * 10
            else if (v < 3.8) printf \"%d\", 80 + (v - 3.6) / 0.2 * 10
            else printf \"%d\", 90 + (v - 3.8) / 0.25 * 10
        }")
    fi

    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$ts | ${BAT_CAPACITY}% | ${vest}% | ${BAT_VOLTAGE_V}V | ${BAT_CURRENT_MA}mA | ${BAT_POWER_MW}mW | $BAT_STATUS | ${temp}C | ${up}s" >> "$LOG_FILE"
}

push_to_github() {
    cd "$HOME" || return
    git add discharge-test.log 2>/dev/null
    git commit -m "discharge-test: $(date '+%H:%M') — $(cat /sys/class/power_supply/axp20x-battery/capacity 2>/dev/null || echo '?')%" --no-gpg-sign 2>/dev/null
    git push origin main 2>/dev/null
    last_push=$(date +%s)
}

echo "[discharge-test] Starting — logging every ${SAMPLE_INTERVAL}s, pushing every $((PUSH_INTERVAL/60))m"
echo "[discharge-test] Log: $LOG_FILE"
echo "[discharge-test] Unplug AC when ready"

# Initial snapshot
log_entry
push_to_github

while true; do
    sleep "$SAMPLE_INTERVAL"
    log_entry

    # Push on interval
    now=$(date +%s)
    if [ $((now - last_push)) -ge "$PUSH_INTERVAL" ]; then
        push_to_github
    fi
done
