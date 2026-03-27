#!/bin/bash
set -euo pipefail

VERSION="0.1.0"
PKG="uconsole-cloud-tools"
BUILD_DIR="build/${PKG}_${VERSION}_arm64"
SCRIPTS_SRC="${HOME}/uconsole/scripts"
CLI_SRC="frontend/public/scripts/uconsole"

# Validate sources exist
if [ ! -d "$SCRIPTS_SRC" ]; then
    echo "ERROR: Scripts source not found at ${SCRIPTS_SRC}" >&2
    exit 1
fi
if [ ! -f "$CLI_SRC" ]; then
    echo "ERROR: CLI source not found at ${CLI_SRC}" >&2
    exit 1
fi

# Clean previous build
rm -rf build/
echo "Building ${PKG} ${VERSION}..."

# Create directory structure
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/opt/uconsole/scripts"
mkdir -p "${BUILD_DIR}/opt/uconsole/www"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/etc/systemd/system"
mkdir -p "${BUILD_DIR}/etc/nginx/sites-available"
mkdir -p "${BUILD_DIR}/etc/avahi/services"
mkdir -p "${BUILD_DIR}/var/lib/uconsole"

# Copy scripts from backup repo
cp "${SCRIPTS_SRC}"/*.sh "${BUILD_DIR}/opt/uconsole/scripts/"
cp "${SCRIPTS_SRC}"/*.py "${BUILD_DIR}/opt/uconsole/scripts/"
chmod +x "${BUILD_DIR}/opt/uconsole/scripts/"*.sh "${BUILD_DIR}/opt/uconsole/scripts/"*.py

# Copy favicon
if [ -f "${SCRIPTS_SRC}/favicon.png" ]; then
    cp "${SCRIPTS_SRC}/favicon.png" "${BUILD_DIR}/opt/uconsole/www/"
fi

# Copy CLI and make executable
cp "${CLI_SRC}" "${BUILD_DIR}/opt/uconsole/scripts/uconsole"
chmod +x "${BUILD_DIR}/opt/uconsole/scripts/uconsole"

# Symlink CLI into PATH
ln -s /opt/uconsole/scripts/uconsole "${BUILD_DIR}/usr/bin/uconsole"

# DEBIAN control files
cp packaging/control "${BUILD_DIR}/DEBIAN/"
cp packaging/conffiles "${BUILD_DIR}/DEBIAN/"
cp packaging/postinst "${BUILD_DIR}/DEBIAN/"
cp packaging/prerm "${BUILD_DIR}/DEBIAN/"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst" "${BUILD_DIR}/DEBIAN/prerm"

# Systemd units
cp packaging/systemd/* "${BUILD_DIR}/etc/systemd/system/"

# nginx config
cp packaging/nginx/uconsole-webdash "${BUILD_DIR}/etc/nginx/sites-available/"

# Avahi mDNS service
cp packaging/avahi/uconsole-webdash.service "${BUILD_DIR}/etc/avahi/services/"

# Set ownership (all root)
# Note: dpkg-deb will warn if not run as root, but the package still works.
# On install, files are owned by root automatically.

# Build the .deb
dpkg-deb --root-owner-group --build "${BUILD_DIR}" "build/${PKG}_${VERSION}_arm64.deb"

echo ""
echo "Built: build/${PKG}_${VERSION}_arm64.deb"
SIZE=$(du -h "build/${PKG}_${VERSION}_arm64.deb" | cut -f1)
echo "Size:  ${SIZE}"
echo ""
echo "To install on device:"
echo "  scp build/${PKG}_${VERSION}_arm64.deb uconsole:/tmp/"
echo "  ssh uconsole \"sudo dpkg -i /tmp/${PKG}_${VERSION}_arm64.deb && sudo apt-get install -f\""
