#!/usr/bin/env bash
# ESP32 Marauder — serial interface, GPS-tagged scans, firmware management
# Device: ESP32 LDDB on AIO internal USB-C (/dev/esp32)
set -euo pipefail

SERIAL_PORT="${ESP32_PORT:-/dev/esp32}"
BAUD=115200
TIMEOUT=3
GPS_SAMPLE='$GPGGA,120000.00,4041.7520,N,07400.3560,W,1,08,1.2,10.0,M,-34.0,M,,*5E'

usage() {
    cat <<'EOF'
ESP32 Marauder

Usage: esp32-marauder.sh [command]

Commands:
  info         Firmware version, MAC, hardware info
  settings     Show/toggle Marauder settings
  serial       Open interactive serial monitor (Ctrl+C to exit)
  scan [type]  Run a scan (ap|station|beacon|deauth|probe|pmkid|bt|all)
  scan-gps     Run AP scan with GPS coordinates tagged
  stop         Stop active scan
  reboot       Reboot the ESP32
  led [hex]    Set LED color (e.g. FF0000) or off
  update [bin] Flash firmware .bin via esptool
  cmd [...]    Send raw command to Marauder

No arguments: show info
EOF
}

check_serial() {
    if [ ! -e "$SERIAL_PORT" ]; then
        echo "ERROR: $SERIAL_PORT not found. Is the ESP32 connected?"
        exit 1
    fi
}

# Send a command, capture output
marauder_cmd() {
    local cmd="$1"
    local wait="${2:-$TIMEOUT}"
    python3 -c "
import serial, time
s = serial.Serial('$SERIAL_PORT', $BAUD, timeout=$wait)
time.sleep(0.3)
s.write(b'\r\n')
time.sleep(0.3)
s.read(s.in_waiting)
s.write(b'$cmd\r\n')
time.sleep($wait)
out = s.read(s.in_waiting).decode('utf-8', errors='replace')
for line in out.splitlines():
    stripped = line.strip()
    if stripped and stripped != '>' and stripped != '#$cmd':
        print(stripped)
s.close()
"
}

# Get GPS fix from gpsd, fall back to sample data
get_gps() {
    local nmea
    nmea=$(gpspipe -r -n 20 2>/dev/null | grep '^\$G[NP]GGA' | head -1) || true
    if [ -z "$nmea" ]; then
        echo "[gps] no fix — using sample data" >&2
        nmea="$GPS_SAMPLE"
    fi
    # Parse GGA: lat, lon, fix quality, satellites, altitude
    python3 -c "
nmea = '$nmea'
parts = nmea.split(',')
if len(parts) < 10:
    print('no_fix,0,0,0,0')
    raise SystemExit
lat_raw, lat_dir = parts[2], parts[3]
lon_raw, lon_dir = parts[4], parts[5]
fix, sats, alt = parts[6], parts[7], parts[9]
# Convert NMEA ddmm.mmmm to decimal degrees
lat_d = int(lat_raw[:2]) + float(lat_raw[2:]) / 60
lon_d = int(lon_raw[:3]) + float(lon_raw[3:]) / 60
if lat_dir == 'S': lat_d = -lat_d
if lon_dir == 'W': lon_d = -lon_d
print(f'{lat_d:.6f},{lon_d:.6f},{fix},{sats},{alt}')
"
}

cmd_info() {
    check_serial
    marauder_cmd "info"
}

cmd_settings() {
    check_serial
    if [ $# -gt 0 ]; then
        marauder_cmd "settings -s $1 ${2:-enable}"
    else
        marauder_cmd "settings"
    fi
}

cmd_serial() {
    check_serial
    echo "Opening Marauder serial (Ctrl+C to exit)..."
    python3 -m serial.tools.miniterm "$SERIAL_PORT" "$BAUD"
}

cmd_scan() {
    check_serial
    local scan_type="${1:-ap}"
    case "$scan_type" in
        ap)       marauder_cmd "scanap" 8 ;;
        station)  marauder_cmd "scanall" 10 ;;
        beacon)   marauder_cmd "sniffbeacon" 8 ;;
        deauth)   marauder_cmd "sniffdeauth" 8 ;;
        probe)    marauder_cmd "sniffprobe" 8 ;;
        pmkid)    marauder_cmd "sniffpmkid" 10 ;;
        bt)       marauder_cmd "sniffbt" 8 ;;
        all)      marauder_cmd "scanall" 15 ;;
        *)        echo "Unknown scan type: $scan_type"; exit 1 ;;
    esac
}

cmd_scan_gps() {
    check_serial
    local gps_data scan_output ts
    gps_data=$(get_gps)
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    IFS=',' read -r lat lon fix sats alt <<< "$gps_data"

    echo "── GPS-Tagged AP Scan ──"
    printf 'Time:       %s\n' "$ts"
    printf 'Position:   %s, %s\n' "$lat" "$lon"
    printf 'Fix/Sats:   %s / %s\n' "$fix" "$sats"
    printf 'Altitude:   %sm\n\n' "$alt"

    scan_output=$(marauder_cmd "scanap" 10)
    echo "$scan_output"

    # Log to file
    local logdir="$HOME/esp32/marauder-logs"
    mkdir -p "$logdir"
    local logfile="$logdir/scan-$(date +%Y%m%d-%H%M%S).log"
    {
        echo "timestamp: $ts"
        echo "lat: $lat"
        echo "lon: $lon"
        echo "fix: $fix"
        echo "satellites: $sats"
        echo "altitude: $alt"
        echo "---"
        echo "$scan_output"
    } > "$logfile"
    echo ""
    echo "Logged to $logfile"
}

cmd_stop() {
    check_serial
    marauder_cmd "stopscan"
}

cmd_reboot() {
    check_serial
    marauder_cmd "reboot"
    echo "ESP32 rebooting..."
}

cmd_led() {
    check_serial
    if [ "${1:-}" = "off" ] || [ -z "${1:-}" ]; then
        marauder_cmd "led -s 000000"
    else
        marauder_cmd "led -s $1"
    fi
}

cmd_update() {
    check_serial
    local bin_file="${1:-}"
    if [ -z "$bin_file" ]; then
        echo "Usage: esp32-marauder.sh update <firmware.bin>"
        echo ""
        echo "Download latest from: https://github.com/justcallmekoko/ESP32Marauder/releases"
        echo "Look for: esp32_marauder_v*_old_hardware.bin"
        exit 1
    fi
    if [ ! -f "$bin_file" ]; then
        echo "ERROR: $bin_file not found"
        exit 1
    fi
    echo "Flashing $bin_file to $SERIAL_PORT..."
    esptool.py --port "$SERIAL_PORT" --baud 115200 \
        write_flash 0x10000 "$bin_file"
    echo "Flash complete. ESP32 will reboot."
}

cmd_raw() {
    check_serial
    local raw_cmd="$*"
    if [ -z "$raw_cmd" ]; then
        echo "Usage: esp32-marauder.sh cmd <marauder command>"
        exit 1
    fi
    marauder_cmd "$raw_cmd" 5
}

# Get just the firmware version string (used by other scripts)
cmd_version() {
    check_serial
    marauder_cmd "info" | grep -oP 'Version: \K.*' || echo "unknown"
}

case "${1:-info}" in
    info)      cmd_info ;;
    version)   cmd_version ;;
    settings)  shift; cmd_settings "$@" ;;
    serial)    cmd_serial ;;
    scan)      shift; cmd_scan "${1:-ap}" ;;
    scan-gps)  cmd_scan_gps ;;
    stop)      cmd_stop ;;
    reboot)    cmd_reboot ;;
    led)       shift; cmd_led "${1:-}" ;;
    update)    shift; cmd_update "${1:-}" ;;
    cmd)       shift; cmd_raw "$@" ;;
    -h|--help|help) usage ;;
    *)         echo "Unknown command: $1"; usage; exit 1 ;;
esac
