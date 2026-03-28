#!/bin/bash
# Fix uConsole false shutdown caused by AXP228 PMU undervoltage cutoff
# Lowers V_OFF from 3.3V (default) to 2.9V via udev rule (persists across reboots)
#
# Usage:
#   curl -fsSL https://uconsole.cloud/scripts/fix-voltage-cutoff.sh | sudo bash
#
# What this does:
#   1. Installs a udev rule that sets voltage_min=2.9V on every boot
#   2. Applies the fix immediately (no reboot required)
#
# Why:
#   The AXP228 PMU defaults to a 3.3V undervoltage cutoff. 18650 cells sag below
#   3.3V under load (especially during cold boot inrush), causing the PMU to kill
#   power — even when the cells have plenty of charge. 2.9V is safe for 18650s
#   (their actual low-voltage cutoff is ~2.5V).
#
# Safe to run multiple times. Revert by removing the udev rule:
#   sudo rm /etc/udev/rules.d/99-uconsole-battery.rules && sudo udevadm control --reload-rules

set -euo pipefail

RULE_FILE="/etc/udev/rules.d/99-uconsole-battery.rules"
VMIN_PATH="/sys/class/power_supply/axp20x-battery/voltage_min_design"

# Check we're on a uConsole with an AXP PMU
if [ ! -d /sys/class/power_supply/axp20x-battery ]; then
    echo "ERROR: AXP20x battery not found — is this a uConsole?" >&2
    exit 1
fi

# Must be root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run with sudo" >&2
    exit 1
fi

# Install udev rule (persists across reboots)
cat > "$RULE_FILE" <<'EOF'
KERNEL=="axp20x-battery", ATTR{constant_charge_current_max}="900000", ATTR{constant_charge_current}="900000", ATTR{voltage_min}="2900000"
EOF

udevadm control --reload-rules

# Apply immediately
echo 2900000 > "$VMIN_PATH"

# Verify
ACTUAL=$(cat "$VMIN_PATH")
if [ "$ACTUAL" -ge 2900000 ] && [ "$ACTUAL" -le 2910000 ]; then
    echo "Fixed! Undervoltage cutoff lowered to 2.9V (reads ${ACTUAL}µV due to register granularity)"
    echo "Udev rule installed at $RULE_FILE — persists across reboots"
    echo ""
    echo "To revert: sudo rm $RULE_FILE && sudo udevadm control --reload-rules"
else
    echo "ERROR: voltage_min_design is $ACTUAL, expected ~2900000" >&2
    exit 1
fi
