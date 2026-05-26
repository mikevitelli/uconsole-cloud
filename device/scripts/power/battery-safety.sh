#!/bin/bash
# battery-safety.sh — enable/disable the 4-layer battery safety stack
#
# Manages:
#   pmu-voltage-min.service      Lower AXP228 VOFF 3.3V → 2.9V (oneshot)
#   cpu-freq-cap.service         Cap CPU to 1.2GHz to reduce sag (oneshot)
#   low-battery-shutdown.service Graceful poweroff at 3.05V (daemon)
#   crash-log.service            Log unclean shutdowns for diagnosis
#
# Status: UNSTABLE — these units were previously broken due to a stale
# path (~/scripts/). Default state on new installs is OFF. Enable
# manually after verifying your battery setup can support the 2.9V
# cutoff (Samsung INR18650-35E cells are tested; other cells may not).
set -euo pipefail

UNITS=(
    pmu-voltage-min.service
    cpu-freq-cap.service
    low-battery-shutdown.service
    crash-log.service
)

sudo_wrap() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

cmd_on() {
    echo "Enabling battery safety stack..."
    sudo_wrap systemctl reset-failed "${UNITS[@]}" 2>/dev/null || true
    sudo_wrap systemctl enable "${UNITS[@]}"
    # Start the oneshots now so VOFF and freq cap apply to this session.
    # crash-log is boot-only (would emit a false "clean boot" mid-session).
    sudo_wrap systemctl start pmu-voltage-min.service
    sudo_wrap systemctl start cpu-freq-cap.service
    sudo_wrap systemctl start low-battery-shutdown.service
    echo "Enabled. Run 'battery-safety.sh status' to verify."
}

cmd_off() {
    echo "Disabling battery safety stack..."
    sudo_wrap systemctl stop low-battery-shutdown.service 2>/dev/null || true
    sudo_wrap systemctl disable "${UNITS[@]}"
    echo "Disabled. Note: PMU VOFF stays at the value last set until next"
    echo "boot. CPU freq cap likewise persists until reboot."
}

cmd_status() {
    printf "%-32s %-10s %s\n" "UNIT" "ENABLED" "ACTIVE"
    for u in "${UNITS[@]}"; do
        enabled=$(systemctl is-enabled "$u" 2>/dev/null || echo "-")
        active=$(systemctl is-active "$u" 2>/dev/null || echo "-")
        printf "%-32s %-10s %s\n" "$u" "$enabled" "$active"
    done
}

case "${1:-status}" in
    on|enable)   cmd_on ;;
    off|disable) cmd_off ;;
    status)      cmd_status ;;
    *)
        cat <<EOF
Usage: battery-safety.sh {on|off|status}

  on      Enable all 4 battery-safety services and start the session-
          applicable ones (pmu-voltage-min, cpu-freq-cap, low-battery-
          shutdown). crash-log runs at next boot.
  off     Stop low-battery-shutdown and disable all 4 at boot. VOFF
          and freq cap persist until reboot.
  status  Show enabled/active state of each unit (default).

UNSTABLE: default is OFF. These were previously broken by a path
migration and are now under active iteration. Opt in at your own risk.
See the project's device/scripts/power/ directory for source.
EOF
        exit 1
        ;;
esac
