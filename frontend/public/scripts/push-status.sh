#!/bin/bash
# Push uConsole system status to the uconsole.cloud API.
# Runs every 5 minutes via cron. Pure bash, no jq/python deps.
# Reads config from ~/.config/uconsole/status.env

set -euo pipefail

# ── Load config ─────────────────────────────────────────
ENV_FILE="${HOME}/.config/uconsole/status.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE" >&2
    exit 1
fi
source "$ENV_FILE"

: "${DEVICE_API_URL:?}"
: "${DEVICE_TOKEN:?}"
: "${DEVICE_REPO:?}"

# ── Helpers ─────────────────────────────────────────────
read_file() { cat "$1" 2>/dev/null || echo "$2"; }

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# ── Battery ─────────────────────────────────────────────
BAT_PATH="/sys/class/power_supply/axp20x-battery"
BAT_CAPACITY=$(read_file "$BAT_PATH/capacity" "0")
BAT_VOLTAGE=$(read_file "$BAT_PATH/voltage_now" "0")
BAT_VOLTAGE=$((BAT_VOLTAGE / 1000))  # microvolts → millivolts
BAT_CURRENT=$(read_file "$BAT_PATH/current_now" "0")
BAT_CURRENT=$((BAT_CURRENT / 1000))  # microamps → milliamps
BAT_STATUS=$(read_file "$BAT_PATH/status" "Unknown")
BAT_HEALTH=$(read_file "$BAT_PATH/health" "Unknown")

# ── CPU ─────────────────────────────────────────────────
CPU_TEMP_RAW=$(read_file "/sys/class/thermal/thermal_zone0/temp" "0")
CPU_TEMP_INT=$((CPU_TEMP_RAW / 1000))
CPU_TEMP_FRAC=$(( (CPU_TEMP_RAW % 1000) / 100 ))

LOADAVG=$(cat /proc/loadavg 2>/dev/null)
LOAD1=$(echo "$LOADAVG" | awk '{print $1}')
LOAD5=$(echo "$LOADAVG" | awk '{print $2}')
LOAD15=$(echo "$LOADAVG" | awk '{print $3}')

CPU_CORES=$(nproc 2>/dev/null || echo "4")

# ── Memory ──────────────────────────────────────────────
MEM_TOTAL=$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo)
MEM_AVAILABLE=$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
MEM_USED=$((MEM_TOTAL - MEM_AVAILABLE))

# ── Disk ────────────────────────────────────────────────
DISK_LINE=$(df -BG / 2>/dev/null | tail -1)
DISK_TOTAL=$(echo "$DISK_LINE" | awk '{gsub("G",""); print $2}')
DISK_USED=$(echo "$DISK_LINE" | awk '{gsub("G",""); print $3}')
DISK_AVAIL=$(echo "$DISK_LINE" | awk '{gsub("G",""); print $4}')
DISK_PCT=$(echo "$DISK_LINE" | awk '{gsub("%",""); print $5}')

# ── WiFi ────────────────────────────────────────────────
WIFI_RAW=$(iwconfig wlan0 2>/dev/null || true)
WIFI_SSID=$(echo "$WIFI_RAW" | grep -oP 'ESSID:"\K[^"]+' || echo "disconnected")
WIFI_SIGNAL=$(echo "$WIFI_RAW" | grep -oP 'Signal level=\K-?[0-9]+' || echo "0")
WIFI_QUALITY_RAW=$(echo "$WIFI_RAW" | grep -oP 'Link Quality=\K[0-9]+/[0-9]+' || echo "0/70")
WIFI_QUALITY_NUM=$(echo "$WIFI_QUALITY_RAW" | cut -d/ -f1)
WIFI_QUALITY_DEN=$(echo "$WIFI_QUALITY_RAW" | cut -d/ -f2)
if [ "$WIFI_QUALITY_DEN" -gt 0 ] 2>/dev/null; then
    WIFI_QUALITY=$((WIFI_QUALITY_NUM * 100 / WIFI_QUALITY_DEN))
else
    WIFI_QUALITY=0
fi
WIFI_BITRATE=$(echo "$WIFI_RAW" | grep -oP 'Bit Rate=\K[0-9.]+' || echo "0")
WIFI_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[0-9.]+' || echo "none")

# ── Screen ──────────────────────────────────────────────
BL_PATH=$(ls -d /sys/class/backlight/*/brightness 2>/dev/null | head -1)
if [ -n "$BL_PATH" ]; then
    BL_DIR=$(dirname "$BL_PATH")
    SCREEN_BRIGHTNESS=$(read_file "$BL_PATH" "0")
    SCREEN_MAX=$(read_file "$BL_DIR/max_brightness" "255")
else
    SCREEN_BRIGHTNESS=0
    SCREEN_MAX=255
fi

# ── System ──────────────────────────────────────────────
HOSTNAME=$(hostname)
KERNEL=$(uname -r)
UPTIME_RAW=$(awk '{print int($1)}' /proc/uptime)
UPTIME_DAYS=$((UPTIME_RAW / 86400))
UPTIME_HOURS=$(( (UPTIME_RAW % 86400) / 3600 ))
UPTIME_MINS=$(( (UPTIME_RAW % 3600) / 60 ))
if [ "$UPTIME_DAYS" -gt 0 ]; then
    UPTIME_STR="${UPTIME_DAYS}d ${UPTIME_HOURS}h ${UPTIME_MINS}m"
elif [ "$UPTIME_HOURS" -gt 0 ]; then
    UPTIME_STR="${UPTIME_HOURS}h ${UPTIME_MINS}m"
else
    UPTIME_STR="${UPTIME_MINS}m"
fi

# ── AIO Board ───────────────────────────────────────────
# SDR (RTL2838)
if lsusb 2>/dev/null | grep -q '0bda:2838'; then
    AIO_SDR_DETECTED=true
    AIO_SDR_CHIP="RTL2838"
else
    AIO_SDR_DETECTED=false
    AIO_SDR_CHIP=""
fi

# LoRa (SX1262 on SPI)
if [ -e /dev/spidev4.0 ]; then
    AIO_LORA_DETECTED=true
    AIO_LORA_CHIP="SX1262"
else
    AIO_LORA_DETECTED=false
    AIO_LORA_CHIP=""
fi

# GPS
AIO_GPS_DETECTED=false
AIO_GPS_FIX=false
if [ -c /dev/ttyS0 ]; then
    GPS_DATA=$(timeout 3 cat /dev/ttyS0 2>/dev/null || true)
    if echo "$GPS_DATA" | grep -q '^\$G'; then
        AIO_GPS_DETECTED=true
        if echo "$GPS_DATA" | grep -qP '\$G[NP]GGA,[^,]+,[0-9]+\.[0-9]+,[NS],[0-9]+\.[0-9]+,[EW]'; then
            AIO_GPS_FIX=true
        fi
    fi
fi

# RTC (PCF85063A at 0x51 — check /sys/class/rtc, fallback to i2cdetect)
AIO_RTC_DETECTED=false
AIO_RTC_SYNCED=false
AIO_RTC_TIME=""
if [ -d /sys/class/rtc/rtc0 ]; then
    AIO_RTC_DETECTED=true
    AIO_RTC_TIME=$(sudo hwclock -r 2>/dev/null | head -1)
    if [ -n "$AIO_RTC_TIME" ]; then
        AIO_RTC_SYNCED=true
    fi
fi

# ── Timestamp ───────────────────────────────────────────
COLLECTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── Build JSON ──────────────────────────────────────────
JSON=$(cat <<ENDJSON
{
  "hostname": "$(json_escape "$HOSTNAME")",
  "uptime": "$(json_escape "$UPTIME_STR")",
  "uptimeSeconds": $UPTIME_RAW,
  "kernel": "$(json_escape "$KERNEL")",
  "battery": {
    "capacity": $BAT_CAPACITY,
    "voltage": $BAT_VOLTAGE,
    "current": $BAT_CURRENT,
    "status": "$(json_escape "$BAT_STATUS")",
    "health": "$(json_escape "$BAT_HEALTH")"
  },
  "cpu": {
    "tempC": ${CPU_TEMP_INT}.${CPU_TEMP_FRAC},
    "loadAvg": [$LOAD1, $LOAD5, $LOAD15],
    "cores": $CPU_CORES
  },
  "memory": {
    "totalMB": $MEM_TOTAL,
    "usedMB": $MEM_USED,
    "availableMB": $MEM_AVAILABLE
  },
  "disk": {
    "totalGB": $DISK_TOTAL,
    "usedGB": $DISK_USED,
    "availableGB": $DISK_AVAIL,
    "usedPercent": $DISK_PCT
  },
  "wifi": {
    "ssid": "$(json_escape "$WIFI_SSID")",
    "signalDBm": $WIFI_SIGNAL,
    "quality": $WIFI_QUALITY,
    "bitrateMbps": $WIFI_BITRATE,
    "ip": "$(json_escape "$WIFI_IP")"
  },
  "aio": {
    "sdr": { "detected": $AIO_SDR_DETECTED, "chip": "$(json_escape "$AIO_SDR_CHIP")" },
    "lora": { "detected": $AIO_LORA_DETECTED, "chip": "$(json_escape "$AIO_LORA_CHIP")" },
    "gps": { "detected": $AIO_GPS_DETECTED, "hasFix": $AIO_GPS_FIX },
    "rtc": { "detected": $AIO_RTC_DETECTED, "synced": $AIO_RTC_SYNCED, "time": "$(json_escape "$AIO_RTC_TIME")" }
  },
  "screen": {
    "brightness": $SCREEN_BRIGHTNESS,
    "maxBrightness": $SCREEN_MAX
  },
  "collectedAt": "$COLLECTED_AT"
}
ENDJSON
)

# ── Push to API ─────────────────────────────────────────
COMPACT_JSON=$(printf '%s' "$JSON" | tr -d '\n' | tr -s ' ')

HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
    "${DEVICE_API_URL}" \
    -H "Authorization: Bearer ${DEVICE_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$COMPACT_JSON")

if [ "$HTTP_CODE" = "200" ]; then
    echo "[$(date -Iseconds)] Status pushed (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" = "401" ]; then
    echo "[$(date -Iseconds)] ERROR: Invalid device token (HTTP 401). Regenerate at https://uconsole.cloud" >&2
    exit 1
else
    echo "[$(date -Iseconds)] ERROR: Push failed (HTTP $HTTP_CODE)" >&2
    exit 1
fi
