#!/bin/bash
# Storage devices and health for the uConsole
# Usage: storage.sh             Overview of all storage devices
#        storage.sh devices     Block device tree
#        storage.sh io          Live I/O stats (updates every 3s)
#        storage.sh smart       SD card / drive health info
#        storage.sh usb         USB storage devices
#        storage.sh mount       Mount points and filesystem details
#        storage.sh temp        Storage temperature sensors

source "$(dirname "$0")/lib.sh"

fmt_bytes() {
    local bytes=$1
    [ "$bytes" -lt 0 ] && bytes=0
    if [ "$bytes" -ge 1073741824 ]; then
        awk "BEGIN {printf \"%.1fG\", $bytes / 1073741824}"
    elif [ "$bytes" -ge 1048576 ]; then
        awk "BEGIN {printf \"%.1fM\", $bytes / 1048576}"
    elif [ "$bytes" -ge 1024 ]; then
        awk "BEGIN {printf \"%.1fK\", $bytes / 1024}"
    else
        echo "${bytes}B"
    fi
}

cmd_overview() {
    echo "┌─────────────────────────────────────────┐"
    echo "│        uConsole Storage Overview         │"
    echo "├─────────────────────────────────────────┤"

    # mounted filesystems with usage
    echo "│  Filesystems                            │"
    echo "├─────────────────────────────────────────┤"

    df -h -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | awk 'NR>1' | while read -r dev size used avail pct mount; do
        pct_num=${pct%\%}
        printf "│  %-10s %5s / %-5s " "$mount" "$used" "$size"
        bar "$pct_num" 100 8
        printf " %4s │\n" "$pct"
    done

    echo "├─────────────────────────────────────────┤"

    # block devices summary
    echo "│  Block Devices                          │"
    echo "├─────────────────────────────────────────┤"

    lsblk -dno NAME,SIZE,TYPE,MODEL 2>/dev/null | grep -v '^loop' | while read -r name size type model; do
        printf "│  %-8s %-6s %-6s %-16s│\n" "$name" "$size" "$type" "$model"
    done

    echo "├─────────────────────────────────────────┤"

    # I/O snapshot
    echo "│  I/O Activity                           │"
    echo "├─────────────────────────────────────────┤"

    for dev in $(lsblk -dno NAME 2>/dev/null | grep -v '^loop'); do
        stat_file="/sys/block/$dev/stat"
        [ -f "$stat_file" ] || continue
        read -r rd _ _ _ wr _ _ _ inflight _ _ _ _ < "$stat_file"
        printf "│  %-8s R: %-8s  W: %-8s    │\n" "$dev" "$(fmt_bytes $((rd * 512)))" "$(fmt_bytes $((wr * 512)))"
    done

    echo "├─────────────────────────────────────────┤"

    # USB storage
    usb_count=$(lsblk -o NAME,TRAN 2>/dev/null | grep -c 'usb' || true)
    printf "│  USB storage devices: %-18s│\n" "$usb_count"

    # SD card info
    sd_cid="/sys/block/mmcblk0/device/cid"
    if [ -f "$sd_cid" ]; then
        sd_name=$(cat /sys/block/mmcblk0/device/name 2>/dev/null)
        sd_date=$(cat /sys/block/mmcblk0/device/date 2>/dev/null)
        printf "│  SD card:  %-29s│\n" "$sd_name (mfg $sd_date)"
    fi

    echo "└─────────────────────────────────────────┘"
}

cmd_devices() {
    printf "${BOLD}${CYAN}Block Device Tree${RESET}\n\n"
    lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL,SERIAL,TRAN 2>/dev/null
    echo ""

    # SD card details
    if [ -d /sys/block/mmcblk0/device ]; then
        printf "${BOLD}${CYAN}SD Card Details${RESET}\n\n"
        printf "  %-14s %s\n" "Name:" "$(cat /sys/block/mmcblk0/device/name 2>/dev/null)"
        printf "  %-14s %s\n" "Type:" "$(cat /sys/block/mmcblk0/device/type 2>/dev/null)"
        printf "  %-14s %s\n" "Date:" "$(cat /sys/block/mmcblk0/device/date 2>/dev/null)"
        printf "  %-14s %s\n" "Serial:" "$(cat /sys/block/mmcblk0/device/serial 2>/dev/null)"
        printf "  %-14s %s\n" "CID:" "$(cat /sys/block/mmcblk0/device/cid 2>/dev/null)"
        printf "  %-14s %s\n" "CSD:" "$(cat /sys/block/mmcblk0/device/csd 2>/dev/null)"
        printf "  %-14s %s\n" "FW Rev:" "$(cat /sys/block/mmcblk0/device/fwrev 2>/dev/null)"
        printf "  %-14s %s\n" "HW Rev:" "$(cat /sys/block/mmcblk0/device/hwrev 2>/dev/null)"
        printf "  %-14s %s\n" "Pref erase:" "$(cat /sys/block/mmcblk0/device/preferred_erase_size 2>/dev/null)"

        # life time estimate (eMMC/SD wear)
        if [ -f /sys/block/mmcblk0/device/life_time ]; then
            printf "  %-14s %s\n" "Life time:" "$(cat /sys/block/mmcblk0/device/life_time 2>/dev/null)"
        fi
    fi
}

cmd_io() {
    printf "${BOLD}${CYAN}Live I/O Stats${RESET}  (Ctrl+C to stop)\n\n"

    # header
    printf "  ${BOLD}%-8s  %10s  %10s  %8s${RESET}\n" "DEVICE" "READ/s" "WRITE/s" "INFLIGHT"
    printf "  %-8s  %10s  %10s  %8s\n" "--------" "----------" "----------" "--------"

    declare -A prev_rd prev_wr
    for dev in $(lsblk -dno NAME 2>/dev/null | grep -v '^loop'); do
        stat_file="/sys/block/$dev/stat"
        [ -f "$stat_file" ] || continue
        read -r rd _ _ _ wr _ _ _ _ _ _ _ _ < "$stat_file"
        prev_rd[$dev]=$rd
        prev_wr[$dev]=$wr
    done

    while true; do
        sleep 3
        # move cursor up
        local lines=0
        for dev in $(lsblk -dno NAME 2>/dev/null | grep -v '^loop'); do
            [ -f "/sys/block/$dev/stat" ] && lines=$((lines + 1))
        done
        printf "\033[${lines}A"

        for dev in $(lsblk -dno NAME 2>/dev/null | grep -v '^loop'); do
            stat_file="/sys/block/$dev/stat"
            [ -f "$stat_file" ] || continue
            read -r rd _ _ _ wr _ _ _ inflight _ _ _ _ < "$stat_file"

            rd_diff=$(( (rd - ${prev_rd[$dev]:-0}) * 512 / 3 ))
            wr_diff=$(( (wr - ${prev_wr[$dev]:-0}) * 512 / 3 ))
            prev_rd[$dev]=$rd
            prev_wr[$dev]=$wr

            rd_str=$(fmt_bytes $rd_diff)
            wr_str=$(fmt_bytes $wr_diff)

            printf "  %-8s  %10s  %10s  %8s\n" "$dev" "${rd_str}/s" "${wr_str}/s" "$inflight"
        done
    done
}

cmd_smart() {
    printf "${BOLD}${CYAN}Storage Health${RESET}\n\n"

    # SD card health from sysfs
    if [ -d /sys/block/mmcblk0/device ]; then
        printf "  ${BOLD}SD Card (mmcblk0)${RESET}\n"
        sd_name=$(cat /sys/block/mmcblk0/device/name 2>/dev/null)
        sd_date=$(cat /sys/block/mmcblk0/device/date 2>/dev/null)
        printf "    Model:     %s\n" "$sd_name"
        printf "    Mfg date:  %s\n" "$sd_date"

        if [ -f /sys/block/mmcblk0/device/life_time ]; then
            lt=$(cat /sys/block/mmcblk0/device/life_time)
            printf "    Life time: %s (0x0A = 90-100%% used)\n" "$lt"
        fi

        if [ -f /sys/block/mmcblk0/device/pre_eol_info ]; then
            eol=$(cat /sys/block/mmcblk0/device/pre_eol_info)
            case "$eol" in
                0x01) eol_str="normal" ;;
                0x02) eol_str="warning (80% lifetime)" ;;
                0x03) eol_str="urgent (90% lifetime)" ;;
                *)    eol_str="$eol" ;;
            esac
            printf "    EOL info:  %s\n" "$eol_str"
        fi

        # total sectors read/written
        stat_file="/sys/block/mmcblk0/stat"
        if [ -f "$stat_file" ]; then
            read -r rd _ _ _ wr _ _ _ _ _ _ _ _ < "$stat_file"
            rd_total=$(fmt_bytes $((rd * 512)))
            wr_total=$(fmt_bytes $((wr * 512)))
            printf "    Total read:    %s (since boot)\n" "$rd_total"
            printf "    Total written: %s (since boot)\n" "$wr_total"
        fi
        echo ""
    fi

    # check for smartctl
    if command -v smartctl &>/dev/null; then
        for dev in $(lsblk -dno NAME,TRAN 2>/dev/null | grep 'usb' | awk '{print $1}'); do
            printf "  ${BOLD}/dev/%s (USB)${RESET}\n" "$dev"
            sudo smartctl -H "/dev/$dev" 2>/dev/null | grep -E 'Health|result|Status' | sed 's/^/    /'
            echo ""
        done
    else
        printf "  ${DIM}Install smartmontools for USB drive health: sudo apt install smartmontools${RESET}\n"
    fi
}

cmd_usb() {
    printf "${BOLD}${CYAN}USB Storage Devices${RESET}\n\n"

    local usb_lines
    usb_lines=$(lsblk -o NAME,SIZE,TYPE,TRAN,MOUNTPOINT,MODEL,SERIAL 2>/dev/null | grep 'usb')

    if [ -n "$usb_lines" ]; then
        echo "$usb_lines" | sed 's/^/  /'
    else
        printf "  ${DIM}No USB storage devices detected${RESET}\n"
    fi

    echo ""
    printf "  ${BOLD}USB Bus${RESET}\n"
    lsusb 2>/dev/null | grep -iE 'storage|mass|flash|disk|sd|ssd' | sed 's/^/  /'

    if [ -z "$(lsusb 2>/dev/null | grep -iE 'storage|mass|flash|disk|sd|ssd')" ]; then
        printf "  ${DIM}No USB mass storage on bus${RESET}\n"
    fi
}

cmd_mount() {
    printf "${BOLD}${CYAN}Mount Points${RESET}\n\n"

    printf "  ${BOLD}%-20s %-8s %-8s %-20s %s${RESET}\n" "DEVICE" "FSTYPE" "SIZE" "MOUNT" "OPTIONS"
    printf "  %-20s %-8s %-8s %-20s %s\n" "--------------------" "--------" "--------" "--------------------" "-------"

    findmnt -rno SOURCE,FSTYPE,SIZE,TARGET,OPTIONS -t notmpfs,nodevtmpfs,nosquashfs,noproc,nosysfs,noautofs,nocgroup2,nobpf,nomqueue,nosunrpc,nodebugfs,notracefs,nofusectl,noconfigfs,nobinfmt_misc,nosecurityfs,nodevpts,norpc_pipefs 2>/dev/null | while read -r src fstype size target opts; do
        # trim options for display
        opts_short=$(echo "$opts" | cut -c1-30)
        printf "  %-20s %-8s %-8s %-20s %s\n" "$src" "$fstype" "$size" "$target" "$opts_short"
    done

    echo ""

    # fstab entries
    printf "  ${BOLD}fstab entries${RESET}\n"
    grep -v '^\s*#\|^\s*$' /etc/fstab 2>/dev/null | while read -r line; do
        printf "  ${DIM}%s${RESET}\n" "$line"
    done
}

cmd_temp() {
    printf "${BOLD}${CYAN}Storage Temperatures${RESET}\n\n"

    found=0

    # check hwmon for storage temps
    for hwmon in /sys/class/hwmon/hwmon*; do
        name=$(cat "$hwmon/name" 2>/dev/null)
        for temp_file in "$hwmon"/temp*_input; do
            [ -f "$temp_file" ] || continue
            temp_raw=$(cat "$temp_file" 2>/dev/null)
            temp=$(awk "BEGIN {printf \"%.1f\", $temp_raw / 1000}")
            label_file="${temp_file%_input}_label"
            label=$(cat "$label_file" 2>/dev/null || echo "$name")
            printf "  %-20s %s°C\n" "$label" "$temp"
            found=1
        done
    done

    # smartctl temps for USB drives
    if command -v smartctl &>/dev/null; then
        for dev in $(lsblk -dno NAME,TRAN 2>/dev/null | grep 'usb' | awk '{print $1}'); do
            temp=$(sudo smartctl -A "/dev/$dev" 2>/dev/null | grep -i temp | awk '{print $NF}')
            if [ -n "$temp" ]; then
                printf "  %-20s %s°C\n" "/dev/$dev (USB)" "$temp"
                found=1
            fi
        done
    fi

    if [ "$found" -eq 0 ]; then
        printf "  ${DIM}No storage temperature sensors found${RESET}\n"
        printf "  ${DIM}(SD cards typically don't expose temperature)${RESET}\n"
    fi
}

case "${1:-}" in
    devices)  cmd_devices ;;
    io)       cmd_io ;;
    smart)    cmd_smart ;;
    usb)      cmd_usb ;;
    mount)    cmd_mount ;;
    temp)     cmd_temp ;;
    *)        cmd_overview ;;
esac
