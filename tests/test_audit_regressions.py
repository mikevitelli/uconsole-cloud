"""Regression tests for security fixes from the 2026-03-24 audit and the
2026-05-09 dev-hardening pass.

These are pattern/source-level tests, not behavioral. The intent is a CI
safety net: if someone reverts a fix, the test fails immediately with a
named pointer to the audit finding it covers. They certify that the
mitigation is *present*, not that the mitigation is correct under every
input — the actual proofs live in the audit docs.
"""

from __future__ import annotations

import os
import re

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(rel: str) -> str:
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


# ── 2026-03-24 audit: webdash.py XSS + security headers + SSE POST ────────


def test_webdash_security_headers_handler_present():
    """add_security_headers must set X-Frame-Options, CSP, X-Content-Type-Options,
    Referrer-Policy. Audit fix; CLAUDE.md "Security Notes" line item."""
    src = _read("device/webdash/app.py")
    handler = re.search(
        r"@app\.after_request\s+def add_security_headers\([^)]*\):.*?return response",
        src,
        re.DOTALL,
    )
    assert handler, "add_security_headers handler missing"
    body = handler.group(0)
    assert "X-Frame-Options" in body, "X-Frame-Options not set"
    assert "Content-Security-Policy" in body, "CSP not set"
    assert "X-Content-Type-Options" in body, "X-Content-Type-Options not set"
    assert "Referrer-Policy" in body, "Referrer-Policy not set"


def test_webdash_stream_endpoint_is_post_only():
    """/api/stream/<script> must be POST. GET state-changing endpoints
    were the audit's SSE POST-only callout — and a regression in the
    state of dev pre-2026-05-09."""
    src = _read("device/webdash/app.py")
    m = re.search(
        r"@app\.route\(\s*['\"]/api/stream/<script>['\"]\s*,\s*methods=\[([^]]*)\]",
        src,
    )
    assert m, "/api/stream/<script> route declaration not found"
    methods = m.group(1)
    assert "'POST'" in methods or '"POST"' in methods, (
        "/api/stream must include POST"
    )
    assert "'GET'" not in methods and '"GET"' not in methods, (
        "/api/stream must NOT include GET — audit specified POST-only"
    )


def test_webdash_no_innerHTML_with_user_data_in_dashboard_js():
    """Dashboard JS must not build click handlers via string concatenation
    (`onclick="selectWifi(...)"`). Regression of the SSID DOM-XSS fix."""
    src = _read("device/webdash/static/js/dashboard.js")
    forbidden = (
        "onclick=\"selectWifi",
        "onclick='selectWifi",
        "onclick=\"connectWifi",
        "onclick='connectWifi",
    )
    for pat in forbidden:
        assert pat not in src, f"{pat!r} re-introduced — SSID XSS regression"


def test_webdash_static_and_template_dashboard_js_in_sync():
    """Two byte-identical copies of dashboard.js exist; if they drift, an
    audit fix could land in one and miss the other."""
    a = _read("device/webdash/static/js/dashboard.js")
    b = _read("device/webdash/templates/js/dashboard.js")
    assert a == b, (
        "static/js/dashboard.js and templates/js/dashboard.js drifted — "
        "both must be updated in lockstep until consolidated"
    )


# ── 2026-05-09 dev-hardening: X-Real-IP pinning + auth rate limit ──────────


def test_webdash_x_real_ip_only_via_client_ip_helper():
    """Direct `request.headers.get('X-Real-IP', request.remote_addr)` was
    spoofable by any client. The fix introduces _client_ip() that only
    honors X-Real-IP from loopback. No other call site may bypass it."""
    src = _read("device/webdash/app.py")
    # _client_ip helper is the one allowed reader of X-Real-IP.
    assert "def _client_ip" in src, "_client_ip helper missing"
    # Outside that helper, no `request.headers.get('X-Real-IP'...)` direct calls.
    direct_reads = re.findall(r"request\.headers\.get\(\s*['\"]X-Real-IP['\"]", src)
    # Exactly one reference is allowed: the one inside _client_ip itself.
    assert len(direct_reads) == 1, (
        f"X-Real-IP read in {len(direct_reads)} places — must only be in _client_ip"
    )


def test_webdash_login_path_is_rate_limited():
    """/login and /api/set-password must be rate-limited per IP. Without it
    a 4-character password floor was trivially brute-forceable from LAN."""
    src = _read("device/webdash/app.py")
    assert "_check_auth_rate_limit" in src, "_check_auth_rate_limit missing"
    assert "_AUTH_PATHS" in src, "_AUTH_PATHS frozenset missing"
    assert "_PASSWORD_MIN_LEN" in src, "password min-length constant missing"
    # Floor must not regress to anything below 8.
    m = re.search(r"_PASSWORD_MIN_LEN\s*=\s*(\d+)", src)
    assert m, "_PASSWORD_MIN_LEN value not parseable"
    assert int(m.group(1)) >= 8, (
        f"password floor regressed to {m.group(1)} — was raised from 4 to 10"
    )


# ── 2026-03-24 audit: wifi.sh + wifi-fallback.sh lockfile location ─────────


def test_wifi_sh_lock_not_in_world_writable_tmp():
    """wifi.sh lockfile must live in $XDG_RUNTIME_DIR or /run, never /tmp.
    Audit fix for the world-writable-lock TOCTOU."""
    src = _read("device/scripts/network/wifi.sh")
    # Find the LOCK / LOCKFILE assignment.
    assert "XDG_RUNTIME_DIR" in src or "/run/" in src, (
        "wifi.sh must use XDG_RUNTIME_DIR or /run for its lock"
    )
    # No bare /tmp/ paths used as lockfiles.
    bad = re.search(r'(?:LOCK[A-Z_]*|lock[a-z_]*)\s*=\s*["\']?/tmp/', src)
    assert not bad, "wifi.sh has a /tmp lockfile path — audit regression"


def test_wifi_fallback_lock_not_in_world_writable_tmp():
    """wifi-fallback.sh: same lockfile-location requirement."""
    src = _read("device/scripts/network/wifi-fallback.sh")
    assert "XDG_RUNTIME_DIR" in src or "/run/" in src, (
        "wifi-fallback.sh must use XDG_RUNTIME_DIR or /run for its lock"
    )
    bad = re.search(r'(?:LOCK[A-Z_]*|lock[a-z_]*)\s*=\s*["\']?/tmp/', src)
    assert not bad, "wifi-fallback.sh has a /tmp lockfile path — audit regression"


# ── 2026-03-24 audit: console.py / TUI argv-form subprocess ────────────────


def test_tui_ssh_uses_argv_subprocess():
    """SSH bookmark launcher must invoke ssh via argv list, not os.system /
    shell=True / f-string concat. Audit fix for SSH hostname injection."""
    src = _read("device/lib/tui/tools.py")
    assert 'subprocess.run(["ssh"' in src, (
        "ssh bookmark launcher no longer uses subprocess.run with argv list"
    )
    # Make sure no ssh f-string snuck in.
    assert 'os.system(f"ssh' not in src, "ssh shell-injection via f-string"
    assert 'os.system("ssh' not in src, "ssh via os.system"
    assert 'subprocess.run(f"ssh' not in src, "ssh via shell-form subprocess"


def test_tui_bluetooth_uses_argv_subprocess():
    """Bluetooth pairing must invoke bluetoothctl via argv list. Audit
    fix for MAC injection (paired MAC came from bluetoothctl output)."""
    src = _read("device/lib/tui/network.py")
    assert 'subprocess.run(["bluetoothctl"' in src, (
        "bluetooth control no longer uses argv-form subprocess"
    )
    assert 'os.system(f"bluetoothctl' not in src
    assert 'subprocess.run(f"bluetoothctl' not in src


def test_tui_process_kill_validates_pid():
    """The process-killer must validate PID is numeric + within kernel
    pid_max. Audit fix for kill-arbitrary-string injection."""
    src = _read("device/lib/tui/processes.py")
    assert "pid.isdigit()" in src, "PID isdigit check missing"
    # Range check: 2 <= pid <= 4194304 (typical pid_max). Look for the
    # presence of the range gate, not the exact literal.
    range_check = re.search(r"int\(pid\)\s*<=\s*\d{6,7}", src)
    assert range_check, "PID upper-bound check missing"
    assert "os.kill(int(pid)" in src, "kill must use os.kill with int conversion"


# ── 2026-05-09 dev-hardening: cloud wifi.ip href validation ───────────────


def test_cloud_local_dashboard_url_helper_exists():
    """The cloud must validate device-pushed wifi.ip before interpolating
    into href. Helper must reject non-IP values."""
    src = _read("frontend/src/lib/network.ts")
    assert "buildLocalDashboardUrl" in src, "buildLocalDashboardUrl helper missing"
    assert "isValidIp" in src, "isValidIp helper missing"
    # The helper must reject by default (return null on non-IP).
    assert "return null" in src


def test_cloud_local_mode_shell_uses_validator():
    """LocalModeShell.tsx must build the webdashUrl via the validator,
    not via raw `https://${...}` interpolation."""
    src = _read("frontend/src/components/dashboard/LocalModeShell.tsx")
    assert "buildLocalDashboardUrl" in src, (
        "LocalModeShell.tsx must call buildLocalDashboardUrl"
    )
    # No raw `https://${deviceLocalIp}` interpolation.
    assert "`https://${deviceLocalIp}`" not in src, (
        "raw https://${deviceLocalIp} interpolation regression"
    )


def test_cloud_device_online_uses_validator():
    """DeviceOnline.tsx Local Shell Hub link must go through the validator."""
    src = _read("frontend/src/components/dashboard/DeviceOnline.tsx")
    assert "buildLocalDashboardUrl" in src, (
        "DeviceOnline.tsx must call buildLocalDashboardUrl"
    )
    assert "`https://${wifi.ip}`" not in src, (
        "raw https://${wifi.ip} interpolation regression"
    )


# ── 2026-05-09 dev-hardening: /api/device/push gating ─────────────────────


def test_device_push_route_has_rate_limit_and_size_cap():
    """The push endpoint must have per-token rate limit + body size cap +
    shape check. Without these, a leaked Bearer token is a DoS."""
    src = _read("frontend/src/app/api/device/push/route.ts")
    assert "checkRateLimit" in src, "rate-limit import missing"
    assert "MAX_BODY_BYTES" in src, "body size cap missing"
    assert "isValidTelemetry" in src, "shape validator missing"
    # Status 413 on oversize, 429 on rate limit — present in the file.
    assert "413" in src, "413 Payload Too Large response missing"
    assert "429" in src, "429 Too Many Requests response missing"


# ── 2026-05-09 dev-hardening: TUI CONFIG_FILE under XDG ──────────────────


def test_tui_config_file_under_xdg_config_home():
    """CONFIG_FILE was under SCRIPT_DIR (root-owned post-deploy) — must
    now resolve under $XDG_CONFIG_HOME / ~/.config/uconsole/."""
    src = _read("device/lib/tui/framework.py")
    assert "XDG_CONFIG_HOME" in src, "XDG_CONFIG_HOME branch missing"
    assert "_migrate_legacy_config" in src, "legacy migration helper missing"
    # CONFIG_FILE must NOT be just SCRIPT_DIR + .console-config.json.
    bad = re.search(
        r"CONFIG_FILE\s*=\s*os\.path\.join\(\s*SCRIPT_DIR,\s*['\"]\.console-config\.json",
        src,
    )
    assert not bad, "CONFIG_FILE re-pinned to SCRIPT_DIR — regression"


# ── 2026-05-09 dev-hardening: restore.sh local-outside-function ──────────


def test_restore_sh_no_local_outside_function():
    """restore.sh runs under `set -e`; `local` outside a function aborts
    the script mid-run. The fix dropped the bare `local` declarations."""
    src = _read("device/scripts/system/restore.sh")
    # Find every `local` occurrence and verify each is inside a function.
    # Simple heuristic: walk lines, track depth via `name() {` / `}` braces.
    in_fn = 0
    bad_lines = []
    for ln_num, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*\(\s*\)\s*\{", stripped):
            in_fn += 1
        elif stripped == "}" and in_fn > 0:
            in_fn -= 1
        if re.match(r"^\s*local\b", line) and in_fn == 0:
            bad_lines.append(ln_num)
    assert not bad_lines, (
        f"restore.sh: `local` declared outside any function on lines "
        f"{bad_lines} — would abort with set -e"
    )


# ── 2026-05-09 dev-hardening: sudoers files removed from source ──────────


def test_no_leaked_sudoers_files_in_source():
    """device/scripts/system/etc/sudoers.d/ must not contain a
    NOPASSWD: ALL grant or hardcoded operator usernames."""
    sudoers = os.path.join(REPO, "device/scripts/system/etc/sudoers.d")
    if not os.path.isdir(sudoers):
        pytest.skip("sudoers.d directory not present (clean)")
    for fname in os.listdir(sudoers):
        path = os.path.join(sudoers, fname)
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            body = f.read()
        assert "NOPASSWD: ALL" not in body, (
            f"{fname}: NOPASSWD: ALL grant must not ship in source"
        )
        assert "mikevitelli " not in body, (
            f"{fname}: hardcoded operator username 'mikevitelli' present"
        )
