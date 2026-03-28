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

## Making changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Run `npm test` and `npm run build` to verify nothing breaks
4. Open a pull request against `main`

## Code style

- TypeScript throughout, strict mode
- Server Components by default — only add `'use client'` when needed
- Tailwind CSS v4 for styling (GitHub-dark theme)
- Keep tests passing (138+ as of March 2026)

## What to work on

- Check [open issues](https://github.com/mikevitelli/uconsole-cloud/issues) for bugs or feature requests
- If you have a uConsole, testing the device scripts and CLI is especially helpful
- Packaging improvements (the `.deb` build runs on macOS via `make build-deb`)

## Device scripts

The device-side code targets arm64 Debian Bookworm. Scripts are organized under `/opt/uconsole/scripts/` by category (system, power, network, radio, util). Power scripts are **safety-critical** — changes to battery/charge logic require extra review.

If you're modifying device-side code, test on actual hardware or an arm64 VM when possible.

## Questions?

Open an issue. There's no Discord or mailing list — GitHub issues are the place.
