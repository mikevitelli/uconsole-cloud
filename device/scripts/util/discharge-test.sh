#!/bin/bash
# Overnight battery discharge test
# Logs battery stats every 30s, pushes to GitHub every 15 minutes
# Run: nohup bash scripts/discharge-test.sh <cell-type> &

source "$(dirname "$0")/lib.sh"

SAMPLE_INTERVAL=30
PUSH_INTERVAL=900  # 15 minutes in seconds

# ── cell profiles: label, mAh, voltage-estimate function ──

declare -A CELL_LABEL CELL_MAH
CELL_LABEL[nitecore-3400]="Nitecore NL1834"
CELL_MAH[nitecore-3400]=3400
CELL_LABEL[samsung-35e]="Samsung INR18650-35E"
CELL_MAH[samsung-35e]=3500
CELL_LABEL[samsung-30q]="Samsung INR18650-30Q"
CELL_MAH[samsung-30q]=3000
CELL_LABEL[panasonic-ga]="Panasonic NCR18650GA"
CELL_MAH[panasonic-ga]=3450

vest_nitecore_3400() {
    awk "BEGIN {
        v = $1 / 1000000
        if (v <= 3.0)      printf \"%d\", 0
        else if (v >= 4.05) printf \"%d\", 100
        else if (v < 3.1)  printf \"%d\", (v - 3.0) / 0.1 * 15
        else if (v < 3.2)  printf \"%d\", 15 + (v - 3.1) / 0.1 * 35
        else if (v < 3.3)  printf \"%d\", 50 + (v - 3.2) / 0.1 * 10
        else if (v < 3.4)  printf \"%d\", 60 + (v - 3.3) / 0.1 * 10
        else if (v < 3.6)  printf \"%d\", 70 + (v - 3.4) / 0.2 * 10
        else if (v < 3.8)  printf \"%d\", 80 + (v - 3.6) / 0.2 * 10
        else               printf \"%d\", 90 + (v - 3.8) / 0.25 * 10
    }"
}

vest_samsung_35e() {
    # Samsung 35E: flatter mid-curve, steeper drop below 3.2V
    awk "BEGIN {
        v = $1 / 1000000
        if (v <= 2.9)       printf \"%d\", 0
        else if (v >= 4.10) printf \"%d\", 100
        else if (v < 3.0)   printf \"%d\", (v - 2.9) / 0.1 * 5
        else if (v < 3.2)   printf \"%d\", 5 + (v - 3.0) / 0.2 * 10
        else if (v < 3.4)   printf \"%d\", 15 + (v - 3.2) / 0.2 * 25
        else if (v < 3.6)   printf \"%d\", 40 + (v - 3.4) / 0.2 * 25
        else if (v < 3.8)   printf \"%d\", 65 + (v - 3.6) / 0.2 * 15
        else                 printf \"%d\", 80 + (v - 3.8) / 0.3 * 20
    }"
}

vest_samsung_30q() {
    # Samsung 30Q: higher-drain cell, slightly steeper overall curve
    awk "BEGIN {
        v = $1 / 1000000
        if (v <= 2.8)       printf \"%d\", 0
        else if (v >= 4.10) printf \"%d\", 100
        else if (v < 3.0)   printf \"%d\", (v - 2.8) / 0.2 * 5
        else if (v < 3.2)   printf \"%d\", 5 + (v - 3.0) / 0.2 * 15
        else if (v < 3.4)   printf \"%d\", 20 + (v - 3.2) / 0.2 * 25
        else if (v < 3.6)   printf \"%d\", 45 + (v - 3.4) / 0.2 * 20
        else if (v < 3.8)   printf \"%d\", 65 + (v - 3.6) / 0.2 * 15
        else                 printf \"%d\", 80 + (v - 3.8) / 0.3 * 20
    }"
}

vest_panasonic_ga() {
    # Panasonic GA: very flat 3.3-3.6V plateau
    awk "BEGIN {
        v = $1 / 1000000
        if (v <= 2.8)       printf \"%d\", 0
        else if (v >= 4.10) printf \"%d\", 100
        else if (v < 3.0)   printf \"%d\", (v - 2.8) / 0.2 * 5
        else if (v < 3.2)   printf \"%d\", 5 + (v - 3.0) / 0.2 * 15
        else if (v < 3.3)   printf \"%d\", 20 + (v - 3.2) / 0.1 * 15
        else if (v < 3.6)   printf \"%d\", 35 + (v - 3.3) / 0.3 * 35
        else if (v < 3.8)   printf \"%d\", 70 + (v - 3.6) / 0.2 * 15
        else                 printf \"%d\", 85 + (v - 3.8) / 0.3 * 15
    }"
}

vest_generic() {
    # Linear fallback for unknown cells
    awk "BEGIN {
        v = $1 / 1000000
        if (v <= 3.0)      printf \"%d\", 0
        else if (v >= 4.2) printf \"%d\", 100
        else               printf \"%d\", (v - 3.0) / 1.2 * 100
    }"
}

voltage_estimate() {
    local cell="$1" voltage_ua="$2"
    case "$cell" in
        nitecore-3400) vest_nitecore_3400 "$voltage_ua" ;;
        samsung-35e)   vest_samsung_35e "$voltage_ua" ;;
        samsung-30q)   vest_samsung_30q "$voltage_ua" ;;
        panasonic-ga)  vest_panasonic_ga "$voltage_ua" ;;
        *)             vest_generic "$voltage_ua" ;;
    esac
}

# ── usage ──

usage() {
    cat <<'EOF'
Overnight Battery Discharge Test

Usage: discharge-test.sh <cell-type> [interval]

Cell types:
  nitecore-3400    Nitecore NL1834 3400mAh (control)
  samsung-35e      Samsung INR18650-35E 3500mAh
  samsung-30q      Samsung INR18650-30Q 3000mAh
  panasonic-ga     Panasonic NCR18650GA 3450mAh
  <custom>         Any label (uses generic voltage curve)

Options:
  interval         Sample interval in seconds (default: 30)

Examples:
  discharge-test.sh samsung-35e
  discharge-test.sh samsung-35e 10
  nohup discharge-test.sh samsung-35e &
EOF
}

# ── parse args ──

CELL="${1:-}"
if [ -z "$CELL" ] || [ "$CELL" = "-h" ] || [ "$CELL" = "--help" ]; then
    usage
    exit 0
fi

SAMPLE_INTERVAL="${2:-$SAMPLE_INTERVAL}"

CELL_NAME="${CELL_LABEL[$CELL]:-$CELL}"
CELL_CAPACITY="${CELL_MAH[$CELL]:-?}"

LOG_FILE="$HOME/battery-tests/discharge-${CELL}.log"
mkdir -p "$HOME/battery-tests"

# ── logging ──

log_entry() {
    read_battery
    local temp
    temp=$(awk '{printf "%.1f", $0/1000}' /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "?")
    local up
    up=$(awk '{print int($1)}' /proc/uptime)

    local vest
    vest=$(voltage_estimate "$CELL" "$BAT_VOLTAGE_UA")

    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$ts | ${BAT_CAPACITY}% | ${vest}% | ${BAT_VOLTAGE_V}V | ${BAT_CURRENT_MA}mA | ${BAT_POWER_MW}mW | $BAT_STATUS | ${temp}C | ${up}s" >> "$LOG_FILE"
}

push_to_github() {
    cd "$HOME" || return
    git add "battery-tests/discharge-${CELL}.log" 2>/dev/null
    git commit -m "discharge-test(${CELL}): $(date '+%H:%M') — $(cat /sys/class/power_supply/axp20x-battery/capacity 2>/dev/null || echo '?')%" --no-gpg-sign 2>/dev/null
    git push origin main 2>/dev/null
    last_push=$(date +%s)
}

# ── start ──

header="timestamp | capacity% | vest% | voltage_V | current_mA | power_mW | status | cpu_temp_C | uptime_s"

echo "# Discharge Test — started $(date '+%Y-%m-%d %H:%M:%S')" > "$LOG_FILE"
echo "# Cells: ${CELL_NAME} ${CELL_CAPACITY}mAh x2" >> "$LOG_FILE"
echo "# $header" >> "$LOG_FILE"

last_push=$(date +%s)

echo "[discharge-test] Starting — ${CELL_NAME} ${CELL_CAPACITY}mAh"
echo "[discharge-test] Logging every ${SAMPLE_INTERVAL}s, pushing every $((PUSH_INTERVAL/60))m"
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
