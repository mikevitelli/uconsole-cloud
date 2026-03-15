<div align="center">

# uConsole Cloud

**Monitor and manage your ClockworkPi uConsole system backups from anywhere.**

[![Live](https://img.shields.io/badge/live-uconsole.cloud-58a6ff?style=for-the-badge)](https://uconsole.cloud)

[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-v4-06b6d4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Sanity](https://img.shields.io/badge/Sanity-v3-f36458?style=flat-square&logo=sanity&logoColor=white)](https://sanity.io)
[![Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-black?style=flat-square&logo=vercel)](https://vercel.com)
[![License](https://img.shields.io/badge/license-private-444?style=flat-square)]()

<br/>

<img src="frontend/src/app/opengraph-image.png" alt="uConsole Cloud" width="280" />

</div>

---

## Overview

A full-stack dashboard that connects to your GitHub backup repository and gives you a real-time view of your uConsole system state — packages, extensions, scripts, configs, and more.

### Features

- **Backup Coverage** — status grid showing what's backed up (shell configs, packages, browser extensions, scripts, desktop settings, git/ssh)
- **Repository Stats** — repo size, branch, last push, visibility
- **Commit History** — 30-day sparkline and recent commit list
- **Package Inventory** — breakdown by manager (APT, Flatpak, Snap, Cargo, pip, ClockworkPi) with donut charts and horizontal bars
- **Browser Extensions** — Chromium extension inventory
- **Scripts Manifest** — table of backup scripts
- **Repository Structure** — file/directory tree with sizes
- **3D Landing** — interactive Sketchfab embed of the ClockworkPi uConsole
- **CMS** — Sanity Studio for system notes, backup logs, and device profiles

## Architecture

```
uconsole-dashboard/
├── frontend/          Next.js 16 dashboard app
│   ├── src/app/       App Router pages & API routes
│   ├── src/lib/       Auth, Redis, GitHub client, types
│   └── src/components Dashboard UI components
├── studio/            Sanity Studio CMS
│   └── schemaTypes/   System notes, backup logs, profiles
└── package.json       npm workspace root
```

### Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router, Server Components, Server Actions) |
| Auth | NextAuth v5 (GitHub OAuth) |
| Data | GitHub REST API, Upstash Redis |
| CMS | Sanity v3 (Structure Tool, Vision) |
| Styling | Tailwind CSS v4 (GitHub-dark theme) |
| Language | TypeScript 5 |
| Hosting | Vercel (frontend), Sanity Cloud (studio) |

## Environments

| Environment | Domain | Trigger |
|---|---|---|
| **Production** | [`uconsole.cloud`](https://uconsole.cloud) | Push to `main` |
| **Preview** | `uconsole-dashboard-*.vercel.app` | PRs & feature branches |
| **Local** | `localhost:3000` | `npm run dev` |

Each environment has its own GitHub OAuth app, environment variables, and callback URLs — configured in Vercel.

## Getting Started

### Prerequisites

- Node.js 20+
- [GitHub OAuth App](https://github.com/settings/developers) (one per environment)
- [Upstash Redis](https://console.upstash.com) database
- [Sanity](https://sanity.io) project

### Install

```bash
git clone https://github.com/mikevitelli/uconsole-dashboard.git
cd uconsole-dashboard
npm install
```

### Configure

**`frontend/.env.local`**

```env
GITHUB_ID=                    # GitHub OAuth Client ID
GITHUB_SECRET=                # GitHub OAuth Client Secret
AUTH_SECRET=                  # openssl rand -base64 33
UPSTASH_REDIS_REST_URL=       # Upstash REST endpoint
UPSTASH_REDIS_REST_TOKEN=     # Upstash REST token
```

**`studio/.env.local`**

```env
SANITY_STUDIO_PROJECT_ID=     # Sanity project ID
SANITY_STUDIO_DATASET=production
```

### Run

```bash
npm run dev        # starts frontend (:3000) and studio (:3333)
npm run build      # builds both workspaces
```

### OAuth Apps

Create one OAuth App per environment at **GitHub > Settings > Developer settings > OAuth Apps**:

| Environment | Homepage URL | Callback URL |
|---|---|---|
| Production | `https://uconsole.cloud` | `https://uconsole.cloud/api/auth/callback/github` |
| Preview | `https://uconsole-dashboard.vercel.app` | `https://uconsole-dashboard.vercel.app/api/auth/callback/github` |
| Local | `http://localhost:3000` | `http://localhost:3000/api/auth/callback/github` |

## Deploy

### Frontend → Vercel

Pushes to `main` auto-deploy via GitHub integration. Root directory is set to `frontend/`.

### Studio → Sanity Cloud

```bash
cd studio && npx sanity deploy
```

### CORS Origins

Add in [sanity.io/manage](https://sanity.io/manage) → API → CORS origins (with credentials):

- `https://uconsole.cloud`
- `http://localhost:3000`

## How It Works

1. **Sign in** with GitHub OAuth
2. **Select** your backup repository from the dropdown
3. **View** real-time dashboard of your system backup state
4. **Manage** supplementary content via Sanity Studio

---

<div align="center">

Built for the [ClockworkPi uConsole](https://www.clockworkpi.com/uconsole) community.

</div>
