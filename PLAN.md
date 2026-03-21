# Refactoring Plan: Address the Honest List

## Phase 1: Break Up the God Page (`page.tsx`)

**Goal**: Split the 268-line monolithic `page.tsx` into focused server components.

### Step 1.1: Extract auth gate pages into standalone components

Create 3 new server components that `page.tsx` currently renders inline:

- `src/components/pages/LandingPage.tsx` — the unauthenticated landing (Sketchfab embed + sign-in button). Props: `content` (Sanity content).
- `src/components/pages/LinkRepoPage.tsx` — the "link your repo" screen. Props: `session`, `content`.
- `src/components/pages/SessionExpiredPage.tsx` — the "session expired, sign out" screen. No props needed beyond `content`.

### Step 1.2: Extract data fetching + transformation into `lib/fetchDashboardData.ts`

Move lines 130-186 of `page.tsx` into a dedicated async function:

```ts
// lib/fetchDashboardData.ts
export async function fetchDashboardData(accessToken: string, repo: string): Promise<DashboardData>
```

This function will:
- Run the 7 parallel fetches (`Promise.all`)
- Transform raw GitHub responses into typed domain objects (`BackupEntry[]`, `TreeEntry[]`, etc.)
- Compute derived values (`totalPackages`, `aptCategories`, `deviceAgeMinutes`)
- Return a single `DashboardData` interface

Add the `DashboardData` type to `lib/types.ts`.

### Step 1.3: Extract dashboard layout into `components/pages/DashboardPage.tsx`

Move the rendered dashboard (lines 189-267) into a server component:

```ts
// Props: DashboardData + session + content
export function DashboardPage({ data, session, content }: DashboardPageProps)
```

### Step 1.4: Extract GitHub error UI into `components/pages/GitHubErrorPage.tsx`

Move the catch block UI (lines 143-159) into its own component.

### Result: `page.tsx` becomes ~30 lines

```ts
export default async function Home() {
  const session = await auth();
  const content = await fetchSiteContent();

  if (!session) return <LandingPage content={content} />;

  const settings = await getUserSettings(session.user.id);
  if (!settings?.repo) return <LinkRepoPage session={session} content={content} />;
  if (!session.accessToken) return <SessionExpiredPage content={content} />;

  try {
    const data = await fetchDashboardData(session.accessToken, settings.repo);
    return <DashboardPage data={data} session={session} content={content} />;
  } catch (err) {
    if (err instanceof GitHubError) return <GitHubErrorPage error={err} content={content} />;
    throw err;
  }
}
```

---

## Phase 2: Refactor `BackupTimeline.tsx`

**Goal**: Reduce from 407 lines / 8 state variables to focused, testable pieces.

### Step 2.1: Extract `FilePreviewModal` to its own file

Move `FilePreviewModal` (lines 15-96) to `src/components/dashboard/FilePreviewModal.tsx`. It's already a self-contained component with its own props interface.

### Step 2.2: Extract state logic into `useBackupTimeline` custom hook

Create `src/hooks/useBackupTimeline.ts`:

```ts
export function useBackupTimeline(backups: BackupEntry[]) {
  // All 8 state variables
  // toggleExpand, openFilePreview callbacks
  // categoryCounts, pillItems, filtered, visible computations
  // Returns: { expandedSha, showAll, selectedCategory, details, loading,
  //            preview, commitError, toggleExpand, openFilePreview,
  //            pillItems, filtered, visible, setShowAll, setSelectedCategory,
  //            setPreview, backupCount, manualCount }
}
```

### Step 2.3: Slim down `BackupTimeline.tsx`

After extraction, `BackupTimeline.tsx` becomes ~150 lines of pure rendering that calls the hook and renders `FilePreviewModal`.

---

## Phase 3: Split `utils.ts` by Domain

**Goal**: Replace the 151-line catch-all with focused modules.

### Step 3.1: Create domain-specific utility files

- `src/lib/formatting.ts` — `fmtDate`, `fmtSize`, `fmtBytes`, `parseLines`
- `src/lib/categories.ts` — `CATEGORY_COLORS`, `CATEGORY_LABELS`, `categoryLabel`, `getLastBackupByCategory`
- `src/lib/freshness.ts` — `daysSince`, `ageLabel`, `freshnessColor`
- `src/lib/backupParsing.ts` — `parseBackupMessage`, `parseScriptsManifest` (+ the 3 regexes)

### Step 3.2: Make `utils.ts` a re-export barrel

```ts
// utils.ts — backwards-compatible re-exports
export { fmtDate, fmtSize, fmtBytes, parseLines } from "./formatting";
export { CATEGORY_COLORS, CATEGORY_LABELS, categoryLabel, getLastBackupByCategory } from "./categories";
export { daysSince, ageLabel, freshnessColor } from "./freshness";
export { parseBackupMessage, parseScriptsManifest } from "./backupParsing";
```

This keeps all existing imports working. Callers can optionally migrate to direct imports later.

### Step 3.3: Update existing tests

Move test assertions in `__tests__/utils.test.ts` to match new file structure — or keep them importing from `utils.ts` barrel (both work, barrel approach is zero-risk).

---

## Phase 4: Add Component Tests

**Goal**: Add `@testing-library/react` tests for the extracted components.

### Step 4.1: Set up testing infrastructure

- Install `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`
- Update `vitest.config.ts`: change environment from `"node"` to `"jsdom"` for component test files (use vitest workspace or `environmentMatchGlobs`)
- Add test setup file for `@testing-library/jest-dom` matchers

### Step 4.2: Write tests for extracted page components

- `__tests__/components/LandingPage.test.tsx` — renders sign-in button, Sketchfab embed, Sanity content fallbacks
- `__tests__/components/LinkRepoPage.test.tsx` — renders user avatar, repo linker form, sign-out button
- `__tests__/components/SessionExpiredPage.test.tsx` — renders error message and sign-out link
- `__tests__/components/GitHubErrorPage.test.tsx` — renders correct message for 401 vs 403

### Step 4.3: Write tests for `fetchDashboardData`

- `__tests__/fetchDashboardData.test.ts` — mock GitHub/Redis calls, verify data transformation, verify `GitHubError` propagation

### Step 4.4: Write tests for `useBackupTimeline` hook

- `__tests__/hooks/useBackupTimeline.test.ts` — use `renderHook` from testing-library
  - Test category filtering
  - Test expand/collapse toggle
  - Test show all / show less
  - Test commit detail fetch + caching (mock fetch)
  - Test file preview fetch

### Step 4.5: Write tests for `FilePreviewModal`

- `__tests__/components/FilePreviewModal.test.tsx` — renders filename, loading state, content with line numbers, error state, Escape key closes

---

## Phase 5: Address Remaining Items

### Step 5.1: Pin NextAuth version

Update `package.json` to pin `next-auth` to exact version instead of `^5.0.0-beta.30`:
```json
"next-auth": "5.0.0-beta.30"
```
This prevents accidental beta upgrades. Add a comment in the code noting to upgrade when v5 stable ships.

### Step 5.2: Add `.env.example`

Create `frontend/.env.example` documenting all required environment variables with placeholder values.

### Step 5.3: Add GitHub Actions CI

Create `.github/workflows/ci.yml`:
- Trigger: push to `main`, `staging`, PRs
- Jobs: `lint` (eslint), `typecheck` (tsc --noEmit), `test` (vitest run), `build` (next build)
- Uses Node 22, npm ci, workspace-aware

---

## Execution Order & Dependencies

```
Phase 1 (God page) ──→ Phase 4.2 (page component tests)
                   ──→ Phase 4.3 (fetchDashboardData tests)

Phase 2 (BackupTimeline) ──→ Phase 4.4 (hook tests)
                          ──→ Phase 4.5 (modal tests)

Phase 3 (utils split) ──→ Phase 4 uses new imports

Phase 4.1 (test setup) ──→ all Phase 4 tests

Phase 5 (remaining) ──→ independent, can run anytime
```

Phases 1, 2, 3 are independent of each other and can be done in parallel.
Phase 4.1 (test infra) must come before 4.2-4.5.
Phase 5 is independent of everything.

---

## Files Created/Modified Summary

**New files (12):**
- `src/components/pages/LandingPage.tsx`
- `src/components/pages/LinkRepoPage.tsx`
- `src/components/pages/SessionExpiredPage.tsx`
- `src/components/pages/GitHubErrorPage.tsx`
- `src/components/pages/DashboardPage.tsx`
- `src/components/dashboard/FilePreviewModal.tsx`
- `src/hooks/useBackupTimeline.ts`
- `src/lib/fetchDashboardData.ts`
- `src/lib/formatting.ts`
- `src/lib/categories.ts`
- `src/lib/freshness.ts`
- `src/lib/backupParsing.ts`

**Modified files (5):**
- `src/app/page.tsx` — slimmed to ~30 lines
- `src/components/dashboard/BackupTimeline.tsx` — slimmed to ~150 lines
- `src/lib/utils.ts` — converted to re-export barrel
- `src/lib/types.ts` — add `DashboardData` interface
- `vitest.config.ts` — add jsdom environment for component tests

**New test files (5):**
- `src/__tests__/components/LandingPage.test.tsx`
- `src/__tests__/components/LinkRepoPage.test.tsx`
- `src/__tests__/components/SessionExpiredPage.test.tsx`
- `src/__tests__/components/GitHubErrorPage.test.tsx`
- `src/__tests__/hooks/useBackupTimeline.test.ts`
- `src/__tests__/components/FilePreviewModal.test.tsx`
- `src/__tests__/fetchDashboardData.test.ts`

**New config files (3):**
- `frontend/.env.example`
- `.github/workflows/ci.yml`
- `src/__tests__/setup.ts` (testing-library setup)

**New dev dependencies (3):**
- `@testing-library/react`
- `@testing-library/jest-dom`
- `jsdom`
