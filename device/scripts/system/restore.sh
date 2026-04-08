#!/bin/bash
# uConsole Restore Script
# Clone this repo, then run: ./restore.sh
#
# This script restores configs from the monorepo backup to a fresh uConsole.
# It uses symlinks where possible so changes are tracked by git.
# Detects Bullseye vs Bookworm and adjusts behavior accordingly.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="$HOME"
AUTO=false
if [ "$1" = "--yes" ] || [ "$1" = "-y" ]; then
    AUTO=true
fi

# --- Detect OS release ---
DEBIAN_CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"

echo "=== uConsole Restore ==="
echo "Repo:  $REPO_DIR"
echo "Home:  $HOME_DIR"
echo "OS:    Debian $DEBIAN_CODENAME"
if $AUTO; then echo "Mode:  automatic (--yes)"; fi
echo ""

confirm() {
    if $AUTO; then return 0; fi
    read -p "$1 [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# --- Shell configs ---
echo "[1/9] Linking shell configs..."
for f in .bashrc .profile .xsessionrc .gitconfig .dmrc .gtkrc-2.0 .gtk-bookmarks; do
    if [ -f "$REPO_DIR/shell/$f" ]; then
        ln -sfn "$REPO_DIR/shell/$f" "$HOME_DIR/$f"
        echo "  -> ~/$f"
    fi
done

# --- Dotfiles ---
echo "[2/9] Linking dotfile configs..."
declare -A dotfile_map=(
    ["weechat"]=".weechat"
    ["minetest"]=".minetest"
    ["dosbox"]=".dosbox"
    ["opentyrian"]=".opentyrian"
    ["mame"]=".mame"
    ["vscode"]=".vscode"
    ["vnc"]=".vnc"
    ["icons"]=".icons"
    ["vba"]=".vba"
)
for src in "${!dotfile_map[@]}"; do
    dest="${dotfile_map[$src]}"
    if [ -d "$REPO_DIR/dotfiles/$src" ]; then
        ln -sfn "$REPO_DIR/dotfiles/$src" "$HOME_DIR/$dest"
        echo "  -> ~/$dest"
    fi
done

# --- Config dirs ---
echo "[3/9] Linking ~/.config app configs..."
mkdir -p "$HOME_DIR/.config"

# Dirs that are runtime/state — apps must own these, never symlink
SKIP_DIRS="chromium dconf evolution pulse systemd-user"

for d in "$REPO_DIR"/config/*/; do
    name="$(basename "$d")"

    # Skip runtime dirs
    if echo "$SKIP_DIRS" | grep -qw "$name"; then
        echo "  -- ~/.config/$name (skipped — runtime dir)"
        continue
    fi

    target="$HOME_DIR/.config/$name"

    if [ -d "$target" ] && [ ! -L "$target" ]; then
        # Dir already exists (created by the OS/app) — link individual files
        for item in "$d"*; do
            item_name="$(basename "$item")"
            [ "$item_name" = "$name" ] && continue  # skip doubly-nested dirs
            dest_item="$target/$item_name"
            if [ ! -e "$dest_item" ]; then
                ln -sfn "$item" "$dest_item"
                echo "  -> ~/.config/$name/$item_name"
            else
                echo "  == ~/.config/$name/$item_name (exists, keeping)"
            fi
        done
    else
        # No existing dir — symlink the whole thing
        ln -sfn "$d" "$target"
        echo "  -> ~/.config/$name"
    fi
done

# Link standalone config files
for f in "$REPO_DIR"/config/*; do
    [ -f "$f" ] || continue
    name="$(basename "$f")"
    [ "$name" = "README.md" ] && continue
    ln -sfn "$f" "$HOME_DIR/.config/$name"
    echo "  -> ~/.config/$name"
done

# --- Scripts ---
echo "[4/9] Ensuring scripts are executable..."
chmod +x "$REPO_DIR/scripts/"*.sh "$REPO_DIR/scripts/"*.py 2>/dev/null
echo "  -> scripts/*.sh and scripts/*.py marked executable"

# --- SSH ---
echo "[5/9] Setting up SSH..."
mkdir -p "$HOME_DIR/.ssh" && chmod 700 "$HOME_DIR/.ssh"
for pubkey in "$REPO_DIR"/ssh/*.pub; do
    [ -f "$pubkey" ] || continue
    cp "$pubkey" "$HOME_DIR/.ssh/"
    echo "  -> ~/.ssh/$(basename "$pubkey")"
done
if [ -f "$REPO_DIR/ssh/config" ]; then
    cp "$REPO_DIR/ssh/config" "$HOME_DIR/.ssh/config"
    echo "  -> ~/.ssh/config"
fi
echo "  (you'll need to restore private keys separately)"

# --- System configs (requires sudo) ---
echo "[6/9] Restoring system configs (requires sudo)..."
if confirm "  Apply system configs (boot, udev, apt sources)?"; then
    # -- Boot config --
    if [ "$DEBIAN_CODENAME" = "bookworm" ]; then
        echo "  Bookworm detected — merging boot overlays (not overwriting config.txt)"
        # Lines to add to [pi4] section if not already present
        BOOT_EXTRAS=(
            "dtparam=i2c_arm=on"
            "dtoverlay=i2c-rtc,pcf85063a"
            "dtoverlay=spi1-1cs"
            "gpio=10=ip,np"
            "dtparam=ant1=off"
        )
        for line in "${BOOT_EXTRAS[@]}"; do
            if ! grep -qF "$line" /boot/config.txt; then
                # Insert into the [pi4] section, after the last dtoverlay/dtparam in that block
                sudo sed -i "/^\[pi4\]/,/^\[/{/^enable_uart=1/a\\$line
}" /boot/config.txt
                echo "  + $line"
            else
                echo "  = $line (already present)"
            fi
        done
        echo "  -> boot overlays merged"
        echo "  (skipping cmdline.txt — Bookworm has its own)"
    else
        sudo cp "$REPO_DIR/system/boot/config.txt" /boot/config.txt
        sudo cp "$REPO_DIR/system/boot/cmdline.txt" /boot/cmdline.txt
        echo "  -> /boot/config.txt, /boot/cmdline.txt"
    fi

    # -- /etc/hosts --
    if [ -f "$REPO_DIR/system/etc/hosts" ]; then
        sudo cp "$REPO_DIR/system/etc/hosts" /etc/hosts
        echo "  -> /etc/hosts"
    fi

    # -- locale --
    if [ -f "$REPO_DIR/system/etc/locale" ]; then
        sudo cp "$REPO_DIR/system/etc/locale" /etc/default/locale
        echo "  -> locale: $(grep '^LANG=' "$REPO_DIR/system/etc/locale" | cut -d= -f2)"
    fi

    # -- timezone --
    if [ -f "$REPO_DIR/system/etc/timezone" ]; then
        local tz
        tz=$(cat "$REPO_DIR/system/etc/timezone")
        sudo timedatectl set-timezone "$tz" 2>/dev/null
        echo "  -> timezone: $tz"
    fi

    # -- keyboard layout --
    if [ -f "$REPO_DIR/system/etc/keyboard" ]; then
        sudo cp "$REPO_DIR/system/etc/keyboard" /etc/default/keyboard
        echo "  -> keyboard layout"
    fi

    # -- udev rules --
    sudo cp "$REPO_DIR/system/udev/"*.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    echo "  -> udev rules"

    # -- WiFi connections --
    if [ -d "$REPO_DIR/system/wifi" ] && [ "$(ls -A "$REPO_DIR/system/wifi" 2>/dev/null)" ]; then
        local wifi_count=0
        for conn in "$REPO_DIR/system/wifi"/*.nmconnection; do
            [ -f "$conn" ] || continue
            sudo cp "$conn" /etc/NetworkManager/system-connections/
            sudo chmod 600 "/etc/NetworkManager/system-connections/$(basename "$conn")"
            wifi_count=$((wifi_count + 1))
        done
        sudo systemctl reload NetworkManager 2>/dev/null
        echo "  -> $wifi_count WiFi connection(s) restored"
    fi

    # -- ALSA mixer state --
    if [ -f "$REPO_DIR/system/alsa/asound.state" ]; then
        sudo cp "$REPO_DIR/system/alsa/asound.state" /var/lib/alsa/asound.state
        sudo alsactl restore 2>/dev/null
        echo "  -> ALSA mixer state"
    fi

    # -- APT sources + GPG keys --
    if [ "$DEBIAN_CODENAME" = "bookworm" ]; then
        echo "  Bookworm detected — keeping system apt sources, adding extras only"

        # Install GPG keys if missing
        if [ ! -f /usr/share/keyrings/githubcli-archive-keyring.gpg ]; then
            echo "  Installing GitHub CLI GPG key..."
            curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
                | sudo tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null
        fi
        if [ ! -f /usr/share/keyrings/docker-archive-keyring.gpg ]; then
            echo "  Installing Docker GPG key..."
            curl -fsSL https://download.docker.com/linux/debian/gpg \
                | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        fi

        # Write correct Bookworm repo files (not from the repo — those may be stale)
        echo "deb [arch=arm64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" \
            | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        echo "  + docker.list (bookworm)"
        echo "deb [arch=arm64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
            | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
        echo "  + github-cli.list"
        echo "  (skipping sources.list, clockworkpi.list, raspi.list — Bookworm has its own)"
    else
        sudo cp "$REPO_DIR/system/apt/sources.list" /etc/apt/sources.list
        sudo cp "$REPO_DIR/system/apt/sources.list.d/"*.list /etc/apt/sources.list.d/ 2>/dev/null
        echo "  -> apt sources"
    fi
fi

# --- Display fix ---
echo "[7/9] Fixing display rotation..."
XRANDR_FILE="/etc/X11/Xsession.d/100custom_xrandr"
if [ -f "$XRANDR_FILE" ] && grep -q "transform 270" "$XRANDR_FILE" 2>/dev/null; then
    echo 'xrandr --output DSI-1 --rotate right' | sudo tee "$XRANDR_FILE" > /dev/null
    echo "  -> fixed xrandr rotation (transform 270 → --rotate right)"
else
    echo "  -> xrandr already correct or not present"
fi

# --- Packages ---
echo "[8/9] Package reinstall..."
if confirm "  Reinstall packages from manifest?"; then
    echo "  Updating apt..."
    sudo apt update
    echo "  Installing apt packages (this may take a while)..."
    if [ "$DEBIAN_CODENAME" = "bookworm" ]; then
        # Some Bullseye packages may be missing/renamed — install what's available
        FAILED_PKGS=""
        while read -r pkg; do
            [ -z "$pkg" ] && continue
            if ! sudo apt install -y "$pkg" 2>/dev/null; then
                FAILED_PKGS="$FAILED_PKGS $pkg"
            fi
        done < "$REPO_DIR/packages/apt-manual.txt"
        if [ -n "$FAILED_PKGS" ]; then
            echo ""
            echo "  WARNING: These packages failed to install (may be renamed/removed in Bookworm):"
            echo " $FAILED_PKGS" | tr ' ' '\n' | sed 's/^/    /'
            echo ""
        fi
    else
        xargs sudo apt install -y < "$REPO_DIR/packages/apt-manual.txt"
    fi
    if [ -f "$REPO_DIR/packages/flatpak.txt" ]; then
        echo "  Installing flatpaks..."
        while read -r app; do
            [ -n "$app" ] && flatpak install -y flathub "$app" 2>/dev/null || true
        done < "$REPO_DIR/packages/flatpak.txt"
    fi
    if [ -f "$REPO_DIR/packages/snap.txt" ]; then
        echo "  Installing snaps..."
        while read -r pkg; do
            [ -n "$pkg" ] && snap install "$pkg" 2>/dev/null || true
        done < "$REPO_DIR/packages/snap.txt"
    fi
fi

# --- Rust/Cargo ---
if [ ! -f "$HOME_DIR/.cargo/env" ]; then
    echo "  Installing Rust (required by shell configs)..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    echo "  -> Rust installed"
else
    echo "  -> Rust already installed"
fi

# --- Systemd timers ---
echo "[9/9] Enabling systemd timers..."
if confirm "  Enable automatic backup/update timers?"; then
    mkdir -p "$HOME_DIR/.config/systemd/user"
    for f in "$REPO_DIR/config/systemd-user/"*.service "$REPO_DIR/config/systemd-user/"*.timer; do
        [ -f "$f" ] || continue
        cp "$f" "$HOME_DIR/.config/systemd/user/"
    done
    sudo systemctl daemon-reload
    sudo systemctl enable --now uconsole-backup.timer 2>/dev/null && echo "  -> backup timer enabled (daily 3am)"
    sudo systemctl enable --now uconsole-update.timer 2>/dev/null && echo "  -> update timer enabled (weekly Sunday 4am)"
fi

# --- Cloud connection ---
echo "[10/10] uconsole.cloud setup..."
if command -v uconsole &>/dev/null; then
    if [ -f /etc/uconsole/status.env ] || [ -f "$HOME_DIR/.config/uconsole/status.env" ]; then
        echo "  -> Already configured (status.env exists)"
    else
        echo "  -> uconsole CLI found but not linked to cloud"
        echo "  -> Run 'uconsole setup' to connect to uconsole.cloud"
    fi
else
    echo "  -> uconsole CLI not installed"
    echo "  -> Run: curl -fsSL https://uconsole.cloud/install | bash"
    echo "  -> Then: uconsole setup"
fi

echo ""
echo "=== Restore complete ==="
echo ""
echo "Manual steps remaining:"
echo "  1. Copy RetroPie ROMs to ~/RetroPie/roms/"
echo "  2. Restore RetroArch configs (not backed up)"
echo "  3. Reboot to apply boot config and udev rules"
if ! command -v uconsole &>/dev/null || [ ! -f "$HOME_DIR/.config/uconsole/status.env" ]; then
    echo "  4. Connect to uconsole.cloud (see step 10 above)"
fi
echo ""
echo "Tip: run './restore.sh --yes' to skip all prompts next time"
