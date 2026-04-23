# Release Pipeline

The full edit → user flow for `uconsole-cloud`. This is the maintainer
reference — contributors see [CONTRIBUTING.md](../CONTRIBUTING.md) for
the subset that applies to PRs.

## Stages

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. EDIT                                                             │
│    vim ~/uconsole-cloud/device/lib/tui/framework.py                 │
│    (nothing automatic — just a file on disk)                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. PREVIEW (Ctrl+`)                                                 │
│    console-dev reads ~/uconsole-cloud/device/lib directly           │
│    → changes visible immediately, no deploy needed                  │
│    Webdash: not auto-reloaded (use `make dev-mode` if touching it)  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. COMMIT                                                           │
│    git add <path> && git commit -m "…" && git push origin dev       │
│                                                                     │
│    GitHub Actions (.github/workflows/ci.yml) fires on push:         │
│      ├── shellcheck on install.sh + uconsole CLI                    │
│      ├── pytest (device tests)                                      │
│      ├── frontend: vitest + eslint + tsc + Next.js build            │
│      └── install-test: .deb build + Docker arm64 install (~2.5 min) │
│                                                                     │
│    Green = safe to merge. Red = fix before /publish.                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. DEPLOY LOCALLY (optional, for verifying the installed flow)      │
│    make install                                                     │
│      ├── rsync device/ → /opt/uconsole/    (--delete, with sudo)    │
│      ├── rsync device/ → ~/pkg/             (no --delete, backup)   │
│      └── systemctl restart uconsole-webdash (if running)            │
│                                                                     │
│    console-pkg (Ctrl+Shift+P) now runs your edits.                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. PUBLISH (/publish)                                               │
│                                                                     │
│    Pre-flight:  python3 -m py_compile + bash -n + personal-data grep│
│       (STOPS on failure)                                            │
│                                                                     │
│    git:    commit dev, push dev                                     │
│            checkout main, merge dev --no-ff                         │
│                                                                     │
│    make bump-patch      VERSION 0.2.1 → 0.2.2 (also device/VERSION) │
│    make build-deb       packaging/build-deb.sh → dist/*.deb         │
│    make publish-apt     sign + refresh frontend/public/apt/         │
│                                                                     │
│    git:    commit release, tag v0.2.2, push main --tags             │
│                                                                     │
│    GitHub Actions (.github/workflows/release.yml) fires on tag:     │
│       verify VERSION matches tag → create GitHub Release page       │
│                                                                     │
│    Vercel detects main push:                                        │
│       build frontend → deploy to uconsole.cloud                     │
│       apt/ directory now serves the new .deb                        │
│                                                                     │
│    Sync ~/pkg/:                                                     │
│       rsync uconsole-cloud/device/ → ~/pkg/                         │
│       commit + push pkg (private repo)                              │
│                                                                     │
│    git:    checkout dev, merge main --ff-only, push dev             │
│            (so dev and main stay aligned)                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 6. USERS RECEIVE (any uConsole with the APT repo added)             │
│    sudo apt update                                                  │
│      → hits uconsole.cloud/apt, sees v0.2.2 available               │
│    sudo apt upgrade                                                 │
│      → downloads .deb, runs postinst (systemd reload, nginx reload, │
│        webdash restart), VERSION file updated to 0.2.2              │
└─────────────────────────────────────────────────────────────────────┘
```

## Three speeds

| Speed | Steps | Time | What you've done |
|---|---|---|---|
| **Flicker** | 1 → 2 | seconds | Preview a TUI change locally |
| **Commit** | 1 → 2 → 3 | ~1 min + CI (~3 min async) | Share on `dev`, CI-verified |
| **Release** | 1 → 2 → 3 → (4) → 5 | ~5–10 min | End users can `apt upgrade` |

## Automation triggers

| When… | What fires | Defined in |
|---|---|---|
| Push to `dev` or `main` | CI (shellcheck + pytest + frontend + Docker install test) | `.github/workflows/ci.yml` |
| Tag push (`v*`) | Release workflow (VERSION check + GitHub Release page) | `.github/workflows/release.yml` |
| Push to `main` | Vercel deploy of `frontend/` to uconsole.cloud | Vercel dashboard config |
| `make install` | webdash auto-restart (if running) | `Makefile` install target |
| `/publish` | bump + build + sign + tag + push | `~/.claude/commands/publish.md` |

## Manual decisions

Nothing above fires without a human pushing, running `make`, or invoking `/publish`. Decisions the pipeline **will not make for you:**

- When to commit (CI doesn't run until you push)
- When to `make install` (Ctrl+\` is enough for TUI-only edits)
- When to `/publish` (no calendar — whenever `dev` is ready)
- Patch vs minor vs major bump (`make bump-patch` is the `/publish` default; use `bump-minor` / `bump-major` when scope warrants)
- Merging feature branches into `dev`

## Failure modes

| Break point | Symptom | Recovery |
|---|---|---|
| Syntax error pre-flight | `/publish` stops at step 1 | Fix file, re-run `/publish` |
| CI red on `dev` | Push status fails in GitHub | Fix locally, push again |
| `make install` permission denied | rsync error | `sudo` prompt — nothing destructive |
| `make publish-apt` GPG error | Signing fails | Only the maintainer with the key can fix |
| Vercel deploy fails | `main` pushed but site unchanged | Check Vercel dashboard — usually env var or build error |
| User device upgrade fails | End-user `apt upgrade` errors | postinst issue — user can pin to prior: `sudo apt install uconsole-cloud=0.2.1-1` |

## Related docs

- [CONTRIBUTING.md](../CONTRIBUTING.md) — contributor-facing subset of this pipeline
- [SECURITY.md](../SECURITY.md) — vulnerability reporting, security posture
- [CHANGELOG.md](../CHANGELOG.md) — released versions + what shipped
- [docs/FEATURES.md](FEATURES.md) — roadmap
- [docs/DEVICE-LINKING.md](DEVICE-LINKING.md) — device auth flow
- [docs/specs/](specs/) — design docs for in-flight features
