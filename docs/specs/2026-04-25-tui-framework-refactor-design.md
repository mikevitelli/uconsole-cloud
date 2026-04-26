# TUI Framework Refactor — Design

**Date:** 2026-04-25
**Status:** Shipped — duplicate-items fix in `011cac6`, plugin handler registry + ~750 lines extracted in `46e85cf`, broken-feature menu hide in `0be1234`. Plus `8f722b5` (launcher auto-detects source tree). Tests in `tests/test_handler_registry.py`.
**Branch:** `dev`
**Scope:** `device/lib/tui/framework.py`

## Why

framework.py is 3059 lines and mixes three things that change at different rates: framework primitives (drawing, runners, input), per-feature flows (~600-line ESP32 hub, process manager, ADSB helpers), and a hand-maintained `NATIVE_TOOLS` dict of ~70 lambdas. Adding a feature means editing framework.py in three places. A broken feature crashes the whole TUI because every handler is loaded eagerly into one dict.

Goal: each feature owns its handlers, broken features fail soft, framework.py shrinks ~750 lines.

## What

Each feature module exports `HANDLERS = {"_foo": fn, ...}` at module scope. framework.py keeps a `FEATURE_MODULES` list and a `_load_handlers()` function that imports each, merges their `HANDLERS`, and skips on `ImportError` (logged to `~/crash.log`). Dispatch is `if key in handlers: handlers[key](scr); else: silently skip`.

YAML-driven menus (the deleted `tui-menu.yaml` direction) are out of scope. `MENU` and `SUBMENUS` stay as Python dicts.

## What moves

| New file              | Receives                                                                                                                                                                                          | LOC  |
|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------|
| `tui/esp32_hub.py`    | `_ESP32_*_ITEMS`, `_esp32_menu_for`, `run_esp32_hub`, `run_esp32_flash_picker`, `_confirm_flash`, `_run_threaded_flash`, `_esp32_install_watchdogs`, `_pick_watchdogs_variant`, `run_esp32_force`, `_esp32_usb_reset`, `_esp32_redetect`, `_esp32_fw_cache_clear`, `_esp32_backup` | ~620 |
| `tui/processes.py`    | `run_process_manager`                                                                                                                                                                              | ~110 |
| `tui/adsb_menu.py`    | `_adsb_layers_menu_entry`, `_adsb_fetch_hires_entry`                                                                                                                                               | ~80  |

## What gets deleted

`_Firmware_MP/MRD/MC` (trivial wrappers — inline the enum), `_run_mimiclaw` (replaced by direct `HANDLERS` registration in `tui/mimiclaw.py`), `NATIVE_TOOLS`, `_get_native_tools`.

## What grows a `HANDLERS` export

Every existing `tui/*.py` module that has a public handler key today: `config_ui`, `tools`, `games`, `monitor`, `files`, `network`, `services`, `radio`, `adsb`, `adsb_home_picker`, `adsb_layer_picker`, `adsb_basemap_info`, `meshtastic_map`, `marauder`, `mimiclaw`, `telegram`, `watchdogs`. One-line edit each: `HANDLERS = {"_foo": run_foo, ...}` at the bottom of the file.

## Failure model

A feature whose module fails to import is logged to `~/crash.log` and skipped. Menu items pointing to its (now-absent) handlers become silent no-ops at dispatch — the user clicks, nothing happens. Hiding the items visually is a follow-up commit, not a blocker.

## Three commits

```
1. fix(tui): dedupe _ESP32_MIMICLAW_ITEMS
   The wardrive merge introduced a duplicate definition at framework.py:1974
   and :1982. Second wins, dropping the Settings entry. ~5-line fix.

2. refactor(tui): extract per-feature flows, plugin handler registry
   - Create esp32_hub.py, processes.py, adsb_menu.py
   - Every tui/*.py with a public handler gets HANDLERS = {...}
   - framework.py: FEATURE_MODULES list + _load_handlers() + crash.log on import failure
   - Delete NATIVE_TOOLS, _get_native_tools, _run_mimiclaw, _Firmware_*
   - run_script dispatches via the loaded handlers dict; missing handler = silent skip
   ~750 LOC moved, no behaviour change.

3. feat(tui): hide menu items whose feature module failed to load
   Walk MENU/SUBMENUS once after _load_handlers(), drop _foo items whose
   target isn't in handlers. ~30 lines.
```

Each commit is independently shippable. Smoke-test the TUI between commits.

## Acceptance

- framework.py drops ≥600 lines.
- `esp32_hub.py`, `processes.py`, `adsb_menu.py` exist with `HANDLERS` exports.
- `NATIVE_TOOLS` and `_get_native_tools` are gone.
- All 9 categories navigate; ESP32 hub flashes work; mimiclaw, marauder, ADSB, processes still launch.
- Deliberately breaking a feature module logs to `~/crash.log` and (after commit 3) hides its menu items. Other categories unaffected.
