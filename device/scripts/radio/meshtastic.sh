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
  status              node info, region, frequency (default)
  nodes               list known nodes in the mesh
  listen              stream incoming packets (Ctrl-C to stop)
  send [msg]          broadcast a text message (prompts if no arg)
  web                 print Meshtastic web UI URL
  service [action]    systemctl wrapper — status|start|stop|restart
  logs                tail meshtasticd journal (Ctrl-C to stop)

  config show                    dump current MQTT/position/region state
  config privacy stealth|public  preset bundles
  config mqtt on|off|toggle      toggle the MQTT module
  config position off|low|full|clear
  config rename [long] [short]   set node long+short name (prompts if empty)
  config region [code]           US|EU_433|EU_868|ANZ|CN|JP|KR|TW|IN|NZ|TH|...
  config channel-name [n] [idx]  set channel name (default index 0)

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
    printf "Listening for packets on %s:4403 — Ctrl-C to stop\n" "$HOST"
    printf "Filtered view. For raw protobuf: meshtastic --host %s --listen\n\n" "$HOST"
    meshtastic --host "$HOST" --listen 2>&1 | python3 -u -c '
import sys, re, time, signal
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
for ln in sys.stdin:
    if "Publishing meshtastic.receive" in ln:
        m = re.search(r"portnum.: .(\w+).", ln)
        frm = re.search(r"fromId.: .([!\w]+).", ln)
        txt = re.search(r"text.: .([^\"]+).", ln)
        t = m.group(1) if m else "?"
        f = frm.group(1) if frm else "?"
        ts = time.strftime("%H:%M:%S")
        out = "[" + ts + "] " + t.ljust(20) + " from=" + f
        if txt:
            out += "  MSG: " + txt.group(1)
        print(out, flush=True)
        continue
    if ln.startswith("DEBUG") or "Unexpected FromRadio" in ln: continue
    if ln.startswith((" ", "\t")) or ln.strip() in ("}", "{"): continue
    s = ln.rstrip()
    if not s: continue
    if s.startswith(("WARNING", "ERROR", "Connected", "Disconnected", "[")):
        print(s, flush=True)
'
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

# ── Config wrappers ──────────────────────────────────────────────────────────

mt() { meshtastic --host "$HOST" "$@" 2>&1 | grep -vE '^(Connected to radio|INFO file:)' | head -4; }

cfg_privacy() {
    local preset="${1:-}"
    case "$preset" in
        stealth)
            section "Privacy: Stealth"
            info "MQTT off, position off + cleared, anon name"
            mt --set mqtt.enabled false
            mt --set position.position_broadcast_secs 0
            mt --set position.position_broadcast_smart_enabled false
            mt --remove-position
            local rnd
            rnd=$(tr -dc 'a-f0-9' </dev/urandom | head -c 4)
            mt --set-owner "node-$rnd" --set-owner-short "n$rnd"
            ok "Stealth applied — you are not on the public mesh"
            warn "Phone app may still push GPS. Turn off location sharing in the app."
            ;;
        public)
            section "Privacy: Public"
            info "MQTT on, low-precision position, uConsole name"
            mt --set mqtt.enabled true
            mt --ch-set uplink_enabled true --ch-index 0
            mt --ch-set downlink_enabled true --ch-index 0
            mt --ch-set name LongFast --ch-index 0
            mt --ch-set position_precision 10 --ch-index 0
            mt --set position.position_broadcast_secs 3600
            mt --set position.position_broadcast_smart_enabled true
            mt --set-owner "uConsole $(hostname -s)" --set-owner-short "ucon"
            ok "Public applied — visible on mqtt.meshtastic.org, ~10km grid"
            ;;
        *)
            err "Usage: meshtastic.sh config privacy {stealth|public}"
            return 1
            ;;
    esac
}

cfg_mqtt() {
    local state="${1:-show}"
    case "$state" in
        on)     section "MQTT → ON";  mt --set mqtt.enabled true ;;
        off)    section "MQTT → OFF"; mt --set mqtt.enabled false ;;
        toggle)
            local cur
            cur=$(meshtastic --host "$HOST" --get mqtt.enabled 2>&1 | awk -F': ' '/mqtt.enabled/ {print $2}')
            if [ "$cur" = "True" ]; then
                section "MQTT toggle: True → False"; mt --set mqtt.enabled false
            else
                section "MQTT toggle: False → True"; mt --set mqtt.enabled true
            fi
            ;;
        show|*)
            section "MQTT state"
            meshtastic --host "$HOST" --get mqtt.enabled 2>&1 | tail -3
            ;;
    esac
}

cfg_position() {
    local mode="${1:-show}"
    case "$mode" in
        off)
            section "Position → OFF"
            mt --set position.position_broadcast_secs 0
            mt --set position.position_broadcast_smart_enabled false
            mt --remove-position
            ;;
        low)
            section "Position → LOW (~10km grid, hourly)"
            mt --set position.position_broadcast_secs 3600
            mt --set position.position_broadcast_smart_enabled false
            mt --ch-set position_precision 10 --ch-index 0
            ;;
        full)
            section "Position → FULL (precise, 15min + smart)"
            mt --set position.position_broadcast_secs 900
            mt --set position.position_broadcast_smart_enabled true
            mt --ch-set position_precision 32 --ch-index 0
            ;;
        clear)
            section "Position → cleared"
            mt --remove-position
            ;;
        show|*)
            section "Position state"
            meshtastic --host "$HOST" --get position.position_broadcast_secs 2>&1 | tail -2
            meshtastic --host "$HOST" --get position.position_broadcast_smart_enabled 2>&1 | tail -2
            ;;
    esac
}

cfg_rename() {
    local long="${1:-}" short="${2:-}"
    if [ -z "$long" ]; then
        printf "Long name:  "; read -r long
        [ -z "$long" ] && { warn "Cancelled"; return 1; }
    fi
    if [ -z "$short" ]; then
        printf "Short (4ch, Enter=auto): "; read -r short
        [ -z "$short" ] && short="${long:0:4}"
    fi
    section "Rename node"
    mt --set-owner "$long" --set-owner-short "$short"
    ok "Node renamed to: $long / $short"
}

cfg_region() {
    local r="${1:-}"
    if [ -z "$r" ]; then
        cat <<EOF
Common region codes:
  US        — 902-928 MHz (United States)
  EU_433    — 433.175-434.775 MHz (Europe/Asia ISM)
  EU_868    — 869.4-869.65 MHz (Europe)
  ANZ       — 915-928 MHz (Australia/New Zealand)
  CN        — 470-510 MHz (China)
  JP        — 920.5-927.5 MHz (Japan)
  KR        — 920-923 MHz (Korea)
  TW        — 920-925 MHz (Taiwan)
  IN        — 865-867 MHz (India)
  TH        — 920-925 MHz (Thailand)
EOF
        printf "\nRegion code: "; read -r r
        [ -z "$r" ] && { warn "Cancelled"; return 1; }
    fi
    section "Region → $r"
    mt --set lora.region "$r"
    warn "Make sure your antenna matches the new region's frequency band."
}

cfg_channel_name() {
    local name="${1:-}" idx="${2:-0}"
    if [ -z "$name" ]; then
        printf "Channel name (idx=$idx): "; read -r name
        [ -z "$name" ] && { warn "Cancelled"; return 1; }
    fi
    section "Channel $idx name → $name"
    mt --ch-set name "$name" --ch-index "$idx"
}

cfg_show() {
    section "Meshtastic Config Summary"
    check_cli
    check_daemon
    printf "\n"
    meshtastic --host "$HOST" --get mqtt.enabled 2>&1 | grep mqtt
    meshtastic --host "$HOST" --get position.position_broadcast_secs 2>&1 | grep position
    meshtastic --host "$HOST" --get position.position_broadcast_smart_enabled 2>&1 | grep position
    meshtastic --host "$HOST" --get lora.region 2>&1 | grep lora
    printf "\nNode identity:\n"
    meshtastic --host "$HOST" --info 2>&1 | grep -E '"longName"|"shortName"|"id"' | head -5
}

cmd_config() {
    shift || true
    local sub="${1:-show}"
    shift || true
    check_cli
    check_daemon
    case "$sub" in
        show)          cfg_show ;;
        privacy)       cfg_privacy "$@" ;;
        mqtt)          cfg_mqtt "$@" ;;
        position)      cfg_position "$@" ;;
        rename)        cfg_rename "$@" ;;
        region)        cfg_region "$@" ;;
        channel-name)  cfg_channel_name "$@" ;;
        *)
            err "Unknown config subcommand: $sub"
            usage
            return 1
            ;;
    esac
}

case "${1:-status}" in
    status)   cmd_status ;;
    nodes)    cmd_nodes ;;
    listen)   cmd_listen ;;
    send)     cmd_send "$@" ;;
    web)      cmd_web ;;
    service)  cmd_service "$@" ;;
    logs)     cmd_logs ;;
    config)   cmd_config "$@" ;;
    -h|--help|help) usage ;;
    *)        echo "Unknown command: $1"; usage; exit 1 ;;
esac
