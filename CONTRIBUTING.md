# Contributing

Thanks for your interest in uconsole-cloud! Contributions are welcome — especially from uConsole owners who can test on real hardware.

## Getting started

```bash
git clone https://github.com/mikevitelli/uconsole-cloud.git
cd uconsole-cloud
npm install
cp frontend/.env.example frontend/.env.local
# Fill in your credentials (see .env.example for details)
npm run dev
```

This starts the Next.js frontend at `:3000` and the Sanity Studio at `:3333`.

### Required environment variables

| Variable | Purpose |
|----------|---------|
| `GITHUB_ID` | GitHub OAuth app ID |
| `GITHUB_SECRET` | GitHub OAuth app secret |
| `AUTH_SECRET` | NextAuth JWT secret (`openssl rand -base64 33`) |
| `UPSTASH_REDIS_REST_URL` | Redis connection URL |
| `UPSTASH_REDIS_REST_TOKEN` | Redis auth token |
| `NEXT_PUBLIC_SANITY_PROJECT_ID` | Sanity CMS project ID (optional for dev) |

## Making changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Run `npm test` and `npm run build` to verify nothing breaks
4. Open a pull request against `main`

## Code style

- TypeScript throughout, strict mode
- Server Components by default — only add `'use client'` when needed
- Tailwind CSS v4 for styling (GitHub-dark theme)
- Keep tests passing (211+ as of v0.1.1)

## Project layout

```
frontend/src/
├── app/            Pages, API routes, server actions
├── components/
│   ├── dashboard/  17 sections (DeviceStatus, BackupHistory, HardwarePanel, etc.)
│   └── viz/        7 visualizations (Sparkline, Donut, CalendarGrid, Treemap, etc.)
├── lib/            20 modules (auth, redis, github, types, utils, etc.)
└── __tests__/      10 test suites (parsing, security, validation, API)
```

**Key patterns:**
- Dashboard sections are Server Components that fetch from Redis/GitHub on page load
- `lib/` modules handle all data access — components don't call APIs directly
- Visualization components are client-only (`'use client'`) for interactivity

## Testing

```bash
npm test              # run all 211 tests (vitest)
npm run test:watch    # watch mode during development
npm run build         # catches type errors the tests don't
npm run lint          # ESLint
```

Tests cover parsing logic, security checks (path traversal, SHA validation), API responses, device code generation, and TUI structure. If you add a new `lib/` module, add a corresponding test file in `__tests__/`.

## What to work on

- Check [open issues](https://github.com/mikevitelli/uconsole-cloud/issues) for bugs or feature requests
- See [FEATURES.md](FEATURES.md) for the roadmap — Phase 2 cloud UX and Phase 5 polish items are good starting points
- If you have a uConsole, testing the device scripts and CLI is especially helpful
- Packaging improvements (the `.deb` build runs on macOS/Linux via `make build-deb`)

## Device scripts

The device-side code targets arm64 Debian Bookworm. Scripts are organized under `/opt/uconsole/scripts/` by category:

| Category | Examples | Notes |
|----------|----------|-------|
| `system/` | push-status, backup, restore, setup, doctor | Core functionality |
| `power/` | battery, charge, discharge-test | **Safety-critical** — extra review required |
| `network/` | wifi, hotspot, tailscale | Network management |
| `radio/` | sdr, lora, gps, rtc, marauder | AIO board features (optional hardware) |
| `util/` | forum browser, games, misc tools | Everything else |

The `example-device/` directory contains a scrubbed copy of the device tree that allows `.deb` builds without access to the private backup repo.

If you're modifying device-side code, test on actual hardware or an arm64 VM when possible.

## Packaging

The `.deb` package is built with `make build-deb` and published to the APT repo with `make publish-apt`. The full release flow (`make release`) bumps the version, builds, publishes, commits, and tags. GitHub Actions automates this on tagged releases.

See `packaging/` for the build script, control file, systemd units, nginx config, and avahi service definition.

## Questions?

Open an issue. There's no Discord or mailing list — GitHub issues are the place.
