# Phase 3 Dispatch Prompts — Merge, Package, Ship

Two prompts. Device runs first (gets extracted files into the repo). Mac runs second (builds .deb, wires APT, deploys).

---

## Prompt 1: uConsole Device (SSH Terminal)

```
CONTEXT — READ THIS FIRST

You're on the uConsole device (RPi CM4, Debian Bookworm). The refactor/device-dispatch-v1 branch has two commits:
- Phase 1 (4a3fa00): config.sh, config.py, webdash.py security fixes (bcrypt, secrets.token_hex, session store, set-password flow), pre-refactor backups
- Phase 2 (c5c02b6): documents the /opt/uconsole/ layout

The EXTRACTED structure at /opt/uconsole/ exists on the device filesystem but is NOT in the git repo. The cloud-side build-deb.sh needs these files to build a proper .deb package. Right now build-deb.sh copies from ~/uconsole/scripts/ (flat) and does a rough categorization — but it doesn't know about the TUI split, the extracted Flask app structure, or the setup wizard.

Your job: get the extracted files into the repo so the .deb build on the Mac side can use them, then merge to main.

Read CLAUDE.md at the repo root first.

---

STEP 1 — EXPORT EXTRACTED FILES TO REPO

The extracted structure at /opt/uconsole/ needs to be represented in the repo. Create a packaging-ready directory in the repo that mirrors what the .deb should install:

Create pkg/ at the repo root with this structure (copy from /opt/uconsole/):

pkg/bin/              ← uconsole CLI, console launcher, webdash launcher, uconsole-passwd, uconsole-setup
pkg/lib/              ← tui_lib.py, lib.sh, ascii_logos.py
pkg/lib/tui/          ← the 8 split TUI modules (framework.py, system.py, monitor.py, files.py, power.py, network.py, services.py, tools.py, config_ui.py, radio.py, __init__.py)
pkg/webdash/          ← app.py + templates/ + static/ + docs/ (the extracted Flask app)
pkg/scripts/system/   ← backup.sh, restore.sh, push-status.sh, update.sh, hardware-detect.sh
pkg/scripts/power/    ← battery.sh, battery-test.sh, cellhealth.sh, charge.sh, low-battery-shutdown.sh, power.sh, cpu-freq-cap.sh
pkg/scripts/network/  ← wifi.sh, wifi-fallback.sh, hotspot.sh, network.sh
pkg/scripts/radio/    ← gps.sh, sdr.sh, lora.sh, esp32.sh, aio-check.sh
pkg/scripts/util/     ← config.sh, smoke-test.sh, anything else
pkg/share/defaults/   ← uconsole.conf.default, config.json.default

Copy from /opt/uconsole/ — these are the tested, working versions (46/46 smoke test). Do NOT re-extract or regenerate. Just copy what's there.

For scripts that only exist in ~/uconsole/scripts/ and weren't part of the extraction, copy them into the appropriate pkg/scripts/ subdirectory using the same categorization:
- battery*, charge*, power*, low-battery*, cpu-freq* → power/
- wifi*, hotspot*, network*, tailscale* → network/
- sdr*, lora*, gps*, rtc*, radio*, esp32*, aio* → radio/
- backup*, restore*, push-status*, update*, doctor*, setup*, hardware* → system/
- everything else → util/

Also copy config.sh and config.py into pkg/scripts/util/ (these are the config helpers from Phase 1).

IMPORTANT: Do NOT copy webdash.py.pre-refactor or console.py.pre-refactor — those are backups, not shipping code.

---

STEP 2 — VERIFY

- Confirm pkg/ has all the files: ls -laR pkg/ | head -80
- Verify the key files exist:
  - pkg/bin/uconsole-setup (the wizard)
  - pkg/bin/uconsole-passwd
  - pkg/lib/tui/__init__.py (TUI modules)
  - pkg/webdash/app.py (extracted Flask app)
  - pkg/webdash/templates/ (Jinja2 templates)
  - pkg/scripts/util/smoke-test.sh
  - pkg/share/defaults/uconsole.conf.default
- python3 -m py_compile pkg/webdash/app.py
- python3 -c "import sys; sys.path.insert(0, 'pkg/lib'); from tui import framework"
- bash -n pkg/bin/uconsole-setup
- bash -n pkg/scripts/util/config.sh

---

STEP 3 — MERGE TO MAIN

git add pkg/
git commit -m "feat: add pkg/ directory with extracted /opt/uconsole/ structure for .deb builds

Copies tested files from /opt/uconsole/ on device into repo-tracked pkg/ directory.
Includes: TUI split (8 modules), extracted Flask webdash, setup wizard, config system,
hardware detection, smoke test. All from the 46/46-passing device build."

git checkout main
git merge refactor/device-dispatch-v1 --no-ff -m "merge: device dispatch v1 — config system, security fixes, extracted package structure"

---

STEP 4 — PUSH AND REPORT

git push origin main

Tell me:
1. File count in pkg/ (find pkg/ -type f | wc -l)
2. Whether all verification checks passed
3. The merge commit hash

DO NOT delete the feature branch yet. DO NOT touch scripts/webdash.py or scripts/console.py — those originals stay as-is alongside pkg/.

WHAT NOT TO DO:
- Don't modify any running services
- Don't touch battery/power scripts logic
- Don't restructure anything — just copy from /opt/uconsole/ to pkg/
- Don't delete or rename existing files outside pkg/
```

---

## Prompt 2: Mac Terminal (uconsole-cloud)

```
CONTEXT — READ THIS FIRST

You're in the uconsole-cloud repo (Next.js 16, Vercel). The refactor/cloud-dispatch-v1 branch has 10 commits: TypeScript device config types, HardwarePanel component, device linking docs, .deb refactor, APT repo scripts, Makefile, README, open-source files.

The uconsole DEVICE repo (mikevitelli/uconsole) has just been merged to main with a new pkg/ directory containing the extracted /opt/uconsole/ structure — the actual files the .deb should install. This means build-deb.sh needs updating: instead of copying from ~/uconsole/scripts/ (flat, old approach), it should copy from ~/uconsole/pkg/ (organized, new approach).

Your job: update build-deb.sh to use pkg/, fix the package naming, merge to main, and wire everything up.

Read CLAUDE.md at the repo root first.

---

STEP 1 — VERIFY PACKAGE NAMING

The package name is "uconsole-cloud" — this is intentional branding. Verify it's consistent across all packaging files:

- packaging/control: Package: uconsole-cloud ✓
- packaging/build-deb.sh: PKG="uconsole-cloud" ✓
- packaging/postinst: banner says "uconsole-cloud" ✓
- frontend/public/install.sh: apt-get install -y uconsole-cloud ✓
- Makefile: publish-apt target globs for uconsole-cloud_*_arm64.deb ✓

If any file says "uconsole-tools" instead, change it back to "uconsole-cloud". The package, the cloud app, and the brand are all "uconsole-cloud".

---

STEP 2 — REWRITE build-deb.sh TO USE pkg/

The device repo now has pkg/ with the final organized layout. Rewrite build-deb.sh to copy from there instead of categorizing scripts from ~/uconsole/scripts/:

SCRIPTS_SRC should become DEVICE_PKG="${HOME}/uconsole/pkg" (the device repo's pkg/ directory).

Replace the entire "Copy scripts into organized subdirs" section and all the per-file case statements with a straightforward copy of the pkg/ tree:

- cp -r ${DEVICE_PKG}/bin/* → ${BUILD_DIR}/opt/uconsole/bin/
- cp -r ${DEVICE_PKG}/lib/* → ${BUILD_DIR}/opt/uconsole/lib/
- cp -r ${DEVICE_PKG}/scripts/* → ${BUILD_DIR}/opt/uconsole/scripts/
- cp -r ${DEVICE_PKG}/webdash/* → ${BUILD_DIR}/opt/uconsole/webdash/
- cp -r ${DEVICE_PKG}/share/* → ${BUILD_DIR}/opt/uconsole/share/

Keep the existing logic for:
- CLI from frontend/public/scripts/uconsole (the cloud-side CLI wrapper)
- DEBIAN control files, systemd units, nginx config, avahi
- Symlinks (usr/bin/uconsole → /opt/uconsole/bin/uconsole)
- Version injection from VERSION file

Update the console symlink: if pkg/bin/console exists, symlink usr/bin/console → /opt/uconsole/bin/console.

Add validation at the top: if ${DEVICE_PKG} doesn't exist, error with "Device repo pkg/ not found at ${DEVICE_PKG}. Clone mikevitelli/uconsole and ensure pkg/ exists."

---

STEP 3 — UPDATE INSTALL ROUTE

The existing frontend/src/app/install/route.ts may have stale logic. Verify it serves install.sh correctly with content-type text/plain. If it reads from a file, make sure it reads frontend/public/install.sh.

Also verify that /apt/* routes work for serving the APT repo (Packages, Release, .deb files from frontend/public/apt/).

---

STEP 4 — MERGE TO MAIN

git add -A
git commit -m "feat: rewrite build-deb.sh for pkg/ layout, align package name to uconsole-tools

build-deb.sh now copies from device repo's pkg/ directory instead of flat scripts/.
Package renamed from uconsole-cloud to uconsole-tools across control, install.sh, Makefile.
Install route and APT serving verified."

git checkout main
git merge refactor/cloud-dispatch-v1 --no-ff -m "merge: cloud dispatch v1 — packaging, APT repo, open-source readiness"

---

STEP 5 — BUILD AND VERIFY

This step validates that the build pipeline works end-to-end. It won't produce a real .deb (no device repo on Mac), but verify everything else:

1. npm run build (Next.js must build clean)
2. npm test (all 138 tests must pass)
3. Verify the install route: check frontend/src/app/install/route.ts returns install.sh content
4. Verify install.sh references "uconsole-tools" not "uconsole-cloud"
5. Verify packaging/control says "uconsole-tools"
6. Verify Makefile targets reference "uconsole-tools"
7. Review the README — make sure install instructions say uconsole-tools

---

STEP 6 — PUSH (but do NOT deploy yet)

git push origin main

Tell me:
1. Whether build + tests passed
2. Every file you modified (not created by previous commits — just your changes)
3. Any issues found during verification
4. The merge commit hash

DO NOT deploy to Vercel yet — I want to review the diff first.
DO NOT delete feature branches.
DO NOT generate or commit GPG keys.

WHAT NOT TO DO:
- Don't change auth logic or existing API routes
- Don't restructure the frontend app
- Don't touch battery/power script logic
- Don't push tags or trigger releases
- Don't run make release or make publish-apt
```
