---
description: "Sync shared files between uconsole-cloud and uconsole backup repo"
allowed-tools: Bash, Read, Edit, Glob, Grep, Write
---

Sync shared files between the uconsole-cloud canonical source and the uconsole backup repo.

## Shared Files

| Cloud (canonical) | Backup (copy) |
|-------------------|---------------|
| `device/scripts/system/push-status.sh` | `~/pkg/scripts/system/push-status.sh` |
| `frontend/public/scripts/push-status.sh` | (cloud-side install copy) |

## Process

1. Diff the two copies of each shared file
2. If they differ, show the diff and identify which is newer (git log)
3. The canonical copy (uconsole-cloud device/) is the source of truth
4. Sync canonical → backup copy (cloud → device backup)
5. Verify the JSON payload schema is identical in both copies
6. Run `bash -n` on both copies after sync
7. Report what changed

If $ARGUMENTS specifies a direction (e.g. "backup → cloud"), use that instead.

Do NOT auto-commit. Show the diff and let the user decide.
