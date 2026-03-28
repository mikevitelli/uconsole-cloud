#!/bin/bash
# Cell health diagnostic for the uConsole (AXP228 PMU, 2x 18650)
#
# Measures real-world cell behavior under load to assess health:
#   - Resting voltage vs reported capacity (fuel gauge accuracy)
#   - Voltage sag under CPU load (internal resistance)
#   - Voltage recovery after load removal
#
# Usage: cellhealth.sh              Run full diagnostic (must be on battery)
#        cellhealth.sh quick        Quick voltage check only (no load test)
#        cellhealth.sh log          Append results to ~/cellhealth.log
#
# IMPORTANT: Unplug AC before running. The test needs ~60 seconds on battery.

source "$(dirname "$0")/lib.sh"

LOAD_DURATION=15
SAMPLE_INTERVAL=1
RECOVERY_WAIT=10
LOG="$HOME/cellhealth.log"

# ── Battery info (update when cells are swapped) ──
CELL_MODEL="Nitecore NL1834"
CELL_CAPACITY="3400mAh"
CELL_COUNT=2
CELL_INSTALL_DATE="2026-03-22"

# ── voltage-based capacity estimate — Nitecore NL1834 measured curve (2026-03-27) ──

vest_from_voltage() {
    local voltage_ua=$1
    if [ "$voltage_ua" -le 3000000 ]; then
        echo 0
    elif [ "$voltage_ua" -ge 4050000 ]; then
        echo 100
    else
        awk "BEGIN {
            v = $voltage_ua / 1000000
            if (v < 3.1) printf \"%d\", (v - 3.0) / 0.1 * 15
            else if (v < 3.2) printf \"%d\", 15 + (v - 3.1) / 0.1 * 35
            else if (v < 3.3) printf \"%d\", 50 + (v - 3.2) / 0.1 * 10
            else if (v < 3.4) printf \"%d\", 60 + (v - 3.3) / 0.1 * 10
            else if (v < 3.6) printf \"%d\", 70 + (v - 3.4) / 0.2 * 10
            else if (v < 3.8) printf \"%d\", 80 + (v - 3.6) / 0.2 * 10
            else printf \"%d\", 90 + (v - 3.8) / 0.25 * 10
        }"
    fi
}

# ── read voltage/current snapshot ──

read_snapshot() {
    local bat="/sys/class/power_supply/axp20x-battery"
    local v_ua c_ua
    v_ua=$(cat "$bat/voltage_now" 2>/dev/null || echo "0")
    c_ua=$(cat "$bat/current_now" 2>/dev/null || echo "0")
    echo "$v_ua $c_ua"
}

voltage_v() {
    awk "BEGIN {printf \"%.3f\", $1 / 1000000}"
}

# ── CPU load generator ──
# Uses dd + md5sum which yield to the scheduler and respond to signals,
# unlike pure busy loops that starve Ctrl+C on a 4-core CM4.

LOAD_PIDS=()

cleanup_load() {
    for pid in "${LOAD_PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    for pid in "${LOAD_PIDS[@]}"; do
        wait "$pid" 2>/dev/null
    done
    LOAD_PIDS=()
}

trap cleanup_load EXIT INT TERM

start_load() {
    LOAD_PIDS=()
    for i in 1 2 3 4; do
        dd if=/dev/urandom bs=64K count=999999 2>/dev/null | md5sum >/dev/null 2>&1 &
        LOAD_PIDS+=($!)
    done
}

stop_load() {
    cleanup_load
}

# ── grade helpers ──

grade_sag() {
    local sag_mv=$1
    if [ "$sag_mv" -le 100 ]; then
        echo "GOOD"
    elif [ "$sag_mv" -le 200 ]; then
        echo "FAIR"
    elif [ "$sag_mv" -le 350 ]; then
        echo "POOR"
    else
        echo "BAD"
    fi
}

grade_recovery() {
    local gap_mv=$1
    if [ "$gap_mv" -le 30 ]; then
        echo "GOOD"
    elif [ "$gap_mv" -le 80 ]; then
        echo "FAIR"
    else
        echo "POOR"
    fi
}

grade_gauge() {
    local drift=$1
    if [ "$drift" -le 5 ]; then
        echo "ACCURATE"
    elif [ "$drift" -le 15 ]; then
        echo "DRIFTED"
    else
        echo "INACCURATE"
    fi
}

grade_overall() {
    local sag_mv=$1 gap_mv=$2 drift=$3
    local score=0

    # sag scoring (most important — directly causes shutdowns)
    if [ "$sag_mv" -le 100 ]; then score=$((score + 40))
    elif [ "$sag_mv" -le 200 ]; then score=$((score + 25))
    elif [ "$sag_mv" -le 350 ]; then score=$((score + 10))
    fi

    # recovery scoring
    if [ "$gap_mv" -le 30 ]; then score=$((score + 30))
    elif [ "$gap_mv" -le 80 ]; then score=$((score + 20))
    elif [ "$gap_mv" -le 150 ]; then score=$((score + 10))
    fi

    # gauge accuracy scoring
    if [ "$drift" -le 5 ]; then score=$((score + 30))
    elif [ "$drift" -le 15 ]; then score=$((score + 20))
    elif [ "$drift" -le 25 ]; then score=$((score + 10))
    fi

    if [ "$score" -ge 80 ]; then
        echo "HEALTHY"
    elif [ "$score" -ge 50 ]; then
        echo "DEGRADED"
    else
        echo "REPLACE"
    fi
}

# ── preflight checks ──

preflight() {
    read_battery

    if [ "$BAT_PRESENT" != "1" ]; then
        err "No battery detected"
        exit 1
    fi

    if [ "$BAT_AC_ONLINE" = "1" ]; then
        err "Unplug AC power before running this test"
        err "The test must run on battery to measure cell health"
        exit 1
    fi

    if [ "$BAT_CAPACITY" -lt 20 ]; then
        err "Battery too low (${BAT_CAPACITY}%) — charge to at least 20% first"
        exit 1
    fi
}

# ── quick check (no load) ──

cmd_quick() {
    section "Quick Cell Check"

    read_battery
    local vest
    vest=$(vest_from_voltage "$BAT_VOLTAGE_UA")
    local drift=$((BAT_CAPACITY - vest))
    [ "$drift" -lt 0 ] && drift=$((-drift))

    printf "  %-20s %s\n" "Status:" "$BAT_STATUS"
    printf "  %-20s %s\n" "AC:" "$([ "$BAT_AC_ONLINE" = "1" ] && echo "plugged in" || echo "unplugged")"
    printf "  %-20s %s%%\n" "Fuel gauge:" "$BAT_CAPACITY"
    printf "  %-20s %s%% (from voltage)\n" "Voltage estimate:" "$vest"
    printf "  %-20s %s\n" "Voltage:" "$(voltage_v "$BAT_VOLTAGE_UA")V"
    printf "  %-20s %smA\n" "Current draw:" "$BAT_CURRENT_MA"
    printf "  %-20s %s\n" "Health:" "$BAT_HEALTH"
    echo ""
    printf "  %-20s %s%% — %s\n" "Gauge drift:" "$drift" "$(grade_gauge "$drift")"

    if [ "$BAT_AC_ONLINE" = "0" ]; then
        # check if resting voltage is suspiciously low for reported capacity
        local expected_min
        if [ "$BAT_CAPACITY" -ge 70 ]; then expected_min=3800000
        elif [ "$BAT_CAPACITY" -ge 50 ]; then expected_min=3600000
        elif [ "$BAT_CAPACITY" -ge 30 ]; then expected_min=3400000
        else expected_min=3200000
        fi

        if [ "$BAT_VOLTAGE_UA" -lt "$expected_min" ]; then
            echo ""
            warn "Voltage $(voltage_v "$BAT_VOLTAGE_UA")V is low for ${BAT_CAPACITY}% — cells may be degraded"
            warn "Run full test (cellhealth.sh) for detailed diagnosis"
        fi
    fi
}

# ── full diagnostic ──

cmd_full() {
    preflight

    section "Cell Health Diagnostic"

    info "This test takes ~${LOAD_DURATION}s load + ${RECOVERY_WAIT}s recovery"
    echo ""

    # ── phase 1: resting baseline ──
    printf "  ${BOLD}Phase 1: Resting baseline${RESET}\n"
    read_battery
    local rest_v_ua=$BAT_VOLTAGE_UA
    local rest_c_ua=$BAT_CURRENT_UA
    local rest_capacity=$BAT_CAPACITY
    local rest_vest
    rest_vest=$(vest_from_voltage "$rest_v_ua")

    printf "    Voltage:    %sV\n" "$(voltage_v "$rest_v_ua")"
    printf "    Current:    %smA\n" "$BAT_CURRENT_MA"
    printf "    Gauge:      %s%%  Estimate: %s%%\n" "$rest_capacity" "$rest_vest"
    echo ""

    # ── phase 2: load test ──
    printf "  ${BOLD}Phase 2: Load test (4 cores, ${LOAD_DURATION}s)${RESET}\n"

    start_load

    local min_v_ua=$rest_v_ua
    local max_c_abs=${rest_c_ua#-}  # absolute value of current
    local samples=0
    local total_v=0

    sleep 2  # let load stabilize

    local i=0
    while [ "$i" -lt "$LOAD_DURATION" ]; do
        local snap
        snap=$(read_snapshot)
        local v_ua=${snap%% *}
        local c_ua=${snap##* }

        [ "$v_ua" -lt "$min_v_ua" ] && min_v_ua=$v_ua
        local c_abs=${c_ua#-}
        [ "$c_abs" -gt "$max_c_abs" ] && max_c_abs=$c_abs
        total_v=$((total_v + v_ua))
        samples=$((samples + 1))

        printf "\r    [%2d/%ds] %sV  %smA" "$((i + 1))" "$LOAD_DURATION" \
            "$(voltage_v "$v_ua")" "$((c_ua / 1000))"

        sleep "$SAMPLE_INTERVAL"
        i=$((i + 1))
    done

    stop_load
    echo ""

    local avg_v_ua=$((total_v / samples))
    local sag_mv=$(( (rest_v_ua - min_v_ua) / 1000 ))
    local avg_sag_mv=$(( (rest_v_ua - avg_v_ua) / 1000 ))

    printf "    Min voltage:  %sV\n" "$(voltage_v "$min_v_ua")"
    printf "    Avg voltage:  %sV\n" "$(voltage_v "$avg_v_ua")"
    printf "    Peak current: %smA\n" "$((max_c_abs / 1000))"
    printf "    Voltage sag:  %smV (peak)  %smV (avg)\n" "$sag_mv" "$avg_sag_mv"
    echo ""

    # ── phase 3: recovery ──
    printf "  ${BOLD}Phase 3: Recovery (${RECOVERY_WAIT}s)${RESET}\n"

    sleep "$RECOVERY_WAIT"
    local snap
    snap=$(read_snapshot)
    local recov_v_ua=${snap%% *}
    local recov_gap_mv=$(( (rest_v_ua - recov_v_ua) / 1000 ))
    [ "$recov_gap_mv" -lt 0 ] && recov_gap_mv=0

    printf "    Recovered to: %sV\n" "$(voltage_v "$recov_v_ua")"
    printf "    Gap from rest: %smV\n" "$recov_gap_mv"
    echo ""

    # ── phase 4: internal resistance estimate ──
    # R_internal ≈ ΔV / ΔI (using peak sag vs rest, absolute values)
    local delta_v_uv=$(( rest_v_ua - min_v_ua ))
    local rest_c_abs=${rest_c_ua#-}
    local delta_i_ua=$(( max_c_abs - rest_c_abs ))
    local ir_mohm=0
    if [ "$delta_i_ua" -gt 0 ]; then
        # R = V/I, convert uV/uA to mohm (uV/uA = ohm, *1000 = mohm)
        ir_mohm=$(awk "BEGIN {printf \"%d\", ($delta_v_uv / $delta_i_ua) * 1000}")
    fi

    # ── results ──
    local gauge_drift=$((rest_capacity - rest_vest))
    [ "$gauge_drift" -lt 0 ] && gauge_drift=$((-gauge_drift))

    local sag_grade recov_grade gauge_grade overall
    sag_grade=$(grade_sag "$sag_mv")
    recov_grade=$(grade_recovery "$recov_gap_mv")
    gauge_grade=$(grade_gauge "$gauge_drift")
    overall=$(grade_overall "$sag_mv" "$recov_gap_mv" "$gauge_drift")

    echo "┌─────────────────────────────────────────┐"
    echo "│          Cell Health Results             │"
    echo "├─────────────────────────────────────────┤"
    printf "│  Voltage sag:     %-5smV   %-12s│\n" "$sag_mv" "$sag_grade"
    printf "│  Recovery gap:    %-5smV   %-12s│\n" "$recov_gap_mv" "$recov_grade"
    printf "│  Gauge drift:     %-5s%%    %-12s│\n" "$gauge_drift" "$gauge_grade"
    if [ "$ir_mohm" -gt 0 ]; then
        printf "│  Est. resistance: %-5smΩ   %-12s│\n" "$ir_mohm" "(per pack)"
    fi
    echo "├─────────────────────────────────────────┤"

    local color
    case "$overall" in
        HEALTHY)  color=$GREEN ;;
        DEGRADED) color=$YELLOW ;;
        REPLACE)  color=$RED ;;
    esac
    printf "│  Overall:         ${color}%-21s${RESET}│\n" "$overall"
    echo "└─────────────────────────────────────────┘"

    # ── advice ──
    echo ""
    case "$overall" in
        HEALTHY)
            ok "Cells are in good shape" ;;
        DEGRADED)
            warn "Cells are degraded — expect reduced runtime"
            warn "Consider replacing both 18650s soon"
            if [ "$sag_mv" -gt 200 ]; then
                warn "High voltage sag may cause shutdowns under heavy load"
            fi
            if [ "$gauge_drift" -gt 15 ]; then
                warn "Fuel gauge is inaccurate — run calibration:"
                info "  echo 1 | sudo tee /sys/class/power_supply/axp20x-battery/calibrate"
            fi
            ;;
        REPLACE)
            err "Cells need replacement — shutdown risk is high"
            err "Replace both 18650s with matched cells (Samsung 35E, Panasonic GA, Samsung 30Q)"
            if [ "$sag_mv" -gt 350 ]; then
                err "Voltage sag of ${sag_mv}mV will cause PMU cutoff under load"
            fi
            ;;
    esac

    # ── return data for log mode ──
    RESULT_SAG_MV=$sag_mv
    RESULT_RECOV_MV=$recov_gap_mv
    RESULT_DRIFT=$gauge_drift
    RESULT_IR_MOHM=$ir_mohm
    RESULT_GRADE=$overall
    RESULT_REST_V=$(voltage_v "$rest_v_ua")
    RESULT_MIN_V=$(voltage_v "$min_v_ua")
    RESULT_RECOV_V=$(voltage_v "$recov_v_ua")
    RESULT_CAPACITY=$rest_capacity
}

# ── log mode ──

log_results() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp | cells=${CELL_MODEL} ${CELL_CAPACITY}x${CELL_COUNT} (installed ${CELL_INSTALL_DATE}) | cap=${RESULT_CAPACITY}% | rest=${RESULT_REST_V}V | min=${RESULT_MIN_V}V | recov=${RESULT_RECOV_V}V | sag=${RESULT_SAG_MV}mV | recovery=${RESULT_RECOV_MV}mV | drift=${RESULT_DRIFT}% | ir=${RESULT_IR_MOHM}mohm | grade=${RESULT_GRADE}" >> "$LOG"
    echo ""
    ok "Logged to $LOG"
}

cmd_log() {
    cmd_full
    log_results
}

# ── main ──

case "${1:-}" in
    quick)  cmd_quick ;;
    log)    cmd_log ;;
    *)      cmd_full; log_results ;;
esac
