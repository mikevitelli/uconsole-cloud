#!/bin/bash
# Webdash status and config overview for TUI panel
LIB_DIR="$(cd "$(dirname "$0")" && pwd)"
for libpath in /opt/uconsole/lib/lib.sh "$LIB_DIR/../lib/lib.sh" "$HOME/scripts/lib.sh"; do
    [ -f "$libpath" ] && { source "$libpath" 2>/dev/null || true; break; }
done

section "Web Dashboard Info"

# ── Service ──
printf "  ${BOLD}Service${RESET}\n"
STATUS=$(systemctl is-active uconsole-webdash 2>/dev/null)
if [ "$STATUS" = "active" ]; then
    PID=$(systemctl show uconsole-webdash --property=MainPID --value 2>/dev/null)
    UPTIME=$(systemctl show uconsole-webdash --property=ActiveEnterTimestamp --value 2>/dev/null)
    printf "    Status:     ${GREEN}running${RESET} (PID %s)\n" "$PID"
    printf "    Since:      %s\n" "$UPTIME"
    MEM=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.1fM", $1/1024}')
    [ -n "$MEM" ] && printf "    Memory:     %s\n" "$MEM"
else
    printf "    Status:     ${RED}stopped${RESET}\n"
fi
echo ""

# ── Access ──
printf "  ${BOLD}Access${RESET}\n"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
printf "    LAN URL:    https://%s\n" "${IP:-unknown}"
printf "    Local URL:  https://uconsole.local\n"
if python3 -c "
import json
with open('$HOME/.config/uconsole/config.json') as f:
    d = json.load(f)
exit(0 if d.get('webdash_password_hash') else 1)
" 2>/dev/null; then
    printf "    Password:   ${GREEN}set (bcrypt)${RESET}\n"
else
    printf "    Password:   ${RED}not set — run uconsole-passwd${RESET}\n"
fi
printf "    Session:    30-day cookie\n"
echo ""

# ── nginx ──
printf "  ${BOLD}Nginx Reverse Proxy${RESET}\n"
NGINX_STATUS=$(systemctl is-active nginx 2>/dev/null)
if [ "$NGINX_STATUS" = "active" ]; then
    printf "    Status:     ${GREEN}running${RESET}\n"
else
    printf "    Status:     ${RED}%s${RESET}\n" "$NGINX_STATUS"
fi
printf "    Listen:     443 (HTTPS)\n"
printf "    Proxy to:   127.0.0.1:8080\n"
printf "    Config:     /etc/nginx/sites-available/uconsole-webdash\n"
echo ""

# ── SSL ──
printf "  ${BOLD}SSL Certificate${RESET}\n"
CERT="/etc/uconsole/ssl/uconsole.crt"
[ ! -f "$CERT" ] && CERT="/etc/uconsole/ssl/uconsole.pem"
if [ -f "$CERT" ]; then
    EXPIRY=$(openssl x509 -enddate -noout -in "$CERT" 2>/dev/null | cut -d= -f2)
    ISSUER=$(openssl x509 -subject -noout -in "$CERT" 2>/dev/null | sed 's/subject=//')
    printf "    Cert:       %s\n" "$CERT"
    printf "    Expires:    %s\n" "$EXPIRY"
    printf "    Subject:   %s\n" "$ISSUER"
else
    printf "    ${RED}Certificate not found${RESET}\n"
fi
echo ""

# ── Firewall ──
printf "  ${BOLD}Firewall (UFW)${RESET}\n"
UFW_STATUS=$(sudo ufw status 2>/dev/null | head -1)
printf "    %s\n" "$UFW_STATUS"
sudo ufw status 2>/dev/null | grep -E '443|2222' | while read -r line; do
    printf "    %s\n" "$line"
done
echo ""

# ── Config Paths ──
printf "  ${BOLD}Config Files${RESET}\n"
printf "    Flask app:      /opt/uconsole/webdash/app.py\n"
printf "    Systemd unit:   /etc/systemd/system/uconsole-webdash.service\n"
printf "    Nginx config:   /etc/nginx/sites-available/uconsole-webdash\n"
printf "    SSL cert:       /etc/uconsole/ssl/uconsole.crt\n"
printf "    SSL key:        /etc/uconsole/ssl/uconsole.key\n"
printf "    System config:  /etc/uconsole/uconsole.conf\n"
printf "    User config:    ~/.config/uconsole/config.json\n"
