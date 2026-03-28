#!/bin/bash
set -euo pipefail

# Generate APT repository metadata from a .deb file.
# Usage: bash packaging/scripts/generate-repo.sh dist/uconsole-cloud_X.Y.Z_arm64.deb

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APT_DIR="${REPO_ROOT}/frontend/public/apt"
KEY_EMAIL="apt@uconsole.cloud"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <path-to-deb-file>" >&2
    exit 1
fi

DEB_FILE="$1"
if [ ! -f "$DEB_FILE" ]; then
    echo "ERROR: .deb file not found: ${DEB_FILE}" >&2
    exit 1
fi

DEB_BASENAME="$(basename "$DEB_FILE")"
echo "Publishing ${DEB_BASENAME} to APT repository..."

# Create directory structure
POOL_DIR="${APT_DIR}/pool/main/u/uconsole-cloud"
DIST_DIR="${APT_DIR}/dists/stable"
BINARY_DIR="${DIST_DIR}/main/binary-arm64"

mkdir -p "${POOL_DIR}"
mkdir -p "${BINARY_DIR}"

# Copy .deb to pool
cp "$DEB_FILE" "${POOL_DIR}/"

# Generate Packages index
echo "Generating Packages index..."
cd "${APT_DIR}"

# Use dpkg-scanpackages if available, otherwise generate manually
if command -v dpkg-scanpackages &>/dev/null; then
    dpkg-scanpackages pool/ /dev/null > "${BINARY_DIR}/Packages"
else
    # Manual Packages generation (works on macOS without dpkg-scanpackages)
    PKG_INFO=$(dpkg-deb --info "${POOL_DIR}/${DEB_BASENAME}")
    PKG_SIZE=$(wc -c < "${POOL_DIR}/${DEB_BASENAME}" | tr -d ' ')
    PKG_MD5=$(md5sum "${POOL_DIR}/${DEB_BASENAME}" 2>/dev/null || md5 -q "${POOL_DIR}/${DEB_BASENAME}")
    PKG_SHA256=$(shasum -a 256 "${POOL_DIR}/${DEB_BASENAME}" | cut -d' ' -f1)

    # Extract control fields
    CONTROL=$(dpkg-deb --field "${POOL_DIR}/${DEB_BASENAME}")

    cat > "${BINARY_DIR}/Packages" <<PKGEOF
${CONTROL}
Filename: pool/main/u/uconsole-cloud/${DEB_BASENAME}
Size: ${PKG_SIZE}
SHA256: ${PKG_SHA256}
PKGEOF
fi

# Generate compressed Packages
gzip -9 -c "${BINARY_DIR}/Packages" > "${BINARY_DIR}/Packages.gz"

# Generate Release file
echo "Generating Release file..."
RELEASE_DATE=$(date -u -R 2>/dev/null || date -u "+%a, %d %b %Y %H:%M:%S +0000")

# Calculate checksums for the Packages files
PKG_SIZE=$(wc -c < "${BINARY_DIR}/Packages" | tr -d ' ')
PKG_GZ_SIZE=$(wc -c < "${BINARY_DIR}/Packages.gz" | tr -d ' ')
PKG_SHA256=$(shasum -a 256 "${BINARY_DIR}/Packages" | cut -d' ' -f1)
PKG_GZ_SHA256=$(shasum -a 256 "${BINARY_DIR}/Packages.gz" | cut -d' ' -f1)

cat > "${DIST_DIR}/Release" <<EOF
Origin: uconsole
Label: uconsole
Suite: stable
Codename: stable
Architectures: arm64
Components: main
Date: ${RELEASE_DATE}
SHA256:
 ${PKG_SHA256} ${PKG_SIZE} main/binary-arm64/Packages
 ${PKG_GZ_SHA256} ${PKG_GZ_SIZE} main/binary-arm64/Packages.gz
EOF

# Sign Release → InRelease (if GPG key is available)
if gpg --list-keys "${KEY_EMAIL}" &>/dev/null; then
    echo "Signing Release with GPG key..."
    gpg --default-key "${KEY_EMAIL}" --armor --detach-sign \
        --output "${DIST_DIR}/Release.gpg" "${DIST_DIR}/Release"
    gpg --default-key "${KEY_EMAIL}" --armor --clearsign \
        --output "${DIST_DIR}/InRelease" "${DIST_DIR}/Release"
    echo "Repository signed."
else
    echo "WARNING: GPG key not found for ${KEY_EMAIL}"
    echo "  Run: bash packaging/scripts/generate-gpg-key.sh"
    echo "  Repository will be unsigned (users need --allow-unauthenticated)."
fi

cd "${REPO_ROOT}"

echo ""
echo "APT repository updated at: frontend/public/apt/"
echo "  Pool: pool/main/u/uconsole-cloud/${DEB_BASENAME}"
echo "  Index: dists/stable/main/binary-arm64/Packages"
echo ""
echo "Deploy to Vercel to make the repo live."
