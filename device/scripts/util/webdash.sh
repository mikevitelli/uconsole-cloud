#!/bin/bash
# Web dashboard for the uConsole
# Usage: webdash.sh           Start the web dashboard on port 8080
#        webdash.sh stop      Stop any running instance

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
    stop)
        pkill -f "python3.*webdash.py" && echo "Stopped." || echo "Not running."
        ;;
    *)
        IP=$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
        echo "Starting uConsole dashboard..."
        echo "  http://${IP:-localhost}:8080"
        echo ""
        echo "  Press Ctrl+C to stop"
        exec python3 "$SCRIPT_DIR/webdash.py"
        ;;
esac
