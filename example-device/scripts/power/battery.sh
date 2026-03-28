#!/bin/bash
# Battery analysis for the uConsole (AXP228 PMU)
# Usage: battery.sh          One-time snapshot
#        battery.sh watch     Live monitor (updates every 5s)
#        battery.sh log       Append a timestamped entry to ~/battery.log

source "$(dirname "$0")/lib.sh"

read_bat() {
    # get base readings from lib.sh
    read_battery

    # map to local variable names for compatibility
    status="$BAT_STATUS"
    capacity="$BAT_CAPACITY"
    voltage_ua="$BAT_VOLTAGE_UA"
    current_ua="$BAT_CURRENT_UA"
    voltage_mv="$BAT_VOLTAGE_MV"
    voltage_v="$BAT_VOLTAGE_V"
    current_ma="$BAT_CURRENT_MA"
    charge_rate_ma="$BAT_CHARGE_RATE_MA"
    charge_max_ma="$BAT_CHARGE_MAX_MA"
    power_mw="$BAT_POWER_MW"
    health="$BAT_HEALTH"
    present="$BAT_PRESENT"
    ac_online="$BAT_AC_ONLINE"
    energy_full="$BAT_ENERGY_FULL"
    source_str="$BAT_SOURCE"

    # voltage-based capacity estimate (more reliable than the fuel gauge at extremes)
    # Nitecore NL1834 3400mAh — measured under ~1A load (2026-03-27)
    # 3.0V=0%, 3.2V=50%, 3.3V=60%, 3.4V=70%, 3.6V=80%, 3.8V=90%, 4.05V=100%
    if [ "$voltage_ua" -le 3000000 ]; then
        vest=0
    elif [ "$voltage_ua" -ge 4050000 ]; then
        vest=100
    else
        vest=$(awk "BEGIN {
            v = $voltage_ua / 1000000
            # piecewise linear — calibrated from nitecore-3400 discharge test
            if (v < 3.1) printf \"%d\", (v - 3.0) / 0.1 * 15
            else if (v < 3.2) printf \"%d\", 15 + (v - 3.1) / 0.1 * 35
            else if (v < 3.3) printf \"%d\", 50 + (v - 3.2) / 0.1 * 10
            else if (v < 3.4) printf \"%d\", 60 + (v - 3.3) / 0.1 * 10
            else if (v < 3.6) printf \"%d\", 70 + (v - 3.4) / 0.2 * 10
            else if (v < 3.8) printf \"%d\", 80 + (v - 3.6) / 0.2 * 10
            else printf \"%d\", 90 + (v - 3.8) / 0.25 * 10
        }")
    fi

    # pick best source: vest% when discharging (accurate), capacity% when charging (voltage inflated)
    if [ "$status" = "Discharging" ]; then
        display_pct=$vest
    else
        display_pct=$capacity
    fi

    # time estimate
    if [ "$status" = "Charging" ] && [ "$current_ma" -gt 0 ]; then
        remaining_pct=$((100 - display_pct))
        if [ "$remaining_pct" -gt 0 ] && [ "$power_mw" -gt 0 ]; then
            remaining_uwh=$((energy_full * remaining_pct / 100))
            mins=$((remaining_uwh / 1000 * 60 / power_mw))
            hours=$((mins / 60))
            mins=$((mins % 60))
            time_est="${hours}h ${mins}m to full"
        else
            time_est="calculating..."
        fi
    elif [ "$status" = "Discharging" ]; then
        local abs_power=${power_mw#-}
        if [ "$display_pct" -gt 0 ] && [ "$abs_power" -gt 0 ]; then
            remaining_uwh=$((energy_full * display_pct / 100))
            mins=$((remaining_uwh / 1000 * 60 / abs_power))
            hours=$((mins / 60))
            mins=$((mins % 60))
            time_est="${hours}h ${mins}m remaining"
        else
            time_est="calculating..."
        fi
    else
        time_est="—"
    fi

    # health bar
    bar_len=20
    filled=$((display_pct * bar_len / 100))
    empty=$((bar_len - filled))
    bar=""
    if [ "$filled" -gt 0 ]; then
        bar=$(printf '%0.s█' $(seq 1 $filled))
    fi
    if [ "$empty" -gt 0 ]; then
        bar="${bar}$(printf '%0.s░' $(seq 1 $empty))"
    fi
}

print_report() {
    read_bat

    cpu_temp_raw=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
    cpu_temp=""
    if [ -n "$cpu_temp_raw" ]; then
        cpu_temp=$(awk "BEGIN {printf \"%.1f\", $cpu_temp_raw / 1000}")
    fi

    echo "┌─────────────────────────────────────────┐"
    echo "│          uConsole Battery Report         │"
    echo "├─────────────────────────────────────────┤"
    printf "│  Status:    %-28s│\n" "$status"
    printf "│  Source:    %-28s│\n" "$source_str"
    printf "│  Health:    %-28s│\n" "$health"
    echo "├─────────────────────────────────────────┤"
    printf "│  Charge:    %-3s%%  [%s] │\n" "$display_pct" "$bar"
    if [ "$status" = "Discharging" ]; then
        printf "│  Gauge:     %-28s│\n" "${capacity}% (AXP228 fuel gauge)"
    else
        printf "│  Vest:      %-28s│\n" "~${vest}% (voltage-based)"
    fi
    printf "│  Voltage:   %-28s│\n" "${voltage_v}V"
    printf "│  Current:   %-28s│\n" "${current_ma}mA"
    printf "│  Power:     %-28s│\n" "${power_mw}mW"
    echo "├─────────────────────────────────────────┤"
    printf "│  Charge rate:    %-23s│\n" "${charge_rate_ma}mA / ${charge_max_ma}mA max"
    printf "│  Time:           %-23s│\n" "$time_est"
    if [ -n "$cpu_temp" ]; then
        printf "│  CPU temp:       %-23s│\n" "${cpu_temp}C"
    fi
    echo "└─────────────────────────────────────────┘"
}

case "${1:-}" in
    watch)
        while true; do
            clear
            print_report
            echo ""
            echo "  Refreshing every 5s... (Ctrl+C to stop)"
            sleep 5
        done
        ;;
    log)
        read_bat
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "$timestamp | ${vest}% vest | ${capacity}% gauge | ${voltage_v}V | ${current_ma}mA | ${power_mw}mW | ${status} | charge_rate=${charge_rate_ma}mA" >> ~/battery.log
        echo "Logged to ~/battery.log"
        ;;
    *)
        print_report
        ;;
esac
