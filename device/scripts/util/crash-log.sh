#!/bin/bash
# Detect unclean shutdowns and log them with battery state.
#
# Runs at boot via systemd. A stamp file distinguishes a clean shutdown
# (stamp removed by ExecStop) from a crash (stamp survives the reboot).
#
# This is a SYSTEM service, so systemd does not set $HOME for it — the
# previous version used "$HOME" under `set -u` and aborted on every boot
# with "HOME: unbound variable", silently disabling crash detection. We
# now resolve the operator's home the same way the package postinst does
# (first real login user, UID >= 1000) and fall back to $HOME only if a
# real session happens to provide one.
#
# crash.log is shared with the TUI's feature-import logger
# (lib/tui/framework.py appends ~/crash.log as the user), so the file
# lives in the operator's home and MUST stay operator-owned — otherwise a
# root-created log blocks the user-mode TUI from appending to it.
set -u

# Resolve operator user/home even when invoked by systemd with no $HOME.
USER_NAME="${SUDO_USER:-}"
if [ -z "$USER_NAME" ]; then
    USER_NAME="$(getent passwd | awk -F: '$3 >= 1000 && $3 < 60000 {print $1; exit}')"
fi
USER_HOME="$(getent passwd "$USER_NAME" 2>/dev/null | cut -d: -f6)"
: "${USER_HOME:=${HOME:-/root}}"

STAMP="$USER_HOME/.uconsole-running"
LOG="$USER_HOME/crash.log"

# Append a line, keeping the operator owning the file (service runs as root).
log_line() {
    echo "$1" >> "$LOG"
    [ -n "$USER_NAME" ] && chown "$USER_NAME" "$LOG" 2>/dev/null || true
}

case "${1:-boot}" in
    boot)
        if [ -f "$STAMP" ]; then
            # Stamp survived reboot — previous shutdown was unclean.
            TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
            BAT="/sys/class/power_supply/axp20x-battery"
            VOLT_RAW=$(cat "$BAT/voltage_now" 2>/dev/null || echo 0)
            VOLT=$(awk "BEGIN {printf \"%.3f\", $VOLT_RAW / 1000000}")
            CAP=$(cat "$BAT/capacity" 2>/dev/null || echo "?")
            AC=$(cat /sys/class/power_supply/axp20x-ac/online 2>/dev/null || echo "?")
            TEMP_RAW=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)
            TEMP=$(awk "BEGIN {printf \"%.1f\", $TEMP_RAW / 1000}")

            # Last kernel errors from the previous boot — clues for the cut.
            LAST_ERR=$(journalctl -b -1 -p err --no-pager -n 3 2>/dev/null | tail -3 | tr '\n' ' | ')

            log_line "$TIMESTAMP | CRASH | boot_volt=${VOLT}V | boot_cap=${CAP}% | ac=${AC} | temp=${TEMP}C | prev_errs=${LAST_ERR}"
        fi

        # Set stamp — persists until a clean shutdown removes it.
        touch "$STAMP"
        [ -n "$USER_NAME" ] && chown "$USER_NAME" "$STAMP" 2>/dev/null || true
        ;;
    stop)
        # Clean shutdown — remove stamp so the next boot isn't flagged.
        rm -f "$STAMP"
        ;;
esac
