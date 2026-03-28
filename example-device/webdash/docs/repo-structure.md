# Repository Structure

## Overview

This monorepo backs up and restores a Clockwork Pi uConsole. Configs are **symlinked** back to the repo so edits are automatically git-tracked. System files are **copied** (they live outside `~/`).

## Directories

| Directory | Purpose | Method |
|-----------|---------|--------|
| `shell/` | Login shell configs (`.bashrc`, `.profile`, `.gitconfig`, etc.) | Symlinked to `~/` |
| `system/` | Root-level configs (`/boot`, `/etc`) | Copied |
| `packages/` | Package manifest snapshots | Generated |
| `scripts/` | Utility and maintenance scripts | Direct |
| `config/` | `~/.config/` app configs (retroarch, openttd, gh, chromium) | Symlinked |
| `dotfiles/` | `~/.*` app configs (emulationstation, etc.) | Symlinked |
| `retropie/` | RetroPie BIOS, menus, ROM directory structure | Direct (ROMs excluded) |
| `emulators/` | Standalone emulator binaries (gearboy, mupen64) | Direct |
| `drivers/` | Hardware drivers (TP-Link WiFi) | Direct |
| `docs/` | Wiki documentation (this!) | Direct |
| `desktop/` | Desktop environment configs (dconf, themes) | Backed up |
| `ssh/` | SSH public keys | Direct (private keys excluded) |
| `bios/` | Emulator BIOS files | Direct |
| `vercel-dashboard/` | Vercel-deployed backup visualization dashboard | Direct |

## Key Files

- `restore.sh` — Automated restore script (symlinks configs, copies system files, reinstalls packages)
- `CLAUDE.md` — AI assistant instructions for this repo
- `.gitignore` — Excludes ROMs, private keys, caches, large regenerable dirs

## Symlinked Configs

These files in `~/` are symlinks pointing back into the repo:

- `~/.bashrc` -> `shell/.bashrc`
- `~/.profile` -> `shell/.profile`
- `~/.gitconfig` -> `shell/.gitconfig`
- `~/.xsessionrc` -> `shell/.xsessionrc`
- `~/.dmrc` -> `shell/.dmrc`
- `~/.config/retroarch` -> `config/retroarch`
- `~/.config/openttd` -> `config/openttd`
- `~/.emulationstation` -> `dotfiles/.emulationstation`
