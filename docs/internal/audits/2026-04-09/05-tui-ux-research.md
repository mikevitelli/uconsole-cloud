# 05 Tui Ux Research

*Generated: 2026-04-09*

Now I have a thorough understanding of the entire TUI codebase. Let me compile my analysis.

---

Here is the full research report.

## 1. Comparison with Similar TUI Projects

### Resizing

**What btop/htop/lazygit do:** They handle `KEY_RESIZE` (triggered by SIGWINCH) explicitly, re-querying terminal dimensions and redrawing all panels. btop collapses or hides panels when the terminal is too narrow to fit them. lazygit maintains fixed panel ratios and reflows content.

**What uconsole does:** Every render loop iteration calls `scr.getmaxyx()` at the top, so it naturally adapts to size changes -- this is correct. However, there is no explicit `KEY_RESIZE` handling anywhere in the codebase (confirmed via grep). Python curses does generate `KEY_RESIZE` when the terminal resizes, and since the TUI just calls `scr.erase()` and redraws everything each frame, resizing will work in practice. The issue is that `KEY_RESIZE` is consumed by `get_key()` and treated as a no-op (falls through without matching any handler), which is fine but could be explicitly handled for clarity.

**Gap:** No graceful degradation at small sizes. More on this in section 2.

### Mouse Support

**What btop/htop do:** btop has full mouse support -- clickable buttons, scrollable lists. htop lets you click column headers to sort and click processes to select them. lazygit supports mouse for panel selection.

**What uconsole does:** Zero mouse support. `curses.mousemask()` is never called. No `BUTTON` event handling anywhere.

**Actionable suggestion:** Add optional mouse support:
- `curses.mousemask(curses.ALL_MOUSE_EVENTS)` at init
- In the main menu, clicking on a menu item selects and runs it
- In panel/stream views, mouse scroll maps to scroll up/down
- In tile view, clicking a tile selects it
- The uConsole has a trackball (mapped as a mouse), so this would be immediately useful. This is probably the single highest-impact missing feature -- users could trackball-click through menus.

### Help/Keybinds Display

**What btop does:** Press `?` or `h` anywhere to open contextual help. lazygit shows a persistent keybind bar at the bottom of each panel that changes based on context. ranger shows `?` help overlay.

**What uconsole does:** There is a static keybind reference screen at `CONFIG > Keybinds` (`run_keybinds` in tools.py, line 426). The footer bar shows context-sensitive hints per view. However, there is no `?` or `h` shortcut to open help from anywhere. You have to navigate to `CONFIG > Keybinds` to see the reference.

**Actionable suggestion:** Add a global `?` key handler in `_tui_input_loop` or at the main loop level that opens `run_keybinds()` from any screen. This is a ~5-line change.

### Search/Filter in Menus

**What lazygit does:** Press `/` in any panel to filter. btop has `f` to filter the process list. ranger has `/` for search-as-you-type that jumps to matching files.

**What uconsole does:** No search or filter capability anywhere. The main menu has 9 categories with 4-5 items each, and submenus can have up to 17 items (e.g., `sub:battest`). The process manager has no filter. The file browser has no search. The Hacker News viewer has no filter.

**Actionable suggestion:** Add `/` search to the main menu and submenus. Since items are tuples with name+description, search could match against both. Implementation: when `/` is pressed, show a text input line at the bottom (similar to how notes/calculator already do inline text entry via `scr.getstr()`), filter the items list to matches, and let the user navigate the filtered results. Start with the main menu and process manager, then extend to file browser.

---

## 2. Accessibility: Small Terminal Sizes

The uConsole's physical screen is 1280x720 at 5 inches. At default font sizes in foot terminal, this gives roughly 80x24 (confirmed: `tput cols` = 80, `tput lines` = 24). This is the primary use case.

### Current issues at small sizes:

**ASCII header is too wide.** The `HEADER` array in framework.py (lines 307-313) is a fixed 79-character-wide box art banner. On any terminal narrower than 79 columns, it will be clipped by `addnstr`. At the default 80 columns, there is only 1 character of margin.

**Category tabs overflow.** `draw_category_tabs` (line 639) lays out all 9 category names horizontally. At 80 columns with 1-char gaps, the categories take approximately 72 characters (SYSTEM + MONITOR + FILES + POWER + NETWORK + HARDWARE + TOOLS + GAMES + CONFIG). This barely fits at 80 columns. Below ~70 columns, later categories would be clipped.

**Tile view minimum width.** `TILE_W_MIN = 22` and with 2px margins per side and 1px gap, a single column of tiles needs 26 characters. Two columns need 47. Three need 68. At 80 columns, you get 3 columns of tiles. At 40 columns, you'd get 1. This actually scales reasonably well.

**Monitor layout is hardcoded to 2-column.** The `run_live_monitor` function divides the screen at `mid = w // 2`. At 40 columns, each panel gets ~18 characters of usable width, which means gauge bars are 14 characters wide. Braille graphs at 14 characters wide are 28 pixels -- barely legible but functional. At 80 columns (the actual use case), each panel gets ~38 characters, which works well.

**No minimum size guard.** No screen in the TUI checks for a minimum usable size. If the terminal is too small (e.g., 16x40 as mentioned), many screens would crash or produce garbled output. The monitor would attempt 2-column layout in 40 columns with each panel at 18 chars, the header would be clipped, and tiles would be oversized.

**Actionable suggestions:**
1. Add a minimum size check at the top of `entry()`: if `h < 16 or w < 40`, show a centered message "Terminal too small (need 40x16)" and wait for resize.
2. Replace the ASCII header with a shorter variant when `w < 60`. For example, just `" UCONSOLE COMMAND CTR "` centered. The 79-char box art header is charming but wastes 5 lines of vertical space on a 24-line terminal -- that's 20% of the screen.
3. In the monitor, switch to single-column layout when `w < 60`.

---

## 3. Performance Analysis

### Rendering loop

Every main loop iteration does:
1. `scr.erase()` -- clears entire screen buffer
2. Redraws everything from scratch
3. `scr.refresh()` -- flushes to terminal

This is the standard approach for curses TUIs (btop and htop do the same). The key question is whether the redraw frequency is appropriate.

**Main menu:** `scr.timeout(100)` = 10 redraws/second. This is appropriate for the scrolling marquee info bar. Each redraw is cheap (drawing ~20 lines of text).

**Tile view:** `scr.timeout(200)` = 5 redraws/second. Also appropriate for the marquee animation.

**Monitor:** `scr.timeout(1000)` = 1 redraw/second. Perfect for a system monitor.

**Stream view:** `scr.timeout(150)` = ~7 redraws/second. Needed for spinner animation and live output. The thread-safe `lines_lock` is correctly used.

### Specific performance concerns:

**`get_quick_info()` calls external processes.** Lines 2143-2225 call `hostname -I`, `iwgetid`, `iwconfig`, and read multiple `/proc` and `/sys` files. This runs every 30 seconds (good) but also after every script execution (line 2369). The `hostname -I` and `iwgetid` calls spawn subprocesses. On a CM4, subprocess spawn costs ~10-20ms each. This is fine at 30s intervals but could add 50-100ms of latency when returning from a script.

**Hacker News fetches 20 stories serially.** `fetch_stories()` (tools.py line 891) does 21 sequential `curl` calls (1 for the list + 20 for individual stories). On a slow connection, this could take 30+ seconds and blocks the TUI.

**Actionable suggestions:**
1. For HN stories, fetch in a background thread (like `run_stream` already does for subprocess output). Show a spinner while loading. Alternatively, batch the story IDs into fewer requests or use `curl --parallel`.
2. The `open("/proc/...")` and `open("/sys/...")` calls in the monitor never close their file handles explicitly (lines 99, 107-108, 145-148, etc.). These use Python's garbage collector to close them, which works but is sloppy. On every 1-second tick, the monitor opens ~10 files and relies on GC. Use `with` statements or explicit closes.
3. The `_resolve_cmd()` function (line 764) does a filesystem walk every time a script is run. The search paths are static. Cache the resolution results in a dict to save ~10 `os.path.isfile()` calls per invocation.

---

## 4. Gamepad UX Analysis

### Current mapping (framework.py lines 322-326):

```
GP_A = 1    # Enter / Run
GP_B = 2    # Back
GP_X = 0    # Refresh
GP_Y = 3    # Quit
```

D-pad maps to arrow keys (handled by the kernel joystick driver as axis events, but the code only reads button events -- wait, let me check).

Looking at `read_gamepad()` (line 396): it only processes `typ == 1` (button) events with `val == 1` (press). **D-pad events are axis events (typ == 2), not button events.** This means the D-pad is NOT being read by the gamepad reader. D-pad only works because the uConsole's AIO board maps D-pad to keyboard arrow keys at the hardware level.

This is actually correct for the uConsole's AIO board (D-pad sends keycodes, not joystick axes), but it means the gamepad reader is effectively only reading ABXY buttons, with D-pad coming through as regular keyboard input.

### Issues with the current mapping:

**B-button double-exit problem.** The code has a `_gp_back_cooldown` mechanism (line 1326) specifically to prevent the B button from triggering "back" twice when returning from sub-views. This is a UX smell -- it means the gamepad input flushing between views isn't reliable. The 0.5s cooldown works but feels laggy if you legitimately want to press B twice quickly.

**Y-button ambiguity.** At the top level, Y = quit the entire TUI. In sub-views, Y = back. This dual mapping (line 1380: `"quit" if map_y_quit else "back"`) is confusing -- the same physical button does different things depending on context with no visual indicator.

**No gamepad PageUp/PageDown.** In panel views with long output, you can only scroll one line at a time with D-pad. ABXY are mapped but none does page-scroll. The code does remap A to "scroll_down" in panel view (line 929), which is clever, but there's no "scroll_up" equivalent and no page-jump.

**Actionable suggestions:**
1. In panel/stream views, map A = page down, X = page up. This gives fast scrolling without needing PgUp/PgDn keys.
2. Make Y always "back" (never "quit"). Add a quit confirmation dialog when pressing Y at the top level, or just use `q` for quit (keyboard only). This eliminates the dual-mapping confusion.
3. Consider adding axis event handling (typ == 2) to `read_gamepad()` as a fallback for non-AIO boards, or if the CM5 upgrade changes the D-pad behavior.

---

## 5. Feature Gaps for Handheld Daily Use

Based on the existing feature set and the handheld use case (walking around with a uConsole), here are the gaps:

### High Priority

**1. Quick-launch favorites / recent items.** With 9 categories and 50+ total items, navigating to a frequently-used tool takes 3-5 button presses. Add a "RECENT" or "FAVORITES" category at the top that auto-populates with the last 5-8 run items. Implementation: write the script name to config on each run, display as the first category. This would dramatically speed up repeated workflows.

**2. Inline search (covered above).** For someone standing and holding the device, counting D-pad presses to reach item 12 in the battery test submenu is painful. `/` search would fix this.

**3. Notification/alert on long-running tasks.** When `run_stream` finishes a long operation (e.g., "Update All" takes minutes), the only indicator is the spinner changing to a checkmark. Add `curses.beep()` or `curses.flash()` when a stream finishes. This is a 1-line addition.

**4. Quick toggle shortcuts.** Add single-key shortcuts for the most common operations:
   - `w` from anywhere = WiFi switcher (the most common handheld need)
   - `m` from anywhere = live monitor
   - `b` from anywhere = battery status
   These bypass menu navigation entirely. Implementation: add handlers in the main loop before the category navigation block.

### Medium Priority

**5. Status bar enrichment.** The scrolling info bar shows UP/LOAD/MEM/DISK/IP/BAT/WIFI/ESP32. For handheld use, add GPS position (lat/lon or "No Fix"), LoRa status (listening/idle), and current WiFi hotspot state (AP active/inactive). These are the things you check constantly when mobile.

**6. Command history in panel views.** The panel viewer shows output from a single script run. Add the ability to see the last N runs of the same script (cached in memory). This is useful for comparing "Battery Status" readings over time without manually re-running.

**7. Clipboard integration.** When viewing output (panel/stream), there's no way to copy text. Add a "yank line" key (Y or `y` in panel view) that copies the selected line to the clipboard via `wl-copy` or `xclip`. Especially useful for IP addresses, URLs from HN, GPS coordinates.

### Lower Priority

**8. Offline-first HN/Forum/Weather.** The HN fetcher does 21 serial HTTP requests. For handheld use where connectivity is intermittent, cache the last-fetched data to disk (not just in-memory like weather currently does). Show "[cached 2h ago]" when offline.

**9. Split-screen monitor.** Allow pinning the battery/temp gauge to a corner while navigating menus. The monitor currently takes over the full screen. A persistent 2-line status strip (battery + temp + wifi) at the top of the main menu would provide at-a-glance info without entering the monitor.

**10. ROM launcher quick-resume.** If the GAMES category is used frequently, add a "Resume Last" option that re-launches the last ROM with the same emulator and save state.

---

## Summary of Highest-Impact Changes

Ranked by effort-to-impact ratio:

| Change | Effort | Impact |
|--------|--------|--------|
| Add `?` global help key | 5 lines | Discoverability |
| Add `curses.beep()` on stream finish | 1 line | Handheld usability |
| Add mouse support (trackball clicks) | ~30 lines | Major UX win |
| Add "RECENT" favorites category | ~40 lines | Daily speed |
| Add `/` search in menus | ~50 lines | Navigation speed |
| Add quick-toggle keys (w/m/b) | ~15 lines | Handheld speed |
| Minimum terminal size guard | ~10 lines | Crash prevention |
| Cache `_resolve_cmd()` results | ~8 lines | Performance |
| Background-thread HN fetch | ~20 lines | Prevents freezing |
| Close /proc file handles properly | ~30 lines (with statements) | Resource hygiene |