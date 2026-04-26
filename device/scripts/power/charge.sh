#!/bin/bash
# Set battery charge current on the uConsole (AXP228 PMU)
# Usage: charge.sh <milliamps>
# Example: charge.sh 900
#
# The AXP228 driver accepts values in microamps and caps at 900mA.
# Common values: 300 (gentle), 500 (moderate), 900 (max)

set -euo pipefail

if [ -z "${1:-}" ]; then
    current_ua=$(cat /sys/class/power_supply/axp20x-battery/constant_charge_current 2>/dev/null || echo "0")
    current_ma=$((current_ua / 1000))
    echo "Current charge rate: ${current_ma}mA"
    echo ""
    echo "Usage: charge.sh <milliamps>"
    echo "  charge.sh 300    Gentle (300mA)"
    echo "  charge.sh 500    Moderate (500mA)"
    echo "  charge.sh 900    Maximum (900mA)"
    exit 0
fi

ua=$(($1 * 1000))

if [ "$ua" -lt 100000 ] || [ "$ua" -gt 900000 ]; then
    echo "Error: value must be between 100 and 900 mA"
    exit 1
fi

echo "$ua" | sudo tee /sys/class/power_supply/axp20x-battery/constant_charge_current_max > /dev/null
echo "$ua" | sudo tee /sys/class/power_supply/axp20x-battery/constant_charge_current > /dev/null

actual_ua=$(cat /sys/class/power_supply/axp20x-battery/constant_charge_current)
actual_ma=$((actual_ua / 1000))
echo "Charge rate set to ${actual_ma}mA"
