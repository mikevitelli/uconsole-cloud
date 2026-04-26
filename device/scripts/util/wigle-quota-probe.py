#!/usr/bin/env python3
"""WiGLE free-tier daily quota probe — ARCHIVED (manual-run only).

Originally a daily cron job to validate two premises in the wardrive×WiGLE
explorer spec (docs/specs/2026-04-19-wardrive-wigle-explorer.md):
  P1: WiGLE free-tier daily query cap
  P2: First-discovery density (fraction of local BSSIDs not in WiGLE)

Both premises were resolved by the 2026-04-23 run: cap >= 5-6 successful
queries, first-discovery rate ~60%. The cron entry was retired on
2026-04-26 because:
  - Continuing to probe daily burns the user's free-tier quota at 00:05 UTC,
    leaving zero queries available for actual webdash enrichment during the
    day.
  - The probe forks the cache state from webdash's authoritative path
    (device/webdash/app.py uses the same wigle-cache.sqlite but tracks 23h
    backoff in a wigle_meta table this script doesn't read or write).
  - Every probe run that hits 429 at query #1 produces a misleading
    "0/0 = 0.0% first-discovery" entry in the spec, which reads as
    "feature is dead" but actually means "no data — quota already burned."

Kept here as a manually-runnable diagnostic. Useful if WiGLE changes their
cap policy or you want to re-validate from scratch:

  python3 device/scripts/util/wigle-quota-probe.py

Outputs:
  - ~/.local/share/wigle-probe/run-<timestamp>.log (full trace)
  - Appends a result block to the spec doc

Notes for future self:
  - Webdash already has a 23h backoff in wigle_meta.last_429_at — the
    correct way to integrate quota awareness is to read/write that table,
    not to maintain a parallel state in this script.
  - Community survey of 10 popular WiGLE clients (2026-04-26) found none
    persist a cross-run cooldown marker; webdash's wigle_meta is the
    state-of-the-art pattern for this use case.
"""

import base64
import csv
import glob
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENV_FILE = Path.home() / ".config" / "uconsole" / "wigle.env"
CACHE_DB = Path.home() / "esp32" / "marauder-logs" / "wigle-cache.sqlite"
LOG_DIR = Path.home() / ".local" / "share" / "wigle-probe"
SPEC_DOC = Path.home() / "uconsole-cloud" / "docs" / "specs" / "2026-04-19-wardrive-wigle-explorer.md"
CSV_GLOB = str(Path.home() / "esp32" / "marauder-logs" / "wardrive-*.csv")

MAX_QUERIES = 150
INTERVAL_SEC = 6
API = "https://api.wigle.net/api/v2/network/search"
BSSID_RE = re.compile(r"^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$")


def load_auth():
    if not ENV_FILE.is_file():
        return None
    cfg = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    user = cfg.get("WIGLE_USER")
    pw = cfg.get("WIGLE_PASS")
    tok = cfg.get("WIGLE_TOKEN")
    if user and pw:
        return base64.b64encode(f"{user}:{pw}".encode()).decode()
    if tok:
        if ":" in tok:
            return base64.b64encode(tok.encode()).decode()
        return tok
    return None


def cached_bssids():
    if not CACHE_DB.is_file():
        return set()
    conn = sqlite3.connect(str(CACHE_DB))
    try:
        rows = conn.execute("SELECT bssid FROM wigle_cache").fetchall()
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()
    return {r[0] for r in rows}


def candidate_bssids(limit):
    """Pull BSSIDs from CSVs that aren't yet cached. Strongest-signal first."""
    known = cached_bssids()
    best = {}
    for path in glob.glob(CSV_GLOB):
        try:
            with open(path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    b = (row.get("bssid") or "").lower().strip()
                    if not BSSID_RE.match(b):
                        continue
                    if b in known:
                        continue
                    try:
                        rssi = int(row.get("rssi") or -100)
                    except ValueError:
                        rssi = -100
                    if b not in best or rssi > best[b]:
                        best[b] = rssi
        except OSError:
            continue
    ordered = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    return [b for b, _ in ordered[:limit]]


def query_one(bssid, auth):
    url = f"{API}?{urllib.parse.urlencode({'netid': bssid})}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            return r.status, body, time.time() - t0
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, body, time.time() - t0


def upsert_cache(bssid, status_bucket, payload):
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS wigle_cache (
        bssid TEXT PRIMARY KEY, ssid TEXT, encryption TEXT,
        first_seen TEXT, last_seen TEXT, trilat REAL, trilon REAL,
        qos INTEGER, country TEXT, city TEXT,
        checked_at INTEGER, status TEXT)""")
    now = int(time.time())
    if status_bucket == "ok" and payload:
        conn.execute("""INSERT OR REPLACE INTO wigle_cache
            (bssid, ssid, encryption, first_seen, last_seen, trilat, trilon,
             qos, country, city, checked_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok')""",
            (bssid, payload.get("ssid", ""), payload.get("encryption", ""),
             payload.get("first_seen", ""), payload.get("last_seen", ""),
             payload.get("trilat"), payload.get("trilon"),
             payload.get("qos", 0), payload.get("country", ""),
             payload.get("city", ""), now))
    else:
        conn.execute("""INSERT OR REPLACE INTO wigle_cache
            (bssid, checked_at, status) VALUES (?, ?, ?)""",
            (bssid, now, status_bucket))
    conn.commit()
    conn.close()


def append_to_spec(text):
    if not SPEC_DOC.is_file():
        return
    with open(SPEC_DOC, "a") as f:
        f.write(text)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"run-{stamp}.log"
    log = open(log_path, "w", buffering=1)

    def say(msg):
        print(msg, file=log)
        print(msg)

    say(f"# WiGLE quota probe — {stamp}")
    auth = load_auth()
    if not auth:
        say(f"FATAL: no WiGLE credentials in {ENV_FILE}")
        return 2
    candidates = candidate_bssids(MAX_QUERIES)
    say(f"candidates: {len(candidates)} uncached BSSIDs")
    if not candidates:
        say("nothing to probe (all BSSIDs already cached)")
        return 0

    ok = not_found = errors = 0
    hit_429_at = None
    first_429_body = None
    started = time.time()

    for i, bssid in enumerate(candidates, 1):
        status, body, dt = query_one(bssid, auth)
        if status == 200:
            try:
                import json as J
                data = J.loads(body)
                results = data.get("results") or []
                if results:
                    r0 = results[0]
                    enc = str(r0.get("encryption") or "unknown").lower()
                    payload = {
                        "ssid": r0.get("ssid") or "",
                        "encryption": enc,
                        "first_seen": r0.get("firsttime") or "",
                        "last_seen": r0.get("lasttime") or "",
                        "trilat": r0.get("trilat"),
                        "trilon": r0.get("trilong"),
                        "qos": r0.get("qos") or 0,
                        "country": r0.get("country") or "",
                        "city": r0.get("city") or "",
                    }
                    upsert_cache(bssid, "ok", payload)
                    ok += 1
                    say(f"[{i:3d}] 200 ok {bssid} enc={enc} dt={dt:.2f}s")
                else:
                    upsert_cache(bssid, "not_found", None)
                    not_found += 1
                    say(f"[{i:3d}] 200 not-found {bssid} dt={dt:.2f}s")
            except Exception as e:
                errors += 1
                say(f"[{i:3d}] parse-err {bssid}: {e}")
        elif status == 429:
            hit_429_at = i
            first_429_body = body[:300]
            say(f"[{i:3d}] 429 RATE-LIMIT {bssid}")
            say(f"       body: {body[:300]!r}")
            break
        else:
            errors += 1
            say(f"[{i:3d}] {status} error {bssid} body={body[:200]!r}")
        time.sleep(INTERVAL_SEC)

    elapsed = time.time() - started
    total_responsive = ok + not_found
    total_sent = total_responsive + errors + (1 if hit_429_at else 0)
    rate_str = (
        f"{not_found / total_responsive:.2%}"
        if total_responsive > 0 else "n/a"
    )
    summary = f"""
# Results
  sent_total: {total_sent}
  successful_200: {total_responsive}
    ok: {ok}
    not_found: {not_found}
  errors_non_429: {errors}
  hit_429_at_query: {hit_429_at}
  first_429_body: {first_429_body!r}
  elapsed_sec: {elapsed:.1f}
  first_discovery_rate_observed: {rate_str}
"""
    say(summary)

    # Spec append: distinguish "no data" (quota burned before first query)
    # from "0% first-discovery" (real measurement). Old script formatted both
    # as "0/0 = 0.0%" which read as "feature is dead" — exactly the wrong
    # signal when the truth is "we have no data."
    if total_responsive == 0:
        p2_line = "- **P2 (first-discovery rate):** no data — quota exhausted before first query returned"
    else:
        p2_line = f"- **P2 (first-discovery rate):** {not_found}/{total_responsive} = {not_found / total_responsive:.1%} of probed BSSIDs not in WiGLE"

    p1_at = f"#{hit_429_at}" if hit_429_at else f"NEVER HIT (cap > {MAX_QUERIES})"
    append_to_spec(f"""
### {stamp} — P1/P2 probe result

- **P1 (daily cap):** first 429 at query {p1_at}
{p2_line}
- Log: `{log_path}`
""")
    log.close()
    return 0 if hit_429_at or total_sent > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
