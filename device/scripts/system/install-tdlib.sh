#!/bin/bash
# install-tdlib.sh — build TDLib from source on aarch64 and install
# python-telegram into ~/tg-venv so paul-nameless/tg can run.
#
# Why: piwheels python-telegram ships an x86_64 libtdjson.so, useless on the Pi.
# Debian has no tdlib package. Only real path is building from source.
#
# Requires: ~2GB RAM during linker (add swap if needed), ~1GB disk, ~30-60 min.
set -euo pipefail

log() { printf '\033[1;36m[tdlib]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[tdlib]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[tdlib]\033[0m %s\n' "$*" >&2; exit 1; }

log "Checking venv..."
if [ ! -x "$HOME/tg-venv/bin/python" ]; then
    log "Creating ~/tg-venv..."
    python3 -m venv "$HOME/tg-venv"
    "$HOME/tg-venv/bin/pip" install --upgrade pip
    "$HOME/tg-venv/bin/pip" install tg
fi

log "Installing build deps (sudo required)..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    gperf cmake g++ libssl-dev zlib1g-dev git ca-certificates

log "Checking memory / swap (linker needs ~2GB RAM)..."
SWAP_MB=$(free -m | awk '/^Swap:/ {print $2}')
MEM_MB=$(free -m | awk '/^Mem:/ {print $2}')
TOTAL_MB=$((SWAP_MB + MEM_MB))
log "  RAM=${MEM_MB}MB  Swap=${SWAP_MB}MB  Total=${TOTAL_MB}MB"
if [ "$TOTAL_MB" -lt 3000 ]; then
    warn "Less than 3GB RAM+swap — linker may OOM. Add swap first:"
    warn "  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile"
    warn "  sudo mkswap /swapfile && sudo swapon /swapfile"
    read -rp "Continue anyway? [y/N] " yn
    [ "${yn:-n}" = "y" ] || exit 1
fi

BUILD_DIR=${TDLIB_BUILD_DIR:-/tmp/td-build}
log "Cloning TDLib into $BUILD_DIR..."
rm -rf "$BUILD_DIR"
git clone --depth 1 https://github.com/tdlib/td.git "$BUILD_DIR"

log "Configuring (Release)..."
mkdir -p "$BUILD_DIR/build"
cd "$BUILD_DIR/build"
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/usr/local ..

log "Building tdjson target (this is the long part)..."
# Use fewer jobs than nproc to keep RAM usage down on the Pi
JOBS=$(( $(nproc) > 2 ? 2 : 1 ))
cmake --build . --target tdjson -- -j"$JOBS"

log "Installing libtdjson.so to /usr/local/lib..."
sudo cp libtdjson.so* /usr/local/lib/ 2>/dev/null || \
    sudo find . -name 'libtdjson.so*' -exec cp {} /usr/local/lib/ \;
sudo ldconfig

if ! ldconfig -p | grep -q libtdjson; then
    fail "libtdjson.so not visible to ldconfig — install failed"
fi
log "  $(ldconfig -p | grep libtdjson | head -1)"

log "Installing python-telegram into ~/tg-venv..."
"$HOME/tg-venv/bin/pip" install python-telegram

log "Verifying import..."
"$HOME/tg-venv/bin/python" -c "from telegram.client import Telegram; print('  ok')"

log "Done. Launch: TUI → TOOLS → Telegram  (or: ~/tg-venv/bin/python -m tg)"
