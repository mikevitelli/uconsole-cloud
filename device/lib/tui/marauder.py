"""TUI module: Marauder ESP32 WiFi/BLE attack toolkit.

Controls an ESP32 running Marauder firmware over serial (/dev/esp32).
Scan -> Select -> Attack workflow with live braille RSSI waveforms.
"""

import collections
import curses
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone

from tui.framework import (
    C_BORDER,
    C_CAT,
    C_DIM,
    C_FOOTER,
    C_HEADER,
    C_ITEM,
    C_SEL,
    C_STATUS,
    _gp_set_cooldown,
    _tui_input_loop,
    close_gamepad,
    draw_tile_grid,
    open_gamepad,
    read_gamepad,
)
import tui_lib as tui

# Gauge colors from tui_lib (initialized by tui.init_gauge_colors())
C_OK = tui.C_OK
C_WARN = tui.C_WARN
C_CRIT = tui.C_CRIT

# ── Serial output parsers ────────────────────────────────────────────

_RE_AP = re.compile(
    r'^(-?\d+)\s+Ch:\s+(\d+)\s+([0-9A-Fa-f:]{17})\s+ESSID:\s+(.*?)\s*$')
_RE_LIST_AP = re.compile(
    r'^\[(\d+)\]\[CH:(\d+)\]\s+(.*?)\s+(-?\d+)(\s+\(selected\))?\s*$')
_RE_DEAUTH = re.compile(
    r'^(-?\d+)\s+Ch:\s+(\d+)\s+([0-9A-Fa-f:]{17})\s+->\s+([0-9A-Fa-f:]{17})')
_RE_PROBE = re.compile(
    r'^(-?\d+)\s+Ch:\s+(\d+)\s+Client:\s+([0-9A-Fa-f:]{17})\s+Requesting:\s+(.*)')
_RE_EAPOL = re.compile(r'^Received EAPOL:\s+([0-9A-Fa-f:]{17})')
_RE_CRED = re.compile(r'^u:\s+(.*?)\s+p:\s+(.*)')

# BLE serial output parsers
_RE_BLE = re.compile(
    r'(-?\d+)\s+BLE:\s+([0-9A-Fa-f:]{17})\s*(?:Name:\s*(.*))?')
_RE_BLE_TYPE = re.compile(
    r'Type:\s+(\w+)\s+RSSI:\s+(-?\d+)\s+MAC:\s+([0-9A-Fa-f:]{17})'
    r'(?:\s+Name:\s*(.*))?')
_RE_SKIM = re.compile(
    r'(?:Potential\s+)?[Ss]kimmer.*?RSSI:\s+(-?\d+)\s+MAC:\s+([0-9A-Fa-f:]{17})')

_IDLE, _SCANNING, _ATTACKING = 0, 1, 2

# Module-level selected AP targets — avoids reliance on Marauder's
# flaky select -a command.  Updated by _wifi_scan's stop/attack flow.
_selected_targets = []


# ── Serial Connection ────────────────────────────────────────────────

class _Conn:
    """Thread-safe serial wrapper for ESP32 Marauder."""

    PORTS = ["/dev/esp32", "/dev/ttyUSB0"]
    BAUD = 115200

    def __init__(self):
        self.port = None
        self.lines = []
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self.state = _IDLE
        self.dev_path = ""
        self.ok = False

    def connect(self):
        """Open the serial port and wait for Marauder to be responsive.

        Uses esp32_detect.open_ready so we don't fight the open-time
        chip reset on ESP32-S3 USB-Serial/JTAG (S3 silicon has no
        firmware-side disable for host-driven reset).
        """
        from tui import esp32_detect
        for dev in self.PORTS:
            ser, fw = esp32_detect.open_ready(
                port=dev, ready_timeout=4.0, open_timeout=0.1,
            )
            if ser is None:
                continue
            self.port = ser
            self.dev_path = dev
            self._stop.clear()
            self._ready.clear()
            self._thread = threading.Thread(target=self._reader, daemon=True)
            self._thread.start()
            self._ready.wait(timeout=1)  # block until reader is running
            self.ok = True
            # Reset Marauder state: stop any pending scan, drain
            try:
                self.port.write(b"stopscan\r\n")
                time.sleep(0.5)
                self.port.reset_input_buffer()
            except Exception:
                pass
            self.clear()
            return True
        return False

    def close(self):
        if self.state != _IDLE:
            self.send("stopscan")
            time.sleep(0.2)
            self.state = _IDLE
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self.port:
            from tui import esp32_detect
            esp32_detect._close_fast(self.port)
        self.port = None
        self.ok = False

    def send(self, cmd):
        if self.port and self.port.is_open:
            try:
                self.port.write(f"{cmd}\n".encode())
            except Exception:
                self.ok = False

    def clear(self):
        with self.lock:
            self.lines.clear()

    def snap(self):
        with self.lock:
            return list(self.lines)

    def drain(self):
        with self.lock:
            s = list(self.lines)
            self.lines.clear()
            return s

    def stop_scan(self):
        self.send("stopscan")
        self.state = _IDLE

    def _reader(self):
        buf = b""
        self._ready.set()
        while not self._stop.is_set():
            try:
                if self.port and self.port.is_open and self.port.in_waiting:
                    buf += self.port.read(self.port.in_waiting)
                    while b'\r\n' in buf:
                        raw, buf = buf.split(b'\r\n', 1)
                        # Strip nulls and non-printable bytes
                        raw = bytes(b for b in raw if 0x20 <= b < 0x7f)
                        ln = raw.decode(errors='replace').strip()
                        if not ln or ln in ('> ', '>'):
                            continue
                        if ln.startswith('#'):
                            continue
                        # Strip leading prompt from async output
                        if ln.startswith('> '):
                            ln = ln[2:]
                        if not ln:
                            continue
                        # Drop garbage lines from MAC errors etc.
                        if 'Failed to set' in ln:
                            continue
                        # Drop truncated ESSID fragments
                        if ln.startswith('D: ') and 'Ch:' not in ln:
                            continue
                        with self.lock:
                            self.lines.append(ln)
                            if len(self.lines) > 4000:
                                del self.lines[:2000]
                else:
                    time.sleep(0.02)
            except Exception:
                time.sleep(0.1)


_inst = None


class _GpsPoller:
    """Persistent gpspipe reader. Thread-safe live TPV/SKY state."""

    def __init__(self):
        self.state = {
            "mode": 0, "lat": None, "lon": None, "alt": None,
            "speed": None, "sats_used": 0, "sats_seen": 0,
            "eph": None, "ts": 0.0, "error": None,
        }
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._proc = None
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        p = self._proc
        if p:
            try:
                p.terminate()
                p.wait(timeout=1)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        if self._thread:
            self._thread.join(timeout=1)
        self._proc = None

    def snap(self):
        with self._lock:
            return dict(self.state)

    def _set_error(self, msg):
        with self._lock:
            self.state["error"] = msg

    def _run(self):
        while not self._stop.is_set():
            try:
                self._proc = subprocess.Popen(
                    ["gpspipe", "-w"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, bufsize=1,
                )
            except FileNotFoundError:
                self._set_error("gpspipe not installed")
                return
            except Exception as e:
                self._set_error(f"gpsd: {e}")
                self._stop.wait(2)
                continue

            with self._lock:
                self.state["error"] = None

            try:
                for line in self._proc.stdout:
                    if self._stop.is_set():
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    cls = d.get("class")
                    if cls == "TPV":
                        with self._lock:
                            self.state["mode"] = d.get("mode", 0)
                            if d.get("lat") is not None:
                                self.state["lat"] = d["lat"]
                            if d.get("lon") is not None:
                                self.state["lon"] = d["lon"]
                            self.state["alt"] = d.get("altMSL", d.get("alt"))
                            self.state["speed"] = d.get("speed")
                            self.state["eph"] = d.get("eph")
                            self.state["ts"] = time.time()
                    elif cls == "SKY":
                        with self._lock:
                            self.state["sats_seen"] = d.get("nSat", 0)
                            self.state["sats_used"] = d.get("uSat", 0)
            except Exception:
                pass

            # Subprocess exited; retry unless stopping
            if not self._stop.is_set():
                self._set_error("gpsd disconnected — retrying")
                self._stop.wait(2)


class _OsmStreetFetcher:
    """Background thread that downloads OSM highway geometry via Overpass API.

    Streets in a ~500m radius around the current GPS fix are cached to disk
    and redrawn under the war-drive map. Re-fetches when position drifts
    >200m from the last query center. Safe to call without network — on
    failure, get_streets() just returns [] and sets an error string.
    """

    CACHE_PATH = os.path.expanduser(
        "~/esp32/marauder-logs/osm-streets-cache.json")
    ENDPOINT = "https://overpass-api.de/api/interpreter"
    RADIUS_M = 500
    MOVE_THRESHOLD_M = 220    # ~2-3 NYC blocks before re-fetch
    MAX_AGE_S = 7 * 86400     # cache for a week — urban grid rarely changes
    RETRY_AFTER_FAIL = 60
    MAX_CACHE_ENTRIES = 50    # cover more unique bboxes for city walks

    # Highway tier — drives the render layer (major/minor) and filters
    # sidewalks / driveways / footpaths / pedestrian zones out of the
    # query entirely. In NYC this trims ~60-70% of ways.
    MAJOR_TYPES = frozenset([
        "motorway", "trunk", "primary", "secondary",
        "motorway_link", "trunk_link", "primary_link", "secondary_link",
    ])
    MINOR_TYPES = frozenset([
        "tertiary", "tertiary_link",
        "unclassified", "residential", "living_street",
    ])
    # Combined regex for the Overpass `[highway~"..."]` filter
    HIGHWAY_FILTER = (
        "^(motorway|trunk|primary|secondary|tertiary|unclassified|"
        "residential|living_street|"
        "motorway_link|trunk_link|primary_link|secondary_link|"
        "tertiary_link)$"
    )

    def __init__(self):
        self.streets = []              # list of polylines [[(lat, lon), ...]]
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._pos = None               # latest (lat, lon) from GPS
        self._last_center = None       # (lat, lon) of last successful fetch
        self._last_fetch_ts = 0.0
        self._last_attempt_ts = 0.0
        self._err = None
        self._cache = None             # loaded on demand

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def update_position(self, lat, lon):
        with self._lock:
            self._pos = (lat, lon)

    def get_streets(self):
        with self._lock:
            return list(self.streets)

    def status(self):
        with self._lock:
            return {
                "count": len(self.streets),
                "err": self._err,
                "last_fetch": self._last_fetch_ts,
                "last_center": self._last_center,
            }

    def _load_cache_file(self):
        if self._cache is not None:
            return self._cache
        try:
            with open(self.CACHE_PATH, "r") as f:
                self._cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._cache = {}
        return self._cache

    def _save_cache_file(self):
        if self._cache is None:
            return
        try:
            os.makedirs(os.path.dirname(self.CACHE_PATH), exist_ok=True)
            tmp = self.CACHE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._cache, f)
            os.replace(tmp, self.CACHE_PATH)
        except OSError:
            pass

    @staticmethod
    def _cache_key(lat, lon):
        return f"{lat:.3f},{lon:.3f}"

    @staticmethod
    def _distance_m(a, b):
        if a is None or b is None:
            return float("inf")
        lat1, lon1 = a
        lat2, lon2 = b
        mean_lat = (lat1 + lat2) / 2
        dlat_m = (lat2 - lat1) * 111320.0
        dlon_m = (lon2 - lon1) * 111320.0 * _math.cos(_math.radians(mean_lat))
        return _math.hypot(dlat_m, dlon_m)

    def _fetch(self, lat, lon):
        query = (
            f"[out:json][timeout:25];"
            f"way(around:{self.RADIUS_M},{lat},{lon})"
            f"[highway~\"{self.HIGHWAY_FILTER}\"];"
            f"out geom tags;"
        )
        data = ("data=" + query).encode("utf-8")
        req = __import__("urllib.request").request.Request(
            self.ENDPOINT, data=data, method="POST",
            headers={"User-Agent": "uconsole-wardrive/0.1"})
        try:
            with __import__("urllib.request").request.urlopen(
                    req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            with self._lock:
                self._err = f"overpass: {e.__class__.__name__}"
            return None

        streets = []
        for el in payload.get("elements", []):
            geom = el.get("geometry") or []
            if len(geom) < 2:
                continue
            htype = (el.get("tags") or {}).get("highway", "residential")
            poly = [(p["lat"], p["lon"]) for p in geom
                    if "lat" in p and "lon" in p]
            if len(poly) >= 2:
                streets.append({"poly": poly, "type": htype})
        return streets

    @staticmethod
    def _normalize_cached_streets(raw):
        """Accept old flat-polyline cache entries alongside new dict entries."""
        out = []
        for item in raw:
            if isinstance(item, dict) and "poly" in item:
                poly = [(p[0], p[1]) for p in item["poly"]]
                htype = item.get("type", "residential")
                if len(poly) >= 2:
                    out.append({"poly": poly, "type": htype})
            elif isinstance(item, list):
                # Legacy format: flat list of [lat, lon] pairs
                poly = [(p[0], p[1]) for p in item]
                if len(poly) >= 2:
                    out.append({"poly": poly, "type": "residential"})
        return out

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                pos = self._pos
            if pos is None:
                self._stop.wait(3)
                continue

            lat, lon = pos
            key = self._cache_key(lat, lon)
            cache = self._load_cache_file()

            # Try cache first — if fresh, use it
            entry = cache.get(key)
            now = time.time()
            if entry and (now - entry.get("fetched", 0) < self.MAX_AGE_S):
                streets = self._normalize_cached_streets(
                    entry.get("streets", []))
                with self._lock:
                    self.streets = streets
                    self._last_center = (lat, lon)
                    self._last_fetch_ts = entry["fetched"]
                    self._err = None
                self._stop.wait(10)
                continue

            # Skip if we already tried to fetch this spot recently
            with self._lock:
                moved = self._distance_m(self._last_center, (lat, lon))
                recent_try = (now - self._last_attempt_ts
                              < self.RETRY_AFTER_FAIL)
            if moved < self.MOVE_THRESHOLD_M and recent_try:
                self._stop.wait(5)
                continue

            with self._lock:
                self._last_attempt_ts = now

            streets = self._fetch(lat, lon)
            if streets is None:
                self._stop.wait(self.RETRY_AFTER_FAIL)
                continue

            # Cache + publish (new dict-per-polyline format)
            cache[key] = {
                "fetched": now, "radius_m": self.RADIUS_M,
                "streets": [
                    {"poly": [[p[0], p[1]] for p in item["poly"]],
                     "type": item["type"]}
                    for item in streets
                ],
            }
            if len(cache) > self.MAX_CACHE_ENTRIES:
                oldest = sorted(cache.items(),
                                key=lambda kv: kv[1].get("fetched", 0))
                for k, _ in oldest[:len(cache) - self.MAX_CACHE_ENTRIES]:
                    cache.pop(k, None)
            self._save_cache_file()

            with self._lock:
                self.streets = streets
                self._last_center = (lat, lon)
                self._last_fetch_ts = now
                self._err = None

            self._stop.wait(15)


def _get_conn():
    """Get or create Marauder serial connection."""
    global _inst
    if _inst and _inst.ok:
        try:
            if _inst.port and _inst.port.is_open:
                return _inst
        except Exception:
            pass
    _inst = _Conn()
    return _inst if _inst.connect() else None


# ── Helpers ──────────────────────────────────────────────────────────

def _rssi_color(rssi):
    """Color pair ID for RSSI. Green > -50, Yellow > -70, Red below."""
    return tui.C_OK if rssi > -50 else tui.C_WARN if rssi > -70 else tui.C_CRIT


def _rssi_bar(rssi, width=10):
    """RSSI gauge bar. -30=full, -90=empty."""
    pct = max(0, min(100, int((rssi + 90) * 100 / 60)))
    f = int(width * pct / 100)
    return "\u2588" * f + "\u2591" * (width - f)


def _confirm(scr, title, msg):
    """Centered confirmation dialog. Returns True on confirm."""
    h, w = scr.getmaxyx()
    bw, bh = min(48, w - 4), 7
    by, bx = (h - bh) // 2, (w - bw) // 2
    wrn = curses.color_pair(C_CRIT) | curses.A_BOLD
    hdr_a = curses.color_pair(C_HEADER) | curses.A_BOLD

    tui.panel_top(scr, by, bx, bw, title)
    for r in range(1, bh - 1):
        tui.panel_side(scr, by + r, bx, bw)
        tui.put(scr, by + r, bx + 2, " " * (bw - 4), bw - 4, curses.color_pair(C_DIM))
    tui.panel_bot(scr, by + bh - 1, bx, bw)
    tui.put(scr, by + 2, bx + 4, msg[:bw - 8], bw - 8, wrn)
    tui.put(scr, by + 4, bx + 4, "[A/Y] CONFIRM", 13, hdr_a)
    tui.put(scr, by + 4, bx + 20, "[B/N] Cancel", 12, curses.color_pair(C_DIM))
    scr.refresh()

    scr.timeout(-1)
    while True:
        k = scr.getch()
        if k in (ord('a'), ord('A'), ord('y'), ord('Y'), 10, 13):
            scr.timeout(100)
            return True
        if k in (ord('b'), ord('B'), ord('n'), ord('N'), ord('q'), 27):
            scr.timeout(100)
            return False


# ── Main Menu ────────────────────────────────────────────────────────

_MENU = [
    ("WiFi Scan",       "Scan access points and stations",       "◎"),
    ("WiFi Attack",     "Deauth, beacon, probe, rickroll, CSA",  "☠"),
    ("Sniffers",        "Deauth, PMKID, beacon, probe, raw",    "◈"),
    ("BLE Tools",       "Scan, spam, AirTag, Flipper, skimmers", "⚑"),
    ("Signal Monitor",  "Live RSSI braille waveforms",           "⣿"),
    ("Evil Portal",     "Captive portal credential capture",     "⚠"),
    ("Network Recon",   "Join network, ping, ARP, port scan",   "⌗"),
    ("War Drive",       "GPS-tagged AP sweep \u2192 CSV",        "◉"),
    ("Device",          "Info, settings, MAC spoof, reboot",     "⚙"),
    ("Raw Console",     "Direct serial I/O",                     "⌨"),
]


WARDRIVE_LOG_DIR = os.path.expanduser("~/esp32/marauder-logs")
WARDRIVE_CSV_GLOB = "wardrive-*.csv"


def _resolve_wardrive_csv(arg):
    """Accept 'latest', a filename, a session stamp, or a full path."""
    import glob as _glob
    if arg == "latest":
        cands = sorted(_glob.glob(os.path.join(
            WARDRIVE_LOG_DIR, WARDRIVE_CSV_GLOB)), reverse=True)
        if not cands:
            raise FileNotFoundError(
                f"no wardrive-*.csv in {WARDRIVE_LOG_DIR}")
        return cands[0]
    if os.path.isabs(arg) or os.path.exists(arg):
        return os.path.abspath(arg)
    bare = os.path.join(WARDRIVE_LOG_DIR, arg)
    if os.path.exists(bare):
        return bare
    stamped = os.path.join(WARDRIVE_LOG_DIR, f"wardrive-{arg}.csv")
    if os.path.exists(stamped):
        return stamped
    raise FileNotFoundError(f"cannot find war-drive CSV: {arg}")


def load_wardrive_csv(path):
    """Parse a wardrive-*.csv.

    Returns (track_rows, aggregated_seen, center_lat, center_lon).
    track_rows: list of (ts_epoch, lat, lon, bssid, essid, ch, rssi)
    aggregated_seen: dict bssid -> final ap-record (not used by replay
    but convenient for static summaries).
    """
    import csv as _csv
    rows = []
    seen = {}
    all_lats, all_lons = [], []
    with open(path, "r") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            try:
                lat_raw = (row.get("lat") or "").strip()
                lon_raw = (row.get("lon") or "").strip()
                if not lat_raw or not lon_raw:
                    continue
                lat = float(lat_raw)
                lon = float(lon_raw)
                rssi = int(row["rssi"])
                ch = int(row["channel"])
                bssid = row["bssid"]
            except (ValueError, KeyError):
                continue
            try:
                ts = datetime.fromisoformat(
                    row["timestamp_iso"].replace("Z", "+00:00")).timestamp()
            except (ValueError, KeyError):
                ts = time.time()
            essid = (row.get("essid") or "").strip() or "(hidden)"
            rows.append((ts, lat, lon, bssid, essid, ch, rssi))
            all_lats.append(lat)
            all_lons.append(lon)
            ex = seen.get(bssid)
            if ex is None:
                seen[bssid] = {
                    "first_ts": ts, "last_seen": ts,
                    "best_rssi": rssi, "last_rssi": rssi,
                    "ch": ch, "essid": essid, "bssid": bssid,
                    "lat": lat, "lon": lon,
                }
            else:
                ex["last_seen"] = ts
                ex["last_rssi"] = rssi
                if rssi > ex["best_rssi"]:
                    ex["best_rssi"] = rssi
                    ex["lat"] = lat
                    ex["lon"] = lon
                if essid != "(hidden)":
                    ex["essid"] = essid
                ex["ch"] = ch
    if not all_lats:
        raise ValueError(f"no rows with valid coordinates in {path}")
    center_lat = sum(all_lats) / len(all_lats)
    center_lon = sum(all_lons) / len(all_lons)
    return rows, seen, center_lat, center_lon


def list_wardrive_sessions():
    """Return [(path, size, mtime, rows_hint, kind)] for picker UIs."""
    import glob as _glob
    out = []
    for p in _glob.glob(os.path.join(WARDRIVE_LOG_DIR, WARDRIVE_CSV_GLOB)):
        try:
            st = os.stat(p)
        except OSError:
            continue
        name = os.path.basename(p)
        kind = "DEMO" if "DEMO" in name else "LIVE"
        out.append({
            "path": p, "name": name,
            "size": st.st_size, "mtime": st.st_mtime, "kind": kind,
        })
    out.sort(key=lambda r: r["mtime"], reverse=True)
    return out


def _wardrive_replay_loop(scr, csv_path=None, speed=30.0, start_static=False,
                          show_header=True, preloaded=None, title=None):
    """Replay a wardrive CSV on the braille map.

    Either pass `csv_path` to load a single file, or pass `preloaded` as
    (rows, center_lat, center_lon) for combined/cross-session views.
    `title` overrides the header label (default: basename of csv_path).
    """
    tui.init_gauge_colors()
    js = open_gamepad()
    scr.timeout(100)

    if preloaded is not None:
        track_rows, center_lat, center_lon = preloaded
    else:
        try:
            track_rows, _final, center_lat, center_lon = \
                load_wardrive_csv(csv_path)
        except (FileNotFoundError, ValueError) as e:
            h, w = scr.getmaxyx()
            scr.erase()
            msg = f"Replay error: {e}"
            tui.put(scr, h // 2, max(0, (w - len(msg)) // 2),
                    msg[:w], min(w, len(msg)),
                    curses.color_pair(C_CRIT) | curses.A_BOLD)
            scr.refresh()
            scr.timeout(-1)
            scr.getch()
            if js:
                close_gamepad(js)
            return

    total = len(track_rows)
    if total == 0:
        return

    fetcher = _OsmStreetFetcher()
    fetcher.start()
    fetcher.update_position(center_lat, center_lon)
    for _ in range(10):
        time.sleep(0.2)
        if fetcher.get_streets():
            break

    seen = {}
    track = []
    idx = 0
    paused = False
    streets_on = True
    cur_speed = float(speed)
    zoom = 1.0
    pan_lat_off = 0.0
    pan_lon_off = 0.0

    def apply_row(row):
        ts, lat, lon, bssid, essid, ch, rssi = row
        track.append((ts, lat, lon))
        ex = seen.get(bssid)
        if ex is None:
            seen[bssid] = {
                "first_ts": ts, "last_seen": ts,
                "best_rssi": rssi, "last_rssi": rssi,
                "ch": ch, "essid": essid, "bssid": bssid,
                "lat": lat, "lon": lon,
            }
        else:
            ex["last_seen"] = ts
            ex["last_rssi"] = rssi
            if rssi > ex["best_rssi"]:
                ex["best_rssi"] = rssi
                ex["lat"] = lat
                ex["lon"] = lon
            if essid != "(hidden)":
                ex["essid"] = essid
            ex["ch"] = ch

    if start_static:
        for r in track_rows:
            apply_row(r)
        idx = total

    first_ts = track_rows[0][0]
    last_ts = track_rows[-1][0]
    wall_start = time.time()
    sim_cursor = first_ts

    try:
        while True:
            real_now = time.time()
            if not paused and idx < total:
                elapsed_real = real_now - wall_start
                sim_cursor = first_ts + elapsed_real * cur_speed
                while idx < total and track_rows[idx][0] <= sim_cursor:
                    apply_row(track_rows[idx])
                    fetcher.update_position(track_rows[idx][1],
                                            track_rows[idx][2])
                    idx += 1

            if track:
                _t, clat, clon = track[-1]
            else:
                clat, clon = center_lat, center_lon
            gps_state = {"mode": 3, "lat": clat, "lon": clon, "alt": 15.0,
                         "speed": 0, "sats_used": 8, "sats_seen": 14,
                         "eph": 8.5, "ts": real_now, "error": None}

            h, w = scr.getmaxyx()
            scr.erase()
            if show_header:
                pct = 100 * idx // total if total else 100
                state = ("\u25a0 DONE" if idx >= total
                         else "\u2016 PAUSED" if paused
                         else "\u25ba PLAYING")
                detail = (f"{len(seen)} APs  {idx}/{total} rows  "
                          f"{pct}%  {cur_speed:g}x")
                header_label = title or "REPLAY"
                tui.panel_top(scr, 0, 0, w,
                              f"{header_label}  {state}", detail,
                              title_pair=curses.color_pair(C_OK)
                              | curses.A_BOLD)
                tui.panel_side(scr, 1, 0, w)
                name = (os.path.basename(csv_path) if csv_path
                        else f"{total} sightings combined")
                info = (f"{name}  \u00b7  streets:"
                        f"{'on' if streets_on else 'off'}")
                tui.put(scr, 1, 2, info[:w - 4], w - 4,
                        curses.color_pair(C_DIM) | curses.A_DIM)
                content_y, content_h = 2, h - 4
            else:
                content_y, content_h = 0, h - 1

            _draw_wardrive_map(
                scr, content_y, content_h, w,
                list(seen.values()), track, gps_state,
                streets=(fetcher.get_streets() if streets_on else None),
                zoom=zoom, pan_offset=(pan_lat_off, pan_lon_off))

            tui.panel_bot(scr, h - 2, 0, w)
            foot = (f" {'X Resume' if paused else 'X Pause'} \u2502 "
                    f"+/- Speed \u2502 \u2190\u2191\u2193\u2192 Pan \u2502 "
                    f"[ ] Zoom \u2502 0 Reset \u2502 R Restart \u2502 S Streets \u2502 B Back ")
            tui.put(scr, h - 1, 0, foot.center(w), w,
                    curses.color_pair(C_FOOTER))
            scr.refresh()

            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None:
                continue
            if key in (ord('q'), ord('Q'), 27) or gp == "back":
                break
            if key in (ord('x'), ord('X'), ord(' ')) or gp == "refresh":
                paused = not paused
                if not paused:
                    elapsed_sim = sim_cursor - first_ts
                    wall_start = real_now - elapsed_sim / cur_speed
            if key in (ord('+'), ord('=')):
                cur_speed = min(300, cur_speed * 1.5)
                elapsed_sim = sim_cursor - first_ts
                wall_start = real_now - elapsed_sim / cur_speed
            if key in (ord('-'), ord('_')):
                cur_speed = max(0.25, cur_speed / 1.5)
                elapsed_sim = sim_cursor - first_ts
                wall_start = real_now - elapsed_sim / cur_speed
            if key in (ord('r'), ord('R')):
                seen.clear(); track.clear(); idx = 0
                wall_start = real_now
                sim_cursor = first_ts
            if key in (ord('s'), ord('S')):
                streets_on = not streets_on
            # Zoom + pan (arrows, [ ], 0). +/- remain reserved for speed.
            step = 0.001 / max(0.2, zoom)
            if key == curses.KEY_UP:
                pan_lat_off += step
            elif key == curses.KEY_DOWN:
                pan_lat_off -= step
            elif key == curses.KEY_LEFT:
                pan_lon_off -= step
            elif key == curses.KEY_RIGHT:
                pan_lon_off += step
            elif key == ord(']'):
                zoom = min(zoom * 1.25, 16.0)
            elif key == ord('['):
                zoom = max(zoom / 1.25, 0.2)
            elif key in (ord('0'), curses.KEY_HOME):
                zoom = 1.0
                pan_lat_off = 0.0
                pan_lon_off = 0.0
    finally:
        fetcher.stop()
        if js:
            close_gamepad(js)


def load_all_wardrive_sessions():
    """Load every wardrive-*.csv and return a single combined dataset.

    Returns (rows, center_lat, center_lon) matching the shape the replay
    loop expects via `preloaded=`. Rows are globally time-sorted so
    static playback feels chronological across sessions.
    """
    sessions = list_wardrive_sessions()
    all_rows = []
    all_lats = []
    all_lons = []
    for s in sessions:
        try:
            rows, _seen, _cl, _clo = load_wardrive_csv(s["path"])
        except (FileNotFoundError, ValueError):
            continue
        all_rows.extend(rows)
        for _ts, lat, lon, *_ in rows:
            all_lats.append(lat)
            all_lons.append(lon)
    if not all_lats:
        raise ValueError("no wardrive CSVs with coordinates found")
    all_rows.sort(key=lambda r: r[0])  # global timeline
    return all_rows, (sum(all_lats) / len(all_lats)), \
        (sum(all_lons) / len(all_lons))


def run_wardrive_combined(scr):
    """Static combined map of every past wardrive session.

    Dedupes APs by BSSID (latest strongest wins) and concatenates tracks
    in chronological order. Shown static; pan/zoom work as usual.
    """
    try:
        rows, clat, clon = load_all_wardrive_sessions()
    except ValueError as e:
        h, w = scr.getmaxyx()
        scr.erase()
        msg = str(e)
        tui.put(scr, h // 2, max(0, (w - len(msg)) // 2),
                msg[:w], min(w, len(msg)),
                curses.color_pair(C_WARN) | curses.A_BOLD)
        tui.put(scr, h // 2 + 2, max(0, (w - 22) // 2),
                "Press any key to exit", 22,
                curses.color_pair(C_DIM) | curses.A_DIM)
        scr.refresh()
        scr.timeout(-1)
        scr.getch()
        return
    _wardrive_replay_loop(scr, csv_path=None,
                          preloaded=(rows, clat, clon),
                          start_static=True, show_header=True,
                          title="ALL SESSIONS")


_COMBINED_SENTINEL = "__combined__"


def _wardrive_session_picker(scr):
    """Curses picker for past wardrive-*.csv.

    Returns one of: a path, the string "__combined__", or None.
    """
    js = open_gamepad()
    scr.timeout(100)
    sessions = list_wardrive_sessions()
    sel = 0
    scroll = 0

    try:
        while True:
            h, w = scr.getmaxyx()
            scr.erase()
            tui.panel_top(scr, 0, 0, w, "SELECT SESSION",
                          f"{len(sessions)} files")

            if not sessions:
                tui.panel_side(scr, 2, 0, w)
                msg = f"No wardrive-*.csv files in {WARDRIVE_LOG_DIR}"
                tui.put(scr, 2, 2, msg[:w - 4], w - 4,
                        curses.color_pair(C_DIM) | curses.A_DIM)
                tui.panel_bot(scr, h - 2, 0, w)
                tui.put(scr, h - 1, 0, " B Back ".center(w), w,
                        curses.color_pair(C_FOOTER))
                scr.refresh()
                key, gp = _tui_input_loop(scr, js)
                if key in (ord('q'), ord('Q'), 27) or gp == "back":
                    return None
                continue

            # Header row
            tui.panel_side(scr, 1, 0, w)
            hdr = f"  {'NAME':<28} {'SIZE':>8} {'AGE':>10}  KIND"
            tui.put(scr, 1, 2, hdr[:w - 4], w - 4,
                    curses.color_pair(C_CAT) | curses.A_BOLD)

            # Rows: index 0 is the "COMBINED" virtual entry, rest are files
            total_items = len(sessions) + 1
            vis = h - 5
            if sel < scroll:
                scroll = sel
            if sel >= scroll + vis:
                scroll = sel - vis + 1

            now = time.time()
            for i in range(vis):
                y = 2 + i
                tui.panel_side(scr, y, 0, w)
                idx = scroll + i
                if idx >= total_items:
                    continue
                is_sel = idx == sel
                mk = "\u25b8" if is_sel else " "
                attr = (curses.color_pair(C_SEL) | curses.A_BOLD if is_sel
                        else curses.color_pair(C_ITEM))
                if idx == 0:
                    # Virtual combined entry
                    total_kb = sum(s["size"] for s in sessions) / 1024
                    sz = (f"{total_kb:.1f}K" if total_kb < 1024
                          else f"{total_kb / 1024:.2f}M")
                    row = (f"{mk} \u22c6 ALL SESSIONS (combined){' ':<6}"
                           f"{sz:>8} {len(sessions):>5} files  \u2217")
                    tui.put(scr, y, 2, row[:w - 4], w - 4,
                            curses.color_pair(C_OK) | curses.A_BOLD
                            if is_sel else
                            curses.color_pair(C_CAT) | curses.A_BOLD)
                    continue
                s = sessions[idx - 1]
                age_s = int(now - s["mtime"])
                if age_s < 60:
                    age = f"{age_s}s ago"
                elif age_s < 3600:
                    age = f"{age_s // 60}m ago"
                elif age_s < 86400:
                    age = f"{age_s // 3600}h ago"
                else:
                    age = f"{age_s // 86400}d ago"
                size_kb = s["size"] / 1024
                size_s = (f"{size_kb:.1f}K" if size_kb < 1024
                          else f"{size_kb / 1024:.2f}M")
                name = s["name"].replace("wardrive-", "").replace(".csv", "")
                row = f"{mk} {name:<28} {size_s:>8} {age:>10}  {s['kind']}"
                tui.put(scr, y, 2, row[:w - 4], w - 4, attr)

            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " \u2191\u2193 Select \u2502 Enter View \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))
            scr.refresh()

            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None:
                continue
            if key in (ord('q'), ord('Q'), 27) or gp == "back":
                return None
            if key in (curses.KEY_UP, ord('k')):
                sel = max(0, sel - 1)
            elif key in (curses.KEY_DOWN, ord('j')):
                sel = min(total_items - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                if sel == 0:
                    return _COMBINED_SENTINEL
                return sessions[sel - 1]["path"]
    finally:
        if js:
            close_gamepad(js)


def run_wardrive_replay(scr):
    """Standalone TUI entry point: pick a past session, then replay it.

    The picker also offers a "COMBINED" entry that renders every past
    session merged into one static map.
    """
    choice = _wardrive_session_picker(scr)
    if not choice:
        return
    if choice == _COMBINED_SENTINEL:
        run_wardrive_combined(scr)
    else:
        _wardrive_replay_loop(scr, choice, speed=30.0,
                              start_static=False, show_header=True)


def run_wardrive(scr):
    """Standalone War Drive entry — opens the view directly without
    going through the Marauder tile grid."""
    tui.init_gauge_colors()
    mrd = _get_conn()
    if not mrd or not mrd.ok:
        # Minimal "not connected" screen — wait for any key then exit.
        h, w = scr.getmaxyx()
        scr.erase()
        msg = "ESP32 not connected \u2014 check /dev/esp32"
        tui.put(scr, h // 2 - 1, max(0, (w - len(msg)) // 2),
                msg[:w], min(w, len(msg)),
                curses.color_pair(C_CRIT) | curses.A_BOLD)
        tui.put(scr, h // 2 + 1, max(0, (w - 22) // 2),
                "Press any key to exit", 22,
                curses.color_pair(C_DIM) | curses.A_DIM)
        scr.refresh()
        scr.timeout(-1)
        scr.getch()
        return
    try:
        _wardrive(scr, mrd)
    finally:
        try:
            mrd.close()
        except Exception:
            pass


def run_marauder(scr):
    """Marauder ESP32 WiFi/BLE attack toolkit."""
    tui.init_gauge_colors()
    js = open_gamepad()
    scr.timeout(100)
    sel, status = 0, ""
    mrd = _get_conn()
    cols = 1

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        if mrd and mrd.ok:
            st = ["IDLE", "SCANNING", "ATTACKING"][mrd.state]
            hdr = f" MARAUDER  {st}  {mrd.dev_path} "
            if _selected_targets:
                names = ", ".join(t["essid"] for t in _selected_targets)
                hdr = f" MARAUDER  {st}  \u25c9 {len(_selected_targets)} AP: {names} "
            tui.put(scr, 0, 0, hdr.center(w), w,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)
        else:
            tui.put(scr, 0, 0,
                    " MARAUDER  NOT CONNECTED ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        # Tile grid
        tiles = [{"name": n, "desc": d, "icon": ic} for n, d, ic in _MENU]
        content_y = 2
        content_h = h - content_y - 3
        cols, _rows = draw_tile_grid(scr, content_y, w, content_h, tiles, sel)

        if status:
            tui.put(scr, h - 2, 1, status[:w - 2], w - 2,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        tui.put(scr, h - 1, 0,
                " \u2191\u2193\u2190\u2192 Navigate \u2502 A Enter \u2502 B Back ".center(w),
                w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - cols)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(_MENU) - 1, sel + cols)
        elif key == curses.KEY_LEFT or key == ord("h"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_RIGHT or key == ord("l"):
            sel = min(len(_MENU) - 1, sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if not mrd or not mrd.ok:
                status = "ESP32 not connected \u2014 check /dev/esp32"
                continue
            status = ""
            fn = _get_menu_fns().get(sel)
            if fn:
                result = fn(scr, mrd)
                if result == "attack":
                    _wifi_attack(scr, mrd)
                # Flush stale B press from sub-view exit
                read_gamepad(js)
                curses.flushinp()
                _gp_set_cooldown(0.5)
                scr.timeout(100)

    if mrd:
        mrd.close()
    if js:
        read_gamepad(js)  # flush lingering B press
        close_gamepad(js)
    curses.flushinp()
    _gp_set_cooldown(0.5)
    scr.timeout(100)


# ── WiFi Scan ────────────────────────────────────────────────────────

def _wifi_scan(scr, mrd):
    """Live AP scanner with RSSI bars and target selection."""
    js = open_gamepad()
    scr.timeout(200)
    aps = []
    sel, scroll = 0, 0
    scanning = False
    t0 = time.time()

    def start():
        nonlocal scanning, t0
        aps.clear()
        # Fully reset Marauder state — stop, clear stale APs, then scan
        mrd.send("stopscan")
        time.sleep(0.3)
        mrd.send("clearlist -a")
        time.sleep(0.3)
        mrd.drain()
        mrd.clear()
        mrd.send("scanap")
        mrd.state = _SCANNING
        scanning = True
        t0 = time.time()

    def _save_targets():
        """Save selected APs to module-level _selected_targets.

        Also attempts Marauder select -a, but Signal Monitor
        uses _selected_targets directly (not Marauder's state).
        """
        global _selected_targets
        selected = [a for a in aps if a.get("selected")]
        _selected_targets = [
            {"essid": a["essid"], "bssid": a["bssid"],
             "ch": a["ch"], "rssi": a["rssi"],
             "hist": tui.make_history(120)}
            for a in selected
        ]
        if not selected:
            return
        # Best-effort Marauder select (needed for attacks)
        time.sleep(0.5)
        mrd.drain()
        for i, a in enumerate(aps):
            if a.get("selected"):
                mrd.send(f"select -a {i}")
                time.sleep(0.15)
        mrd.drain()

    def stop():
        nonlocal scanning
        mrd.stop_scan()
        scanning = False
        _save_targets()

    start()

    while True:
        for ln in mrd.drain():
            m = _RE_AP.match(ln)
            if m:
                bssid = m.group(3)
                existing = next((a for a in aps if a["bssid"] == bssid), None)
                if existing:
                    existing["rssi"] = int(m.group(1))
                else:
                    aps.append({
                        "rssi": int(m.group(1)), "ch": int(m.group(2)),
                        "bssid": bssid,
                        "essid": m.group(4).strip() or "(hidden)",
                        "selected": False,
                    })

        h, w = scr.getmaxyx()
        scr.erase()
        val = curses.color_pair(C_ITEM)
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        elapsed = int(time.time() - t0) if scanning else 0
        n_sel = sum(1 for a in aps if a.get("selected"))
        detail = f"{len(aps)} APs"
        if n_sel:
            detail += f"  {n_sel} selected"
        if scanning:
            detail += f"  {elapsed}s"
        tui.panel_top(scr, 0, 0, w,
                      "AP SCAN" if scanning else "AP LIST", detail)

        tui.panel_side(scr, 1, 0, w)
        tui.put(scr, 1, 2, f"  {'RSSI':<12} {'CH':>3}  {'BSSID':<18} ESSID",
                w - 4, curses.color_pair(C_CAT) | curses.A_BOLD)
        tui.panel_side(scr, 2, 0, w)
        tui.put(scr, 2, 2, "\u2500" * (w - 4), w - 4, dim)

        vis = h - 6
        if aps:
            sel = min(sel, len(aps) - 1)
            if sel < scroll:
                scroll = sel
            if sel >= scroll + vis:
                scroll = sel - vis + 1

        for i in range(vis):
            y = 3 + i
            idx = scroll + i
            tui.panel_side(scr, y, 0, w)
            if idx >= len(aps):
                continue
            ap = aps[idx]
            is_sel = idx == sel
            mk = "\u25b8" if is_sel else " "
            ck = "\u25c9" if ap.get("selected") else "\u25cb"
            rssi = ap["rssi"]
            bar = _rssi_bar(rssi, 8)
            col = _rssi_color(rssi)
            attr = curses.color_pair(C_SEL) | curses.A_BOLD if is_sel else val

            tui.put(scr, y, 1, f"{mk}{ck}", 2, attr)
            tui.put(scr, y, 4, bar, 8, curses.color_pair(col))
            tui.put(scr, y, 13, f"{rssi:>4}", 4,
                    curses.color_pair(col) | curses.A_BOLD)
            tui.put(scr, y, 18, f"{ap['ch']:>3}", 3, dim)
            tui.put(scr, y, 22, ap["bssid"], 17, dim)
            ew = max(1, w - 42)
            tui.put(scr, y, 40, ap["essid"][:ew], ew, attr)

        if not aps:
            tui.panel_side(scr, 3, 0, w)
            msg = "Scanning..." if scanning else "No APs found. Press S to scan."
            tui.put(scr, 3, 4, msg, w - 8, dim)

        # Status hint
        tui.panel_side(scr, h - 3, 0, w)
        if n_sel and not scanning:
            hint = f"  {n_sel} AP(s) selected. X \u2192 Attack \u2502 B Back"
            tui.put(scr, h - 3, 2, hint[:w - 4], w - 4,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        tui.panel_bot(scr, h - 2, 0, w)

        if scanning:
            foot = " \u2191\u2193 Nav \u2502 A Select \u2502 X Stop scan \u2502 B Back "
        elif n_sel:
            foot = " \u2191\u2193 Nav \u2502 A Select \u2502 X Attack \u2502 D Details \u2502 S Rescan \u2502 B Back "
        else:
            foot = " \u2191\u2193 Nav \u2502 A Select \u2502 D Details \u2502 S Rescan \u2502 B Back "
        tui.put(scr, h - 1, 0, foot.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if scanning:
                stop()
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(max(0, len(aps) - 1), sel + 1)
        elif key == ord(" ") or key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            # A button / Enter / Space = toggle selection
            if aps and sel < len(aps):
                aps[sel]["selected"] = not aps[sel]["selected"]
        elif key == ord("x") or key == ord("X") or gp == "refresh":
            if scanning:
                stop()
            elif n_sel:
                # X when APs selected = select + attack
                _save_targets()
                if js:
                    close_gamepad(js)
                scr.timeout(100)
                return "attack"
            elif aps and sel < len(aps):
                # X when no selection = show AP details
                mrd.clear()
                mrd.send(f"info -a {sel}")
                time.sleep(0.5)
                info = mrd.drain()
                bw = min(50, w - 4)
                bh = min(len(info) + 3, h - 4)
                by, bx = (h - bh) // 2, (w - bw) // 2
                tui.panel_top(scr, by, bx, bw, aps[sel]["essid"])
                for ri, ln in enumerate(info[:bh - 3]):
                    tui.panel_side(scr, by + 1 + ri, bx, bw)
                    tui.put(scr, by + 1 + ri, bx + 2, ln[:bw - 4], bw - 4, val)
                tui.panel_bot(scr, by + bh - 1, bx, bw)
                scr.refresh()
                scr.timeout(-1)
                scr.getch()
                scr.timeout(200)
        elif key == ord("d") or key == ord("D"):
            # D = details (moved from X)
            if not scanning and aps and sel < len(aps):
                mrd.clear()
                mrd.send(f"info -a {sel}")
                time.sleep(0.5)
                info = mrd.drain()
                bw = min(50, w - 4)
                bh = min(len(info) + 3, h - 4)
                by, bx = (h - bh) // 2, (w - bw) // 2
                tui.panel_top(scr, by, bx, bw, aps[sel]["essid"])
                for ri, ln in enumerate(info[:bh - 3]):
                    tui.panel_side(scr, by + 1 + ri, bx, bw)
                    tui.put(scr, by + 1 + ri, bx + 2, ln[:bw - 4], bw - 4, val)
                tui.panel_bot(scr, by + bh - 1, bx, bw)
                scr.refresh()
                scr.timeout(-1)
                scr.getch()
                scr.timeout(200)
        elif key == ord("s") or key == ord("S"):
            if not scanning:
                start()

    if js:
        close_gamepad(js)
    scr.timeout(100)
    return None


# ── WiFi Attack ──────────────────────────────────────────────────────

_ATTACKS = [
    ("Deauth",        "attack -t deauth",     "Disconnect clients from selected APs", "⚡"),
    ("Deauth (tgt)",  "attack -t deauth -c",  "Target specific selected clients",     "⚡"),
    ("Beacon List",   "attack -t beacon -l",  "Broadcast SSIDs from SSID list",       "📡"),
    ("Beacon Random", "attack -t beacon -r",  "Random SSID beacon flood",             "⁂"),
    ("Beacon Clone",  "attack -t beacon -a",  "Clone selected AP beacons",            "◎"),
    ("Probe Flood",   "attack -t probe",      "Probe request flood",                  "⟫"),
    ("Rickroll",      "attack -t rickroll",    "Rickroll SSID beacon spam",            "♪"),
    ("CSA",           "attack -t csa",         "Channel Switch Announcement",          "⇋"),
    ("SAE",           "attack -t sae",         "WPA3 SAE flood",                       "⚿"),
]


def _wifi_attack(scr, mrd):
    """WiFi attack launcher with confirmation dialog."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0
    cols = 1
    attacking = False
    status = ""

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        st = "ATTACKING" if attacking else "SELECT"
        tui.put(scr, 0, 0,
                f" WIFI ATTACK  {st} ".center(w),
                w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        if not attacking:
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _ATTACKS]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)
        else:
            dim = curses.color_pair(C_DIM) | curses.A_DIM
            tui.put(scr, 2, 2, f"Running: {_ATTACKS[sel][0]}",
                    w - 4, curses.color_pair(C_CRIT) | curses.A_BOLD)
            for i, ln in enumerate(mrd.snap()[-(h - 6):]):
                y = 4 + i
                if y >= h - 3:
                    break
                tui.put(scr, y, 2, ln[:w - 4], w - 4, dim)

        if status:
            tui.put(scr, h - 2, 1, status[:w - 2], w - 2,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        foot = (" X Stop \u2502 B Back " if attacking
                else " \u2191\u2193\u2190\u2192 Navigate \u2502 A Launch \u2502 B Back ")
        tui.put(scr, h - 1, 0, foot.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if attacking:
                mrd.stop_scan()
                attacking = False
            break
        elif not attacking:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(_ATTACKS) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(_ATTACKS) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                name, cmd, _desc, _ic = _ATTACKS[sel]
                if _confirm(scr, "ATTACK", f"Launch {name}?"):
                    mrd.clear()
                    mrd.send(cmd)
                    mrd.state = _ATTACKING
                    attacking = True
                    status = f"Running: {name}"
                    time.sleep(0.3)
                    for ln in mrd.drain():
                        if "don't have any" in ln.lower() or "list is empty" in ln.lower():
                            status = ln
                            mrd.stop_scan()
                            attacking = False
                            break
        elif (key == ord("x") or key == ord("X")) and attacking:
            mrd.stop_scan()
            attacking = False
            status = "Attack stopped"

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Sniffers ─────────────────────────────────────────────────────────

_SNIFFERS = [
    ("Deauth",       "sniffdeauth",     "Detect deauth/disassoc frames",     "⚡"),
    ("PMKID",        "sniffpmkid",      "Capture EAPOL/PMKID handshakes",    "⚿"),
    ("PMKID+Deauth", "sniffpmkid -d",   "Active PMKID with forced deauth",   "⚿"),
    ("Beacon",       "sniffbeacon",      "All beacon frames (live feed)",      "◈"),
    ("Probe",        "sniffprobe",       "Probe requests from clients",       "⟫"),
    ("Raw",          "sniffraw",         "Raw 802.11 frame capture",          "▤"),
    ("Pwnagotchi",   "sniffpwn",         "Detect nearby pwnagotchis",        "☺"),
    ("SAE",          "sniffsae",         "WPA3 SAE commit frames",            "⚿"),
    ("Pineapple",    "sniffpinescan",    "Detect WiFi Pineapple APs",        "⚠"),
]


def _sniffers(scr, mrd):
    """Sniffer selector then streaming capture view."""
    js = open_gamepad()
    scr.timeout(200)
    sel = 0
    cols = 1
    sniffing = False
    log = []
    pkt = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not sniffing:
            tui.put(scr, 0, 0,
                    " SNIFFERS  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _SNIFFERS]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)
            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))
        else:
            for ln in mrd.drain():
                pkt += 1
                if _RE_DEAUTH.match(ln):
                    log.append(("CRIT", ln))
                elif _RE_EAPOL.match(ln):
                    log.append(("OK", f"*** {ln} ***"))
                elif _RE_PROBE.match(ln):
                    log.append(("WARN", ln))
                elif "Pwnagotchi" in ln:
                    log.append(("OK", ln))
                else:
                    log.append(("DIM", ln))
                if len(log) > 2000:
                    del log[:1000]

            name = _SNIFFERS[sel][0]
            tui.panel_top(scr, 0, 0, w, f"SNIFF {name.upper()}", f"{pkt} packets")

            vis = h - 4
            start = max(0, len(log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start + i
                if idx < len(log):
                    tag, text = log[idx]
                    if tag == "CRIT":
                        attr = curses.color_pair(C_CRIT)
                    elif tag == "OK":
                        attr = curses.color_pair(C_OK) | curses.A_BOLD
                    elif tag == "WARN":
                        attr = curses.color_pair(C_WARN)
                    else:
                        attr = dim
                    tui.put(scr, y, 2, text[:w - 4], w - 4, attr)

            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if sniffing:
                mrd.stop_scan()
                sniffing = False
            else:
                break
        elif not sniffing:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(_SNIFFERS) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(_SNIFFERS) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                mrd.clear()
                mrd.send(_SNIFFERS[sel][1])
                mrd.state = _SCANNING
                sniffing = True
                log.clear()
                pkt = 0
        else:
            if key == ord("x") or key == ord("X") or gp == "refresh":
                mrd.stop_scan()
                sniffing = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── BLE Tools ────────────────────────────────────────────────────────

_BLE = [
    ("Scan AirTags",    "sniffbt -t airtag",   "Detect Apple AirTags",          "⚠"),
    ("Scan Flippers",   "sniffbt -t flipper",  "Detect Flipper Zero devices",   "◈"),
    ("Scan Flock",      "sniffbt -t flock",    "Google Find My trackers",       "◈"),
    ("Scan Meta",       "sniffbt -t meta",     "Meta/Facebook BLE devices",     "◈"),
    ("Detect Skimmers", "sniffskim",           "Card skimmer BLE detection",    "⚠"),
    ("Spam All",        "blespam -t all",      "Apple+Samsung+Windows+Flipper", "☠"),
    ("Spam Apple",      "blespam -t apple",    "Apple notification spam",       "☠"),
    ("Spam Samsung",    "blespam -t samsung",  "Samsung BLE spam",              "☠"),
    ("Spam Windows",    "blespam -t windows",  "Windows Swift Pair spam",       "☠"),
    ("Spam Flipper",    "blespam -t flipper",  "Flipper Zero BLE spam",         "☠"),
]


def _ble_parse(ln, devices, now):
    """Parse a single BLE serial line, update *devices* dict (keyed by MAC)."""
    dtype, rssi, mac, name = None, None, None, ""

    m = _RE_SKIM.search(ln)
    if m:
        rssi, mac = int(m.group(1)), m.group(2).upper()
        dtype = "Skimmer"
    if not dtype:
        m = _RE_BLE_TYPE.search(ln)
        if m:
            kw = m.group(1).capitalize()
            rssi, mac = int(m.group(2)), m.group(3).upper()
            name = (m.group(4) or "").strip()
            dtype = {"Airtag": "AirTag", "Flipper": "Flipper",
                     "Flock": "Flock", "Meta": "Meta"}.get(kw, kw)
    if not dtype:
        m = _RE_BLE.search(ln)
        if m:
            rssi, mac = int(m.group(1)), m.group(2).upper()
            name = (m.group(3) or "").strip()
            dtype = "BLE"

    if dtype is None or mac is None:
        return

    # Infer type from keywords when generic BLE
    if dtype == "BLE":
        ll = ln.lower()
        if "airtag" in ll:
            dtype = "AirTag"
        elif "flipper" in ll:
            dtype = "Flipper"
        elif "skimmer" in ll or "potential" in ll:
            dtype = "Skimmer"

    pct = max(0, min(100, int((rssi + 100) * 100 / 100)))

    if mac in devices:
        dev = devices[mac]
        dev["rssi"] = rssi
        dev["last_seen"] = now
        if name:
            dev["name"] = name
        if dtype != "BLE":
            dev["type"] = dtype
        tui.push(dev["history"], pct)
    else:
        hist = tui.make_history(120)
        tui.push(hist, pct)
        devices[mac] = {
            "type": dtype,
            "mac": mac,
            "name": name,
            "rssi": rssi,
            "last_seen": now,
            "history": hist,
        }


def _ble(scr, mrd):
    """BLE scan and spam tools with real-time dashboard."""
    js = open_gamepad()
    scr.timeout(200)
    menu_sel = 0
    cols = 1
    active = False
    is_spam = False
    devices = {}          # MAC -> device dict
    dev_sel = 0           # cursor in device list
    scan_start = 0.0
    spam_log = []

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not active:
            # ── Menu mode ────────────────────────────────────────────
            tui.put(scr, 0, 0,
                    " BLE TOOLS  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _BLE]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, menu_sel)
            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))

        elif is_spam:
            # ── Spam mode: simple raw log ────────────────────────────
            for ln in mrd.drain():
                spam_log.append(ln)
                if len(spam_log) > 2000:
                    del spam_log[:1000]

            sname = _BLE[menu_sel][0]
            tui.panel_top(scr, 0, 0, w, f"BLE {sname.upper()}",
                          "broadcasting")
            vis = h - 4
            start_i = max(0, len(spam_log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start_i + i
                if idx < len(spam_log):
                    tui.put(scr, y, 2, spam_log[idx][:w - 4], w - 4, dim)
                elif i == vis // 2 and not spam_log:
                    tui.put(scr, y, 2, "Broadcasting... (silent mode)",
                            w - 4, dim)
            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        else:
            # ── Live BLE Dashboard ───────────────────────────────────
            now = time.time()

            # Parse incoming lines
            for ln in mrd.drain():
                _ble_parse(ln, devices, now)

            # Expire stale devices (>30s)
            stale = [m for m, d in devices.items()
                     if now - d["last_seen"] > 30]
            for m in stale:
                del devices[m]

            # Sort by RSSI (strongest first)
            dev_list = sorted(devices.values(),
                              key=lambda d: d["rssi"], reverse=True)

            # Clamp cursor
            if dev_list:
                dev_sel = max(0, min(dev_sel, len(dev_list) - 1))
            else:
                dev_sel = 0

            elapsed = int(now - scan_start)
            el_m, el_s = elapsed // 60, elapsed % 60

            # Graph panel height
            GR = 4
            # Alert bar
            skimmer_alert = None
            airtag_alert = None
            for d in dev_list:
                if d["type"] == "Skimmer":
                    if skimmer_alert is None or d["rssi"] > skimmer_alert:
                        skimmer_alert = d["rssi"]
                if d["type"] in ("AirTag", "Flock"):
                    if airtag_alert is None or d["rssi"] > airtag_alert:
                        airtag_alert = d["rssi"]
            has_alert = skimmer_alert is not None or airtag_alert is not None

            # Layout: hdr(1) + col_hdr(1) + device_rows + alert(0-1)
            #         + graph_hdr(1) + graph(GR) + graph_bot(1) + footer(1)
            bot_fixed = GR + 3 + (1 if has_alert else 0)
            list_rows = max(1, h - 3 - bot_fixed)

            # ── Device List panel ────────────────────────────────────
            scan_name = _BLE[menu_sel][0]
            tui.panel_top(scr, 0, 0, w, f"BLE {scan_name.upper()}",
                          f"{len(dev_list)} devices  {el_m}:{el_s:02d}")

            # Column header
            hdr_y = 1
            tui.panel_side(scr, hdr_y, 0, w)
            col_type = 9
            col_sig = 10
            col_rssi = 6
            col_age = 5
            hdr_txt = (f" {'TYPE':<{col_type}}"
                       f"{'SIGNAL':<{col_sig}}"
                       f"{'RSSI':>{col_rssi}}"
                       f"  {'MAC':<17}"
                       f"  {'AGE':>{col_age}}")
            tui.put(scr, hdr_y, 1, hdr_txt[:w - 2], w - 2,
                    curses.color_pair(C_HEADER) | curses.A_BOLD)

            # Scrolling window
            scroll_off = 0
            if dev_sel >= list_rows:
                scroll_off = dev_sel - list_rows + 1
            visible_devs = dev_list[scroll_off:scroll_off + list_rows]

            for i, d in enumerate(visible_devs):
                y = 2 + i
                if y >= h - 1:
                    break
                tui.panel_side(scr, y, 0, w)

                real_idx = scroll_off + i
                is_selected = (real_idx == dev_sel)

                # Row color by type
                if d["type"] == "Skimmer":
                    row_attr = curses.color_pair(C_CRIT) | curses.A_BOLD
                elif d["type"] in ("AirTag", "Flipper", "Flock"):
                    row_attr = curses.color_pair(C_WARN)
                else:
                    row_attr = curses.color_pair(C_OK)

                if is_selected:
                    row_attr |= curses.A_REVERSE

                sig_bar = _rssi_bar(d["rssi"], 8)
                age = int(now - d["last_seen"])
                age_s = f"{age}s" if age < 60 else f"{age // 60}m"

                dname = d["name"] or d["type"]
                row = (f" {dname:<{col_type}}"
                       f"{sig_bar:<{col_sig}}"
                       f"{d['rssi']:>{col_rssi}}"
                       f"  {d['mac']:<17}"
                       f"  {age_s:>{col_age}}")
                tui.put(scr, y, 1, row[:w - 2], w - 2, row_attr)

            # Fill remaining list rows
            for i in range(len(visible_devs), list_rows):
                y = 2 + i
                if y >= h - 1:
                    break
                tui.panel_side(scr, y, 0, w)

            # ── Alert bar ────────────────────────────────────────────
            alert_y = 2 + list_rows
            if has_alert and alert_y < h - 1:
                tui.panel_side(scr, alert_y, 0, w)
                if skimmer_alert is not None:
                    amsg = f" \u26a0 Potential skimmer detected! {skimmer_alert}dBm"
                    tui.put(scr, alert_y, 1, amsg[:w - 2], w - 2,
                            curses.color_pair(C_CRIT) | curses.A_BOLD)
                elif airtag_alert is not None:
                    amsg = f" \u26a0 AirTag nearby {airtag_alert}dBm"
                    tui.put(scr, alert_y, 1, amsg[:w - 2], w - 2,
                            curses.color_pair(C_WARN) | curses.A_BOLD)
                alert_y += 1

            # ── Signal History panel (selected device) ───────────────
            graph_y = alert_y
            if dev_list and dev_sel < len(dev_list):
                sel_dev = dev_list[dev_sel]
                sig_detail = f"{sel_dev['rssi']}dBm  {sel_dev['mac']}"
                tui.panel_top(scr, graph_y, 0, w,
                              f"{sel_dev['type']} SIGNAL", sig_detail,
                              detail_pair=(curses.color_pair(
                                  _rssi_color(sel_dev["rssi"]))
                                  | curses.A_BOLD))
                graph_y += 1

                gw = w - 4
                if len(sel_dev["history"]) > 1:
                    col = _rssi_color(sel_dev["rssi"])
                    for row_str in tui.make_area(sel_dev["history"],
                                                 gw, GR):
                        if graph_y >= h - 1:
                            break
                        tui.panel_side(scr, graph_y, 0, w)
                        tui.put(scr, graph_y, 2, row_str, gw,
                                curses.color_pair(col))
                        graph_y += 1
                else:
                    for _ in range(GR):
                        if graph_y >= h - 1:
                            break
                        tui.panel_side(scr, graph_y, 0, w)
                        tui.put(scr, graph_y, 2, "waiting for data...",
                                gw, dim)
                        graph_y += 1
                if graph_y < h - 1:
                    tui.panel_bot(scr, graph_y, 0, w)
            else:
                tui.panel_top(scr, graph_y, 0, w, "SIGNAL", "no device")
                graph_y += 1
                for _ in range(GR):
                    if graph_y >= h - 1:
                        break
                    tui.panel_side(scr, graph_y, 0, w)
                    tui.put(scr, graph_y, 2, "no devices found",
                            w - 4, dim)
                    graph_y += 1
                if graph_y < h - 1:
                    tui.panel_bot(scr, graph_y, 0, w)

            tui.put(scr, h - 1, 0,
                    " \u2191\u2193 Nav \u2502 X Stop \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if active:
                mrd.stop_scan()
                active = False
                is_spam = False
            else:
                break
        elif not active:
            if key == curses.KEY_UP or key == ord("k"):
                menu_sel = max(0, menu_sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                menu_sel = min(len(_BLE) - 1, menu_sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                menu_sel = max(0, menu_sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                menu_sel = min(len(_BLE) - 1, menu_sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                name, cmd, _desc, _ic = _BLE[menu_sel]
                if "spam" in cmd and not _confirm(scr, "BLE SPAM",
                                                  f"Start {name}?"):
                    continue
                mrd.clear()
                mrd.send(cmd)
                mrd.state = _SCANNING
                active = True
                is_spam = "spam" in cmd
                devices.clear()
                dev_sel = 0
                scan_start = time.time()
                spam_log.clear()
        else:
            if key == ord("x") or key == ord("X") or gp == "refresh":
                mrd.stop_scan()
                active = False
                is_spam = False
            elif not is_spam:
                # Device list navigation (scan mode only)
                if key == curses.KEY_UP or key == ord("k"):
                    dev_sel = max(0, dev_sel - 1)
                elif key == curses.KEY_DOWN or key == ord("j"):
                    dev_sel = dev_sel + 1

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Signal Monitor ───────────────────────────────────────────────────

def _sigmon(scr, mrd):
    """Live RSSI waveforms per selected AP using braille area graphs."""
    js = open_gamepad()
    scr.timeout(500)

    # Use module-level targets saved by WiFi Scan (reliable)
    # instead of Marauder's flaky select -a state
    targets = list(_selected_targets)  # shallow copy

    if not targets:
        h, w = scr.getmaxyx()
        scr.erase()
        tui.panel_top(scr, 0, 0, w, "SIGNAL MONITOR", "no targets")
        tui.panel_side(scr, 2, 0, w)
        tui.put(scr, 2, 4,
                "No APs selected. Use WiFi Scan to select targets first.",
                w - 8, curses.color_pair(C_DIM))
        tui.panel_bot(scr, 4, 0, w)
        tui.put(scr, h - 1, 0, " B Back ".center(w), w,
                curses.color_pair(C_FOOTER))
        scr.refresh()
        scr.timeout(-1)
        scr.getch()
        if js:
            close_gamepad(js)
        scr.timeout(100)
        return

    mrd.clear()
    mrd.send("sniffbeacon")
    mrd.state = _SCANNING

    GR = 3

    while True:
        for ln in mrd.drain():
            m = _RE_AP.match(ln)
            if m:
                bssid = m.group(3)
                rssi = int(m.group(1))
                essid = m.group(4).strip()
                for t in targets:
                    if t["bssid"] == bssid or t["essid"] == essid:
                        t["bssid"] = bssid
                        t["rssi"] = rssi
                        tui.push(t["hist"], rssi)

        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        tui.panel_top(scr, 0, 0, w, "SIGNAL MONITOR",
                      f"{len(targets)} targets  sniffbeacon")

        y = 1
        gw = w - 6

        for t in targets:
            if y + GR + 2 >= h - 2:
                break

            rssi = t["rssi"]
            col = _rssi_color(rssi)
            bar = _rssi_bar(rssi, 8)

            tui.panel_top(scr, y, 1, w - 2, t["essid"][:20],
                          f"{bar} {rssi}dBm  Ch{t['ch']}",
                          detail_pair=curses.color_pair(col) | curses.A_BOLD)
            y += 1

            if len(t["hist"]) > 1:
                scaled = tui.make_history(120)
                for v in t["hist"]:
                    pct = max(0, min(100, int((v + 90) * 100 / 60)))
                    tui.push(scaled, pct)
                for row_str in tui.make_area(scaled, gw, GR):
                    tui.panel_side(scr, y, 1, w - 2)
                    tui.put(scr, y, 3, row_str, gw, curses.color_pair(col))
                    y += 1
            else:
                for _ in range(GR):
                    tui.panel_side(scr, y, 1, w - 2)
                    tui.put(scr, y, 3, "waiting for beacons...", gw, dim)
                    y += 1

            tui.panel_bot(scr, y, 1, w - 2)
            y += 1

        tui.put(scr, h - 1, 0,
                " X Stop \u2502 B Back ".center(w), w,
                curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key in (ord("q"), ord("Q"), ord("x"), ord("X")) or gp == "back":
            mrd.stop_scan()
            break

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Evil Portal ──────────────────────────────────────────────────────

def _portal(scr, mrd):
    """Evil portal / karma with credential capture stream."""
    js = open_gamepad()
    scr.timeout(200)
    active = False
    creds = []
    log = []
    sel = 0
    items = [
        ("Evil Portal",  "evilportal -c start", "Default captive portal", "⚠"),
        ("Karma Attack", "karma -p 0",          "Respond to all probes",  "◎"),
    ]

    cols = 1

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not active:
            tui.put(scr, 0, 0,
                    " EVIL PORTAL  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in items]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)

            if creds:
                # Show captured creds below tiles
                cy = h - 3
                for i, (u, p) in enumerate(creds[-2:]):
                    if cy - 1 - i < content_y + content_h:
                        break
                tui.put(scr, h - 2, 1,
                        f"{len(creds)} cred(s) captured"[:w - 2], w - 2,
                        curses.color_pair(C_OK) | curses.A_BOLD)

            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))
        else:
            for ln in mrd.drain():
                m = _RE_CRED.match(ln)
                if m:
                    creds.append((m.group(1), m.group(2)))
                    log.append(("CRIT", f"CAPTURED  u={m.group(1)}  p={m.group(2)}"))
                elif "client connected" in ln.lower():
                    log.append(("WARN", ln))
                elif "Evil Portal READY" in ln:
                    log.append(("OK", ln))
                else:
                    log.append(("DIM", ln))
                if len(log) > 1000:
                    del log[:500]

            tui.panel_top(scr, 0, 0, w, "EVIL PORTAL  ACTIVE",
                          f"{len(creds)} creds captured")
            vis = h - 4
            start_i = max(0, len(log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start_i + i
                if idx < len(log):
                    tag, text = log[idx]
                    if tag == "CRIT":
                        attr = curses.color_pair(C_CRIT) | curses.A_BOLD
                    elif tag == "OK":
                        attr = curses.color_pair(C_OK)
                    elif tag == "WARN":
                        attr = curses.color_pair(C_WARN)
                    else:
                        attr = dim
                    tui.put(scr, y, 2, text[:w - 4], w - 4, attr)
            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if active:
                mrd.stop_scan()
                active = False
            else:
                break
        elif not active:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(items) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(items) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                name, cmd, _desc, _ic = items[sel]
                if _confirm(scr, "PORTAL", f"Start {name}?"):
                    mrd.clear()
                    mrd.send(cmd)
                    mrd.state = _ATTACKING
                    active = True
                    log.clear()
        else:
            if key == ord("x") or key == ord("X"):
                mrd.stop_scan()
                active = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Network Recon ────────────────────────────────────────────────────

_NETRECON = [
    ("Ping Scan",  "pingscan",         "ICMP sweep (requires WiFi join)",  "⌗"),
    ("ARP Scan",   "arpscan",          "ARP sweep for local hosts",        "⌗"),
    ("ARP Full",   "arpscan -f",       "Full ARP scan (slower)",           "⌗"),
    ("Port SSH",   "portscan -s ssh",  "Scan for SSH (port 22)",           "⚿"),
    ("Port HTTP",  "portscan -s http", "Scan for HTTP (port 80)",          "◎"),
    ("Port HTTPS", "portscan -s https","Scan for HTTPS (port 443)",        "⚿"),
    ("Port RDP",   "portscan -s rdp",  "Scan for RDP (port 3389)",         "◎"),
    ("List IPs",   "list -i",          "Show discovered IPs",              "▤"),
]


def _netrecon(scr, mrd):
    """Network recon: ping, ARP, port scan."""
    js = open_gamepad()
    scr.timeout(200)
    sel = 0
    cols = 1
    active = False
    log = []

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        if not active:
            tui.put(scr, 0, 0,
                    " NETWORK RECON  SELECT ".center(w),
                    w, curses.color_pair(C_HEADER) | curses.A_BOLD)
            tiles = [{"name": n, "desc": d, "icon": ic}
                     for n, _cmd, d, ic in _NETRECON]
            content_y = 2
            content_h = h - content_y - 3
            cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                         tiles, sel)
            tui.put(scr, h - 1, 0,
                    " \u2191\u2193\u2190\u2192 Navigate \u2502 A Start \u2502 B Back ".center(w),
                    w, curses.color_pair(C_FOOTER))
        else:
            for ln in mrd.drain():
                log.append(ln)
                if len(log) > 1000:
                    del log[:500]
            name = _NETRECON[sel][0]
            tui.panel_top(scr, 0, 0, w, f"RECON {name.upper()}",
                          f"{len(log)} results")
            vis = h - 4
            start_i = max(0, len(log) - vis)
            for i in range(vis):
                y = 1 + i
                tui.panel_side(scr, y, 0, w)
                idx = start_i + i
                if idx < len(log):
                    tui.put(scr, y, 2, log[idx][:w - 4], w - 4,
                            curses.color_pair(C_ITEM))
            tui.panel_bot(scr, h - 2, 0, w)
            tui.put(scr, h - 1, 0,
                    " X Stop \u2502 B Back ".center(w), w,
                    curses.color_pair(C_FOOTER))

        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            if active:
                mrd.stop_scan()
                active = False
            else:
                break
        elif not active:
            if key == curses.KEY_UP or key == ord("k"):
                sel = max(0, sel - cols)
            elif key == curses.KEY_DOWN or key == ord("j"):
                sel = min(len(_NETRECON) - 1, sel + cols)
            elif key == curses.KEY_LEFT or key == ord("h"):
                sel = max(0, sel - 1)
            elif key == curses.KEY_RIGHT or key == ord("l"):
                sel = min(len(_NETRECON) - 1, sel + 1)
            elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
                mrd.clear()
                mrd.send(_NETRECON[sel][1])
                mrd.state = _SCANNING
                active = True
                log.clear()
        else:
            if key == ord("x") or key == ord("X"):
                mrd.stop_scan()
                active = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── War Drive ────────────────────────────────────────────────────────

import math as _math


def _wd_project(canvas_pw, canvas_ph, mid_lat, mid_lon, lat_span, lon_span):
    """Return a projector fn mapping (lat, lon) -> (px, py) in the canvas.
    Applies cos(lat) correction so east/north have equal screen distance."""
    lon_scale = _math.cos(_math.radians(mid_lat))
    margin = 2
    scale_x = (canvas_pw - 2 * margin) / max(lon_span * lon_scale, 1e-9)
    scale_y = (canvas_ph - 2 * margin) / max(lat_span, 1e-9)
    scale = min(scale_x, scale_y)
    cx_px = canvas_pw / 2
    cy_px = canvas_ph / 2

    def proj(lat, lon):
        px = int(cx_px + (lon - mid_lon) * lon_scale * scale)
        py = int(cy_px - (lat - mid_lat) * scale)
        return px, py
    return proj, scale


def _draw_wardrive_map(scr, y0, h_avail, w, seen_aps, track, gps_state,
                       streets=None, zoom=1.0, pan_offset=(0.0, 0.0)):
    """Braille map: streets (dim), walked track, APs, position crosshair.

    When `streets` is provided (list of [(lat, lon), ...] polylines), they
    are drawn on a separate canvas rendered BEHIND the data canvas in a
    dim color. Cells that contain both are shown in bright (data wins).

    `zoom` > 1 magnifies (smaller span). `pan_offset` is a (lat, lon)
    delta in degrees applied on top of the auto-fit center. (0, 0) + 1.0
    reproduces the original auto-fit behavior.
    """
    cw = max(10, w - 4)
    ch = max(5, h_avail - 1)
    streets = streets or []

    coords = [(a["lat"], a["lon"]) for a in seen_aps
              if a.get("lat") is not None]
    for t in track:
        coords.append((t[1], t[2]))
    cur_lat = gps_state.get("lat")
    cur_lon = gps_state.get("lon")
    if cur_lat is not None:
        coords.append((cur_lat, cur_lon))
    # Include first and last point of each street polyline — they pin
    # the viewport to the neighborhood even before any APs are seen.
    for item in streets:
        poly = item["poly"] if isinstance(item, dict) else item
        if poly:
            coords.append(poly[0])
            coords.append(poly[-1])

    if not coords:
        for i in range(h_avail):
            tui.panel_side(scr, y0 + i, 0, w)
        msg = "Waiting for GPS fix + AP sightings to build map..."
        tui.put(scr, y0 + h_avail // 2, max(2, (w - len(msg)) // 2),
                msg[:w - 4], w - 4,
                curses.color_pair(C_DIM) | curses.A_DIM)
        return

    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]
    min_span = 0.0005  # ~50m minimum view
    lat_span = max(max(lats) - min(lats), min_span)
    lon_span = max(max(lons) - min(lons), min_span)
    lat_span *= 1.15
    lon_span *= 1.15
    mid_lat = (min(lats) + max(lats)) / 2
    mid_lon = (min(lons) + max(lons)) / 2

    # Apply user zoom + pan on top of the auto-fit viewport
    if zoom and zoom > 0 and zoom != 1.0:
        lat_span /= zoom
        lon_span /= zoom
    if pan_offset and (pan_offset[0] or pan_offset[1]):
        mid_lat += pan_offset[0]
        mid_lon += pan_offset[1]

    major_canvas = tui.BrailleCanvas(cw, ch) if streets else None
    minor_canvas = tui.BrailleCanvas(cw, ch) if streets else None
    data_canvas = tui.BrailleCanvas(cw, ch)
    pw, ph = data_canvas.pw, data_canvas.ph
    proj, _ = _wd_project(pw, ph, mid_lat, mid_lon, lat_span, lon_span)

    # Viewport bounds in lat/lon for bbox culling (use the *padded*
    # span so we don't clip polylines entering the edge of the view).
    view_pad_lat = lat_span * 0.1
    view_pad_lon = lon_span * 0.1
    v_min_lat = mid_lat - lat_span / 2 - view_pad_lat
    v_max_lat = mid_lat + lat_span / 2 + view_pad_lat
    v_min_lon = mid_lon - lon_span / 2 - view_pad_lon
    v_max_lon = mid_lon + lon_span / 2 + view_pad_lon

    _MAJOR = _OsmStreetFetcher.MAJOR_TYPES

    # Streets layer — two tiers, view-culled
    if major_canvas is not None:
        for item in streets:
            if isinstance(item, dict):
                poly, htype = item["poly"], item["type"]
            else:
                poly, htype = item, "residential"
            if len(poly) < 2:
                continue

            # Quick bbox cull — drop anything entirely off-viewport
            lats_p = [p[0] for p in poly]
            lons_p = [p[1] for p in poly]
            if (max(lats_p) < v_min_lat or min(lats_p) > v_max_lat
                    or max(lons_p) < v_min_lon
                    or min(lons_p) > v_max_lon):
                continue

            target = major_canvas if htype in _MAJOR else minor_canvas
            last = None
            for lat, lon in poly:
                p = proj(lat, lon)
                if last is not None:
                    target.line(last[0], last[1], p[0], p[1])
                last = p

    # Walked track (bright)
    last = None
    for t in track:
        p = proj(t[1], t[2])
        if last is not None:
            data_canvas.line(last[0], last[1], p[0], p[1])
        last = p

    # APs — strong ones get a larger marker
    for a in seen_aps:
        if a.get("lat") is None:
            continue
        px, py = proj(a["lat"], a["lon"])
        data_canvas.set(px, py)
        if a.get("best_rssi", -100) > -65:
            for d in (1, 2):
                data_canvas.set(px + d, py)
                data_canvas.set(px - d, py)
                data_canvas.set(px, py + d)
                data_canvas.set(px, py - d)

    # Crosshair for current position
    if cur_lat is not None:
        cx, cy = proj(cur_lat, cur_lon)
        for d in range(1, 4):
            data_canvas.set(cx + d, cy)
            data_canvas.set(cx - d, cy)
            data_canvas.set(cx, cy + d)
            data_canvas.set(cx, cy - d)

    # Render priority: data (bright) > major streets (medium) >
    # minor streets (very dim). Each braille cell is an 8-bit mask;
    # we OR the masks from all layers and pick the color from the
    # highest-priority layer that contributed.
    data_attr = curses.color_pair(C_OK)
    major_attr = curses.color_pair(C_DIM)                    # medium
    minor_attr = curses.color_pair(C_DIM) | curses.A_DIM      # dimmer

    for cy in range(ch):
        y = y0 + cy
        if y >= y0 + h_avail:
            break
        tui.panel_side(scr, y, 0, w)
        for cx in range(cw):
            d_bits = data_canvas.grid[cy][cx]
            M_bits = major_canvas.grid[cy][cx] if major_canvas else 0
            m_bits = minor_canvas.grid[cy][cx] if minor_canvas else 0
            bits = d_bits | M_bits | m_bits
            if bits == 0:
                continue
            ch_str = chr(0x2800 | bits)
            if d_bits:
                attr = data_attr
            elif M_bits:
                attr = major_attr
            else:
                attr = minor_attr
            tui.put(scr, y, 2 + cx, ch_str, 1, attr)

    # Scale caption
    m_per_deg_lat = 111320
    lon_scale = _math.cos(_math.radians(mid_lat))
    width_m = int(lon_span * lon_scale * m_per_deg_lat)
    height_m = int(lat_span * m_per_deg_lat)
    if streets:
        n_major = sum(1 for s in streets
                      if isinstance(s, dict) and s.get("type") in _MAJOR)
        street_tag = f"  \u22b8 {n_major}/{len(streets)} major"
    else:
        street_tag = ""
    zoom_tag = ""
    if zoom and abs(zoom - 1.0) > 0.01:
        zoom_tag = f"  {zoom:.2g}x"
    if pan_offset and (pan_offset[0] or pan_offset[1]):
        zoom_tag += "  \u271a"  # panned indicator
    cap = (f"\u229e you  \u2022 AP  ~{width_m}m x {height_m}m"
           f"{street_tag}{zoom_tag}")
    cap_y = y0 + ch
    if cap_y < y0 + h_avail:
        tui.panel_side(scr, cap_y, 0, w)
        tui.put(scr, cap_y, 2, cap[:w - 4], w - 4,
                curses.color_pair(C_DIM) | curses.A_DIM)


def _draw_wardrive_list(scr, y0, h_avail, w, recent, now):
    """Scrolling feed of recent AP sightings."""
    dim = curses.color_pair(C_DIM) | curses.A_DIM
    val = curses.color_pair(C_ITEM)

    # Column header row (consumes 1 row of h_avail)
    tui.panel_side(scr, y0, 0, w)
    hdr = f"  {'RSSI':<14} {'CH':>3}  {'BSSID':<18} {'ESSID':<24} AGE"
    tui.put(scr, y0, 2, hdr[:w - 4], w - 4,
            curses.color_pair(C_CAT) | curses.A_BOLD)

    for i in range(h_avail - 1):
        y = y0 + 1 + i
        tui.panel_side(scr, y, 0, w)
        if i >= len(recent):
            continue
        ap = recent[i]
        rssi = ap["rssi"]
        age = int(now - ap["ts"])
        col = _rssi_color(rssi)
        bar = _rssi_bar(rssi, 8)
        tag = "NEW" if ap["new"] else f"{age}s"
        tag_attr = (curses.color_pair(C_OK) | curses.A_BOLD
                    if ap["new"] else dim)
        tui.put(scr, y, 2, bar, 8, curses.color_pair(col))
        tui.put(scr, y, 11, f"{rssi:>4}", 4,
                curses.color_pair(col) | curses.A_BOLD)
        tui.put(scr, y, 17, f"{ap['ch']:>3}", 3, dim)
        tui.put(scr, y, 22, ap["bssid"], 17, dim)
        ew = max(1, w - 46)
        tui.put(scr, y, 41, ap["essid"][:ew], ew, val)
        tui.put(scr, y, w - 6, tag[:5], 5, tag_attr)


def _wardrive_summary(scr, js, log_path, row_count, ap_count, duration_s,
                      with_gps, sightings, log_err):
    """Modal: session saved — show file info, require confirmation to exit."""
    size_bytes = 0
    try:
        if log_path and os.path.exists(log_path):
            size_bytes = os.path.getsize(log_path)
    except OSError:
        pass
    if size_bytes >= 1024 * 1024:
        size_str = f"{size_bytes / 1024 / 1024:.2f} MB"
    elif size_bytes >= 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes} B"

    mins = duration_s // 60
    secs = duration_s % 60
    dur_str = f"{mins}m {secs}s"

    host = os.uname().nodename
    url = f"https://{host}.local/wardrive"

    lines = [
        ("SESSION SAVED", curses.color_pair(C_OK) | curses.A_BOLD),
        ("", 0),
        (f"Unique APs:    {ap_count}", curses.color_pair(C_ITEM)),
        (f"Sightings:     {sightings}", curses.color_pair(C_ITEM)),
        (f"With GPS fix:  {with_gps}", curses.color_pair(C_ITEM)),
        (f"Duration:      {dur_str}", curses.color_pair(C_ITEM)),
        (f"File size:     {size_str}  ({row_count} CSV rows)",
         curses.color_pair(C_ITEM)),
        ("", 0),
        ("Saved to:", curses.color_pair(C_DIM) | curses.A_DIM),
        (log_path or "(no file written)",
         curses.color_pair(C_HEADER) | curses.A_BOLD),
        ("", 0),
        (f"Live map:  {url}",
         curses.color_pair(C_STATUS) | curses.A_BOLD),
    ]
    if log_err:
        lines.append(("", 0))
        lines.append((f"Warning: {log_err}",
                      curses.color_pair(C_CRIT) | curses.A_BOLD))

    scr.timeout(-1)
    try:
        while True:
            h, w = scr.getmaxyx()
            scr.erase()
            bw = min(max(50, len(log_path) + 6 if log_path else 50), w - 2)
            bh = len(lines) + 6
            by = max(0, (h - bh) // 2)
            bx = max(0, (w - bw) // 2)
            tui.panel_top(scr, by, bx, bw, "WAR DRIVE")
            for i, (text, attr) in enumerate(lines):
                y = by + 2 + i
                tui.panel_side(scr, y, bx, bw)
                tui.put(scr, y, bx + 3, text[:bw - 6], bw - 6,
                        attr or curses.color_pair(C_ITEM))
            tui.panel_side(scr, by + bh - 2, bx, bw)
            foot = "[A/Enter] Exit    [B] Keep scanning"
            tui.put(scr, by + bh - 2, bx + 3, foot[:bw - 6], bw - 6,
                    curses.color_pair(C_FOOTER) | curses.A_BOLD)
            tui.panel_bot(scr, by + bh - 1, bx, bw)
            scr.refresh()
            key, gp = _tui_input_loop(scr, js)
            if key in (ord("a"), ord("A"), ord("y"), ord("Y"),
                       10, 13) or gp == "enter":
                return True
            if key in (ord("b"), ord("B"), ord("n"), ord("N"), ord("q"),
                       ord("Q"), 27) or gp == "back":
                return False
    finally:
        scr.timeout(200)


def _wardrive(scr, mrd):
    """Continuous AP capture tagged with live GPS coords.

    Writes a CSV row for every sighting (not just new APs) so you get
    signal-over-time for later heatmap/triangulation work. Schema close
    to WiGLE WigleWifi-1.4 so sessions are portable.
    """
    js = open_gamepad()
    scr.timeout(200)

    # ── Log file ─────────────────────────────────────────────────────
    log_dir = os.path.expanduser("~/esp32/marauder-logs")
    log_f = None
    log_err = None
    log_path = ""
    try:
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        log_path = os.path.join(log_dir, f"wardrive-{stamp}.csv")
        log_f = open(log_path, "w", buffering=1)
        log_f.write("timestamp_iso,bssid,essid,channel,rssi,"
                    "lat,lon,altitude,speed,gps_mode,sats_used,first_seen\n")
    except OSError as e:
        log_err = f"log: {e}"

    # ── State ────────────────────────────────────────────────────────
    gps = _GpsPoller()
    gps.start()
    streets_fetcher = _OsmStreetFetcher()
    streets_fetcher.start()

    seen = {}
    recent = collections.deque(maxlen=400)
    track = collections.deque(maxlen=1200)   # (ts, lat, lon) samples
    new_ts = collections.deque()
    row_count = 0
    rows_with_gps = 0
    sighting_count = 0

    scan_start = time.time()
    last_restart = scan_start
    last_track_sample = 0.0
    last_size_check = 0.0
    file_size = 0
    paused = False
    view = "map"  # or "list"
    streets_on = True
    status = ""
    zoom = 1.0
    pan_lat_off = 0.0
    pan_lon_off = 0.0

    def start_scan():
        mrd.send("stopscan")
        time.sleep(0.2)
        mrd.send("clearlist -a")
        time.sleep(0.2)
        mrd.drain()
        mrd.clear()
        mrd.send("scanap")
        mrd.state = _SCANNING

    def _csv_escape(s):
        if s is None:
            return ""
        s = str(s)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    def log_sighting(bssid, essid, ch, rssi, first_seen, gps_state):
        nonlocal log_err, row_count, rows_with_gps, sighting_count
        sighting_count += 1
        if log_f is None or log_err:
            return
        try:
            lat = gps_state.get("lat")
            lon = gps_state.get("lon")
            alt = gps_state.get("alt")
            spd = gps_state.get("speed")
            mode = gps_state.get("mode", 0)
            used = gps_state.get("sats_used", 0)
            row = ",".join([
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                _csv_escape(bssid),
                _csv_escape(essid),
                str(ch),
                str(rssi),
                f"{lat:.6f}" if lat is not None else "",
                f"{lon:.6f}" if lon is not None else "",
                f"{alt:.1f}" if alt is not None else "",
                f"{spd:.2f}" if spd is not None else "",
                str(mode),
                str(used),
                "1" if first_seen else "0",
            ])
            log_f.write(row + "\n")
            row_count += 1
            if lat is not None:
                rows_with_gps += 1
        except OSError as e:
            log_err = f"log: {e}"

    if not paused:
        start_scan()

    host = os.uname().nodename
    web_url = f"https://{host}.local/wardrive"

    try:
        while True:
            now = time.time()

            if not paused and mrd.ok and now - last_restart > 90:
                start_scan()
                last_restart = now

            gps_state = gps.snap()

            # Sample own-position track every 1s when fix is valid
            if (gps_state.get("mode", 0) >= 2
                    and gps_state.get("lat") is not None
                    and now - last_track_sample >= 1.0):
                track.append((now, gps_state["lat"], gps_state["lon"]))
                last_track_sample = now
                streets_fetcher.update_position(
                    gps_state["lat"], gps_state["lon"])

            # Drain Marauder serial
            for ln in mrd.drain():
                m = _RE_AP.match(ln)
                if not m:
                    continue
                rssi = int(m.group(1))
                ch = int(m.group(2))
                bssid = m.group(3).lower()
                essid = m.group(4).strip() or "(hidden)"

                ap = seen.get(bssid)
                is_new = ap is None
                if is_new:
                    new_ap = {
                        "first_ts": now,
                        "best_rssi": rssi,
                        "last_rssi": rssi,
                        "ch": ch,
                        "essid": essid,
                        "last_seen": now,
                        "lat": gps_state.get("lat"),
                        "lon": gps_state.get("lon"),
                    }
                    seen[bssid] = new_ap
                    new_ts.append(now)
                else:
                    ap["last_rssi"] = rssi
                    ap["last_seen"] = now
                    if rssi > ap["best_rssi"]:
                        ap["best_rssi"] = rssi
                    if essid != "(hidden)":
                        ap["essid"] = essid
                    ap["ch"] = ch
                    # Capture coord if we didn't have one at first-seen
                    if ap.get("lat") is None and gps_state.get("lat"):
                        ap["lat"] = gps_state["lat"]
                        ap["lon"] = gps_state["lon"]

                recent.appendleft({
                    "ts": now, "bssid": bssid, "essid": essid,
                    "ch": ch, "rssi": rssi, "new": is_new,
                })
                log_sighting(bssid, essid, ch, rssi, is_new, gps_state)

            while new_ts and now - new_ts[0] > 60:
                new_ts.popleft()

            # File size poll every 2s
            if log_f and now - last_size_check > 2.0:
                try:
                    file_size = os.path.getsize(log_path)
                except OSError:
                    pass
                last_size_check = now

            # ── Render ───────────────────────────────────────────────
            h, w = scr.getmaxyx()
            scr.erase()
            dim = curses.color_pair(C_DIM) | curses.A_DIM

            # Row 0: title panel with state badge
            if paused:
                state_badge = "\u2016 PAUSED"
                state_pair = curses.color_pair(C_WARN) | curses.A_BOLD
            elif not mrd.ok:
                state_badge = "\u25a0 ESP32 DOWN"
                state_pair = curses.color_pair(C_CRIT) | curses.A_BOLD
            else:
                pulse = "\u25cf" if int(now * 2) % 2 == 0 else "\u25cb"
                state_badge = f"{pulse} LOGGING"
                state_pair = curses.color_pair(C_OK) | curses.A_BOLD

            elapsed = int(now - scan_start)
            el_m, el_s = elapsed // 60, elapsed % 60
            detail = (f"{len(seen)} APs  {len(new_ts)}/min  "
                      f"{el_m}:{el_s:02d}")
            tui.panel_top(scr, 0, 0, w, f"WAR DRIVE  {state_badge}",
                          detail, title_pair=state_pair)

            # Row 1: GPS line
            tui.panel_side(scr, 1, 0, w)
            mode = gps_state.get("mode", 0)
            err = gps_state.get("error")
            if err:
                tui.put(scr, 1, 2, f"GPS: {err}"[:w - 4], w - 4,
                        curses.color_pair(C_CRIT) | curses.A_BOLD)
            elif mode >= 2 and gps_state.get("lat") is not None:
                lat = gps_state["lat"]
                lon = gps_state["lon"]
                used = gps_state.get("sats_used", 0)
                seen_s = gps_state.get("sats_seen", 0)
                spd = gps_state.get("speed") or 0.0
                eph = gps_state.get("eph")
                eph_s = f"\u00b1{eph:.0f}m" if eph else ""
                mstr = "3D" if mode == 3 else "2D"
                gps_line = (f"GPS {mstr}  {lat:.5f},{lon:.5f}  "
                            f"{used}/{seen_s} sats  {spd:.1f}m/s  {eph_s}")
                tui.put(scr, 1, 2, gps_line[:w - 4], w - 4,
                        curses.color_pair(C_OK) | curses.A_BOLD)
            else:
                used = gps_state.get("sats_used", 0)
                seen_s = gps_state.get("sats_seen", 0)
                msg = (f"GPS: no fix  {used}/{seen_s} sats  "
                       f"(APs still logged without coords)")
                tui.put(scr, 1, 2, msg[:w - 4], w - 4,
                        curses.color_pair(C_WARN) | curses.A_BOLD)

            # Row 2: log file line (path + rows + size)
            tui.panel_side(scr, 2, 0, w)
            if log_err:
                tui.put(scr, 2, 2, log_err[:w - 4], w - 4,
                        curses.color_pair(C_CRIT) | curses.A_BOLD)
            elif log_path:
                kb = file_size / 1024 if file_size else 0
                size_str = (f"{kb:.1f} KB" if kb < 1024
                            else f"{kb / 1024:.2f} MB")
                short = os.path.basename(log_path)
                log_line = (f"\u2193 {short}  {row_count} rows  "
                            f"{size_str}  \u2022 {web_url}")
                tui.put(scr, 2, 2, log_line[:w - 4], w - 4, dim)

            # Content area
            content_y = 3
            content_h = h - content_y - 2
            if view == "map":
                street_data = (streets_fetcher.get_streets()
                               if streets_on else None)
                _draw_wardrive_map(scr, content_y, content_h, w,
                                   list(seen.values()), list(track),
                                   gps_state, streets=street_data,
                                   zoom=zoom,
                                   pan_offset=(pan_lat_off, pan_lon_off))
            else:
                _draw_wardrive_list(scr, content_y, content_h, w,
                                    recent, now)

            # Status
            if status:
                tui.put(scr, h - 2, 1, status[:w - 2], w - 2,
                        curses.color_pair(C_STATUS) | curses.A_BOLD)
            tui.panel_bot(scr, h - 2, 0, w)

            # Footer
            view_hint = "List" if view == "map" else "Map"
            s_state = "on" if streets_on else "off"
            if view == "map":
                foot = (f" {'X Resume' if paused else 'X Pause'} \u2502 "
                        f"Tab {view_hint} \u2502 \u2190\u2191\u2193\u2192 Pan \u2502 "
                        f"[ ] Zoom \u2502 0 Reset \u2502 "
                        f"S Streets:{s_state} \u2502 B Save ")
            else:
                foot = (f" {'X Resume' if paused else 'X Pause'} \u2502 "
                        f"Tab {view_hint} \u2502 "
                        f"S Streets:{s_state} \u2502 B Save & Exit ")
            tui.put(scr, h - 1, 0, foot.center(w), w,
                    curses.color_pair(C_FOOTER))
            scr.refresh()

            key, gp = _tui_input_loop(scr, js)
            if key == -1 and gp is None:
                continue
            if key == ord("q") or key == ord("Q") or gp == "back":
                if log_f:
                    try:
                        log_f.flush()
                    except Exception:
                        pass
                dur = int(time.time() - scan_start)
                confirm = _wardrive_summary(
                    scr, js, log_path, row_count, len(seen), dur,
                    rows_with_gps, sighting_count, log_err,
                )
                if confirm:
                    break
                # Else keep scanning
                continue
            elif key == ord("x") or key == ord("X") or gp == "refresh":
                if paused:
                    start_scan()
                    paused = False
                    last_restart = time.time()
                    status = ""
                else:
                    mrd.stop_scan()
                    paused = True
                    status = "Paused \u2014 file still open, X to resume"
            elif key in (9, ord("m"), ord("M"), ord("d"), ord("D")):
                # Tab, M, or D — toggle view
                view = "list" if view == "map" else "map"
            elif key in (ord("s"), ord("S")):
                streets_on = not streets_on
                st = streets_fetcher.status()
                if streets_on and st["count"] == 0 and not st["err"]:
                    status = "Streets on — fetching from Overpass..."
                elif streets_on and st["err"]:
                    status = f"Streets on — last error: {st['err']}"
                else:
                    status = (f"Streets {'on' if streets_on else 'off'}"
                              f"  ({st['count']} segments cached)")
            else:
                # Zoom + pan keybinds (only affect map view)
                if view == "map":
                    step = 0.001 / max(0.2, zoom)  # smaller when zoomed in
                    if key == curses.KEY_UP:
                        pan_lat_off += step
                    elif key == curses.KEY_DOWN:
                        pan_lat_off -= step
                    elif key == curses.KEY_LEFT:
                        pan_lon_off -= step
                    elif key == curses.KEY_RIGHT:
                        pan_lon_off += step
                    elif key in (ord("]"), ord("+"), ord("=")):
                        zoom = min(zoom * 1.25, 16.0)
                    elif key in (ord("["), ord("-"), ord("_")):
                        zoom = max(zoom / 1.25, 0.2)
                    elif key in (ord("0"), curses.KEY_HOME):
                        zoom = 1.0
                        pan_lat_off = 0.0
                        pan_lon_off = 0.0

    finally:
        try:
            mrd.stop_scan()
        except Exception:
            pass
        gps.stop()
        try:
            streets_fetcher.stop()
        except Exception:
            pass
        if log_f:
            try:
                log_f.flush()
                log_f.close()
            except Exception:
                pass
        if js:
            close_gamepad(js)
        scr.timeout(100)


# ── Device Info ──────────────────────────────────────────────────────

_DEV = [
    ("Device Info",     "info",            "Chip, firmware, MAC, SD card",    "⚙"),
    ("Settings",        "settings",        "View Marauder settings",          "⚙"),
    ("Random AP MAC",   "randapmac",       "Randomize AP MAC address",        "⇋"),
    ("Random STA MAC",  "randstamac",      "Randomize station MAC address",   "⇋"),
    ("Clear AP List",   "clearlist -a",    "Clear scanned APs",               "▤"),
    ("Clear STA List",  "clearlist -c",    "Clear scanned stations",          "▤"),
    ("Clear SSID List", "clearlist -s",    "Clear SSID list",                 "▤"),
    ("LED Rainbow",     "led -p rainbow",  "Rainbow LED mode",                "⁂"),
    ("LED Off",         "led -s 000000",   "Turn off LED",                    "⁂"),
    ("Reboot",          "reboot",          "Restart ESP32",                   "⚡"),
]


def _device(scr, mrd):
    """Device info, settings, MAC spoofing, reboot."""
    js = open_gamepad()
    scr.timeout(100)
    sel = 0
    cols = 1
    output = []
    status = ""

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM

        tui.put(scr, 0, 0,
                f" DEVICE  {mrd.dev_path} ".center(w),
                w, curses.color_pair(C_HEADER) | curses.A_BOLD)

        tiles = [{"name": n, "desc": d, "icon": ic}
                 for n, _cmd, d, ic in _DEV]
        content_y = 2
        content_h = h - content_y - 3
        cols, _rows = draw_tile_grid(scr, content_y, w, content_h,
                                     tiles, sel)

        if output:
            oy = h - 3
            for i, ln in enumerate(output[-2:]):
                if oy + i >= h - 2:
                    break
                tui.put(scr, oy + i, 2, ln[:w - 4], w - 4, dim)

        if status:
            tui.put(scr, h - 2, 1, status[:w - 2], w - 2,
                    curses.color_pair(C_STATUS) | curses.A_BOLD)

        tui.put(scr, h - 1, 0,
                " \u2191\u2193\u2190\u2192 Navigate \u2502 A Run \u2502 B Back ".center(w),
                w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - cols)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(_DEV) - 1, sel + cols)
        elif key == curses.KEY_LEFT or key == ord("h"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_RIGHT or key == ord("l"):
            sel = min(len(_DEV) - 1, sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            name, cmd, _desc, _ic = _DEV[sel]
            if name == "Reboot":
                if not _confirm(scr, "REBOOT", "Reboot ESP32?"):
                    continue
            mrd.clear()
            mrd.send(cmd)
            status = f"Sent: {cmd}"
            time.sleep(0.5)
            output = mrd.drain()
            if name == "Reboot":
                status = "ESP32 rebooting..."
                mrd.ok = False

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Raw Console ──────────────────────────────────────────────────────

def _console(scr, mrd):
    """Direct serial terminal for raw Marauder commands."""
    js = open_gamepad()
    scr.timeout(100)
    log = []
    cmd_buf = ""
    mrd.clear()

    while True:
        for ln in mrd.drain():
            log.append(ln)
            if len(log) > 2000:
                del log[:1000]

        h, w = scr.getmaxyx()
        scr.erase()
        dim = curses.color_pair(C_DIM) | curses.A_DIM
        grn = curses.color_pair(C_OK)

        tui.panel_top(scr, 0, 0, w, "SERIAL CONSOLE", mrd.dev_path)

        vis = h - 5
        start_i = max(0, len(log) - vis)
        for i in range(vis):
            y = 1 + i
            tui.panel_side(scr, y, 0, w)
            idx = start_i + i
            if idx < len(log):
                tui.put(scr, y, 2, log[idx][:w - 4], w - 4, grn)

        tui.panel_side(scr, h - 3, 0, w)
        tui.put(scr, h - 3, 2, "\u2500" * (w - 4), w - 4, dim)
        tui.panel_side(scr, h - 2, 0, w)
        prompt = f"> {cmd_buf}_"
        tui.put(scr, h - 2, 2, prompt[:w - 4], w - 4,
                curses.color_pair(C_HEADER) | curses.A_BOLD)
        tui.panel_bot(scr, h - 1, 0, w)
        tui.put(scr, h - 1, 2, " ESC Back ", 10, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue
        if key == 27 or gp == "back":
            break
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter":
            if cmd_buf:
                log.append(f"> {cmd_buf}")
                mrd.send(cmd_buf)
                cmd_buf = ""
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            cmd_buf = cmd_buf[:-1]
        elif 32 <= key < 127:
            cmd_buf += chr(key)

    if js:
        close_gamepad(js)
    scr.timeout(100)


# ── Menu → function dispatch (index-synced with _MENU) ─────────────

_MENU_FNS = None

def _get_menu_fns():
    """Lazy-init menu dispatch dict so forward refs are resolved."""
    global _MENU_FNS
    if _MENU_FNS is None:
        _MENU_FNS = {
            0: _wifi_scan,
            1: _wifi_attack,
            2: _sniffers,
            3: _ble,
            4: _sigmon,
            5: _portal,
            6: _netrecon,
            7: _wardrive,
            8: _device,
            9: _console,
        }
    return _MENU_FNS
