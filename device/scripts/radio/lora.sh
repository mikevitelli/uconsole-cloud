#!/usr/bin/env bash
# LoRa radio — SX1262 on SPI1 (/dev/spidev1.0), transmit/receive/range-test
# SPI1 overlay loaded on demand to avoid audio interference with GPIO 12/13
set -euo pipefail

source "$(dirname "$0")/lib.sh"

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
SPI_DEV="/dev/spidev1.0"
LORA_CONF="$HOME/.config/uconsole/lora.conf"
WEBDASH_API="http://localhost:8080/api/lora"
# python3-spidev is system-only; user shells may sit in venvs that lack it
PYTHON3="${PYTHON3:-/usr/bin/python3}"

usage() {
    cat <<EOF
Usage: lora.sh [command] [args]

Commands:
  status       SX1262 SPI check + config (default)
  config       show/set parameters (freq, bw, sf, power)
  send <msg>   transmit a message
  listen       receive incoming messages
  ping         range test — send ping, wait for pong
  chat         interactive LoRa chat
  bridge       forward received messages to webdash
EOF
}

check_spi() {
    if [ ! -e "$SPI_DEV" ]; then
        # Load SPI1 overlay on demand (not in config.txt to avoid audio interference)
        sudo dtoverlay spi1-1cs 2>/dev/null
        sleep 0.5
        if [ ! -e "$SPI_DEV" ]; then
            err "SPI device not found at $SPI_DEV"
            exit 1
        fi
    fi
}

unload_spi() {
    sudo dtoverlay -r spi1-1cs 2>/dev/null || true
}

load_config() {
    # Defaults (US ISM 915 MHz)
    LORA_FREQ=915.0
    LORA_BW=125
    LORA_SF=7
    LORA_POWER=22
    LORA_CR=5
    LORA_SYNC=0x12

    if [ -f "$LORA_CONF" ]; then
        # shellcheck source=/dev/null
        source "$LORA_CONF"
    fi
}

save_config() {
    mkdir -p "$(dirname "$LORA_CONF")"
    cat > "$LORA_CONF" <<EOF
# LoRa SX1262 configuration
LORA_FREQ=$LORA_FREQ
LORA_BW=$LORA_BW
LORA_SF=$LORA_SF
LORA_POWER=$LORA_POWER
LORA_CR=$LORA_CR
LORA_SYNC=$LORA_SYNC
EOF
}

lora_py() {
    "$PYTHON3" "$SCRIPTS_DIR/lora_helper.py" "$@"
}

cmd_status() {
    section "LoRa Status (SX1262)"
    check_spi
    if [ -e "$SPI_DEV" ]; then
        ok "SPI device present at $SPI_DEV"
    else
        err "SPI device not found at $SPI_DEV"
    fi

    load_config
    printf "\nConfiguration:\n"
    printf "  Frequency:       %.1f MHz\n" "$LORA_FREQ"
    printf "  Bandwidth:       %s kHz\n" "$LORA_BW"
    printf "  Spreading Factor: SF%s\n" "$LORA_SF"
    printf "  TX Power:        %s dBm\n" "$LORA_POWER"
    printf "  Coding Rate:     4/%s\n" "$LORA_CR"
    printf "  Config file:     %s\n" "$LORA_CONF"

    # Try to read SX1262 chip version
    if [ -e "$SPI_DEV" ] && [ -x "$PYTHON3" ]; then
        printf "\nHardware check:\n"
        "$PYTHON3" -c "
import spidev, subprocess, time
def gpioset(pin, val):
    subprocess.run(['gpioset','-m','exit','gpiochip0',f'{pin}={val}'],capture_output=True)
gpioset(25,0); time.sleep(0.05); gpioset(25,1); time.sleep(0.1)
spi = spidev.SpiDev()
try:
    spi.open(1, 0)
    spi.max_speed_hz = 1000000
    spi.mode = 0
    # Read VersionCode register (0x0320)
    resp = spi.xfer2([0x1D, 0x03, 0x20, 0x00, 0x00])
    version = resp[-1]
    if version in (0x53, 0x58):
        print(f'  SX1262 chip confirmed (version 0x{version:02X})')
    elif version == 0x00 or version == 0xFF:
        print('  SPI bus responsive but no valid chip ID')
    else:
        print(f'  SPI response: 0x{version:02X} (unexpected)')
    spi.close()
except Exception as e:
    print(f'  SPI error: {e}')
" 2>/dev/null || warn "Could not query SX1262 over SPI"
    fi
    unload_spi
}

cmd_config() {
    load_config
    if [ $# -le 1 ]; then
        section "LoRa Configuration"
        printf "LORA_FREQ=%s      # MHz\n" "$LORA_FREQ"
        printf "LORA_BW=%s        # kHz bandwidth\n" "$LORA_BW"
        printf "LORA_SF=%s          # spreading factor (7-12)\n" "$LORA_SF"
        printf "LORA_POWER=%s       # TX power dBm (max 22)\n" "$LORA_POWER"
        printf "LORA_CR=%s          # coding rate 4/N\n" "$LORA_CR"
        printf "\nEdit: %s\n" "$LORA_CONF"
        return
    fi

    local key="${2:-}"
    local val="${3:-}"
    if [ -z "$key" ] || [ -z "$val" ]; then
        echo "Usage: lora.sh config <key> <value>"
        echo "Keys: freq, bw, sf, power, cr"
        return 1
    fi

    case "$key" in
        freq)  LORA_FREQ="$val" ;;
        bw)    LORA_BW="$val" ;;
        sf)    LORA_SF="$val" ;;
        power) LORA_POWER="$val" ;;
        cr)    LORA_CR="$val" ;;
        *)     err "Unknown key: $key"; return 1 ;;
    esac
    save_config
    ok "Set $key=$val"
}

cmd_send() {
    check_spi
    load_config
    local msg="${2:-test}"
    section "LoRa TX"
    printf "Sending: %s\n" "$msg"
    printf "  Freq: %.1f MHz  SF%s  BW%s  %s dBm\n" "$LORA_FREQ" "$LORA_SF" "$LORA_BW" "$LORA_POWER"
    lora_py send "$msg" "$LORA_FREQ" "$LORA_BW" "$LORA_SF" "$LORA_POWER"
    unload_spi
}

cmd_listen() {
    check_spi
    load_config
    section "LoRa RX — Listening"
    printf "Freq: %.1f MHz  SF%s  BW%s  (Ctrl-C to stop)\n\n" "$LORA_FREQ" "$LORA_SF" "$LORA_BW"
    lora_py listen "$LORA_FREQ" "$LORA_BW" "$LORA_SF"
    unload_spi
}

cmd_ping() {
    check_spi
    load_config
    section "LoRa Ping"
    printf "Freq: %.1f MHz  SF%s  BW%s  %s dBm\n" "$LORA_FREQ" "$LORA_SF" "$LORA_BW" "$LORA_POWER"
    lora_py ping "$LORA_FREQ" "$LORA_BW" "$LORA_SF" "$LORA_POWER"
    unload_spi
}

cmd_chat() {
    check_spi
    load_config
    section "LoRa Chat"
    printf "Freq: %.1f MHz  SF%s  BW%s  (Ctrl-C to exit)\n\n" "$LORA_FREQ" "$LORA_SF" "$LORA_BW"
    lora_py chat "$LORA_FREQ" "$LORA_BW" "$LORA_SF" "$LORA_POWER"
    unload_spi
}

cmd_bridge() {
    check_spi
    load_config
    section "LoRa → Webdash Bridge"
    printf "Forwarding received messages to %s\n" "$WEBDASH_API/push"
    printf "Freq: %.1f MHz  SF%s  BW%s  (Ctrl-C to stop)\n\n" "$LORA_FREQ" "$LORA_SF" "$LORA_BW"
    lora_py bridge "$LORA_FREQ" "$LORA_BW" "$LORA_SF" "$WEBDASH_API/push"
    unload_spi
}

case "${1:-status}" in
    status)  cmd_status ;;
    config)  cmd_config "$@" ;;
    send)    cmd_send "$@" ;;
    listen)  cmd_listen ;;
    ping)    cmd_ping ;;
    chat)    cmd_chat ;;
    bridge)  cmd_bridge ;;
    -h|--help|help) usage ;;
    *)       echo "Unknown command: $1"; usage; exit 1 ;;
esac
