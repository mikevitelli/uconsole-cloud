# uConsole Dashboard

A monorepo for monitoring and managing system backup repositories on GitHub. Built with Next.js and Sanity Studio.

**Production:** [uconsole.cloud](https://uconsole.cloud)

## Structure

```
├── frontend/     Next.js 16 dashboard app
├── studio/       Sanity Studio CMS
└── package.json  Workspace root
```

## Frontend

The dashboard authenticates via GitHub OAuth and displays data from a linked backup repository:

- **Backup Coverage** — status grid showing what's backed up (shell configs, packages, browser extensions, scripts, desktop settings, git/ssh)
- **Repository Stats** — repo size, branch, last push, visibility
- **Commit History** — 30-day sparkline and recent commit list
- **Package Inventory** — breakdown by manager (APT, Flatpak, Snap, Cargo, pip, ClockworkPi) with donut charts and horizontal bars
- **Browser Extensions** — Chromium extension inventory
- **Scripts Manifest** — table of backup scripts
- **Repository Structure** — file/directory tree with sizes
- **3D Model** — interactive Sketchfab embed of the ClockworkPi uConsole on the landing page

### Tech

- Next.js 16 (App Router, Server Components, Server Actions)
- NextAuth v5 (GitHub OAuth)
- Upstash Redis (user settings persistence)
- Tailwind CSS v4 (GitHub-dark theme)
- TypeScript 5

## Studio

Sanity Studio for managing dashboard content:

- **System Notes** — categorized notes (packages, config, scripts, hardware, general) with pinning
- **Backup Logs** — timestamped entries with status tracking (success/partial/failed) and module coverage
- **System Profiles** — device inventory with hostname, OS, device type, and linked backup repos

### Tech

- Sanity v3 (Structure Tool, Vision)
- TypeScript 5

## Deployment

### Environments

| Environment | Domain | Trigger |
|---|---|---|
| Production | [uconsole.cloud](https://uconsole.cloud) | Push to `main` or `vercel --prod` |
| Preview | `uconsole-dashboard-*.vercel.app` | PRs, non-main branches, or `vercel` |
| Local | `localhost:3000` | `npm run dev` |

Each environment uses its own GitHub OAuth app and environment variables, configured in Vercel.

### Frontend (Vercel)

The frontend is deployed to [Vercel](https://vercel.com) with the root directory set to `frontend/`. Pushes to `main` trigger production deployments automatically via GitHub integration.

### Studio (Sanity Cloud)

Deploy the studio from the `studio/` directory:

```bash
cd studio && npx sanity deploy
```

### CORS Origins (Sanity)

Add these in [sanity.io/manage](https://sanity.io/manage) → API → CORS origins (with credentials):

- `https://uconsole.cloud`
- `http://localhost:3000`

## Setup

### Prerequisites

- Node.js 20+
- GitHub OAuth App (one per environment)
- Upstash Redis database
- Sanity project

### Environment Variables

**`frontend/.env.local`**

```env
GITHUB_ID=           # GitHub OAuth App Client ID
GITHUB_SECRET=       # GitHub OAuth App Client Secret
AUTH_SECRET=          # openssl rand -base64 33
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
```

**`studio/.env.local`**

```env
SANITY_STUDIO_PROJECT_ID=
SANITY_STUDIO_DATASET=production
```

### Install & Run

```bash
npm install        # installs all workspaces
npm run dev        # starts frontend (:3000) and studio (:3333) in parallel
npm run build      # builds both workspaces
```

### GitHub OAuth Apps

Create a separate OAuth App per environment at **GitHub > Settings > Developer settings > OAuth Apps**:

| Environment | Homepage URL | Callback URL |
|---|---|---|
| Production | `https://uconsole.cloud` | `https://uconsole.cloud/api/auth/callback/github` |
| Preview | `https://uconsole-dashboard.vercel.app` | `https://uconsole-dashboard.vercel.app/api/auth/callback/github` |
| Local | `http://localhost:3000` | `http://localhost:3000/api/auth/callback/github` |

## How It Works

1. Sign in with GitHub
2. Select your backup repository from the dropdown (or enter manually)
3. Dashboard fetches and displays repo data via GitHub API
4. Sanity Studio manages supplementary content (notes, logs, profiles)
