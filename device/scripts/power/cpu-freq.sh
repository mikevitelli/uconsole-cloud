#!/bin/bash
# Get / set CPU min and max scaling frequencies on the uConsole.
#
# Usage:
#   cpu-freq.sh                   # show current state
#   cpu-freq.sh min <MHz>         # set scaling_min_freq (e.g. 1500..2400)
#   cpu-freq.sh max <MHz>         # set scaling_max_freq
#   cpu-freq.sh preset <name>     # apply preset: battery|balanced|performance|max
#
# Presets (min/max in MHz):
#   battery       1500 / 1500   (lock to lowest)
#   balanced      1500 / 2000   (range, ondemand)
#   performance   1800 / 2400   (higher floor, max ceiling)
#   max           2400 / 2400   (lock to max — burns power, fastest)

set -euo pipefail

CPU_MIN=/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq
CPU_MAX=/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq
GOV=/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
CUR=/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq

# Helpers
khz_to_mhz() { echo $(( $1 / 1000 )); }
mhz_to_khz() { echo $(( $1 * 1000 )); }

show_state() {
    echo "CPU frequency state"
    echo "==================="
    echo "Governor : $(cat "$GOV")"
    echo "Min      : $(khz_to_mhz "$(cat "$CPU_MIN")") MHz"
    echo "Max      : $(khz_to_mhz "$(cat "$CPU_MAX")") MHz"
    if [ -r "$CUR" ]; then
        echo "Current  : $(khz_to_mhz "$(cat "$CUR")") MHz"
    fi
    echo ""
    echo "Available: $(tr ' ' '\n' < /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies | awk 'NF{print $1/1000}' | tr '\n' ' ')MHz"
}

write_freq() {
    local target="$1"     # "min" or "max"
    local mhz="$2"
    local khz; khz=$(mhz_to_khz "$mhz")
    local path; [ "$target" = "min" ] && path="$CPU_MIN" || path="$CPU_MAX"
    if [ -w "$path" ]; then
        echo "$khz" > "$path"
    else
        echo "$khz" | sudo tee "$path" > /dev/null
    fi
}

apply_preset() {
    case "$1" in
        battery)     write_freq min 1500; write_freq max 1500 ;;
        balanced)    write_freq min 1500; write_freq max 2000 ;;
        performance) write_freq min 1800; write_freq max 2400 ;;
        max)         write_freq min 2400; write_freq max 2400 ;;
        *) echo "Unknown preset: $1"; echo "Valid: battery|balanced|performance|max"; exit 1 ;;
    esac
    echo "Applied preset: $1"
    echo ""
    show_state
}

case "${1:-}" in
    "")        show_state ;;
    min)       [ -n "${2:-}" ] || { echo "Usage: cpu-freq.sh min <MHz>"; exit 1; }; write_freq min "$2"; show_state ;;
    max)       [ -n "${2:-}" ] || { echo "Usage: cpu-freq.sh max <MHz>"; exit 1; }; write_freq max "$2"; show_state ;;
    preset)    [ -n "${2:-}" ] || { echo "Usage: cpu-freq.sh preset <name>"; exit 1; }; apply_preset "$2" ;;
    *)         echo "Unknown command: $1"; echo "Usage: cpu-freq.sh [min|max <MHz> | preset <name>]"; exit 1 ;;
esac
