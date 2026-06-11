# uconsole-cloud v0.3.1 Release-Gate Audit

*Synthesis report — 2026-06-10. Gates the v0.3.1 publish (VERSION file: 0.3.0 → 0.3.1).*
*Scope: committed dev HEAD a02ea67 (device/.deb), committed main HEAD ee130eb (frontend/Vercel), plus an uncommitted WIP audit. Every finding below carries concrete file:line evidence and has been independently adversarially verified.*

---

## VERDICT: NO-GO

**Do not publish v0.3.1 as it stands.** The release exists to retire the battery/VOFF stack (commit a02ea67), and that retirement is **incomplete on the upgrade path in exactly the way that defeats the commit's own purpose**: opted-in v0.3.0 devices keep executing the forced bus-0 i2cset + 2.9V VOFF write from the initrd on every boot, while the same upgrade deletes the only tool that could remove it and ships docs that still tell users to run that deleted tool. Two telemetry/security regressions in the cloud-link plumbing also ship in this cut. None of these are theoretical — each is verified against the actual code.

### Blocking fixes (must clear before tagging v0.3.1)

| # | Sev | ⚠ | Finding | File:line | Fix |
|---|-----|---|---------|-----------|-----|
| B1 | high | ⚠ SAFETY | Upgrade leaves fix-battery-boot **initramfs hook + premount + udev VOFF rule** installed; `update-initramfs` re-bakes the forced `i2cset -f -y 0 0x34 0x31 0x03` (2.9V VOFF) into every future kernel. postinst only `systemctl disable`s the units; postrm purge doesn't touch them either. The only removal tool (`fix-battery-boot.sh remove`) is deleted by the same commit. *(Same root issue surfaced by both the release-a02ea67 and install-upgrade dimensions.)* | `packaging/postinst:139-150` (no initramfs/udev cleanup); installer at `a02ea67^:device/scripts/power/fix-battery-boot.sh:86-114` | M — **manual review only, do not auto-fix.** postinst must `rm` the three /etc payload files + the orphaned unit file and run a guarded `update-initramfs -u`. |
| B2 | high | | Packaged **push-status.sh hardcodes `${HOME}/.config/uconsole/status.env`** and `exit 1`s if absent, but package-mode linking writes only `/etc/uconsole/status.env`. Fresh .deb installs can **never push telemetry** (`uconsole push`, cmd_link's first push, every timer run all fail). Only standalone-migrated devices survive — which is why this device never noticed. | `device/scripts/system/push-status.sh:13-17` | S — read `${ENV_FILE:-...}` with an /etc fallback (or honor the unit's `EnvironmentFile`). |
| B3 | high | | **`frontend/public/scripts/push-status.sh:14` still does `source "$ENV_FILE"`** — the pre-hardening RCE pattern the device copy explicitly removed. Served live via `/api/scripts/push-status.sh`; standalone `uconsole update` re-downloads the un-hardened copy. A fix recorded as closed in v0.2.2 is still being distributed from the cloud endpoint. | `frontend/public/scripts/push-status.sh:14` | S — port the device copy's `env_value()` parser. |
| B4 | medium | ⚠ SAFETY | **uconsole-setup still prompts for and saves `power.low_battery_shutdown` (3.05V)** — a02ea67 deleted every consumer (low-battery-shutdown.service / battery-safety.sh). Users are told a low-battery auto-shutdown protects their pack; **nothing implements it.** Safety-expectation mismatch shipping in this release. | `device/bin/uconsole-setup:204-213` | S — **manual review only, do not auto-fix.** Remove the prompt or restore a consumer. |
| B5 | medium | ⚠ SAFETY | **docs/TROUBLESHOOTING.md still tells users to run the deleted `fix-battery-boot.sh`** (install/status/revert) and a removed TUI menu path. This is the exact doc a user with a battery boot failure follows; every command now points at a nonexistent script. | `docs/TROUBLESHOOTING.md:122,128,131` | S — rewrite to the kept `fix-voltage-cutoff.sh` path; add manual initramfs-cleanup note until B1 lands. |

**Pre-tag hygiene gate (not a hard publish blocker, but must be resolved at commit time):** the uncommitted WIP cellular/camera feature spans 6 files — `framework.py`/`launcher.py` menu edits depend on four **untracked** files (`device/lib/tui/{camera,cellular_signal,cellular_map}.py`, `device/scripts/network/4g.sh`). They must be `git add`-ed atomically (and the 4g.sh ship-vs-private decision made — it hardcodes T-Mobile config) or the WIP reverted before tagging. `tests/test_tui_integrity.py` would catch a partial commit. The build packages the working tree, so a .deb built now ships the files regardless; the real risk is repo/.deb divergence on a future clean-clone rebuild. *(Verifier downgraded this to low / "not release-blocking"; listed here as a release-discipline item.)*

Also note: **main (ee130eb) is unpushed.** Pushing main deploys Vercel prod and is what delivers the frontend docs-page fix; the frontend `source`-pattern regression (B3) and the cross-user cache/token issues (R1–R3) all live on that same main and reach prod only on push.

---

## Ranked findings

Ranked by severity, then by release relevance. ⚠ SAFETY = battery/power/PMIC code — **report only, manual review, never auto-fix.**

### Release-blocking (verified)

| Rank | Sev | Dim | File:line | Evidence | Fix |
|------|-----|-----|-----------|----------|-----|
| 1 | high ⚠ | release-a02ea67 / install-upgrade | `packaging/postinst:139-150` | Retire block only `systemctl disable --now`s the 5 units. The runtime-installed `/etc/initramfs-tools/hooks/axp-voff` + `scripts/init-premount/axp-voff` (`i2cset -f -y 0 0x34 0x31 0x03`) and `/etc/udev/rules.d/99-uconsole-battery.rules` (`ATTR{voltage_min}="2900000"`) are never removed and no `update-initramfs` is run; the removal tool `fix-battery-boot.sh` is deleted in the same commit; purge leaves them too. | M |
| 2 | high | tui-cli | `device/scripts/system/push-status.sh:13-17` | `ENV_FILE="${HOME}/.config/uconsole/status.env"` then `[ ! -f ] && exit 1`; package linking writes only `/etc/uconsole/status.env`. Fresh installs can never push telemetry. | S |
| 3 | high | dead-code | `frontend/public/scripts/push-status.sh:14` | `source "$ENV_FILE"` — pre-hardening RCE pattern; live-served, re-downloaded by `uconsole update`; documented as closed in v0.2.2. | S |
| 4 | high | tui-cli / roadmap-diff | `device/bin/uconsole-setup:307` | Wizard Step 5 polls `GET ${API_URL}/api/device/claim` — **no such route exists** (only code, code/confirm, poll, push, status). Locally generated `secrets.token_hex(3)` code never registered server-side. Every "Link to uconsole.cloud?" → 5-min timeout. Pre-existing, not a v0.3.1 regression → **not blocking**, but a dead promise in the primary install funnel. | M |
| 5 | medium ⚠ | dead-code | `device/bin/uconsole-setup:204-213` | Prompts/saves `power.low_battery_shutdown=3.05`; a02ea67 removed all consumers. Write-only safety setting. | S |
| 6 | medium ⚠ | release-a02ea67 / known-deferred | `docs/TROUBLESHOOTING.md:122,128,131` | "boot failure on battery" section commands all point at the deleted `fix-battery-boot.sh`; TUI path "Power > Power Config > Install Boot Fix" also removed. | S |

### Non-blocking — high (frontend/cloud, pre-existing; fix soon)

| Rank | Sev | Dim | File:line | Evidence | Fix |
|------|-----|-----|-----------|----------|-----|
| R1 | high | sec-frontend | `frontend/src/lib/auth.ts:22` | Repo-scoped GitHub OAuth token (`scope: "repo read:user"`) copied into the NextAuth session → reachable client-side via `GET /api/auth/session` (middleware exempts `/api/auth/*`). Any XSS → full private-repo compromise. Not a drop-in delete: server `auth()` consumers depend on `session.accessToken`; needs restructuring. | S |
| R2 | high | sec-frontend | `frontend/src/app/api/device/status/route.ts:26` (+ `github:38`, `raw:47`, `commits/[sha]:36`) | Session-scoped responses set shared-cache `s-maxage` with no `private`/`Vary`. Vercel CDN key = path only → user B served user A's device telemetry / private-repo contents within the window. | S |
| R3 | high | sec-device-api | `frontend/src/lib/github/fetch.ts:191` | Tenant isolation keyed on the GitHub **repo string**, not user id. `validateUconsoleRepo` only checks readability via raw.githubusercontent.com (succeeds for any public repo). Attacker links `victim/public-backup` → token scoped to victim's Redis bucket → read/overwrite victim telemetry. | M |
| R4 | high | roadmap-diff | `device/bin/uconsole-setup:307` | Same dead `/api/device/claim` flow as rank 4 (escalation of prior-audit I10); wizard cloud-link provably dead in both directions. | M |

### Non-blocking — medium

| Rank | Sev | Dim | File:line | Evidence | Fix |
|------|-----|-----|-----------|----------|-----|
| M1 | medium | sec-device-api | `frontend/src/app/api/device/push/route.ts:19-30` | `isValidTelemetry` checks only hostname+collectedAt; nested cpu/memory/disk/battery unchecked → malformed push from a valid token throws during server render (root error boundary replaces dashboard; no TTL on key → stays broken). | M |
| M2 | medium | tui-cli | `device/bin/uconsole-setup:457` | `sudo cp "$CERT" "$PKG_BASE/webdash/uconsole.crt"` — `$PKG_BASE` undefined; under `set -euo pipefail` the unbound expansion aborts the wizard mid-Step-8 (even with `|| true`). Masked on normal installs (postinst pre-generates cert); hits cert-regeneration/standalone runs. | S |
| M3 | medium | tui-cli / known-deferred | `device/lib/tui/processes.py:90` | **2026-03-24 deferred item still present:** Enter / gamepad-A `os.kill(pid, SIGTERM)` with no confirmation; footer advertises "A Kill". Mitigated (SIGTERM, PID range-check), but a fat-finger kills the compositor/emulator. `run_confirm` helper exists, unused here. | S |
| M4 | medium | sec-apt | `packaging/scripts/generate-gpg-key.sh:33-34` | `Expire-Date: 0` + `%no-protection` — one passphraseless, never-expiring RSA-4096 key signs every release; no rotation/revocation doc. Signing host compromise → indefinite forgeable InRelease. | M |
| M5 | medium | sec-apt | `frontend/public/apt/pool/.../uconsole-cloud_0.2.1_arm64.deb` | Historical pool .debs (0.1.7–0.2.1) still ship `opt/uconsole/scripts/system/backup.sh` that `private_scripts.txt` forbids (2026-04-17 plaintext-PSK incident). Post-build assertion can't scrub pool artifacts. Private-source disclosure (no live creds; 0.3.0 clean). | S |
| M6 | medium | sec-apt | `packaging/postinst:71` | postinst pre-seeds well-known default webdash password `clockwork` (bcrypt), defeating the app's own forced `/setup-password` first-run flow. LAN-reachable once webdash enabled (not auto-started). | M (drop the pre-seed → fix becomes S) |
| M7 | medium | release-a02ea67 | `packaging/postinst:148` | Orphaned `/etc/systemd/system/axp-voff-shutdown.service` (forced bus-0 i2cset) left on disk after upgrade — disabled, but un-owned by dpkg and one `systemctl enable` from reintroducing the known CM5 regression; removal tool deleted. | S |
| M8 | medium | release-a02ea67 | `CHANGELOG.md:3-5` | "(unreleased)" placeholder has no entry for the battery/VOFF removal + forced retirement of 5 opted-in services. The changelog ships in the .deb (`build-deb.sh:112`) and `/publish` notes reference an entry that won't exist. | S |
| M9 | medium | install-upgrade | `packaging/postinst:111` | Upgrades never restart the running webdash (`# ... do NOT enable or start`; prerm has no upgrade branch). Old process serves new on-disk code until crash/reboot. Makefile dev path *does* restart — parity gap. | S |
| M10 | medium | install-upgrade | `device/share/defaults/uconsole.conf.default:17,27,35,37` | Two divergent `uconsole.conf.default` sources: `.deb` ships packaging copy (backup=false, cap=0, shutdown=3200 **mV**, ssl=.crt); `make install` rsyncs device copy (backup=true, cap=1200, shutdown=3.05 **V**, ssl=.pem). Units mismatch on a battery threshold; wizard reads it back as "voltage". | S |
| M11 | medium | install-upgrade | `packaging/control:6` | `openssl` absent from Depends while `postinst:83-88` runs `openssl req ... 2>/dev/null` under `set -e` with no `|| true` → missing openssl half-configures the package silently. CI masks it (`Dockerfile.test:8` installs openssl out-of-band). | S |
| M12 | medium | install-upgrade | `packaging/Dockerfile.test:146` | `dpkg -i ... 2>&1; exit 0` masks exit codes on upgrade/remove/purge/reinstall; only fresh install has a `dpkg -s` status assertion. v0.3.1's upgrade-branch postinst logic is exactly this blind spot. | S |
| M13 | medium | dead-code | `packaging/systemd/uconsole-backup.service:11` | Unit `ExecStart=.../system/backup.sh all` but `backup.sh` is scrubbed from the .deb; setup wizard (`uconsole-setup:411`), webdash, and restore.sh all `enable` the timer → guaranteed-failing service on every install. | M |
| M14 | medium | dead-code | `device/webdash/app.py:1134` | `/api/timer-schedule` edits `/opt/uconsole/config/systemd-user/*.timer` — a path in no install layout (packaged timers live in `/etc/systemd/system`). `open()` always `FileNotFoundError`; live UI button wired to it. Even corrected path fails (ProtectSystem=strict). | M |
| M15 | medium | dead-code | `device/scripts/util/console.sh:3` (+`webdash.sh:19`) | Dead wrappers exec `console.py`/`webdash.py` that no longer exist; ship executable in .deb; still advertised in `docs/page.tsx:443`. | S |
| M16 | medium | dead-code | `device/scripts/util/smoke-test.sh:108-119` | Smoke-test sections 8-9 assert pre-refactor `~/scripts/{webdash,console}.py`/`config.*` → hard-fails (exit 1) on every clean install. Related: `push-status.sh:188` reads `$HOME/scripts/esp32-marauder.sh` (real path `/opt/uconsole/scripts/radio/`) → ESP32 FW telemetry permanently "unknown". | M |
| M17 | medium | dead-code | `device/scripts/system/install-tdlib.sh` | Obsolete TDLib build-from-source installer (for `paul-nameless/tg`); TUI rewritten on Telethon. Zero consumers; ships executable; would run apt + 30-60min compile for an unused client. | S |
| M18 | medium | dead-code | `device/share/defaults/uconsole.conf.default` | Divergent conf twins (mV-vs-V battery threshold); device copy dead in .deb (clobbered) but live via `make install`; `/etc/uconsole/uconsole.conf.default` fallback path never installed → `smoke-test.sh:65` fails on every install. | S |
| M19 | medium | dead-code | `device/webdash/uconsole.crt` | Operator's own self-signed cert (CN=uconsole, 2026-03-23) committed and served unauthenticated at `/uconsole.crt` with docs telling users to add it as a trustRoot — never matches any device's real per-install TLS cert. Sole sync path is the dead `$PKG_BASE` line (M2). | M |
| M20 | medium | roadmap-diff | `packaging/control:6` | **Prior G3 (high) still present:** openssl used by postinst, absent from Depends. (qrencode was added since — Depends touched without fixing this.) | S |
| M21 | medium | roadmap-diff | `.github/workflows/release.yml:47` | **Prior R10+R11 (called "most critical") still present:** release.yml runs only `npm test`; no `pytest`, no Dockerfile.test install-test (those live only in ci.yml). A tagged release can ship a .deb whose device code/install path were never tested in release form. | M |

### Non-blocking — low

| Rank | Sev | Dim | File:line | Evidence |
|------|-----|-----|-----------|----------|
| L1 | low | sec-frontend | `frontend/src/app/api/device/code/confirm/route.ts:31` | Device token generated/stored **before** code validated → failed confirms leave 90-day orphan tokens, rotate `settings.deviceToken` (defeating revocation), no rate limit. Existing device link still works (token looked up directly). |
| L2 | low | sec-frontend | `frontend/src/app/api/settings/regenerate-token/route.ts:6` | No rate-limit/Origin check on session-gated mutating routes; SameSite=Lax is the only CSRF mitigation. Forced regenerate → telemetry DoS. |
| L3 | low | sec-device-api | `device/scripts/system/push-status.sh:293` | Device bearer token passed as `curl -H` argv → ps-visible in `/proc/<pid>/cmdline` for each curl's lifetime, recurring every 5 min. |
| L4 | low | sec-device-api | `frontend/src/app/api/device/code/confirm/route.ts:7` | No rate-limit/lockout on confirm (contrast code:10). Non-exploitable (8-char/32-sym, single-use, 10-min TTL) — defense-in-depth only. |
| L5 | low | sec-webdash | `device/webdash/app.py:1560` | Unauthenticated LAN-reachable `/api/battery-test/start`; `interval` unvalidated (no injection — list-exec). Local-IP gate + rate limit + pidfile mitigate; bad interval busy-loops `sleep`. ⚠ power script — flag only. |
| L6 | low | sec-webdash | `device/webdash/app.py:41` | Socket.IO PTY shell allows `https://uconsole.cloud` CORS origin; mitigated today by SameSite=Lax (handshake carries no cookie), but a remote-shell vector if cookie policy ever loosens to None. |
| L7 | low | sec-webdash | `device/webdash/app.py:2250` | Production traffic served by Werkzeug/SocketIO dev server with `allow_unsafe_werkzeug=True`; loopback-behind-nginx, `debug=False`. |
| L8 | low | sec-apt | `packaging/nginx/uconsole-webdash:17` | `Access-Control-Allow-Private-Network "true"` + uconsole.cloud origin allowlist on the catch-all vhost → compromised cloud frontend gets a CORS+PNA path into LAN webdash (uncredentialed, bounded by webdash auth). |
| L9 | low | sec-apt | `packaging/postinst:58` | `~/.config/uconsole/config.json` (password hash) written under root umask, only chown'd — world-readable 644 (contrast status.env chmod 600). |
| L10 | low | tui-cli | `device/bin/uconsole-setup:106` | ini_set fallback interpolates `$value` into `sudo sh -c "printf ...'$value'..."` — a quote breaks out in a root shell. Narrow branch (operator already has sudo; safe python path normally taken). Also corrupts config on any quote. |
| L11 | low | tui-cli | `device/bin/console:27` | No lib tree → raw `ModuleNotFoundError` traceback instead of "not installed"; nonexistent `UCONSOLE_DEV_LIB` silently skipped (contradicts "highest priority" docstring). |
| L12 | low | install-upgrade | `Makefile:36` | `make install` skips build-deb's private-script scrub (installs scripts/config, scripts/packages; would re-spill any future system/wifi PSKs) and never updates `/opt/uconsole/VERSION`; stale `build-deb.sh:60` .gitignore comment is false. |
| L13 | low | install-upgrade | `Makefile:43` | `sudo make install` writes the `~/pkg` mirror to `/root/pkg` (uses `$(HOME)`, no SUDO_USER resolution); real backup silently stops updating. |
| L14 | low | install-upgrade | `packaging/postinst:107` | postinst force re-enables the nginx site on every configure, overriding deliberate admin disablement. |
| L15 | low | install-upgrade | `packaging/postinst:10` | `get_real_user` fallback picks first uid≥1000; non-interactive root upgrades (apt cron/unattended) can switch which user services run as. Shipped self-update path is safe (SUDO_USER set). |
| L16 | low | dead-code | `device/webdash/static/js/dashboard.js` | Byte-identical dead dup of `templates/js/dashboard.js` (JS pair guarded by test; **style.css pair unguarded** — maintenance trap). |
| L17 | low | dead-code | `device/scripts/util/config.sh:14` | `config.sh`/`config.py` config-reader libs with zero consumers; ship in .deb. |
| L18 | low | dead-code | `device/scripts/config/systemd-user/trackball-scroll.service` | Byte-identical dup of `share/systemd/` copy; scrubbed from .deb, dead via `make install`. |
| L19 | low | dead-code | `frontend/src/components/DeviceSetup.tsx` (+`dashboard/HardwarePanel.tsx`) | Never imported by any route/component; tree-shaken from bundle. |
| L20 | low | dead-code | `studio/schemas/backupLog.ts` | 3 of 4 Sanity schemas unused by product (telemetry → Redis); committed `.sanity/runtime/app.js` auto-generated artifact. (`dist/` correctly gitignored.) |
| L21 | low | roadmap-diff | `device/scripts/power/battery.sh:1` | `set -euo pipefail` rollout still partial — 22 entry scripts lack `set -e` (PMU subset done). Two cycles past v0.2.3 target. (Count is 28 files incl. 6 libs, not 34; wifi-fallback.sh + restore.sh DO have it.) |
| L22 | low | roadmap-diff | `packaging/postinst:89` | **Committed-but-undone:** `chgrp www-data` still unguarded under `set -e` (nginx hard-dep mitigates). |
| L23 | low | roadmap-diff | `frontend/public/install.sh:34` | install.sh architecture check — NOT DONE (no `uname -m`/`dpkg --print-architecture`; non-arm64 → apt's opaque failure). |
| L24 | low | roadmap-diff | `frontend/public/install.sh:28` | install.sh GPG fingerprint verification — NOT DONE (TOFU over HTTPS). |
| L25 | low | roadmap-diff | `frontend/src/app/page.tsx:233` | **M4 still present:** non-GitHub (Upstash) errors rethrow past the catch → whole dashboard crashes to error boundary. |
| L26 | low | roadmap-diff | `frontend/src/app/api/device/code/confirm/route.ts:13` | **M5 still present:** `req.json()` without try/catch → 500 on malformed body (push route handles it). |
| L27 | low | roadmap-diff | `frontend/next.config.ts:14` | **M6 still present:** production CSP allows `unsafe-eval`+`unsafe-inline`; M3 (uncached paginated repos fetch) also remains. |
| L28 | low | roadmap-diff | `frontend/src/app/api/device/push/route.ts:120` | v0.2.0 multi-device model (device IDs, user array, status TTL) skipped despite version at 0.3.x; no explicit deferral note. |

### Info (status confirmations & notes)

- **sec-apt** `frontend/public/install.sh:28` — install GPG key is TOFU over HTTPS, no OOB verification (acceptable curl|bash model).
- **release-a02ea67** `README.md:139` — README still advertises the removed battery-safety stack as a shipped feature (low).
- **release-a02ea67** `device/webdash/docs/console-tui.md:25` — wiki doc still lists removed "crash log" TUI item (low).
- **release-a02ea67** `frontend/src/app/docs/page.tsx:426` — removed-script refs on **dev** copy; fixed-held on **main** (ships from main). dev→main merge keeps main's clean version.
- **release-a02ea67 ⚠** `device/scripts/power/fix-voltage-cutoff.sh:40` — intentional keep, but the kept curl|bash script applies the same 2.9V/900mA settings the commit calls "unsafe for other chemistries"; product decision worth a conscious sign-off or an 18650-only header warning. **Manual review only.**
- **tui-cli** `device/bin/uconsole-setup:64` / `frontend/public/scripts/uconsole:61` — **C2 (eval injection) and C3 (status.env eval) FIXED-HELD/shipped.**
- **tui-cli** `packaging/control:7` — optional-feature deps (pyserial/websocket-client/telethon) absent from Depends/Recommends → features degrade with a raw error string (telethon path degrades gracefully).
- **dead-code** `device/lib/uconsole_ai.py` — README advertises a TOOLS-menu `uconsole-ai` entry that doesn't exist; binary off PATH (drifting toward orphanhood; superseded by uconsole-hermes).
- **dead-code** `device/scripts/util/wardrive-preview.py` (cluster) — ~7 unreferenced dev/diagnostic tools ship executable in the public .deb; `scripts-manifest.txt` stale (still lists backup.sh).
- **dead-code** `device/lib/lib.sh:284` — `git_commit_and_push` back-compat alias has zero in-repo callers.
- **install-upgrade** `Makefile:35` — **2026-05-10 make-install ownership bug FIXED-HELD** (root ownership now enforced by construction on all three paths).
- **roadmap-diff** — C1/C2/C3 (all 3 prior critical vulns) FIXED-HELD/shipped; config_ui systemctl timeouts + framework git-describe FIXED/RETIRED; Dockerfile.test upgrade/uninstall tests DONE; v0.1.9 false-positive test NOT DONE (pattern-only substitute exists); hardware-detect.sh missing root check STILL PRESENT but fails loudly (not silent false success); v0.2.1 webdash/TUI runtime tests STILL OPEN.

---

## Refuted findings (do not re-report next cycle)

- **Device-code rate limit keyed on spoofable leftmost X-Forwarded-For** (sec-frontend, `device/code/route.ts`) — Vercel strips/overwrites client XFF before the function sees it; the platform value equals the proposed fix. Not bypassable in the shipped (Vercel-only) deployment.
- **Retired battery units: disable runs after dpkg deleted the unit files, so disable/stop no-op and symlinks dangle** (install-upgrade, `postinst`) — empirically false on systemd 252 (Bookworm): `systemctl disable --now` of a deleted-file unit removes dangling .wants symlinks, returns 0, and still executes the `--now` stop. No fix needed.
- **lora.sh sources user-writable lora.conf — FIXED-HELD** (roadmap-diff) — code fix is real but status label wrong: it's fixed-**released** in v0.3.0, not held. (Refuted as a *status* finding only.)
- **C3 status.env "FIXED-HELD, no source anywhere"** (known-deferred) — the device/CLI copies are fixed, but `frontend/public/scripts/push-status.sh:14` still `source`s it (that exposure is now tracked as blocking finding B3). The "no source anywhere" claim was false.

---

## Diff vs the 2026-04-09 audit

**Closed since 2026-04-09 (verified held):**
- All 3 critical vulns: C1 (`/api/set-password` auth bypass), C2 (setup `ask()` eval), C3 (CLI status.env eval) — fixed and shipped in v0.3.0, backed by `tests/test_audit_regressions.py`.
- Both source-without-validation must-fixes (device push-status.sh, lora.sh) — fixed in the device copies.
- v0.1.8 should-fixes: config_ui systemctl timeouts, framework git-describe (retired to VERSION file).
- v0.1.9 install-robustness: Dockerfile.test upgrade + uninstall/purge tests DONE.
- Bonus hardening: login rate-limiting, 10-char password floor, POST-only SSE, server-side session store + bcrypt + CSPRNG tokens (the three 2026-03-24 webdash deferrals all closed).

**Still open from 2026-04-09 (carried forward):**
- G3/openssl-not-in-Depends (was high) → M20/M11 here.
- R10+R11 release.yml skips pytest + install-test ("most critical finding") → M21 here.
- v0.1.9: install.sh arch-check (L23), GPG fingerprint (L24), trap cleanup (info), postinst www-data guard (L22), false-positive test (info).
- Frontend M4/M5/M6 (Redis-crash, confirm req.json, prod CSP) → L25/L26/L27.
- v0.2.0 multi-device model skipped entirely while versioning moved to 0.3.x (L28) — no documented deferral.

**Newly surfaced this cycle:**
- The entire **B1–B5 battery/VOFF retirement-incompleteness cluster** (a02ea67 is new) — the headline NO-GO driver.
- **B2/B3** push-status.sh env-path + live `source` regressions.
- **R1–R3** frontend token-in-session, shared-cache cross-user leak, and repo-string tenancy bypass (pre-existing but newly characterized).
- Prior-audit I10 escalated to a confirmed-dead `/api/device/claim` wizard flow (rank 4 / R4).

---

*Battery/power findings (⚠ SAFETY) are reported only — manual review required, no auto-fix. Safety-critical PMIC behavior must not be machine-patched.*
