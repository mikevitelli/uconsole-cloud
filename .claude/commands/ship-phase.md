---
description: "Ship an entire phase from FEATURES.md — design UX, implement features, audit, test, commit"
allowed-tools: Agent, Bash, Read, Edit, Write, Glob, Grep
---

Ship Phase $ARGUMENTS from the feature map.

## Process

### 1. Load Phase
Read FEATURES.md. Extract all TODO items (`[ ]`) for the specified phase. Check that all dependencies from earlier phases are marked `[x]`.

If dependencies are unmet, STOP and report what's blocking.

### 2. Identify UX Design Needs
Check if the phase has a "UX Design Needed" section. If yes, for each UX item:
- Run the /design-ux flow (read-only, output design doc)
- Present designs to user for approval before proceeding

### 3. Group Implementation
Group the phase's features into implementation batches:
- Batch by repo (uconsole-cloud vs uconsole backup)
- Within each repo, batch by file cluster (features touching the same files go together)
- Independent features can be parallel; dependent features are sequential

### 4. Implement Each Batch
For each batch, run the /implement-feature flow:
- Explore → Plan → Implement → Test → Audit
- Present each batch's changes for review before moving to the next

### 5. Sync
If both repos were modified, run /sync-repos to ensure shared files match.

### 6. Final Verification
- `npm run build && npm test` (uconsole-cloud)
- `bash -n` on all modified shell scripts
- `python3 -m py_compile` on all modified Python files
- Full /audit-fix on all changed files

### 7. Report
Update FEATURES.md — mark completed items as `[x]`.
Present a summary of everything that was done, ready for commit.
