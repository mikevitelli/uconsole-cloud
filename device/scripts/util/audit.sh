#!/bin/bash
# Repo hygiene auditor for the uConsole backup system
# Usage: audit.sh              Overview — repo health at a glance
#        audit.sh junk         Detailed junk file scan by category
#        audit.sh clean        Interactive cleanup (git rm --cached + .gitignore)
#        audit.sh untracked    Show files that will be picked up by next git add -A
#        audit.sh categories   Show tracked files grouped by backup category

# source lib.sh relative to this script's actual location
_AUDIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_AUDIT_DIR/lib.sh"

# ── junk patterns ──
# Format: "glob:category" — extend this list as needed

JUNK_PATTERNS=(
    # bytecode / compiled
    "*.pyc:bytecode"
    "*.pyo:bytecode"
    "*.class:bytecode"
    "*.o:bytecode"
    "*.so:bytecode"
    # caches
    "__pycache__/*:cache"
    "node_modules/*:cache"
    ".cache/*:cache"
    # logs
    "*.log:log"
    "debug.txt:log"
    # IDE / editor
    "*.swp:ide"
    "*.swo:ide"
    ".DS_Store:ide"
    "Thumbs.db:ide"
    ".idea/*:ide"
    "*.code-workspace:ide"
    "*.lock:ide"
    # temp
    "*.tmp:temp"
    "*.bak:temp"
    "*~:temp"
    # OS junk
    ".Trash-*:os"
    ".directory:os"
)

# ── helpers ──

# Match a filename against junk patterns. Prints category if matched.
match_junk() {
    local file="$1"
    local base
    base=$(basename "$file")
    for entry in "${JUNK_PATTERNS[@]}"; do
        local pattern="${entry%%:*}"
        local category="${entry##*:}"
        # match against full path and basename
        # shellcheck disable=SC2254
        case "$file" in $pattern) echo "$category"; return 0 ;; esac
        case "$base" in $pattern) echo "$category"; return 0 ;; esac
    done
    return 1
}

# Map a file path to a backup category (mirrors build_commit_message logic)
classify_file() {
    local path="$1"
    local dir="${path%%/*}"
    case "$dir" in
        shell|ssh)      echo "git" ;;
        packages)       echo "packages" ;;
        system)         echo "system" ;;
        scripts)        echo "scripts" ;;
        dotfiles)       echo "dotfiles" ;;
        retropie|bios)  echo "retropie" ;;
        emulators)      echo "emulators" ;;
        drivers)        echo "drivers" ;;
        docs)           echo "docs" ;;
        vercel-dashboard) echo "vercel" ;;
        desktop)        echo "desktop" ;;
        misc)           echo "misc" ;;
        config)
            local subdir
            subdir=$(echo "$path" | cut -d/ -f2)
            case "$subdir" in
                gh)           echo "gh" ;;
                chromium)     echo "browser" ;;
                dconf|gtk-*)  echo "desktop" ;;
                systemd-user) echo "system" ;;
                FlashGBX)     echo "flashgbx" ;;
                *)            echo "config" ;;
            esac
            ;;
        *)
            # root-level files
            case "$path" in
                */*) echo "other" ;;
                *)   echo "root" ;;
            esac
            ;;
    esac
}

# Human-readable size
human_size() {
    numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "${1}B"
}

# Get size of a file, 0 if missing
file_size() {
    stat -c%s "$REPO_DIR/$1" 2>/dev/null || echo 0
}

# ── overview (default) ──

cmd_overview() {
    section "Repo Health"

    cd "$REPO_DIR" || return 1

    # total tracked files
    local total_files
    total_files=$(git ls-files | wc -l)

    # total size
    local total_size=0
    while IFS= read -r f; do
        local s
        s=$(stat -c%s "$f" 2>/dev/null || echo 0)
        total_size=$((total_size + s))
    done < <(git ls-files)

    printf "  ${BOLD}%d${RESET} tracked files  ${DIM}(%s)${RESET}\n" "$total_files" "$(human_size $total_size)"

    # junk scan
    section "Junk Files"
    local junk_count=0 junk_size=0
    while IFS= read -r f; do
        if match_junk "$f" >/dev/null; then
            junk_count=$((junk_count + 1))
            local s
            s=$(stat -c%s "$f" 2>/dev/null || echo 0)
            junk_size=$((junk_size + s))
        fi
    done < <(git ls-files)

    if [ "$junk_count" -gt 0 ]; then
        warn "$junk_count junk files found ($(human_size $junk_size))"
        info "Run: audit.sh junk"
    else
        ok "No junk files detected"
    fi

    # large files
    section "Large Files (>1MB)"
    local large_count=0
    while IFS= read -r f; do
        local s
        s=$(stat -c%s "$f" 2>/dev/null || echo 0)
        if [ "$s" -gt 1048576 ]; then
            warn "$(human_size $s)  $f"
            large_count=$((large_count + 1))
        fi
    done < <(git ls-files)

    [ "$large_count" -eq 0 ] && ok "No files over 1MB"

    # last commit
    section "Last Commit"
    git log -1 --format="  %C(auto)%h%Creset %s %C(dim)(%ar)%Creset"
    echo ""
    while IFS= read -r f; do
        [ -n "$f" ] && info "  $f"
    done < <(git diff-tree --no-commit-id --name-only -r HEAD)

    # untracked
    section "Pending (Untracked)"
    local untracked_count
    untracked_count=$(git ls-files --others --exclude-standard | wc -l)

    if [ "$untracked_count" -gt 0 ]; then
        warn "$untracked_count untracked file(s) will be added on next sync"
        info "Run: audit.sh untracked"
    else
        ok "No pending untracked files"
    fi
}

# ── junk scan ──

cmd_junk() {
    section "Junk File Scan"

    cd "$REPO_DIR" || return 1

    # collect junk by category
    declare -A cat_files cat_sizes
    local total_junk=0 total_junk_size=0

    while IFS= read -r f; do
        local cat
        cat=$(match_junk "$f") || continue
        local s
        s=$(stat -c%s "$f" 2>/dev/null || echo 0)
        cat_files[$cat]="${cat_files[$cat]:-}${f}\n"
        cat_sizes[$cat]=$(( ${cat_sizes[$cat]:-0} + s ))
        total_junk=$((total_junk + 1))
        total_junk_size=$((total_junk_size + s))
    done < <(git ls-files)

    if [ "$total_junk" -eq 0 ]; then
        ok "No junk files found"
        return 0
    fi

    for cat in bytecode cache log ide temp os; do
        [ -z "${cat_files[$cat]:-}" ] && continue
        local size="${cat_sizes[$cat]}"
        printf "\n  ${BOLD}${YELLOW}%s${RESET}  ${DIM}%s${RESET}\n" "$cat" "$(human_size $size)"
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            local s
            s=$(stat -c%s "$f" 2>/dev/null || echo 0)
            printf "    ${DIM}%8s${RESET}  %s\n" "$(human_size $s)" "$f"
        done < <(printf '%b' "${cat_files[$cat]}")
    done

    section "Summary"
    warn "$total_junk junk files ($(human_size $total_junk_size))"
    info "Run: audit.sh clean — to remove from repo and add to .gitignore"
}

# ── clean ──

cmd_clean() {
    local auto_yes=false
    [[ "${1:-}" == "--yes" ]] && auto_yes=true

    section "Cleanup (non-destructive)"
    info "Files will be removed from git tracking but kept on disk"

    cd "$REPO_DIR" || return 1

    # find junk
    local -a junk_files=()
    local -A junk_patterns_found
    while IFS= read -r f; do
        local cat
        cat=$(match_junk "$f") || continue
        junk_files+=("$f")
        # find which pattern matched for .gitignore
        local base
        base=$(basename "$f")
        for entry in "${JUNK_PATTERNS[@]}"; do
            local pattern="${entry%%:*}"
            # shellcheck disable=SC2254
            case "$base" in $pattern) junk_patterns_found[$pattern]=1; break ;; esac
            case "$f" in $pattern) junk_patterns_found[$pattern]=1; break ;; esac
        done
    done < <(git ls-files)

    if [ ${#junk_files[@]} -eq 0 ]; then
        ok "Nothing to clean"
        return 0
    fi

    echo ""
    warn "${#junk_files[@]} junk file(s) to remove:"
    for f in "${junk_files[@]}"; do
        printf "    ${RED}✗${RESET} %s\n" "$f"
    done

    echo ""
    info "Patterns to add to .gitignore:"
    for p in "${!junk_patterns_found[@]}"; do
        printf "    ${GREEN}+${RESET} %s\n" "$p"
    done
    echo ""

    if [ "$auto_yes" = false ]; then
        printf "  ${BOLD}Remove from repo and update .gitignore? [y/N]${RESET} "
        read -r answer
        [[ "$answer" != [yY] ]] && { info "Aborted"; return 0; }
    fi

    # remove from tracking
    local removed=0
    for f in "${junk_files[@]}"; do
        if git rm --cached "$f" --quiet 2>/dev/null; then
            removed=$((removed + 1))
        fi
    done

    # add patterns to .gitignore
    local added=0
    for p in "${!junk_patterns_found[@]}"; do
        if ! grep -qxF "$p" "$REPO_DIR/.gitignore" 2>/dev/null; then
            echo "$p" >> "$REPO_DIR/.gitignore"
            added=$((added + 1))
        fi
    done

    echo ""
    ok "Removed $removed file(s) from tracking"
    [ "$added" -gt 0 ] && ok "Added $added pattern(s) to .gitignore"
    info "Files still exist on disk. Run 'backup.sh sync' to commit cleanup."
}

# ── untracked ──

cmd_untracked() {
    section "Untracked Files"
    info "These will be added to the repo on next git add -A / sync"

    cd "$REPO_DIR" || return 1

    local count=0 total_size=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        count=$((count + 1))
        local s
        s=$(stat -c%s "$f" 2>/dev/null || echo 0)
        total_size=$((total_size + s))

        local flag=""
        if match_junk "$f" >/dev/null; then
            flag="${RED}[JUNK]${RESET}"
        elif [ "$s" -gt 1048576 ]; then
            flag="${YELLOW}[LARGE]${RESET}"
        fi

        printf "  %8s  %s  %b\n" "$(human_size $s)" "$f" "$flag"
    done < <(git ls-files --others --exclude-standard)

    echo ""
    if [ "$count" -eq 0 ]; then
        ok "No untracked files"
    else
        info "$count file(s) ($(human_size $total_size))"
    fi
}

# ── categories ──

cmd_categories() {
    section "Backup Categories"

    cd "$REPO_DIR" || return 1

    declare -A cat_count cat_size
    local max_count=0

    while IFS= read -r f; do
        local cat
        cat=$(classify_file "$f")
        cat_count[$cat]=$(( ${cat_count[$cat]:-0} + 1 ))
        local s
        s=$(stat -c%s "$f" 2>/dev/null || echo 0)
        cat_size[$cat]=$(( ${cat_size[$cat]:-0} + s ))
        [ "${cat_count[$cat]}" -gt "$max_count" ] && max_count="${cat_count[$cat]}"
    done < <(git ls-files)

    # display in a fixed order
    for cat in git gh system packages desktop browser scripts dotfiles retropie emulators drivers flashgbx docs vercel config misc root other; do
        [ -z "${cat_count[$cat]:-}" ] && continue
        local c="${cat_count[$cat]}"
        local s="${cat_size[$cat]}"
        printf "  %-16s ${BOLD}%4d${RESET} files  ${DIM}%8s${RESET}  " "$cat" "$c" "$(human_size $s)"
        bar "$c" "$max_count" 15
        echo ""
    done
}

# ── main (only when executed, not sourced) ──

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        junk)       cmd_junk ;;
        clean)      cmd_clean "${2:-}" ;;
        untracked)  cmd_untracked ;;
        categories) cmd_categories ;;
        *)          cmd_overview ;;
    esac
fi
