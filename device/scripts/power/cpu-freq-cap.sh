#!/bin/bash
# Cap CPU frequency to 1.2GHz to reduce voltage sag on battery
# Default max is 1.5GHz which causes current spikes that can trigger PMU cutoff

set -euo pipefail

FREQ_PATH="/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq"

if [ ! -w "$FREQ_PATH" ]; then
    echo 1200000 | sudo tee "$FREQ_PATH" > /dev/null
else
    echo 1200000 > "$FREQ_PATH"
fi
