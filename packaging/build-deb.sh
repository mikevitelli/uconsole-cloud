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
SCRIPTS_SRC="${HOME}/uconsole/scripts"
CLI_SRC="${REPO_ROOT}/frontend/public/scripts/uconsole"

# Validate sources exist
if [ ! -d "$SCRIPTS_SRC" ]; then
    echo "ERROR: Scripts source not found at ${SCRIPTS_SRC}" >&2
    echo "  This is the device backup repo. Clone it or set SCRIPTS_SRC." >&2
    exit 1
fi
if [ ! -f "$CLI_SRC" ]; then
    echo "ERROR: CLI source not found at ${CLI_SRC}" >&2
    exit 1
fi

# Clean previous build
rm -rf "${REPO_ROOT}/dist/"
echo "Building ${PKG} ${VERSION}..."

# ── Create directory structure matching target filesystem ──

# DEBIAN control
mkdir -p "${BUILD_DIR}/DEBIAN"

# Binaries and launchers
mkdir -p "${BUILD_DIR}/opt/uconsole/bin"

# Shared libraries
mkdir -p "${BUILD_DIR}/opt/uconsole/lib"

# Scripts organized by category
mkdir -p "${BUILD_DIR}/opt/uconsole/scripts/system"
mkdir -p "${BUILD_DIR}/opt/uconsole/scripts/power"
mkdir -p "${BUILD_DIR}/opt/uconsole/scripts/network"
mkdir -p "${BUILD_DIR}/opt/uconsole/scripts/radio"
mkdir -p "${BUILD_DIR}/opt/uconsole/scripts/util"

# Webdash
mkdir -p "${BUILD_DIR}/opt/uconsole/webdash"

# Shared data
mkdir -p "${BUILD_DIR}/opt/uconsole/share/themes"
mkdir -p "${BUILD_DIR}/opt/uconsole/share/battery-data"
mkdir -p "${BUILD_DIR}/opt/uconsole/share/esp32"

# System config
mkdir -p "${BUILD_DIR}/etc/uconsole/ssl"

# User config template (actual user config created at runtime)
mkdir -p "${BUILD_DIR}/opt/uconsole/share/defaults"

# Symlinks directory
mkdir -p "${BUILD_DIR}/usr/bin"

# Systemd units
mkdir -p "${BUILD_DIR}/etc/systemd/system"

# Nginx
mkdir -p "${BUILD_DIR}/etc/nginx/sites-available"

# Avahi
mkdir -p "${BUILD_DIR}/etc/avahi/services"

# Runtime data
mkdir -p "${BUILD_DIR}/var/lib/uconsole"

# ── Copy scripts into organized subdirs ──

# Categorize scripts by naming convention and known mapping
for script in "${SCRIPTS_SRC}"/*.sh; do
    [ -f "$script" ] || continue
    name="$(basename "$script")"
    case "$name" in
        # Power scripts — SAFETY-CRITICAL, copied without modification
        battery*.sh|charge*.sh|power*.sh)
            cp "$script" "${BUILD_DIR}/opt/uconsole/scripts/power/" ;;
        # Network scripts
        wifi*.sh|hotspot*.sh|network*.sh|tailscale*.sh)
            cp "$script" "${BUILD_DIR}/opt/uconsole/scripts/network/" ;;
        # Radio scripts (AIO board)
        sdr*.sh|lora*.sh|gps*.sh|rtc*.sh|radio*.sh)
            cp "$script" "${BUILD_DIR}/opt/uconsole/scripts/radio/" ;;
        # System scripts
        backup*.sh|restore*.sh|push-status.sh|update*.sh|doctor*.sh|setup*.sh|hardware*.sh)
            cp "$script" "${BUILD_DIR}/opt/uconsole/scripts/system/" ;;
        # Everything else → util
        *)
            cp "$script" "${BUILD_DIR}/opt/uconsole/scripts/util/" ;;
    esac
done

# Copy Python scripts (webdash, TUI, libs)
for pyfile in "${SCRIPTS_SRC}"/*.py; do
    [ -f "$pyfile" ] || continue
    name="$(basename "$pyfile")"
    case "$name" in
        webdash.py|app.py)
            cp "$pyfile" "${BUILD_DIR}/opt/uconsole/webdash/" ;;
        console.py)
            cp "$pyfile" "${BUILD_DIR}/opt/uconsole/bin/" ;;
        tui_lib.py|ascii_logos.py)
            cp "$pyfile" "${BUILD_DIR}/opt/uconsole/lib/" ;;
        *)
            cp "$pyfile" "${BUILD_DIR}/opt/uconsole/lib/" ;;
    esac
done

# Copy lib.sh if it exists
if [ -f "${SCRIPTS_SRC}/lib.sh" ]; then
    cp "${SCRIPTS_SRC}/lib.sh" "${BUILD_DIR}/opt/uconsole/lib/"
fi

# Copy webdash templates and static if they exist
if [ -d "${SCRIPTS_SRC}/templates" ]; then
    cp -r "${SCRIPTS_SRC}/templates" "${BUILD_DIR}/opt/uconsole/webdash/"
fi
if [ -d "${SCRIPTS_SRC}/static" ]; then
    cp -r "${SCRIPTS_SRC}/static" "${BUILD_DIR}/opt/uconsole/webdash/"
fi
if [ -d "${SCRIPTS_SRC}/docs" ]; then
    cp -r "${SCRIPTS_SRC}/docs" "${BUILD_DIR}/opt/uconsole/webdash/"
fi

# Copy themes and data
if [ -d "${SCRIPTS_SRC}/themes" ]; then
    cp -r "${SCRIPTS_SRC}/themes/"* "${BUILD_DIR}/opt/uconsole/share/themes/" 2>/dev/null || true
fi
if [ -d "${SCRIPTS_SRC}/battery-data" ]; then
    cp -r "${SCRIPTS_SRC}/battery-data/"* "${BUILD_DIR}/opt/uconsole/share/battery-data/" 2>/dev/null || true
fi
if [ -d "${SCRIPTS_SRC}/esp32" ]; then
    cp -r "${SCRIPTS_SRC}/esp32/"* "${BUILD_DIR}/opt/uconsole/share/esp32/" 2>/dev/null || true
fi

# Copy favicon for webdash
if [ -f "${SCRIPTS_SRC}/favicon.png" ]; then
    cp "${SCRIPTS_SRC}/favicon.png" "${BUILD_DIR}/opt/uconsole/webdash/"
fi

# Copy CLI and make executable
cp "${CLI_SRC}" "${BUILD_DIR}/opt/uconsole/bin/uconsole"
chmod +x "${BUILD_DIR}/opt/uconsole/bin/uconsole"

# Copy default config
cp "${REPO_ROOT}/packaging/defaults/uconsole.conf.default" "${BUILD_DIR}/opt/uconsole/share/defaults/"

# Make all scripts executable
find "${BUILD_DIR}/opt/uconsole/" -name "*.sh" -exec chmod +x {} \;
find "${BUILD_DIR}/opt/uconsole/" -name "*.py" -exec chmod +x {} \;
chmod +x "${BUILD_DIR}/opt/uconsole/bin/"* 2>/dev/null || true

# ── Symlinks into PATH ──
ln -s /opt/uconsole/bin/uconsole "${BUILD_DIR}/usr/bin/uconsole"
# Console TUI launcher — only if console.py was copied
if [ -f "${BUILD_DIR}/opt/uconsole/bin/console.py" ]; then
    ln -s /opt/uconsole/bin/console.py "${BUILD_DIR}/usr/bin/console"
fi

# ── DEBIAN control files ──
sed "s/^Version:.*/Version: ${VERSION}/" "${REPO_ROOT}/packaging/control" > "${BUILD_DIR}/DEBIAN/control"
cp "${REPO_ROOT}/packaging/conffiles" "${BUILD_DIR}/DEBIAN/"
cp "${REPO_ROOT}/packaging/postinst" "${BUILD_DIR}/DEBIAN/"
cp "${REPO_ROOT}/packaging/prerm" "${BUILD_DIR}/DEBIAN/"
cp "${REPO_ROOT}/packaging/postrm" "${BUILD_DIR}/DEBIAN/"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst" "${BUILD_DIR}/DEBIAN/prerm" "${BUILD_DIR}/DEBIAN/postrm"

# ── Systemd units (installed but NOT enabled — setup wizard handles that) ──
cp "${REPO_ROOT}/packaging/systemd/"* "${BUILD_DIR}/etc/systemd/system/"

# ── Nginx config (installed but NOT enabled) ──
cp "${REPO_ROOT}/packaging/nginx/uconsole-webdash" "${BUILD_DIR}/etc/nginx/sites-available/"

# ── Avahi mDNS service ──
cp "${REPO_ROOT}/packaging/avahi/uconsole-webdash.service" "${BUILD_DIR}/etc/avahi/services/"

# ── Build the .deb ──
dpkg-deb --root-owner-group --build "${BUILD_DIR}" "${REPO_ROOT}/dist/${PKG}_${VERSION}_arm64.deb"

echo ""
echo "Built: dist/${PKG}_${VERSION}_arm64.deb"
SIZE=$(du -h "${REPO_ROOT}/dist/${PKG}_${VERSION}_arm64.deb" | cut -f1)
echo "Size:  ${SIZE}"
echo ""
echo "To install on device:"
echo "  scp dist/${PKG}_${VERSION}_arm64.deb uconsole:/tmp/"
echo "  ssh uconsole \"sudo dpkg -i /tmp/${PKG}_${VERSION}_arm64.deb && sudo apt-get install -f\""
