#!/bin/bash
# AIO V1 Board — component status check

source "$(dirname "$0")/lib.sh"

section "AIO V1 Board Check"

# ── SDR (RTL2838 via USB) ──
printf "  ${BOLD}SDR (RTL2838)${RESET}\n"
if lsusb 2>/dev/null | grep -q '0bda:2838'; then
    ok "Detected on USB"
else
    err "Not detected — check USB connection"
fi
echo ""

# ── LoRa (SX1262 on SPI) ──
printf "  ${BOLD}LoRa (SX1262)${RESET}\n"
if [ -e /dev/spidev4.0 ]; then
    ok "SPI device present at /dev/spidev4.0"
else
    err "No SPI device — check dtoverlay=spi1-1cs in boot config"
fi
echo ""

# ── GPS (UART) ──
printf "  ${BOLD}GPS${RESET}\n"
if [ -c /dev/ttyS0 ]; then
    GPS_DATA=$(timeout 3 cat /dev/ttyS0 2>/dev/null || true)
    if echo "$GPS_DATA" | grep -q '^\$G'; then
        ok "Receiving NMEA sentences"
        if echo "$GPS_DATA" | grep -qP '\$G[NP]GGA,[^,]+,[0-9]+\.[0-9]+,[NS],[0-9]+\.[0-9]+,[EW]'; then
            ok "Has satellite fix"
        else
            warn "No fix yet — move near a window or outside"
        fi
    else
        warn "Serial open but no NMEA data (cold start may take a minute)"
    fi
else
    err "No serial device at /dev/ttyS0"
fi
echo ""

# ── RTC (PCF85063A at 0x51 on i2c-0) ──
printf "  ${BOLD}RTC (PCF85063A)${RESET}\n"
if ! command -v i2cdetect &>/dev/null; then
    err "i2c-tools not installed — run: sudo apt install i2c-tools"
elif i2cdetect -y 1 2>/dev/null | grep -q '50:.*\(51\|UU\)'; then
    ok "Detected at i2c-1 address 0x51"
    RTC_TIME=$(sudo hwclock -r 2>/dev/null)
    if [ -n "$RTC_TIME" ]; then
        ok "RTC time: $RTC_TIME"
    else
        warn "Could not read time — try: sudo hwclock -r"
    fi
else
    err "Not detected on i2c-1 — check dtoverlay=i2c-rtc,pcf85063a in boot config"
fi
