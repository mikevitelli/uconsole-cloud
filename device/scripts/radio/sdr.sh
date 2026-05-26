#!/usr/bin/env bash
# SDR receiver — RTL2838 dongle management, scanning, and decoding
set -euo pipefail

source "$(dirname "$0")/lib.sh"

SDR_DIR="$HOME/sdr"

usage() {
    cat <<EOF
Usage: sdr.sh [command] [args]

Commands:
  status       check RTL2838 device (default)
  test         run tuner test
  info         detailed device capabilities
  fm [freq]    listen to FM radio (default: 101.1M)
  adsb         track aircraft (readsb)
  scan [range] power spectrum scan (default: 88M:108M:125k)
  433          IoT device decoder (rtl_433)
  decode       pager/POCSAG decoding (multimon-ng)
  record [freq] capture raw IQ samples
EOF
}

ensure_sdr_dir() { mkdir -p "$SDR_DIR"; }

check_sdr() {
    if ! lsusb 2>/dev/null | grep -q '0bda:2838'; then
        err "RTL2838 SDR not detected on USB"
        exit 1
    fi
}

check_tool() {
    if ! command -v "$1" &>/dev/null; then
        err "$1 not found — install with: sudo apt install $2"
        exit 1
    fi
}

cmd_status() {
    section "SDR Status (RTL2838)"
    if lsusb 2>/dev/null | grep -q '0bda:2838'; then
        ok "RTL2838 detected on USB"
        local usb_info
        usb_info=$(lsusb 2>/dev/null | grep '0bda:2838')
        printf "  %s\n" "$usb_info"
    else
        err "RTL2838 not detected"
        return 1
    fi

    if command -v rtl_test &>/dev/null; then
        printf "\nTuner quick check:\n"
        timeout 3 rtl_test -t 2>&1 | grep -E 'Found|Tuner|Using' | head -5 || true
    else
        warn "rtl-sdr tools not installed — run: sudo apt install rtl-sdr"
    fi
}

cmd_test() {
    check_sdr
    check_tool rtl_test rtl-sdr
    section "RTL-SDR Tuner Test"
    timeout 10 rtl_test -t 2>&1 || true
}

cmd_info() {
    check_sdr
    section "SDR Device Info"
    if command -v rtl_test &>/dev/null; then
        timeout 5 rtl_test -t 2>&1 | head -20 || true
    fi
    echo ""
    if command -v SoapySDRUtil &>/dev/null; then
        printf "SoapySDR probe:\n"
        SoapySDRUtil --probe="driver=rtlsdr" 2>&1 | head -30 || true
    fi
}

cmd_fm() {
    check_sdr
    check_tool rtl_fm rtl-sdr
    local freq="${2:-101.1M}"
    section "FM Radio — $freq"
    printf "Tuning to %s... (Ctrl-C to stop)\n\n" "$freq"
    rtl_fm -f "$freq" -M fm -s 200000 -r 48000 - 2>/dev/null | \
        aplay -r 48000 -f S16_LE -t raw -c 1 2>/dev/null
}

cmd_adsb() {
    check_sdr
    check_tool viewadsb readsb
    section "ADS-B Aircraft Tracking (viewadsb → readsb)"
    if systemctl is-active --quiet readsb; then
        printf "Connecting viewadsb to running readsb... (Ctrl-C to exit)\n\n"
        viewadsb 2>/dev/null
    else
        printf "readsb not running — start it first: sudo systemctl start readsb\n"
        printf "Or use the TUI: console → Radio → ADS-B → Feeder (readsb)\n"
        return 1
    fi
}

cmd_scan() {
    check_sdr
    check_tool rtl_power rtl-sdr
    ensure_sdr_dir
    local range="${2:-88M:108M:125k}"
    local outfile="$SDR_DIR/scan-$(date +%Y%m%d-%H%M%S).csv"
    section "Frequency Scan — $range"
    printf "Scanning %s → %s\n" "$range" "$outfile"
    rtl_power -f "$range" -g 40 -i 10 -1 "$outfile" 2>&1
    ok "Scan saved: $outfile"
    wc -l "$outfile" | awk '{print "  " $1 " data points"}'
}

cmd_433() {
    check_sdr
    if ! command -v rtl_433 &>/dev/null; then
        err "rtl_433 not found — build from source: https://github.com/merbanan/rtl_433"
        exit 1
    fi
    section "IoT Device Scanner (433/915 MHz)"
    printf "Listening for wireless devices... (Ctrl-C to stop)\n\n"
    rtl_433 -F json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        model = d.get('model', '?')
        t = d.get('time', '')
        # Print key fields
        parts = [f'{t}  {model}']
        for k in ('temperature_C', 'humidity', 'battery_ok', 'channel', 'id'):
            if k in d:
                parts.append(f'{k}={d[k]}')
        print('  '.join(parts))
    except: pass
"
}

cmd_decode() {
    check_sdr
    check_tool rtl_fm rtl-sdr
    check_tool multimon-ng multimon-ng
    section "Pager/POCSAG Decoder"
    printf "Listening on 152.0 MHz... (Ctrl-C to stop)\n\n"
    rtl_fm -f 152.0M -s 22050 2>/dev/null | \
        multimon-ng -t raw -a POCSAG512 -a POCSAG1200 -a POCSAG2400 -f alpha -
}

cmd_record() {
    check_sdr
    check_tool rtl_sdr rtl-sdr
    ensure_sdr_dir
    local freq="${2:-100M}"
    local duration="${3:-10}"
    local outfile="$SDR_DIR/iq-$(date +%Y%m%d-%H%M%S).raw"
    section "IQ Recording — $freq"
    printf "Recording %ss at %s → %s\n" "$duration" "$freq" "$outfile"
    timeout "$duration" rtl_sdr -f "$freq" -s 2.4e6 "$outfile" 2>&1 || true
    ok "Saved: $outfile"
    ls -lh "$outfile" | awk '{print "  Size: " $5}'
}

case "${1:-status}" in
    status)  cmd_status ;;
    test)    cmd_test ;;
    info)    cmd_info ;;
    fm)      cmd_fm "$@" ;;
    adsb)    cmd_adsb ;;
    scan)    cmd_scan "$@" ;;
    433)     cmd_433 ;;
    decode)  cmd_decode ;;
    record)  cmd_record "$@" ;;
    -h|--help|help) usage ;;
    *)       echo "Unknown command: $1"; usage; exit 1 ;;
esac
