# TUI Framework Refactor — Design

**Date:** 2026-04-25
**Status:** Draft, planning-only (action tomorrow)
**Branch:** `dev`
**Scope:** `device/lib/tui/framework.py`
**Approach:** Approach 3 (minimal extraction). YAML migration deferred.

## Why this doc exists

`device/lib/tui/framework.py` has grown to 3059 lines and now mixes three concerns that change at different rates:

1. **Framework primitives** — drawing, theming, input, runner modes, tile UI, main loop. These change rarely.
2. **Per-feature flows** — the ~600-line ESP32 hub, the ~110-line process manager, two ADSB menu helpers, a mimiclaw wrapper, three trivial `_Firmware_*` shims. These change every time a feature is added or extended.
3. **The handler registry** — `NATIVE_TOOLS` plus `_get_native_tools()`, ~70 lambda-mapped handler keys all hand-maintained in one giant dict.

Adding a new feature today requires editing framework.py in three places: imports, `NATIVE_TOOLS`, and sometimes a wrapper. When a feature breaks, the failure mode is "TUI crashes at startup" because every feature's handlers are loaded eagerly into one dict. The watchdogs feature is the only one with import-failure isolation, and it had to be hand-wired with try/except.

The goal is to make adding a feature a one-file change and to make a broken feature fail soft.

A separate session drafted `device/share/tui-menu.yaml` earlier today as a possible data-driven menu source, then deleted it. That direction is deferred. This refactor keeps `MENU` and `SUBMENUS` as Python dicts. If a YAML data model is wanted later, it can be regenerated from whatever shape the refactor settles on.

## Goals

- **Self-contained features.** Each feature module declares its own `HANDLERS` dict at module scope and is the only place its handler logic lives.
- **Soft failure.** A feature whose module fails to import has its menu items hidden entirely (failure model A). The TUI still launches with the rest of its surface area intact. The import error is logged once to `~/crash.log`.
- **One-file feature additions.** Adding a feature means: create a module under `tui/`, export `HANDLERS`, add the module name to `FEATURE_MODULES`, add menu entries to `MENU`/`SUBMENUS`. No edits to handler-registry plumbing.
- **No public API change.** `run_panel`, `run_stream`, `run_action`, `run_fullscreen`, `run_confirm`, `load_config`, `save_config`, the `C_*` colour constants, and `tui_lib` re-export all stay. Existing feature modules (mimiclaw, marauder, adsb, network, etc.) keep working without changes.
- **Framework.py shrinks substantially.** Target: ~3059 → ~2300 lines.

## Non-goals

- No menu structure change. Categories, submenus, and items render exactly as today (apart from the duplicate-definition bug fix below).
- No YAML migration. `MENU` and `SUBMENUS` remain Python data structures.
- No new features.
- No re-architecting of drawing, input, or runner-mode code.
- No changes to feature module internals beyond moving them into their own files and exporting `HANDLERS`.

## Architecture

### Handler registry contract

Each feature module exports a `HANDLERS` dict at module scope:

```python
# device/lib/tui/processes.py
def run_process_manager(scr): ...

HANDLERS = {
    "_processes": run_process_manager,
}
```

`HANDLERS` values are callables that accept `(scr)` and return either `None` or `"switch_view"` (the existing dispatch contract used by `run_script`).

### Framework loading

`framework.py` keeps a `FEATURE_MODULES` constant — a list of dotted module names — and a `_load_handlers()` function that walks it:

```python
FEATURE_MODULES = [
    "tui.config_ui",
    "tui.tools",
    "tui.games",
    "tui.monitor",
    "tui.files",
    "tui.network",
    "tui.services",
    "tui.radio",
    "tui.adsb",
    "tui.adsb_home_picker",
    "tui.adsb_layer_picker",
    "tui.adsb_basemap_info",
    "tui.adsb_menu",
    "tui.meshtastic_map",
    "tui.marauder",
    "tui.mimiclaw",
    "tui.telegram",
    "tui.watchdogs",
    "tui.esp32_hub",
    "tui.processes",
]


def _load_handlers():
    """Import every module in FEATURE_MODULES, merge their HANDLERS dicts.
    Modules that fail to import are logged to ~/crash.log and skipped."""
    handlers = {}
    for mod_name in FEATURE_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            _log_feature_failure(mod_name, e)
            continue
        handlers.update(getattr(mod, "HANDLERS", {}))
    return handlers
```

Loading is **eager** at first menu interaction (preserving the current `_get_native_tools()` lazy-load timing). The cold-start cost is unchanged.

### Menu filtering — the failure model

After `_load_handlers()` runs, framework.py walks `MENU` and `SUBMENUS` and drops any item whose `target` starts with `_` and isn't in the loaded handlers dict. Submenu drilldown items (`sub:foo`) and shell script paths are left alone.

```python
def _filter_unknown_handlers(menu, handlers):
    """Drop items whose _foo target isn't in handlers. Recursively descends submenus."""
    ...
```

This is the (a) failure model: broken module ⇒ its menu items disappear ⇒ user sees a clean menu, with no broken items, no crash dialogs. The import error is logged.

Filtering is done once per session, after handler load. If a submenu becomes empty after filtering, the submenu itself is dropped from any parent that referenced it (preventing dead drilldowns).

### Logging

Import failures append to `~/crash.log` with a structured line:

```
2026-04-26T03:14:27Z  feature-import-failed  tui.esp32_hub  ImportError: No module named 'esptool'
```

One line per failure. `crash-log.sh` already reads `~/crash.log`, so failures surface in the existing crash log viewer.

### Bug fix: duplicate `_ESP32_MIMICLAW_ITEMS`

The wardrive merge introduced a duplicate definition at framework.py:1974 and :1982. The second wins, dropping the Settings entry that points to `sub:mimiclaw:settings`. This is silently broken on dev right now. The refactor folds the fix in: only the 4-item version (with Settings) survives the move into `tui/esp32_hub.py`.

## Extraction targets

Files to create:

| New file                       | Receives from framework.py                                                                                                                                                                                                                                | Approx lines |
|--------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|
| `tui/esp32_hub.py`             | `_ESP32_MICROPYTHON_ITEMS`, `_ESP32_MARAUDER_ITEMS`, `_ESP32_COMMON_ITEMS`, `_ESP32_MIMICLAW_ITEMS` (deduped), `_esp32_menu_for`, `run_esp32_hub`, `run_esp32_flash_picker`, `_confirm_flash`, `_run_threaded_flash`, `_esp32_install_watchdogs`, `_pick_watchdogs_variant`, `run_esp32_force`, `_esp32_usb_reset`, `_esp32_redetect`, `_esp32_fw_cache_clear`, `_esp32_backup` | ~620         |
| `tui/processes.py`             | `run_process_manager`                                                                                                                                                                                                                                     | ~110         |
| `tui/adsb_menu.py`             | `_adsb_layers_menu_entry`, `_adsb_fetch_hires_entry`                                                                                                                                                                                                       | ~80          |

Code to delete outright (replaced by direct calls or HANDLERS entries):

| Removed                                       | Why                                                                                              |
|-----------------------------------------------|--------------------------------------------------------------------------------------------------|
| `_Firmware_MP`, `_Firmware_MRD`, `_Firmware_MC` | Three-line wrappers that just return `Firmware.X`. Inline the enum reference inside `esp32_hub.py`. |
| `_run_mimiclaw`                                | Dynamic-dispatch wrapper. Replace with direct registration: `tui/mimiclaw.py` exports `HANDLERS = {"_mimiclaw_chat": run_mimiclaw_chat, ...}`. |
| `_get_native_tools`                            | Replaced by `_load_handlers()`.                                                                  |
| `NATIVE_TOOLS`                                 | Replaced by the handlers dict from `_load_handlers()`.                                            |

Existing modules to grow `HANDLERS`:

`tui/config_ui.py`, `tui/tools.py`, `tui/games.py`, `tui/monitor.py`, `tui/files.py`, `tui/network.py`, `tui/services.py`, `tui/radio.py`, `tui/adsb.py`, `tui/adsb_home_picker.py`, `tui/adsb_layer_picker.py`, `tui/adsb_basemap_info.py`, `tui/meshtastic_map.py`, `tui/marauder.py`, `tui/mimiclaw.py`, `tui/telegram.py`, `tui/watchdogs.py`.

Each gains a `HANDLERS = {...}` block at the bottom of the file mapping its public handler keys to the existing functions. No function renames, no signature changes.

## What stays in framework.py

- All UI primitives: `init_colors`, `apply_theme`, `build_custom_theme`, `draw_header`, `draw_footer`, `draw_status_bar`, `draw_category_tabs`, `draw_separator`, `draw_menu`, `draw_box`, `_colorize_line`, `draw_tile`, `draw_tile_grid`
- All input handling: `get_key`, gamepad helpers (`_claim_gamepad`, `_is_gamepad_owner`, `open_gamepad`, `close_gamepad`, `read_gamepad`, `_gp_set_cooldown`, `_reopen_gamepad`)
- Workspace: `_read_active_workspace`, `_init_workspace`
- Config: `load_config`, `_save_config_locked`, `save_config`, `save_config_multi`, `load_theme`, `load_view_mode`, `_resolve_theme`
- Runner modes: `run_panel`, `run_stream`, `run_action`, `run_fullscreen`, `run_confirm`, `run_submenu`
- Submenu utilities: `_submenu_run_selected`, `_resolve_cmd`, `_run_and_capture`, `_run_subview`, `_tui_input_loop`
- Top-level loop: `main`, `entry`, `main_tiles`, `wait_for_input`
- Menu data: `MENU`, `CATEGORIES`, `SUBMENUS`, `CAT_ICONS`, `CAT_DESCS`, `CONFIRM_SCRIPTS`, the various tile-layout constants
- Handler registry plumbing: `FEATURE_MODULES`, `_load_handlers`, `_filter_unknown_handlers`, `_log_feature_failure`, the loaded handlers dict (replacing `NATIVE_TOOLS`)
- The version logic at the top of the file
- `run_script` itself (now consults the loaded handlers dict instead of `NATIVE_TOOLS`)

Public symbols re-exported via the existing import paths so that feature modules already importing from `tui.framework` keep working.

## Migration plan (executed tomorrow)

Six phases, each its own commit, each independently shippable. Verification gate between every phase: TUI launches cleanly + py_compile passes + relevant smoke test for the touched feature.

The transition strategy: phase A introduces `_load_handlers()` and a new combined registry `_get_handlers()` that returns `NATIVE_TOOLS` merged with the result of `_load_handlers()`. `run_script` is rewired to consult `_get_handlers()`. With `FEATURE_MODULES` empty, this is behaviour-equivalent to today.

Phases B–E migrate features off `NATIVE_TOOLS` into their own modules' `HANDLERS` exports, adding each module to `FEATURE_MODULES`. Each migration is a strict swap: an entry removed from `NATIVE_TOOLS` is added via `HANDLERS`, and the merged dict still serves it.

Phase E ends with `NATIVE_TOOLS` empty. Phase F removes the now-empty literal entirely and runs the failure-model verification.

| Phase | What lands                                                                                              | Approx LOC change |
|-------|---------------------------------------------------------------------------------------------------------|-------------------|
| **A** | Add `FEATURE_MODULES = []`, `_load_handlers()`, `_filter_unknown_handlers()`, `_log_feature_failure()`, and `_get_handlers()`. Rewire `run_script` to use `_get_handlers()`. `NATIVE_TOOLS` unchanged; `FEATURE_MODULES` empty; behaviour-equivalent. Audit feature modules' existing imports from `tui.framework` and add any missing re-exports. | +130              |
| **B** | Convert `tui/processes.py` (smallest, simplest). Move `run_process_manager` out, add `HANDLERS = {"_processes": run_process_manager}`, add `"tui.processes"` to `FEATURE_MODULES`, remove the `_processes` lambda from `NATIVE_TOOLS`. Smoke: open Process Manager from MONITOR menu. | -110, +130        |
| **C** | Convert `tui/adsb_menu.py` (next-simplest). Two helpers move out, two lambdas removed from `NATIVE_TOOLS`. Smoke: ADS-B Layers and Fetch Hi-Res Basemap items still launch. | -80, +95          |
| **D** | Convert `tui/esp32_hub.py` (largest extraction). All ESP32 hub flows move out, dedupe `_ESP32_MIMICLAW_ITEMS`, drop `_Firmware_*` wrappers. Ten lambdas removed from `NATIVE_TOOLS`. Smoke: full ESP32 hub navigation including reflash and force-firmware paths. | -620, +650        |
| **E** | Direct registration of remaining existing modules. `tui/mimiclaw.py` (4 entries), `tui/marauder.py`, `tui/adsb.py`, `tui/network.py`, `tui/services.py`, `tui/radio.py`, `tui/tools.py`, `tui/games.py`, `tui/monitor.py`, `tui/files.py`, `tui/config_ui.py`, `tui/telegram.py`, `tui/watchdogs.py`, `tui/meshtastic_map.py`, plus the three small adsb-* modules each grow a `HANDLERS` export and join `FEATURE_MODULES`. Their corresponding lambdas are removed from `NATIVE_TOOLS`. The `_run_mimiclaw` wrapper is deleted. After this phase, `NATIVE_TOOLS` is `{}`. Smoke: full TUI walk through every category. | -240              |
| **F** | Cleanup + failure-model verification. Delete the empty `NATIVE_TOOLS` dict and `_get_native_tools` function. Collapse `_get_handlers` into a direct call to `_load_handlers` since the local-dict fallback is no longer needed. Then deliberately break one feature module (e.g. add `import nonexistent` to `tui/processes.py`), confirm: (1) `~/crash.log` records the failure, (2) Process Manager menu item is hidden, (3) other categories render normally. Revert the deliberate break. | -40 (test included) |

After phase F: framework.py is approximately 2300 lines (3059 → 2300, ~750 lines moved or removed). `NATIVE_TOOLS` is gone. Each feature lives in its own file with a one-line entry in `FEATURE_MODULES`.

## Testing

- **Unit tests for the new plumbing.** Add `tests/test_handler_registry.py`:
  - `_load_handlers` merges multiple modules' `HANDLERS` correctly
  - A module that raises on import is skipped, its key is absent from the result, the failure is logged
  - `_filter_unknown_handlers` drops items whose target is absent
  - `_filter_unknown_handlers` drops empty submenus from parent menus that referenced them
  - Shell script targets and `sub:foo` targets are not filtered
- **Per-feature smoke.** No new automated tests for individual extractions — the existing `test_navigation.py` and `test_tui_integrity.py` already validate that menu items reference real handlers, which becomes the regression net.
- **Regression baseline.** Before phase A, capture full pytest output. After each phase, diff against baseline. The five known-failing tests in `test_navigation.py` / `test_tui_integrity.py` (orphan submenu refs) stay failing for the same reasons; nothing new should fail.
- **Live device smoke after each phase.** `make install` and walk the relevant menu in the TUI on the device.

## Risks and mitigations

- **Risk:** Eager-loading every feature module at startup adds cold-start latency. **Mitigation:** Match current behaviour — `_load_handlers` runs on first navigation into a feature, exactly when `_get_native_tools` runs today.
- **Risk:** A feature module imports framework symbols that aren't currently re-exported, so the extraction breaks the import. **Mitigation:** Phase A audits every existing feature module's imports from `tui.framework`. Anything missing gets added to the public surface in phase A, before any extraction.
- **Risk:** The wardrive merge's duplicate `_ESP32_MIMICLAW_ITEMS` definition is currently dead code. Restoring the Settings entry surfaces a path that may or may not work end-to-end. **Mitigation:** Phase D smoke includes opening MimiClaw → Settings to confirm the existing `sub:mimiclaw:settings` submenu still resolves cleanly.
- **Risk:** A feature that takes a long time to import (e.g. `radio.py` pulling in heavy SDR libraries) makes startup feel slow. **Mitigation:** Out of scope for this refactor — same behaviour as today. If it becomes a problem, deferred-import wrappers are a follow-up task.
- **Risk:** The other chat starts another framework.py edit before tomorrow's execution. **Mitigation:** This doc is committed to dev. The other chat's status block already says they're done with this area pending the merge. Coordinate via shared dev branch state.

## Out of scope (explicitly deferred)

- YAML migration — Approach 2 step C. Deferred indefinitely; only revisit if a future need is concrete.
- Per-item icon overhaul. The other chat applied category-level emoji to `CAT_ICONS`; per-item icons are unchanged.
- Decorator-style registration (`@register("_foo")`). The manifest-export model is simpler and easier to grep.
- Convention-based discovery (auto-scanning `tui/*.py`). Explicit `FEATURE_MODULES` list is easier to reason about.
- Removing the trivial `_Firmware_*` wrappers in any context other than the ESP32 hub extraction (they are removed there as part of phase D).

## Open question for tomorrow's execution session

- **Phase ordering tweak:** if phase A's audit reveals that a feature module is already importing something framework hasn't been re-exporting, the missing re-export gets added in phase A and the rest proceeds. If multiple modules are doing it, consider a dedicated phase A.5 for "expand framework public surface." Decide at the audit step.

## Acceptance criteria

The refactor is done when, on dev:

1. `git diff main..dev -- device/lib/tui/framework.py` shows a net reduction of ≥600 lines.
2. `device/lib/tui/esp32_hub.py`, `tui/processes.py`, `tui/adsb_menu.py` exist with `HANDLERS` exports.
3. `NATIVE_TOOLS` and `_get_native_tools` are absent from framework.py.
4. Every existing feature module under `tui/` exports `HANDLERS`.
5. The TUI launches; all 9 categories render; every smoke-tested item still works.
6. Deliberately breaking one feature module hides its menu items and logs to `~/crash.log` — TUI otherwise unaffected.
7. `tests/test_handler_registry.py` passes.
8. Existing tests have no new failures (pre-existing 5 known failures continue at parity).
