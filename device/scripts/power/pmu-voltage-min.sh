#!/bin/bash
# Lower AXP228 PMU undervoltage cutoff to 2.9V
# Default is 3.3V which causes false shutdowns during voltage sag

set -euo pipefail

VMIN_PATH="/sys/class/power_supply/axp20x-battery/voltage_min"

# Wait for AXP driver to create the sysfs path (up to 30s)
for i in $(seq 1 30); do
    [ -e "$VMIN_PATH" ] && break
    sleep 1
done

if [ ! -e "$VMIN_PATH" ]; then
    echo "ERROR: $VMIN_PATH not found after 30s" >&2
    exit 1
fi

if [ -w "$VMIN_PATH" ]; then
    echo 2900000 > "$VMIN_PATH"
else
    echo 2900000 | sudo tee "$VMIN_PATH" > /dev/null
fi

# Verify the write
ACTUAL=$(cat "$VMIN_PATH")
if [ "$ACTUAL" != "2900000" ]; then
    echo "ERROR: voltage_min is $ACTUAL, expected 2900000" >&2
    exit 1
fi
echo "voltage_min set to 2.9V successfully"
