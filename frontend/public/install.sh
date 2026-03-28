#!/bin/bash
# uconsole-cloud installer
# Usage: curl -s https://uconsole.cloud/install | sudo bash
#
# Adds the uconsole APT repository and installs uconsole-cloud.
# Safe to run multiple times (idempotent).
set -euo pipefail

BASE_URL="${UCONSOLE_URL:-https://uconsole.cloud}"
APT_LIST="/etc/apt/sources.list.d/uconsole.list"
GPG_KEY="/etc/apt/keyrings/uconsole.gpg"

# Must run as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)." >&2
    echo "  curl -s ${BASE_URL}/install | sudo bash" >&2
    exit 1
fi

echo "Installing uconsole-cloud from ${BASE_URL}..."
echo ""

# Create keyrings directory if needed
mkdir -p /etc/apt/keyrings

# Add GPG key (idempotent — overwrites if exists)
echo "Adding GPG key..."
curl -fsSL "${BASE_URL}/apt/uconsole.gpg" | gpg --dearmor -o "${GPG_KEY}" 2>/dev/null || \
    curl -fsSL "${BASE_URL}/apt/uconsole.gpg" -o "${GPG_KEY}"
chmod 644 "${GPG_KEY}"

# Add repository (idempotent — overwrites if exists)
echo "Adding APT repository..."
cat > "${APT_LIST}" <<EOF
deb [arch=arm64 signed-by=${GPG_KEY}] ${BASE_URL}/apt stable main
EOF

# Update and install
echo "Updating package lists..."
apt-get update -qq

echo "Installing uconsole-cloud..."
apt-get install -y uconsole-cloud

echo ""
echo "Installation complete. Run 'uconsole setup' to configure your device."
