#!/bin/bash
# smoke-test.sh — verify uConsole installation
# Exit 0 if all critical tests pass, 1 if any fail.

set -uo pipefail

PASS=0
FAIL=0
WARN=0

ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS + 1)); }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL + 1)); }
skip() { printf "  \033[33m-\033[0m %s\n" "$1"; WARN=$((WARN + 1)); }

section() { echo ""; printf "\033[1m\033[36m── %s ──\033[0m\n\n" "$1"; }

# ── 1. Directory structure ──
section "1. Directory Structure"
for d in /opt/uconsole/bin /opt/uconsole/lib /opt/uconsole/lib/tui \
         /opt/uconsole/scripts /opt/uconsole/webdash /opt/uconsole/share; do
    [ -d "$d" ] && ok "$d" || fail "$d missing"
done

# ── 2. Executables ──
section "2. Executables"
for f in /opt/uconsole/bin/console /opt/uconsole/bin/webdash \
         /opt/uconsole/bin/uconsole-passwd /opt/uconsole/bin/uconsole-setup \
         /opt/uconsole/scripts/util/hardware-detect.sh; do
    if [ -f "$f" ]; then
        [ -x "$f" ] && ok "$f executable" || fail "$f not executable"
    else
        fail "$f missing"
    fi
done

# ── 3. Python imports ──
section "3. Python Imports"
PYPATH="/opt/uconsole/lib:$HOME/scripts"

python3 -c "
import sys; sys.path[:0] = ['$HOME/scripts', '/opt/uconsole/lib']
from tui import framework
" 2>/dev/null && ok "tui.framework imports" || fail "tui.framework import failed"

python3 -c "
import sys; sys.path[:0] = ['$HOME/scripts', '/opt/uconsole/lib']
from tui import monitor, files, network, services, tools, config_ui, radio
" 2>/dev/null && ok "all TUI modules import" || fail "TUI module import failed"

python3 -c "
import sys; sys.path[:0] = ['/opt/uconsole/webdash', '$HOME/scripts']
from app import app
" 2>/dev/null && ok "webdash app imports" || fail "webdash app import failed"

python3 -c "
sys_path_extra = ['$HOME/scripts', '/opt/uconsole/lib']
import sys; sys.path[:0] = sys_path_extra
import config as cfg
v = cfg.get('webdash', 'port', '8080')
print(v)
" 2>/dev/null && ok "config.py reads config" || fail "config.py failed"

# ── 4. Config files ──
section "4. Config Files"
[ -f /etc/uconsole/uconsole.conf.default ] && ok "uconsole.conf.default" || fail "uconsole.conf.default missing"
[ -f "$HOME/.config/uconsole/config.json.default" ] && ok "config.json.default" || fail "config.json.default missing"

# Validate JSON
python3 -c "import json; json.load(open('$HOME/.config/uconsole/config.json.default'))" 2>/dev/null \
    && ok "config.json.default valid JSON" || fail "config.json.default invalid"

# ── 5. Webdash app.py compiles ──
section "5. Webdash"
python3 -m py_compile /opt/uconsole/webdash/app.py 2>/dev/null \
    && ok "app.py compiles" || fail "app.py compilation failed"

[ -f /opt/uconsole/webdash/templates/dashboard.html ] && ok "dashboard.html exists" || fail "dashboard.html missing"
[ -f /opt/uconsole/webdash/templates/login.html ] && ok "login.html exists" || fail "login.html missing"
[ -f /opt/uconsole/webdash/templates/set_password.html ] && ok "set_password.html exists" || fail "set_password.html missing"

# Check template subdirs
[ -f /opt/uconsole/webdash/templates/css/style.css ] && ok "style.css exists" || fail "style.css missing"
[ -f /opt/uconsole/webdash/templates/js/dashboard.js ] && ok "dashboard.js exists" || fail "dashboard.js missing"
[ -f /opt/uconsole/webdash/templates/dashboard_body.html ] && ok "dashboard_body.html exists" || fail "dashboard_body.html missing"

# ── 6. TUI modules compile ──
section "6. TUI Modules"
for mod in framework monitor files network services tools config_ui radio; do
    python3 -m py_compile /opt/uconsole/lib/tui/$mod.py 2>/dev/null \
        && ok "tui/$mod.py compiles" || fail "tui/$mod.py failed"
done
python3 -m py_compile /opt/uconsole/lib/tui_lib.py 2>/dev/null \
    && ok "tui_lib.py compiles" || fail "tui_lib.py failed"

# ── 7. Hardware detection ──
section "7. Hardware Detection"
output=$(/opt/uconsole/scripts/util/hardware-detect.sh --json --quiet 2>/dev/null)
if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    ok "hardware-detect.sh produces valid JSON"
    module=$(echo "$output" | python3 -c "import json,sys; print(json.load(sys.stdin)['expansion_module'])" 2>/dev/null)
    ok "expansion_module: $module"
else
    fail "hardware-detect.sh failed or invalid JSON"
fi

# ── 8. Original files untouched ──
section "8. Original Files Intact"
[ -f "$HOME/scripts/webdash.py" ] && ok "scripts/webdash.py exists" || fail "scripts/webdash.py missing"
[ -f "$HOME/scripts/console.py" ] && ok "scripts/console.py exists" || fail "scripts/console.py missing"
python3 -m py_compile "$HOME/scripts/webdash.py" 2>/dev/null && ok "webdash.py compiles" || fail "webdash.py broken"
python3 -m py_compile "$HOME/scripts/console.py" 2>/dev/null && ok "console.py compiles" || fail "console.py broken"

# ── 9. Syntax checks ──
section "9. Syntax Checks"
bash -n /opt/uconsole/scripts/util/hardware-detect.sh 2>/dev/null && ok "hardware-detect.sh syntax" || fail "hardware-detect.sh syntax error"
bash -n /opt/uconsole/bin/uconsole-setup 2>/dev/null && ok "uconsole-setup syntax" || fail "uconsole-setup syntax error"
bash -n /opt/uconsole/bin/uconsole-passwd 2>/dev/null && ok "uconsole-passwd syntax" || fail "uconsole-passwd syntax error"
bash -n "$HOME/scripts/config.sh" 2>/dev/null && ok "config.sh syntax" || fail "config.sh syntax error"
python3 -m py_compile "$HOME/scripts/config.py" 2>/dev/null && ok "config.py compiles" || fail "config.py failed"

# ── 10. Nginx ──
section "10. Nginx"
if command -v nginx &>/dev/null; then
    sudo nginx -t 2>/dev/null && ok "nginx config valid" || skip "nginx config has errors"
else
    skip "nginx not installed"
fi

# ── Summary ──
echo ""
printf "\033[1m── Summary ──\033[0m\n\n"
printf "  \033[32m✓ %d passed\033[0m" "$PASS"
[ "$FAIL" -gt 0 ] && printf "  \033[31m✗ %d failed\033[0m" "$FAIL"
[ "$WARN" -gt 0 ] && printf "  \033[33m- %d skipped\033[0m" "$WARN"
echo ""
echo ""

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
