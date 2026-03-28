#!/bin/bash
# hardware-detect.sh — detect uConsole expansion module and peripherals
# Usage: hardware-detect.sh [--json] [--quiet]
#
# Writes results to /etc/uconsole/hardware.json (default)
# --json   print JSON to stdout instead of writing file
# --quiet  suppress terminal output (still writes file)

set -euo pipefail

# source lib.sh if available (for colors), otherwise define stubs
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$_SCRIPT_DIR/../../scripts/lib.sh" ]; then
    source "$_SCRIPT_DIR/../../scripts/lib.sh" 2>/dev/null || true
elif [ -f "/home/$(whoami)/scripts/lib.sh" ]; then
    source "/home/$(whoami)/scripts/lib.sh" 2>/dev/null || true
fi
# ensure output helpers exist even without lib.sh
type ok    &>/dev/null || ok()      { printf "  \033[32m✓\033[0m %s\n" "$1"; }
type warn  &>/dev/null || warn()    { printf "  \033[33m!\033[0m %s\n" "$1"; }
type err   &>/dev/null || err()     { printf "  \033[31m✗\033[0m %s\n" "$1"; }
type info  &>/dev/null || info()    { printf "  \033[2m%s\033[0m\n" "$1"; }
type section &>/dev/null || section() { echo ""; printf "\033[1m\033[36m── %s ──\033[0m\n\n" "$1"; }

# --- args ---
FLAG_JSON=false
FLAG_QUIET=false
for arg in "$@"; do
    case "$arg" in
        --json)  FLAG_JSON=true ;;
        --quiet) FLAG_QUIET=true ;;
    esac
done

log() { [ "$FLAG_QUIET" = false ] && "$@" || true; }

OUT_FILE="/etc/uconsole/hardware.json"

# --- detection helpers ---

has_usb_device() {
    lsusb 2>/dev/null | grep -qi "$1"
}

service_active() {
    systemctl is-active "$1" &>/dev/null
}

gpio_exported() {
    [ -d "/sys/class/gpio/gpio$1" ]
}

# --- detect expansion module ---

detect_expansion() {
    local sdr=false lora=false has_4g=false
    local module="none"

    # SDR: RTL2838
    if has_usb_device "RTL2838"; then
        sdr=true
    fi

    # LoRa: SX1262 via SPI
    if [ -e /dev/spidev1.0 ] || [ -e /dev/spidev4.0 ]; then
        lora=true
    fi

    # 4G modem
    if has_usb_device "Quectel" || has_usb_device "SimCom" || has_usb_device "Huawei.*Modem" || \
       command -v mmcli &>/dev/null && mmcli -L 2>/dev/null | grep -qi "modem"; then
        has_4g=true
    fi

    # classify
    if [ "$sdr" = true ] || [ "$lora" = true ]; then
        # AIO board present — distinguish V1 vs V2
        # V2 has GPIO-gated power control pins
        local v2_pins=0
        for pin in 27 16 7 23; do
            if gpio_exported "$pin"; then
                v2_pins=$((v2_pins + 1))
            fi
        done
        if [ "$v2_pins" -ge 2 ]; then
            module="aio-v2"
        else
            module="aio-v1"
        fi
    elif [ "$has_4g" = true ]; then
        module="4g"
    fi

    printf '%s' "$module"
}

# --- detect WiFi method ---

detect_wifi_method() {
    if systemctl is-active NetworkManager &>/dev/null; then
        printf 'networkmanager'
    elif systemctl is-active dhcpcd &>/dev/null; then
        printf 'dhcpcd'
    else
        printf 'unknown'
    fi
}

# --- detect battery ---

detect_battery() {
    local bat="/sys/class/power_supply/axp20x-battery"
    local voltage_ua capacity present
    voltage_ua=$(cat "$bat/voltage_now" 2>/dev/null || echo "0")
    capacity=$(cat "$bat/capacity" 2>/dev/null || echo "0")
    present=$(cat "$bat/present" 2>/dev/null || echo "0")

    local voltage_v
    voltage_v=$(awk "BEGIN {printf \"%.3f\", $voltage_ua / 1000000}" 2>/dev/null || echo "0")

    # estimate capacity class from voltage range
    local capacity_class="unknown"
    if [ "$present" = "1" ]; then
        capacity_class="standard"
        # >4.1V under charge with high capacity suggests upgraded cells
        local mv=$((voltage_ua / 1000))
        if [ "$mv" -gt 3800 ]; then
            capacity_class="high"
        fi
    fi

    printf '{"present": %s, "voltage": "%s", "capacity_pct": %s, "capacity_class": "%s"}' \
        "$( [ "$present" = "1" ] && echo true || echo false )" \
        "$voltage_v" "$capacity" "$capacity_class"
}

# --- probe AIO components ---

probe_sdr() {
    has_usb_device "RTL2838" && echo "detected" || echo "not_detected"
}

probe_lora() {
    ( [ -e /dev/spidev1.0 ] || [ -e /dev/spidev4.0 ] ) && echo "detected" || echo "not_detected"
}

probe_gps() {
    if service_active gpsd || [ -e /dev/ttyS0 ]; then
        echo "detected"
    else
        echo "not_detected"
    fi
}

probe_rtc() {
    # PCF85063A at I2C address 0x51
    if command -v i2cdetect &>/dev/null; then
        if i2cdetect -y 1 0x51 0x51 2>/dev/null | grep -q "51"; then
            echo "detected"
        else
            echo "not_detected"
        fi
    else
        echo "not_detected"
    fi
}

probe_esp32() {
    if ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1 | grep -q .; then
        echo "detected"
    else
        echo "not_detected"
    fi
}

# --- build JSON ---

build_json() {
    local module wifi_method battery
    module=$(detect_expansion)
    wifi_method=$(detect_wifi_method)
    battery=$(detect_battery)

    local sdr lora gps rtc esp32
    sdr=$(probe_sdr)
    lora=$(probe_lora)
    gps=$(probe_gps)
    rtc=$(probe_rtc)
    esp32=$(probe_esp32)

    local hostname kernel arch
    hostname=$(hostname 2>/dev/null || echo "uconsole")
    kernel=$(uname -r 2>/dev/null || echo "unknown")
    arch=$(uname -m 2>/dev/null || echo "unknown")

    cat <<ENDJSON
{
  "detected_at": "$(date -Iseconds)",
  "hostname": "$hostname",
  "kernel": "$kernel",
  "arch": "$arch",
  "expansion_module": "$module",
  "wifi_method": "$wifi_method",
  "battery": $battery,
  "components": {
    "sdr": "$sdr",
    "lora": "$lora",
    "gps": "$gps",
    "rtc": "$rtc",
    "esp32": "$esp32"
  }
}
ENDJSON
}

# --- main ---

log section "Hardware Detection"

json=$(build_json)

if [ "$FLAG_JSON" = true ]; then
    echo "$json"
else
    echo "$json" > "$OUT_FILE"
    log ok "Wrote $OUT_FILE"
fi

# pretty-print summary
if [ "$FLAG_QUIET" = false ]; then
    module=$(echo "$json" | grep '"expansion_module"' | cut -d'"' -f4)
    wifi=$(echo "$json" | grep '"wifi_method"' | cut -d'"' -f4)

    case "$module" in
        aio-v1) log ok "Expansion: AIO Board V1" ;;
        aio-v2) log ok "Expansion: AIO Board V2 (GPIO power control)" ;;
        4g)     log ok "Expansion: 4G LTE Modem" ;;
        none)   log info "Expansion: None detected" ;;
    esac

    log info "WiFi: $wifi"

    for comp in sdr lora gps rtc esp32; do
        status=$(echo "$json" | grep "\"$comp\"" | head -1 | cut -d'"' -f4)
        if [ "$status" = "detected" ]; then
            log ok "$comp"
        else
            log info "$comp: not detected"
        fi
    done
fi
