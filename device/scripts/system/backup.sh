#!/bin/bash
# Comprehensive backup manager for the uConsole monorepo
# Usage: backup.sh              Interactive backup menu
#        backup.sh all          Run all backups
#        backup.sh git          Backup git config and SSH keys
#        backup.sh gh           Backup GitHub CLI config, extensions, and repos
#        backup.sh system       Backup /etc configs, hostname, fstab, crontab
#        backup.sh packages     Snapshot all package managers (apt, flatpak, snap, npm, pip, cargo, vscode)
#        backup.sh desktop      Backup dconf, GTK themes, fonts
#        backup.sh browser      Backup Chromium bookmarks and extensions list
#        backup.sh status       Show backup coverage overview

source "$(dirname "$0")/lib.sh"

# ── git ──

cmd_git() {
    section "Git Config"

    # .gitconfig
    if [ -L "$HOME/.gitconfig" ]; then
        local target
        target=$(readlink -f "$HOME/.gitconfig")
        ok ".gitconfig symlinked -> $target"
    elif [ -f "$HOME/.gitconfig" ]; then
        cp "$HOME/.gitconfig" "$SHELL_DIR/.gitconfig"
        ok ".gitconfig backed up"
    else
        warn "No .gitconfig found"
    fi

    # global gitignore
    local gitignore
    gitignore=$(git config --global core.excludesFile 2>/dev/null)
    if [ -n "$gitignore" ] && [ -f "$gitignore" ]; then
        cp "$gitignore" "$SHELL_DIR/.gitignore_global"
        ok "Global gitignore backed up"
    else
        info "No global gitignore configured"
    fi

    local name email
    name=$(git config --global user.name 2>/dev/null)
    email=$(git config --global user.email 2>/dev/null)
    info "User: $name <$email>"

    section "SSH Keys"

    mkdir -p "$SSH_DIR"

    local count=0
    for pubkey in "$HOME"/.ssh/*.pub; do
        [ -f "$pubkey" ] || continue
        cp "$pubkey" "$SSH_DIR/$(basename "$pubkey")"
        ok "$(basename "$pubkey") backed up"
        count=$((count + 1))
    done

    [ "$count" -eq 0 ] && warn "No SSH public keys found" || info "$count public key(s) backed up"

    if [ -f "$HOME/.ssh/config" ]; then
        cp "$HOME/.ssh/config" "$SSH_DIR/config"
        ok "SSH config backed up"
    fi

    info "Private keys are NOT backed up (by design)"
}

# ── gh ──

cmd_gh() {
    section "GitHub CLI Config"

    if ! command -v gh &>/dev/null; then
        err "gh CLI not installed"
        return 1
    fi

    mkdir -p "$GH_DIR"

    # config.yml
    if [ -f "$HOME/.config/gh/config.yml" ]; then
        local src dest
        src=$(readlink -f "$HOME/.config/gh/config.yml")
        dest="$GH_DIR/config.yml"
        [ "$src" != "$(readlink -f "$dest" 2>/dev/null)" ] && cp "$src" "$dest"
        ok "config.yml backed up"

        local aliases
        aliases=$(gh alias list 2>/dev/null)
        if [ -n "$aliases" ]; then
            info "Aliases:"
            echo "$aliases" | while read -r line; do info "  $line"; done
        fi
    else
        warn "No gh config.yml found"
    fi

    info "Auth status:"
    gh auth status 2>&1 | while read -r line; do info "  $line"; done

    section "GitHub CLI Extensions"

    local ext_list
    ext_list=$(gh extension list 2>/dev/null)

    if [ -z "$ext_list" ]; then
        info "No extensions installed"
    else
        echo "$ext_list" | awk '{print $1}' > "$GH_DIR/extensions.txt"
        ok "$(wc -l < "$GH_DIR/extensions.txt") extension(s) saved"
        echo "$ext_list" | while read -r name version rest; do info "  $name ($version)"; done
    fi

    section "GitHub Repos Snapshot"

    info "Fetching repo list..."
    local repos
    repos=$(gh repo list --limit 100 --json nameWithOwner,isPrivate,updatedAt \
        --template '{{range .}}{{.nameWithOwner}}{{"\t"}}{{if .isPrivate}}private{{else}}public{{end}}{{"\t"}}{{.updatedAt}}{{"\n"}}{{end}}' 2>/dev/null)

    if [ -z "$repos" ]; then
        warn "Could not fetch repos (auth issue?)"
        return 1
    fi

    echo "$repos" > "$GH_DIR/repos.txt"
    ok "$(echo "$repos" | wc -l) repo(s) saved"
}

# ── system ──

cmd_system() {
    section "System Configs"

    mkdir -p "$SYS_DIR/etc"

    # hostname
    if [ -f /etc/hostname ]; then
        cp /etc/hostname "$SYS_DIR/etc/hostname"
        ok "hostname: $(cat /etc/hostname)"
    fi

    # fstab
    if [ -f /etc/fstab ]; then
        cp /etc/fstab "$SYS_DIR/etc/fstab"
        ok "fstab backed up"
    fi

    # sshd config
    if [ -f /etc/ssh/sshd_config ]; then
        cp /etc/ssh/sshd_config "$SYS_DIR/etc/sshd_config"
        ok "sshd_config backed up"
    fi

    # sudoers (readable parts only)
    if [ -r /etc/sudoers.d/ ]; then
        mkdir -p "$SYS_DIR/etc/sudoers.d"
        for f in /etc/sudoers.d/*; do
            [ -f "$f" ] || continue
            local dest="$SYS_DIR/etc/sudoers.d/$(basename "$f")"
            sudo cp "$f" "$dest" 2>/dev/null && \
                sudo chown "$(id -u):$(id -g)" "$dest" && \
                chmod 644 "$dest" && \
                ok "sudoers.d/$(basename "$f") backed up"
        done
    fi

    # boot configs (already tracked, but refresh)
    if [ -f /boot/config.txt ]; then
        cp /boot/config.txt "$SYS_DIR/boot/config.txt"
        ok "boot/config.txt refreshed"
    fi
    if [ -f /boot/cmdline.txt ]; then
        cp /boot/cmdline.txt "$SYS_DIR/boot/cmdline.txt"
        ok "boot/cmdline.txt refreshed"
    fi

    # udev rules
    mkdir -p "$SYS_DIR/udev"
    local udev_count=0
    for rule in /etc/udev/rules.d/99-* /etc/udev/rules.d/100-*; do
        [ -f "$rule" ] || continue
        cp "$rule" "$SYS_DIR/udev/$(basename "$rule")"
        udev_count=$((udev_count + 1))
    done
    [ "$udev_count" -gt 0 ] && ok "$udev_count custom udev rule(s) backed up"

    # apt sources
    mkdir -p "$SYS_DIR/apt"
    if [ -f /etc/apt/sources.list ]; then
        cp /etc/apt/sources.list "$SYS_DIR/apt/sources.list"
    fi
    local src_count=0
    for src in /etc/apt/sources.list.d/*.list; do
        [ -f "$src" ] || continue
        cp "$src" "$SYS_DIR/apt/$(basename "$src")"
        src_count=$((src_count + 1))
    done
    [ "$src_count" -gt 0 ] && ok "$src_count apt source list(s) backed up"

    # /etc/hosts
    if [ -f /etc/hosts ]; then
        cp /etc/hosts "$SYS_DIR/etc/hosts"
        ok "hosts backed up"
    fi

    # locale
    if [ -f /etc/default/locale ]; then
        cp /etc/default/locale "$SYS_DIR/etc/locale"
        ok "locale: $(grep '^LANG=' /etc/default/locale 2>/dev/null | cut -d= -f2)"
    fi

    # timezone
    local tz
    tz=$(timedatectl show --property=Timezone --value 2>/dev/null)
    if [ -n "$tz" ]; then
        echo "$tz" > "$SYS_DIR/etc/timezone"
        ok "timezone: $tz"
    fi

    # keyboard layout
    if [ -f /etc/default/keyboard ]; then
        cp /etc/default/keyboard "$SYS_DIR/etc/keyboard"
        local layout
        layout=$(grep '^XKBLAYOUT=' /etc/default/keyboard | cut -d'"' -f2)
        ok "keyboard: $layout"
    fi

    section "WiFi Connections"

    local wifi_dir="/etc/NetworkManager/system-connections"
    if [ -d "$wifi_dir" ]; then
        mkdir -p "$SYS_DIR/wifi"
        local wifi_count=0
        for conn in "$wifi_dir"/*.nmconnection; do
            [ -f "$conn" ] || continue
            sudo cp "$conn" "$SYS_DIR/wifi/$(basename "$conn")" 2>/dev/null && \
                sudo chown "$(id -u):$(id -g)" "$SYS_DIR/wifi/$(basename "$conn")" && \
                chmod 600 "$SYS_DIR/wifi/$(basename "$conn")"
            wifi_count=$((wifi_count + 1))
        done
        if [ "$wifi_count" -gt 0 ]; then
            ok "$wifi_count WiFi connection(s) backed up"
            info "Contains passwords — ensure repo is private"
        else
            info "No saved WiFi connections"
        fi
    fi

    section "Crontab"

    local cron
    cron=$(crontab -l 2>/dev/null)
    if [ -n "$cron" ]; then
        echo "$cron" > "$SYS_DIR/etc/crontab.user"
        ok "User crontab backed up ($(echo "$cron" | grep -cv '^#\|^$') job(s))"
    else
        info "No user crontab"
    fi

    section "Audio"

    # PulseAudio / PipeWire config
    if [ -d "$HOME/.config/pulse" ]; then
        mkdir -p "$REPO_DIR/config/pulse"
        cp "$HOME/.config/pulse"/* "$REPO_DIR/config/pulse/" 2>/dev/null
        ok "PulseAudio config backed up"
    fi
    # ALSA state
    if [ -f /var/lib/alsa/asound.state ]; then
        mkdir -p "$SYS_DIR/alsa"
        sudo cp /var/lib/alsa/asound.state "$SYS_DIR/alsa/asound.state" 2>/dev/null && \
            sudo chown "$(id -u):$(id -g)" "$SYS_DIR/alsa/asound.state" && \
            ok "ALSA mixer state backed up"
    fi

    section "Systemd User Services"

    local svc_dir="$HOME/.config/systemd/user"
    if [ -d "$svc_dir" ] && [ "$(ls -A "$svc_dir" 2>/dev/null)" ]; then
        mkdir -p "$REPO_DIR/config/systemd-user"
        cp "$svc_dir"/*.service "$REPO_DIR/config/systemd-user/" 2>/dev/null
        cp "$svc_dir"/*.timer "$REPO_DIR/config/systemd-user/" 2>/dev/null
        ok "Systemd user services backed up"
    else
        info "No user systemd services"
    fi
}

# ── packages ──

cmd_packages() {
    section "Package Snapshots"

    mkdir -p "$PKG_DIR"

    # apt (manual = explicitly installed, not auto-pulled dependencies)
    info "Snapshotting apt packages..."
    apt-mark showmanual | sort > "$PKG_DIR/apt-manual.txt"
    ok "apt: $(wc -l < "$PKG_DIR/apt-manual.txt") manually installed packages"
    # also save the full list for reference
    dpkg --get-selections | grep -v deinstall | awk '{print $1}' | sort > "$PKG_DIR/apt-installed-all.txt"
    info "  (full list: $(wc -l < "$PKG_DIR/apt-installed-all.txt") total packages in apt-installed-all.txt)"

    # flatpak
    if command -v flatpak &>/dev/null; then
        flatpak list --app --columns=application 2>/dev/null | sort > "$PKG_DIR/flatpak.txt"
        ok "flatpak: $(wc -l < "$PKG_DIR/flatpak.txt") apps"
    else
        info "Flatpak not installed"
    fi

    # snap
    if command -v snap &>/dev/null; then
        snap list 2>/dev/null | tail -n +2 | awk '{print $1}' | sort > "$PKG_DIR/snap.txt"
        ok "snap: $(wc -l < "$PKG_DIR/snap.txt") packages"
    else
        info "Snap not installed"
    fi

    section "Dev Tool Packages"

    # npm global
    if command -v npm &>/dev/null; then
        npm list -g --depth=0 --parseable 2>/dev/null | tail -n +2 | xargs -I{} basename {} | sort > "$PKG_DIR/npm-global.txt"
        ok "npm global: $(wc -l < "$PKG_DIR/npm-global.txt") packages"
        local node_ver
        node_ver=$(node --version 2>/dev/null)
        info "Node: $node_ver"
    else
        info "npm not installed"
    fi

    # pip user
    if command -v pip3 &>/dev/null; then
        pip3 list --user --format=freeze 2>/dev/null | sort > "$PKG_DIR/pip-user.txt"
        local pip_count
        pip_count=$(wc -l < "$PKG_DIR/pip-user.txt")
        if [ "$pip_count" -gt 0 ]; then
            ok "pip user: $pip_count packages"
        else
            info "No pip user packages"
            rm -f "$PKG_DIR/pip-user.txt"
        fi
    else
        info "pip not installed"
    fi

    # cargo
    if command -v cargo &>/dev/null; then
        cargo install --list 2>/dev/null | grep -v '^ ' > "$PKG_DIR/cargo.txt"
        local cargo_count
        cargo_count=$(wc -l < "$PKG_DIR/cargo.txt")
        if [ "$cargo_count" -gt 0 ]; then
            ok "cargo: $cargo_count crate(s)"
        else
            info "No cargo crates installed"
            rm -f "$PKG_DIR/cargo.txt"
        fi
    else
        info "cargo not installed"
    fi

    # vscode extensions
    if command -v code &>/dev/null; then
        code --list-extensions 2>/dev/null | sort > "$PKG_DIR/vscode-extensions.txt"
        local ext_count
        ext_count=$(wc -l < "$PKG_DIR/vscode-extensions.txt")
        if [ "$ext_count" -gt 0 ]; then
            ok "vscode: $ext_count extension(s)"
        else
            info "No VS Code extensions"
            rm -f "$PKG_DIR/vscode-extensions.txt"
        fi
    else
        info "VS Code not installed"
    fi
}

# ── desktop ──

cmd_desktop() {
    section "Desktop Settings (dconf)"

    if command -v dconf &>/dev/null; then
        mkdir -p "$REPO_DIR/config/dconf"
        dconf dump / > "$REPO_DIR/config/dconf/dconf-dump.ini"
        local sections
        sections=$(grep -c '^\[' "$REPO_DIR/config/dconf/dconf-dump.ini")
        ok "dconf dumped ($sections sections)"
        info "Restore with: dconf load / < config/dconf/dconf-dump.ini"
    else
        info "dconf not available"
    fi

    section "GTK Themes"

    # gtk-3.0
    if [ -f "$HOME/.config/gtk-3.0/settings.ini" ]; then
        mkdir -p "$REPO_DIR/config/gtk-3.0"
        local src dest
        src=$(readlink -f "$HOME/.config/gtk-3.0/settings.ini")
        dest="$REPO_DIR/config/gtk-3.0/settings.ini"
        [ "$src" != "$(readlink -f "$dest" 2>/dev/null)" ] && cp "$src" "$dest"
        ok "GTK3 settings backed up"
    else
        info "No GTK3 settings"
    fi

    # gtk-4.0
    if [ -f "$HOME/.config/gtk-4.0/settings.ini" ]; then
        mkdir -p "$REPO_DIR/config/gtk-4.0"
        src=$(readlink -f "$HOME/.config/gtk-4.0/settings.ini")
        dest="$REPO_DIR/config/gtk-4.0/settings.ini"
        [ "$src" != "$(readlink -f "$dest" 2>/dev/null)" ] && cp "$src" "$dest"
        ok "GTK4 settings backed up"
    fi

    # mime associations
    if [ -f "$HOME/.config/mimeapps.list" ]; then
        src=$(readlink -f "$HOME/.config/mimeapps.list")
        dest="$REPO_DIR/config/mimeapps.list"
        [ "$src" != "$(readlink -f "$dest" 2>/dev/null)" ] && cp "$src" "$dest"
        ok "MIME associations backed up"
    fi

    section "Fonts"

    local font_dir="$HOME/.local/share/fonts"
    if [ -d "$font_dir" ] && [ "$(ls -A "$font_dir" 2>/dev/null)" ]; then
        mkdir -p "$REPO_DIR/config/fonts"
        cp -r "$font_dir"/* "$REPO_DIR/config/fonts/" 2>/dev/null
        local font_count
        font_count=$(find "$REPO_DIR/config/fonts" -type f | wc -l)
        ok "$font_count font file(s) backed up"
    else
        info "No custom fonts"
    fi

    section "Themes"

    local theme_dir="$HOME/.local/share/themes"
    if [ -d "$theme_dir" ] && [ "$(ls -A "$theme_dir" 2>/dev/null)" ]; then
        # save theme names only (themes can be large)
        ls -1 "$theme_dir" > "$REPO_DIR/config/themes.txt"
        ok "Theme list saved ($(wc -l < "$REPO_DIR/config/themes.txt") themes)"
        info "Full theme dirs not copied (re-download on restore)"
    else
        info "No custom themes"
    fi
}

# ── browser ──

cmd_browser() {
    section "Chromium Browser"

    local chrome_dir="$HOME/.config/chromium/Default"

    if [ ! -d "$chrome_dir" ]; then
        info "Chromium not found"
        return 0
    fi

    mkdir -p "$REPO_DIR/config/chromium"

    # bookmarks
    if [ -f "$chrome_dir/Bookmarks" ]; then
        cp "$chrome_dir/Bookmarks" "$REPO_DIR/config/chromium/Bookmarks.json"
        local bm_count
        bm_count=$(python3 -c "
import json, sys
def count(node):
    c = 0
    if node.get('type') == 'url': c = 1
    for child in node.get('children', []): c += count(child)
    return c
data = json.load(open(sys.argv[1]))
total = sum(count(v) for v in data.get('roots', {}).values() if isinstance(v, dict))
print(total)
" "$chrome_dir/Bookmarks" 2>/dev/null)
        ok "Bookmarks backed up ($bm_count bookmarks)"
    else
        info "No bookmarks file"
    fi

    # extensions list
    if [ -d "$chrome_dir/Extensions" ]; then
        local ext_file="$REPO_DIR/config/chromium/extensions.txt"
        > "$ext_file"
        for ext_dir in "$chrome_dir/Extensions"/*/; do
            [ -d "$ext_dir" ] || continue
            local manifest
            manifest=$(find "$ext_dir" -name manifest.json -maxdepth 2 2>/dev/null | head -1)
            if [ -n "$manifest" ]; then
                local ext_name ext_id
                ext_id=$(basename "$ext_dir")
                ext_name=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get('name','unknown'))" "$manifest" 2>/dev/null)
                echo "$ext_id  $ext_name" >> "$ext_file"
            fi
        done
        ok "$(wc -l < "$ext_file") extension(s) catalogued"
        while read -r line; do info "  $line"; done < "$ext_file"
    fi

    # preferences (non-sensitive)
    if [ -f "$chrome_dir/Preferences" ]; then
        # extract just the settings we care about
        python3 -c "
import json, sys
prefs = json.load(open(sys.argv[1]))
safe = {}
for key in ['browser', 'extensions.settings', 'default_search_provider', 'homepage']:
    parts = key.split('.')
    node = prefs
    for p in parts:
        node = node.get(p, {}) if isinstance(node, dict) else {}
    if node:
        safe[key] = True
print(json.dumps({'keys_present': list(safe.keys())}, indent=2))
" "$chrome_dir/Preferences" > "$REPO_DIR/config/chromium/preferences-summary.json" 2>/dev/null
        ok "Preferences summary saved"
    fi

    info "Full browser profile NOT backed up (cache, cookies, history)"
}

# ── scripts ──

cmd_scripts() {
    section "Scripts"

    local count=0
    local new_count=0

    # ensure all scripts are executable and tracked
    for script in "$SCRIPTS_DIR"/*.sh "$SCRIPTS_DIR"/*.py; do
        [ -f "$script" ] || continue
        local name
        name=$(basename "$script")
        count=$((count + 1))

        # make executable if not already
        if [ ! -x "$script" ]; then
            chmod +x "$script"
            warn "$name: made executable"
        fi

        # check if git-tracked
        if ! git -C "$REPO_DIR" ls-files --error-unmatch "scripts/$name" >/dev/null 2>&1; then
            git -C "$REPO_DIR" add "scripts/$name"
            new_count=$((new_count + 1))
            ok "$name: added to repo"
        fi
    done

    # save a manifest of scripts with sizes and descriptions
    local manifest="$SCRIPTS_DIR/scripts-manifest.txt"
    printf "%-20s  %8s  %s\n" "SCRIPT" "SIZE" "DESCRIPTION" > "$manifest"
    printf "%-20s  %8s  %s\n" "────────────────────" "────────" "────────────────────" >> "$manifest"
    for script in "$SCRIPTS_DIR"/*.sh "$SCRIPTS_DIR"/*.py; do
        [ -f "$script" ] || continue
        local name size desc
        name=$(basename "$script")
        size=$(du -h "$script" | cut -f1)
        # grab description from second line comment
        desc=$(sed -n '2s/^# *//p' "$script" 2>/dev/null)
        [ -z "$desc" ] && desc=$(sed -n '2s/^"""//;2s/"""$//p' "$script" 2>/dev/null)
        printf "%-20s  %8s  %s\n" "$name" "$size" "$desc" >> "$manifest"
    done
    ok "$count scripts catalogued"
    if [ "$new_count" -gt 0 ]; then
        ok "$new_count new script(s) staged"
    fi

    # show the manifest
    while IFS= read -r line; do info "  $line"; done < "$manifest"
}

# ── status ──

cmd_status() {
    section "Backup Coverage"

    printf "  ${BOLD}%-22s  %-18s  %s${RESET}\n" "CATEGORY" "STATUS" "DETAIL"
    printf "  ${DIM}%-22s  %-18s  %s${RESET}\n" "──────────────────────" "──────────────────" "────────────────────"

    # git
    if [ -L "$HOME/.gitconfig" ]; then
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "git config" "symlinked" ""
    elif [ -f "$SHELL_DIR/.gitconfig" ]; then
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "git config" "backed up" ""
    else
        printf "  %-22s  ${RED}%-18s${RESET}  %s\n" "git config" "missing" ""
    fi

    # ssh
    local keycount=0
    for pubkey in "$HOME"/.ssh/*.pub; do [ -f "$pubkey" ] && keycount=$((keycount + 1)); done
    printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "ssh keys" "$keycount key(s)" "public only"

    # gh
    if [ -f "$GH_DIR/config.yml" ]; then
        local age=$(( ($(date +%s) - $(stat -c %Y "$GH_DIR/config.yml")) / 86400 ))
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "github cli" "backed up" "${age}d ago"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "github cli" "not backed up" ""
    fi

    # system
    if [ -f "$SYS_DIR/etc/hostname" ]; then
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "system configs" "backed up" "hostname, fstab, sshd, udev, apt"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "system configs" "partial" "run: backup.sh system"
    fi

    # packages
    local pkg_status="apt"
    [ -f "$PKG_DIR/flatpak.txt" ] && pkg_status="$pkg_status, flatpak"
    [ -f "$PKG_DIR/snap.txt" ] && pkg_status="$pkg_status, snap"
    [ -f "$PKG_DIR/npm-global.txt" ] && pkg_status="$pkg_status, npm"
    [ -f "$PKG_DIR/cargo.txt" ] && pkg_status="$pkg_status, cargo"
    [ -f "$PKG_DIR/vscode-extensions.txt" ] && pkg_status="$pkg_status, vscode"
    if [ -f "$PKG_DIR/apt-manual.txt" ]; then
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "packages" "backed up" "$pkg_status"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "packages" "not backed up" ""
    fi

    # desktop
    if [ -f "$REPO_DIR/config/dconf/dconf-dump.ini" ]; then
        local age=$(( ($(date +%s) - $(stat -c %Y "$REPO_DIR/config/dconf/dconf-dump.ini")) / 86400 ))
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "desktop (dconf)" "backed up" "${age}d ago"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "desktop (dconf)" "not backed up" "run: backup.sh desktop"
    fi

    # browser
    if [ -d "$REPO_DIR/config/chromium" ] && [ "$(ls -A "$REPO_DIR/config/chromium" 2>/dev/null)" ]; then
        local browser_detail=""
        [ -f "$REPO_DIR/config/chromium/Bookmarks.json" ] && browser_detail="bookmarks"
        [ -f "$REPO_DIR/config/chromium/extensions.txt" ] && browser_detail="${browser_detail:+$browser_detail + }extensions"
        [ -f "$REPO_DIR/config/chromium/preferences-summary.json" ] && browser_detail="${browser_detail:+$browser_detail + }prefs"
        local newest
        newest=$(stat -c %Y "$REPO_DIR/config/chromium"/* 2>/dev/null | sort -rn | head -1)
        local age=$(( ($(date +%s) - ${newest:-0}) / 86400 ))
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "browser" "backed up" "${browser_detail} (${age}d ago)"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "browser" "not backed up" "run: backup.sh browser"
    fi

    # crontab
    local cron
    cron=$(crontab -l 2>/dev/null)
    if [ -n "$cron" ]; then
        if [ -f "$SYS_DIR/etc/crontab.user" ]; then
            printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "crontab" "backed up" ""
        else
            printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "crontab" "not backed up" "has jobs"
        fi
    else
        printf "  %-22s  ${DIM}%-18s${RESET}  %s\n" "crontab" "empty" ""
    fi

    # wifi
    local wifi_count=0
    [ -d "$SYS_DIR/wifi" ] && wifi_count=$(ls -1 "$SYS_DIR/wifi"/*.nmconnection 2>/dev/null | wc -l)
    if [ "$wifi_count" -gt 0 ]; then
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "wifi connections" "backed up" "$wifi_count network(s)"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "wifi connections" "not backed up" "run: backup.sh system"
    fi

    # locale/timezone/keyboard
    if [ -f "$SYS_DIR/etc/locale" ] && [ -f "$SYS_DIR/etc/timezone" ] && [ -f "$SYS_DIR/etc/keyboard" ]; then
        local tz
        tz=$(cat "$SYS_DIR/etc/timezone" 2>/dev/null)
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "locale/tz/keyboard" "backed up" "$tz"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "locale/tz/keyboard" "partial" "run: backup.sh system"
    fi

    # audio
    if [ -f "$SYS_DIR/alsa/asound.state" ] || [ -d "$REPO_DIR/config/pulse" ]; then
        printf "  %-22s  ${GREEN}%-18s${RESET}  %s\n" "audio" "backed up" "ALSA + PulseAudio"
    else
        printf "  %-22s  ${YELLOW}%-18s${RESET}  %s\n" "audio" "not backed up" "run: backup.sh system"
    fi

    echo ""

    # intentional exclusions
    info "Intentionally excluded:"
    info "  Private SSH keys, .bash_history, .cache, ROMs, snap app data"
    info "  Browser cache/cookies/history, .local runtime data"
}

# ── gather multiple categories ──

do_gather() {
    for cat in "$@"; do
        case "$cat" in
            git)      cmd_git ;;
            gh)       cmd_gh ;;
            system)   cmd_system ;;
            packages) cmd_packages ;;
            desktop)  cmd_desktop ;;
            browser)  cmd_browser ;;
            scripts)  cmd_scripts ;;
            all)      cmd_git; cmd_gh; cmd_system; cmd_packages; cmd_desktop; cmd_browser; cmd_scripts ;;
            *)        err "Unknown category: $cat"; return 1 ;;
        esac
    done
}

# ── interactive menu ──

cmd_interactive() {
    while true; do
        clear
        printf "${BOLD}${CYAN}"
        echo "  ╔═══════════════════════════════════════╗"
        echo "  ║       uConsole Backup Manager          ║"
        echo "  ╚═══════════════════════════════════════╝"
        printf "${RESET}"
        echo ""
        printf "  ${BOLD}${GREEN}1${RESET}  %-14s ${DIM}%s${RESET}\n" "all" "Gather all + sync to GitHub"
        printf "  ${BOLD}${GREEN}2${RESET}  %-14s ${DIM}%s${RESET}\n" "git" "Gather git config and SSH keys"
        printf "  ${BOLD}${GREEN}3${RESET}  %-14s ${DIM}%s${RESET}\n" "gh" "Gather GitHub CLI config"
        printf "  ${BOLD}${GREEN}4${RESET}  %-14s ${DIM}%s${RESET}\n" "system" "Gather /etc configs, hostname, crontab"
        printf "  ${BOLD}${GREEN}5${RESET}  %-14s ${DIM}%s${RESET}\n" "packages" "Gather package managers"
        printf "  ${BOLD}${GREEN}6${RESET}  %-14s ${DIM}%s${RESET}\n" "desktop" "Gather dconf, GTK themes, fonts"
        printf "  ${BOLD}${GREEN}7${RESET}  %-14s ${DIM}%s${RESET}\n" "browser" "Gather Chromium bookmarks"
        printf "  ${BOLD}${GREEN}8${RESET}  %-14s ${DIM}%s${RESET}\n" "status" "Show backup coverage"
        printf "  ${BOLD}${GREEN}9${RESET}  %-14s ${DIM}%s${RESET}\n" "sync" "Commit & push pending changes to GitHub"
        echo ""
        printf "  ${BOLD}${GREEN}q${RESET}  %-14s ${DIM}%s${RESET}\n" "quit" "Exit"
        echo ""
        printf "  ${BOLD}>${RESET} "
        read -r choice

        case "$choice" in
            1|all)      do_gather all; git_sync; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            2|git)      cmd_git; info "Gathered. Press 9 to sync, or gather more."; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            3|gh)       cmd_gh; info "Gathered. Press 9 to sync, or gather more."; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            4|system)   cmd_system; info "Gathered. Press 9 to sync, or gather more."; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            5|packages) cmd_packages; info "Gathered. Press 9 to sync, or gather more."; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            6|desktop)  cmd_desktop; info "Gathered. Press 9 to sync, or gather more."; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            7|browser)  cmd_browser; info "Gathered. Press 9 to sync, or gather more."; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            8|status)   cmd_status; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            9|sync)     git_sync; echo ""; printf "${DIM}  Press Enter to continue...${RESET}"; read -r ;;
            q|Q|quit)   clear; exit 0 ;;
            *)          echo "  Invalid selection"; sleep 1 ;;
        esac
    done
}

# ── main dispatch ──
#
# Three verbs:
#   gather <cat...>    Gather categories into working tree (local, no git)
#   sync               Pull + commit + push everything pending (one round-trip)
#   run <cat...>       Gather + sync in one step
#
# Bare category names (git, packages, etc.) are backward-compatible aliases
# for "run <cat>" — they gather that category then sync. This preserves
# webdash compatibility.

case "${1:-}" in
    gather)
        shift
        [ $# -eq 0 ] && { err "Usage: backup.sh gather <category...>"; exit 1; }
        do_gather "$@"
        ;;
    sync)
        git_sync
        ;;
    run)
        shift
        [ $# -eq 0 ] && { err "Usage: backup.sh run <category...>"; exit 1; }
        do_gather "$@"
        git_sync
        ;;
    status)
        cmd_status
        ;;
    # backward compat: bare category names = gather + sync
    all)      do_gather all; git_sync ;;
    git)      cmd_git; git_sync ;;
    gh)       cmd_gh; git_sync ;;
    system)   cmd_system; git_sync ;;
    packages) cmd_packages; git_sync ;;
    desktop)  cmd_desktop; git_sync ;;
    browser)  cmd_browser; git_sync ;;
    scripts)  cmd_scripts; git_sync ;;
    *)        cmd_interactive ;;
esac
