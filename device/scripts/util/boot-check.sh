#!/bin/bash
# Log battery state on boot — runs via cron @reboot
LOG="$HOME/cellhealth.log"
BAT="/sys/class/power_supply/axp20x-battery"

sleep 10  # wait for sysfs to settle

VOLTAGE=$(cat "$BAT/voltage_now" 2>/dev/null || echo 0)
VOLTAGE_MV=$((VOLTAGE / 1000))
VOLTAGE_V=$(echo "scale=3; $VOLTAGE_MV / 1000" | bc)
CAPACITY=$(cat "$BAT/capacity" 2>/dev/null || echo "?")
STATUS=$(cat "$BAT/status" 2>/dev/null || echo "?")
HEALTH=$(cat "$BAT/health" 2>/dev/null || echo "?")
UPTIME=$(awk '{print int($1)}' /proc/uptime)

# Check for previous failed boots via journal
FAILS=$(journalctl -b -1 --no-pager 2>/dev/null | grep -ciE 'panic|oops|emergency|failed to start' || echo 0)

echo "[$( date -Iseconds)] BOOT: voltage=${VOLTAGE_V}V capacity=${CAPACITY}% status=${STATUS} health=${HEALTH} uptime=${UPTIME}s prev_boot_errors=${FAILS}" >> "$LOG"

# Log any failed services
FAILED_UNITS=$(systemctl --failed --no-legend 2>/dev/null)
if [ -n "$FAILED_UNITS" ]; then
    echo "[$(date -Iseconds)] BOOT-FAILURES: $FAILED_UNITS" >> "$LOG"
fi
