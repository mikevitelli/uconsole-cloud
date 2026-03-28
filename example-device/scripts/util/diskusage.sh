#!/bin/bash
# Disk usage analyzer for the uConsole
# Usage: diskusage.sh              Overview of disk usage
#        diskusage.sh big           Find largest files (>50MB)
#        diskusage.sh dirs [path]   Top directories by size (default: ~/)
#        diskusage.sh clean         Show safe cleanup candidates

source "$(dirname "$0")/lib.sh"

cmd_overview() {
    echo "┌─────────────────────────────────────────┐"
    echo "│          uConsole Disk Usage             │"
    echo "├─────────────────────────────────────────┤"

    df -h / /boot 2>/dev/null | awk 'NR>1{
        printf "│  %-10s %5s / %-5s  %4s used     │\n", $6, $3, $2, $5
    }'

    echo "├─────────────────────────────────────────┤"
    echo "│  Top directories in ~/                  │"
    echo "├─────────────────────────────────────────┤"

    du -sh ~/*/  2>/dev/null | sort -rh | head -15 | while read -r size dir; do
        name=$(basename "$dir")
        printf "│  %8s  %-30s│\n" "$size" "$name/"
    done

    echo "├─────────────────────────────────────────┤"

    # hidden dirs
    echo "│  Top hidden directories in ~/           │"
    echo "├─────────────────────────────────────────┤"

    du -sh ~/.*/ 2>/dev/null | grep -v '/\.\.\?/$' | sort -rh | head -10 | while read -r size dir; do
        name=$(basename "$dir")
        printf "│  %8s  %-30s│\n" "$size" "$name/"
    done

    echo "└─────────────────────────────────────────┘"
}

cmd_big() {
    echo "Files larger than 50MB in ~/:"
    echo ""
    printf "  %-10s  %s\n" "SIZE" "FILE"
    printf "  %-10s  %s\n" "----------" "----"
    find ~/ -xdev -type f -size +50M 2>/dev/null | while read -r f; do
        size=$(du -sh "$f" 2>/dev/null | awk '{print $1}')
        printf "  %-10s  %s\n" "$size" "${f/#$HOME/~}"
    done | sort -rh
}

cmd_dirs() {
    local target="${1:-$HOME}"
    echo "Top 20 directories by size in $target:"
    echo ""
    printf "  %-10s  %s\n" "SIZE" "DIRECTORY"
    printf "  %-10s  %s\n" "----------" "---------"
    du -sh "$target"/*/ "$target"/.*/  2>/dev/null | grep -v '/\.\.\?/$' | sort -rh | head -20 | while read -r size dir; do
        printf "  %-10s  %s\n" "$size" "${dir/#$HOME/~}"
    done
}

cmd_clean() {
    echo "┌─────────────────────────────────────────┐"
    echo "│       Cleanup Candidates                │"
    echo "├─────────────────────────────────────────┤"

    # apt cache
    apt_cache=$(du -sh /var/cache/apt/archives/ 2>/dev/null | awk '{print $1}')
    printf "│  %-8s  apt cache                     │\n" "$apt_cache"
    echo "│           sudo apt clean                │"
    echo "│                                         │"

    # journal logs
    journal=$(journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+[KMGT]')
    printf "│  %-8s  systemd journal logs           │\n" "${journal:-?}"
    echo "│           sudo journalctl --vacuum-size=50M │"
    echo "│                                         │"

    # thumbnails
    thumb=$(du -sh ~/.cache/thumbnails/ 2>/dev/null | awk '{print $1}')
    printf "│  %-8s  thumbnails cache               │\n" "${thumb:-0}"
    echo "│           rm -rf ~/.cache/thumbnails/*  │"
    echo "│                                         │"

    # general cache
    cache=$(du -sh ~/.cache/ 2>/dev/null | awk '{print $1}')
    printf "│  %-8s  ~/.cache total                 │\n" "${cache:-0}"
    echo "│           (review before clearing)      │"
    echo "│                                         │"

    # tmp
    tmp=$(du -sh /tmp/ 2>/dev/null | awk '{print $1}')
    printf "│  %-8s  /tmp                           │\n" "${tmp:-0}"
    echo "│                                         │"

    # old kernels
    old_kernels=$(dpkg -l 'linux-image-*' 2>/dev/null | grep '^ii' | wc -l)
    printf "│  %-8s  installed kernel images        │\n" "$old_kernels"
    echo "│           sudo apt autoremove           │"
    echo "│                                         │"

    # snap cache
    snap_cache=$(du -sh /var/lib/snapd/cache/ 2>/dev/null | awk '{print $1}')
    printf "│  %-8s  snap cache                     │\n" "${snap_cache:-0}"
    echo "│           sudo rm /var/lib/snapd/cache/* │"
    echo "│                                         │"

    # orphaned packages
    orphans=$(apt list --installed 2>/dev/null | wc -l)
    autoremovable=$(apt-get --dry-run autoremove 2>/dev/null | grep -c '^Remv')
    printf "│  %-8s  autoremovable packages         │\n" "$autoremovable"
    echo "│           sudo apt autoremove           │"
    echo "└─────────────────────────────────────────┘"
}

case "${1:-}" in
    big)    cmd_big ;;
    dirs)   cmd_dirs "$2" ;;
    clean)  cmd_clean ;;
    *)      cmd_overview ;;
esac
