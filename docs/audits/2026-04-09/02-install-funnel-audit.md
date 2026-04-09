# Install Funnel & Test Coverage Audit

*Generated: 2026-04-09*

I now have a comprehensive picture. Here is the full audit report.

---

## Install Funnel Audit Report: uconsole-cloud

### 1. INSTALL.SH (Bootstrap Script)

**File:** `/home/mikevitelli/uconsole-cloud/frontend/public/install.sh`

#### RISKS

**R1. Partial download via `curl | sudo bash` has no integrity check (line 3)**
The usage pattern `curl -s https://uconsole.cloud/install | sudo bash` is inherently dangerous. If the connection drops mid-download, `bash` will execute a truncated script. The `set -euo pipefail` on line 7 helps (it will abort on the first error), but if the truncation happens mid-line (e.g., at a `curl` command), the partial command could be destructive or do something unexpected. There is no checksum verification or `Content-Length` validation.

**R2. No architecture check (line 34)**
The `apt sources.list` hardcodes `arch=arm64`. On an x86_64 machine, `apt-get update` will succeed but `apt-get install -y uconsole-cloud` will fail with "no candidate" -- a confusing error message that doesn't explain WHY. The script should detect the architecture upfront and fail with a clear message.

**R3. GPG key downloaded over HTTPS without fingerprint verification (line 28)**
The GPG key is fetched via `curl -fsSL` and piped through `gpg --dearmor`. If uconsole.cloud were compromised or MITM'd, a malicious key could be installed. The script should verify the key fingerprint after downloading.

**R4. `curl -fsSL` silent failure mode (line 28)**
The `-f` flag makes curl return exit code 22 on HTTP errors, which combined with `set -e` would abort. But the `-s` flag in the usage line (`curl -s ... | sudo bash`) suppresses progress AND errors. If the initial download of install.sh itself fails partially, there is no protection.

#### GAPS

**G1. No `apt-get update` failure handling**
Line 39: `apt-get update -qq` -- if this fails (DNS resolution, network timeout), `set -e` will abort, but the error message from `apt-get` can be opaque. No user-friendly diagnostic.

**G2. No cleanup on failure**
If the script fails after adding the GPG key and sources.list but before installing, the system is left in a partially configured state (stale apt source). There's no trap handler for cleanup.

#### IDEMPOTENCY: Good
- Line 26-29: GPG key uses `--yes` to overwrite. Good.
- Line 33-35: Sources list uses `cat >` (overwrite). Good.
- Running twice is safe.

---

### 2. POSTINST (Package Post-Install Script)

**File:** `/home/mikevitelli/uconsole-cloud/packaging/postinst`

#### RISKS

**R5. `www-data` group assumed to exist (line 52)**
`chgrp www-data /etc/uconsole/ssl/uconsole.key` -- the `www-data` group only exists if nginx (or Apache) is installed. The `control` file declares `nginx (>= 1.18)` as a hard dependency, so this SHOULD be fine. But if a user installs with `--force-depends`, or if nginx is installed without `www-data` (rare edge case), this line would fail. The `2>/dev/null` on the `openssl` line doesn't cover the `chgrp`.

**R6. No `upgrade` case handling (line 21)**
The `case "$1"` only matches `configure`. During a Debian package upgrade, `$1` is still `configure` (with `$2` being the old version), so this is technically OK. But there's no guard against re-doing one-time setup operations on upgrade:
- Line 46-53: SSL cert check is properly idempotent (checks `! -f` first).
- Line 34: Config copy is properly idempotent (checks `! -f` first).
- Line 62-66: Service unit `sed -i` substitution is NOT idempotent -- if upgrading from a version where `UCONSOLE_USER` was already replaced with `mikevitelli`, running `sed -i "s/UCONSOLE_USER/${REAL_USER}/g"` is a no-op (the string no longer exists). This is safe but confusing. However, if the .deb upgrade REPLACES the service files with fresh copies containing `UCONSOLE_USER` again, then the sed runs correctly. This depends on dpkg conffile handling.

**R7. `id -gn "$REAL_USER"` could fail (lines 41, 90)**
If `REAL_USER` is set but the user doesn't have a primary group that matches their username (e.g., in some LDAP setups), `id -gn` may return a different group name. Not a practical risk on a uConsole but a theoretical portability issue.

**R8. labwc keybind injection is fragile (lines 97-105)**
Line 102: `sed -i '/<keyboard>/r '"$SNIPPET" "$LABWC_RC"` -- this inserts the snippet file contents after the first `<keyboard>` line. If `<keyboard>` appears in a comment or if the XML structure changes, this could inject content in the wrong place. Also, the check on line 99 (`grep -q 'C-grave'`) prevents duplicate injection, which is good.

**R9. `get_real_user` with multiple UID >= 1000 users (line 10)**
If the system has multiple non-root users (UID >= 1000), `awk ... {print $1; exit}` picks the FIRST one alphabetically from `getent passwd`. This may not be the intended user. On a uConsole with a single user, this is fine. But if someone adds a second user, the config could be installed into the wrong home directory.

#### GAPS

**G3. No `openssl` availability check (line 46)**
The `control` file doesn't list `openssl` as a dependency. Wait -- checking: the `Dockerfile.test` installs `openssl` explicitly (line 6), and the `control` file Depends line does NOT include openssl. However, looking at `Dockerfile.test` line 6, openssl is installed as a test dependency. The actual package depends should probably include it, since `postinst` calls `openssl req`.

Actually, re-reading: the `control` file does NOT list `openssl` as a dependency. The `postinst` line 46 calls `openssl req`. If openssl is not installed, this fails. The `2>/dev/null` on line 51 only suppresses stderr from the `openssl` command itself, but the `set -e` on line 2 means the whole postinst would abort if openssl returns non-zero. This would leave the package in a half-configured state.

**G4. Service unit files are NOT in conffiles (line 88-90 of build-deb.sh)**
The `conffiles` list includes `/etc/uconsole/uconsole.conf`, nginx config, and avahi config. But NOT the systemd service files. This means on upgrade, dpkg will silently replace the service files with new versions containing `UCONSOLE_USER` placeholder. The `postinst` will then need to re-substitute. This works, but if a user has customized a service file, their changes will be lost without warning.

---

### 3. DOCKERFILE.TEST (Install Test Matrix)

**File:** `/home/mikevitelli/uconsole-cloud/Dockerfile.test`

#### GAPS

**G5. No upgrade test**
All 18 tests validate a fresh install. There's no test for: install v0.1.6, then upgrade to v0.1.7. This would catch regressions in:
- Config file preservation across upgrades
- Service file re-substitution after upgrade
- SSL cert preservation (the `! -f` check)
- Migration of old user-level webdash service

**G6. No uninstall/purge test**
The `prerm` and `postrm` scripts are never tested. A test should verify:
- After `dpkg -r uconsole-cloud`: services stopped, nginx site disabled, CLI symlinks removed, but config preserved
- After `dpkg -P uconsole-cloud`: `/etc/uconsole/` and `/opt/uconsole/` cleaned up

**G7. No multi-user test**
The Docker image creates only user `uconsole` (UID 1000). There's no test for what happens with multiple UID >= 1000 users, testing the `get_real_user` fallback logic.

**G8. dpkg install error suppressed (line 21)**
`RUN dpkg -i /tmp/uconsole-cloud.deb 2>&1; exit 0` -- This always succeeds even if dpkg partially fails (e.g., if postinst has an error). The `; exit 0` masks ANY failure. The intent is to allow dpkg to fail on missing systemd (expected in Docker), but this also hides real packaging errors.

**G9. No test for what happens WITHOUT nginx**
Every test runs in a container with nginx pre-installed. If a user has a minimal system without nginx, the postinst would fail at `nginx -t` (line 71) -- wait, that's guarded with `2>/dev/null || true`. But the hard dependency in `control` means apt won't install without nginx anyway. However, the `dpkg -i` path (manual install) would proceed without nginx.

**G10. No test for file ownership/permissions**
Tests check that files exist and are executable, but not that ownership is correct. The SSL key should be owned by root:www-data with 640 permissions. Service files should be owned by root.

---

### 4. TEST COVERAGE ANALYSIS

#### Frontend Tests (9 test files, vitest)

**File:** `/home/mikevitelli/uconsole-cloud/frontend/src/__tests__/`

**What's tested:**
- Device code flow (generate, confirm, poll, full flow) -- `deviceCode.test.ts`
- Device token CRUD (generate, validate, revoke, regenerate) -- `deviceToken.test.ts`
- Security posture (Sanity config, OAuth scope, error boundary, URL validation, CSP headers, env secrets, API auth guards, Redis key isolation, push endpoint auth) -- `security.test.ts`
- Path/repo/SHA validation regex -- `pathValidation.test.ts`
- Utility functions (parseLines, fmtSize, categoryLabel, parseScriptsManifest) -- `utils.test.ts`
- GitHub API client (error handling, fetch calls) -- `github.test.ts`
- Backup message parsing -- `parseBackupMessage.test.ts`
- APT repo structure integrity -- `aptRepo.test.ts`
- TUI menu structure, script references, themes -- `tuiStructure.test.ts`

**What's NOT tested:**
- **G11. No API route integration tests.** The `security.test.ts` checks that auth guards EXIST in source code (via string matching), but never tests that an unauthenticated request is actually rejected. A route could import `auth()` but fail to use its return value, and these tests would still pass.
- **G12. No push-status.sh integration test.** The device -> cloud data flow is untested. The push endpoint `/api/device/push` has auth tests (source inspection) but no actual HTTP test.
- **G13. No `uconsole setup` flow test.** The CLI setup wizard that generates device codes and writes `status.env` is not tested end-to-end.
- **G14. No Redis integration tests.** All Redis calls are mocked. If the Redis schema changes (e.g., key naming convention), the mocks would still pass.

#### Device Tests (5 test files, pytest)

**File:** `/home/mikevitelli/uconsole-cloud/tests/`

**What's tested:**
- Navigation structure (categories, submenus, bounds, coverage) -- `test_navigation.py`
- `_resolve_cmd` path resolution for every menu script -- `test_resolve_cmd.py`
- `_run_and_capture` subprocess handling (ANSI stripping, timeouts, stderr) -- `test_run_and_capture.py`
- Shell script health (syntax, permissions, shebang, conventions) -- `test_script_health.py`

**What's NOT tested:**
- **G15. No webdash app.py test.** The Flask web dashboard has zero test coverage. No route tests, no auth tests, no SSE endpoint tests.
- **G16. No actual curses rendering test.** Tests mock `stdscr` but never test that `addstr`/`addnstr` calls produce correct output in different terminal sizes.
- **G17. No battery/power script safety test beyond syntax.** These are documented as safety-critical but only get `bash -n` syntax checks.

#### False Positive Risks

**G18. `security.test.ts` tests are pure source-code string checks.**
For example, line 162-165 of `security.test.ts`:
```typescript
const hasAuth = source.includes("auth()") ||
  source.includes("requireAuth()") ||
  source.includes("requireAuthWithToken()");
expect(hasAuth).toBe(true);
```
This would pass even if `auth()` were called but its result discarded, or if it appeared only in a comment. A route that has `// TODO: add auth()` in a comment would pass this test.

**G19. `aptRepo.test.ts` checks filesystem structure, not actual GPG validity.**
The test verifies that `Release.gpg` and `InRelease` files exist, but doesn't verify the signatures are valid or that they match the GPG key. A corrupted signature would pass all tests.

---

### 5. CI/CD WORKFLOWS

#### CI (`ci.yml`)

**File:** `/home/mikevitelli/uconsole-cloud/.github/workflows/ci.yml`

**What it does:**
1. `ci` job: checkout, npm install, shellcheck, pytest, bash syntax, lint, typecheck, vitest, Next.js build
2. `install-test` job: builds .deb via `build-deb.sh`, runs Dockerfile.test in arm64 QEMU

This is solid coverage. Both jobs must pass for PRs.

#### Release (`release.yml`)

**File:** `/home/mikevitelli/uconsole-cloud/.github/workflows/release.yml`

**What it does:** Triggered on `v*` tags. Verifies VERSION matches tag, runs lint+typecheck+tests, builds Next.js, builds .deb, creates GitHub Release with .deb attached.

#### RISKS

**R10. Release workflow does NOT run the install-test (Docker/arm64)**
The `ci.yml` runs the install-test, but `release.yml` does NOT. This means a tag push could produce a broken .deb that was never tested in its release configuration. The CI install-test runs on the branch, not the tag.

**R11. Release workflow does NOT run pytest (device tests)**
Line 40-53 of `release.yml` runs lint, typecheck, and frontend vitest, but NOT `python -m pytest tests/`. Shell script syntax checks are also missing. A release could ship with a broken device script.

**R12. No APT repo update in release workflow**
The release workflow builds the .deb and attaches it to GitHub Releases, but does NOT run `generate-repo.sh` or update the APT repo metadata. The APT repo update happens via `make publish-apt` locally (or via the `/publish` skill). This means the GitHub Release .deb and the APT repo .deb could be out of sync.

**R13. `.deb` is built on ubuntu-latest (x86_64), not arm64**
Line 55 of `release.yml`: `bash packaging/build-deb.sh` runs on `ubuntu-latest`. The `build-deb.sh` script uses `dpkg-deb --build` which is architecture-agnostic (it just packages files). The `control` file declares `arm64`, so the .deb will only install on arm64. This is fine for a pure-script package, but if native binaries were ever added, they'd be x86_64 inside an arm64 .deb.

---

### 6. MISSING TESTS BETWEEN CI AND USER EXPERIENCE

**G20. `install.sh` is shellchecked but never actually executed in CI.**
CI runs `shellcheck frontend/public/install.sh` (syntax/lint) but never simulates `curl | sudo bash`. A test could set `UCONSOLE_URL` to a local server, serve the GPG key and .deb from the Docker container, and run the full install flow.

**G21. No test for the `uconsole` CLI wrapper beyond `--version` and `help`.**
The Dockerfile.test (lines 118-127) tests `uconsole help` and `uconsole --version`. But `uconsole setup`, `uconsole doctor`, `uconsole logs`, `uconsole restore` are untested.

**G22. No test for service enablement flow.**
The postinst deliberately does NOT enable services (line 74: "do NOT enable or start"). The `uconsole setup` wizard presumably enables them. But this flow is never tested.

---

### IMPROVEMENTS (Prioritized)

**P1. Add architecture check to install.sh** (Low effort, high impact)
```bash
# Add after line 18 of install.sh
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
if [ "$ARCH" != "arm64" ] && [ "$ARCH" != "aarch64" ]; then
    echo "ERROR: uconsole-cloud requires arm64. Detected: $ARCH" >&2
    exit 1
fi
```

**P2. Add openssl to package dependencies**
File: `/home/mikevitelli/uconsole-cloud/packaging/control`, line 6 -- add `openssl` to the `Depends:` line.

**P3. Fix Dockerfile.test dpkg error masking**
File: `/home/mikevitelli/uconsole-cloud/Dockerfile.test`, line 21 -- replace `; exit 0` with a more targeted approach:
```dockerfile
RUN dpkg -i /tmp/uconsole-cloud.deb 2>&1 || \
    (echo "dpkg failed (expected in Docker for systemd operations)" && \
     dpkg --configure -a)
```

**P4. Add install-test and pytest to release.yml**
File: `/home/mikevitelli/uconsole-cloud/.github/workflows/release.yml` -- add QEMU setup, .deb build in arm64, and `python -m pytest tests/ -v` steps (mirroring what `ci.yml` does).

**P5. Add upgrade test to Dockerfile.test**
After the current tests, add a second `dpkg -i` of the same .deb (simulates upgrade) and verify idempotency:
```dockerfile
RUN echo "=== TEST: Upgrade idempotency ===" \
    && dpkg -i /tmp/uconsole-cloud.deb 2>&1; exit 0

RUN echo "=== TEST: Config preserved after upgrade ===" \
    && test -f /etc/uconsole/uconsole.conf \
    && test -f /etc/uconsole/ssl/uconsole.crt \
    && grep -q "User=uconsole" /etc/systemd/system/uconsole-webdash.service \
    && echo "PASS"
```

**P6. Add uninstall/purge test to Dockerfile.test**
```dockerfile
RUN echo "=== TEST: Uninstall preserves config ===" \
    && dpkg -r uconsole-cloud \
    && test -f /etc/uconsole/uconsole.conf \
    && ! test -L /usr/bin/uconsole \
    && echo "PASS"
```

**P7. Add file permission test to Dockerfile.test**
```dockerfile
RUN echo "=== TEST: SSL key permissions ===" \
    && stat -c "%a %G" /etc/uconsole/ssl/uconsole.key | grep -q "640 www-data" \
    && echo "PASS"
```

**P8. Add GPG signature validation test to aptRepo.test.ts**
Verify that `Release.gpg` is a valid GPG signature over `Release`, not just that the file exists.

**P9. Add a trap cleanup handler to install.sh**
```bash
cleanup() {
    if [ $? -ne 0 ]; then
        echo "Installation failed. You may need to remove:" >&2
        echo "  sudo rm -f ${APT_LIST} ${GPG_KEY}" >&2
    fi
}
trap cleanup EXIT
```

**P10. Replace source-code string matching tests with actual HTTP tests**
The `security.test.ts` API auth guard checks (lines 148-179) should be supplemented with integration tests that make actual requests to API routes without auth and verify 401 responses.

---

### Summary

| Category | Count | Severity |
|----------|-------|----------|
| RISKS | 13 | R1 (high), R2 (medium), R5 (low), R8 (low), R10 (high), R11 (high), R12 (medium) |
| GAPS | 22 | G3 (high - missing openssl dep), G5 (high - no upgrade test), G8 (high - masked dpkg errors), G11 (medium), G18 (medium - false positive tests) |
| IMPROVEMENTS | 10 | P1-P4 highest priority |

The most critical finding is **R10+R11**: the release workflow skips the Docker install test AND pytest, meaning a tagged release can ship a broken .deb that was never tested in its release form. The second most critical is **G3**: `openssl` is not declared as a dependency but is required by `postinst` -- if a minimal system doesn't have it, the package will fail to configure and be left in a broken state.