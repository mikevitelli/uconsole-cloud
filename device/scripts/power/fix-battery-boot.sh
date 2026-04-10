#!/usr/bin/env bash
# Fix battery boot — install all three VOFF layers so the uConsole boots on battery
# Called from TUI Power Config menu. Requires sudo.
set -euo pipefail

source "$(dirname "$0")/lib.sh"

SHARE_DIR="/opt/uconsole/share/battery-fix"

usage() {
    cat <<EOF
Usage: fix-battery-boot.sh [command]

Commands:
  status    Show current battery boot fix status (default)
  install   Install all three VOFF fix layers
  remove    Remove all fix layers and restore defaults
EOF
}

check_files() {
    if [ ! -d "$SHARE_DIR" ]; then
        err "Template files not found at $SHARE_DIR"
        exit 1
    fi
}

cmd_status() {
    section "Battery Boot Fix Status"

    # Check AXP PMU
    if [ ! -d /sys/class/power_supply/axp20x-battery ]; then
        warn "AXP PMU not found — not a uConsole?"
        return
    fi

    local vmin
    vmin=$(cat /sys/class/power_supply/axp20x-battery/voltage_min 2>/dev/null || echo "?")
    local vmin_v
    vmin_v=$(awk "BEGIN {printf \"%.1f\", $vmin / 1000000}" 2>/dev/null || echo "?")

    printf "  VOFF cutoff:        %sV" "$vmin_v"
    if [ "$vmin" = "2900000" ]; then
        printf " (fixed)\n"
    else
        printf " (default — may cause boot failure)\n"
    fi

    # Layer 1: udev rule
    printf "  Udev rule:          "
    if [ -f /etc/udev/rules.d/99-uconsole-battery.rules ]; then
        ok "installed"
    else
        warn "not installed"
    fi

    # Layer 2: initramfs hook
    printf "  Initramfs hook:     "
    if [ -f /etc/initramfs-tools/hooks/axp-voff ] && \
       [ -f /etc/initramfs-tools/scripts/init-premount/axp-voff ]; then
        ok "installed"
    else
        warn "not installed"
    fi

    # Layer 3: shutdown service
    printf "  Shutdown service:   "
    if systemctl is-enabled axp-voff-shutdown.service &>/dev/null; then
        ok "enabled"
    else
        warn "not enabled"
    fi
}

cmd_install() {
    check_files
    section "Installing Battery Boot Fix"

    if [ "$(id -u)" -ne 0 ]; then
        err "Run with sudo"
        exit 1
    fi

    # Layer 1: udev rule
    printf "  Installing udev rule... "
    cp "$SHARE_DIR/99-uconsole-battery.rules" /etc/udev/rules.d/
    udevadm control --reload-rules
    ok "done"

    # Layer 2: initramfs
    printf "  Installing initramfs hooks... "
    cp "$SHARE_DIR/axp-voff-hook" /etc/initramfs-tools/hooks/axp-voff
    cp "$SHARE_DIR/axp-voff-premount" /etc/initramfs-tools/scripts/init-premount/axp-voff
    chmod +x /etc/initramfs-tools/hooks/axp-voff
    chmod +x /etc/initramfs-tools/scripts/init-premount/axp-voff
    ok "done"

    # Layer 3: shutdown service
    printf "  Installing shutdown service... "
    cp "$SHARE_DIR/axp-voff-shutdown.service" /etc/systemd/system/
    systemctl daemon-reload 2>/dev/null
    systemctl enable axp-voff-shutdown.service 2>/dev/null
    ok "done"

    # Apply immediately
    printf "  Setting VOFF to 2.9V... "
    echo 2900000 > /sys/class/power_supply/axp20x-battery/voltage_min 2>/dev/null || true
    i2cset -f -y 0 0x34 0x31 0x03 2>/dev/null || true
    ok "done"

    # Rebuild initramfs
    printf "  Rebuilding initramfs... "
    update-initramfs -u >/dev/null 2>&1
    ok "done"

    echo ""
    ok "Battery boot fix installed. Reboot to verify."
}

cmd_remove() {
    section "Removing Battery Boot Fix"

    if [ "$(id -u)" -ne 0 ]; then
        err "Run with sudo"
        exit 1
    fi

    rm -f /etc/udev/rules.d/99-uconsole-battery.rules
    udevadm control --reload-rules 2>/dev/null || true

    rm -f /etc/initramfs-tools/hooks/axp-voff
    rm -f /etc/initramfs-tools/scripts/init-premount/axp-voff

    systemctl disable axp-voff-shutdown.service 2>/dev/null || true
    rm -f /etc/systemd/system/axp-voff-shutdown.service
    systemctl daemon-reload 2>/dev/null || true

    update-initramfs -u >/dev/null 2>&1 || true

    ok "Battery boot fix removed. Default VOFF (3.3V) will apply on next reboot."
}

case "${1:-status}" in
    status)  cmd_status ;;
    install) cmd_install ;;
    remove)  cmd_remove ;;
    -h|--help|help) usage ;;
    *)       echo "Unknown command: $1"; usage; exit 1 ;;
esac
