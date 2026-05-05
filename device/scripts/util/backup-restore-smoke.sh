#!/bin/bash
# backup-restore-smoke.sh — assert backup ↔ restore symmetry
#
# Static analysis check that catches the class of bug where a cmd_* writes
# to a path that restore.sh doesn't read (backup data orphaned), or
# restore.sh reads a path that no cmd_* produces (restore silently skips).
#
# Usage: backup-restore-smoke.sh           Run all checks, exit non-zero on drift
#        backup-restore-smoke.sh --verbose Show every checked path
#
# Wire into CI or run before /publish. Cheap (~1s), high signal.

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_TOOL=1
source "$_SCRIPT_DIR/lib.sh"

VERBOSE=false
[ "${1:-}" = "--verbose" ] && VERBOSE=true

BACKUP_SH="$REPO_DIR/scripts/system/backup.sh"
RESTORE_SH="$REPO_DIR/restore.sh"

# Normalize both scripts so their path references use the same prefix.
# backup.sh uses $SYS_DIR/etc/foo while restore.sh uses $REPO_DIR/system/etc/foo —
# substitute the variable shorthand to canonical "system/" / "packages/" / etc.
# so a single grep pattern matches both sides.
TMPDIR_SMOKE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_SMOKE"' EXIT
sed -e 's|\$SYS_DIR|system|g' \
    -e 's|\$PKG_DIR|packages|g' \
    -e 's|\$GH_DIR|config/gh|g' \
    -e 's|\$SHELL_DIR|shell|g' \
    -e 's|\$SSH_DIR|ssh|g' \
    -e 's|\$REPO_DIR/||g' \
    "$BACKUP_SH" > "$TMPDIR_SMOKE/backup.normalized"
sed -e 's|\$REPO_DIR/||g' "$RESTORE_SH" > "$TMPDIR_SMOKE/restore.normalized"
BACKUP_SH="$TMPDIR_SMOKE/backup.normalized"
RESTORE_SH="$TMPDIR_SMOKE/restore.normalized"

# Categories we expect to see on BOTH sides. Format: "label:path-fragment"
# path-fragment is grepped against the normalized scripts. Keep fragments
# slash-free at the end so they match both `system/wifi` (no slash) and
# `system/wifi/` (with slash) and `system/wifi"/` (quoted-then-slash).
EXPECTED_PAIRS=(
    "shell:shell"
    "ssh-pub:ssh"
    "wifi:system/wifi"
    "alsa:system/alsa/asound.state"
    "boot-config:system/boot/config.txt"
    "boot-cmdline:system/boot/cmdline.txt"
    "etc-hostname:system/etc/hostname"
    "etc-hosts:system/etc/hosts"
    "etc-fstab:system/etc/fstab"
    "etc-sshd:system/etc/sshd_config"
    "etc-locale:system/etc/locale"
    "etc-timezone:system/etc/timezone"
    "etc-keyboard:system/etc/keyboard"
    "etc-sudoers:system/etc/sudoers.d"
    "etc-crontab:system/etc/crontab.user"
    "udev:system/udev"
    "apt-list:system/apt/sources.list"
    "apt-list-d:system/apt/sources.list.d"
    "apt-manual:packages/apt-manual.txt"
    "flatpak:packages/flatpak.txt"
    "snap:packages/snap.txt"
    "systemd-user:config/systemd-user"
    "gh-config:config/gh"
    "dconf:config/dconf"
    "gtk:config/gtk-"
    "pulse:config/pulse"
)

# Paths produced by backup but intentionally not consumed by restore.
# (e.g. snapshots that are reference-only, or things you'd reinstall manually)
BACKUP_ONLY_WHITELIST=(
    "packages/apt-installed-all.txt"  # reference snapshot, restore uses apt-manual
    "packages/npm-global.txt"          # reference list, no auto-restore
    "packages/cargo.txt"               # reference list
    "packages/pip-user.txt"            # reference list
    "packages/vscode-extensions.txt"   # reference list
    "config/gh/extensions.txt"         # reference list
    "config/gh/repos.txt"              # reference list
    "config/themes.txt"                # reference list
    "config/chromium/"                 # reference snapshot
    "config/mimeapps.list"             # symlinked back, not copied
    "scripts/manifest.txt"             # generated catalogue
)

# Paths consumed by restore but produced by hand (not by any cmd_*).
# Document them here so the symmetry check doesn't false-positive.
RESTORE_ONLY_WHITELIST=(
    "dotfiles/"             # hand-curated, symlinked at restore time
    "system/ssl/"           # hand-curated webdash certs
    "system/etc/logind.conf.d/"  # hand-curated
    "system/etc/modprobe.d/"     # hand-curated
    "system/etc/systemd/"   # hand-curated
)

PASS=0
FAIL=0
WARN=0

check_pair() {
    local label="$1" frag="$2"
    local in_backup=0 in_restore=0

    grep -q -F "$frag" "$BACKUP_SH" && in_backup=1
    grep -q -F "$frag" "$RESTORE_SH" && in_restore=1

    # restore.sh has a `for d in config/*/` symlink loop that auto-covers
    # any backup-side write under config/. Recognize it so we don't
    # false-positive on every config/ subdir.
    if [[ "$frag" == config/* ]] && grep -q 'for d in "\?\$REPO_DIR\?"\?/config/\*' "$RESTORE_SH"; then
        in_restore=1
    fi

    if [ "$in_backup" = 1 ] && [ "$in_restore" = 1 ]; then
        $VERBOSE && ok "$label: backup ✓ restore ✓ ($frag)"
        PASS=$((PASS + 1))
    elif [ "$in_backup" = 0 ] && [ "$in_restore" = 1 ]; then
        warn "$label: restore reads $frag but no cmd_* writes it"
        WARN=$((WARN + 1))
    elif [ "$in_backup" = 1 ] && [ "$in_restore" = 0 ]; then
        # check whitelist
        local ok_unread=0
        for w in "${BACKUP_ONLY_WHITELIST[@]}"; do
            [[ "$frag" == "$w"* ]] && ok_unread=1 && break
        done
        if [ "$ok_unread" = 1 ]; then
            $VERBOSE && info "$label: backup-only (whitelisted) — $frag"
        else
            err "$label: cmd_* writes $frag but restore.sh never reads it"
            FAIL=$((FAIL + 1))
        fi
    else
        err "$label: neither backup nor restore handles $frag"
        FAIL=$((FAIL + 1))
    fi
}

section "Backup ↔ Restore Symmetry"

if [ ! -f "$BACKUP_SH" ]; then
    err "backup.sh not found at $BACKUP_SH"
    exit 1
fi
if [ ! -f "$RESTORE_SH" ]; then
    err "restore.sh not found at $RESTORE_SH"
    exit 1
fi

for pair in "${EXPECTED_PAIRS[@]}"; do
    label="${pair%%:*}"
    frag="${pair#*:}"
    check_pair "$label" "$frag"
done

section "Subdirectory Coverage"

# For each top-level backup subdir, list its immediate child dirs and check
# that at least one of (backup.sh, restore.sh) references each. Catches
# wholesale category gaps without drowning in per-file noise.
#
# config/* is auto-covered by restore.sh's symlink loop, so anything under
# config/ is considered handled even without a direct grep match.
HAS_CONFIG_GLOB=0
grep -q 'for d in "\?\$REPO_DIR\?"\?/config/\*' "$RESTORE_SH" && HAS_CONFIG_GLOB=1

DRIFT=0
for top in system packages config; do
    [ -d "$REPO_DIR/$top" ] || continue
    while IFS= read -r -d '' subdir; do
        rel="${subdir#$REPO_DIR/}"
        skip=0
        for w in "${RESTORE_ONLY_WHITELIST[@]}" "${BACKUP_ONLY_WHITELIST[@]}"; do
            [[ "$rel/" == "$w"* ]] && skip=1 && break
        done
        [ "$skip" = 1 ] && continue
        # config/* covered by restore.sh's symlink loop
        if [ "$HAS_CONFIG_GLOB" = 1 ] && [[ "$rel" == config/* ]]; then
            $VERBOSE && ok "$rel/ covered (via config/* symlink loop)"
            continue
        fi
        if ! grep -q -F "$rel/" "$BACKUP_SH" "$RESTORE_SH" 2>/dev/null \
           && ! grep -q -F "$rel\"" "$BACKUP_SH" "$RESTORE_SH" 2>/dev/null; then
            warn "$rel/ — present on disk but no script references this category"
            DRIFT=$((DRIFT + 1))
        elif $VERBOSE; then
            ok "$rel/ covered"
        fi
    done < <(find "$REPO_DIR/$top" -mindepth 1 -maxdepth 2 -type d -print0 2>/dev/null)
done

WARN=$((WARN + DRIFT))

section "Summary"
ok "$PASS pair(s) symmetric"
[ "$WARN" -gt 0 ] && warn "$WARN warning(s)"
[ "$FAIL" -gt 0 ] && err "$FAIL failure(s)"

if [ "$FAIL" -gt 0 ]; then
    exit 1
elif [ "$WARN" -gt 0 ]; then
    exit 2
fi
exit 0
