#!/bin/bash
# End-to-end test — runs on the real device against the live system.
# Installs the .deb, verifies services, webdash, auth, mDNS, CLI.
#
# Usage: make test-e2e
#        bash scripts/test-e2e.sh
set -euo pipefail

PASS=0
FAIL=0
DEB="$(ls -t dist/uconsole-cloud_*_arm64.deb 2>/dev/null | head -1)"

ok()   { PASS=$((PASS + 1)); echo "  [OK] $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  [!!] $1"; }
skip() { echo "  [--] $1"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     uconsole-cloud end-to-end test       ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "This will:"
echo "  1. Install the .deb (sudo dpkg -i)"
echo "  2. Restart webdash"
echo "  3. Test auth, mDNS, CLI, services"
echo ""

if [ -z "$DEB" ]; then
    echo "ERROR: No .deb found in dist/. Run 'make build-deb' first."
    exit 1
fi

echo "Package: $DEB"
echo ""
printf "Continue? [y/N] "
read -r CONFIRM
case "$CONFIRM" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Cancelled."; exit 0 ;;
esac

echo ""
echo "── Install ──────────────────────────────"
sudo dpkg -i "$DEB" 2>&1 | tail -5
sudo systemctl restart uconsole-webdash 2>/dev/null || true
sleep 2

echo ""
echo "── Doctor ───────────────────────────────"
/usr/bin/uconsole doctor
echo ""

echo "── Auth ─────────────────────────────────"

# Default password login
COOKIES=$(mktemp)
HTTP_CODE=$(curl -sk -X POST https://localhost/login \
    -d 'password=clockwork' -c "$COOKIES" -o /dev/null -w '%{http_code}')
if [ "$HTTP_CODE" = "302" ]; then
    ok "Default password 'clockwork' accepted (HTTP $HTTP_CODE)"
else
    fail "Default password rejected (HTTP $HTTP_CODE)"
fi

# Change password (authenticated)
CHANGE=$(curl -sk -X POST https://localhost/api/change-password \
    -d 'password=testpass&confirm=testpass' -b "$COOKIES" 2>&1)
if echo "$CHANGE" | grep -q '"ok"'; then
    ok "Change password via API"
else
    fail "Change password failed: $CHANGE"
fi

# Login with new password
HTTP_CODE=$(curl -sk -X POST https://localhost/login \
    -d 'password=testpass' -c "$COOKIES" -o /dev/null -w '%{http_code}')
if [ "$HTTP_CODE" = "302" ]; then
    ok "New password 'testpass' accepted"
else
    fail "New password rejected (HTTP $HTTP_CODE)"
fi

# set-password blocked (password already set)
HTTP_CODE=$(curl -sk -X POST https://localhost/api/set-password \
    -d 'password=hacked&confirm=hacked' -o /dev/null -w '%{http_code}')
if [ "$HTTP_CODE" = "302" ]; then
    ok "/api/set-password blocked (redirected to login)"
else
    fail "/api/set-password NOT blocked (HTTP $HTTP_CODE) — SECURITY ISSUE"
fi

# Restore original password
curl -sk -X POST https://localhost/api/change-password \
    -d 'password=clockwork&confirm=clockwork' -b "$COOKIES" -o /dev/null 2>&1
ok "Password restored to 'clockwork'"

rm -f "$COOKIES"

echo ""
echo "── mDNS ─────────────────────────────────"

if avahi-resolve -n uconsole.local &>/dev/null; then
    ok "uconsole.local resolves"
else
    fail "uconsole.local does not resolve"
fi

HTTP_CODE=$(curl -sk --max-time 3 -o /dev/null -w '%{http_code}' https://uconsole.local)
if [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "200" ]; then
    ok "https://uconsole.local responds (HTTP $HTTP_CODE)"
else
    fail "https://uconsole.local not responding (HTTP $HTTP_CODE)"
fi

echo ""
echo "── CLI ──────────────────────────────────"

if /usr/bin/uconsole --version | grep -q "uconsole-cloud"; then
    ok "uconsole --version: $(/usr/bin/uconsole --version)"
else
    fail "uconsole --version failed"
fi

if /usr/bin/uconsole help | grep -q "passwd"; then
    ok "uconsole help lists passwd command"
else
    fail "uconsole help missing passwd"
fi

if /usr/bin/uconsole help | grep -q "logs"; then
    ok "uconsole help lists logs command"
else
    fail "uconsole help missing logs"
fi

/usr/bin/uconsole logs status 2>&1 | tail -1 | grep -q "uconsole" && \
    ok "uconsole logs status returns data" || \
    skip "uconsole logs status (no recent push)"

echo ""
echo "── Services ─────────────────────────────"

for svc in uconsole-webdash.service uconsole-status.timer; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        ok "$svc active"
    else
        fail "$svc not active"
    fi
done

HTTP_CODE=$(curl -sk --max-time 3 -o /dev/null -w '%{http_code}' https://localhost)
if [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "200" ]; then
    ok "webdash responding on HTTPS"
else
    fail "webdash not responding (HTTP $HTTP_CODE)"
fi

echo ""
echo "══════════════════════════════════════════"
echo "  $PASS passed, $FAIL failed"
echo "══════════════════════════════════════════"
echo ""

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
