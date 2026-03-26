# Device Code Auth — Branch Status & Changes

## Branches

| Branch | Based On | Deployed To | Status |
|--------|----------|-------------|--------|
| `main` | — | `uconsole.cloud` (production) | Stable, no new features |
| `feat/device-code-auth` | `main` | `preview.uconsole.cloud` (via `staging`) | All features implemented, needs UX review |
| `test/device-code-e2e` | `feat/device-code-auth` | Own Vercel preview URL | 17 e2e tests with dummy data |

Note: `feat/device-code-auth` is pushed to the `staging` branch which maps to `preview.uconsole.cloud`.

---

## What Was Built

### 1. Device Code Auth (TV-style linking)
Users link their uConsole without needing a browser on the device.

**Flow:** CLI generates code → user enters code on phone → device gets token

**New files:**
- `src/lib/deviceCode.ts` — code generation (XXXX-XXXX format), Redis storage with 10min TTL
- `src/app/api/device/code/route.ts` — POST, generate code (public)
- `src/app/api/device/code/confirm/route.ts` — POST, confirm code (auth required)
- `src/app/api/device/poll/[secret]/route.ts` — GET, poll for confirmation (public)

### 2. Installer & CLI
One-command install with `curl | bash`.

**New files:**
- `src/app/install/route.ts` — GET /install, returns bash installer script
- `src/app/api/scripts/[name]/route.ts` — serves allowlisted scripts (push-status.sh, uconsole)
- `public/scripts/uconsole` — CLI with subcommands: setup, push, status, unlink, update, help
- `public/scripts/push-status.sh` — copy of device telemetry script

**CLI features:**
- `uconsole setup` — device code flow, writes config, sets up cron
- Detects existing config and asks before overwriting
- BASE_URL overridable via env var for local testing

### 3. /link Browser Page
Where users enter the device code from their phone.

**New files:**
- `src/app/link/page.tsx` — server component, checks auth + repo status
- `src/components/DeviceCodeForm.tsx` — code entry form (auto-uppercase, auto-hyphen)

### 4. Auto-Create GitHub Repo
New users can create a bootstrapped backup repo without leaving the web UI.

**New/modified files:**
- `src/lib/github.ts` — added `githubPost`, `BOOTSTRAP_FILES` (11 files), `createBootstrapRepo` (uses Trees API), `fetchGitHubUser`
- `src/app/api/github/repos/create/route.ts` — POST, creates repo + bootstrap files + auto-links
- `src/app/api/github/user/route.ts` — GET, returns GitHub username for display
- `src/components/RepoLinker.tsx` — added "create" mode toggle alongside existing "select" mode

**Bootstrap files created in new repo:**
- `packages/` — 6 empty manifests (apt, flatpak, snap, cargo, pip, clockworkpi)
- `scripts/push-status.sh` + `scripts/backup.sh` — placeholders
- `restore.sh`, `README.md`, `.gitignore`

### 5. Landing Page Redesign
Hero layout inspired by Claude Code's landing page.

**Modified:** `src/app/page.tsx`
- Large heading + description
- Prominent `curl` install command with copy button
- Feature stats strip (5 min / 1 command / Zero config)
- Sign-in pushed to secondary action

**New:** `src/components/CopyCommand.tsx` — copy-to-clipboard command display

### 6. Middleware Update
**Modified:** `src/middleware.ts`
- Added exclusions for: `device/code$`, `device/poll`, `scripts`
- `device/code/confirm` stays protected (regex uses `$` anchor)

### 7. Tests
- `src/__tests__/deviceCode.test.ts` — 20 unit tests for code generation, confirm, poll
- `src/__tests__/security.test.ts` — 5 new tests for middleware exclusions
- `src/__tests__/e2e-deviceFlow.test.ts` — 17 e2e tests (on test branch)
- **Total: 155 tests, all passing**

---

## Known Issues / Blockers

### Vercel Deployment Protection
`preview.uconsole.cloud` has Vercel's SSO/deployment protection enabled. Public endpoints (`/install`, `/api/device/code`, `/api/device/poll/*`, `/api/scripts/*`) get blocked with 401 before reaching the app. Need to either:
- Disable deployment protection for preview
- Add these paths to the bypass list
- Or just test via `localhost:3000`

### Preview OAuth
Separate GitHub OAuth app (`uconsole-cloud-preview`) was created for preview. Env vars are configured for the `staging` branch. Production OAuth app is unchanged.

### Install Script Hardcodes Production URL
The install script (`/install` route) downloads scripts from `uconsole.cloud` (production). For testing against preview, users need to manually edit the CLI's BASE_URL after install. The CLI now supports `BASE_URL` env var override for local testing.

---

## UX Decisions To Make

1. **Landing page copy** — current text: "Monitor your uConsole from anywhere. Battery, CPU, memory, WiFi, and more — pushed every 5 minutes." Good enough or needs work?

2. **RepoLinker flow** — currently "select existing repo" is the default view with "or create a new repo" as secondary. Should "create" be the default for new users who likely don't have a repo?

3. **/link page** — currently shows RepoLinker if no repo linked, then DeviceCodeForm if repo is linked. Should these be combined into one flow? (create/link repo → enter code, all on one page)

4. **Install script** — should it also run `uconsole setup` automatically, or keep them as separate steps?

5. **Repo name** — defaults to `uconsole`. Should it be `uconsole-backup` or something else?

6. **Private vs public** — defaults to private. Right default?

---

## How to Test Locally

```bash
# Start dev server (from frontend/)
npm run dev

# Test CLI against localhost
BASE_URL=http://localhost:3000 bash public/scripts/uconsole setup

# Then open http://localhost:3000/link in browser to enter the code

# Run all tests
npx vitest run
```

## How to Merge to Production

1. Review UX decisions above
2. Merge `feat/device-code-auth` → `main`
3. Vercel auto-deploys to `uconsole.cloud`
4. Test: `curl -fsSL https://uconsole.cloud/install | bash` on uConsole
