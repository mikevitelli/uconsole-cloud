# Self-hosting

Run your own cloud dashboard instead of using `uconsole.cloud`.

## 1. Deploy the Next.js app

Vercel, Netlify, or any Next.js host. Required env vars:

| Variable | Purpose |
|---|---|
| `GITHUB_ID` / `GITHUB_SECRET` | GitHub OAuth app credentials |
| `AUTH_SECRET` | NextAuth JWT secret (`openssl rand -base64 33`) |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Redis credentials (Upstash free tier works) |

## 2. Point your device at it

After `apt install uconsole-cloud`:

```bash
sudoedit /etc/uconsole/status.env
# DEVICE_API_URL=https://your-domain.com/api/device/push
uconsole setup
```

## 3. Host your own APT repo (optional)

```bash
bash packaging/scripts/generate-gpg-key.sh
make build-deb
make publish-apt
```

The signed repo lives in `frontend/public/apt/` and is served by whatever hosts your frontend.
