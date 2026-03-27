# Contributing

Thanks for your interest in uconsole-cloud! This project is a personal tool built for the ClockworkPi uConsole, but contributions are welcome.

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
- Tailwind CSS for styling (GitHub-dark theme)
- Keep tests passing (138+ as of March 2026)

## What to work on

- Check [open issues](https://github.com/mikevitelli/uconsole-cloud/issues) for bugs or feature requests
- The roadmap in README.md lists planned features
- If you have a uConsole, testing the device scripts and CLI is especially helpful

## Device scripts

The scripts in `packaging/` and `frontend/public/scripts/` run on arm64 Debian. If you're modifying device-side code, test on actual hardware or an arm64 VM when possible.

## Questions?

Open an issue. There's no Discord or mailing list — GitHub issues are the place.
