---
description: "Sync shared files between uconsole-cloud and uconsole backup repo"
allowed-tools: Bash, Read, Edit, Glob, Grep, Write
---

Sync shared files between the uconsole-cloud install copies and the uconsole backup repo canonical copies.

## Shared Files

| Cloud (install copy) | Device (canonical) |
|---------------------|--------------------|
| `frontend/public/scripts/push-status.sh` | `~/uconsole/scripts/push-status.sh` |

## Process

1. Diff the two copies of each shared file
2. If they differ, show the diff and identify which is newer (git log)
3. The canonical copy (backup repo) is the source of truth
4. Sync canonical → install copy (not the other way)
5. Verify the JSON payload schema is identical in both copies
6. Run `bash -n` on both copies after sync
7. Report what changed

If $ARGUMENTS specifies a direction (e.g. "cloud → device"), use that instead.

Do NOT auto-commit. Show the diff and let the user decide.
