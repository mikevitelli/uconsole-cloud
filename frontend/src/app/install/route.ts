import { NextResponse } from "next/server";

const INSTALL_SCRIPT = `#!/bin/bash
# uconsole.cloud installer
# Usage: curl -fsSL https://uconsole.cloud/install | bash
set -euo pipefail

BASE_URL="https://uconsole.cloud"
BIN_DIR="\${HOME}/.local/bin"
SCRIPTS_DIR="\${HOME}/scripts"

echo "Installing uconsole CLI..."

# Create directories
mkdir -p "\${BIN_DIR}" "\${SCRIPTS_DIR}"

# Download CLI
curl -fsSL "\${BASE_URL}/api/scripts/uconsole" -o "\${BIN_DIR}/uconsole"
chmod +x "\${BIN_DIR}/uconsole"

# Download push-status script
curl -fsSL "\${BASE_URL}/api/scripts/push-status.sh" -o "\${SCRIPTS_DIR}/push-status.sh"
chmod +x "\${SCRIPTS_DIR}/push-status.sh"

# Add to PATH if needed
if ! echo "\${PATH}" | grep -q "\${BIN_DIR}"; then
  SHELL_RC="\${HOME}/.bashrc"
  [ -f "\${HOME}/.zshrc" ] && SHELL_RC="\${HOME}/.zshrc"
  echo "export PATH=\\"\\\${HOME}/.local/bin:\\\${PATH}\\"" >> "\${SHELL_RC}"
  export PATH="\${BIN_DIR}:\${PATH}"
  echo "Added \${BIN_DIR} to PATH (restart shell or: source \${SHELL_RC})"
fi

echo ""
echo "Installed uconsole CLI to \${BIN_DIR}/uconsole"
echo "Downloaded scripts to \${SCRIPTS_DIR}/"
echo ""
echo "Next: run 'uconsole setup' to link your device"
`;

export async function GET() {
  return new NextResponse(INSTALL_SCRIPT, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
