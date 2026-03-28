#!/bin/bash
set -euo pipefail

# Generate a GPG signing key for the uconsole APT repository.
# Run this ONCE on the machine that will sign packages.
# The public key is exported to frontend/public/apt/uconsole.gpg

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APT_DIR="${REPO_ROOT}/frontend/public/apt"
KEY_NAME="uconsole-apt"
KEY_EMAIL="apt@uconsole.cloud"

echo "Generating GPG key for APT repository signing..."
echo ""
echo "  Name:  ${KEY_NAME}"
echo "  Email: ${KEY_EMAIL}"
echo ""

# Check if key already exists
if gpg --list-keys "${KEY_EMAIL}" &>/dev/null; then
    echo "GPG key for ${KEY_EMAIL} already exists."
    echo "To regenerate, first delete it:"
    echo "  gpg --delete-secret-and-public-key ${KEY_EMAIL}"
    exit 1
fi

# Generate key (non-interactive)
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Name-Real: ${KEY_NAME}
Name-Email: ${KEY_EMAIL}
Expire-Date: 0
%no-protection
%commit
EOF

echo ""
echo "Key generated. Exporting public key..."

# Export public key for distribution
mkdir -p "${APT_DIR}"
gpg --export --armor "${KEY_EMAIL}" > "${APT_DIR}/uconsole.gpg"

echo ""
echo "Public key exported to: ${APT_DIR}/uconsole.gpg"
echo ""
echo "IMPORTANT: Back up your GPG private key securely."
echo "  gpg --export-secret-keys ${KEY_EMAIL} > uconsole-apt-private.gpg"
echo ""
echo "DO NOT commit the private key to git."
