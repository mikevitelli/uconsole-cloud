# MimiClaw WiFi Config + ESP32 TUI Refactor — Design

**Date:** 2026-04-22
**Status:** Draft
**Author:** mikevitelli (via session with Claude)
**Reviewer:** —

## Why this doc exists

MimiClaw's IP is hardcoded to `192.168.1.23` in `tui/mimiclaw.py:23`. When the
device lands on any other IP — which is almost every time after a reflash or
WiFi change — the TUI chat panel silently fails. The naive fix is to flip the
constant; the correct fix is to stop embedding an IP in source code at all.

While we're in the ESP32 menu code, the submenus have accumulated duplicate
actions (Reset vs USB Reset, Reboot vs USB Reset, Install Bruce as a peer of
Switch Firmware, Scan APs that duplicates Marauder's own in-app menu). This
is the right moment to distill them.

## The actual problem

Two problems, one touchpoint.

**Problem A — IP resolution.** MimiClaw reports its own IP over serial every
time you ask (`wifi_status`). The TUI already talks to it over serial for
every other command (`_query_mimiclaw_status` at `mimiclaw.py:254` is the
pattern). There is no reason to hardcode.

**Problem B — ESP32 submenu bloat.** Across three firmware modes and a shared
footer, the TUI exposes 14 items per mode, with four of them duplicating or
subsuming others. The menu is harder to navigate than it needs to be, and the
destructive ops (reflash) sit at the top level alongside everyday ops.

## What we are building

### 1. IP auto-discovery + cache

- New file: `tui/esp32_wifi_cache.py` (<80 lines).
- Cache at `~/.config/uconsole/mimiclaw.json`, chmod 600, shape:
  ```json
  {"ip": "192.168.1.149", "ssid": "Digital Counsel", "updated_at": "ISO8601"}
  ```
- `_resolve_ip()` returns cache → probe → None.
- `run_mimiclaw_chat()` uses `_resolve_ip()` instead of `MIMI_IP`. On WS
  connect failure, it re-probes serial once, updates the cache, retries.
- No TTL. Serial probe is cheap. Failure self-heals.

### 2. WiFi config panel (`MimiClaw ▸ Settings ▸ WiFi`)

Initial screen — method picker, with a `Current:` line that reflects
live `wifi_status`:

```
Current:  Digital Counsel  (192.168.1.149)

  Scan nearby networks
  Copy from uConsole WiFi
  Enter manually
  Disconnect
```

**Scan flow.** `wifi_scan` over serial, 6s timeout. Parse
`[idx] SSID=... RSSI=... CH=... Auth=...`. Sort by RSSI desc, de-dup,
drop empties. List with signal bars (▁▃▅▇) and lock icon for secured
networks. Select → password prompt (skipped on open) → apply.

**Copy-from-uConsole flow.** Shells out to `nmcli -s` for the currently
active WiFi connection's SSID and PSK. One-line confirm. Apply.

**Manual flow.** Two fields: SSID (allows spaces, quoted in payload),
password (masked, `X` to reveal). Apply.

**Apply pipeline** (identical for all three methods):
1. Send `set_wifi "<ssid>" <password>\r\n`.
2. Wait ≤3s for `WiFi credentials saved for SSID: <ssid>` line.
3. Send `restart\r\n`.
4. Progress screen `Restarting MimiClaw… (15s)` with animated dots.
5. After 10s boot delay, poll `wifi_status` every 2s for up to 15s.
6. On success: update cache, return to picker with refreshed `Current:`.
7. On failure at 25s total: show error + `set_wifi` args, offer retry/back.
   Cache untouched.

**Disconnect flow.** Sends `set_wifi "" ""`. If firmware rejects empty
args, fall back to `config_reset` (heavier — clears API key, model, etc.,
so requires explicit confirm dialog).

**Edge cases.**
- Serial port busy (Serial Monitor open elsewhere): show
  `Close Serial Monitor and try again.` — no silent wait.
- SSID with `"` or `\`: escape for payload; reject `\r`/`\n`.
- Empty scan result: `No networks found. Try again or use Manual.`

### 3. MimiClaw Settings subfold

MimiClaw submenu gains a `Settings▸` row. v1 contains only `WiFi`. The
subfold exists today to house the 14 other `set_*` commands the firmware
exposes (API key, model, bridge URL, Telegram token, etc.) as they are
added, without another restructure.

### 4. Per-firmware submenu distillation

Consistent pattern across all three firmwares:

```
Primary action      — firmware-specific
Serial Monitor      — always position 2
Status              — always position 3; "firmware info + wifi + chip"
Settings▸           — firmwares with knobs (Marauder, MimiClaw)
... firmware extras
```

**MicroPython (8 → 6):**
```
Live Monitor
Serial Monitor
Status              (absorbs current "Chip Info")
REPL
Flash Scripts
Log Entry
— drop "Reset" (dup of common USB Reset)
```

**Marauder (8 → 5 top-level + 2 nested):**
```
Marauder
Serial Monitor
Status              (renamed from "Device Info")
War Drive▸
  Start             (was "War Drive")
  Replay            (was "Replay Session")
Settings
— drop "Scan APs" (dup of Marauder's own in-app menu)
— drop "Reboot" (dup of common USB Reset)
```

**MimiClaw (3 → 4 top-level + 1 nested):**
```
Chat
Serial Monitor
Status
Settings▸
  WiFi              (new)
```

### 5. Common footer distillation

Current 6 items, flat. Target: 4 top-level + nested Reflash. Order by
frequency × safety: recovery ops first, destructive ops behind a ▸.

```
USB Reset
Re-detect
Backup FW
Reflash▸
  MicroPython
  Marauder
  Bruce             (was "Install Bruce" top-level)
  MimiClaw
  ─────
  Clear FW Cache    (utility; only affects downloaded Bruce binaries)
```

"Install Bruce" stops being a top-level common item and becomes one of the
four choices inside Reflash. "Switch Firmware" is renamed to "Reflash"
for clarity. Clear FW Cache moves inside Reflash since it only exists to
support that flow.

### Totals

| Scope        | Before | After              | Δ  |
|--------------|--------|--------------------|----|
| MicroPython  | 8      | 6                  | −2 |
| Marauder     | 8      | 5 (+2 nested)      | −1 |
| MimiClaw     | 3      | 4 (+1 nested)      | +1 structure |
| Common       | 6      | 4 (+5 nested)      | −2 |
| **Top-level per mode** | 14 | 10 | **−4** |

## What we are NOT building (and why)

- **No firmware fork.** Everything needed is exposed by the stock MimiClaw
  CLI (`set_wifi`, `wifi_scan`, `wifi_status`, `restart`). The Python side
  owns the IP problem.
- **No DHCP reservation as the fix.** User explicitly rejected the
  router-side approach. This spec solves it in software.
- **No mDNS discovery.** Requires a firmware change (publish
  `mimiclaw.local`). Out of scope for the same reason.
- **No Textual / urwid migration.** 19,150 lines of working `curses` +
  `tui_lib` code. Introducing a second TUI framework for ~200 lines of new
  panel is tail wagging dog. Framework migration is its own project.
- **No expansion of Settings beyond WiFi in v1.** The subfold is created
  with headroom, but only WiFi ships. Adding API Key / Model / bridge URL
  entries later is a follow-up — each is a two-line addition once WiFi
  proves the pattern.
- **No "Log Entry" removal from MicroPython.** Kept because dropping it
  is a one-line change if we discover it is unused; keeping an unused
  item is cheaper than rebuilding it if we were wrong.
- **No reorg of the top-level `console` menu.** This spec is scoped to
  the ESP32 submenu subtree and the common footer under it.

## Architecture

**Files:**
- `lib/tui/mimiclaw.py` — extend. Add `_cached_ip`, `_save_ip`,
  `_probe_ip_via_serial`, `_resolve_ip`, `run_mimiclaw_settings`,
  `run_mimiclaw_wifi`, `_wifi_scan_parse`, `_apply_wifi_creds`.
  Remove `MIMI_IP = "192.168.1.23"`.
- `lib/tui/framework.py` — update `_ESP32_MICROPYTHON_ITEMS`,
  `_ESP32_MARAUDER_ITEMS`, `_ESP32_MIMICLAW_ITEMS`, `_ESP32_COMMON_ITEMS`.
  Add `SUBMENUS["sub:esp32:reflash"]` and `SUBMENUS["sub:esp32:wardrive"]`
  and `SUBMENUS["sub:mimiclaw:settings"]`. Wire new dispatch tokens
  (`_mimiclaw_settings`, `_mimiclaw_wifi`, `_esp32_clear_fw_cache`,
  etc.).
- **New:** `lib/tui/esp32_wifi_cache.py` — `load()`, `save(ip, ssid)`.
  Handles JSON IO, `chmod 600`, atomic write via temp+rename.
- `lib/tui/esp32_flash.py` — add `clear_fw_cache()` entry point if not
  already present. No structural change.

**Serial contention.** All new serial ops use short-lived
`pyserial.Serial(timeout=2)` — no persistent connection. Matches
`_query_mimiclaw_status` pattern. If the existing Serial Monitor holds
the port, the panel surfaces that and refuses to proceed; the user
closes the monitor and retries.

**Payload escaping.** `set_wifi` uses `argtable3` on the ESP-IDF side
and accepts double-quoted args (confirmed empirically: `set_wifi
"Digital Counsel" 311EastBroadway` succeeded). SSIDs with embedded `"`
or `\` get shell-style escaped; SSIDs with `\r` or `\n` are rejected
client-side with an error.

## Testing strategy

Unit-testable pieces:
- `esp32_wifi_cache.load/save` — pure JSON IO, covered with pytest.
- `_wifi_scan_parse(raw)` — feed captured `wifi_scan` output, assert
  parsed list. Golden file in `tests/fixtures/mimiclaw-wifi-scan.txt`.
- `_format_apply_payload(ssid, password)` — quoting/escaping rules.

Integration-testable:
- `_probe_ip_via_serial` + `_resolve_ip` — mocked `pyserial.Serial`.
- Apply pipeline happy path — mocked serial returning canned
  `credentials saved` + `wifi_status: connected` responses.

Not automated (manual):
- Full round-trip with real ESP32 on `/dev/ttyACM0`: scan, pick,
  connect, verify cache update.
- Serial-busy path: open Serial Monitor in one panel, try WiFi config
  in another, confirm error message.

## Premises to validate before coding

1. **`wifi_scan` output format is stable** — grab one real capture,
   build the parser against it. Fail fast if output differs.
2. **`set_wifi "" ""` actually disconnects.** If it no-ops or errors,
   the Disconnect flow falls back to `config_reset` with a confirm.
   Verify empirically before shipping Disconnect.
3. **Reflash subfold can be built with existing `run_submenu`
   infrastructure** — `SUBMENUS` dict + item tuples. Should be yes
   based on `sub:esp32` already existing as a submenu key.

## Risks

- **Serial port contention** between the cache probe on chat launch
  and a Serial Monitor left open. Handled by the `close Serial
  Monitor` message — not by forcing a close.
- **Firmware-specific `wifi_scan` format drift** — future MimiClaw
  builds could change the line format. Parser should log + skip
  unrecognized lines, not crash.
- **User's MimiClaw firmware has the Telegram DNS bug** seen in
  session (`couldn't get hostname for :api.telegram.org` — note the
  leading colon, suggesting a URL-parsing defect in the firmware).
  Out of scope for this spec but worth a follow-up.

## Open questions

- Does the existing TUI submenu infrastructure support two levels of
  nesting (`ESP32 ▸ Reflash ▸ MicroPython`)? If not, Reflash becomes a
  flat list rendered by a one-off picker rather than a generic
  `run_submenu`. Confirm during implementation planning.
- Is "Log Entry" in MicroPython actually used? If not, drop in a
  follow-up spec — not blocking this one.

## Non-goals timeline

- **Textual migration** — separate spec if ever pursued.
- **Full settings panel for MimiClaw** (API key, model, tokens) —
  follow-up, each as a one-row addition to the Settings subfold once
  WiFi validates the pattern.
- **mDNS / DHCP-reservation** — not happening; explicitly rejected.
