---
description: "Implement a feature from FEATURES.md with codebase exploration, implementation, testing, and audit"
allowed-tools: Agent, Bash, Read, Edit, Write, Glob, Grep
---

Implement a feature from the uconsole ecosystem. The feature description is: $ARGUMENTS

## Process

### Step 1: Locate in Feature Map
Read `FEATURES.md` at the repo root and find the feature. Identify:
- Which phase it belongs to
- What dependencies it has (are prerequisite features done?)
- Which repo(s) it touches (uconsole-cloud, uconsole backup, or both)

If the feature has unmet dependencies, STOP and report what needs to be done first.

### Step 2: Explore
Read the CLAUDE.md for the relevant repo(s). Then use Explore agents to understand:
- Existing code that this feature touches or extends
- Similar patterns already in the codebase
- Test files that need updating

### Step 3: Plan
Present a concise implementation plan:
- Files to create/modify
- Key decisions or trade-offs
- Anything that needs user input

Wait for user approval before proceeding.

### Step 4: Implement
Make the changes. For each file:
- Read before editing
- Follow existing patterns and conventions
- Verify syntax after changes

### Step 5: Test
- Run `npm run build` and `npm test` (uconsole-cloud)
- Run `bash -n` on any modified shell scripts
- Run `python3 -m py_compile` on any modified Python files

### Step 6: Audit
Run the equivalent of /audit-fix (Phase 2 only — audit, no separate implementation) on the changed files. Report any findings.

### Step 7: Update Feature Map
Mark the feature as `[x]` done in FEATURES.md.

Do NOT commit. Present the changes for user review.
