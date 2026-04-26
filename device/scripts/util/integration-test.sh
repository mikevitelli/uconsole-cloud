#!/bin/bash
# integration-test.sh — verify all package scripts can resolve dependencies
# Tests that every script can source lib.sh, find sibling scripts, and
# that webdash ALLOWED_SCRIPTS paths resolve correctly.
#
# Usage: bash integration-test.sh [--fix]
#   --fix: create missing lib.sh symlinks automatically

set -uo pipefail

PASS=0
FAIL=0
FIX_MODE=false
[ "${1:-}" = "--fix" ] && FIX_MODE=true

ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS + 1)); }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL + 1)); }
section() { echo ""; printf "\033[1m\033[36m── %s ──\033[0m\n\n" "$1"; }

PKG_BASE="/opt/uconsole"
SCRIPTS="$PKG_BASE/scripts"
LIB="$PKG_BASE/lib/lib.sh"

# ── 1. lib.sh exists ──
section "1. Shared Library"
[ -f "$LIB" ] && ok "lib.sh exists at $LIB" || fail "lib.sh missing at $LIB"

# ── 2. lib.sh symlinks in every script subdir ──
section "2. lib.sh Symlinks"
for sub in system power network radio util; do
    dir="$SCRIPTS/$sub"
    [ -d "$dir" ] || continue
    link="$dir/lib.sh"
    if [ -L "$link" ] || [ -f "$link" ]; then
        # verify it actually resolves
        if bash -c "source '$link' 2>/dev/null && type ok &>/dev/null"; then
            ok "$sub/lib.sh resolves"
        else
            fail "$sub/lib.sh exists but doesn't source correctly"
        fi
    else
        fail "$sub/lib.sh missing"
        if [ "$FIX_MODE" = true ]; then
            sudo ln -sf "$LIB" "$link" && printf "       \033[33m→ fixed\033[0m\n"
        fi
    fi
done

# ── 3. Every .sh script can source lib.sh ──
section "3. Script Source Check"
while IFS= read -r script; do
    if grep -q 'source.*lib\.sh' "$script" 2>/dev/null; then
        dir=$(dirname "$script")
        name=$(basename "$script")
        if [ -f "$dir/lib.sh" ] || [ -L "$dir/lib.sh" ]; then
            ok "$name sources lib.sh"
        else
            fail "$name needs lib.sh but $dir/lib.sh missing"
            if [ "$FIX_MODE" = true ]; then
                sudo ln -sf "$LIB" "$dir/lib.sh" && printf "       \033[33m→ fixed\033[0m\n"
            fi
        fi
    fi
done < <(find "$SCRIPTS" -name "*.sh" -type f 2>/dev/null)

# ── 4. Cross-script references resolve ──
section "4. Cross-Script References"
while IFS= read -r script; do
    dir=$(dirname "$script")
    name=$(basename "$script")
    # Find references like $SCRIPT_DIR/something.sh or $(dirname "$0")/something.sh
    while IFS= read -r ref; do
        ref_name=$(echo "$ref" | grep -oP '[a-zA-Z0-9_-]+\.sh' | tail -1)
        [ -z "$ref_name" ] && continue
        [ "$ref_name" = "lib.sh" ] && continue
        if [ -f "$dir/$ref_name" ]; then
            ok "$name → $ref_name (same dir)"
        elif [ -f "$SCRIPTS/$ref_name" ]; then
            ok "$name → $ref_name (scripts root)"
        else
            fail "$name references $ref_name but not found in $dir/"
        fi
    done < <(grep -n 'SCRIPT_DIR.*\.sh\|dirname.*\.sh' "$script" 2>/dev/null | grep -v lib.sh | grep -v BASH_SOURCE)
done < <(find "$SCRIPTS" -name "*.sh" -type f 2>/dev/null)

# ── 5. Webdash script resolution ──
section "5. Webdash Script Paths"
if [ -f "$PKG_BASE/webdash/app.py" ]; then
    # Extract all _s('xxx.sh') calls
    while IFS= read -r script_name; do
        found=false
        for search_dir in "$SCRIPTS"/system "$SCRIPTS"/power "$SCRIPTS"/network "$SCRIPTS"/radio "$SCRIPTS"/util "$SCRIPTS" "$HOME/scripts"; do
            if [ -f "$search_dir/$script_name" ]; then
                found=true
                break
            fi
        done
        if [ "$found" = true ]; then
            ok "webdash → $script_name"
        else
            fail "webdash → $script_name NOT FOUND"
        fi
    done < <(grep -oP "_s\('([^']+)'\)" "$PKG_BASE/webdash/app.py" | grep -oP "'[^']+'" | tr -d "'")
else
    fail "app.py not found"
fi

# ── 6. Python imports ──
section "6. Python Imports"
python3 -c "
import sys
sys.path[:0] = ['$PKG_BASE/lib', '$HOME/scripts']
from tui.framework import entry, _load_handlers
handlers = _load_handlers()
print(f'  OK: {len(handlers)} feature handlers loaded')
" 2>&1 && PASS=$((PASS + 1)) || { echo "  FAIL: TUI import chain broken"; FAIL=$((FAIL + 1)); }

python3 -c "
import sys
sys.path[:0] = ['$PKG_BASE/webdash', '$PKG_BASE/lib', '$HOME/scripts']
from app import app
print(f'  OK: webdash app imports')
" 2>&1 && PASS=$((PASS + 1)) || { echo "  FAIL: webdash import broken"; FAIL=$((FAIL + 1)); }

# ── Summary ──
echo ""
printf "\033[1m── Summary ──\033[0m\n\n"
printf "  \033[32m✓ %d passed\033[0m" "$PASS"
[ "$FAIL" -gt 0 ] && printf "  \033[31m✗ %d failed\033[0m" "$FAIL"
echo ""
echo ""
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
