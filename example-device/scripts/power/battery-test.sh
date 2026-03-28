#!/usr/bin/env bash
# Battery test logger — continuous CSV logging for comparing battery sets
set -euo pipefail

LOG_DIR="$HOME/battery-tests"
INTERVAL="${3:-5}"  # seconds between samples, default 5

BAT="/sys/class/power_supply/axp20x-battery"
AC="/sys/class/power_supply/axp22x-ac"

usage() {
    cat <<'EOF'
Battery Test Logger

Usage: battery-test.sh <command> [options]

Commands:
  start <label>     Start logging (e.g. "nitecore-3400" or "set-A")
  stop              Stop any running test
  status            Show active test info
  list              List all completed tests
  compare           Compare all tests side-by-side (summary)
  export [label]    Print CSV path for a test (all if no label)
  live [label]      Tail the active or named test log
  delete <label>    Delete a test log

Options:
  INTERVAL env or 2nd arg sets sample rate (default: 5s)

Examples:
  battery-test.sh start nitecore-3400
  battery-test.sh start stock-cells 2     # sample every 2s
  battery-test.sh compare
EOF
}

read_sysfs() {
    cat "$1" 2>/dev/null || echo "0"
}

get_sample() {
    local ts voltage_ua current_ua capacity status power_ua charge_rate
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    voltage_ua=$(read_sysfs "$BAT/voltage_now")
    current_ua=$(read_sysfs "$BAT/current_now")
    capacity=$(read_sysfs "$BAT/capacity")
    status=$(read_sysfs "$BAT/status")
    power_ua=$(read_sysfs "$BAT/power_now")
    charge_rate=$(read_sysfs "$BAT/constant_charge_current")

    local voltage_v current_ma power_mw charge_ma
    voltage_v=$(awk "BEGIN {printf \"%.3f\", $voltage_ua / 1000000}")
    current_ma=$(( current_ua / 1000 ))
    power_mw=$(( (voltage_ua / 1000) * (current_ua / 1000) / 1000 ))
    charge_ma=$(( charge_rate / 1000 ))

    echo "$ts,$voltage_v,$current_ma,$power_mw,$capacity,$status,$charge_ma"
}

cmd_start() {
    local label="${1:?Usage: battery-test.sh start <label>}"
    mkdir -p "$LOG_DIR"

    local pidfile="$LOG_DIR/.active.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "ERROR: A test is already running (PID $(cat "$pidfile")). Stop it first."
        exit 1
    fi

    local csv="$LOG_DIR/${label}.csv"
    local is_new=true
    if [ -f "$csv" ]; then
        is_new=false
        echo "Appending to existing test: $csv"
    fi

    echo "Starting battery test: $label"
    echo "Sampling every ${INTERVAL}s → $csv"
    echo "Run 'battery-test.sh stop' to end, or Ctrl+C"

    # Write CSV header if new
    if $is_new; then
        echo "timestamp,voltage_v,current_ma,power_mw,capacity_pct,status,charge_rate_ma" > "$csv"
    fi

    # Record metadata
    cat > "$LOG_DIR/${label}.meta" <<METAEOF
label=$label
started=$(date '+%Y-%m-%d %H:%M:%S')
interval=${INTERVAL}s
METAEOF

    # Background logger
    (
        trap 'exit 0' TERM INT
        while true; do
            get_sample >> "$csv"
            sleep "$INTERVAL"
        done
    ) &
    local pid=$!
    echo "$pid" > "$pidfile"
    echo "$label" > "$LOG_DIR/.active.label"
    echo "Logging started (PID $pid)"

    # Show live output only if running in a terminal
    if [ -t 1 ]; then
        echo ""
        echo "time       | volts | mA    | mW    | cap% | status"
        echo "-----------|-------|-------|-------|------|--------"
        tail -f "$csv" 2>/dev/null | while IFS=, read -r ts v ma mw cap st cr; do
            [ "$ts" = "timestamp" ] && continue
            local t="${ts##* }"
            printf "%s | %s | %5s | %5s | %3s%% | %s\n" "$t" "$v" "$ma" "$mw" "$cap" "$st"
        done
    fi
}

cmd_stop() {
    local pidfile="$LOG_DIR/.active.pid"
    if [ ! -f "$pidfile" ]; then
        echo "No active test."
        return
    fi
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null
        echo "Stopped test (PID $pid)"
    fi
    local label="unknown"
    [ -f "$LOG_DIR/.active.label" ] && label=$(cat "$LOG_DIR/.active.label")
    local csv="$LOG_DIR/${label}.csv"
    local lines=$(( $(wc -l < "$csv") - 1 ))
    local duration=""
    if [ "$lines" -gt 1 ]; then
        local first last
        first=$(sed -n '2p' "$csv" | cut -d, -f1)
        last=$(tail -1 "$csv" | cut -d, -f1)
        duration="$first → $last"
    fi
    echo "Test '$label': $lines samples"
    [ -n "$duration" ] && echo "Duration: $duration"
    echo "CSV: $csv"
    rm -f "$pidfile" "$LOG_DIR/.active.label"
}

cmd_status() {
    local pidfile="$LOG_DIR/.active.pid"
    if [ ! -f "$pidfile" ] || ! kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "No active test."
        return
    fi
    local label
    label=$(cat "$LOG_DIR/.active.label" 2>/dev/null || echo "unknown")
    local csv="$LOG_DIR/${label}.csv"
    local lines=$(( $(wc -l < "$csv") - 1 ))
    local latest
    latest=$(tail -1 "$csv")
    echo "Active test: $label (PID $(cat "$pidfile"))"
    echo "Samples: $lines"
    echo "Latest: $latest"
}

cmd_list() {
    mkdir -p "$LOG_DIR"
    local found=false
    for csv in "$LOG_DIR"/*.csv; do
        [ -f "$csv" ] || continue
        found=true
        local name
        name=$(basename "$csv" .csv)
        local lines=$(( $(wc -l < "$csv") - 1 ))
        local first last
        first=$(sed -n '2p' "$csv" | cut -d, -f1)
        last=$(tail -1 "$csv" | cut -d, -f1)
        # Get voltage range
        local vmin vmax
        vmin=$(tail -n +2 "$csv" | cut -d, -f2 | sort -n | head -1)
        vmax=$(tail -n +2 "$csv" | cut -d, -f2 | sort -n | tail -1)
        printf "%-20s %5d samples  %sV–%sV  %s → %s\n" "$name" "$lines" "$vmin" "$vmax" "$first" "$last"
    done
    if ! $found; then
        echo "No tests yet. Run: battery-test.sh start <label>"
    fi
}

cmd_compare() {
    mkdir -p "$LOG_DIR"
    echo "── Battery Test Comparison ──"
    echo ""
    printf "%-20s │ %5s │ %6s │ %6s │ %6s │ %5s │ %s\n" \
        "Test" "Smpls" "V max" "V min" "V drop" "Cap%" "Duration"
    printf "%.0s─" {1..85}
    echo ""

    for csv in "$LOG_DIR"/*.csv; do
        [ -f "$csv" ] || continue
        local name
        name=$(basename "$csv" .csv)
        python3 -c "
import csv, sys
with open('$csv') as f:
    rows = list(csv.DictReader(f))
if not rows:
    sys.exit()
voltages = [float(r['voltage_v']) for r in rows]
caps = [int(r['capacity_pct']) for r in rows]
vmax = max(voltages)
vmin = min(voltages)
vdrop = round(vmax - vmin, 3)
cap_start = caps[0]
cap_end = caps[-1]
cap_str = '{}→{}'.format(cap_start, cap_end)
t0 = rows[0]['timestamp']
t1 = rows[-1]['timestamp']
# duration
from datetime import datetime
try:
    d = datetime.strptime(t1, '%Y-%m-%d %H:%M:%S') - datetime.strptime(t0, '%Y-%m-%d %H:%M:%S')
    hrs = d.total_seconds() / 3600
    dur = '{:.1f}h'.format(hrs) if hrs >= 1 else '{:.0f}m'.format(d.total_seconds()/60)
except: dur = '--'
print('{:<20s} │ {:>5d} │ {:>6.3f} │ {:>6.3f} │ {:>6.3f} │ {:>5s} │ {}'.format(
    '$name', len(rows), vmax, vmin, vdrop, cap_str, dur))
"
    done
}

cmd_export() {
    local label="${1:-}"
    if [ -n "$label" ]; then
        local csv="$LOG_DIR/${label}.csv"
        [ -f "$csv" ] && echo "$csv" || echo "Not found: $csv"
    else
        ls "$LOG_DIR"/*.csv 2>/dev/null || echo "No tests found."
    fi
}

cmd_live() {
    local label="${1:-}"
    if [ -z "$label" ] && [ -f "$LOG_DIR/.active.label" ]; then
        label=$(cat "$LOG_DIR/.active.label")
    fi
    local csv="$LOG_DIR/${label}.csv"
    if [ ! -f "$csv" ]; then
        echo "No test found: $label"
        exit 1
    fi
    echo "── Live: $label ──"
    echo "time       | volts | mA    | mW    | cap% | status"
    echo "-----------|-------|-------|-------|------|--------"
    tail -f "$csv" 2>/dev/null | while IFS=, read -r ts v ma mw cap st cr; do
        [ "$ts" = "timestamp" ] && continue
        local t="${ts##* }"
        printf "%s | %s | %5s | %5s | %3s%% | %s\n" "$t" "$v" "$ma" "$mw" "$cap" "$st"
    done
}

cmd_delete() {
    local label="${1:?Usage: battery-test.sh delete <label>}"
    rm -f "$LOG_DIR/${label}.csv" "$LOG_DIR/${label}.meta"
    echo "Deleted: $label"
}

case "${1:-help}" in
    start)   cmd_start "${2:-}" ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    list)    cmd_list ;;
    compare) cmd_compare ;;
    export)  cmd_export "${2:-}" ;;
    live)    cmd_live "${2:-}" ;;
    delete)  cmd_delete "${2:-}" ;;
    -h|--help|help) usage ;;
    *) echo "Unknown: $1"; usage; exit 1 ;;
esac
