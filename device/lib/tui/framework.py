#!/usr/bin/env python3
"""uConsole Command Center — full-screen TUI launcher."""

import curses
import fcntl
import json
import math
import subprocess
import os
import sys
import time
import signal
import struct
import select
import threading
import tty
import termios
import re

# Allow importing tui_lib from multiple locations
for _p in [os.path.dirname(os.path.realpath(__file__)),
           os.path.expanduser('~/scripts'),
           '/opt/uconsole/lib']:
    if _p not in sys.path:
        sys.path.insert(0, _p)
import tui_lib as tui

# SCRIPT_DIR: resolve relative to this file's package, env override available
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_DIR = os.environ.get('UCONSOLE_SCRIPTS',
    os.path.join(_PKG_ROOT, 'scripts') if os.path.isdir(os.path.join(_PKG_ROOT, 'scripts'))
    else '/opt/uconsole/scripts')
CONFIG_FILE = os.path.join(SCRIPT_DIR, ".console-config.json")

# Package version — read from VERSION file next to package root
_VERSION_FILE = os.path.join(_PKG_ROOT, 'VERSION')
if not os.path.isfile(_VERSION_FILE):
    _VERSION_FILE = '/opt/uconsole/VERSION'
try:
    with open(_VERSION_FILE) as _f:
        PKG_VERSION = _f.read().strip()
except OSError:
    PKG_VERSION = ""

# ── Menu structure ──────────────────────────────────────────────────────────
# Display modes:
#   "panel"    — capture output, show in scrollable curses panel
#   "stream"   — long-running: stream output with spinner in curses panel
#   "action"   — quick command: flash result in status bar
#   "fullscreen" — interactive: drop to raw terminal
#   "submenu"  — drill into a sub-menu (script field = key into SUBMENUS dict)

# ── Sub-menus (referenced by key from main menu items) ─────────────────────

SUBMENUS = {
    "sub:updates": [
        ("Update All",       "system/update.sh all",       "apt + flatpak + firmware + repo sync",   "stream"),
        ("Update APT",       "system/update.sh apt",       "update apt packages",                    "stream"),
        ("Update Flatpak",   "system/update.sh flatpak",   "update flatpak apps",                    "stream"),
        ("Update Status",    "system/update.sh status",    "check what's outdated",                  "panel"),
        ("Update Log",       "system/update.sh log",       "show update history",                    "panel"),
    ],
    "sub:backups": [
        ("Backup All",       "system/backup.sh all",       "run all backup categories",              "stream"),
        ("Backup Git",       "system/backup.sh git",       "git config and SSH keys",                "stream"),
        ("Backup System",    "system/backup.sh system",    "etc configs, hostname, fstab, crontab",  "stream"),
        ("Backup Packages",  "system/backup.sh packages",  "snapshot all package managers",          "stream"),
        ("Backup Status",    "system/backup.sh status",    "show backup coverage overview",          "panel"),
    ],
    "sub:cell_health": [
        ("Quick Check",      "power/cellhealth.sh quick",  "quick voltage sag check",               "stream"),
        ("Full Test",        "power/cellhealth.sh",        "full 18650 sag and recovery test",      "stream"),
        ("History",          "power/cellhealth.sh log",    "show cell health history",               "panel"),
    ],
    "sub:disk": [
        ("Disk Overview",    "util/diskusage.sh",        "filesystem usage summary",               "panel"),
        ("Big Files",        "util/diskusage.sh big",    "largest files on disk",                  "panel"),
        ("Top Directories",  "util/diskusage.sh dirs",   "top directories by size",                "panel"),
    ],
    "sub:storage": [
        ("Overview",         "util/storage.sh",          "filesystems, blocks, I/O",               "panel"),
        ("Block Devices",    "util/storage.sh devices",  "block device details",                   "panel"),
        ("USB Devices",      "util/storage.sh usb",      "connected USB devices",                  "panel"),
        ("Drive Temps",      "util/storage.sh temp",     "drive temperatures",                     "panel"),
    ],
    "sub:audit": [
        ("Junk Files",       "util/audit.sh junk",       "detect junk files in repo",              "panel"),
        ("Untracked Files",  "util/audit.sh untracked",  "show untracked files",                   "panel"),
        ("Category Coverage","util/audit.sh categories",  "backup category coverage",              "panel"),
    ],
    "sub:webdash": [
        ("Status",           "util/webdash-info.sh",         "service, nginx, SSL, auth status",   "panel"),
        ("Config",           "_webdash_config",              "change username and password",       "action"),
        ("Start",            "util/webdash-ctl.sh start",    "start webdash service",              "action"),
        ("Stop",             "util/webdash-ctl.sh stop",     "stop webdash service",               "action"),
        ("Restart",          "util/webdash-ctl.sh restart",  "restart webdash service",            "action"),
        ("Logs",             "util/webdash-ctl.sh logs",     "recent webdash log output",          "panel"),
        ("Push Status",      "system/push-status.sh",        "push system status to uconsole.cloud", "action"),
        ("Push Interval",    "_push_interval",               "set cloud status push frequency",    "action"),
    ],
    "sub:hw_config": [
        ("PMU Voltage Min",  "power/pmu-voltage-min.sh",  "set undervoltage cutoff to 2.9 V",      "action"),
        ("CPU Freq Cap",     "power/cpu-freq-cap.sh",     "cap CPU at 1.2 GHz for battery",        "action"),
        ("Charge Rate",      "power/charge.sh",           "set charge current (300-900 mA)",        "fullscreen"),
        ("Fix Voltage Cutoff","power/fix-voltage-cutoff.sh","install 2.9 V cutoff (community fix)", "action"),
    ],
    "sub:power_ctl": [
        ("Power Status",     "power/power.sh status",     "current power state",                    "panel"),
        ("Low Batt Status",  "power/low-battery-shutdown.sh status", "voltage vs shutdown threshold", "panel"),
        ("Reboot",           "power/power.sh reboot",     "reboot with 3s delay",                   "fullscreen"),
        ("Shutdown",         "power/power.sh shutdown",   "power off with 3s delay",                "fullscreen"),
    ],
    "sub:wifi": [
        ("WiFi Switcher",    "_wifi",               "scan and connect to networks",           "action"),
        ("WiFi Scan",        "network/network.sh scan",     "nearby WiFi networks",                   "panel"),
        ("Hotspot Toggle",   "_hotspot_toggle",     "start/stop WiFi hotspot",                "action"),
        ("Hotspot Config",   "_hotspot_config",     "change AP name and password",            "action"),
        ("WiFi Fallback",    "_wifi_fallback",      "auto iPhone hotspot → AP on WiFi loss",  "action"),
    ],
    "sub:diagnostics": [
        ("Network Info",     "network/network.sh",          "connection overview",                    "panel"),
        ("Speed Test",       "network/network.sh speed",    "download and upload speed",              "stream"),
        ("Ping Test",        "network/network.sh ping",     "latency test (1.1.1.1)",                "panel"),
        ("Traceroute",       "network/network.sh trace",    "network path trace",                    "panel"),
        ("Network Log",      "network/network.sh log",      "append entry to network.log",           "action"),
    ],
    "sub:battest": [
        ("Start: Nitecore-3400",  "power/battery-test.sh start nitecore-3400",  "control — 3400mAh",           "action"),
        ("Start: Panasonic-GA",   "power/battery-test.sh start panasonic-ga",   "3450mAh 10A",                 "action"),
        ("Start: Samsung-35E",    "power/battery-test.sh start samsung-35e",    "3500mAh 8A",                  "action"),
        ("Start: Samsung-30Q",    "power/battery-test.sh start samsung-30q",    "3000mAh 15A",                 "action"),
        ("Stop Test",             "power/battery-test.sh stop",                 "stop active test",            "action"),
        ("Status",                "power/battery-test.sh status",               "show active test info",       "panel"),
        ("Live View",             "power/battery-test.sh live",                 "tail active test log",        "fullscreen"),
        ("List Tests",            "power/battery-test.sh list",                 "all completed tests",         "panel"),
        ("Compare",               "power/battery-test.sh compare",             "side-by-side comparison",     "panel"),
        ("Voltage Chart",         "power/battery-test.sh chart",               "ASCII voltage curves",        "panel"),
        ("Health Report",         "power/battery-test.sh health",              "capacity, energy, temp stats", "panel"),
        ("Stress: Samsung-35E",   "power/battery-test.sh stress samsung-35e",  "max CPU load + logging",      "stream"),
        ("Stress: Nitecore",      "power/battery-test.sh stress nitecore-3400","max CPU load + logging",      "stream"),
        ("Calibrate Gauge",       "power/battery-test.sh calibrate",           "AXP228 fuel gauge reset",     "stream"),
        ("Discharge: Nitecore",   "util/discharge-test.sh nitecore-3400",      "overnight 30s log + git push","stream"),
        ("Discharge: Samsung-35E","util/discharge-test.sh samsung-35e",        "overnight 30s log + git push","stream"),
        ("Discharge: Samsung-30Q","util/discharge-test.sh samsung-30q",        "overnight 30s log + git push","stream"),
        ("Discharge: Panasonic",  "util/discharge-test.sh panasonic-ga",       "overnight 30s log + git push","stream"),
    ],
    "sub:esp32": [
        ("Marauder",         "_marauder",                 "WiFi/BLE attack toolkit (ESP32)",        "action"),
        ("Status",           "radio/esp32.sh status",     "latest sensor reading",                  "panel"),
        ("Live Monitor",     "_esp32_monitor",            "real-time sensor dashboard",             "action"),
        ("Serial Monitor",   "radio/esp32.sh serial",     "raw serial output",                      "fullscreen"),
        ("REPL",             "radio/esp32.sh repl",       "MicroPython interactive shell",          "fullscreen"),
        ("Flash",            "radio/esp32.sh flash",      "upload boot.py + main.py",               "stream"),
        ("Reset",            "radio/esp32.sh reset",      "hard-reset ESP32",                       "action"),
        ("Log Entry",        "radio/esp32.sh log",        "append reading to esp32.log",            "action"),
        ("Chip Info",        "radio/esp32.sh info",       "chip type, features, MAC",               "panel"),
    ],
    "sub:gps": [
        ("Status",           "radio/gps.sh status",       "position, altitude, satellites",          "panel"),
        ("Live Dashboard",   "radio/gps.sh live",         "real-time GPS display",                  "fullscreen"),
        ("Satellite Globe",  "_gps_globe",                "wireframe globe with satellites",         "action"),
        ("Start Tracking",   "radio/gps.sh track",        "log position to GPX file",               "action"),
        ("Stop Tracking",    "radio/gps.sh stop",         "stop active track log",                  "action"),
        ("NMEA Stream",      "radio/gps.sh nmea",         "raw NMEA sentence output",               "fullscreen"),
        ("Time Compare",     "radio/gps.sh time",         "GPS vs system vs RTC time",              "panel"),
        ("Log Position",     "radio/gps.sh log",          "append fix to gps.log",                  "action"),
    ],
    "sub:sdr": [
        ("Status",           "radio/sdr.sh status",       "RTL2838 device check",                   "panel"),
        ("Device Test",      "radio/sdr.sh test",         "tuner and sample rate test",             "stream"),
        ("Device Info",      "radio/sdr.sh info",         "detailed device capabilities",           "panel"),
        ("FM Radio",         "_fm_radio",                 "FM receiver with waveform",              "action"),
        ("ADS-B Aircraft",   "radio/sdr.sh adsb",         "track aircraft (dump1090)",              "fullscreen"),
        ("Freq Scan",        "radio/sdr.sh scan",         "power spectrum scan",                    "stream"),
        ("IoT Scanner",      "radio/sdr.sh 433",          "rtl_433 device decoder",                 "fullscreen"),
        ("Pager Decode",     "radio/sdr.sh decode",       "POCSAG/pager decoding",                  "fullscreen"),
        ("Record IQ",        "radio/sdr.sh record",       "capture raw IQ samples",                 "stream"),
    ],
    "sub:lora": [
        ("Status",           "radio/lora.sh status",      "SX1262 SPI check + config",              "panel"),
        ("Configuration",    "radio/lora.sh config",      "frequency, BW, SF, power",               "panel"),
        ("Send Message",     "radio/lora.sh send test",   "transmit test message",                  "action"),
        ("Listen",           "radio/lora.sh listen",      "receive incoming messages",               "fullscreen"),
        ("Ping / Range",     "radio/lora.sh ping",        "range test with RSSI",                   "stream"),
        ("Chat",             "radio/lora.sh chat",        "interactive LoRa chat",                  "fullscreen"),
        ("Bridge to Web",    "radio/lora.sh bridge",      "forward messages to webdash",            "fullscreen"),
    ],
}

CATEGORIES = [
    {
        "name": "SYSTEM",
        "items": [
            ("Updates",          "sub:updates",         "apt, flatpak, firmware",                 "submenu"),
            ("Backups",          "sub:backups",         "git, system, packages",                  "submenu"),
            ("Webdash",          "sub:webdash",         "dashboard, cloud push, logs",            "submenu"),
            ("Cron / Timers",    "_cron",               "view scheduled tasks",                   "action"),
        ],
    },
    {
        "name": "MONITOR",
        "items": [
            ("Live Monitor",     "_monitor",            "real-time CPU, RAM, temp, battery",      "action"),
            ("Processes",        "_processes",           "view and kill running processes",        "action"),
            ("System Logs",      "_syslog",             "live journalctl log viewer",             "action"),
            ("Crash Log",        "util/crash-log.sh",   "recent crash and boot errors",           "panel"),
        ],
    },
    {
        "name": "FILES",
        "items": [
            ("File Browser",     "_filebrowser",        "navigate directories and files",         "action"),
            ("Audit",            "sub:audit",           "junk, untracked, coverage",              "submenu"),
            ("Disk Usage",       "sub:disk",            "usage, big files, directories",          "submenu"),
            ("Storage",          "sub:storage",         "filesystems, devices, USB, temps",       "submenu"),
        ],
    },
    {
        "name": "POWER",
        "items": [
            ("Battery Status",   "power/battery.sh",    "voltage, current, capacity",             "panel"),
            ("Cell Health",      "sub:cell_health",     "voltage sag and recovery tests",         "submenu"),
            ("Battery Test",     "sub:battest",         "log, compare, discharge curves",         "submenu"),
            ("Power Control",    "sub:power_ctl",       "status, low-battery, reboot, shutdown",  "submenu"),
            ("Power Config",     "sub:hw_config",       "PMU, CPU, charge rate tuning",           "submenu"),
        ],
    },
    {
        "name": "NETWORK",
        "items": [
            ("Connect iPhone",   "network/wifi.sh iphone",      "join iPhone hotspot",            "stream"),
            ("WiFi",             "sub:wifi",            "switcher, scan, hotspot, fallback",      "submenu"),
            ("Diagnostics",      "sub:diagnostics",     "info, speed, ping, traceroute",          "submenu"),
            ("Bluetooth",        "_bluetooth",          "manage paired BT devices",               "action"),
            ("SSH Bookmarks",    "_ssh",                "connect to saved SSH hosts",              "action"),
        ],
    },
    {
        "name": "HARDWARE",
        "items": [
            ("AIO Board Check",  "radio/aio-check.sh",  "V1 board component status",              "panel"),
            ("GPS Receiver",     "sub:gps",             "position, tracking, satellites",          "submenu"),
            ("SDR Radio",        "sub:sdr",             "FM, ADS-B, scanning, decoding",          "submenu"),
            ("LoRa Radio",       "sub:lora",            "send, receive, range test",              "submenu"),
            ("ESP32",            "_esp32_hub",          "sensor, marauder, flash",                "action"),
        ],
    },
    {
        "name": "TOOLS",
        "items": [
            ("Git Panel",        "_git",                "repo status, commits, remote",           "action"),
            ("Quick Notes",      "_notes",              "scratchpad — view and add notes",        "action"),
            ("Calculator",       "_calc",               "math expression evaluator",              "action"),
            ("Stopwatch",        "_stopwatch",          "start, stop, reset timer",               "action"),
            ("Pomodoro",         "_pomodoro",           "focus timer with work/break cycles",     "action"),
            ("Weather",          "_weather",            "local forecast and conditions",          "action"),
            ("Hacker News",      "_hackernews",         "top stories from HN",                    "action"),
            ("uConsole Forum",   "_forum",              "ClockworkPi community topics",           "action"),
            ("Markdown Viewer",  "_mdviewer",           "render markdown notes",                  "action"),
            ("Screenshot",       "_screenshot",         "capture screen to PNG",                  "action"),
        ],
    },
    {
        "name": "GAMES",
        "items": [
            ("Minesweeper",      "_minesweeper",        "classic mine-clearing game",             "action"),
            ("Snake",            "_snake",              "eat food, grow, don't hit walls",        "action"),
            ("Tetris",           "_tetris",             "stack and clear falling blocks",         "action"),
            ("2048",             "_2048",               "slide and merge number tiles",           "action"),
            ("ROM Launcher",     "_romlauncher",        "launch Game Boy / N64 ROMs",             "action"),
        ],
    },
    {
        "name": "CONFIG",
        "items": [
            ("TUI Theme",        "_theme",              "change color theme",                     "action"),
            ("View Mode",        "_viewmode",           "switch between list and tile view",      "action"),
            ("Keybinds",         "_keybinds",           "keyboard and gamepad reference",         "action"),
            ("Battery Gauge",    "_bat_gauge",          "toggle voltage-est vs fuel gauge",       "action"),
            ("Trackball Scroll", "_trackball_scroll",   "Fn + trackball = scroll wheel",      "action"),
        ],
    },
]

# ── ASCII header ────────────────────────────────────────────────────────────
HEADER = [
    "┌─────────────────────────────────────────────────────────────────────────────┐",
    "│        ╦ ╦╔═╗╔═╗╔╗╔╔═╗╔═╗╦  ╔═╗  ╔═╗╔═╗╔╦╗╔╦╗╔═╗╔╗╔╔╦╗  ╔═╗╔╦╗╦═╗      │",
    "│        ║ ║║  ║ ║║║║╚═╗║ ║║  ║╣   ║  ║ ║║║║║║║╠═╣║║║ ║║  ║   ║ ╠╦╝      │",
    "│        ╚═╝╚═╝╚═╝╝╚╝╚═╝╚═╝╩═╝╚═╝  ╚═╝╚═╝╩ ╩╩ ╩╩ ╩╝╚╝═╩╝  ╚═╝ ╩ ╩╚═      │",
    "└─────────────────────────────────────────────────────────────────────────────┘",
]

FOOTER_HELP = " ↑↓ Navigate │ ←→ Category │ A Run │ B Back │ X Refresh │ Y Quit "

# ── Gamepad (js0) ─────────────────────────────────────────────────────────
JS_PATH = "/dev/input/js0"
JS_FMT = "IhBB"
JS_SIZE = struct.calcsize(JS_FMT)

# Button mapping: Y=3, X=0, B=2, A=1
GP_A = 1       # Enter / run
GP_B = 2       # Back (previous category)
GP_X = 0       # Refresh
GP_Y = 3       # Quit

# Gamepad ownership uses two layers:
# 1. Workspace detection — workspace-monitor daemon writes active workspace name
# 2. Keyboard claim — for multiple consoles on the same workspace, last keyboard
#    input wins. Both must agree for gamepad events to be processed.
_RUN_DIR = os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))
_WS_FILE = os.path.join(_RUN_DIR, "labwc-active-workspace")
_GP_CLAIM = os.path.join(_RUN_DIR, "console-gamepad-owner")
_MY_PID = str(os.getpid())
_MY_WORKSPACE = None  # set at startup


def _read_active_workspace():
    try:
        with open(_WS_FILE, "r") as f:
            return f.read().strip()
    except (OSError, ValueError):
        return None


def _init_workspace():
    global _MY_WORKSPACE
    _MY_WORKSPACE = _read_active_workspace()
    # Claim gamepad on startup (last launched instance wins initially)
    _claim_gamepad()


def _claim_gamepad():
    try:
        with open(_GP_CLAIM, "w") as f:
            f.write(_MY_PID)
    except OSError:
        pass


def _is_gamepad_owner():
    """Check workspace match AND claim ownership."""
    # Layer 1: workspace check (cross-workspace isolation)
    if _MY_WORKSPACE is not None:
        active = _read_active_workspace()
        if active is not None and active != _MY_WORKSPACE:
            return False
    # Layer 2: claim check (same-workspace isolation)
    try:
        with open(_GP_CLAIM, "r") as f:
            return f.read().strip() == _MY_PID
    except (OSError, ValueError):
        return False


def open_gamepad():
    """Open js0 in non-blocking mode. Returns file object or None."""
    try:
        f = open(JS_PATH, "rb")
        os.set_blocking(f.fileno(), False)
        return f
    except (OSError, FileNotFoundError):
        return None


def close_gamepad(js=None):
    """Close gamepad file descriptor."""
    if js is not None:
        try:
            js.close()
        except OSError:
            pass


def read_gamepad(js):
    """Read pending button presses. Returns [] if not the gamepad owner."""
    pressed = []
    if js is None:
        return pressed
    try:
        while True:
            data = js.read(JS_SIZE)
            if not data or len(data) < JS_SIZE:
                break
            _ts, val, typ, num = struct.unpack(JS_FMT, data)
            if typ & 0x80:
                continue  # skip init events
            if typ == 1 and val == 1:
                pressed.append(num)
    except (OSError, BlockingIOError):
        pass
    if not _is_gamepad_owner():
        return []
    return pressed


def get_key(scr):
    """Wrapper around getch() that claims gamepad on keyboard input."""
    key = scr.getch()
    if key > 0:
        _claim_gamepad()
    return key

# ── Color themes ──────────────────────────────────────────────────────────
C_HEADER   = 1
C_CAT      = 2
C_ITEM     = 3
C_SEL      = 4
C_DESC     = 5
C_BORDER   = 6
C_FOOTER   = 7
C_STATUS   = 8
C_DIM      = 9
# Dedicated pair slots for theme picker (avoids mutating C_DIM)
C_PICKER_SWATCH = 10
C_PICKER_PREV1  = 11
C_PICKER_PREV2  = 12
C_PICKER_PREV3  = 13
# Tile preview pairs are allocated dynamically per tile.
# Each tile gets 5 consecutive pair slots starting at TILE_PAIR_BASE.
# Tile i uses pairs: base + i*5 + 0..4  (hdr, cat, sel, brd, lbl)
TILE_PAIR_BASE = 30   # leaves room for C_OK/WARN/CRIT at 20-22

THEMES = {
    # ── classic (single accent) ──
    "cyan":     {"header": curses.COLOR_CYAN,    "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_CYAN,    "border": curses.COLOR_CYAN,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_WHITE,   "status": curses.COLOR_GREEN},
    "green":    {"header": curses.COLOR_GREEN,   "cat": curses.COLOR_CYAN,    "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_GREEN,   "border": curses.COLOR_GREEN,   "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_WHITE,   "status": curses.COLOR_CYAN},
    "amber":    {"header": curses.COLOR_YELLOW,  "cat": curses.COLOR_WHITE,   "item": curses.COLOR_YELLOW,  "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_YELLOW,  "border": curses.COLOR_YELLOW,  "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_YELLOW,  "status": curses.COLOR_GREEN},
    "red":      {"header": curses.COLOR_RED,     "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_RED,     "border": curses.COLOR_RED,     "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_WHITE,   "status": curses.COLOR_GREEN},
    "magenta":  {"header": curses.COLOR_MAGENTA, "cat": curses.COLOR_CYAN,    "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_MAGENTA, "border": curses.COLOR_MAGENTA, "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_WHITE,   "status": curses.COLOR_GREEN},
    "blue":     {"header": curses.COLOR_BLUE,    "cat": curses.COLOR_CYAN,    "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_WHITE, "sel_bg": curses.COLOR_BLUE,    "border": curses.COLOR_BLUE,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_WHITE,   "status": curses.COLOR_GREEN},
    "white":    {"header": curses.COLOR_WHITE,   "cat": curses.COLOR_WHITE,   "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_WHITE,   "border": curses.COLOR_WHITE,   "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_WHITE,   "status": curses.COLOR_WHITE},
    # ── duo (two-tone combos) ──
    "synthwave":{"header": curses.COLOR_MAGENTA, "cat": curses.COLOR_CYAN,    "item": curses.COLOR_MAGENTA, "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_CYAN,    "border": curses.COLOR_MAGENTA, "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_MAGENTA, "status": curses.COLOR_CYAN},
    "solar":    {"header": curses.COLOR_YELLOW,  "cat": curses.COLOR_RED,     "item": curses.COLOR_YELLOW,  "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_YELLOW,  "border": curses.COLOR_RED,     "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_RED,     "status": curses.COLOR_YELLOW},
    "ocean":    {"header": curses.COLOR_CYAN,    "cat": curses.COLOR_BLUE,    "item": curses.COLOR_CYAN,    "sel_fg": curses.COLOR_WHITE, "sel_bg": curses.COLOR_BLUE,    "border": curses.COLOR_BLUE,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_CYAN,    "status": curses.COLOR_GREEN},
    "forest":   {"header": curses.COLOR_GREEN,   "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_GREEN,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_GREEN,   "border": curses.COLOR_YELLOW,  "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_GREEN,   "status": curses.COLOR_YELLOW},
    "hotline":  {"header": curses.COLOR_RED,     "cat": curses.COLOR_MAGENTA, "item": curses.COLOR_RED,     "sel_fg": curses.COLOR_WHITE, "sel_bg": curses.COLOR_RED,     "border": curses.COLOR_MAGENTA, "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_RED,     "status": curses.COLOR_MAGENTA},
    "frost":    {"header": curses.COLOR_WHITE,   "cat": curses.COLOR_CYAN,    "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_WHITE,   "border": curses.COLOR_CYAN,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_CYAN,    "status": curses.COLOR_GREEN},
    "coral":    {"header": curses.COLOR_RED,     "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_RED,     "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_YELLOW,  "border": curses.COLOR_RED,     "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_RED,     "status": curses.COLOR_YELLOW},
    "aurora":   {"header": curses.COLOR_GREEN,   "cat": curses.COLOR_MAGENTA, "item": curses.COLOR_GREEN,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_GREEN,   "border": curses.COLOR_MAGENTA, "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_GREEN,   "status": curses.COLOR_MAGENTA},
    "twilight": {"header": curses.COLOR_BLUE,    "cat": curses.COLOR_MAGENTA, "item": curses.COLOR_BLUE,    "sel_fg": curses.COLOR_WHITE, "sel_bg": curses.COLOR_MAGENTA, "border": curses.COLOR_BLUE,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_BLUE,    "status": curses.COLOR_MAGENTA},
    "citrus":   {"header": curses.COLOR_YELLOW,  "cat": curses.COLOR_GREEN,   "item": curses.COLOR_YELLOW,  "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_GREEN,   "border": curses.COLOR_YELLOW,  "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_YELLOW,  "status": curses.COLOR_GREEN},
    "arctic":   {"header": curses.COLOR_CYAN,    "cat": curses.COLOR_WHITE,   "item": curses.COLOR_CYAN,    "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_WHITE,   "border": curses.COLOR_CYAN,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_CYAN,    "status": curses.COLOR_WHITE},
    "neon":     {"header": curses.COLOR_GREEN,   "cat": curses.COLOR_RED,     "item": curses.COLOR_GREEN,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_RED,     "border": curses.COLOR_GREEN,   "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_GREEN,   "status": curses.COLOR_RED},
    "vapor":    {"header": curses.COLOR_MAGENTA, "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_MAGENTA, "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_YELLOW,  "border": curses.COLOR_MAGENTA, "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_MAGENTA, "status": curses.COLOR_YELLOW},
    "hazard":   {"header": curses.COLOR_YELLOW,  "cat": curses.COLOR_RED,     "item": curses.COLOR_RED,     "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_YELLOW,  "border": curses.COLOR_RED,     "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_YELLOW,  "status": curses.COLOR_RED},
    "sakura":   {"header": curses.COLOR_MAGENTA, "cat": curses.COLOR_WHITE,   "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_MAGENTA, "border": curses.COLOR_WHITE,   "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_MAGENTA, "status": curses.COLOR_WHITE},
    "jungle":   {"header": curses.COLOR_GREEN,   "cat": curses.COLOR_CYAN,    "item": curses.COLOR_CYAN,    "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_GREEN,   "border": curses.COLOR_CYAN,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_GREEN,   "status": curses.COLOR_CYAN},
    "lava":     {"header": curses.COLOR_RED,     "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_YELLOW,  "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_RED,     "border": curses.COLOR_YELLOW,  "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_RED,     "status": curses.COLOR_YELLOW},
    "electric": {"header": curses.COLOR_CYAN,    "cat": curses.COLOR_MAGENTA, "item": curses.COLOR_MAGENTA, "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_CYAN,    "border": curses.COLOR_MAGENTA, "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_CYAN,    "status": curses.COLOR_MAGENTA},
    "midnight": {"header": curses.COLOR_BLUE,    "cat": curses.COLOR_CYAN,    "item": curses.COLOR_CYAN,    "sel_fg": curses.COLOR_WHITE, "sel_bg": curses.COLOR_BLUE,    "border": curses.COLOR_CYAN,    "footer_fg": curses.COLOR_WHITE, "footer_bg": curses.COLOR_BLUE,    "status": curses.COLOR_CYAN},
    "rust":     {"header": curses.COLOR_RED,     "cat": curses.COLOR_WHITE,   "item": curses.COLOR_WHITE,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_RED,     "border": curses.COLOR_WHITE,   "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_RED,     "status": curses.COLOR_WHITE},
    "toxic":    {"header": curses.COLOR_GREEN,   "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_YELLOW,  "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_YELLOW,  "border": curses.COLOR_GREEN,   "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_GREEN,   "status": curses.COLOR_YELLOW},
    # ── mono (single-color immersive) ──
    "matrix":   {"header": curses.COLOR_GREEN,   "cat": curses.COLOR_GREEN,   "item": curses.COLOR_GREEN,   "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_GREEN,   "border": curses.COLOR_GREEN,   "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_GREEN,   "status": curses.COLOR_GREEN},
    "ember":    {"header": curses.COLOR_RED,     "cat": curses.COLOR_RED,     "item": curses.COLOR_RED,     "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_RED,     "border": curses.COLOR_RED,     "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_RED,     "status": curses.COLOR_RED},
    "phantom":  {"header": curses.COLOR_MAGENTA, "cat": curses.COLOR_MAGENTA, "item": curses.COLOR_MAGENTA, "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_MAGENTA, "border": curses.COLOR_MAGENTA, "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_MAGENTA, "status": curses.COLOR_MAGENTA},
    "ice":      {"header": curses.COLOR_CYAN,    "cat": curses.COLOR_CYAN,    "item": curses.COLOR_CYAN,    "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_CYAN,    "border": curses.COLOR_CYAN,    "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_CYAN,    "status": curses.COLOR_CYAN},
    "cobalt":   {"header": curses.COLOR_BLUE,    "cat": curses.COLOR_BLUE,    "item": curses.COLOR_BLUE,    "sel_fg": curses.COLOR_WHITE, "sel_bg": curses.COLOR_BLUE,    "border": curses.COLOR_BLUE,    "footer_fg": curses.COLOR_WHITE, "footer_bg": curses.COLOR_BLUE,    "status": curses.COLOR_BLUE},
    "gold":     {"header": curses.COLOR_YELLOW,  "cat": curses.COLOR_YELLOW,  "item": curses.COLOR_YELLOW,  "sel_fg": curses.COLOR_BLACK, "sel_bg": curses.COLOR_YELLOW,  "border": curses.COLOR_YELLOW,  "footer_fg": curses.COLOR_BLACK, "footer_bg": curses.COLOR_YELLOW,  "status": curses.COLOR_YELLOW},
}

# Folder structure for theme picker
THEME_FOLDERS = [
    ("CLASSIC",  ["cyan", "green", "amber", "red", "magenta", "blue", "white"]),
    ("DUO",      ["synthwave", "solar", "ocean", "forest", "hotline", "frost",
                  "coral", "aurora", "twilight", "citrus", "arctic", "neon", "vapor",
                  "hazard", "sakura", "jungle", "lava", "electric", "midnight", "rust", "toxic"]),
    ("MONO",     ["matrix", "ember", "phantom", "ice", "cobalt", "gold"]),
    ("CUSTOM",   ["custom"]),
]

# Color names for custom theme picker
COLOR_NAMES = ["red", "green", "yellow", "blue", "magenta", "cyan", "white"]
COLOR_MAP = {
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "blue": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
}


def build_custom_theme(primary, secondary):
    """Build a theme dict from primary and secondary color names."""
    p = COLOR_MAP[primary]
    s = COLOR_MAP[secondary]
    dark_sel = primary not in ("blue",)
    return {
        "header": p,
        "cat": s,
        "item": p,
        "sel_fg": curses.COLOR_BLACK if dark_sel else curses.COLOR_WHITE,
        "sel_bg": p,
        "border": s,
        "footer_fg": curses.COLOR_BLACK,
        "footer_bg": p,
        "status": s,
    }


def load_config():
    """Load config from file."""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config_locked(updates):
    """Atomically read-modify-write config with file locking."""
    fd = os.open(CONFIG_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with os.fdopen(os.dup(fd), "r+") as f:
            try:
                content = f.read()
                data = json.loads(content) if content.strip() else {}
            except json.JSONDecodeError:
                data = {}
            data.update(updates)
            f.seek(0)
            f.truncate()
            json.dump(data, f)
    finally:
        os.close(fd)


def save_config(key, value):
    """Save a config key with file locking."""
    _save_config_locked({key: value})


def save_config_multi(updates):
    """Save multiple config keys atomically."""
    _save_config_locked(updates)


def load_theme():
    return load_config().get("theme", "cyan")


def load_view_mode():
    return load_config().get("view_mode", "tiles")


def _resolve_theme(name=None):
    """Resolve a theme name to a theme dict, handling custom themes."""
    if name is None:
        name = load_theme()
    if name == "custom":
        cfg = load_config()
        p = cfg.get("custom_primary", "cyan")
        s = cfg.get("custom_secondary", "magenta")
        return build_custom_theme(p, s)
    return THEMES.get(name, THEMES["cyan"])


def apply_theme(name=None):
    """Apply a color theme by name."""
    t = _resolve_theme(name)
    curses.init_pair(C_HEADER,  t["header"],    -1)
    curses.init_pair(C_CAT,     t["cat"],       -1)
    curses.init_pair(C_ITEM,    t["item"],      -1)
    curses.init_pair(C_SEL,     t["sel_fg"],    t["sel_bg"])
    curses.init_pair(C_DESC,    t["item"],      -1)
    curses.init_pair(C_BORDER,  t["border"],    -1)
    curses.init_pair(C_FOOTER,  t["footer_fg"], t["footer_bg"])
    curses.init_pair(C_STATUS,  t["status"],    -1)
    curses.init_pair(C_DIM,     t["item"],      -1)


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    apply_theme()


# ── Drawing helpers ─────────────────────────────────────────────────────────


def draw_header(scr, w):
    for i, line in enumerate(HEADER):
        x = max(0, (w - len(line)) // 2)
        scr.addnstr(i, x, line, w, curses.color_pair(C_HEADER) | curses.A_BOLD)


def _footer_bar(help_text, w):
    """Build a footer string with version on the left and help centered."""
    ver = f" v{PKG_VERSION}" if PKG_VERSION else ""
    pad = w - len(ver)
    if pad > len(help_text):
        return ver + help_text.center(pad)
    return (ver + help_text)[:w]


def draw_footer(scr, h, w):
    bar = _footer_bar(FOOTER_HELP, w)
    try:
        scr.addnstr(h - 1, 0, bar.ljust(w), w, curses.color_pair(C_FOOTER))
    except curses.error:
        pass


def draw_status_bar(scr, h, w, msg, attr=None):
    if attr is None:
        attr = curses.color_pair(C_STATUS) | curses.A_BOLD
    y = h - 2
    scr.move(y, 0)
    scr.clrtoeol()
    scr.addnstr(y, 1, msg[:w - 2], w - 2, attr)


def draw_category_tabs(scr, y, w, cat_idx):
    x = 2
    for i, cat in enumerate(CATEGORIES):
        label = f" {cat['name']} "
        if i == cat_idx:
            attr = curses.color_pair(C_SEL) | curses.A_BOLD
        else:
            attr = curses.color_pair(C_CAT)
        if x + len(label) + 2 < w:
            scr.addnstr(y, x, label, w - x, attr)
            x += len(label) + 1


def draw_separator(scr, y, w, char="─"):
    line = char * (w - 4)
    scr.addnstr(y, 2, line, w - 4, curses.color_pair(C_BORDER))


MODE_ICONS = {"panel": "◇", "stream": "▷", "action": "⚡", "fullscreen": "■", "submenu": "▸"}


def draw_menu(scr, y_start, w, items, sel_idx, scroll=0):
    max_visible = curses.LINES - y_start - 3
    for i in range(max_visible):
        idx = scroll + i
        y = y_start + i
        if idx >= len(items):
            scr.move(y, 0)
            scr.clrtoeol()
            continue

        name, _script, desc, mode = items[idx][:4]
        custom_icon = items[idx][4] if len(items[idx]) > 4 else None
        icon = custom_icon or MODE_ICONS.get(mode, " ")

        if idx == sel_idx:
            marker = "▸"
            name_attr = curses.color_pair(C_SEL) | curses.A_BOLD
            desc_attr = curses.color_pair(C_SEL)
        else:
            marker = " "
            name_attr = curses.color_pair(C_ITEM)
            desc_attr = curses.color_pair(C_DIM) | curses.A_DIM

        scr.move(y, 0)
        scr.clrtoeol()

        # marker + icon + name
        label = f"  {marker} {icon} {name}"
        scr.addnstr(y, 0, label, w, name_attr)

        # description
        pad = 32
        if pad + len(desc) + 4 < w:
            scr.addnstr(y, pad, desc, w - pad - 2, desc_attr)


def draw_box(scr, y, x, h, w, title=""):
    """Draw a thin-line box."""
    attr = curses.color_pair(C_BORDER)
    scr.addch(y, x, "┌", attr)
    scr.addch(y, x + w - 1, "┐", attr)
    scr.addch(y + h - 1, x, "└", attr)
    try:
        scr.addch(y + h - 1, x + w - 1, "┘", attr)
    except curses.error:
        pass
    for cx in range(x + 1, x + w - 1):
        scr.addch(y, cx, "─", attr)
        try:
            scr.addch(y + h - 1, cx, "─", attr)
        except curses.error:
            pass
    for cy in range(y + 1, y + h - 1):
        scr.addch(cy, x, "│", attr)
        try:
            scr.addch(cy, x + w - 1, "│", attr)
        except curses.error:
            pass
    if title:
        t = f" {title} "
        scr.addnstr(y, x + 2, t, w - 4, attr | curses.A_BOLD)


# ── Shared: wait for any key or gamepad button ────────────────────────────


def wait_for_input():
    """Block until a keyboard key or gamepad button is pressed."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    js = open_gamepad()
    if js:
        try:
            while js.read(JS_SIZE):
                pass  # drain
        except (OSError, BlockingIOError):
            pass
    try:
        tty.setraw(fd)
        fds = [fd]
        if js:
            fds.append(js.fileno())
        while True:
            ready, _, _ = select.select(fds, [], [], 0.1)
            for r in ready:
                if r == fd:
                    sys.stdin.read(1)
                    return
                elif js and r == js.fileno():
                    data = js.read(JS_SIZE)
                    if data and len(data) >= JS_SIZE:
                        _ts, val, typ, num = struct.unpack(JS_FMT, data)
                        if typ == 1 and val == 1:
                            return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        close_gamepad(js)


# ── Script execution modes ─────────────────────────────────────────────────

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _resolve_cmd(script_name):
    """Resolve 'script.sh arg1 arg2' into (path, [cmd_list]) or (None, None)."""
    parts = script_name.split()
    name = parts[0]
    # Search: SCRIPT_DIR flat, then subdirectories, then /opt/uconsole/scripts/ tree
    search_dirs = [SCRIPT_DIR]
    for base in [SCRIPT_DIR, '/opt/uconsole/scripts']:
        if os.path.isdir(base):
            for sub in ['system', 'power', 'network', 'radio', 'util']:
                d = os.path.join(base, sub)
                if os.path.isdir(d):
                    search_dirs.append(d)
    for d in search_dirs:
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path, ["bash", path] + parts[1:]
    return None, None


def _colorize_line(scr, y, x, line, w, is_border, is_header, is_separator):
    """Render a single output line with contextual color."""
    maxlen = w - x - 1
    if maxlen <= 0:
        return
    text = line[:maxlen]
    try:
        if is_border or is_separator:
            scr.addnstr(y, x, text, maxlen, curses.color_pair(C_BORDER))
        elif is_header:
            scr.addnstr(y, x, text, maxlen,
                         curses.color_pair(C_HEADER) | curses.A_BOLD)
        elif ":" in text and "│" in text:
            # Key: value line — split and color separately
            inner = text.strip("│ ")
            parts = inner.split(":", 1)
            if len(parts) == 2:
                pre = text.index(inner[0]) if inner else 1
                scr.addnstr(y, x, text[:pre], maxlen, curses.color_pair(C_BORDER))
                scr.addnstr(y, x + pre, parts[0] + ":", len(parts[0]) + 1,
                             curses.color_pair(C_CAT))
                val_x = x + pre + len(parts[0]) + 1
                scr.addnstr(y, val_x, parts[1], maxlen - (val_x - x),
                             curses.color_pair(C_ITEM) | curses.A_BOLD)
                # Trailing border
                trail = text.rstrip()
                if trail.endswith("│"):
                    bx = x + len(text.rstrip()) - 1
                    if bx < w - 1:
                        scr.addnstr(y, bx, "│", 1, curses.color_pair(C_BORDER))
            else:
                scr.addnstr(y, x, text, maxlen, curses.color_pair(C_ITEM))
        else:
            scr.addnstr(y, x, text, maxlen, curses.color_pair(C_ITEM))
    except curses.error:
        safe = text.encode("ascii", "replace").decode("ascii")
        try:
            scr.addnstr(y, x, safe, maxlen, curses.color_pair(C_ITEM))
        except curses.error:
            pass


def _run_and_capture(cmd, timeout=30):
    """Run a command, return (output_lines, retcode, max_line_width)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        retcode = result.returncode
    except subprocess.TimeoutExpired:
        output = "(timed out after 30s)"
        retcode = 1
    except Exception as e:
        output = f"(error: {e})"
        retcode = 1

    output = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', output)
    if not output.strip():
        output = "(no output)"
    lines = output.splitlines()
    max_w = max((len(l) for l in lines), default=0)
    return lines, retcode, max_w


def run_panel(scr, script_name, title):
    """Run script, capture output, display in scrollable curses panel."""
    path, cmd = _resolve_cmd(script_name)
    if path is None:
        h, w = scr.getmaxyx()
        draw_status_bar(scr, h, w, f"  ✗ Script not found: {script_name}",
                        curses.color_pair(C_HEADER) | curses.A_BOLD)
        scr.refresh()
        time.sleep(2)
        return

    # Initial run
    h, w = scr.getmaxyx()
    draw_status_bar(scr, h, w, f"  Running {script_name}...",
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    lines, retcode, max_line_w = _run_and_capture(cmd)

    scroll = 0
    js = open_gamepad()

    while True:
        try:
            scr.erase()
            h, w = scr.getmaxyx()

            # Title bar
            status = "✓" if retcode == 0 else "✗"
            title_str = f" {status} {title} "
            scr.addnstr(0, 0, title_str.center(w), w,
                         curses.color_pair(C_HEADER) | curses.A_BOLD)

            # Center output horizontally
            pad_x = max(1, (w - max_line_w) // 2)

            # Output lines
            view_h = h - 3
            for i in range(view_h):
                li = scroll + i
                if li >= len(lines):
                    break
                line = lines[li]
                stripped = line.strip()
                is_border = stripped and all(c in "┌┐└┘─│├┤┬┴┼╔╗╚╝═║╠╣╦╩╬" for c in stripped)
                is_separator = stripped and all(c in "─├┤│ ═╠╣║" for c in stripped)
                is_header = (stripped.startswith("│") and stripped.endswith("│")
                             and ":" not in stripped and len(stripped) > 4
                             and not is_border)
                _colorize_line(scr, i + 1, pad_x, line, w, is_border, is_header, is_separator)

            # Scroll indicator (right side)
            if len(lines) > view_h:
                total = len(lines)
                bar_h = max(1, view_h * view_h // total)
                bar_pos = scroll * (view_h - bar_h) // max(1, total - view_h)
                for i in range(view_h):
                    ch = "█" if bar_pos <= i < bar_pos + bar_h else "░"
                    try:
                        scr.addnstr(i + 1, w - 2, ch, 1, curses.color_pair(C_DIM))
                    except curses.error:
                        pass

            # Footer
            more = ""
            if len(lines) > view_h:
                pct = min(100, (scroll + view_h) * 100 // len(lines))
                more = f" {pct}%"
            bar = _footer_bar(f" ↑↓ Scroll │ X Refresh │ B Back{more} ", w)
            try:
                scr.addnstr(h - 1, 0, bar.ljust(w), w, curses.color_pair(C_FOOTER))
            except curses.error:
                pass

            scr.refresh()
        except curses.error:
            pass

        # Input
        key, gp_action = _tui_input_loop(scr, js)
        # Remap: GP_A scrolls down in panel view
        if gp_action == "enter":
            gp_action = "scroll_down"

        if key == -1 and gp_action is None:
            continue
        elif key == ord("q") or key == ord("Q") or gp_action == "back":
            break
        elif key == ord("r") or key == ord("R") or gp_action == "refresh":
            # Re-run the script
            draw_status_bar(scr, h, w, f"  ⟳ Re-running {script_name}...",
                            curses.color_pair(C_STATUS) | curses.A_BOLD)
            scr.refresh()
            lines, retcode, max_line_w = _run_and_capture(cmd)
            scroll = 0
        elif key == curses.KEY_UP or key == ord("k"):
            scroll = max(0, scroll - 1)
        elif key == curses.KEY_DOWN or key == ord("j") or gp_action == "scroll_down":
            scroll = min(max(0, len(lines) - view_h), scroll + 1)
        elif key == curses.KEY_PPAGE:
            scroll = max(0, scroll - (h - 3))
        elif key == curses.KEY_NPAGE:
            scroll = min(max(0, len(lines) - view_h), scroll + (h - 3))
        elif key in (curses.KEY_ENTER, 10, 13):
            break

    if js:
        close_gamepad(js)


def run_stream(scr, script_name, title):
    """Run long script, stream output live into curses panel."""
    path, cmd = _resolve_cmd(script_name)
    if path is None:
        return

    lines = []
    lines_lock = threading.Lock()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )

    # Read output in a thread so we don't block curses
    def reader(p):
        for line in p.stdout:
            clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line.rstrip())
            with lines_lock:
                lines.append(clean)
        p.wait()

    t = threading.Thread(target=reader, args=(proc,), daemon=True)
    t.start()

    spin_i = 0
    js = open_gamepad()
    scr.timeout(150)

    while True:
        try:
            h, w = scr.getmaxyx()
            scr.erase()

            running = proc.poll() is None
            spin = SPINNER[spin_i % len(SPINNER)] if running else "✓" if proc.returncode == 0 else "✗"
            spin_i += 1

            # Title
            title_str = f" {spin} {title} "
            scr.addnstr(0, 0, title_str.center(w), w,
                         curses.color_pair(C_HEADER) | curses.A_BOLD)

            # Snapshot lines under lock for thread-safe rendering
            with lines_lock:
                snap = list(lines)

            # Output — show last (h-3) lines (auto-scroll)
            view_h = h - 3
            start = max(0, len(snap) - view_h)
            for i in range(min(view_h, len(snap))):
                li = start + i
                if li < len(snap):
                    line = snap[li][:w - 2]
                    try:
                        scr.addnstr(i + 1, 1, line, w - 2,
                                     curses.color_pair(C_ITEM))
                    except curses.error:
                        safe = line.encode("ascii", "replace").decode("ascii")
                        try:
                            scr.addnstr(i + 1, 1, safe, w - 2,
                                         curses.color_pair(C_ITEM))
                        except curses.error:
                            pass

            # Footer
            if running:
                bar = _footer_bar(f" {len(snap)} lines │ running... ", w)
            else:
                bar = _footer_bar(f" Done ({len(snap)} lines) │ X Re-run │ B/q Back ", w)
            try:
                scr.addnstr(h - 1, 0, bar.ljust(w), w, curses.color_pair(C_FOOTER))
            except curses.error:
                pass

            scr.refresh()
        except curses.error:
            pass

        # Input
        key, gp_action = _tui_input_loop(scr, js)

        # Re-run when finished
        if not running and (key == ord("r") or key == ord("R") or gp_action == "refresh"):
            with lines_lock:
                lines.clear()
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            t = threading.Thread(target=reader, args=(proc,), daemon=True)
            t.start()
            spin_i = 0
            continue

        if not running and (key == ord("q") or key == ord("Q") or
                           key in (curses.KEY_ENTER, 10, 13) or
                           gp_action == "back"):
            break

        # Allow quitting while running with B/Y
        if running and (key == ord("q") or key == ord("Q") or gp_action == "back"):
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            break

    t.join(timeout=2)
    if js:
        close_gamepad(js)
    scr.timeout(100)


def run_action(scr, script_name, title):
    """Run a quick command and flash the result in the status bar."""
    path, cmd = _resolve_cmd(script_name)
    if path is None:
        return

    h, w = scr.getmaxyx()
    draw_status_bar(scr, h, w, f"  ⚡ {title}...",
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            msg = f"  ✓ {title} — done"
            attr = curses.color_pair(C_STATUS) | curses.A_BOLD
        else:
            msg = f"  ✗ {title} — failed (exit {result.returncode})"
            attr = curses.color_pair(C_HEADER) | curses.A_BOLD
    except subprocess.TimeoutExpired:
        msg = f"  ✗ {title} — timed out"
        attr = curses.color_pair(C_HEADER) | curses.A_BOLD

    draw_status_bar(scr, h, w, msg, attr)
    scr.refresh()
    time.sleep(1.5)


def run_fullscreen(scr, script_name):
    """Drop to terminal for interactive scripts."""
    path, cmd = _resolve_cmd(script_name)
    if path is None:
        return

    curses.endwin()
    os.system("clear")
    print(f"\033[1;36m{'─' * 60}")
    print(f"  Running: {script_name}")
    print(f"{'─' * 60}\033[0m\n")

    ret = subprocess.run(cmd).returncode

    print(f"\n\033[1;36m{'─' * 60}")
    if ret == 0:
        print(f"  ✓ Finished ({script_name})")
    else:
        print(f"  ✗ Exit code {ret} ({script_name})")
    print(f"{'─' * 60}\033[0m")
    print("\n  Press any key/button to return...")

    wait_for_input()

    scr.refresh()
    curses.doupdate()


# ── Dangerous-command scripts that require confirmation before running ──────
CONFIRM_SCRIPTS = {"power/power.sh reboot", "power/power.sh shutdown"}


def run_confirm(scr, title):
    """Show 'Are you sure?' with a 5s countdown. Returns True to proceed."""
    js = open_gamepad()
    scr.timeout(200)

    for remaining in range(5, 0, -1):
        h, w = scr.getmaxyx()
        scr.erase()

        msg = f"  {title}  "
        scr.addnstr(h // 2 - 2, max(0, (w - len(msg)) // 2), msg, w,
                     curses.color_pair(C_SEL) | curses.A_BOLD)

        warn = f"  Are you sure? Proceeding in {remaining}s...  "
        scr.addnstr(h // 2, max(0, (w - len(warn)) // 2), warn, w,
                     curses.color_pair(C_HEADER) | curses.A_BOLD)

        cancel = "  [B / ESC / q] Cancel  "
        scr.addnstr(h // 2 + 2, max(0, (w - len(cancel)) // 2), cancel, w,
                     curses.color_pair(C_DIM))

        scr.refresh()

        # Poll for cancel input over ~1 second (5 × 200ms)
        for _ in range(5):
            key, gp_action = _tui_input_loop(scr, js)

            if key in (27, ord("q"), ord("Q"), ord("n"), ord("N")) or gp_action == "back":
                if js:
                    close_gamepad(js)
                scr.timeout(100)
                return False

    if js:
        close_gamepad(js)
    scr.timeout(100)
    return True


def _submenu_run_selected(scr, items, sel_idx, js):
    """Run the selected submenu item. Returns ('switch_view', js), (None, js), or ('cancel', js)."""
    if not items:
        return None, js
    h, w = scr.getmaxyx()
    name, script, _desc, mode = items[sel_idx][:4]

    # Confirmation gate for dangerous commands
    if script in CONFIRM_SCRIPTS:
        if not run_confirm(scr, name):
            draw_status_bar(scr, h, w, "  ✗ Cancelled",
                            curses.color_pair(C_STATUS) | curses.A_BOLD)
            scr.refresh()
            time.sleep(1)
            return "cancel", js

    draw_status_bar(scr, h, w, f"  ▶ Running {script}...",
                    curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    curses.napms(300)
    try:
        result = run_script(scr, script, name, mode)
        if result == "switch_view":
            if js:
                close_gamepad(js)
            return "switch_view", None
    except Exception as e:
        draw_status_bar(scr, h, w, f"  ✗ Error: {e}",
                        curses.color_pair(C_HEADER) | curses.A_BOLD)
        scr.refresh()
        time.sleep(3)
    js = _reopen_gamepad(js)
    return None, js


def run_submenu(scr, submenu_key, parent_title):
    """Show a sub-menu in list or tile mode. Returns 'switch_view' or None."""
    items = SUBMENUS.get(submenu_key, [])
    if not items:
        return None

    use_tiles = load_view_mode() == "tiles"

    sel_idx = 0
    menu_scroll = 0
    js = open_gamepad()
    scr.timeout(100)
    cols = 1  # for tile nav; updated each frame in tile mode

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # Title bar
        title_str = f" ◂ {parent_title} "
        scr.addnstr(0, 0, title_str.center(w), w,
                     curses.color_pair(C_HEADER) | curses.A_BOLD)

        if use_tiles:
            # Build tile dicts from items
            tiles = []
            for item in items:
                name, script, desc, mode = item[:4]
                custom_icon = item[4] if len(item) > 4 else None
                tiles.append({
                    "name": name,
                    "desc": desc,
                    "icon": custom_icon or MODE_ICONS.get(mode, ""),
                })
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h, tiles, sel_idx)

            # Breadcrumb
            try:
                sel_name = items[sel_idx][0] if items else ""
                scr.addnstr(h - 2, 1, f"  {parent_title} ▸ {sel_name}",
                             w - 2, curses.color_pair(C_STATUS) | curses.A_BOLD)
            except curses.error:
                pass

            bar = _footer_bar(" ↑↓←→ Navigate │ A Run │ B Back ", w)
        else:
            # List mode
            menu_y = 2
            max_visible = h - menu_y - 3

            if sel_idx < menu_scroll:
                menu_scroll = sel_idx
            elif sel_idx >= menu_scroll + max_visible:
                menu_scroll = sel_idx - max_visible + 1

            draw_menu(scr, menu_y, w, items, sel_idx, menu_scroll)

            # Status hint
            if items:
                _name, script, _desc, mode = items[sel_idx][:4]
                mode_label = {"panel": "view", "stream": "live", "action": "quick", "fullscreen": "terminal"}
                draw_status_bar(scr, h, w, f"  {script}  [{mode_label.get(mode, mode)}]")

            bar = _footer_bar(" ↑↓ Navigate │ Enter Run │ B/ESC Back ", w)

        # Footer
        try:
            scr.addnstr(h - 1, 0, bar.ljust(w), w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass

        scr.refresh()

        key, gp_action = _tui_input_loop(scr, js)

        if key == -1 and gp_action is None:
            continue

        # Back
        if key == 27 or key == ord("q") or key == ord("Q") or gp_action == "back":
            break

        # Navigation — tile mode uses grid (left/right + up/down by columns)
        if use_tiles:
            if key == curses.KEY_RIGHT or key == ord("l"):
                if sel_idx + 1 < len(items):
                    sel_idx += 1
            elif key == curses.KEY_LEFT or key == ord("h"):
                if sel_idx > 0:
                    sel_idx -= 1
            elif key == curses.KEY_DOWN or key == ord("j"):
                if sel_idx + cols < len(items):
                    sel_idx += cols
            elif key == curses.KEY_UP or key == ord("k"):
                if sel_idx - cols >= 0:
                    sel_idx -= cols
            elif key in (curses.KEY_ENTER, 10, 13) or gp_action == "enter":
                result, js = _submenu_run_selected(scr, items, sel_idx, js)
                if result == "switch_view":
                    return "switch_view"
        else:
            if key == curses.KEY_UP or key == ord("k"):
                sel_idx = max(0, sel_idx - 1)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel_idx = min(len(items) - 1, sel_idx + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp_action == "enter":
                result, js = _submenu_run_selected(scr, items, sel_idx, js)
                if result == "switch_view":
                    return "switch_view"

    if js:
        close_gamepad(js)
    return None


_gp_back_cooldown = 0  # monotonic timestamp — ignore "back" until this time

def _gp_set_cooldown(secs=0.5):
    """Suppress gamepad 'back' for a short window after returning from a sub-view."""
    global _gp_back_cooldown
    _gp_back_cooldown = time.monotonic() + secs


def _reopen_gamepad(js):
    """Close old gamepad, open fresh one, flush all input. Returns new js."""
    if js:
        close_gamepad(js)
    js = open_gamepad()
    read_gamepad(js)
    curses.flushinp()
    _gp_set_cooldown()
    return js


def _run_subview(scr, js, fn, *args):
    """Call a sub-view function with full input-flush protection on return.

    Closes the parent's gamepad before entering the sub-view (so the child
    can open its own), then reopens + flushes + cooldowns on return.
    Returns (result, new_js).
    """
    if js:
        close_gamepad(js)
    result = fn(scr, *args)
    js = open_gamepad()
    read_gamepad(js)
    curses.flushinp()
    _gp_set_cooldown()
    return result, js


def _tui_input_loop(scr, js, map_y_quit=False):
    """Shared input reader. Returns (key, gp_action).

    gp_action is one of: "enter", "back", "refresh", "quit", or None.
    map_y_quit=True maps GP_Y to "quit" (for top-level loops);
    otherwise GP_Y maps to "back" (for sub-views).
    """
    try:
        key = get_key(scr)
    except curses.error:
        key = -1
    gp_action = None
    for btn in read_gamepad(js):
        if btn == GP_A:
            gp_action = "enter"
        elif btn == GP_B:
            gp_action = "back"
        elif btn == GP_Y:
            gp_action = "quit" if map_y_quit else "back"
        elif btn == GP_X:
            gp_action = "refresh"
    # Suppress stale back/quit during cooldown (prevents double-exit from sub-views)
    if gp_action in ("back", "quit") and time.monotonic() < _gp_back_cooldown:
        gp_action = None
    # Also suppress keyboard escape during cooldown (AIO B button sends both)
    if key == 27 and time.monotonic() < _gp_back_cooldown:
        key = -1
    return key, gp_action


def run_process_manager(scr):
    """Interactive process viewer with kill support."""
    js = open_gamepad()
    scr.timeout(2000)
    sel = 0
    sort_by = "cpu"  # "cpu" or "mem"

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        title = f" Process Manager (sort: {sort_by}) "
        scr.addnstr(0, 0, title.center(w), w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        # Get processes
        try:
            sf = "--sort=-%cpu" if sort_by == "cpu" else "--sort=-rss"
            out = subprocess.check_output(
                ["ps", "aux", sf], timeout=3
            ).decode()
            lines = out.splitlines()
            header = lines[0] if lines else ""
            procs = lines[1:] if len(lines) > 1 else []
        except Exception:
            procs = []
            header = ""

        # Header
        try:
            scr.addnstr(1, 1, header[:w - 2], w - 2, curses.color_pair(C_CAT) | curses.A_BOLD)
        except curses.error:
            pass

        view_h = h - 4
        sel = min(sel, max(0, len(procs) - 1))

        for i in range(view_h):
            if i >= len(procs):
                break
            attr = curses.color_pair(C_SEL) | curses.A_BOLD if i == sel else curses.color_pair(C_ITEM)
            marker = "▸" if i == sel else " "
            try:
                scr.addnstr(i + 2, 0, f" {marker} {procs[i][:w - 4]}", w, attr)
            except curses.error:
                pass

        bar = _footer_bar(" ↑↓ Select │ A Kill │ X Sort │ B Back ", w)
        try:
            scr.addnstr(h - 1, 0, bar.ljust(w), w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(procs) - 1, sel + 1)
        elif gp == "refresh" or key == ord("x") or key == ord("X"):
            sort_by = "mem" if sort_by == "cpu" else "cpu"
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if procs and sel < len(procs):
                pid = procs[sel].split()[1] if len(procs[sel].split()) > 1 else None
                if pid and pid.isdigit() and 2 <= int(pid) <= 4194304:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        draw_status_bar(scr, h, w, f"  ✓ Sent SIGTERM to PID {pid}")
                    except ProcessLookupError:
                        draw_status_bar(scr, h, w, f"  ✗ Process {pid} not found")
                    except PermissionError:
                        draw_status_bar(scr, h, w, f"  ✗ Permission denied for PID {pid}")
                    scr.refresh()
                    time.sleep(1)

    if js:
        close_gamepad(js)
    scr.timeout(100)


TILE_W_MIN = 22
TILE_H = 5

CAT_ICONS = {
    "SYSTEM": "\u2699",
    "MONITOR": "\u25c9",
    "FILES": "\u25a4",
    "POWER": "\u26a1",
    "NETWORK": "\u25ce",
    "HARDWARE": "\u2301",
    "TOOLS": "\u2605",
    "GAMES": "\u265f",
    "CONFIG": "\u2630",
}

CAT_DESCS = {
    "SYSTEM": "updates, backups, webdash, timers",
    "MONITOR": "real-time CPU, RAM, temp, and logs",
    "FILES": "file browser, audits, disk and storage",
    "POWER": "battery, cell health, charging, PMU",
    "NETWORK": "WiFi, Bluetooth, SSH, diagnostics",
    "HARDWARE": "AIO board, GPS, SDR, LoRa, ESP32",
    "TOOLS": "git, notes, pomodoro, weather, HN",
    "GAMES": "minesweeper, snake, tetris, 2048, ROMs",
    "CONFIG": "theme, view mode, keybinds",
}


def draw_tile(scr, y, x, w, h, label, sublabel, selected, icon="", marquee_offset=0):
    """Draw a single tile with border, icon above label, and marquee description."""
    attr_border = curses.color_pair(C_SEL) | curses.A_BOLD if selected else curses.color_pair(C_BORDER)
    attr_label = curses.color_pair(C_SEL) | curses.A_BOLD if selected else curses.color_pair(C_ITEM) | curses.A_BOLD
    attr_sub = curses.color_pair(C_SEL) if selected else curses.color_pair(C_DIM) | curses.A_DIM

    inner_w = w - 2

    # Top border
    try:
        scr.addnstr(y, x, "┌" + "─" * inner_w + "┐", w, attr_border)
    except curses.error:
        pass

    # Fill rows
    for row in range(1, h - 1):
        try:
            scr.addnstr(y + row, x, "│" + " " * inner_w + "│", w, attr_border)
        except curses.error:
            pass

    # Bottom border
    try:
        scr.addnstr(y + h - 1, x, "└" + "─" * inner_w + "┘", w, attr_border)
    except curses.error:
        pass

    inner_h = h - 2
    has_sub = sublabel and inner_h >= 3
    content_lines = 2 + (1 if has_sub else 0)
    vy = y + 1 + max(0, (inner_h - content_lines) // 2)

    # Icon on its own line above label
    if icon and inner_h >= 3:
        ix = x + max(1, (w - 1) // 2)
        try:
            scr.addnstr(vy, ix, icon, inner_w, attr_label)
        except curses.error:
            pass
        vy += 1
        text = label
    else:
        text = f"{icon} {label}" if icon else label

    tx = x + max(1, (w - len(text)) // 2)
    try:
        scr.addnstr(vy, tx, text[:inner_w], inner_w, attr_label)
    except curses.error:
        pass

    # Description — marquee if selected and overflows
    if has_sub:
        if len(sublabel) > inner_w:
            if selected and marquee_offset > 0:
                padded = sublabel + "   " + sublabel
                visible = padded[marquee_offset:marquee_offset + inner_w]
            else:
                visible = sublabel[:inner_w - 1] + "~"
        else:
            visible = sublabel

        sx = x + max(1, (w - len(visible)) // 2) if len(visible) <= inner_w else x + 1
        try:
            scr.addnstr(vy + 1, sx, visible[:inner_w], inner_w, attr_sub)
        except curses.error:
            pass


def draw_tile_grid(scr, y_start, w, h_avail, tiles, sel_idx, marquee_offset=0):
    """Draw tiles in a grid, sized to fill available space. Returns (cols, rows)."""
    n = len(tiles)
    usable_w = w - 4  # 2px margin each side

    # Determine column count: fit as many as possible at min width, then expand
    cols = max(1, usable_w // (TILE_W_MIN + 1))
    # Don't use more columns than items
    cols = min(cols, n)
    # Expand tile width to fill available space evenly
    tile_w = max(TILE_W_MIN, (usable_w - (cols - 1)) // cols)

    rows = (n + cols - 1) // cols

    # Expand tile height to fill vertical space if few rows
    # figlet small font = 4 lines, + label + desc + borders = needs ~8-9 rows
    tile_h = TILE_H
    if rows > 0:
        avail_per_row = h_avail // rows
        tile_h = max(TILE_H, min(avail_per_row - 1, 10))

    for i, tile in enumerate(tiles):
        row = i // cols
        col = i % cols
        ty = y_start + row * (tile_h + 1)
        # Center the grid horizontally
        grid_w = cols * tile_w + (cols - 1)
        margin_x = max(2, (w - grid_w) // 2)
        tx = margin_x + col * (tile_w + 1)

        if ty + tile_h > y_start + h_avail:
            break

        label = tile.get("name", "")
        sublabel = tile.get("desc", "")
        icon = tile.get("icon", "")
        m_off = marquee_offset if i == sel_idx else 0
        draw_tile(scr, ty, tx, tile_w, tile_h, label, sublabel, i == sel_idx, icon, m_off)

    return cols, rows


def main_tiles(scr):
    """Tile-view main loop: categories → items → run."""
    curses.curs_set(0)
    init_colors()
    scr.timeout(200)  # 200ms for marquee animation

    # State: "categories" or "items"
    level = "categories"
    cat_sel = 0
    item_sel = 0

    # Marquee state
    marquee_offset = 0
    marquee_tick = 0
    last_sel = (-1, "")

    info = get_quick_info()
    last_info_time = time.time()
    info_scroll = 0
    js = open_gamepad()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # Header
        draw_header(scr, w)
        header_end = len(HEADER)

        # Quick-info bar (scrolling marquee)
        info_y = header_end
        info_parts = [f" {k}: {v}" for k, v in info]
        info_line = "│".join(info_parts)
        visible_w = w - 2
        if len(info_line) > visible_w:
            gap = "   ◈   "
            scroll_buf = info_line + gap + info_line
            offset = info_scroll % (len(info_line) + len(gap))
            visible = scroll_buf[offset:offset + visible_w]
            scr.addnstr(info_y, 1, visible, visible_w, curses.color_pair(C_STATUS))
            info_scroll += 1
        else:
            scr.addnstr(info_y, 1, info_line[:visible_w], visible_w, curses.color_pair(C_STATUS))

        draw_separator(scr, info_y + 1, w)

        content_y = info_y + 2
        content_h = h - content_y - 3

        if level == "categories":
            # Build category tiles
            tiles = []
            for cat in CATEGORIES:
                name = cat["name"]
                tiles.append({
                    "name": name,
                    "desc": CAT_DESCS.get(name, f"{len(cat['items'])} items"),
                    "icon": CAT_ICONS.get(name, ""),
                })

            cur_sel = (cat_sel, level)
            if cur_sel != last_sel:
                marquee_offset = 0
                marquee_tick = 0
                last_sel = cur_sel

            cols, rows = draw_tile_grid(scr, content_y, w, content_h, tiles, cat_sel, marquee_offset)

            # Breadcrumb
            try:
                scr.addnstr(h - 2, 1, "  Categories",
                             w - 2, curses.color_pair(C_STATUS) | curses.A_BOLD)
            except curses.error:
                pass

            # Footer
            bar = _footer_bar(" ↑↓←→ Navigate │ A Select │ X Refresh │ Y Quit ", w)

        else:
            # Show items for selected category
            cat = CATEGORIES[cat_sel]
            tiles = []
            for item in cat["items"]:
                name, script, desc, mode = item[:4]
                custom_icon = item[4] if len(item) > 4 else None
                tiles.append({
                    "name": name,
                    "desc": desc,
                    "icon": custom_icon or MODE_ICONS.get(mode, ""),
                })

            cur_sel = (item_sel, level)
            if cur_sel != last_sel:
                marquee_offset = 0
                marquee_tick = 0
                last_sel = cur_sel

            cols, rows = draw_tile_grid(scr, content_y, w, content_h, tiles, item_sel, marquee_offset)

            # Breadcrumb
            try:
                scr.addnstr(h - 2, 1, f"  {cat['name']} ▸ {tiles[item_sel]['name']}" if tiles else f"  {cat['name']}",
                             w - 2, curses.color_pair(C_STATUS) | curses.A_BOLD)
            except curses.error:
                pass

            # Footer
            bar = _footer_bar(" ↑↓←→ Navigate │ A Run │ B Back │ X Refresh │ Y Quit ", w)

        try:
            scr.addnstr(h - 1, 0, bar.ljust(w), w, curses.color_pair(C_FOOTER))
        except curses.error:
            pass

        scr.refresh()

        # Advance marquee for selected tile if desc overflows
        sel_desc = ""
        if level == "categories" and tiles:
            sel_desc = tiles[cat_sel].get("desc", "")
        elif level == "items" and tiles:
            sel_desc = tiles[item_sel].get("desc", "")

        usable_w = w - 4
        tile_cols = max(1, usable_w // (TILE_W_MIN + 1))
        tile_cols = min(tile_cols, len(tiles) if tiles else 1)
        tile_w = max(TILE_W_MIN, (usable_w - (tile_cols - 1)) // tile_cols)
        inner_w = tile_w - 2

        if sel_desc and len(sel_desc) > inner_w:
            marquee_tick += 1
            if marquee_tick > 3:
                marquee_offset = (marquee_tick - 3) % (len(sel_desc) + 3)
        else:
            marquee_offset = 0

        # Refresh info
        if time.time() - last_info_time > 30:
            info = get_quick_info()
            last_info_time = time.time()

        # Input
        key, gp_action = _tui_input_loop(scr, js, map_y_quit=True)

        if key == -1 and gp_action is None:
            continue

        # Navigation
        sel = cat_sel if level == "categories" else item_sel
        count = len(CATEGORIES) if level == "categories" else len(CATEGORIES[cat_sel]["items"])

        if key == ord("q") or key == ord("Q") or gp_action == "quit":
            break
        elif key == curses.KEY_RIGHT or key == ord("l"):
            if sel + 1 < count:
                sel += 1
        elif key == curses.KEY_LEFT or key == ord("h"):
            if sel > 0:
                sel -= 1
        elif key == curses.KEY_DOWN or key == ord("j"):
            if sel + cols < count:
                sel += cols
        elif key == curses.KEY_UP or key == ord("k"):
            if sel - cols >= 0:
                sel -= cols
        elif key == ord("r") or key == ord("R") or gp_action == "refresh":
            info = get_quick_info()
            last_info_time = time.time()
        elif gp_action == "back":
            if level == "items":
                level = "categories"
                item_sel = 0
            # At categories level, B does nothing (or quit)
        elif key in (curses.KEY_ENTER, 10, 13) or gp_action == "enter":
            if level == "categories":
                cat_sel = sel
                level = "items"
                item_sel = 0
                sel = 0
            else:
                # Run the selected item
                items = CATEGORIES[cat_sel]["items"]
                if items:
                    name, script, _desc, mode = items[sel][:4]
                    draw_status_bar(scr, h, w, f"  ▶ Running {script}...",
                                    curses.color_pair(C_STATUS) | curses.A_BOLD)
                    scr.refresh()
                    curses.napms(300)
                    try:
                        result = run_script(scr, script, name, mode)
                        if result == "switch_view":
                            if js:
                                close_gamepad(js)
                            return "switch_view"
                    except Exception as e:
                        draw_status_bar(scr, h, w, f"  ✗ Error: {e}",
                                        curses.color_pair(C_HEADER) | curses.A_BOLD)
                        scr.refresh()
                        time.sleep(3)
                    js = _reopen_gamepad(js)
                    info = get_quick_info()
                    last_info_time = time.time()
        elif key == 27:  # ESC
            if level == "items":
                level = "categories"
                item_sel = 0

        # Write back
        if level == "categories":
            cat_sel = sel
        else:
            item_sel = sel

    close_gamepad(js)
    return None


# ── ESP32 dynamic submenu items ──────────────────────────────────────────

_ESP32_MICROPYTHON_ITEMS = [
    ("Status",           "radio/esp32.sh status",     "latest sensor reading",                  "panel",      "📡"),
    ("Live Monitor",     "_esp32_monitor",            "real-time sensor dashboard",             "action",     "📊"),
    ("Serial Monitor",   "radio/esp32.sh serial",     "raw serial output",                      "fullscreen", "⌨"),
    ("REPL",             "radio/esp32.sh repl",       "MicroPython interactive shell",          "fullscreen", "⟩⟩"),
    ("Flash Scripts",    "radio/esp32.sh flash",      "upload boot.py + main.py",               "stream",     "⇪"),
    ("Reset",            "radio/esp32.sh reset",      "hard-reset ESP32",                       "action",     "⟳"),
    ("Log Entry",        "radio/esp32.sh log",        "append reading to esp32.log",            "action",     "✎"),
    ("Chip Info",        "radio/esp32.sh info",       "chip type, features, MAC",               "panel",      "ℹ"),
]

_ESP32_MARAUDER_ITEMS = [
    ("Marauder",         "_marauder",                      "WiFi/BLE attack toolkit",                "action",     "☠"),
    ("Serial Monitor",   "radio/esp32-marauder.sh serial", "raw Marauder output",                    "fullscreen", "⌨"),
    ("Scan APs",         "radio/esp32-marauder.sh scan ap", "scan nearby access points",             "stream",     "◎"),
    ("Device Info",      "radio/esp32-marauder.sh info",    "firmware, MAC, hardware",               "panel",      "ℹ"),
    ("Settings",         "radio/esp32-marauder.sh settings","Marauder settings",                     "panel",      "⚙"),
    ("Reboot",           "radio/esp32-marauder.sh reboot",  "reboot ESP32",                          "action",     "⟳"),
]

_ESP32_COMMON_ITEMS = [
    ("USB Reset",        "_esp32_usb_reset",          "power cycle ESP32 via USB reset",        "action",     "⚡"),
    ("Switch Firmware",  "_esp32_flash",              "flash MicroPython or Marauder",          "action",     "⇄"),
    ("Re-detect",        "_esp32_redetect",           "re-probe firmware handshake",            "action",     "⟲"),
]


def _esp32_menu_for(firmware):
    """Return submenu items for the detected firmware mode."""
    from tui.esp32_detect import Firmware
    if firmware == Firmware.MICROPYTHON:
        items = list(_ESP32_MICROPYTHON_ITEMS)
    elif firmware == Firmware.MARAUDER:
        items = list(_ESP32_MARAUDER_ITEMS)
    else:
        items = [
            ("Manual: MicroPython", "_esp32_force_mp",  "assume MicroPython firmware",  "action", "🐍"),
            ("Manual: Marauder",    "_esp32_force_mrd", "assume Marauder firmware",     "action", "☠"),
        ]
    items.extend(_ESP32_COMMON_ITEMS)
    return items


def run_esp32_hub(scr):
    """ESP32 hub — detect firmware, show appropriate submenu."""
    from tui.esp32_detect import Firmware, detect, invalidate_cache

    # Release Marauder serial connection if held (so detect() can open the port)
    try:
        from tui.marauder import _inst as _mrd_inst
        if _mrd_inst and getattr(_mrd_inst, 'port', None):
            _mrd_inst.close()
    except Exception:
        pass

    h, w = scr.getmaxyx()
    scr.erase()

    # Detection splash
    msg = " Detecting ESP32 firmware... "
    scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
    scr.refresh()

    firmware = detect()

    # Build dynamic submenu
    SUBMENUS["sub:esp32"] = _esp32_menu_for(firmware)

    # Show mode badge in title
    badge = {
        Firmware.MICROPYTHON: "MicroPython",
        Firmware.MARAUDER: "Marauder",
        Firmware.UNKNOWN: "Unknown",
    }.get(firmware, "Unknown")

    run_submenu(scr, "sub:esp32", f"ESP32 [{badge}]")


def run_esp32_flash_picker(scr):
    """Switch firmware — pick target and flash with safety gates."""
    from tui.esp32_detect import Firmware, detect, invalidate_cache
    from tui.esp32_flash import FlashError, flash

    current = detect()

    # Determine target (opposite of current)
    if current == Firmware.MICROPYTHON:
        target = Firmware.MARAUDER
        target_name = "Marauder"
    elif current == Firmware.MARAUDER:
        target = Firmware.MICROPYTHON
        target_name = "MicroPython"
    else:
        # Unknown — ask user to pick
        target = Firmware.MARAUDER
        target_name = "Marauder"

    h, w = scr.getmaxyx()
    scr.erase()

    # Confirmation
    msg = f" Flash {target_name}? (Y/N) "
    scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
    scr.refresh()
    scr.timeout(-1)
    key = scr.getch()
    scr.timeout(100)
    if key not in (ord("y"), ord("Y")):
        return

    # Flash with progress
    scr.erase()
    lines = []

    def on_output(line):
        lines.append(line)
        y = min(len(lines), h - 2)
        try:
            scr.addnstr(y, 1, line[:w - 2], w - 2, curses.color_pair(C_DIM))
            scr.refresh()
        except curses.error:
            pass

    try:
        scr.addnstr(0, 0, f" Flashing {target_name}... ".center(w), w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        scr.refresh()
        flash(target, on_output=on_output)
        msg = f" Flash complete — {target_name} installed. Press any key. "
    except FlashError as e:
        msg = f" Flash failed: {e} "

    scr.addnstr(h - 1, 0, msg[:w], w,
                curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    scr.timeout(-1)
    scr.getch()
    scr.timeout(100)

    # Invalidate cache so hub re-detects on return
    invalidate_cache()


def run_esp32_force(scr, firmware):
    """Force-set detection to a specific firmware and re-enter hub."""
    from tui.esp32_detect import Firmware, invalidate_cache, _cache
    import time as _time
    # Manually populate cache with forced value
    _cache["firmware"] = firmware
    _cache["port"] = "/dev/esp32"
    _cache["timestamp"] = _time.time()
    run_esp32_hub(scr)


def _esp32_usb_reset(scr):
    """USB-reset the ESP32 to recover from a hung state."""
    from tui.esp32_detect import invalidate_cache
    import subprocess

    h, w = scr.getmaxyx()
    scr.erase()
    msg = " Resetting ESP32 via USB... "
    scr.addnstr(h // 2, max(0, (w - len(msg)) // 2), msg, w,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
    scr.refresh()

    # Close Marauder connection if held
    try:
        from tui.marauder import _inst as _mrd_inst
        if _mrd_inst and getattr(_mrd_inst, 'port', None):
            _mrd_inst.close()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["usbreset", "CP2102 USB to UART Bridge Controller"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import time
            time.sleep(2)  # wait for device to re-enumerate
            invalidate_cache()
            msg = " ESP32 reset OK "
        else:
            msg = f" Reset failed: {result.stderr.strip()[:40]} "
    except FileNotFoundError:
        msg = " usbreset not installed "
    except subprocess.TimeoutExpired:
        msg = " Reset timed out "

    scr.addnstr(h // 2 + 1, max(0, (w - len(msg)) // 2), msg, w,
                curses.color_pair(C_STATUS) | curses.A_BOLD)
    scr.refresh()
    scr.timeout(-1)
    scr.getch()
    scr.timeout(100)


def _esp32_redetect(scr):
    """Invalidate cache and re-enter ESP32 hub."""
    from tui.esp32_detect import invalidate_cache
    invalidate_cache()
    run_esp32_hub(scr)


def _Firmware_MP():
    from tui.esp32_detect import Firmware
    return Firmware.MICROPYTHON


def _Firmware_MRD():
    from tui.esp32_detect import Firmware
    return Firmware.MARAUDER


def _get_native_tools():
    """Lazy-load native tools from submodules to avoid circular imports."""
    from tui.config_ui import run_theme_picker, run_viewmode_toggle, run_bat_gauge_toggle, run_trackball_scroll_toggle
    from tui.tools import (run_keybinds, run_git_panel, run_notes, run_calculator,
                           run_stopwatch, run_screenshot, run_syslog_viewer, run_ssh_bookmarks,
                           run_pomodoro, run_weather, run_hackernews, run_forum, run_mdviewer)
    from tui.games import (run_minesweeper, run_snake, run_tetris, run_2048, run_romlauncher)
    from tui.monitor import run_live_monitor, run_esp32_monitor
    from tui.files import run_file_browser
    from tui.network import (run_wifi_switcher, run_hotspot_toggle, run_hotspot_config,
                             run_wifi_fallback, run_bluetooth)
    from tui.services import run_cron_viewer, run_webdash_config, run_push_interval
    from tui.radio import run_gps_globe, run_fm_radio
    from tui.marauder import run_marauder
    return {
        "_theme":       lambda scr: run_theme_picker(scr),
        "_viewmode":    lambda scr: run_viewmode_toggle(scr),
        "_bat_gauge":   lambda scr: run_bat_gauge_toggle(scr),
        "_keybinds":    lambda scr: run_keybinds(scr),
        "_trackball_scroll": lambda scr: run_trackball_scroll_toggle(scr),
        "_monitor":     lambda scr: run_live_monitor(scr),
        "_processes":   lambda scr: run_process_manager(scr),
        "_syslog":      lambda scr: run_syslog_viewer(scr),
        "_filebrowser": lambda scr: run_file_browser(scr),
        "_wifi":        lambda scr: run_wifi_switcher(scr),
        "_hotspot_toggle": lambda scr: run_hotspot_toggle(scr),
        "_hotspot_config": lambda scr: run_hotspot_config(scr),
        "_webdash_config": lambda scr: run_webdash_config(scr),
        "_push_interval": lambda scr: run_push_interval(scr),
        "_wifi_fallback": lambda scr: run_wifi_fallback(scr),
        "_bluetooth":   lambda scr: run_bluetooth(scr),
        "_ssh":         lambda scr: run_ssh_bookmarks(scr),
        "_git":         lambda scr: run_git_panel(scr),
        "_notes":       lambda scr: run_notes(scr),
        "_calc":        lambda scr: run_calculator(scr),
        "_stopwatch":   lambda scr: run_stopwatch(scr),
        "_pomodoro":    lambda scr: run_pomodoro(scr),
        "_weather":     lambda scr: run_weather(scr),
        "_hackernews":  lambda scr: run_hackernews(scr),
        "_forum":       lambda scr: run_forum(scr),
        "_mdviewer":    lambda scr: run_mdviewer(scr),
        "_cron":        lambda scr: run_cron_viewer(scr),
        "_screenshot":  lambda scr: run_screenshot(scr),
        "_minesweeper": lambda scr: run_minesweeper(scr),
        "_snake":       lambda scr: run_snake(scr),
        "_tetris":      lambda scr: run_tetris(scr),
        "_2048":        lambda scr: run_2048(scr),
        "_romlauncher": lambda scr: run_romlauncher(scr),
        "_esp32_monitor": lambda scr: run_esp32_monitor(scr),
        "_esp32_hub":     lambda scr: run_esp32_hub(scr),
        "_esp32_flash":   lambda scr: run_esp32_flash_picker(scr),
        "_esp32_usb_reset": lambda scr: _esp32_usb_reset(scr),
        "_esp32_redetect": lambda scr: _esp32_redetect(scr),
        "_esp32_force_mp":  lambda scr: run_esp32_force(scr, _Firmware_MP()),
        "_esp32_force_mrd": lambda scr: run_esp32_force(scr, _Firmware_MRD()),
        "_marauder":      lambda scr: run_marauder(scr),
        "_gps_globe":     lambda scr: run_gps_globe(scr),
        "_fm_radio":      lambda scr: run_fm_radio(scr),
    }

NATIVE_TOOLS = None


def run_script(scr, script_name, title, mode):
    """Dispatch to the appropriate runner based on mode. Returns 'switch_view' or None."""
    global NATIVE_TOOLS
    if NATIVE_TOOLS is None:
        NATIVE_TOOLS = _get_native_tools()
    if mode == "submenu":
        return run_submenu(scr, script_name, title)
    if script_name in NATIVE_TOOLS:
        result = NATIVE_TOOLS[script_name](scr)
        if script_name == "_viewmode":
            return "switch_view"
        return None
    # Confirmation gate for dangerous commands at top level
    if script_name in CONFIRM_SCRIPTS:
        if not run_confirm(scr, title):
            return None
    if mode == "panel":
        run_panel(scr, script_name, title)
    elif mode == "stream":
        run_stream(scr, script_name, title)
    elif mode == "action":
        run_action(scr, script_name, title)
    else:
        run_fullscreen(scr, script_name)
    return None


# ── Quick info panel ────────────────────────────────────────────────────────


def get_quick_info():
    """Gather a few system stats for the sidebar."""
    lines = []
    # Uptime — read /proc directly
    try:
        up_s = float(open("/proc/uptime").read().split()[0])
        up_h = int(up_s // 3600)
        up_m = int((up_s % 3600) // 60)
        lines.append(("UP", f"{up_h}h {up_m:02d}m" if up_h > 0 else f"{up_m}m"))
    except Exception:
        pass
    # Load
    try:
        load = open("/proc/loadavg").read().split()[:3]
        lines.append(("LOAD", " ".join(load)))
    except Exception:
        pass
    # Memory — read /proc/meminfo directly
    try:
        mi = {}
        for ln in open("/proc/meminfo"):
            p = ln.split()
            if len(p) >= 2:
                mi[p[0].rstrip(":")] = int(p[1])
        total_kb = mi.get("MemTotal", 1)
        avail_kb = mi.get("MemAvailable", 0)
        used_kb = total_kb - avail_kb
        def _fmt_kb(kb):
            return f"{kb / 1048576:.1f}G" if kb >= 1048576 else f"{kb // 1024}M"
        lines.append(("MEM", f"{_fmt_kb(used_kb)}/{_fmt_kb(total_kb)}"))
    except Exception:
        pass
    # Disk — use os.statvfs directly
    try:
        s = os.statvfs("/")
        dt = s.f_blocks * s.f_frsize
        du = dt - s.f_bfree * s.f_frsize
        pct = du * 100 // max(1, dt)
        def _fmt_bytes(b):
            return f"{b / (1024**3):.1f}G" if b >= 1024**3 else f"{b // (1024**2)}M"
        lines.append(("DISK", f"{_fmt_bytes(du)}/{_fmt_bytes(dt)} ({pct}%)"))
    except Exception:
        pass
    # IP
    try:
        ip = subprocess.check_output(["hostname", "-I"], timeout=2).decode().split()[0]
        lines.append(("IP", ip or "—"))
    except Exception:
        pass
    # Battery
    try:
        bat_cap = open("/sys/class/power_supply/axp20x-battery/capacity").read().strip()
        bat_v = int(open("/sys/class/power_supply/axp20x-battery/voltage_now").read()) / 1e6
        bat_status = open("/sys/class/power_supply/axp20x-battery/status").read().strip()
        bat_icon = "⚡" if bat_status == "Charging" else ""
        lines.append(("BAT", f"{bat_icon}{bat_cap}% {bat_v:.3f}V"))
    except Exception:
        pass
    # WiFi
    try:
        ssid = subprocess.check_output(["iwgetid", "-r"], stderr=subprocess.DEVNULL, timeout=1).decode().strip()
        if ssid:
            try:
                iwout = subprocess.check_output(["iwconfig", "wlan0"], stderr=subprocess.DEVNULL, timeout=1).decode()
                m = re.search(r'Signal level=(\S+)', iwout)
                sig = m.group(1) if m else ""
            except Exception:
                sig = ""
            lines.append(("WIFI", f"{ssid} {sig}dBm" if sig else ssid))
    except Exception:
        pass
    # ESP32
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:8080/api/esp32", timeout=1)
        esp = json.loads(resp.read())
        if esp.get("online"):
            lines.append(("ESP32", f"{esp.get('temp_c', 0):.0f}°C"))
        elif os.path.exists(os.environ.get("ESP32_PORT", "/dev/ttyUSB0")):
            lines.append(("ESP32", "Marauder" if os.path.isdir(os.path.expanduser("~/marauder")) else "USB"))
    except Exception:
        pass
    return lines


# ── Main loop ───────────────────────────────────────────────────────────────


def main(scr):
    curses.curs_set(0)
    init_colors()
    scr.timeout(100)  # 100ms for responsive input

    cat_idx = 0
    sel_idx = 0
    menu_scroll = 0

    # Pre-fetch info
    info = get_quick_info()
    last_info_time = time.time()
    info_scroll = 0

    # Gamepad
    js = open_gamepad()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # Header
        draw_header(scr, w)
        header_end = len(HEADER)

        # Quick-info bar (scrolling marquee)
        info_y = header_end
        info_parts = [f" {k}: {v}" for k, v in info]
        info_line = "│".join(info_parts)
        visible_w = w - 2
        if len(info_line) > visible_w:
            gap = "   ◈   "
            scroll_buf = info_line + gap + info_line
            offset = info_scroll % (len(info_line) + len(gap))
            visible = scroll_buf[offset:offset + visible_w]
            scr.addnstr(info_y, 1, visible, visible_w, curses.color_pair(C_STATUS))
            info_scroll += 1
        else:
            scr.addnstr(info_y, 1, info_line[:visible_w], visible_w, curses.color_pair(C_STATUS))

        # Separator
        draw_separator(scr, info_y + 1, w)

        # Category tabs
        tab_y = info_y + 2
        draw_category_tabs(scr, tab_y, w, cat_idx)

        # Separator
        draw_separator(scr, tab_y + 1, w, "━")

        # Menu items with scrolling
        items = CATEGORIES[cat_idx]["items"]
        menu_y = tab_y + 2
        max_visible = h - menu_y - 3

        # Keep selection visible
        if sel_idx < menu_scroll:
            menu_scroll = sel_idx
        elif sel_idx >= menu_scroll + max_visible:
            menu_scroll = sel_idx - max_visible + 1

        draw_menu(scr, menu_y, w, items, sel_idx, menu_scroll)

        # Scroll arrows if needed
        if menu_scroll > 0:
            try:
                scr.addnstr(menu_y, w - 3, "▲", 1, curses.color_pair(C_DIM))
            except curses.error:
                pass
        if menu_scroll + max_visible < len(items):
            try:
                scr.addnstr(menu_y + max_visible - 1, w - 3, "▼", 1, curses.color_pair(C_DIM))
            except curses.error:
                pass

        # Footer
        draw_footer(scr, h, w)

        # Status: selected item hint
        if items:
            _name, script, _desc, mode = items[sel_idx][:4]
            mode_label = {"panel": "view", "stream": "live", "action": "quick", "fullscreen": "terminal"}
            draw_status_bar(scr, h, w, f"  {script}  [{mode_label.get(mode, mode)}]")

        scr.refresh()

        # Refresh system info every 30s
        if time.time() - last_info_time > 30:
            info = get_quick_info()
            last_info_time = time.time()

        # Input
        key, gp_action = _tui_input_loop(scr, js, map_y_quit=True)

        if key == -1 and gp_action is None:
            continue

        # Quit
        if key == ord("q") or key == ord("Q") or gp_action == "quit":
            break
        # Navigate up
        elif key == curses.KEY_UP or key == ord("k"):
            sel_idx = max(0, sel_idx - 1)
        # Navigate down
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel_idx = min(len(items) - 1, sel_idx + 1)
        # Previous category
        elif key == curses.KEY_LEFT or key == ord("h") or gp_action == "back":
            cat_idx = (cat_idx - 1) % len(CATEGORIES)
            sel_idx = 0
            menu_scroll = 0
        # Next category
        elif key == curses.KEY_RIGHT or key == ord("l"):
            cat_idx = (cat_idx + 1) % len(CATEGORIES)
            sel_idx = 0
            menu_scroll = 0
        # Run script
        elif key in (curses.KEY_ENTER, 10, 13) or gp_action == "enter":
            if items:
                name, script, _desc, mode = items[sel_idx][:4]
                draw_status_bar(scr, h, w, f"  ▶ Running {script}...",
                                curses.color_pair(C_STATUS) | curses.A_BOLD)
                scr.refresh()
                curses.napms(300)
                try:
                    result = run_script(scr, script, name, mode)
                    if result == "switch_view":
                        if js:
                            close_gamepad(js)
                        return "switch_view"
                except Exception as e:
                    draw_status_bar(scr, h, w, f"  ✗ Error: {e}",
                                    curses.color_pair(C_HEADER) | curses.A_BOLD)
                    scr.refresh()
                    time.sleep(3)
                # Re-open gamepad (fd may be stale after curses endwin/reinit)
                js = _reopen_gamepad(js)
                # Refresh info after running a script
                info = get_quick_info()
                last_info_time = time.time()
        # Refresh
        elif key == ord("r") or key == ord("R") or gp_action == "refresh":
            draw_status_bar(scr, h, w, "  ⟳ Refreshing...",
                            curses.color_pair(C_STATUS) | curses.A_BOLD)
            scr.refresh()
            info = get_quick_info()
            last_info_time = time.time()

    close_gamepad(js)
    return None


def entry(scr):
    """Entry point that switches between list and tile views."""
    _init_workspace()
    # Migrate old config
    old_config = os.path.join(SCRIPT_DIR, ".console-theme.json")
    if os.path.isfile(old_config) and not os.path.isfile(CONFIG_FILE):
        os.rename(old_config, CONFIG_FILE)

    while True:
        mode = load_view_mode()
        if mode == "tiles":
            result = main_tiles(scr)
        else:
            result = main(scr)
        if result != "switch_view":
            break


