#!/usr/bin/env bash
# ESP32 sensor node — query, monitor, flash, and manage via serial or HTTP
set -euo pipefail

SERIAL_PORT="${ESP32_PORT:-/dev/ttyUSB0}"
BAUD=115200
ESP32_DIR="$HOME/esp32"
WEBDASH_API="http://localhost:8080/api/esp32"

usage() {
    cat <<'EOF'
ESP32 Sensor Node

Usage: esp32.sh [command]

Commands:
  status     Show latest sensor reading (from webdash API)
  serial     Open live serial monitor (Ctrl+C to exit)
  repl       Open interactive MicroPython REPL (Ctrl+] to exit)
  flash      Re-flash boot.py and main.py to ESP32
  reset      Hard-reset the ESP32
  hall       Show hall effect reading (live from serial)
  touch      Show touch pin readings (live from serial)
  live       Live-updating sensor display (polls webdash)
  log        Append current reading to esp32.log
  ip         Show ESP32's IP address
  info       Show chip info via esptool

No arguments: show status
EOF
}

check_serial() {
    if [ ! -e "$SERIAL_PORT" ]; then
        echo "ERROR: $SERIAL_PORT not found. Is the ESP32 plugged in?"
        exit 1
    fi
}

stop_gpsd() {
    if sudo fuser "$SERIAL_PORT" >/dev/null 2>&1; then
        echo "Releasing serial port from gpsd..."
        sudo systemctl stop gpsd.socket gpsd.service 2>/dev/null || true
        sleep 0.5
    fi
}

serial_cmd() {
    # Send a command to MicroPython REPL via serial, return output
    local cmd="$1"
    python3 -c "
import serial, time
s = serial.Serial('$SERIAL_PORT', $BAUD, timeout=2)
time.sleep(0.1)
s.write(b'\x03\x03')
time.sleep(0.3)
s.read(s.in_waiting)
s.write(b'$cmd\r\n')
time.sleep(1)
out = s.read(s.in_waiting).decode(errors='replace')
lines = out.strip().split('\r\n')
for line in lines:
    if line.strip() and line.strip() != '>>>' and '$cmd' not in line:
        print(line.strip())
s.close()
"
}

cmd_status() {
    local data
    data=$(curl -sf "$WEBDASH_API" 2>/dev/null) || {
        echo "Webdash API unreachable. Trying serial..."
        check_serial
        stop_gpsd
        echo "── ESP32 Serial Reading ──"
        serial_cmd "exec(\"import esp32,network; t=esp32.raw_temperature(); w=network.WLAN(network.STA_IF); print('Temp:',round((t-32)*5/9,1),'C'); print('IP:',w.ifconfig()[0] if w.isconnected() else 'disconnected')\")"
        return
    }

    local online hall temp_c ip age t0 t3 t4 t7
    online=$(echo "$data" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ONLINE' if d.get('online') else 'OFFLINE')")
    free_kb=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('free_kb','--'))")
    temp_c=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('temp_c','--'))")
    ip=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ip','--'))")
    age=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('age','--'))")
    t0=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch0'); print('touched' if v else '--')")
    t3=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch3'); print('touched' if v else '--')")
    t4=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch4'); print('touched' if v else '--')")
    t7=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch7'); print('touched' if v else '--')")

    printf '── ESP32 Sensor Node ──\n'
    printf 'Status:      %s\n' "$online"
    printf 'Free RAM:    %s KB\n' "$free_kb"
    printf 'Temperature: %s°C\n' "$temp_c"
    printf 'IP Address:  %s\n' "$ip"
    printf 'Last Update: %ss ago\n' "$age"
    printf '\nTouch Pins:\n'
    printf '  T0: %-6s  T3: %-6s\n' "$t0" "$t3"
    printf '  T4: %-6s  T7: %-6s\n' "$t4" "$t7"
}

cmd_serial() {
    check_serial
    stop_gpsd
    echo "Opening serial monitor on $SERIAL_PORT @ ${BAUD}baud (Ctrl+C to exit)..."
    python3 -m serial.tools.miniterm "$SERIAL_PORT" "$BAUD"
}

cmd_repl() {
    check_serial
    stop_gpsd
    echo "Opening MicroPython REPL (Ctrl+] to exit)..."
    python3 -m serial.tools.miniterm --raw "$SERIAL_PORT" "$BAUD"
}

cmd_flash() {
    check_serial
    stop_gpsd
    echo "Uploading boot.py..."
    ampy --port "$SERIAL_PORT" put "$ESP32_DIR/boot.py"
    echo "Uploading main.py..."
    ampy --port "$SERIAL_PORT" put "$ESP32_DIR/main.py"
    echo "Done. Resetting ESP32..."
    cmd_reset
}

cmd_reset() {
    check_serial
    stop_gpsd
    python3 -c "
import serial, time
s = serial.Serial('$SERIAL_PORT', $BAUD, timeout=1)
s.setDTR(False)
time.sleep(0.1)
s.setDTR(True)
s.close()
"
    echo "ESP32 reset."
}

cmd_hall() {
    check_serial
    stop_gpsd
    serial_cmd "print(esp32.hall_sensor())"
}

cmd_touch() {
    check_serial
    stop_gpsd
    serial_cmd "exec(\"import machine; pins={'T0':4,'T3':15,'T4':13,'T7':27}\\nfor n,p in pins.items(): print(n,':',machine.TouchPad(machine.Pin(p)).read())\")"
}

cmd_live() {
    echo "── ESP32 Live Monitor (Ctrl+C to stop) ──"
    while true; do
        local data
        data=$(curl -sf "$WEBDASH_API" 2>/dev/null) || { sleep 1; continue; }
        local free_kb temp_c ip age t0 t3 t4 t7 online
        online=$(echo "$data" | python3 -c "import sys,json; d=json.load(sys.stdin); print('\033[32mONLINE\033[0m' if d.get('online') else '\033[31mOFFLINE\033[0m')")
        free_kb=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('free_kb','--'))")
        temp_c=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('temp_c','--'))")
        ip=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ip','--'))")
        age=$(echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('age','--'))")
        t0=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch0'); print('touched' if v else '--')")
        t3=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch3'); print('touched' if v else '--')")
        t4=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch4'); print('touched' if v else '--')")
        t7=$(echo "$data" | python3 -c "import sys,json; v=json.load(sys.stdin).get('touches',{}).get('touch7'); print('touched' if v else '--')")

        printf '\033[2J\033[H'
        printf '── ESP32 Live Monitor ──\n\n'
        printf 'Status:      %b\n' "$online"
        printf 'Free RAM:    %s KB\n' "$free_kb"
        printf 'Temperature: %s°C\n' "$temp_c"
        printf 'IP Address:  %s\n' "$ip"
        printf 'Last Update: %ss ago\n\n' "$age"
        printf 'Touch Pins:\n'
        printf '  T0: %-6s  T3: %-6s\n' "$t0" "$t3"
        printf '  T4: %-6s  T7: %-6s\n\n' "$t4" "$t7"
        printf '\033[2m(Ctrl+C to stop)\033[0m\n'
        sleep 2
    done
}

cmd_log() {
    local logfile="$HOME/esp32/esp32.log"
    local data
    data=$(curl -sf "$WEBDASH_API" 2>/dev/null) || { echo "Cannot reach webdash API"; exit 1; }
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    local line
    line=$(echo "$data" | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = d.get('touches',{})
def tf(k): return 'Y' if t.get(k) else 'N'
print('$ts temp={}C free={}KB ip={} t0={} t3={} t4={} t7={}'.format(
    d.get('temp_c','--'), d.get('free_kb','--'), d.get('ip','--'),
    tf('touch0'), tf('touch3'), tf('touch4'), tf('touch7')))
")
    echo "$line" >> "$logfile"
    echo "Logged: $line"
}

cmd_ip() {
    local data
    data=$(curl -sf "$WEBDASH_API" 2>/dev/null) || {
        check_serial
        stop_gpsd
        serial_cmd "exec(\"import network; w=network.WLAN(network.STA_IF); print(w.ifconfig()[0] if w.isconnected() else 'disconnected')\")"
        return
    }
    echo "$data" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ip','unknown'))"
}

cmd_info() {
    check_serial
    stop_gpsd
    esptool --port "$SERIAL_PORT" chip-id 2>&1 | grep -E '(Chip type|Features|Crystal|MAC)'
}

case "${1:-status}" in
    status)  cmd_status ;;
    serial)  cmd_serial ;;
    repl)    cmd_repl ;;
    flash)   cmd_flash ;;
    reset)   cmd_reset ;;
    hall)    cmd_hall ;;
    touch)   cmd_touch ;;
    live)    cmd_live ;;
    log)     cmd_log ;;
    ip)      cmd_ip ;;
    info)    cmd_info ;;
    -h|--help|help) usage ;;
    *) echo "Unknown command: $1"; usage; exit 1 ;;
esac
