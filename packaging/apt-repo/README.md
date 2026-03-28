# APT Repository

This directory documents the APT repository structure hosted at `uconsole.cloud/apt/`.

## Repository Structure

```
frontend/public/apt/
├── dists/
│   └── stable/
│       ├── main/
│       │   └── binary-arm64/
│       │       ├── Packages          # Package index (plain text)
│       │       └── Packages.gz       # Compressed package index
│       ├── Release                   # Repository metadata (signed)
│       └── InRelease                 # Inline-signed Release
└── pool/
    └── main/
        └── u/
            └── uconsole-tools/
                └── uconsole-tools_X.Y.Z_arm64.deb
```

## How It Works

1. The `.deb` file is built with `make build-deb`
2. `make publish-apt` runs `generate-repo.sh` which:
   - Copies the .deb into the pool directory
   - Generates `Packages` and `Packages.gz` indexes
   - Generates `Release` with checksums
   - Signs `Release` → `InRelease` (GPG inline signature)
3. The files under `frontend/public/apt/` are served statically by Next.js/Vercel
4. Users add the repo with `curl -s https://uconsole.cloud/install | sudo bash`

## Publishing a New Version

```bash
# 1. Bump version
make bump-patch   # or bump-minor / bump-major

# 2. Build and publish
make release      # builds .deb, updates apt repo, commits + tags
```

## GPG Key Setup (One-Time)

```bash
bash packaging/scripts/generate-gpg-key.sh
```

This creates a GPG key for signing the repository. The public key is exported to
`frontend/public/apt/uconsole.gpg` for distribution.

## Manual Repo Generation

```bash
bash packaging/scripts/generate-repo.sh dist/uconsole-tools_0.1.0_arm64.deb
```
