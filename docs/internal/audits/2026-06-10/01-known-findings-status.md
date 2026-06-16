# Known & Deferred Findings — Status Ledger (2026-06-10)

Status of every previously-tracked finding the v0.3.1 gate had to re-confirm. Each row is verified against committed code (dev for device, main for frontend). ⚠ = battery/power, manual review only.

## v0.1.8 critical fixes (2026-04-09 audit)

| ID | Finding | Status | Evidence | Held? |
|----|---------|--------|----------|-------|
| **C1** | webdash `/api/set-password` unauthenticated write | **FIXED — HELD/SHIPPED** | `device/webdash/app.py:228-231` `if _password_is_set(): return redirect('/login')` (first-run only); rotation moved to authenticated `/api/change-password` (`app.py:252-254`); both in `_AUTH_PATHS`, rate-limited (`app.py:360-362`, 376-381); `_PASSWORD_MIN_LEN=10`. Present on origin/dev AND main. | yes |
| **C2** | eval injection in `uconsole-setup` `ask()` | **FIXED — SHIPPED** | `device/bin/uconsole-setup:64,73` `printf -v "$var" '%s' ...` (no eval); `grep -n eval` over file = 0. Landed in 4137e0a "release: v0.3.0". | yes |
| **C3** | eval/source of `status.env` in `uconsole` CLI | **FIXED — SHIPPED** | `frontend/public/scripts/uconsole:58-67` `read_env_value()` (grep/tail/sed, no source/eval), used by cmd_link + cmd_status. Live on origin/main. *(Caveat: the separate `frontend/public/scripts/push-status.sh:14` still `source`s — see report B3.)* | yes |

## 2026-03-24 deferred webdash items

| Item | Status | Evidence |
|------|--------|----------|
| Plaintext password comparison (`==`) | **RETIRED — bcrypt** | `device/webdash/app.py:163` `_bcrypt.checkpw(...)`; hash via `_hash_password` (`165-168`); no `==` compare anywhere; fails closed. On origin/dev + main. |
| Deterministic session token | **RETIRED — CSPRNG** | `app.py:176-180` `_make_token() → secrets.token_hex(32)` (256-bit), server-registered with expiry; not derived from user/time/secret_key. |
| No server-side session invalidation | **RETIRED — store + logout revoke** | `app.py:174` `_active_sessions = {}`; `_is_authenticated` (`182-189`) only accepts registered/unexpired tokens; `/logout` (`269-275`) → `_invalidate_session` (`191-192`). Caveat (non-regression): in-memory store, lazy expiry, all sessions drop on restart. |
| Unconfirmed process kill | **STILL PRESENT** ⚠(UX) | Successor `device/lib/tui/processes.py:90` `os.kill(int(pid), SIGTERM)` on Enter/gamepad-A with no confirm (footer:67 advertises "A Kill"). Mitigated: SIGTERM-only, PID range-check (`:88`), exceptions caught. `run_confirm` helper exists (framework.py), unused here. Fat-finger hazard, not a security hole. → report M3. Fix S (add y/n confirm). |

## i2c-bus-0 VOFF regression retirement (a02ea67)

| Aspect | Status | Evidence |
|--------|--------|----------|
| `axp-voff-shutdown.service` removed from packaging | **DONE** | `git ls-tree dev packaging/systemd/` → only backup/status/update/webdash units; build-deb.sh battery-fix payload block deleted. |
| postinst disables retired units on upgrade | **DONE** | `packaging/postinst:145-150` `RETIRED_UNITS="pmu-voltage-min cpu-freq-cap low-battery-shutdown crash-log axp-voff-shutdown"` + `systemctl disable --now` loop + `reset-failed`. systemd 252 cleans dangling .wants even after dpkg deletes the files (empirically verified; refutes the "dangling symlink" concern). |
| **On-device opt-in residue (udev rule + initramfs hook/premount)** | **NOT RETIRED — RELEASE-BLOCKING** ⚠ SAFETY | `fix-battery-boot.sh cmd_install` (a02ea67^:86-114) wrote `/etc/udev/rules.d/99-uconsole-battery.rules` (`voltage_min=2900000`), `/etc/initramfs-tools/hooks/axp-voff`, `scripts/init-premount/axp-voff` (`i2cset -f -y 0 0x34 0x31 0x03`). postinst removes none of them and runs no `update-initramfs`; purge doesn't either. The removal tool `fix-battery-boot.sh` is deleted by the same commit. Opted-in v0.3.0 devices keep applying the 2.9V VOFF every boot; kernel updates re-bake it. → **report B1** (and orphaned unit file → M7). **Manual review only — do not auto-fix.** |
| Orphaned `/etc/systemd/system/axp-voff-shutdown.service` file | **LEFT ON DISK** ⚠ | `packaging/postinst:148` disables but never `rm`s it; un-owned by dpkg; one `systemctl enable` from reintroducing the forced bus-0 write. → report M7. |
| TROUBLESHOOTING.md revert instructions | **STALE — RELEASE-BLOCKING** ⚠ | `docs/TROUBLESHOOTING.md:122,128,131` still point at the deleted `fix-battery-boot.sh`. → report B5. |

## Summary

The security ledger is in good health: **all 3 v0.1.8 criticals and all 3 fixable 2026-03-24 webdash deferrals are closed and held**, several with regression tests. Two items remain open — the unconfirmed process kill (UX fat-finger, non-blocking M3) and, critically, the **incomplete on-device retirement of the opt-in battery-fix residue**, which is the primary v0.3.1 NO-GO driver (B1/B5, with M7). All battery/PMIC items are flagged for manual review and must not be auto-patched.
