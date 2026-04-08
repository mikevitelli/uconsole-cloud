#!/bin/bash
# System update manager for the uConsole
# Usage: update.sh              Interactive update menu
#        update.sh all           Run all updates (apt, flatpak, firmware, repo)
#        update.sh apt           Update apt packages only
#        update.sh flatpak       Update flatpak apps only
#        update.sh firmware      Check for firmware/kernel updates
#        update.sh repo          Snapshot, commit, and push monorepo to GitHub
#        update.sh status        Show what's outdated without updating
#        update.sh log           Show update history

source "$(dirname "$0")/lib.sh"

count_upgradable() {
    local n
    n=$(apt list --upgradable 2>/dev/null | grep -c 'upgradable') || true
    echo "${n:-0}"
}

# ── apt ──

cmd_apt() {
    section "APT Packages"

    info "Updating package lists..."
    if sudo apt update -qq 2>&1 | tail -1; then
        ok "Package lists updated"
    else
        err "Failed to update package lists"
        return 1
    fi

    local upgradable
    upgradable=$(count_upgradable)

    if [ "$upgradable" -eq 0 ]; then
        ok "All packages up to date"
        log_entry "apt" "no updates"
        return 0
    fi

    warn "$upgradable package(s) upgradable"
    echo ""
    apt list --upgradable 2>/dev/null | grep -v '^Listing' | head -20
    if [ "$upgradable" -gt 20 ]; then
        info "... and $((upgradable - 20)) more"
    fi
    echo ""

    info "Upgrading packages..."
    if sudo apt upgrade -y 2>&1 | tail -5; then
        ok "Packages upgraded"
        log_entry "apt" "upgraded $upgradable package(s)"
    else
        err "Upgrade failed"
        log_entry "apt" "upgrade FAILED"
        return 1
    fi

    # autoremove
    local removable
    removable=$(apt-get -s autoremove 2>/dev/null | grep -c '^Remv')
    removable=${removable:-0}
    if [ "$removable" -gt 0 ]; then
        info "Removing $removable unused package(s)..."
        sudo apt autoremove -y -qq
        ok "Cleaned up $removable package(s)"
        log_entry "apt" "autoremoved $removable package(s)"
    fi
}

# ── flatpak ──

cmd_flatpak() {
    section "Flatpak Apps"

    if ! command -v flatpak &>/dev/null; then
        info "Flatpak not installed, skipping"
        return 0
    fi

    local installed
    installed=$(flatpak list --app 2>/dev/null | wc -l)
    info "$installed flatpak app(s) installed"

    local updates
    updates=$(flatpak remote-ls --updates 2>/dev/null | wc -l)

    if [ "$updates" -eq 0 ]; then
        ok "All flatpaks up to date"
        log_entry "flatpak" "no updates"
        return 0
    fi

    warn "$updates update(s) available"
    echo ""
    flatpak remote-ls --updates 2>/dev/null | head -15
    echo ""

    info "Updating flatpaks..."
    if flatpak update -y 2>&1 | tail -3; then
        ok "Flatpaks updated"
        log_entry "flatpak" "updated $updates app(s)"
    else
        err "Flatpak update failed"
        log_entry "flatpak" "update FAILED"
        return 1
    fi
}

# ── firmware ──

cmd_firmware() {
    section "Firmware & Kernel"

    # current kernel
    local kernel
    kernel=$(uname -r)
    info "Running kernel: $kernel"

    # architecture
    local arch
    arch=$(uname -m)
    info "Architecture: $arch"

    # check for kernel updates via apt
    local kernel_updates
    kernel_updates=$(apt list --upgradable 2>/dev/null | grep -c 'linux-image\|linux-headers\|linux-firmware' || echo 0)

    if [ "$kernel_updates" -gt 0 ]; then
        warn "$kernel_updates kernel/firmware update(s) available"
        apt list --upgradable 2>/dev/null | grep 'linux-image\|linux-headers\|linux-firmware'
        info "These will be installed with 'update.sh apt'"
    else
        ok "Kernel/firmware is current"
    fi

    # rpi firmware
    if [ -f /boot/config.txt ]; then
        info "Boot config: /boot/config.txt"
        local dtoverlay_count
        dtoverlay_count=$(grep -c '^dtoverlay=' /boot/config.txt 2>/dev/null || echo 0)
        info "Active overlays: $dtoverlay_count"
    fi

    # check rpi-update availability
    if command -v rpi-update &>/dev/null; then
        info "rpi-update is available (use manually — can be unstable)"
    fi

    log_entry "firmware" "kernel=$kernel arch=$arch"
}

# ── status (dry run) ──

cmd_status() {
    section "Update Status"

    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    printf "  ${DIM}Checked: %s${RESET}\n" "$timestamp"
    echo ""

    # apt
    printf "  ${BOLD}APT${RESET}       "
    local apt_count
    sudo apt update -qq 2>/dev/null
    apt_count=$(count_upgradable)
    if [ "$apt_count" -eq 0 ]; then
        printf "${GREEN}up to date${RESET}\n"
    else
        printf "${YELLOW}%s upgradable${RESET}\n" "$apt_count"
    fi

    # flatpak
    printf "  ${BOLD}Flatpak${RESET}   "
    if command -v flatpak &>/dev/null; then
        local fp_count
        fp_count=$(flatpak remote-ls --updates 2>/dev/null | wc -l)
        if [ "$fp_count" -eq 0 ]; then
            printf "${GREEN}up to date${RESET}\n"
        else
            printf "${YELLOW}%s updatable${RESET}\n" "$fp_count"
        fi
    else
        printf "${DIM}not installed${RESET}\n"
    fi

    # kernel
    printf "  ${BOLD}Kernel${RESET}    "
    local kern_count
    kern_count=$(apt list --upgradable 2>/dev/null | grep -c 'linux-image\|linux-headers\|linux-firmware') || true
    kern_count="${kern_count:-0}"
    if [ "$kern_count" -eq 0 ]; then
        printf "${GREEN}%s${RESET}\n" "$(uname -r)"
    else
        printf "${YELLOW}%s update(s)${RESET}\n" "$kern_count"
    fi

    # last update
    echo ""
    if [ -f "$LOG_FILE" ]; then
        local last
        last=$(tail -1 "$LOG_FILE")
        info "Last update: $last"
    else
        info "No update history found"
    fi
}

# ── update all ──

cmd_all() {
    local start_time
    start_time=$(date +%s)

    printf "${BOLD}${CYAN}"
    echo "  ╔═══════════════════════════════════════╗"
    echo "  ║       uConsole System Update          ║"
    echo "  ╚═══════════════════════════════════════╝"
    printf "${RESET}"
    info "Started: $(date '+%Y-%m-%d %H:%M:%S')"

    log_entry "all" "full update started"

    # 1. update system packages
    cmd_apt
    cmd_flatpak
    cmd_firmware

    # 2. gather everything (captures new package states, configs, etc.)
    section "Full Backup"
    info "Gathering all backup categories..."
    bash "$SCRIPTS_DIR/backup.sh" gather all

    # 3. single sync — one commit, one push
    info "Syncing to GitHub..."
    bash "$SCRIPTS_DIR/backup.sh" sync

    local end_time elapsed_min elapsed_sec
    end_time=$(date +%s)
    elapsed_sec=$((end_time - start_time))
    elapsed_min=$((elapsed_sec / 60))
    elapsed_sec=$((elapsed_sec % 60))

    section "Complete"
    ok "All updates finished in ${elapsed_min}m ${elapsed_sec}s"
    log_entry "all" "full update completed in ${elapsed_min}m ${elapsed_sec}s"

    # check if reboot needed
    if [ -f /var/run/reboot-required ]; then
        echo ""
        warn "Reboot required to apply kernel/system updates"
        info "Run: sudo reboot"
    fi
}

# ── log ──

cmd_log() {
    section "Update History"

    if [ ! -f "$LOG_FILE" ]; then
        info "No update history yet"
        return 0
    fi

    local count
    count=$(wc -l < "$LOG_FILE")
    info "$count entries in $LOG_FILE"
    echo ""

    printf "  ${BOLD}%-20s  %-12s  %s${RESET}\n" "TIMESTAMP" "ACTION" "DETAIL"
    printf "  ${DIM}%-20s  %-12s  %s${RESET}\n" "────────────────────" "────────────" "──────────────────────────"

    tail -20 "$LOG_FILE" | while IFS='|' read -r ts action detail; do
        printf "  %-20s  %-12s  %s\n" "$(echo "$ts" | xargs)" "$(echo "$action" | xargs)" "$(echo "$detail" | xargs)"
    done

    if [ "$count" -gt 20 ]; then
        echo ""
        info "Showing last 20 of $count entries"
    fi
}

# ── snapshot (delegates to backup.sh) ──

cmd_snapshot() {
    section "Package Snapshot"
    bash "$SCRIPTS_DIR/backup.sh" packages
    log_entry "snapshot" "package lists refreshed"
}

# ── repo (snapshot + sync) ──

cmd_repo() {
    # gather package snapshots
    cmd_snapshot

    # sync — commits whatever changed (packages/) in one round-trip
    git_sync
}

# ── interactive menu ──

cmd_interactive() {
    while true; do
        clear
        printf "${BOLD}${CYAN}"
        echo "  ╔═══════════════════════════════════════╗"
        echo "  ║       uConsole Update Manager         ║"
        echo "  ╚═══════════════════════════════════════╝"
        printf "${RESET}"
        echo ""
        printf "  ${BOLD}${GREEN}1${RESET}  %-14s ${DIM}%s${RESET}\n" "all" "Run all updates (apt + flatpak + firmware + repo)"
        printf "  ${BOLD}${GREEN}2${RESET}  %-14s ${DIM}%s${RESET}\n" "apt" "Update apt packages"
        printf "  ${BOLD}${GREEN}3${RESET}  %-14s ${DIM}%s${RESET}\n" "flatpak" "Update flatpak apps"
        printf "  ${BOLD}${GREEN}4${RESET}  %-14s ${DIM}%s${RESET}\n" "firmware" "Check firmware & kernel"
        printf "  ${BOLD}${GREEN}5${RESET}  %-14s ${DIM}%s${RESET}\n" "repo" "Snapshot, commit & push to GitHub"
        printf "  ${BOLD}${GREEN}6${RESET}  %-14s ${DIM}%s${RESET}\n" "status" "Check what's outdated"
        printf "  ${BOLD}${GREEN}7${RESET}  %-14s ${DIM}%s${RESET}\n" "snapshot" "Save package lists to repo"
        printf "  ${BOLD}${GREEN}8${RESET}  %-14s ${DIM}%s${RESET}\n" "log" "Show update history"
        echo ""
        printf "  ${BOLD}${GREEN}q${RESET}  %-14s ${DIM}%s${RESET}\n" "quit" "Exit"
        echo ""
        printf "  ${BOLD}>${RESET} "
        read -r choice

        case "$choice" in
            1|all)       cmd_all; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            2|apt)       cmd_apt; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            3|flatpak)   cmd_flatpak; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            4|firmware)  cmd_firmware; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            5|repo)      cmd_repo; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            6|status)    cmd_status; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            7|snapshot)  cmd_snapshot; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            8|log)       cmd_log; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            q|Q|quit)    clear; exit 0 ;;
            *)           echo "  Invalid selection"; sleep 1 ;;
        esac
    done
}

# ── main ──

case "${1:-}" in
    all)       cmd_all ;;
    apt)       cmd_apt ;;
    flatpak)   cmd_flatpak ;;
    firmware)  cmd_firmware ;;
    repo)      cmd_repo ;;
    status)    cmd_status ;;
    log)       cmd_log ;;
    snapshot)  cmd_snapshot ;;
    *)         cmd_interactive ;;
esac
