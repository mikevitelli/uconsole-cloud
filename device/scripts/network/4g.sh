#!/bin/bash
# 4g.sh — uConsole 4G / Cellular control (SIMCom SIM7600G-H) for the TUI.
#
# Usage: 4g.sh status      Modem + connection overview
#        4g.sh enable       Power ON the module (GPIO pulse, ~25s)
#        4g.sh disable      Power OFF the module (battery save)
#        4g.sh up           Connect the data path on wwan0
#        4g.sh down         Drop the data path (modem stays powered)
#        4g.sh reset        down -> disable -> enable -> up (full cycle)
#        4g.sh diagnose     Run the vendor diagnostics
#
# T-Mobile US is IPv6-only (464XLAT/NAT64): a plain IPv4 bearer is rejected with
# 'pdn-ipv4-call-disallowed', so we connect with ip-type=ipv4v6 and apply the STATIC
# IPv6 bearer to wwan0 ourselves (there is no DHCP). IPv4 reaches via NAT64 64:ff9b::/96.
# The module powers OFF by default (on-demand) to save battery; WiFi stays primary
# (cellular default route gets a high metric).

source "$(dirname "$0")/lib.sh"

APN="${UCONSOLE_4G_APN:-fast.t-mobile.com}"
IFACE="${UCONSOLE_4G_IFACE:-wwan0}"
METRIC="${UCONSOLE_4G_METRIC:-700}"

strip_ansi() { sed 's/\x1b\[[0-9;]*m//g'; }
modem_index()  { mmcli -L 2>/dev/null | grep -oE '/Modem/[0-9]+' | grep -oE '[0-9]+$' | head -1; }
modem_present(){ mmcli -L 2>/dev/null | grep -q SIM7600; }

# field NAME  -> value from a (newline-joined) mmcli dump on stdin
_field() { awk -F"$1: *" -v k="$1:" '$0 ~ k {print $2; exit}'; }

cmd_status() {
    section "4G / Cellular  (SIM7600G-H)"
    if ! modem_present; then
        warn "Module not powered on / not detected."
        info "Run 'Power On' first — it pulses the GPIO and waits ~25s for USB."
        return 0
    fi
    local m dump
    m=$(modem_index)
    dump=$(mmcli -m "$m" 2>/dev/null | strip_ansi)

    ok    "Model:        $(echo "$dump" | _field 'model')"
    ok    "Operator:     $(echo "$dump" | _field 'operator name')  ($(echo "$dump" | _field 'registration'))"
    ok    "Access tech:  $(echo "$dump" | _field 'access tech')"
    ok    "Signal:       $(echo "$dump" | _field 'signal quality')"
    ok    "Modem state:  $(echo "$dump" | grep -m1 'state:' | sed 's/.*state: *//')"
    ok    "Packet svc:   $(echo "$dump" | _field 'packet service state')"

    local ip6
    ip6=$(ip -6 addr show "$IFACE" 2>/dev/null | grep -oE 'inet6 [23][0-9a-f:]+/[0-9]+' | head -1)
    if [ -n "$ip6" ]; then
        ok "wwan0 IPv6:   ${ip6#inet6 }"
    else
        warn "wwan0:        no global IPv6 (not connected — run 'Connect')"
    fi

    section "Reachability"
    if [ -n "$ip6" ]; then
        if ping6 -c1 -W4 -I "$IFACE" 2001:4860:4860::8888 >/dev/null 2>&1; then
            ok "IPv6 over cellular ...... OK"
        else
            err "IPv6 over cellular ...... FAIL"
        fi
        if ping6 -c1 -W4 -I "$IFACE" 64:ff9b::8.8.8.8 >/dev/null 2>&1; then
            ok "IPv4 via NAT64 ......... OK"
        else
            err "IPv4 via NAT64 ......... FAIL"
        fi
    else
        info "Data path down — nothing to test."
    fi
}

cmd_enable() {
    section "Powering on 4G module"
    info "Pulsing POWER/RESET GPIO and waiting for USB enumeration (~25s)..."
    sudo uconsole-4g enable
}

cmd_disable() {
    section "Powering off 4G module"
    cmd_down >/dev/null 2>&1 || true
    sudo uconsole-4g disable
}

cmd_up() {
    section "Connecting cellular data ($APN)"
    if ! modem_present; then
        info "Module not detected — powering on first..."
        sudo uconsole-4g enable
    fi
    local m
    m=$(modem_index)
    if [ -z "$m" ]; then err "No modem found."; return 1; fi

    sudo mmcli -m "$m" --simple-disconnect >/dev/null 2>&1 || true
    sleep 1
    info "Requesting bearer (ip-type=ipv4v6 — required for T-Mobile)..."
    if ! sudo mmcli -m "$m" --simple-connect="apn=$APN,ip-type=ipv4v6"; then
        err "Bearer connect failed (check signal / SIM / APN)."
        return 1
    fi
    sleep 2

    # find the connected bearer that carries an IPv6 config
    local b bsel=""
    for b in $(mmcli -m "$m" 2>/dev/null | grep -oE 'Bearer/[0-9]+' | sed 's#Bearer/##'); do
        if mmcli -b "$b" 2>/dev/null | grep -qi 'connected: *yes' \
        && mmcli -b "$b" 2>/dev/null | grep -qi 'IPv6 config'; then bsel="$b"; fi
    done
    if [ -z "$bsel" ]; then err "No connected IPv6 bearer."; return 1; fi

    local d addr pfx gw
    d=$(mmcli -b "$bsel" 2>/dev/null | strip_ansi)
    addr=$(echo "$d" | awk '/IPv6 config/{f=1} f&&/address:/{print $NF; exit}')
    pfx=$(echo "$d"  | awk '/IPv6 config/{f=1} f&&/prefix:/{print $NF; exit}')
    gw=$(echo "$d"   | awk '/IPv6 config/{f=1} f&&/gateway:/{print $NF; exit}')
    if [ -z "$addr" ] || [ -z "$gw" ]; then err "Bearer has no IPv6 address/gateway."; return 1; fi

    sudo ip link set "$IFACE" up
    sudo ip -6 addr flush dev "$IFACE" 2>/dev/null || true
    sudo ip -6 addr add "$addr/${pfx:-64}" dev "$IFACE"
    sudo ip -6 route replace default via "$gw" dev "$IFACE" metric "$METRIC"
    ok "wwan0: $addr/${pfx:-64}  via $gw  (metric $METRIC — WiFi stays primary)"

    if ping6 -c2 -W4 -I "$IFACE" 2001:4860:4860::8888 >/dev/null 2>&1; then
        ok "IPv6 over cellular OK"
    else
        warn "Connected, but IPv6 test ping failed (weak signal?)."
    fi
    ping6 -c2 -W4 -I "$IFACE" 64:ff9b::8.8.8.8 >/dev/null 2>&1 && ok "IPv4 via NAT64 OK"
}

cmd_down() {
    section "Dropping cellular data path"
    local m
    m=$(modem_index)
    sudo ip -6 route del default dev "$IFACE" 2>/dev/null || true
    sudo ip -6 addr flush dev "$IFACE" 2>/dev/null || true
    [ -n "$m" ] && sudo mmcli -m "$m" --simple-disconnect >/dev/null 2>&1 || true
    ok "Data path down (module still powered — use 'Power Off' to save battery)."
}

cmd_reset() {
    section "Full 4G reset cycle"
    cmd_down  || true
    cmd_disable || true
    sleep 2
    cmd_enable
    cmd_up
}

cmd_diagnose() {
    if ! modem_present; then
        section "4G Diagnostics"
        warn "Module not powered on / not detected."
        info "Run 'Power On' first — it pulses the GPIO and waits ~25s for USB."
        return 0
    fi
    local m dump
    m=$(modem_index)
    dump=$(mmcli -m "$m" 2>/dev/null | strip_ansi)

    section "Service"
    if [ "$(systemctl is-active ModemManager 2>/dev/null)" = "active" ]; then
        ok "ModemManager: active"
    else
        err "ModemManager: not active"
    fi

    section "Hardware"
    ok "Model:        $(echo "$dump" | _field 'model')"
    ok "Firmware:     $(echo "$dump" | _field 'firmware revision')"
    ok "IMEI:         $(echo "$dump" | _field 'equipment id')"

    section "Network"
    ok "Operator:     $(echo "$dump" | _field 'operator name')"
    ok "Registration: $(echo "$dump" | _field 'registration')"
    ok "Access tech:  $(echo "$dump" | _field 'access tech')"
    local sigq sigpct
    sigq=$(echo "$dump" | _field 'signal quality')
    sigpct=$(echo "$sigq" | grep -oE '[0-9]+' | head -1)
    ok "Signal:       $sigq"
    if [ -n "$sigpct" ]; then printf "    "; bar_inv "$sigpct" 100; printf "\n"; fi
    local bands
    bands=$(echo "$dump" | awk '/Bands/{f=1} f&&/current:/{sub(/.*current: */,""); print; exit}' | sed 's/,[[:space:]]*$//')
    ok "Bands:        ${bands:-(unknown)}"

    section "SIM"
    ok   "Lock status:  $(echo "$dump" | _field 'lock')"
    info "A 'sim-pin2' lock is harmless/expected (PIN2 = fixed-dialing, not data)."

    section "Data"
    ok "Modem state:  $(echo "$dump" | grep -m1 'state:' | sed 's/.*state: *//')"
    # find the connected bearer that carries an IPv6 config
    local b bsel=""
    for b in $(echo "$dump" | grep -oE 'Bearer/[0-9]+' | sed 's#Bearer/##'); do
        if mmcli -b "$b" 2>/dev/null | grep -qi 'connected: *yes' \
        && mmcli -b "$b" 2>/dev/null | grep -qi 'IPv6 config'; then bsel="$b"; fi
    done
    if [ -n "$bsel" ]; then
        local d bapn btype bgw bdns
        d=$(mmcli -b "$bsel" 2>/dev/null | strip_ansi)
        bapn=$(echo "$d" | _field 'apn')
        btype=$(echo "$d" | _field 'ip type')
        bgw=$(echo "$d"  | awk '/IPv6 config/{f=1} f&&/gateway:/{print $NF; exit}')
        bdns=$(echo "$d" | awk '/IPv6 config/{f=1} f&&/dns:/{print $NF; exit}')
        ok "Bearer APN:   $bapn  (ip-type $btype)"
        ok "Gateway:      ${bgw:-(none)}"
        ok "DNS:          ${bdns:-(none)}"
    else
        warn "No connected IPv6 bearer (data path down — run 'Connect')."
    fi
    local ip6
    ip6=$(ip -6 addr show "$IFACE" 2>/dev/null | grep -oE 'inet6 [23][0-9a-f:]+/[0-9]+' | head -1)
    if [ -n "$ip6" ]; then
        ok "wwan0 IPv6:   ${ip6#inet6 }"
    else
        warn "wwan0:        no global IPv6"
    fi

    section "Routing"
    info "IPv4 default: $(ip -4 route show default 2>/dev/null | head -1 | sed 's/  */ /g')"
    info "IPv6 default: $(ip -6 route show default 2>/dev/null | head -1 | sed 's/  */ /g')"

    section "Connectivity"
    if [ -n "$ip6" ]; then
        if ping6 -c1 -W4 -I "$IFACE" 2001:4860:4860::8888 >/dev/null 2>&1; then
            ok "IPv6 over cellular ...... OK"
        else
            err "IPv6 over cellular ...... FAIL"
        fi
        if ping6 -c1 -W4 -I "$IFACE" 64:ff9b::8.8.8.8 >/dev/null 2>&1; then
            ok "IPv4 via NAT64 ......... OK"
        else
            err "IPv4 via NAT64 ......... FAIL"
        fi
    else
        warn "Data path down — nothing to test (run 'Connect')."
    fi
    info "Plain IPv4 is disabled by T-Mobile (IPv6-only + NAT64) — this is expected."

    section "USB"
    if lsusb 2>/dev/null | grep -qi 1e0e; then
        ok "SIMCom USB device present (1e0e)."
    else
        warn "SIMCom USB device (1e0e) not found on the bus."
    fi
}

cmd_speed() {
    section "Cellular Speed Test (wwan0)"
    if ! modem_present; then
        warn "Module not powered on / not detected — run 'Power On' first."
        return 0
    fi
    local m state ip6
    m=$(modem_index)
    state=$(mmcli -m "$m" 2>/dev/null | strip_ansi | grep -m1 'state:' | sed 's/.*state: *//')
    ip6=$(ip -6 addr show "$IFACE" 2>/dev/null | grep -oE 'inet6 [23][0-9a-f:]+/[0-9]+' | head -1)
    if [ "$state" != "connected" ] || [ -z "$ip6" ]; then
        info "Data path is down — bringing it up first..."
        cmd_up
        if ! modem_present; then
            warn "Module not detected — aborting."
            return 0
        fi
        section "Cellular Speed Test (wwan0)"
    fi

    info "This uses CELLULAR DATA — it will consume data on your plan."

    # Latency
    local rttline avg
    rttline=$(ping6 -c5 -W3 -I "$IFACE" 2001:4860:4860::8888 2>/dev/null | grep -E 'rtt|round-trip')
    avg=$(echo "$rttline" | awk -F'= ' '{print $2}' | awk -F'/' '{print $2}')
    if [ -n "$avg" ]; then
        ok "Latency: $avg ms"
    else
        err "Latency: test failed"
    fi

    # Download
    local dl_bps dl_mbit
    dl_bps=$(curl -6 --interface "$IFACE" -s -o /dev/null -w '%{speed_download}' \
        --max-time 30 "https://speed.cloudflare.com/__down?bytes=10485760")
    dl_mbit=$(echo "$dl_bps" | awk '{printf "%.1f", $1*8/1000000}')
    if awk "BEGIN{exit !($dl_bps>0)}"; then
        ok "Download: $dl_mbit Mbit/s"
        printf "    "; bar_inv "$(echo "$dl_mbit" | awk '{printf "%d", $1}')" 150; printf "\n"
    else
        err "Download failed"
    fi

    # Upload
    local ul_bps ul_mbit
    ul_bps=$(head -c 5242880 /dev/zero | curl -6 --interface "$IFACE" -s -o /dev/null \
        -w '%{speed_upload}' --max-time 30 --data-binary @- "https://speed.cloudflare.com/__up")
    ul_mbit=$(echo "$ul_bps" | awk '{printf "%.1f", $1*8/1000000}')
    if awk "BEGIN{exit !($ul_bps>0)}"; then
        ok "Upload: $ul_mbit Mbit/s"
    else
        warn "Upload failed"
    fi
}

cmd_help() {
    section "4G / Cellular — uConsole commands"
    echo "  Module: SIMCom SIM7600G-H (LTE)   Carrier: T-Mobile (APN fast.t-mobile.com)"
    echo "  The module is OFF by default to save battery — power on, then connect."
    section "Power"
    echo "  4g enable      power on the module (GPIO pulse, ~25s)"
    echo "  4g disable     power off the module (battery save)"
    section "Data"
    echo "  4g up          connect T-Mobile data on wwan0 (ip-type=ipv4v6 + static IPv6)"
    echo "  4g down        disconnect the data path (module stays powered)"
    section "Info & test"
    echo "  4g status      modem + connection overview"
    echo "  4g diagnose    full modem health report"
    echo "  4g speed       latency + down/up speed over cellular"
    echo "  4g reset       full down -> off -> on -> up cycle"
    echo "  4g help        this reference"
    section "Standalone helpers"
    echo "  4g-verify      one-shot install check (enable->status->connect->ping + brownout watch)"
    echo "  4g-up / 4g-down   same as 'up' / 'down', run directly"
    echo "  uconsole-4g …  low-level CM5 control (enable/disable/unlock/reset/diagnose)"
    section "TUI"
    echo "  console -> NETWORK -> Cellular   live dashboard · signal monitor · tower map · speed"
    section "Notes"
    echo "  T-Mobile is IPv6-only; IPv4 rides NAT64 (64:ff9b::/96)."
    echo "  Power on while on AC — this unit has brownout sensitivity."
    echo "  Docs: ~/docs/4g-install/"
    echo
}

case "${1:-status}" in
    status)   cmd_status ;;
    enable)   cmd_enable ;;
    disable)  cmd_disable ;;
    up)       cmd_up ;;
    down)     cmd_down ;;
    reset)    cmd_reset ;;
    diagnose) cmd_diagnose ;;
    speed)    cmd_speed ;;
    help|-h|--help) cmd_help ;;
    *) echo "Unknown command: $1"; echo; cmd_help; exit 2 ;;
esac
