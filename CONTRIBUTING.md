# Contributing

Thanks for your interest in uconsole-cloud! Contributions are welcome — especially from uConsole owners who can test on real hardware.

## Quick overview

This repo has two products in one:

1. **Cloud dashboard** (`frontend/`) — Next.js app at uconsole.cloud showing device telemetry
2. **Device package** (`device/`) — TUI, webdash, and 47 scripts installed via `.deb` on the uConsole

They share a repo because they ship together — the `.deb` is built from `device/` and hosted via the frontend's APT repo.

For data flow and project layout, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Branching

| Branch | Purpose |
|--------|---------|
| `main` | Released state — tagged versions, deployed to Vercel + APT |
| `dev` | Active development — PRs target this branch, CI runs on push |

1. Fork the repo and create a branch from `dev` (not `main`)
2. Make your changes
3. Run tests (see below)
4. Open a pull request against `dev`

Do not open PRs against `main` — releases are merged from `dev` → `main` by maintainers.

## Setup

```bash
git clone https://github.com/mikevitelli/uconsole-cloud.git
cd uconsole-cloud
npm install
```

### Frontend development (cloud dashboard)

```bash
cp frontend/.env.example frontend/.env.local
# Fill in your credentials (see .env.example for details)
npm run dev        # frontend :3000, studio :3333
```

Required env vars: `GITHUB_ID`, `GITHUB_SECRET`, `AUTH_SECRET`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`. (Sanity vars are optional for dev.)

### Device development (TUI, webdash, scripts)

If you have a uConsole (or any arm64 Debian device):

```bash
# Edit source in device/
vim device/lib/tui/framework.py

# Just launch — no install step. The default `console` auto-detects
# ~/uconsole-cloud/device/lib/ and uses it when present.
console
```

`make install` exists for packaging a `.deb` for end users — it's not part of the day-to-day edit loop on a developer's box.

Three TUI launchers:

| Launcher | Keybind (labwc) | Reads from | Use when |
|----------|-----------------|------------|----------|
| `console` | — | `~/uconsole-cloud/device/lib` if present, else `/opt/uconsole/lib` | default — works for both devs and end users |
| `console-pkg` | Ctrl+Shift+P | `/opt/uconsole/lib` (forced) | verify what end users would see |
| `console-dev` | Ctrl+\` | `~/uconsole-cloud/device/lib` (forced) | redundant with the new default — kept for the keybind |

To point at any arbitrary tree: `UCONSOLE_DEV_LIB=/some/path console`.

Toggle webdash between dev and installed: `make dev-mode` / `make pkg-mode`. `make install` auto-restarts webdash if running.

If you don't have a uConsole, you can still run `make test` — most checks don't require hardware.

## Testing

Four test layers, fast/local to slow/device-specific:

### 1. Source tests (no hardware needed)

```bash
make test-device     # pytest + bash syntax + py_compile
make test-frontend   # vitest + eslint + typecheck (Node 22)
make test            # both
```

Catches: broken imports, missing scripts, menu/handler mismatches, shell syntax errors, TypeScript errors, frontend regressions.

### 2. Docker install test (Docker, no hardware)

```bash
make test-install    # builds .deb, installs in arm64 Debian Bookworm container
```

30+ tests in a fresh Debian container via QEMU arm64 emulation: install, postinst, upgrade, uninstall, purge, reinstall. Native ~40s on arm64; ~3 min on x86 with QEMU.

Interactive shell into the container: `sudo docker run --rm -it uconsole-test bash`

### 3. End-to-end test (real device only)

```bash
make test-e2e        # installs .deb, tests live system
```

Tests `uconsole doctor`, password change, mDNS, HTTPS, CLI, systemd. Requires sudo.

### 4. CI (every push)

| Job | What | Time |
|-----|------|------|
| `ci` | shellcheck, pytest, lint, typecheck, vitest, Next.js build | ~90s |
| `install-test` | Docker arm64 install test via QEMU | ~2.5min |

E2E is NOT in CI (real-hardware-only).

### Single test

```bash
python3 -m pytest tests/test_tui_integrity.py -v
python3 -m pytest tests/ -k "test_each_script"
npm test -w @uconsole/frontend -- --run src/__tests__/devicePaths.test.ts
```

### When to run what

| Scenario | Command |
|----------|---------|
| Editing device Python/bash | `make test-device` |
| Editing frontend TypeScript | `make test-frontend` |
| Before opening a PR | `make test` |
| Changed packaging/postinst | `make test-install` |
| Before a release | `make test-install && make test-e2e` |

## Versioning

You don't need to manually bump versions during development.

- **Installed package** (`console-pkg`, or `console` on a machine without a source tree): reads `VERSION` directly — shows the released version, e.g. `0.2.1`.
- **Dev tree** (plain `console` on a developer's box, or `console-dev`): reads `VERSION`, patch-bumps, appends `-dev` — `0.2.1` becomes `0.2.2-dev`.
- **Releases**: maintainers run `/publish` — bumps `VERSION`, merges `dev` → `main`, builds the `.deb`, signs the APT repo, commits, tags.

The `uconsole --version` CLI reads the same `VERSION` file.

## Code style

- TypeScript throughout, strict mode
- Server Components by default — only add `'use client'` when needed
- Tailwind CSS v4 (GitHub-dark theme)
- TUI: each feature module exports a `HANDLERS = {"_foo": fn}` dict at module scope; framework.py walks `FEATURE_MODULES` and merges them. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before adding new features.
- Shell scripts use `bash`, include a shebang, must pass `bash -n`
- Battery/power scripts are **safety-critical** — always flag for manual review

## What to work on

- [Open issues](https://github.com/mikevitelli/uconsole-cloud/issues) for bugs and feature requests
- [docs/FEATURES.md](docs/FEATURES.md) for the roadmap
- [CHANGELOG.md](CHANGELOG.md) "What's next" section for planned work

If you have a uConsole, testing device scripts and the CLI on real hardware is especially valuable.

## Questions?

Open an issue. There's no Discord or mailing list — GitHub issues are the place.
