# Console TUI

The uConsole Command Center (`scripts/console.py`) is a full-screen terminal UI for managing the system. It runs directly on the uConsole's built-in screen and supports both keyboard and gamepad input.

## Quick Start

```bash
console              # launch (symlinked from ~/.local/bin)
console.sh           # alternative via scripts/
```

## Views

Two view modes, switchable via CONFIG > View Mode:

- **List view** — vertical list with category tabs across the top
- **Tile view** — category tiles drill down into item tiles with directional navigation

## Categories

| Category | Contents |
|----------|----------|
| **SYSTEM** | Update (all/apt/flatpak/status/log), Backup (all/git/system/packages/status) |
| **MONITOR** | Live system monitor, process manager, system log viewer, crash log |
| **FILES** | File browser, audit (junk/untracked/categories), disk usage, storage |
| **POWER** | Battery status, cell health (quick/full/log), charge rate, PMU, CPU freq cap, power control |
| **NETWORK** | WiFi switcher, network info, speed test, scan, ping, traceroute, Bluetooth, SSH bookmarks |
| **SERVICES** | Webdash (status/config/start/stop/restart/logs), cron/timers, AIO board check |
| **TOOLS** | Git panel, quick notes, calculator, stopwatch, screenshot |
| **CONFIG** | Color theme (6 themes), view mode (list/tiles), keybind reference |

## Live Monitor

Real-time dashboard updating every second with a two-column layout:

**Left column:**
- CPU — gauge bar, sparkline history, load averages, frequency, core count, top 4 processes
- Memory — gauge bar, sparkline, used/total, buffers/cache/swap
- Disk — gauge bar, used/free/total

**Right column:**
- Temperature — gauge bar, sparkline, governor, thermal status
- Battery — gauge bar, sparkline, voltage/current, estimated time remaining or charge rate
- Network — rx/tx rates, sparklines, WiFi SSID, IP, signal strength, total transferred

Color-coded thresholds: green (OK) → yellow (warning) → red (critical).

## Native TUI Tools

These run entirely within the TUI (no external scripts):

| Tool | Description |
|------|-------------|
| Live Monitor | Real-time gauges, sparklines, and stats |
| Process Manager | View processes, sort by CPU/MEM, kill with A |
| File Browser | Navigate directories, view file sizes |
| WiFi Switcher | Scan networks, connect via nmcli |
| Bluetooth | View paired devices, connect/disconnect |
| Git Panel | Repo status, recent commits, remote tracking |
| System Logs | Live journalctl with error highlighting |
| Quick Notes | Timestamped scratchpad saved to ~/notes.txt |
| SSH Bookmarks | Parse ~/.ssh/config, one-press connect |
| Cron Viewer | Crontab + systemd timers (system and user) |
| Calculator | Math expression evaluator with history |
| Stopwatch | Start/stop/reset with large centered display |
| Screenshot | Capture screen to PNG via scrot |
| Keybind Reference | Full keyboard and gamepad mapping |

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

## Color Themes

Six built-in themes, selectable via CONFIG > TUI Theme:

- **cyan** (default) — cyan headers, yellow categories
- **green** — green headers, cyan categories
- **amber** — yellow/amber monochrome
- **red** — red headers and borders
- **magenta** — magenta accents
- **blue** — blue headers and selection

Theme is saved to `scripts/.console-config.json`.

## Script Execution Modes

| Mode | Icon | Behavior |
|------|------|----------|
| panel | ◈ | Capture output, show in scrollable viewer with colorized rendering |
| stream | ▶ | Stream output live with spinner, auto-scroll |
| action | ⚡ | Quick run, flash result in status bar |
| fullscreen | ◻ | Drop to raw terminal for interactive scripts |

## Panel Viewer Features

- Centered output with colorized key:value lines
- Box-drawing characters rendered in border color
- Section headers highlighted
- Visual scrollbar on right edge with percentage
- X to re-run the script and refresh output

## Configuration

Config file: `scripts/.console-config.json`

```json
{
  "theme": "cyan",
  "view_mode": "list"
}
```

## Architecture

- Single-file Python TUI: `scripts/console.py` (~2800 lines)
- Wrapper: `scripts/console.sh`
- Symlink: `~/.local/bin/console → scripts/console.py`
- Uses curses for rendering, supports UTF-8 box-drawing and sparkline characters
- Gamepad input via `/dev/input/js0` (non-blocking)
- External scripts called via subprocess with ANSI stripping
- Native tools run as curses sub-loops within the same process
