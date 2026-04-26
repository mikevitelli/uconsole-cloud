# Wardrive × WiGLE Explorer — Design

**Date:** 2026-04-19
**Status:** Wardrive functionality shipped in `51b4945` (wip/wardrive-map → dev, 2026-04-25). WiGLE enrichment lives in `device/webdash/app.py` (`_wigle_*` family at lines 1898–2068); HTML viewer in `device/webdash/templates/wardrive.html`. The TUI BSSID lookup panel (originally planned at `device/lib/tui/wigle.py`) was not built — webdash modal covers that need. The daily quota-probe cron was retired on 2026-04-26; see Commit trail.
**Author:** mikevitelli (via session with Claude)

## Why this doc exists

I almost built a ten-hour feature on top of three unverified assumptions. This
document is the Linus pass on that idea: state the actual problem, cut
everything that doesn't solve it, prove the premises before writing code, and
ship the smallest thing that could possibly be useful.

## The actual problem

The `/wardrive` ALL SESSIONS view shows 8,845 unique APs. None of them tell me
anything beyond SSID/BSSID/signal. I want to know **which of my APs aren't in
WiGLE's global database** — that is the single piece of information worth
spending API quota on, because it's the one thing WiGLE can tell me that I
can't derive locally. It is also the one thing that has an emotional payoff:
APs I caught that nobody else has logged yet.

Everything else the WiGLE API can do (area search, SSID search, personal
stats, history) is *interesting*, not *useful*. Until I'm uploading data, the
stats are zero; until I'm traveling somewhere new, area search duplicates
what's already on wigle.net's regular map.

## What we are building

Exactly two things:

### 1. "First Discovery" color mode on `/wardrive`

A third toggle alongside Signal and Security. Gold dots for APs where
`wigle_cache.status == 'not_found'`. Gray dots for APs WiGLE already knows.
Uncached APs stay the default color.

Menu badge: `🏆 N first-discovery candidates / M checked`.

That's the whole feature. One color expression, one legend, one count. The
existing enrichment pipeline already populates `status`; we are just
presenting it.

### 2. TUI BSSID lookup panel

One screen. One purpose. Type a MAC, see what WiGLE knows about it globally.
Cached forever. Reachable from the `console` root menu as a sibling of
Marauder.

No sub-menus. No "Nearby" panel. No "Search" panel. No "Me" stats screen. No
recent-queries history. Those are all speculative features that solve
problems I don't have yet.

## What we are NOT building (and why)

- **Five-panel TUI explorer.** The original pitch had Nearby / Search / BSSID
  / Me / Recent. Four of those solve imaginary problems:
  - *Nearby* only helps if I'm somewhere unfamiliar and my phone is dead.
    Unlikely enough that it's not worth the cache-invalidation complexity.
  - *Search* is a worse version of wigle.net's browser search, on a 720×720
    screen.
  - *Me* is zero until uploads start. We decided uploads are off-limits
    (data quality). So it's meaningless indefinitely.
  - *Recent* is a meta-feature that solves a navigation problem that doesn't
    exist in a one-panel design.

- **Area-enrichment endpoint.** I was about to build a bounding-box variant
  of `/api/wigle/enrich` to batch lookups more efficiently. I have no
  evidence the existing per-BSSID path is the bottleneck. I haven't yet seen
  a successful enrichment run (the daily quota burned before we shipped the
  UI). Build this only if per-BSSID enrichment proves insufficient *after*
  observing actual usage for a week.

- **Probe-request geolocation, WiGLE overlay layer, client tracking,**
  anything else from the earlier brainstorm. Each is a separate project with
  its own premises to validate. Conflating them here is how ten-hour
  estimates become hundred-hour estimates.

## Premises we must validate first

Before writing any of the code above:

### P1: WiGLE's free-tier daily cap

We burned today's allotment on ~5 auth-test queries. We need to know whether
the cap is 5, 10, 100, or something else. Method: at 00:05 UTC tomorrow,
issue one authenticated query, record the response. Issue nine more. Record
when 429 first appears. Commit the count to this doc as *"free-tier
observed daily cap: N"*.

If N ≤ 10, the whole WiGLE-enrichment direction is effectively dead without a
donor upgrade, and we should stop here.

If N is ~100, both features remain viable as described.

### P2: First-discovery density

If 95% of my BSSIDs are already in WiGLE, the gold-dot feature is
underwhelming. Method: after enrichment of a small sample (~25 APs, one
quota-day), compute the fraction marked `not_found`. Commit observed rate to
this doc.

Acceptable threshold: ≥10% first-discovery rate. Below that, reconsider
whether the feature is interesting enough to implement.

### P3: TUI menu integration point

I don't actually know where the root `console` TUI menu is registered.
Grep turned up `lib/tui/marauder.py` but not the parent launcher. Method:
find the entry point before I start, not after. Commit the file path here.

## Architecture notes

### Caching is non-negotiable

The existing `~/esp32/marauder-logs/wigle-cache.sqlite` is the single source
of truth. TUI lookups and webdash enrichment share it. A query answered from
cache must cost zero quota. If I ever see the same BSSID queried twice in
the same year, the design is wrong.

### TTL per query kind

| Kind | TTL | Reason |
|---|---|---|
| BSSID detail | Forever | WiGLE's data on a given BSSID rarely changes |
| Rate-limit backoff flag | 23 hours | Free tier resets at 00:00 UTC |

No other query kinds in scope.

### Failure modes

- **401 auth error:** surface "WiGLE token invalid — check `~/.config/uconsole/wigle.env`"
- **403 email-unverified:** surface verification URL
- **412 email-unverified (older response):** same as 403
- **429 rate-limit:** set backoff flag, refuse further calls for 23h, tell user when reset is
- **Network error / timeout (10s):** treat as transient, don't mark cache, let user retry

All five cases are already handled by the existing `_wigle_query_one` function.
No new error handling needed for first-discovery mode or the TUI panel.

## File changes

### Webdash (`uconsole-cloud/device/webdash/`)

- `templates/wardrive.html`
  - Add "First Discovery" as a third option in the Color-by menu
  - Extend `SEC_COLORS` / `applyApColor()` with a `first-discovery` branch
  - Extend `updateLegend()` with first-discovery legend rows
  - Add first-discovery count to the menu stats widget
  - Target LOC: ~40

- `app.py`
  - No changes. The existing `/api/wigle/cached` endpoint already exposes
    `status`, which is all we need.

### TUI (`uconsole-cloud/device/lib/tui/`)

- Create `wigle.py` — BSSID lookup panel only
  - Single screen: MAC input at top, result card below
  - Reads token from `~/.config/uconsole/wigle.env`
  - Reads/writes the same `wigle-cache.sqlite`
  - Uses `urllib.request` directly (no new deps)
  - Same 5-status branching as webdash
  - Target LOC: ~180

- Edit root TUI menu (path TBD per P3) — add one line:
  `("WiGLE Lookup", "Query a BSSID in WiGLE", "◉")`

No other files touched.

## Testing strategy

- **Manual, visual, real data.** This is user-facing and small enough that
  unit tests are overkill.
- **First-discovery color mode:** enrich ~25 BSSIDs, confirm gold dots appear
  for the `not_found` ones, confirm count matches.
- **TUI BSSID lookup:** type a known-in-WiGLE MAC, confirm result card
  renders. Type an obscure one, confirm "not found" display. Second lookup
  of the same MAC must hit cache (no API call — verified by `queries_today`
  unchanged).
- No regression testing needed on existing `/wardrive` features beyond
  "does the page still load with the new color mode off."

## Build order and exit criteria

1. **Validate premises.** P1 tomorrow at 00:05 UTC. P2 after a small
   enrichment sample. P3 via one grep. Commit observed values to this doc
   before writing any code.
2. **Webdash first-discovery color mode.** Ship. Test with the P2 sample.
3. **TUI BSSID lookup panel.** Ship. Test against five real BSSIDs.
4. **Stop.** Use it for at least one drive. Decide whether anything is
   actually missing before touching any of the skipped features.

Estimated effort: 3–4 hours of focused work. Down from the original ten.

## Appendix: things we considered and rejected

- **Upload path.** Pollutes WiGLE with placeholder AuthMode. Decided off.
- **Firmware patch to add encryption column.** Viable but risky (flash). On
  hold until the monitor-mode USB adapter arrives, at which point Kismet
  makes this moot.
- **Kismet on uConsole.** Waiting on monitor-mode USB adapter. Separate doc
  when that happens.
- **Parallel `iw scan` during drives.** Too narrow (wlan0 only sees close
  2.4 GHz APs). Cleaner to wait for proper hardware.

## Appendix: rate-limit math

At `N = 100 queries/day` (optimistic free-tier assumption):

- 8,845 unique BSSIDs
- 100/day → 88 days to enrich everything via per-BSSID lookups
- Realistic usage: enrich only the ~500 strongest-signal APs. That's a
  5-day burn. Weekly drives refresh the interesting set.

At `N = 10 queries/day` (pessimistic), the feature is effectively a toy.
Good to know before we build.

## Commit trail

- 2026-04-19: draft written, awaiting P1/P2/P3 validation
- 2026-04-26: probe cron retired, premises P1/P2 resolved (see below), spec corrected

### Premise resolution (consolidated 2026-04-26)

The probe ran daily from 2026-04-20 through 2026-04-26 (logs in
`~/.local/share/wigle-probe/`). Of seven runs, five were either
header-only (process killed before first query, likely device sleep) or
hit 429 immediately because earlier auth tests / earlier runs had
already burned the day's quota. **One run produced real signal:**

| Run | Queries sent | 200 OK | 429 at | First-discovery |
|---|---|---|---|---|
| 20260420T040502Z | 1 | 0 | #1 | no data — quota burned earlier |
| 20260421T040501Z | 2+ (truncated) | ≥2 | — | partial |
| 20260422T040501Z | 0 | 0 | — | run interrupted |
| **20260423T040501Z** | **6** | **5** | **#6** | **3/5 = 60%** |
| 20260424T040501Z | 0 | 0 | — | run interrupted |
| 20260425T040502Z | 0 | 0 | — | run interrupted |
| 20260426T040502Z | 1 | 0 | #1 | no data — quota burned earlier |

**P1 (daily cap):** observed cap is **5–6 successful queries before
first 429**. Well below the 100/day optimistic case in the rate-limit
math appendix. Above the ≤10 kill threshold the spec set, so the
direction is not formally dead — but enrich-everything is impractical
(8,845 BSSIDs ÷ 5/day ≈ 4.8 years).

**P2 (first-discovery rate):** observed **60%** on the one valid run.
Well above the spec's ≥10% acceptability bar. The "First Discovery"
color mode is viable on the data we have, though it should be
re-validated with a larger sample if/when quota allows.

**P3 (TUI menu integration point):** moot — the TUI lookup panel was
never built. Webdash's enrichment modal covers the same need.

### Why the cron was retired

1. **Quota cannibalism.** The probe fired at 00:05 UTC daily and burned
   the day's free-tier quota before the user could use it during a
   wardrive. Webdash's "Enrich now" button got rate-limited every time.
2. **Forked state.** The probe wrote to `wigle-cache.sqlite` but didn't
   coordinate with `device/webdash/app.py`'s `wigle_meta.last_429_at`
   23h-backoff marker. Webdash's authoritative path was the right place
   for quota state; the probe ran blind.
3. **Misleading reporting.** When the probe hit 429 at query #1, it
   wrote `0/0 = 0.0%` to this doc — mathematically wrong, semantically
   "feature is dead." The correct read is "no data — quota burned
   earlier." This was a reporting bug masquerading as a kill signal.

The probe script was archived to `device/scripts/util/wigle-quota-probe.py`
with the no-data labeling fixed and a header explaining its history.
Manually runnable; no longer cron-scheduled.

### Recommendation going forward

Use webdash's existing enrichment path for actual work. Target the
strongest-signal ~500 BSSIDs over a 100-day burn (per the rate-limit
math appendix). If the daily cap policy ever changes, run the archived
probe manually to re-measure.
