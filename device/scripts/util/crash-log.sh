#!/bin/bash
# Detect unclean shutdowns and log them with battery state
# Runs at boot via systemd. Uses a stamp file to distinguish
# clean shutdown (stamp removed by ExecStop) from crash (stamp remains).
set -u

STAMP="$HOME/.uconsole-running"
LOG="$HOME/crash.log"

case "${1:-boot}" in
    boot)
        if [ -f "$STAMP" ]; then
            # Stamp survived reboot — previous shutdown was unclean
            TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
            BAT="/sys/class/power_supply/axp20x-battery"
            VOLT_RAW=$(cat "$BAT/voltage_now" 2>/dev/null || echo 0)
            VOLT=$(awk "BEGIN {printf \"%.3f\", $VOLT_RAW / 1000000}")
            CAP=$(cat "$BAT/capacity" 2>/dev/null || echo "?")
            AC=$(cat /sys/class/power_supply/axp20x-ac/online 2>/dev/null || echo "?")
            TEMP_RAW=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)
            TEMP=$(awk "BEGIN {printf \"%.1f\", $TEMP_RAW / 1000}")
            UPTIME_PREV=$(last -x shutdown reboot 2>/dev/null | head -2 | tail -1 | awk '{print $NF}')

            # Check last kernel log for clues
            LAST_ERR=$(journalctl -b -1 -p err --no-pager -n 3 2>/dev/null | tail -3 | tr '\n' ' | ')

            echo "$TIMESTAMP | CRASH | boot_volt=${VOLT}V | boot_cap=${CAP}% | ac=${AC} | temp=${TEMP}C | prev_errs=${LAST_ERR}" >> "$LOG"
        fi

        # Set stamp — will persist until clean shutdown removes it
        touch "$STAMP"
        ;;
    stop)
        # Clean shutdown — remove stamp so next boot isn't flagged
        rm -f "$STAMP"
        ;;
esac
