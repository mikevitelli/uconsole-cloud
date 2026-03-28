#!/bin/bash
# Network analysis for the uConsole
# Usage: network.sh              Connection overview
#        network.sh speed         Download/upload speed test
#        network.sh scan          Scan nearby Wi-Fi networks
#        network.sh ping [host]   Latency test (default: 1.1.1.1)
#        network.sh trace [host]  Traceroute to host
#        network.sh watch         Live signal monitor (updates every 3s)
#        network.sh log           Append timestamped entry to ~/network.log

source "$(dirname "$0")/lib.sh"

IFACE="wlan0"

# --- helpers ---

signal_bar() {
    local quality=$1 max=$2 bar_len=20
    local filled=$((quality * bar_len / max))
    local empty=$((bar_len - filled))
    [ "$filled" -lt 0 ] && filled=0
    [ "$filled" -gt "$bar_len" ] && filled=$bar_len
    printf '%0.s█' $(seq 1 $filled 2>/dev/null)
    printf '%0.s░' $(seq 1 $empty 2>/dev/null)
}

signal_rating() {
    local dbm=$1
    if [ "$dbm" -ge -50 ]; then echo "Excellent"
    elif [ "$dbm" -ge -60 ]; then echo "Good"
    elif [ "$dbm" -ge -70 ]; then echo "Fair"
    elif [ "$dbm" -ge -80 ]; then echo "Weak"
    else echo "Very weak"
    fi
}

get_wifi_info() {
    iw_out=$(iwconfig "$IFACE" 2>/dev/null)
    ssid=$(echo "$iw_out" | grep -oP 'ESSID:"\K[^"]+')
    freq=$(echo "$iw_out" | grep -oP 'Frequency:\K[\d.]+')
    bitrate=$(echo "$iw_out" | grep -oP 'Bit Rate=\K[\d.]+')
    txpower=$(echo "$iw_out" | grep -oP 'Tx-Power=\K[\d]+')
    quality=$(echo "$iw_out" | grep -oP 'Link Quality=\K\d+')
    quality_max=$(echo "$iw_out" | grep -oP 'Link Quality=\d+/\K\d+')
    signal_dbm=$(echo "$iw_out" | grep -oP 'Signal level=\K[-\d]+')
    ap=$(echo "$iw_out" | grep -oP 'Access Point: \K[^\s]+')
    powermgmt=$(echo "$iw_out" | grep -oP 'Power Management:\K\w+')

    ip_addr=$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}')
    gateway=$(ip route show default dev "$IFACE" 2>/dev/null | awk '{print $3}')
    dns=$(grep -m1 'nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}')
    mac=$(cat /sys/class/net/"$IFACE"/address 2>/dev/null)

    # antenna — read from boot config
    if grep -q '^dtparam=ant2' /boot/config.txt 2>/dev/null; then
        antenna="External (ant2)"
    elif grep -q '^dtparam=ant1' /boot/config.txt 2>/dev/null; then
        antenna="Internal (ant1)"
    else
        antenna="Default"
    fi
}

# --- commands ---

cmd_overview() {
    get_wifi_info

    local rating=$(signal_rating "$signal_dbm")
    local bar=$(signal_bar "$quality" "$quality_max")

    # band detection
    local band="2.4 GHz"
    if [ -n "$freq" ] && awk "BEGIN {exit !($freq > 5.0)}"; then
        band="5 GHz"
    fi

    # internet check
    local internet="No"
    if ping -c1 -W2 1.1.1.1 &>/dev/null; then
        internet="Yes"
    fi

    echo "┌─────────────────────────────────────────┐"
    echo "│          uConsole Network Report         │"
    echo "├─────────────────────────────────────────┤"
    printf "│  SSID:      %-28s│\n" "${ssid:-(disconnected)}"
    printf "│  Band:      %-28s│\n" "$band ($freq GHz)"
    printf "│  AP:        %-28s│\n" "${ap:-—}"
    printf "│  Internet:  %-28s│\n" "$internet"
    echo "├─────────────────────────────────────────┤"
    printf "│  Signal:    %-3s dBm  [%s] │\n" "$signal_dbm" "$bar"
    printf "│  Quality:   %-28s│\n" "$quality/$quality_max ($rating)"
    printf "│  Bit rate:  %-28s│\n" "${bitrate} Mbit/s"
    printf "│  Tx power:  %-28s│\n" "${txpower} dBm"
    printf "│  Antenna:  %-28s│\n" "$antenna"
    printf "│  Power mgmt: %-27s│\n" "$powermgmt"
    echo "├─────────────────────────────────────────┤"
    printf "│  IP:        %-28s│\n" "${ip_addr:-—}"
    printf "│  Gateway:   %-28s│\n" "${gateway:-—}"
    printf "│  DNS:       %-28s│\n" "${dns:-—}"
    printf "│  MAC:       %-28s│\n" "${mac:-—}"
    echo "└─────────────────────────────────────────┘"
}

cmd_speed() {
    if command -v speedtest-cli &>/dev/null; then
        echo "Running speedtest-cli..."
        echo ""
        speedtest-cli --simple
    else
        echo "Running speed test (curl fallback)..."
        echo ""

        # download test — fetch a 10MB file from Cloudflare
        echo "Download:"
        dl_result=$(curl -o /dev/null -w '%{speed_download} %{time_total}' -s \
            'https://speed.cloudflare.com/__down?bytes=10000000' 2>/dev/null)
        dl_speed=$(echo "$dl_result" | awk '{printf "%.1f", $1 / 1000000 * 8}')
        dl_time=$(echo "$dl_result" | awk '{printf "%.1f", $2}')
        echo "  ${dl_speed} Mbit/s (10MB in ${dl_time}s)"

        echo ""

        # upload test — push 2MB of zeros to Cloudflare
        echo "Upload:"
        ul_result=$(dd if=/dev/zero bs=1M count=2 2>/dev/null | \
            curl -o /dev/null -w '%{speed_upload} %{time_total}' -s \
            -X POST --data-binary @- \
            'https://speed.cloudflare.com/__up' 2>/dev/null)
        ul_speed=$(echo "$ul_result" | awk '{printf "%.1f", $1 / 1000000 * 8}')
        ul_time=$(echo "$ul_result" | awk '{printf "%.1f", $2}')
        echo "  ${ul_speed} Mbit/s (2MB in ${ul_time}s)"

        echo ""

        # latency
        echo "Latency:"
        ping_result=$(ping -c5 -q 1.1.1.1 2>/dev/null | tail -1)
        if [ -n "$ping_result" ]; then
            avg=$(echo "$ping_result" | cut -d'/' -f5)
            echo "  ${avg}ms avg (5 pings to 1.1.1.1)"
        else
            echo "  Could not reach 1.1.1.1"
        fi
    fi
}

cmd_scan() {
    echo "Scanning Wi-Fi networks..."
    echo ""
    printf "%-4s  %-30s  %-6s  %-10s  %-12s\n" "SIG" "SSID" "SIGNAL" "FREQ" "RATE"
    printf "%-4s  %-30s  %-6s  %-10s  %-12s\n" "----" "------------------------------" "------" "----------" "------------"
    nmcli -t -f active,ssid,signal,freq,rate dev wifi list 2>/dev/null | sort -t: -k3 -rn | while IFS=: read -r active ssid signal freq rate; do
        if [ "$active" = "yes" ]; then
            marker=" *"
        else
            marker="  "
        fi
        bar_len=4
        filled=$((signal * bar_len / 100))
        bar=$(printf '%0.s█' $(seq 1 $filled 2>/dev/null))$(printf '%0.s░' $(seq 1 $((bar_len - filled)) 2>/dev/null))
        printf "%s  %-30s  %-4s%%  %-10s  %-12s\n" "$bar" "${ssid:-(hidden)}" "$signal" "$freq" "$rate"
    done
}

cmd_ping() {
    local host="${1:-1.1.1.1}"
    echo "Pinging $host..."
    echo ""
    ping -c 10 "$host" 2>/dev/null
}

cmd_trace() {
    local host="${1:-1.1.1.1}"
    if command -v traceroute &>/dev/null; then
        traceroute -m 20 "$host"
    else
        echo "traceroute not installed. Using ping-based trace:"
        for ttl in $(seq 1 20); do
            result=$(ping -c1 -W2 -t "$ttl" "$host" 2>/dev/null | head -2 | tail -1)
            printf "%2d  %s\n" "$ttl" "$result"
            echo "$result" | grep -q "from $host" && break
        done
    fi
}

cmd_watch() {
    while true; do
        clear
        get_wifi_info
        local bar=$(signal_bar "$quality" "$quality_max")
        local rating=$(signal_rating "$signal_dbm")
        local timestamp=$(date '+%H:%M:%S')

        echo "┌─────────────────────────────────────────┐"
        echo "│        Wi-Fi Signal Monitor  [$timestamp] │"
        echo "├─────────────────────────────────────────┤"
        printf "│  SSID:    %-30s│\n" "$ssid"
        printf "│  Signal:  %-3s dBm  [%s] │\n" "$signal_dbm" "$bar"
        printf "│  Quality: %-30s│\n" "$quality/$quality_max ($rating)"
        printf "│  Rate:    %-30s│\n" "${bitrate} Mbit/s"
        echo "└─────────────────────────────────────────┘"
        echo ""
        echo "  Refreshing every 3s... (Ctrl+C to stop)"
        sleep 3
    done
}

cmd_log() {
    get_wifi_info
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp | $ssid | ${signal_dbm}dBm | ${quality}/${quality_max} | ${bitrate}Mbit/s | ${ip_addr}" >> ~/network.log
    echo "Logged to ~/network.log"
}

# --- main ---

case "${1:-}" in
    speed)   cmd_speed ;;
    scan)    cmd_scan ;;
    ping)    cmd_ping "$2" ;;
    trace)   cmd_trace "$2" ;;
    watch)   cmd_watch ;;
    log)     cmd_log ;;
    *)       cmd_overview ;;
esac
