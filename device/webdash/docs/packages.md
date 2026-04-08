# Package Inventory

## Summary

| Manager | Count | Manifest |
|---------|-------|----------|
| APT | 2,405 | `packages/apt-manual.txt` |
| Snap | 12 | `packages/snap.txt` |
| ClockworkPi | 13 | `packages/clockworkpi.txt` |
| Flatpak | 10 | `packages/flatpak.txt` |
| pip (user) | 9 | `packages/pip-user.txt` |
| Cargo | 1 | `packages/cargo.txt` |
| npm (global) | 0 | `packages/npm-global.txt` |
| **Total** | **~2,450** | |

## How Manifests Are Generated

Run `backup.sh packages` or `update.sh snapshot` to regenerate all manifests.

- **APT**: `apt-mark showmanual` (manually installed only, not dependencies)
- **Flatpak**: `flatpak list --app --columns=application`
- **Snap**: `snap list`
- **Cargo**: `cargo install --list`
- **pip**: `pip3 list --user --format=freeze`
- **npm**: `npm list -g --depth=0`
- **ClockworkPi**: Custom package list from Clockwork's APT repo

## Restoring Packages

The restore script reads each manifest and reinstalls:

```
xargs -a packages/apt-manual.txt sudo apt install -y
flatpak install --noninteractive $(cat packages/flatpak.txt)
```
