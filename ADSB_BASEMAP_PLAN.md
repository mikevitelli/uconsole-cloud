# ADS-B Global Basemap — Implementation Plan

**Branch:** `feature/adsb-global-basemap`
**Scope:** Replace the NYC-only static basemap with a global, layered, dynamically-fetchable basemap. User can relocate anywhere on Earth and have a recognizable map automatically.
**Approach chosen:** Option 3 (hybrid) — bundled global low-res + on-demand hi-res fetch around home.

---

## 0. What exists today (baseline to preserve)

- `device/lib/tui/adsb.py` — live map TUI module. Recent user additions that must survive the refactor:
  - `_draw_speed_vector(canvas, px, py, track, speed_kt, scale)` — 1-minute velocity vectors scaled to zoom
  - Plane glyphs drawn as unicode heading arrows (`↑↗→↘↓↙←↖`) on scr (not braille dots)
  - Selected plane uses `A_REVERSE`
  - Each visible aircraft dict stores `px`, `py` for glyph placement
- `device/lib/tui/adsb_basemap.json` — 58 KB file, NYC-clipped, 38 coastline segments + 8 hardcoded airports. **Will be replaced.**
- Config keys already in use: `adsb_home_lat`, `adsb_home_lon`, `adsb_rings`, `adsb_overlay`
- In-map keys: `↑↓` select, `+/-` zoom, `r` rings cycle, `o` overlay toggle, `h` set home from GPS, `q` back
- Submenu path: HARDWARE → ADS-B Map → {Live Map, Aircraft Table, Set Home (GPS), Receiver (raw)}

---

## 1. Data: what we bundle vs. fetch

### 1a. Bundled global file — `adsb_basemap_global.json`

Built once from Natural Earth 1:50m vector data. Aim for **~1.0–1.5 MB** uncompressed, smaller after simplification.

| Layer         | Source                                       | Stored as              | Est. size |
|---------------|----------------------------------------------|------------------------|-----------|
| coastlines    | `ne_50m_coastline`                           | list of `[[lon,lat]…]` | ~350 KB   |
| countries     | `ne_50m_admin_0_countries` (boundary lines)  | list of `[[lon,lat]…]` | ~300 KB   |
| states        | `ne_50m_admin_1_states_provinces_lines`      | list of `[[lon,lat]…]` | ~200 KB   |
| airports      | `ne_10m_airports` (TYPE=major/large)         | `[{code,name,lat,lon}]`| ~40 KB    |
| cities        | `ne_50m_populated_places_simple` (pop ≥ 500k)| `[{name,lat,lon,pop}]` | ~60 KB    |

**Build script** (run once, committed output): `scripts/build_adsb_basemap.py` — downloads NE GeoJSON from the `nvkelso/natural-earth-vector` GitHub mirror, simplifies lines (Douglas-Peucker with ~0.05° tolerance for 1:50m), rounds coords to 3 decimals, writes compact JSON. Re-runnable so we can update or tweak filters.

**Rationale for 1:50m not 1:110m:** 110m is too blocky near cities (Long Island barely shows). 50m is the sweet spot where Manhattan has shape but file size is still tractable.

### 1b. On-demand hi-res overlay — `~/.config/uconsole/adsb_basemap_hires.json`

Triggered manually via menu. Grabs 1:10m data and clips to a bbox around current home (± ~5° lat, ± ~7° lon).

| Layer         | Source                          | Notes                       |
|---------------|---------------------------------|-----------------------------|
| coastlines    | `ne_10m_coastline`              | detailed shoreline          |
| states        | `ne_10m_admin_1_states_provinces_lines` | county-like detail  |
| lakes         | `ne_10m_lakes` (pick area ≥ threshold) | Great Lakes, Champlain etc. |
| rivers        | `ne_10m_rivers_lake_centerlines` | major rivers only          |
| airports      | `ne_10m_airports` (all types)    | ~900 airports globally, clipped to bbox |

Target size after clip: **~200-400 KB per cached region**. Cache key: `floor(home_lat)_floor(home_lon)` so small drifts don't re-fetch. Store as `~/.config/uconsole/adsb_basemap_hires_{lat}_{lon}.json`.

### 1c. Data format (unified schema)

```json
{
  "version": 1,
  "generated": "2026-04-13T22:00:00Z",
  "layers": {
    "coastlines": [[[lon,lat], ...], ...],
    "countries":  [[[lon,lat], ...], ...],
    "states":     [[[lon,lat], ...], ...],
    "lakes":      [[[lon,lat], ...], ...],
    "rivers":     [[[lon,lat], ...], ...],
    "airports":   [{"code":"JFK","name":"Kennedy","lat":40.64,"lon":-73.78}, ...],
    "cities":     [{"name":"New York","lat":40.71,"lon":-74.00,"pop":8000000}, ...]
  }
}
```

Both global and hi-res files use the same schema so the renderer is layer-agnostic.

---

## 2. Runtime architecture

### 2a. Basemap loader (lazy, cached)

```python
# in adsb.py
_BASEMAP = {"global": None, "hires": None, "hires_key": None}

def _load_basemap(home_lat, home_lon):
    if _BASEMAP["global"] is None:
        _BASEMAP["global"] = json.load(open(GLOBAL_PATH))
    key = _bbox_key(home_lat, home_lon)
    if _BASEMAP["hires_key"] != key:
        path = _hires_path_for(key)
        _BASEMAP["hires"] = json.load(open(path)) if os.path.exists(path) else None
        _BASEMAP["hires_key"] = key
    return _BASEMAP["global"], _BASEMAP["hires"]
```

### 2b. Bbox filtering (skip features far from viewport)

Before projecting any line, check its rough bbox vs. the viewport bbox (`home ± range_nm + 20% margin`). Natural Earth features are simple enough that a precomputed per-feature bbox isn't worth it; a coarse first-point check is fine.

```python
def _in_viewport(lat, lon, home_lat, home_lon, range_nm):
    lat_margin = range_nm / 55.0        # 1° lat ≈ 60 nm
    lon_margin = range_nm / (55.0 * max(0.2, math.cos(math.radians(home_lat))))
    return (abs(lat - home_lat) < lat_margin * 1.2 and
            abs(lon - home_lon) < lon_margin * 1.2)
```

### 2c. Layer draw order (bottom to top on the braille canvas)

1. Countries (dim, long dashes if possible — actually just plain lines)
2. States/provinces (dimmer)
3. Coastlines (brighter — they're the anchor shapes)
4. Lakes (outline only)
5. Rivers (thin)
6. Range rings (existing, on top of geography)
7. Aircraft speed vectors (existing)

Then on `scr` (text layer, over the braille render):

8. Airport labels
9. City labels (smaller, dim; only show if zoom ≤ 100 nm so they don't clutter wide views)
10. Cardinals N/S/E/W
11. Aircraft heading-arrow glyphs (existing)
12. Selected aircraft HUD (existing)
13. Status/footer (existing)

### 2d. Layer visibility state

Extend the overlay system from binary (on/off) to per-layer bitmap. New config key `adsb_layers` as an int bitmask:

```python
LAYER_COAST     = 1 << 0
LAYER_COUNTRIES = 1 << 1
LAYER_STATES    = 1 << 2
LAYER_LAKES     = 1 << 3
LAYER_RIVERS    = 1 << 4
LAYER_AIRPORTS  = 1 << 5
LAYER_CITIES    = 1 << 6
LAYER_RINGS     = 1 << 7
LAYER_CARDINALS = 1 << 8

DEFAULT_LAYERS = COAST | COUNTRIES | STATES | AIRPORTS | CITIES | RINGS | CARDINALS
```

Existing `adsb_overlay` key becomes "master" toggle (`o`) — flips whole bitmap to 0 / restore.

### 2e. Zoom-aware label density

- Airport labels: show major airports when `range_nm ≥ 50`; show all when `range_nm ≤ 50`
- City labels: show pop ≥ 1M when `range_nm ≥ 100`; pop ≥ 500k when 25–100; hide under 25
- Prevents a soup of overlapping labels at wide zooms

Tie-break overlap: simple greedy — track occupied cells, skip labels that would collide.

---

## 3. New user-facing controls

### 3a. In-map keys (added)

| Key | Action                          | Persisted |
|-----|---------------------------------|-----------|
| `l` | Cycle layer preset: `full → minimal (coast+rings) → planes-only → full` | yes |
| `L` | Toggle individual layer popup menu (pick which layers on) | yes |
| `f` | Trigger "Fetch Hi-Res Basemap" around current home | n/a (prompts) |

Existing `o` (master overlay toggle) stays.

### 3b. Submenu additions under `sub:adsb`

```python
"sub:adsb": [
    ("Live Map",         "_adsb_map",         "real-time aircraft map",             "action"),
    ("Aircraft Table",   "_adsb_table",       "sorted list by distance",            "action"),
    ("Set Home (GPS)",   "_adsb_set_home",    "record GPS fix as map center",       "action"),
    ("Set Home (Manual)","_adsb_set_home_manual", "type lat/lon",                   "action"),   # NEW
    ("Layer Config",     "_adsb_layers",      "pick overlay layers",                "action"),   # NEW
    ("Fetch Hi-Res",     "_adsb_fetch_hires", "download 1:10m data for your region","action"),   # NEW
    ("Basemap Info",     "_adsb_basemap_info","which files loaded, coverage",       "action"),   # NEW
    ("Receiver (raw)",   "radio/sdr.sh adsb", "launch dump1090 interactive",        "fullscreen"),
],
```

### 3c. Manual home entry

Currently home is set via GPS only, which fails indoors. Add a simple prompt screen:

```
Set Home — Manual
Latitude  : [ 40.7128   ]
Longitude : [ -74.0060  ]
Presets   : NYC  LAX  ORD  LHR  NRT  SYD  (arrow to pick)
[Enter] save    [q] cancel
```

Saves `adsb_home_lat`, `adsb_home_lon` to config. Presets are a hand-picked list of major metros to make cross-region testing easy.

---

## 4. Fetch Hi-Res flow

```
Fetch Hi-Res Basemap
────────────────────
Region:   40.71, -74.01  (±5° lat, ±7° lon)
Layers:   coastlines, states, lakes, rivers, airports
Estimated size:  ~350 KB
Source:   github.com/nvkelso/natural-earth-vector (1:10m)

This requires internet. Cached to ~/.config/uconsole/adsb_basemap_hires_40_-74.json
No data is sent to any server besides the public GitHub file download.

[y] fetch   [n] cancel
```

Implementation:
- Use `urllib.request` (stdlib, no new deps)
- Download each layer file → parse GeoJSON → clip to bbox → add to cache dict
- Stream progress with a simple spinner in curses
- On error: show message, keep whatever was cached before
- Total download: ~10-30 MB of raw GeoJSON, reduced to ~300 KB after clip — takes 15-60s on decent wifi

**Crucial safety:** Download to `~/.config/uconsole/adsb_basemap_hires_{key}.tmp` first, then rename atomically so an interrupted fetch never leaves a half-file.

---

## 5. File changes

| Path | Action | Notes |
|------|--------|-------|
| `device/lib/tui/adsb.py` | MAJOR edit | Refactor for layer system, bbox filter, hi-res overlay merge, new key handlers |
| `device/lib/tui/adsb_basemap.json` | DELETE | Replaced by `adsb_basemap_global.json` |
| `device/lib/tui/adsb_basemap_global.json` | NEW | Bundled 1:50m global data |
| `device/lib/tui/adsb_hires.py` | NEW | Fetch + clip logic (keeps adsb.py manageable) |
| `device/lib/tui/adsb_home_picker.py` | NEW | Manual home entry UI + presets |
| `device/lib/tui/adsb_layer_picker.py` | NEW | Layer toggle popup |
| `scripts/build_adsb_basemap.py` | NEW | One-shot builder for the bundled global file (dev tool) |
| `device/lib/tui/framework.py` | EDIT | Register 3 new native tools |

Keeping UI pieces in their own files so `adsb.py` doesn't balloon.

---

## 6. Config keys (all under `.console-config.json`)

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `adsb_home_lat` | float | — | existing |
| `adsb_home_lon` | float | — | existing |
| `adsb_rings` | int | 2 | existing — stays as ring preset index |
| `adsb_overlay` | bool | true | existing — master toggle |
| `adsb_layers` | int | `DEFAULT_LAYERS` bitmask | NEW |
| `adsb_zoom_idx` | int | 6 (150 nm) | NEW — persist last zoom |
| `adsb_hires_enabled` | bool | true | NEW — use hi-res if cached |

---

## 7. Open decisions (to resolve on walk return)

1. **Bundled file size cap** — am I OK with ~1.5 MB added to the .deb? If not, drop `countries` + `states` from the bundle and make hi-res fetch mandatory for borders.
2. **Cities layer at all?** — debate: at wide zooms it gets messy, at tight zooms airports matter more. Default: show at 25–100 nm only. Could also drop entirely for MVP.
3. **Preset list for manual home entry** — default suggests NYC, LAX, ORD, LHR, NRT, SYD. Anything you'd add/remove?
4. **Hi-res fetch UI** — one-shot action or a separate downloader screen with progress bar? (I'd start with one-shot action, add progress bar if the 30-60s feels dead.)
5. **Manual home precision** — free-form lat/lon text entry vs. number spinners vs. preset-only? Probably text entry with numeric validation.
6. **What happens if GitHub is unreachable?** — Silent failure to global file, or loud error? I'd do loud in the fetch screen, silent-fallback in the live map.

---

## 8. Implementation order (when we launch)

1. **Build script + global bundle** (no UI changes yet) — verify size, visual quality at key locations (NYC, LAX, London, Tokyo)
2. **Wire global bundle into live map** — replace old adsb_basemap.json path, confirm NYC still looks right
3. **Layer bitmask + default layers** — visual parity with current, refactor `_draw_basemap_canvas` into per-layer draws
4. **Bbox culling** — confirm wide-zoom performance didn't regress (feature count in viewport)
5. **Manual home picker** — unlock indoor testing and cross-region verification
6. **Layer picker popup** — in-map `L` key
7. **Fetch hi-res** — network code + clip logic + cache + menu item
8. **Zoom-aware label density** — polish pass
9. **Basemap Info screen** — show loaded files, feature counts (debug aid)

Each step commits separately. Steps 1-5 get us to "works anywhere on Earth offline"; steps 6-8 are polish.

---

## 9. Test plan

- **NYC (current home)**: all recent visual state preserved; Manhattan outline still recognizable; JFK/LGA/EWR labels in right spots
- **Manual jump to London (51.47, -0.45)**: coastlines of England + France visible; LHR labeled; Thames if hi-res fetched
- **Manual jump to Tokyo (35.55, 139.78)**: HND/NRT labeled; coastline of Honshu; Mt. Fuji-area clean
- **Manual jump to middle of Pacific (0, -160)**: basemap mostly empty (correct); range rings + aircraft render correctly with no crash
- **Zoom extremes**: 2 nm (Manhattan airspace) and 250 nm (northeast corridor) — no lag, no layer overflow
- **Overlay off (`o`)**: only planes + HUD visible
- **Rings cycle (`r`)**: 0→4 and back
- **Layer cycle (`l`)**: visible difference between presets
- **Hi-res fetch then go offline**: still works from cache
- **No internet, no cache, new region**: falls back to global silently, warns in Basemap Info screen

---

## 10. Risks / mitigations

- **Bundle size creeping past 2 MB** → simplification tolerance is tunable in the build script; drop layers if needed
- **Fetch blocking the UI** → do it in a thread with a spinner; allow cancel
- **Over-dense labels** → zoom-gated + occupied-cell tracking
- **Braille renders slow at 250 nm with all layers** → bbox cull before projection; profile if needed
- **Config schema drift** → version field in basemap files + graceful fallback when cache is old format
- **Preserving user's in-flight edits** (`_draw_speed_vector`, arrow glyphs, selected-plane HUD) → all of those live in the aircraft-rendering path, orthogonal to basemap changes; refactor touches `_draw_basemap_canvas` and adds `_draw_layer_X` helpers, nothing under them

---

## 11. Non-goals for this round

- No raster/OSM tiles
- No nav charts (VOR/airways/airspace) — cool but a whole separate project
- No runway detail (just airport points)
- No timezone/DST awareness in labels
- No airline/registration enrichment (that's a different feature entirely)

---

## 12. What I need from you when you're back

1. Confirm or adjust decisions 1-6 above
2. Say "go" and I'll work through the implementation order in section 8
3. Tell me if you'd rather test in a worktree or just keep going on this branch
