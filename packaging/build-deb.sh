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

# ── Copy from device repo pkg/ tree ──

# Each subdir mirrors the target /opt/uconsole/ layout
for dir in bin lib scripts webdash share; do
    if [ -d "${DEVICE_PKG}/${dir}" ]; then
        cp -r "${DEVICE_PKG}/${dir}" "${BUILD_DIR}/opt/uconsole/"
    fi
done

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

# Make all scripts executable
find "${BUILD_DIR}/opt/uconsole/" -name "*.sh" -exec chmod +x {} \;
find "${BUILD_DIR}/opt/uconsole/" -name "*.py" -exec chmod +x {} \;
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
