#!/bin/bash
# uConsole Terminal Dashboard
# Usage: dashboard.sh          Status overview + script launcher
#        dashboard.sh status   Status only (no menu)

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

source "$(dirname "$0")/lib.sh"

# ── data collection ──

gather_stats() {
    # uptime
    uptime_secs=$(awk '{print int($1)}' /proc/uptime)
    uptime_days=$((uptime_secs / 86400))
    uptime_hrs=$(( (uptime_secs % 86400) / 3600 ))
    uptime_mins=$(( (uptime_secs % 3600) / 60 ))
    if [ "$uptime_days" -gt 0 ]; then
        uptime_str="${uptime_days}d ${uptime_hrs}h ${uptime_mins}m"
    else
        uptime_str="${uptime_hrs}h ${uptime_mins}m"
    fi

    # cpu
    cpu_temp_raw=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
    cpu_temp=$(awk "BEGIN {printf \"%.0f\", $cpu_temp_raw / 1000}")
    cpu_freq_raw=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)
    cpu_freq=$((cpu_freq_raw / 1000))
    cpu_gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
    cpu_usage=$(awk '/^cpu /{u=$2+$4; t=$2+$3+$4+$5+$6+$7+$8; printf "%.0f", u*100/t}' /proc/stat)

    # memory
    mem_total=$(free -m | awk '/Mem:/{print $2}')
    mem_used=$(free -m | awk '/Mem:/{print $3}')
    mem_pct=$((mem_used * 100 / mem_total))

    # disk
    disk_total=$(df -BG / | awk 'NR==2{gsub("G",""); print $2}')
    disk_used=$(df -BG / | awk 'NR==2{gsub("G",""); print $3}')
    disk_pct=$(df / | awk 'NR==2{gsub("%",""); print $5}')

    # battery (from lib.sh)
    read_battery
    bat_status="$BAT_STATUS"
    bat_capacity="$BAT_CAPACITY"
    bat_voltage="$(awk "BEGIN {printf \"%.2f\", $BAT_VOLTAGE_UA / 1000000}")"
    bat_current="$BAT_CURRENT_MA"
    bat_charge_rate="$BAT_CHARGE_RATE_MA"
    ac_online="$BAT_AC_ONLINE"

    # wifi
    iw_out=$(iwconfig wlan0 2>/dev/null)
    wifi_ssid=$(echo "$iw_out" | grep -oP 'ESSID:"\K[^"]+')
    wifi_signal=$(echo "$iw_out" | grep -oP 'Signal level=\K[-\d]+')
    wifi_quality=$(echo "$iw_out" | grep -oP 'Link Quality=\K\d+')
    wifi_quality_max=$(echo "$iw_out" | grep -oP 'Link Quality=\d+/\K\d+')
    wifi_rate=$(echo "$iw_out" | grep -oP 'Bit Rate=\K[\d.]+')
    wifi_ip=$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)

    # antenna
    if grep -q '^dtparam=ant2' /boot/config.txt 2>/dev/null; then
        wifi_antenna="ext"
    else
        wifi_antenna="int"
    fi

    # time
    timestamp=$(date '+%H:%M:%S')
    datestr=$(date '+%a %b %d')
}

# ── display ──

print_status() {
    gather_stats

    # battery icon
    if [ "$ac_online" = "1" ]; then
        bat_icon="AC"
    else
        bat_icon="DC"
    fi

    printf "${BOLD}${CYAN}"
    echo "  _   _  ___                      _       "
    echo " | | | |/ __|___ _ _  ___ ___| |___   "
    echo " | |_| | (__/ _ \\ ' \\(_-</ _ \\ / -_)  "
    echo "  \\___/ \\___\\___/_||_/__/\\___/_\\___|  "
    printf "${RESET}"
    printf "  ${DIM}%s  %s  up %s${RESET}\n" "$datestr" "$timestamp" "$uptime_str"
    echo ""

    # ── system row ──
    printf "  ${BOLD}CPU${RESET}  %3s%% " "$cpu_usage"
    bar "$cpu_usage" 100 12
    printf "  ${DIM}%sMHz %s %s°C${RESET}\n" "$cpu_freq" "$cpu_gov" "$cpu_temp"

    printf "  ${BOLD}MEM${RESET}  %3s%% " "$mem_pct"
    bar "$mem_pct" 100 12
    printf "  ${DIM}%s/%sM${RESET}\n" "$mem_used" "$mem_total"

    printf "  ${BOLD}DSK${RESET}  %3s%% " "$disk_pct"
    bar "$disk_pct" 100 12
    printf "  ${DIM}%s/%sG${RESET}\n" "$disk_used" "$disk_total"

    echo ""

    # ── battery row ──
    printf "  ${BOLD}BAT${RESET}  %3s%% " "$bat_capacity"
    bar_inv "$bat_capacity" 100 12
    printf "  ${DIM}%sV %smA [%s] %s${RESET}\n" "$bat_voltage" "$bat_current" "$bat_icon" "$bat_status"

    printf "  ${BOLD}CHG${RESET}       "
    printf "               ${DIM}rate: %smA${RESET}\n" "$bat_charge_rate"

    echo ""

    # ── network row ──
    local wifi_quality_pct=0
    if [ -n "$wifi_quality" ] && [ -n "$wifi_quality_max" ] && [ "$wifi_quality_max" -gt 0 ]; then
        wifi_quality_pct=$((wifi_quality * 100 / wifi_quality_max))
    fi

    printf "  ${BOLD}NET${RESET}  %3s%% " "$wifi_quality_pct"
    bar_inv "$wifi_quality_pct" 100 12
    printf "  ${DIM}%sdBm %sMbit/s [%s]${RESET}\n" "$wifi_signal" "$wifi_rate" "$wifi_antenna"

    printf "       ${DIM}%-20s  %s${RESET}\n" "$wifi_ssid" "$wifi_ip"
}

print_menu() {
    echo ""
    printf "  ${BOLD}${BLUE}── Scripts ──────────────────────────────${RESET}\n"
    echo ""

    local i=1
    declare -gA script_map

    for script in "$SCRIPTS_DIR"/*.sh; do
        [ "$script" = "$SCRIPTS_DIR/dashboard.sh" ] && continue
        [ "$script" = "$SCRIPTS_DIR/myscript.sh" ] && continue
        local name=$(basename "$script" .sh)
        local desc=$(head -3 "$script" | grep -oP '(?<=# ).*' | head -1)
        script_map[$i]="$script"
        printf "  ${BOLD}${GREEN}%d${RESET}  %-12s ${DIM}%s${RESET}\n" "$i" "$name" "$desc"
        i=$((i + 1))
    done

    script_count=$((i - 1))

    echo ""
    printf "  ${BOLD}${GREEN}r${RESET}  %-12s ${DIM}%s${RESET}\n" "refresh" "Refresh dashboard"
    printf "  ${BOLD}${GREEN}q${RESET}  %-12s ${DIM}%s${RESET}\n" "quit" "Exit"
    echo ""
}

run_interactive() {
    while true; do
        clear
        print_status
        print_menu

        printf "  ${BOLD}>${RESET} "
        read -r choice

        case "$choice" in
            q|Q|quit|exit)
                clear
                exit 0
                ;;
            r|R|"")
                continue
                ;;
            [0-9]*)
                if [ -n "${script_map[$choice]}" ]; then
                    clear
                    local script="${script_map[$choice]}"
                    local name=$(basename "$script" .sh)
                    printf "${BOLD}${CYAN}── %s ──${RESET}\n\n" "$name"

                    # show usage and prompt for args
                    local usage=$(grep -oP '(?<=# Usage: )\S+ +\K.*' "$script" 2>/dev/null | head -5)
                    if [ -n "$usage" ]; then
                        printf "${DIM}Usage:%s${RESET}\n" ""
                        grep '# Usage:\|#        ' "$script" 2>/dev/null | sed 's/^#  */  /' | head -8
                        echo ""
                    fi

                    printf "  Args (or Enter for none): "
                    read -r args
                    echo ""
                    bash "$script" $args  # args intentionally unquoted for word splitting
                    echo ""
                    printf "${DIM}  Press Enter to return...${RESET}"
                    read -r
                else
                    echo "  Invalid selection"
                    sleep 1
                fi
                ;;
            *)
                echo "  Invalid selection"
                sleep 1
                ;;
        esac
    done
}

# ── main ──

case "${1:-}" in
    status)
        print_status
        ;;
    *)
        run_interactive
        ;;
esac
