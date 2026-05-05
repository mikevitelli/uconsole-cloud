#!/bin/bash
set -euo pipefail

# Read version from VERSION file at repo root
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="${REPO_ROOT}/VERSION"
if [ ! -f "$VERSION_FILE" ]; then
    echo "ERROR: VERSION file not found at ${VERSION_FILE}" >&2
    exit 1
fi
VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

PKG="uconsole-cloud"
BUILD_DIR="${REPO_ROOT}/dist/${PKG}_${VERSION}_arm64"
DEVICE_PKG="${UCONSOLE_DEVICE_PKG:-${REPO_ROOT}/device}"
CLI_SRC="${REPO_ROOT}/frontend/public/scripts/uconsole"

# Validate device source exists
if [ ! -d "$DEVICE_PKG" ]; then
    echo "ERROR: Device source not found at ${DEVICE_PKG}. Set UCONSOLE_DEVICE_PKG to override." >&2
    exit 1
fi
if [ ! -f "$CLI_SRC" ]; then
    echo "ERROR: CLI source not found at ${CLI_SRC}" >&2
    exit 1
fi

# Clean previous build
rm -rf "${REPO_ROOT}/dist/"
echo "Building ${PKG} ${VERSION}..."

# ── Create directory structure ──

mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/opt/uconsole"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/etc/uconsole/ssl"
mkdir -p "${BUILD_DIR}/etc/systemd/system"
mkdir -p "${BUILD_DIR}/etc/nginx/sites-available"
mkdir -p "${BUILD_DIR}/etc/avahi/services"
mkdir -p "${BUILD_DIR}/usr/share/bash-completion/completions"

# ── Copy from device repo pkg/ tree ──

# Each subdir mirrors the target /opt/uconsole/ layout
for dir in bin lib scripts webdash share; do
    if [ -d "${DEVICE_PKG}/${dir}" ]; then
        cp -r "${DEVICE_PKG}/${dir}" "${BUILD_DIR}/opt/uconsole/"
    fi
done

# Scrub gitignored artifacts that can leak into cp -r: Python bytecode
# caches and user-local TUI config (contains home coords / paths).
find "${BUILD_DIR}/opt/uconsole/" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}/opt/uconsole/" -name '.console-config.json' -delete 2>/dev/null || true
find "${BUILD_DIR}/opt/uconsole/" -name '*.pyc' -delete 2>/dev/null || true

# Scrub user-specific config snapshots that live in device/scripts/ as a
# private backup but must NOT ship in the public .deb. These are also
# .gitignored so they shouldn't be in canonical, but cp -r doesn't care
# about .gitignore — it copies whatever is on the working-tree disk.
rm -rf "${BUILD_DIR}/opt/uconsole/scripts/ssh"            # personal SSH keys
rm -rf "${BUILD_DIR}/opt/uconsole/scripts/system/etc"     # crontab.user, sudoers.d
rm -rf "${BUILD_DIR}/opt/uconsole/scripts/system/wifi"    # NetworkManager .nmconnection (PSKs)
rm -rf "${BUILD_DIR}/opt/uconsole/scripts/config"         # systemd-user, dconf, gh OAuth, etc.
rm -rf "${BUILD_DIR}/opt/uconsole/scripts/packages"       # apt/pip/etc machine snapshots
rm -f  "${BUILD_DIR}/opt/uconsole/scripts/.console-config.json"

# Scrub PRIVATE SCRIPTS (single source of truth: packaging/private_scripts.txt).
# Defense-in-depth layer 1: scrub at build time so an accidental re-introduction
# in canonical can't leak into the .deb. Layer 2 (post-build assertion below)
# is the real gate.
#
# Set BYPASS_PRIVATE_SCRUB=1 to skip this layer — useful only for testing the
# layer-2 assertion in isolation. Don't set it in production builds.
PRIVATE_SCRIPTS_FILE="${REPO_ROOT}/packaging/private_scripts.txt"
if [ ! -f "$PRIVATE_SCRIPTS_FILE" ]; then
    echo "ERROR: private_scripts.txt missing — cannot enforce private-script scrub" >&2
    exit 1
fi
if [ "${BYPASS_PRIVATE_SCRUB:-0}" != "1" ]; then
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(echo "$line" | tr -d '[:space:]')"
        [ -z "$line" ] && continue
        target="${BUILD_DIR}/opt/uconsole/scripts/${line}"
        if [ -e "$target" ]; then
            echo "  scrubbed private script: ${line}"
            rm -f "$target"
        fi
    done < "$PRIVATE_SCRIPTS_FILE"
fi

# ── Cloud-side CLI wrapper (overrides device repo's copy if present) ──

cp "${CLI_SRC}" "${BUILD_DIR}/opt/uconsole/bin/uconsole"
chmod +x "${BUILD_DIR}/opt/uconsole/bin/uconsole"

# Copy default config
mkdir -p "${BUILD_DIR}/opt/uconsole/share/defaults"
cp "${REPO_ROOT}/packaging/defaults/uconsole.conf.default" "${BUILD_DIR}/opt/uconsole/share/defaults/"

# Ship uconsole.conf as a dpkg conffile (postinst won't overwrite user edits)
cp "${REPO_ROOT}/packaging/defaults/uconsole.conf.default" "${BUILD_DIR}/etc/uconsole/uconsole.conf"

# Write VERSION file for uconsole --version
echo "${VERSION}" > "${BUILD_DIR}/opt/uconsole/VERSION"

# Make all scripts executable (skip symlinks)
find "${BUILD_DIR}/opt/uconsole/" -name "*.sh" ! -type l -exec chmod +x {} \;
find "${BUILD_DIR}/opt/uconsole/" -name "*.py" ! -type l -exec chmod +x {} \;
chmod +x "${BUILD_DIR}/opt/uconsole/bin/"* 2>/dev/null || true

# ── Symlinks into PATH ──

ln -s /opt/uconsole/bin/uconsole "${BUILD_DIR}/usr/bin/uconsole"
if [ -f "${BUILD_DIR}/opt/uconsole/bin/console" ]; then
    ln -s /opt/uconsole/bin/console "${BUILD_DIR}/usr/bin/console"
fi

# ── DEBIAN control files ──

sed "s/^Version:.*/Version: ${VERSION}/" "${REPO_ROOT}/packaging/control" > "${BUILD_DIR}/DEBIAN/control"
cp "${REPO_ROOT}/packaging/conffiles" "${BUILD_DIR}/DEBIAN/"
cp "${REPO_ROOT}/packaging/postinst" "${BUILD_DIR}/DEBIAN/"
cp "${REPO_ROOT}/packaging/prerm" "${BUILD_DIR}/DEBIAN/"
cp "${REPO_ROOT}/packaging/postrm" "${BUILD_DIR}/DEBIAN/"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst" "${BUILD_DIR}/DEBIAN/prerm" "${BUILD_DIR}/DEBIAN/postrm"

# ── Systemd units (installed but NOT enabled — setup wizard handles that) ──

# Copy systemd units except battery fix (user opt-in via TUI)
for unit in "${REPO_ROOT}/packaging/systemd/"*; do
    [ "$(basename "$unit")" = "axp-voff-shutdown.service" ] && continue
    cp "$unit" "${BUILD_DIR}/etc/systemd/system/"
done

# ── Battery boot fix templates (user applies via TUI Power Config) ──

mkdir -p "${BUILD_DIR}/opt/uconsole/share/battery-fix"
cp "${REPO_ROOT}/packaging/udev/99-uconsole-battery.rules" "${BUILD_DIR}/opt/uconsole/share/battery-fix/"
cp "${REPO_ROOT}/packaging/initramfs/axp-voff-hook" "${BUILD_DIR}/opt/uconsole/share/battery-fix/"
cp "${REPO_ROOT}/packaging/initramfs/axp-voff-premount" "${BUILD_DIR}/opt/uconsole/share/battery-fix/"
cp "${REPO_ROOT}/packaging/systemd/axp-voff-shutdown.service" "${BUILD_DIR}/opt/uconsole/share/battery-fix/"
chmod +x "${BUILD_DIR}/opt/uconsole/share/battery-fix/axp-voff-hook"
chmod +x "${BUILD_DIR}/opt/uconsole/share/battery-fix/axp-voff-premount"

# ── Nginx config (installed but NOT enabled) ──

cp "${REPO_ROOT}/packaging/nginx/uconsole-webdash" "${BUILD_DIR}/etc/nginx/sites-available/"

# ── Avahi mDNS service ──

cp "${REPO_ROOT}/packaging/avahi/uconsole-webdash.service" "${BUILD_DIR}/etc/avahi/services/"

# ── Bash completion ──

cp "${BUILD_DIR}/opt/uconsole/share/defaults/uconsole-completion.bash" "${BUILD_DIR}/usr/share/bash-completion/completions/uconsole"

# ── Build the .deb ──

DEB_PATH="${REPO_ROOT}/dist/${PKG}_${VERSION}_arm64.deb"
dpkg-deb --root-owner-group --build "${BUILD_DIR}" "${DEB_PATH}"

# ── Post-build assertion: no PRIVATE SCRIPTS in shipped .deb ──
# Background: 0.2.1 (built 2026-04-15) shipped backup.sh because the script
# was in canonical at build time. This check catches that class of leak by
# inspecting the actual .deb payload — not just canonical state.
echo ""
echo "── Asserting private-script absence in built .deb ──"
DEB_CONTENTS="$(dpkg-deb -c "${DEB_PATH}")"
LEAKED=()
while IFS= read -r line; do
    line="${line%%#*}"
    line="$(echo "$line" | tr -d '[:space:]')"
    [ -z "$line" ] && continue
    if echo "${DEB_CONTENTS}" | grep -qE "[[:space:]]\./opt/uconsole/scripts/${line}\$"; then
        LEAKED+=("${line}")
    fi
done < "$PRIVATE_SCRIPTS_FILE"

if [ ${#LEAKED[@]} -gt 0 ]; then
    echo "" >&2
    echo "FATAL: built .deb contains private scripts that must NOT ship:" >&2
    for s in "${LEAKED[@]}"; do echo "  - opt/uconsole/scripts/${s}" >&2; done
    echo "" >&2
    echo "These paths are listed in packaging/private_scripts.txt." >&2
    echo "Either remove them from device/scripts/ (preferred) or remove" >&2
    echo "them from packaging/private_scripts.txt (only if they're now" >&2
    echo "intentionally public)." >&2
    rm -f "${DEB_PATH}"
    exit 1
fi
echo "  ok — no private scripts shipped"

echo ""
echo "Built: dist/${PKG}_${VERSION}_arm64.deb"
SIZE=$(du -h "${DEB_PATH}" | cut -f1)
echo "Size:  ${SIZE}"
echo ""
echo "To install on device:"
echo "  scp dist/${PKG}_${VERSION}_arm64.deb uconsole:/tmp/"
echo "  ssh uconsole \"sudo dpkg -i /tmp/${PKG}_${VERSION}_arm64.deb && sudo apt-get install -f\""
