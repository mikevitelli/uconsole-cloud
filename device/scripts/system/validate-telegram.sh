#!/bin/bash
# validate-telegram.sh — runtime checks for the Telegram TUI feature.
#
# Unlike tests/test_telegram.py (which runs fast static/unit tests), this
# script validates the live install state on a real device:
#   - Telethon importable from system Python
#   - Credentials file present, well-formed, chmod 600
#   - Session file present and a valid sqlite DB (optional — means logged in)
#   - Bridge can instantiate without a thread crash
#   - telegram.py can be imported via the same path the TUI uses at runtime
#
# Exit codes:
#   0 — all checks pass
#   1 — at least one check failed
#
# Safe to run anytime. Does NOT touch Telegram's network or modify state.
set -u

: "${HOME:?HOME must be set}"

for cmd in python3 stat sed; do
    command -v "$cmd" >/dev/null || { echo "missing required command: $cmd" >&2; exit 2; }
done

LOG=$(mktemp -t val-telegram.XXXXXX) || { echo "mktemp failed" >&2; exit 2; }
trap 'rm -f "$LOG"' EXIT

PASS="\033[1;32m✓\033[0m"
FAIL="\033[1;31m✗\033[0m"
SKIP="\033[1;33m●\033[0m"
failed=0

check() {
    local name="$1"
    shift
    if "$@" >"$LOG" 2>&1; then
        printf "  ${PASS} %s\n" "$name"
    else
        printf "  ${FAIL} %s\n" "$name"
        sed 's/^/      /' "$LOG"
        failed=$((failed + 1))
    fi
}

skip() {
    printf "  ${SKIP} %s\n" "$1"
}

echo "── Telegram TUI validation ──"

# 1. Telethon importable from system Python
check "telethon importable" python3 -c "import telethon; assert telethon.__version__"

# 2. TUI module importable via the same sys.path the TUI uses at runtime
check "tui.telegram importable via /opt/uconsole/lib" python3 -c "
import sys
sys.path.insert(0, '/opt/uconsole/lib')
import tui.telegram
assert hasattr(tui.telegram, 'run_telegram')
assert callable(tui.telegram.run_telegram)
"

# 3. Bridge class can instantiate without starting a thread
check "_TelegramBridge instantiates" python3 -c "
import sys
sys.path.insert(0, '/opt/uconsole/lib')
from tui.telegram import _TelegramBridge
b = _TelegramBridge(1, 'h')
state, err, me = b.state()
assert state == 'init', f'unexpected initial state: {state}'
b.close()
"

# 4. Credentials file
CRED_FILE="$HOME/.config/uconsole/telegram.json"
if [ -f "$CRED_FILE" ]; then
    if python3 - "$CRED_FILE" >"$LOG" 2>&1 <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
assert 'api_id' in d and isinstance(d['api_id'], int), 'api_id missing or not int'
assert 'api_hash' in d and isinstance(d['api_hash'], str) and len(d['api_hash']) == 32, 'api_hash missing or wrong length'
PY
    then
        printf "  ${PASS} credentials file is valid JSON\n"
    else
        printf "  ${FAIL} credentials file is valid JSON\n"
        sed 's/^/      /' "$LOG"
        failed=$((failed + 1))
    fi
    MODE=$(stat -c "%a" "$CRED_FILE" 2>/dev/null || stat -f "%A" "$CRED_FILE" 2>/dev/null || true)
    if [ -z "$MODE" ]; then
        printf "  ${FAIL} cannot stat credentials file\n"
        failed=$((failed + 1))
    elif [ "$MODE" = "600" ]; then
        printf "  ${PASS} credentials file chmod 600\n"
    else
        printf "  ${FAIL} credentials file mode is %s (should be 600)\n" "$MODE"
        failed=$((failed + 1))
    fi
else
    skip "credentials file not yet created (run TUI → Telegram to set up)"
fi

# 5. Session file (optional — means user has logged in)
SESSION_FILE="$HOME/.config/uconsole/telegram.session"
if [ -f "$SESSION_FILE" ]; then
    if python3 - "$SESSION_FILE" >"$LOG" 2>&1 <<'PY'
import sqlite3, sys
c = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True, timeout=1)
cur = c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = {r[0] for r in cur.fetchall()}
c.close()
# Telethon creates at least 'sessions' and 'entities' tables
assert 'sessions' in tables or 'entities' in tables, f'no telethon tables in {tables}'
PY
    then
        printf "  ${PASS} session file is a valid sqlite DB\n"
    else
        printf "  ${FAIL} session file is a valid sqlite DB\n"
        sed 's/^/      /' "$LOG"
        failed=$((failed + 1))
    fi
else
    skip "session file not yet created (log in via TUI → Telegram to create)"
fi

# 6. Menu wiring check — the _telegram handler is actually registered
check "_telegram registered in framework.py" python3 -c "
with open('/opt/uconsole/lib/tui/framework.py') as f:
    src = f.read()
assert '\"_telegram\"' in src or \"'_telegram'\" in src, '_telegram not in framework.py'
assert 'run_telegram' in src, 'run_telegram not imported in framework.py'
"

echo
if [ $failed -eq 0 ]; then
    printf "${PASS} All checks passed\n"
    exit 0
else
    printf "${FAIL} %d check(s) failed\n" "$failed"
    exit 1
fi
