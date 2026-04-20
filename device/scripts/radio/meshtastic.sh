#!/usr/bin/env bash
# Meshtastic — talk to the local meshtasticd daemon over TCP (port 4403)
# Wraps the official `meshtastic` Python CLI so the TUI has a clean entrypoint.
set -euo pipefail

source "$(dirname "$0")/lib.sh"

# meshtastic CLI is typically installed via `pip install --user`
export PATH="$HOME/.local/bin:$PATH"

HOST="${MESHTASTIC_HOST:-localhost}"
WEB_URL_LOCAL="https://uconsole.local:9443"

usage() {
    cat <<EOF
Usage: meshtastic.sh [command] [args]

Commands:
  status       node info, region, frequency (default)
  nodes        list known nodes in the mesh
  listen       stream incoming packets (Ctrl-C to stop)
  send [msg]   broadcast a text message (prompts if no arg)
  web          print Meshtastic web UI URL
  service [s]  systemctl wrapper — status|start|stop|restart
  logs         tail meshtasticd journal (Ctrl-C to stop)

Host: $HOST (set \$MESHTASTIC_HOST to override)
EOF
}

check_cli() {
    if ! command -v meshtastic &>/dev/null; then
        err "meshtastic CLI not found"
        info "Install: pip3 install --user --break-system-packages meshtastic"
        exit 1
    fi
}

check_daemon() {
    if ! systemctl is-active --quiet meshtasticd; then
        err "meshtasticd is not running"
        info "Start: sudo systemctl start meshtasticd"
        info "Or: meshtastic.sh service start"
        exit 1
    fi
}

cmd_status() {
    section "Meshtastic Node Status"
    check_cli
    check_daemon
    meshtastic --host "$HOST" --info 2>&1 | head -60
}

cmd_nodes() {
    section "Meshtastic Mesh Nodes"
    check_cli
    check_daemon
    meshtastic --host "$HOST" --nodes
}

cmd_listen() {
    section "Meshtastic — Listening"
    check_cli
    check_daemon
    printf "Listening for packets on %s:4403 — Ctrl-C to stop\n\n" "$HOST"
    meshtastic --host "$HOST" --listen
}

cmd_send() {
    shift || true
    local msg="${*:-}"
    check_cli
    check_daemon
    if [ -z "$msg" ]; then
        printf "Message: "
        read -r msg
        [ -z "$msg" ] && { warn "Empty message — cancelled"; return 1; }
    fi
    section "Meshtastic TX"
    printf "Sending: %s\n" "$msg"
    meshtastic --host "$HOST" --sendtext "$msg"
    ok "Sent (delivery depends on peers in range)"
}

cmd_web() {
    section "Meshtastic Web UI"
    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    printf "  Local:     %s\n" "$WEB_URL_LOCAL"
    [ -n "$ip" ] && printf "  IP:        https://%s:9443\n" "$ip"
    printf "\n"
    info "Port 9443, self-signed cert (accept the browser warning)"
    info "Requires meshtasticd running. Features: chat, nodes map, config, channels."
}

cmd_service() {
    local action="${2:-status}"
    case "$action" in
        status)
            section "meshtasticd Service"
            systemctl status meshtasticd --no-pager 2>&1 | head -15
            ;;
        start|stop|restart)
            section "meshtasticd: $action"
            sudo systemctl "$action" meshtasticd
            sleep 1
            systemctl is-active meshtasticd
            ;;
        *)
            err "Unknown action: $action"
            info "Valid: status|start|stop|restart"
            return 1
            ;;
    esac
}

cmd_logs() {
    section "meshtasticd Logs"
    info "Tailing — Ctrl-C to stop"
    echo ""
    sudo journalctl -u meshtasticd -f --no-pager
}

case "${1:-status}" in
    status)   cmd_status ;;
    nodes)    cmd_nodes ;;
    listen)   cmd_listen ;;
    send)     cmd_send "$@" ;;
    web)      cmd_web ;;
    service)  cmd_service "$@" ;;
    logs)     cmd_logs ;;
    -h|--help|help) usage ;;
    *)        echo "Unknown command: $1"; usage; exit 1 ;;
esac
