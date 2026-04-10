#!/usr/bin/env bash
# GPS receiver — query gpsd, track, log, and manage position data
set -euo pipefail

source "$(dirname "$0")/lib.sh"

GPS_DIR="$HOME/gps"
WEBDASH_API="http://localhost:8080/api/gps"

usage() {
    cat <<EOF
Usage: gps.sh [command]

Commands:
  status       position, altitude, satellites (default)
  live         real-time GPS dashboard
  satellites   constellation view (cgps)
  track        start logging position to GPX
  stop         stop active track log
  nmea         raw NMEA sentence stream
  time         GPS vs system vs RTC time
  log          append single fix to gps.log
  fix          fix status and quality info
EOF
}

ensure_gps_dir() { mkdir -p "$GPS_DIR"; }

check_gpsd() {
    if ! command -v gpspipe &>/dev/null; then
        err "gpspipe not found — install gpsd-clients"
        exit 1
    fi
    if ! systemctl is-active --quiet gpsd 2>/dev/null; then
        # Try to start it
        sudo systemctl start gpsd 2>/dev/null
        if ! systemctl is-active --quiet gpsd 2>/dev/null; then
            err "gpsd is not running — start with: sudo systemctl start gpsd"
            exit 1
        fi
    fi
}

# Get a single TPV fix from gpsd (JSON)
gpsd_tpv() {
    gpspipe -w -n 10 -x 5 2>/dev/null | grep -m1 '"class":"TPV"' || echo '{}'
}

# Parse TPV JSON into display fields
parse_tpv() {
    local json="$1"
    python3 -c "
import json, sys
try:
    d = json.loads('''$json''')
except: d = {}
mode = d.get('mode', 0)
fix = {0: 'none', 1: 'none', 2: '2D', 3: '3D'}.get(mode, 'none')
lat = d.get('lat', 0.0)
lon = d.get('lon', 0.0)
alt = d.get('altMSL', d.get('alt', 0.0))
speed = d.get('speed', 0.0) * 3.6  # m/s to km/h
climb = d.get('climb', 0.0)
hdop = d.get('hdop', 0.0)
t = d.get('time', '--')
print(f'Fix:        {fix}')
print(f'Latitude:   {lat:.6f}')
print(f'Longitude:  {lon:.6f}')
print(f'Altitude:   {alt:.1f} m')
print(f'Speed:      {speed:.1f} km/h')
print(f'HDOP:       {hdop}')
print(f'GPS Time:   {t}')
"
}

# Get satellite count from SKY message
sat_count() {
    local sky
    sky=$(gpspipe -w -n 20 -x 5 2>/dev/null | grep -m1 '"class":"SKY"' || echo '{}')
    python3 -c "
import json
try:
    d = json.loads('''$sky''')
    sats = d.get('satellites', [])
    used = sum(1 for s in sats if s.get('used'))
    print(f'Satellites: {used}/{len(sats)} (used/visible)')
except: print('Satellites: --')
"
}

cmd_status() {
    check_gpsd
    section "GPS Status"
    local tpv
    tpv=$(gpsd_tpv)
    parse_tpv "$tpv"
    sat_count
}

cmd_live() {
    check_gpsd
    while true; do
        clear
        printf "\033[1mGPS Live Dashboard\033[0m  (Ctrl-C to exit)\n\n"
        local tpv
        tpv=$(gpsd_tpv)
        parse_tpv "$tpv"
        sat_count
        printf "\nUpdated: %s\n" "$(date '+%H:%M:%S')"
        sleep 2
    done
}

cmd_satellites() {
    check_gpsd
    exec cgps -s
}

cmd_track() {
    ensure_gps_dir
    if [ -f "$GPS_DIR/.tracking.pid" ]; then
        local pid
        pid=$(cat "$GPS_DIR/.tracking.pid")
        if kill -0 "$pid" 2>/dev/null; then
            err "Track already running (PID $pid). Use 'gps.sh stop' first."
            exit 1
        fi
        rm -f "$GPS_DIR/.tracking.pid"
    fi

    local gpx="$GPS_DIR/track-$(date +%Y%m%d-%H%M%S).gpx"
    echo "$gpx" > "$GPS_DIR/.tracking.file"

    # Start background GPX logger
    (
        python3 -c "
import subprocess, json, time, sys, os

gpx = '$gpx'
with open(gpx, 'w') as f:
    f.write('<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n')
    f.write('<gpx version=\"1.1\" creator=\"uconsole-gps\">\n<trk><name>uConsole Track</name><trkseg>\n')
    f.flush()

    proc = subprocess.Popen(['gpspipe', '-w'], stdout=subprocess.PIPE, text=True)
    try:
        for line in proc.stdout:
            try:
                d = json.loads(line)
            except: continue
            if d.get('class') != 'TPV': continue
            if d.get('mode', 0) < 2: continue
            lat = d.get('lat', 0)
            lon = d.get('lon', 0)
            ele = d.get('altMSL', d.get('alt', 0))
            t = d.get('time', '')
            f.write(f'<trkpt lat=\"{lat}\" lon=\"{lon}\"><ele>{ele}</ele><time>{t}</time></trkpt>\n')
            f.flush()
    except KeyboardInterrupt:
        pass
    finally:
        f.write('</trkseg></trk>\n</gpx>\n')
        proc.terminate()
" &
    )
    local pid=$!
    echo "$pid" > "$GPS_DIR/.tracking.pid"
    ok "Tracking started → $gpx (PID $pid)"
}

cmd_stop() {
    ensure_gps_dir
    if [ ! -f "$GPS_DIR/.tracking.pid" ]; then
        warn "No active track"
        return
    fi
    local pid
    pid=$(cat "$GPS_DIR/.tracking.pid")
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null
        wait "$pid" 2>/dev/null || true
        ok "Tracking stopped (PID $pid)"
    else
        warn "Tracker process $pid already dead"
    fi
    local gpx
    gpx=$(cat "$GPS_DIR/.tracking.file" 2>/dev/null || echo "unknown")
    rm -f "$GPS_DIR/.tracking.pid" "$GPS_DIR/.tracking.file"
    ok "GPX saved: $gpx"
}

cmd_nmea() {
    check_gpsd
    exec gpspipe -r
}

cmd_time() {
    check_gpsd
    section "Time Comparison"
    local tpv
    tpv=$(gpsd_tpv)
    local gps_time sys_time rtc_time
    gps_time=$(python3 -c "
import json
try:
    d = json.loads('''$tpv''')
    print(d.get('time', '--'))
except: print('--')
")
    sys_time=$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')
    rtc_time=$(sudo hwclock -r 2>/dev/null | head -1 || echo "--")

    printf "GPS Time:    %s\n" "$gps_time"
    printf "System Time: %s\n" "$sys_time"
    printf "RTC Time:    %s\n" "$rtc_time"

    # Compute drift if GPS time is available
    if [ "$gps_time" != "--" ]; then
        python3 -c "
from datetime import datetime
try:
    gps = datetime.fromisoformat('$gps_time'.replace('Z', '+00:00'))
    sys = datetime.fromisoformat('$sys_time'.replace('Z', '+00:00'))
    delta = abs((sys - gps).total_seconds())
    print(f'GPS-System drift: {delta:.1f}s')
except Exception as e:
    print(f'Could not compute drift: {e}')
"
    fi
}

cmd_log() {
    check_gpsd
    ensure_gps_dir
    local tpv
    tpv=$(gpsd_tpv)
    local line
    line=$(python3 -c "
import json
from datetime import datetime
try:
    d = json.loads('''$tpv''')
    lat = d.get('lat', 0)
    lon = d.get('lon', 0)
    alt = d.get('altMSL', d.get('alt', 0))
    speed = d.get('speed', 0) * 3.6
    mode = d.get('mode', 0)
    t = d.get('time', datetime.utcnow().isoformat())
    print(f'{t} | {lat:.6f},{lon:.6f} | {alt:.1f}m | {speed:.1f}km/h | fix={mode}')
except: print('-- no fix --')
")
    echo "$line" >> "$GPS_DIR/gps.log"
    ok "Logged: $line"
}

cmd_fix() {
    check_gpsd
    section "GPS Fix Info"
    local tpv
    tpv=$(gpsd_tpv)
    python3 -c "
import json
try:
    d = json.loads('''$tpv''')
    mode = d.get('mode', 0)
    fix = {0: 'none', 1: 'none', 2: '2D', 3: '3D'}.get(mode, 'none')
    eps = d.get('eps', 0)
    eph = d.get('eph', 0)
    epv = d.get('epv', 0)
    print(f'Fix Type:     {fix}')
    print(f'H. Accuracy:  {eph:.1f} m')
    print(f'V. Accuracy:  {epv:.1f} m')
    print(f'Speed Error:  {eps:.1f} m/s')
except:
    print('No fix available')
"
    sat_count
}

case "${1:-status}" in
    status)     cmd_status ;;
    live)       cmd_live ;;
    satellites) cmd_satellites ;;
    track)      cmd_track ;;
    stop)       cmd_stop ;;
    nmea)       cmd_nmea ;;
    time)       cmd_time ;;
    log)        cmd_log ;;
    fix)        cmd_fix ;;
    -h|--help|help) usage ;;
    *)          echo "Unknown command: $1"; usage; exit 1 ;;
esac
