# Console TUI

The uConsole Command Center is a full-screen terminal UI for managing the system. Launcher: `console` (resolves to `device/bin/console` in the source tree, `/opt/uconsole/bin/console` when installed via `.deb`). Calls into the modular framework at `device/lib/tui/framework.py` and 25 feature modules. Supports keyboard and gamepad input.

## Quick start

```bash
console              # default — auto-detects ~/uconsole-cloud/device/lib/ for devs
console-pkg          # force the deployed copy at /opt/uconsole/lib/ (Ctrl+Shift+P)
console-dev          # force the source tree (Ctrl+`) — redundant with default
```

## Views

Two view modes, switchable via CONFIG → View Mode:

- **List view** — vertical list with category tabs across the top
- **Tile view** — emoji-iconed category tiles, drill down into item tiles with directional navigation

## Categories

| Category | Contents |
|----------|----------|
| **SYSTEM** | Updates, Backups, Webdash control, Cron/Timer viewer |
| **MONITOR** | Live system monitor, process manager, system log viewer, crash log |
| **FILES** | File browser, audit (junk/untracked/categories), disk usage, storage |
| **POWER** | Battery status, cell health, battery test, power control, hardware config |
| **NETWORK** | iPhone hotspot connect, WiFi, diagnostics, Bluetooth, SSH bookmarks |
| **HARDWARE** | AIO board check, GPS receiver, SDR radio, **ADS-B map** (global basemap, hi-res fetch, layer picker), LoRa Mesh (Meshtastic), **ESP32 hub** (firmware detect, MicroPython/Marauder/MimiClaw/Bruce flashing, war drive, mimiclaw chat) |
| **TOOLS** | Git panel, quick notes, calculator, stopwatch, pomodoro, weather, Hacker News, uConsole forum, **Telegram** (terminal chat via tg + tdlib), markdown viewer, screenshot |
| **GAMES** | **Watch Dogs Go** (auto-installs from GitHub on first run), minesweeper, snake, tetris, 2048, ROM launcher |
| **CONFIG** | TUI theme, view mode, keybinds reference, battery gauge style, trackball scroll, push interval, Watch Dogs config |

9 categories, 64 native handlers, plus shell-script targets that run via panel/stream/action/fullscreen modes.

## Live Monitor

Real-time dashboard, 1-second tick, two-column layout.

**Left:** CPU (gauge, sparkline, load avg, freq, top 4 procs), Memory (gauge, sparkline, used/total), Disk (gauge, used/free).

**Right:** Temperature (gauge, sparkline, governor), Battery (gauge, sparkline, voltage, time-left), Network (rx/tx rates, sparklines, SSID, IP, signal).

Color-coded thresholds: green (OK) → yellow (warning) → red (critical).

## Controls

### Keyboard

| Key | Main Menu | Panel Viewer | Stream Viewer |
|-----|-----------|-------------|---------------|
| ↑/↓ or k/j | Navigate items | Scroll output | — |
| ←/→ or h/l | Switch category | — | — |
| Enter | Run selected | Close | Close (when done) |
| r | Refresh stats | Re-run script | Re-run (when done) |
| q | Quit | Back to menu | Stop / Back |
| PgUp/PgDn | — | Page scroll | — |

### Gamepad

| Button | Action |
|--------|--------|
| A (btn 1) | Enter / Confirm / Scroll down |
| B (btn 2) | Back / Previous category |
| X (btn 0) | Refresh / Re-run script |
| Y (btn 3) | Quit |
| D-pad | Arrow key navigation |

## Themes

30+ built-in color themes selectable via CONFIG → TUI Theme — classic single-accent (cyan, green, amber, red, magenta, blue, white), duo combos (synthwave, hotline, ocean, forest, etc.), and a long tail of named palettes. Theme is saved to `/opt/uconsole/scripts/.console-config.json`.

## Script execution modes

| Mode | Behavior |
|------|----------|
| `panel` | Capture script output, show in scrollable viewer with colorized rendering |
| `stream` | Stream output live with spinner, auto-scroll |
| `action` | Quick run, flash result in status bar |
| `fullscreen` | Drop to raw terminal for interactive scripts |
| `submenu` | Drilldown to another menu |

## Architecture

- Modular Python package: `device/lib/tui/` — `framework.py` (drawing, runners, input, registry plumbing) plus 25 feature modules
- Each feature module exports a `HANDLERS = {"_foo": fn}` dict at module scope; framework.py walks `FEATURE_MODULES` and merges them on first menu interaction
- A feature module that fails to import is logged to `~/crash.log` and its menu items are hidden — the rest of the TUI keeps working
- Curses for rendering, UTF-8 box-drawing + sparkline characters, color emoji icons in tile view
- Gamepad via `/dev/input/js0` (non-blocking)
- External scripts via subprocess with ANSI stripping
- External GUI programs (emulators, Watch Dogs Go) launch through a shared `tui.launcher` helper using `start_new_session=True` + `DEVNULL` stdio, so a child crash can't disturb the curses parent

For the full data flow and project layout, see [ARCHITECTURE.md in the repo](https://github.com/mikevitelli/uconsole-cloud/blob/main/docs/ARCHITECTURE.md).
