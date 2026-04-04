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
  chart [label]     ASCII voltage curve (all tests, or one)
  health [label]    Capacity estimate and health analysis
  stress <label>    Start logging under CPU stress load
  calibrate         Guided fuel gauge calibration cycle
  export [label]    Print CSV path for a test (all if no label)
  live [label]      Tail the active or named test log
  delete <label>    Delete a test log

Options:
  INTERVAL env or 2nd arg sets sample rate (default: 5s)

Examples:
  battery-test.sh start nitecore-3400
  battery-test.sh start stock-cells 2     # sample every 2s
  battery-test.sh chart
  battery-test.sh health samsung-35e
  battery-test.sh stress samsung-35e
  battery-test.sh calibrate
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

    local voltage_v current_ma power_mw charge_ma temp
    voltage_v=$(awk "BEGIN {printf \"%.3f\", $voltage_ua / 1000000}")
    current_ma=$(( current_ua / 1000 ))
    power_mw=$(( (voltage_ua / 1000) * (current_ua / 1000) / 1000 ))
    charge_ma=$(( charge_rate / 1000 ))
    temp=$(awk '{printf "%.1f", $0/1000}' /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "0")

    echo "$ts,$voltage_v,$current_ma,$power_mw,$capacity,$status,$charge_ma,$temp"
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
        echo "timestamp,voltage_v,current_ma,power_mw,capacity_pct,status,charge_rate_ma,temp_c" > "$csv"
    fi

    # Record metadata
    cat > "$LOG_DIR/${label}.meta" <<METAEOF
label=$label
started=$(date '+%Y-%m-%d %H:%M:%S')
interval=${INTERVAL}s
METAEOF

    # Background logger (disown so it survives terminal close)
    (
        trap 'exit 0' TERM INT HUP
        while true; do
            get_sample >> "$csv"
            sleep "$INTERVAL"
        done
    ) &
    local pid=$!
    disown "$pid"
    echo "$pid" > "$pidfile"
    echo "$label" > "$LOG_DIR/.active.label"
    echo "Logging started (PID $pid)"

    # Show live output only if running in a terminal
    if [ -t 1 ]; then
        echo ""
        echo "time       | volts | mA    | mW    | cap% | status     | temp"
        echo "-----------|-------|-------|-------|------|------------|------"
        tail -f "$csv" 2>/dev/null | while IFS=, read -r ts v ma mw cap st cr tmp; do
            [ "$ts" = "timestamp" ] && continue
            local t="${ts##* }"
            printf "%s | %s | %5s | %5s | %3s%% | %-10s | %s\n" "$t" "$v" "$ma" "$mw" "$cap" "$st" "${tmp:-}"
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
    if [ ! -f "$csv" ]; then
        echo "Test '$label': no data"
        rm -f "$pidfile" "$LOG_DIR/.active.label"
        return
    fi
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
    # Also stop any stress process
    if [ -f "$LOG_DIR/.stress.pid" ]; then
        local spid
        spid=$(cat "$LOG_DIR/.stress.pid")
        kill "$spid" 2>/dev/null && echo "Stopped stress load (PID $spid)"
        rm -f "$LOG_DIR/.stress.pid"
    fi
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
    if [ -f "$LOG_DIR/.stress.pid" ] && kill -0 "$(cat "$LOG_DIR/.stress.pid")" 2>/dev/null; then
        echo "Stress load: active"
    fi
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

cmd_chart() {
    local filter_label="${1:-}"
    mkdir -p "$LOG_DIR"

    python3 -c "
import csv, sys, os

LOG_DIR = '$LOG_DIR'
filt = '$filter_label'
CHART_W = 72
CHART_H = 20

# Collect all test data
tests = {}
for f in sorted(os.listdir(LOG_DIR)):
    if not f.endswith('.csv'):
        continue
    name = f[:-4]
    if filt and name != filt:
        continue
    path = os.path.join(LOG_DIR, f)
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) < 2:
        continue
    from datetime import datetime
    t0 = datetime.strptime(rows[0]['timestamp'], '%Y-%m-%d %H:%M:%S')
    points = []
    for r in rows:
        t = datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S')
        mins = (t - t0).total_seconds() / 60
        points.append((mins, float(r['voltage_v'])))
    tests[name] = points

if not tests:
    print('No test data found.')
    sys.exit()

# Find global ranges
all_v = [v for pts in tests.values() for _, v in pts]
all_t = [t for pts in tests.values() for t, _ in pts]
v_min = min(all_v) - 0.05
v_max = max(all_v) + 0.05
t_max = max(all_t)
if t_max == 0:
    t_max = 1

# Symbols for different tests
syms = ['█', '▓', '░', '▒', '◆', '●', '■', '▲']
grid = [[' '] * CHART_W for _ in range(CHART_H)]

legend = []
for i, (name, pts) in enumerate(tests.items()):
    sym = syms[i % len(syms)]
    legend.append(f'  {sym} {name}')
    for t, v in pts:
        x = int(t / t_max * (CHART_W - 1))
        y = int((v - v_min) / (v_max - v_min) * (CHART_H - 1))
        y = CHART_H - 1 - y  # flip
        if 0 <= x < CHART_W and 0 <= y < CHART_H:
            grid[y][x] = sym

# Print chart
print()
print('── Voltage Curves ──')
print()
for row_i, row in enumerate(grid):
    v_label = v_max - (row_i / (CHART_H - 1)) * (v_max - v_min)
    print(f'{v_label:5.2f}V │{\"\" .join(row)}│')
print(f'       └{\"─\" * CHART_W}┘')
# Time axis labels
t_labels = f'       0m{\" \" * (CHART_W - len(str(int(t_max))) - 3)}{int(t_max)}m'
print(t_labels)
print()
for l in legend:
    print(l)
print()
"
}

cmd_health() {
    local filter_label="${1:-}"
    mkdir -p "$LOG_DIR"

    python3 -c "
import csv, sys, os

LOG_DIR = '$LOG_DIR'
filt = '$filter_label'

print('── Battery Health Report ──')
print()

for f in sorted(os.listdir(LOG_DIR)):
    if not f.endswith('.csv'):
        continue
    name = f[:-4]
    if filt and name != filt:
        continue
    path = os.path.join(LOG_DIR, f)
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) < 10:
        continue

    from datetime import datetime

    voltages = [float(r['voltage_v']) for r in rows]
    currents = [int(r['current_ma']) for r in rows]
    powers = [int(r['power_mw']) for r in rows]
    caps = [int(r['capacity_pct']) for r in rows]
    temps = []
    for r in rows:
        t = r.get('temp_c', '0')
        try:
            temps.append(float(t))
        except (ValueError, TypeError):
            pass

    t0 = datetime.strptime(rows[0]['timestamp'], '%Y-%m-%d %H:%M:%S')
    t1 = datetime.strptime(rows[-1]['timestamp'], '%Y-%m-%d %H:%M:%S')
    duration_h = (t1 - t0).total_seconds() / 3600

    # Determine if this is a discharge or charge test
    avg_current = sum(currents) / len(currents)
    test_type = 'Discharge' if avg_current < 0 else 'Charge'

    # Energy estimate: sum(|power| * interval) in mWh
    # Estimate interval from timestamps
    if len(rows) > 1:
        t_second = datetime.strptime(rows[1]['timestamp'], '%Y-%m-%d %H:%M:%S')
        interval_s = (t_second - t0).total_seconds()
        if interval_s <= 0:
            interval_s = 5
    else:
        interval_s = 5

    energy_mwh = sum(abs(p) * interval_s / 3600 for p in powers)
    energy_wh = energy_mwh / 1000

    avg_power = sum(abs(p) for p in powers) / len(powers)
    avg_current_abs = sum(abs(c) for c in currents) / len(currents)

    v_max = max(voltages)
    v_min = min(voltages)
    v_sag = v_max - v_min

    # Temperature stats
    if temps:
        t_avg = sum(temps) / len(temps)
        t_max = max(temps)
        t_min = min(temps)
        temp_str = f'{t_avg:.1f}C avg / {t_max:.1f}C max'
    else:
        temp_str = 'n/a'

    # Capacity per cell estimate (2 cells in series/parallel)
    cap_mah = int(energy_mwh / ((v_max + v_min) / 2)) if (v_max + v_min) > 0 else 0

    print(f'  {name}')
    print(f'  {\"─\" * 50}')
    print(f'  Type:        {test_type}')
    print(f'  Duration:    {duration_h:.1f}h ({len(rows)} samples @ {interval_s:.0f}s)')
    print(f'  Capacity:    {caps[0]}% → {caps[-1]}%')
    print(f'  Voltage:     {v_max:.3f}V → {v_min:.3f}V (sag: {v_sag:.3f}V)')
    print(f'  Energy:      {energy_wh:.1f} Wh')
    print(f'  Est. mAh:    ~{cap_mah} mAh (per cell pair)')
    print(f'  Avg current: {avg_current_abs:.0f} mA')
    print(f'  Avg power:   {avg_power:.0f} mW')
    print(f'  Temperature: {temp_str}')
    print()
"
}

cmd_stress() {
    local label="${1:?Usage: battery-test.sh stress <label>}"
    echo "Starting stress test: $label"
    echo "CPU stress load will run alongside battery logging."
    echo ""

    # Start CPU stress in background (use all cores)
    local ncpu
    ncpu=$(nproc)
    (
        trap 'exit 0' TERM INT HUP
        # Pure bash CPU stress — one busy loop per core
        for _ in $(seq 1 "$ncpu"); do
            while :; do :; done &
        done
        wait
    ) &
    local stress_pid=$!
    disown "$stress_pid"
    mkdir -p "$LOG_DIR"
    echo "$stress_pid" > "$LOG_DIR/.stress.pid"
    echo "Stress PID: $stress_pid ($ncpu cores)"

    # Start normal logging
    cmd_start "$label"
}

cmd_calibrate() {
    echo "── AXP228 Fuel Gauge Calibration ──"
    echo ""

    local capacity
    capacity=$(cat "$BAT/capacity" 2>/dev/null || echo "0")
    local status
    status=$(cat "$BAT/status" 2>/dev/null || echo "Unknown")
    local voltage
    voltage=$(awk "BEGIN {printf \"%.3f\", $(cat "$BAT/voltage_now" 2>/dev/null || echo 0) / 1000000}")

    echo "Current: ${capacity}% | ${voltage}V | ${status}"
    echo ""

    if [ "$capacity" -lt 95 ]; then
        echo "Battery is at ${capacity}%. Charge to 100% first."
        echo ""
        echo "Steps:"
        echo "  1. Plug in and charge to 100%"
        echo "  2. Run this command again"
        echo "  3. It will trigger calibration and monitor the drain"
        return 1
    fi

    echo "Battery is at ${capacity}% — ready to calibrate."
    echo ""
    echo "This will:"
    echo "  1. Write 1 to /sys/class/power_supply/axp20x-battery/calibrate"
    echo "  2. Start logging as 'calibrate-cycle'"
    echo "  3. You unplug and let it drain to shutdown"
    echo "  4. Then charge back to 100% to complete calibration"
    echo ""
    read -rp "Proceed? [y/N] " answer
    if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
        echo "Cancelled."
        return 0
    fi

    echo ""
    echo "Triggering calibration..."
    echo 1 | sudo tee /sys/class/power_supply/axp20x-battery/calibrate > /dev/null
    local cal_state
    cal_state=$(cat /sys/class/power_supply/axp20x-battery/calibrate 2>/dev/null || echo "?")
    echo "Calibrate state: $cal_state (32=enabled, 48=in progress)"
    echo ""

    echo "Starting discharge log: calibrate-cycle"
    INTERVAL=30
    cmd_start "calibrate-cycle"
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
    echo "time       | volts | mA    | mW    | cap% | status     | temp"
    echo "-----------|-------|-------|-------|------|------------|------"
    tail -f "$csv" 2>/dev/null | while IFS=, read -r ts v ma mw cap st cr tmp; do
        [ "$ts" = "timestamp" ] && continue
        local t="${ts##* }"
        printf "%s | %s | %5s | %5s | %3s%% | %-10s | %s\n" "$t" "$v" "$ma" "$mw" "$cap" "$st" "${tmp:-}"
    done
}

cmd_delete() {
    local label="${1:?Usage: battery-test.sh delete <label>}"
    rm -f "$LOG_DIR/${label}.csv" "$LOG_DIR/${label}.meta"
    echo "Deleted: $label"
}

case "${1:-help}" in
    start)     cmd_start "${2:-}" ;;
    stop)      cmd_stop ;;
    status)    cmd_status ;;
    list)      cmd_list ;;
    compare)   cmd_compare ;;
    chart)     cmd_chart "${2:-}" ;;
    health)    cmd_health "${2:-}" ;;
    stress)    cmd_stress "${2:-}" ;;
    calibrate) cmd_calibrate ;;
    export)    cmd_export "${2:-}" ;;
    live)      cmd_live "${2:-}" ;;
    delete)    cmd_delete "${2:-}" ;;
    -h|--help|help) usage ;;
    *) echo "Unknown: $1"; usage; exit 1 ;;
esac
