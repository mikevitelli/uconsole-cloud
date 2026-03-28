# Vercel Dashboard

## Overview

A web-based backup visualization dashboard deployed on Vercel at `uconsole.vercel.app`. It reads backup data from the private GitHub repo via serverless API proxies.

## Architecture

```
Browser -> Vercel (static HTML) -> /api/github.js -> GitHub API
                                -> /api/raw.js   -> raw.githubusercontent.com
```

- **Frontend**: Single HTML file with inline CSS/JS
- **Backend**: Two Vercel serverless functions (Node.js)
- **Auth**: Password gate (checked against `DASHBOARD_PASSWORD` env var)
- **GitHub token**: Stored as `GITHUB_TOKEN` env var on Vercel (never exposed to browser)

## Environment Variables

Set these in Vercel project Settings -> Environment Variables:

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub PAT with `repo` scope |
| `DASHBOARD_PASSWORD` | Password for the login screen |

## Sections

- **Package Inventory** — Donut charts + bar charts for all package managers
- **Backup Coverage** — Status grid showing what's backed up
- **Browser** — Chromium extension list
- **Scripts** — Manifest table from `scripts-manifest.txt`
- **Repository Structure** — File tree from GitHub API
- **Commit History** — 30-day sparkline + commit list
- **Repository Stats** — Size, branch, last push

## Updating

Push changes to `vercel-dashboard/` in the uconsole repo. Vercel auto-deploys from the `main` branch.

## Files

```
vercel-dashboard/
  index.html      # Full dashboard (single file)
  vercel.json     # Vercel config
  api/
    github.js     # Proxy for GitHub API
    raw.js        # Proxy for raw file content
```
