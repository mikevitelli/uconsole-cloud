#!/bin/bash
# Shared library for uConsole scripts
# Usage: source "$(dirname "$0")/lib.sh"

# guard against double-sourcing
[ -n "${_LIB_SH_LOADED:-}" ] && return 0
_LIB_SH_LOADED=1

# ── directory constants ──
# derived from lib.sh's own location so consumers don't need to compute these
LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$LIB_DIR/.." && pwd)"
SCRIPTS_DIR="$LIB_DIR"
PKG_DIR="$REPO_DIR/packages"
SHELL_DIR="$REPO_DIR/shell"
SSH_DIR="$REPO_DIR/ssh"
GH_DIR="$REPO_DIR/config/gh"
SYS_DIR="$REPO_DIR/system"
LOG_FILE="${LOG_FILE:-$HOME/update.log}"

# ── colors ──
BOLD="\033[1m"
DIM="\033[2m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
BLUE="\033[34m"
MAGENTA="\033[35m"
RESET="\033[0m"

# ── output helpers ──
ok()      { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn()    { printf "  ${YELLOW}!${RESET} %s\n" "$1"; }
err()     { printf "  ${RED}✗${RESET} %s\n" "$1"; }
info()    { printf "  ${DIM}%s${RESET}\n" "$1"; }
section() { echo ""; printf "${BOLD}${CYAN}── %s ──${RESET}\n\n" "$1"; }

# ── progress bars ──

bar() {
    local val=$1 max=$2 len=${3:-15}
    local filled=$((val * len / max))
    [ "$filled" -gt "$len" ] && filled=$len
    [ "$filled" -lt 0 ] && filled=0
    local empty=$((len - filled))
    local color=$GREEN
    if [ "$val" -gt $((max * 80 / 100)) ]; then color=$RED
    elif [ "$val" -gt $((max * 60 / 100)) ]; then color=$YELLOW
    fi
    printf "${color}"
    printf '%0.s█' $(seq 1 $filled 2>/dev/null)
    printf "${DIM}"
    printf '%0.s░' $(seq 1 $empty 2>/dev/null)
    printf "${RESET}"
}

bar_inv() {
    local val=$1 max=$2 len=${3:-15}
    local filled=$((val * len / max))
    [ "$filled" -gt "$len" ] && filled=$len
    [ "$filled" -lt 0 ] && filled=0
    local empty=$((len - filled))
    local color=$RED
    if [ "$val" -gt $((max * 60 / 100)) ]; then color=$GREEN
    elif [ "$val" -gt $((max * 30 / 100)) ]; then color=$YELLOW
    fi
    printf "${color}"
    printf '%0.s█' $(seq 1 $filled 2>/dev/null)
    printf "${DIM}"
    printf '%0.s░' $(seq 1 $empty 2>/dev/null)
    printf "${RESET}"
}

# ── battery ──

read_battery() {
    local bat="/sys/class/power_supply/axp20x-battery"
    local ac="/sys/class/power_supply/axp22x-ac"

    BAT_STATUS=$(cat "$bat/status" 2>/dev/null || echo "Unknown")
    BAT_CAPACITY=$(cat "$bat/capacity" 2>/dev/null || echo "0")
    BAT_VOLTAGE_UA=$(cat "$bat/voltage_now" 2>/dev/null || echo "0")
    BAT_CURRENT_UA=$(cat "$bat/current_now" 2>/dev/null || echo "0")
    BAT_CHARGE_RATE_UA=$(cat "$bat/constant_charge_current" 2>/dev/null || echo "0")
    BAT_CHARGE_MAX_UA=$(cat "$bat/constant_charge_current_max" 2>/dev/null || echo "0")
    BAT_HEALTH=$(cat "$bat/health" 2>/dev/null || echo "Unknown")
    BAT_PRESENT=$(cat "$bat/present" 2>/dev/null || echo "0")
    BAT_ENERGY_FULL=$(cat "$bat/energy_full" 2>/dev/null || echo "0")
    BAT_AC_ONLINE=$(cat "$ac/online" 2>/dev/null || echo "0")

    BAT_VOLTAGE_MV=$((BAT_VOLTAGE_UA / 1000))
    BAT_VOLTAGE_V=$(awk "BEGIN {printf \"%.3f\", $BAT_VOLTAGE_UA / 1000000}")
    BAT_CURRENT_MA=$((BAT_CURRENT_UA / 1000))
    BAT_CHARGE_RATE_MA=$((BAT_CHARGE_RATE_UA / 1000))
    BAT_CHARGE_MAX_MA=$((BAT_CHARGE_MAX_UA / 1000))
    BAT_POWER_MW=$((BAT_VOLTAGE_MV * BAT_CURRENT_MA / 1000))

    if [ "$BAT_AC_ONLINE" = "1" ]; then
        BAT_SOURCE="AC (plugged in)"
    else
        BAT_SOURCE="Battery (unplugged)"
    fi
}

# ── logging ──

log_entry() {
    local action="$1" detail="$2"
    # strip newlines and collapse whitespace to prevent log corruption
    detail=$(printf '%s' "$detail" | tr '\n' ' ' | sed 's/  */ /g')
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $action | $detail" >> "$LOG_FILE"
}

# ── staging ──
# No hardcoded path list. git_sync stages everything not in .gitignore.
# Drop a file or folder in the repo → it gets backed up. That simple.

# ── build commit message from staged diff ──
#
# Inspects git's staging area and derives a descriptive message.
# Maps changed directories to human-readable category labels.

build_commit_message() {
    local file_count
    file_count=$(git diff --cached --numstat | wc -l)

    # detect which categories have staged changes
    local -A seen
    local labels=()
    while IFS= read -r path; do
        local dir="${path%%/*}"
        local label=""
        case "$dir" in
            shell|ssh)   label="git" ;;
            packages)    label="packages" ;;
            system)      label="system" ;;
            scripts)     label="scripts" ;;
            dotfiles)    label="dotfiles" ;;
            retropie)    label="retropie" ;;
            emulators)   label="emulators" ;;
            drivers)     label="drivers" ;;
            config)
                # config/ holds multiple categories — check subdirectory
                local subdir
                subdir=$(echo "$path" | cut -d/ -f2)
                case "$subdir" in
                    gh)           label="gh" ;;
                    chromium)     label="browser" ;;
                    dconf|gtk-*)  label="desktop" ;;
                    systemd-user) label="system" ;;
                    *)            label="config" ;;
                esac
                ;;
            *)  label="$dir" ;;
        esac
        if [ -n "$label" ] && [ -z "${seen[$label]:-}" ]; then
            seen[$label]=1
            labels+=("$label")
        fi
    done < <(git diff --cached --name-only)

    local label_str
    if [ ${#labels[@]} -eq 0 ]; then
        label_str="backup"
    elif [ ${#labels[@]} -le 4 ]; then
        label_str=$(IFS=,; echo "${labels[*]}")
    else
        label_str="all"
    fi

    echo "backup($label_str): $(date '+%Y-%m-%d %H:%M') — ${file_count} file(s)"
}

# ── git sync ──
#
# Pulls, stages all managed paths, builds a commit message from what
# actually changed, commits, and pushes. One network round-trip.
#
# Usage: git_sync [--quiet]
#
# This is the ONLY function that touches the network. Gather functions
# just modify the working tree. Sync commits whatever is dirty.

git_sync() {
    local quiet=false
    [[ "${1:-}" == "--quiet" ]] && quiet=true

    section "Git Sync"

    cd "$REPO_DIR" || { err "Cannot cd to $REPO_DIR"; return 1; }

    # 1. stage everything not in .gitignore
    git add -A 2>/dev/null

    # 2. check if anything is staged
    if git diff --cached --quiet 2>/dev/null; then
        ok "Nothing to commit — working tree clean"
        log_entry "sync" "no changes"
        return 0
    fi

    # 3. show what's staged
    local staged_count
    staged_count=$(git diff --cached --numstat | wc -l)
    if [ "$quiet" = false ]; then
        echo ""
        git diff --cached --stat | head -20
        echo ""
    fi

    # 4. commit locally first (always succeeds — clean tree for rebase)
    local commit_msg
    commit_msg=$(build_commit_message)
    info "Committing: $commit_msg"

    if git commit -m "$commit_msg" --quiet; then
        ok "Committed"
    else
        err "Commit failed"
        log_entry "sync" "commit FAILED"
        return 1
    fi

    # 5. rebase on remote (if remote is ahead, our commit goes on top)
    info "Syncing with origin..."
    if git pull --rebase --quiet 2>&1; then
        ok "Up to date with origin"
    else
        warn "Pull failed — pushing local commit anyway"
    fi

    # 6. push
    info "Pushing to origin..."
    if git push --quiet 2>&1; then
        ok "Pushed to GitHub"
        log_entry "sync" "$commit_msg"
    else
        err "Push failed — commit is local only"
        log_entry "sync" "push FAILED (commit is local)"
        return 1
    fi
}

# ── backward compat alias ──
git_commit_and_push() { git_sync "$@"; }
