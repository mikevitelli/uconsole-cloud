"""TUI module: cellular tower map (SIMCom SIM7600G-H / 4G modem).

Shows the LTE serving cell the modem is camped on, plotted on a map that
REUSES the ADS-B basemap renderer (tui.adsb), centered on the device's
location. Towers seen over time are cached and drawn as dim markers so the
map gradually fills in with every cell the device has used.

Data sources (all validated on-device):
  1. Serving cell   — `AT+CPSI?` over /dev/ttyUSB2 (parsed below).
  2. Geolocation    — WiGLE cell/search (OpenCelliD fallback if a key exists).
  3. Device location — modem GPS → ADS-B "home" → serving-tower fallback.

Self-contained except for the explicit reuse of adsb.py's renderer; a fault
here can only ever hide this one menu entry.

  q Back
"""
import curses
import json
import math
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone

from tui.framework import _tui_input_loop, open_gamepad, load_config
import tui_lib as tui

# Reuse the ADS-B basemap renderer rather than reinventing it.
from tui.adsb import (
    _draw_basemap_canvas,
    _ll_to_px,
    _load_global_basemap,
    _load_hires_basemap,
    LAYER_ALL,
)

CPSI_TTY = "/dev/ttyUSB2"
RANGE_NM_DEFAULT = 25  # half-width; towers are usually within a few km
POLL_FRAMES = 4        # 4 * 1s timeout ≈ 4s between CPSI polls

CACHE_DIR = os.path.expanduser("~/.config/uconsole")
TOWER_CACHE = os.path.join(CACHE_DIR, "cell-towers.json")
OPENCELLID_KEY_FILE = os.path.join(CACHE_DIR, "opencellid.key")

# Cached, pre-encoded HTTP-Basic credential for WiGLE (module global). Never
# printed or logged. Populated lazily by _wigle_cred().
_WIGLE_CRED = None
_WIGLE_CRED_TRIED = False
_OCID_KEY = None
_OCID_KEY_TRIED = False


# ── CPSI parsing ────────────────────────────────────────────────────────
def _read_cpsi():
    """Query the modem for its serving cell. Returns the raw +CPSI line or ''."""
    try:
        out = subprocess.run(
            ["sudo", "socat", "-", f"{CPSI_TTY},crnl"],
            input="AT+CPSI?\r\n", capture_output=True, text=True, timeout=6,
        ).stdout
    except Exception:
        return ""
    for line in out.splitlines():
        if line.strip().startswith("+CPSI:"):
            return line.strip()
    return ""


def parse_cpsi(line):
    """Parse a `+CPSI:` line. Returns a serving-cell dict or None.

    Handles the LTE form:
      +CPSI: LTE,Online,<MCC>-<MNC>,<TAC_hex>,<ECI>,<PCI>,<band>,<earfcn>,
             <dlbw>,<ulbw>,<RSRQ*10>,<RSRP*10>,<RSSI*10>,<RSSNR>
    Returns None for NR5G / "No Service" / unparseable input.
    """
    if not line or "+CPSI:" not in line:
        return None
    body = line.split(":", 1)[1].strip()
    parts = [p.strip() for p in body.split(",")]
    if len(parts) < 2:
        return None
    sysmode = parts[0].upper()
    # No-service / not-camped states.
    joined = body.upper()
    if "NO SERVICE" in joined or "NOSERVICE" in joined or "OFFLINE" in joined:
        return None
    # Only the LTE form carries the TAC/ECI fields we geolocate from.
    if not sysmode.startswith("LTE"):
        return None
    if len(parts) < 13:
        return None
    try:
        mcc, mnc = parts[2].split("-")
        mcc, mnc = mcc.strip(), mnc.strip()
        mccmnc = mcc + mnc
        lac = int(parts[3], 16)              # TAC (hex)
        cid = int(parts[4])                  # ECI / SCellID
        pci = int(parts[5])
        band = parts[6]
        earfcn = parts[7]
        rsrq = int(parts[10]) / 10.0
        rsrp = int(parts[11]) / 10.0
        rssi = int(parts[12]) / 10.0
        snr = _to_float(parts[13]) if len(parts) > 13 else None
    except (ValueError, IndexError):
        return None
    return {
        "sysmode": sysmode,
        "mcc": mcc, "mnc": mnc, "mccmnc": mccmnc,
        "lac": lac, "cid": cid,
        "enb": cid >> 8, "sector": cid & 0xFF,
        "pci": pci, "band": band, "earfcn": earfcn,
        "rsrp": rsrp, "rsrq": rsrq, "rssi": rssi, "snr": snr,
    }


def _to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ── Severity (mirrors cellular_signal.py) ───────────────────────────────
def rsrp_severity(v):
    if v is None:
        return "dim"
    if v >= -90:
        return "ok"
    if v >= -105:
        return "warn"
    return "bad"


def _sev_attr(sev, bold=True):
    pair = {"ok": tui.C_OK, "warn": tui.C_WARN, "bad": tui.C_CRIT}.get(sev, tui.C_DIM)
    a = curses.color_pair(pair)
    return a | curses.A_BOLD if bold else a


# ── Distance (haversine, adapted from meshtastic_map._distance_nm) ──────
def _distance_km(lat1, lon1, lat2, lon2):
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


# ── Tower cache (persists across sessions) ──────────────────────────────
def _cache_key(mccmnc, lac, cid):
    return f"{mccmnc}_{lac}_{cid}"


def load_tower_cache():
    try:
        with open(TOWER_CACHE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_tower_cache(cache):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = TOWER_CACHE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cache, f, indent=1)
        os.replace(tmp, TOWER_CACHE)
    except Exception:
        pass


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_serving(cache, cell, geo):
    """Insert/update the serving cell in the cache; returns the cache entry."""
    key = _cache_key(cell["mccmnc"], cell["lac"], cell["cid"])
    now = _now_iso()
    ent = cache.get(key, {})
    if not ent.get("first_seen"):
        ent["first_seen"] = now
    ent["last_seen"] = now
    ent["enb"] = cell["enb"]
    ent["sector"] = cell["sector"]
    ent["pci"] = cell["pci"]
    ent["band"] = cell["band"]
    rsrp = cell.get("rsrp")
    if rsrp is not None:
        best = ent.get("rsrp_best")
        ent["rsrp_best"] = rsrp if best is None else max(best, rsrp)
    if geo:
        ent["lat"] = geo.get("lat")
        ent["lon"] = geo.get("lon")
        ent["source"] = geo.get("source")
        ent["city"] = geo.get("city")
        ent["region"] = geo.get("region")
        ent["country"] = geo.get("country")
    cache[key] = ent
    return ent


# ── Geolocation ─────────────────────────────────────────────────────────
def _op_field(title, label="credential"):
    """Fetch a 1Password field via the op CLI (service account). None on failure.
    Shared by the WiGLE and OpenCelliD secret loaders; the value is never logged."""
    try:
        with open("/home/mikevitelli/.config/op/service-account-token") as f:
            tok = f.read().strip()
    except Exception:
        return None
    env2 = dict(os.environ)
    env2["OP_SERVICE_ACCOUNT_TOKEN"] = tok
    try:
        out = subprocess.run(
            ["op", "item", "get", title, "--vault", "uConsole Infra",
             "--fields", f"label={label}", "--reveal"],
            capture_output=True, text=True, timeout=15, env=env2,
        ).stdout.strip()
        return out.strip().strip('"').strip("'") or None
    except Exception:
        return None


def _wigle_cred():
    """Pre-encoded WiGLE Basic credential (env override → 1Password). Cached."""
    global _WIGLE_CRED, _WIGLE_CRED_TRIED
    if _WIGLE_CRED is not None:
        return _WIGLE_CRED
    if _WIGLE_CRED_TRIED:
        return None
    _WIGLE_CRED_TRIED = True
    env = os.environ.get("WIGLE_BASIC")
    _WIGLE_CRED = (env.strip().strip('"').strip("'") if env
                   else _op_field("wigle-token", "credential"))
    return _WIGLE_CRED


def _opencellid_key():
    """OpenCelliD API key (env override → 1Password 'OpenCellid' → legacy file). Cached."""
    global _OCID_KEY, _OCID_KEY_TRIED
    if _OCID_KEY is not None:
        return _OCID_KEY
    if _OCID_KEY_TRIED:
        return None
    _OCID_KEY_TRIED = True
    key = os.environ.get("OPENCELLID_KEY")
    if not key:
        key = _op_field("OpenCellid", "credential")
    if not key:
        try:
            with open(OPENCELLID_KEY_FILE) as f:
                key = f.read().strip()
        except Exception:
            key = None
    _OCID_KEY = key
    return _OCID_KEY


def _wigle_query(mccmnc, lac, cid):
    """One WiGLE cell/search request. Returns the parsed JSON dict or None.

    Uses the CORRECT param names: cell_op (mccmnc), cell_net (lac),
    cell_id (cid). cell_net is included to narrow by LAC.
    """
    cred = _wigle_cred()
    if not cred:
        return None
    base = "https://api.wigle.net/api/v2/cell/search"
    if lac is not None:
        url = f"{base}?cell_op={mccmnc}&cell_net={lac}&cell_id={cid}"
    else:
        url = f"{base}?cell_op={mccmnc}&cell_id={cid}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {cred}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _wigle_geolocate(mccmnc, lac, cid):
    """WiGLE lookup with LAC-narrow then LAC-less retry. Returns geo dict|None."""
    data = _wigle_query(mccmnc, lac, cid)
    if data is None:
        return None
    # A huge totalResults means the filter was ignored (whole DB) → no match.
    total = data.get("totalResults")
    if isinstance(total, int) and total > 100000:
        return None
    results = data.get("results") or []
    if not results and lac is not None and data.get("success"):
        # Narrow filter found nothing → retry without LAC.
        data2 = _wigle_query(mccmnc, None, cid)
        if data2:
            total2 = data2.get("totalResults")
            if isinstance(total2, int) and total2 > 100000:
                return None
            results = data2.get("results") or []
    if not results:
        return None
    r = results[0]
    lat = r.get("trilat")
    lon = r.get("trilong")
    if lat is None or lon is None:
        return None
    return {
        "lat": float(lat), "lon": float(lon), "source": "wigle",
        "city": r.get("city"), "region": r.get("region"),
        "country": r.get("country"),
    }


def _opencellid_geolocate(mcc, mnc, lac, cid):
    """OpenCelliD fallback — only if a key is available. Returns geo dict|None."""
    key = _opencellid_key()
    if not key:
        return None
    url = (f"https://opencellid.org/cell/get?key={key}&mcc={mcc}&mnc={mnc}"
           f"&lac={lac}&cellid={cid}&format=json")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    lat = data.get("lat")
    lon = data.get("lon")
    if lat in (None, 0) or lon in (None, 0):
        return None
    return {
        "lat": float(lat), "lon": float(lon), "source": "opencellid",
        "city": None, "region": None, "country": None,
    }


def geolocate_cell(mccmnc, lac, cid, mcc=None, mnc=None, cache=None):
    """Resolve a cell to {lat,lon,source,city,region,country} or None.

    Checks the persisted cache BEFORE hitting the network (rate-limit guard).
    WiGLE first, OpenCelliD fallback.
    """
    if cache is not None:
        key = _cache_key(mccmnc, lac, cid)
        ent = cache.get(key)
        if ent and ent.get("lat") is not None and ent.get("lon") is not None:
            return {
                "lat": ent["lat"], "lon": ent["lon"],
                "source": ent.get("source"), "city": ent.get("city"),
                "region": ent.get("region"), "country": ent.get("country"),
            }
    geo = _wigle_geolocate(mccmnc, lac, cid)
    if geo:
        return geo
    if mcc is None or mnc is None:
        # Derive from a 6-digit mccmnc (3-digit MCC).
        if len(mccmnc) >= 5:
            mcc = mccmnc[:3]
            mnc = mccmnc[3:]
    if mcc and mnc:
        return _opencellid_geolocate(mcc, mnc, lac, cid)
    return None


# ── Device location ─────────────────────────────────────────────────────
def _run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout
    except Exception:
        return ""


def _find_modem_index():
    """First /Modem/N from `mmcli -L`; require SIM7600 to consider it present."""
    text = _run(["mmcli", "-L"])
    for m in re.finditer(r"/Modem/(\d+)\b(.*)", text):
        idx, rest = int(m.group(1)), m.group(2)
        if "SIM7600" in rest or "SIMCOM" in rest.upper():
            return idx
    return None


def _modem_gps_location(idx):
    """Try modem GPS via mmcli. Returns (lat, lon) or (None, None)."""
    if idx is None:
        return None, None
    # Best-effort enable (ignore failures — needs a GPS antenna/fix).
    _run(["mmcli", "-m", str(idx), "--location-enable-gps-nmea"], timeout=6)
    out = _run(["mmcli", "-m", str(idx), "--location-get"], timeout=6)
    # mmcli prints e.g. "latitude: 40.712800" / "longitude: -74.006000"
    mlat = re.search(r"latitude:\s*(-?\d+\.\d+)", out)
    mlon = re.search(r"longitude:\s*(-?\d+\.\d+)", out)
    if mlat and mlon:
        try:
            lat, lon = float(mlat.group(1)), float(mlon.group(1))
            if lat or lon:  # ignore 0,0
                return lat, lon
        except ValueError:
            pass
    return None, None


def _adsb_home():
    """Reuse the ADS-B home location loader convention (config keys)."""
    cfg = load_config()
    lat = cfg.get("adsb_home_lat")
    lon = cfg.get("adsb_home_lon")
    if lat is None or lon is None:
        return None, None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def device_location(idx, serving_geo):
    """(lat, lon, source) using: modem GPS → ADS-B home → serving tower."""
    lat, lon = _modem_gps_location(idx)
    if lat is not None:
        return lat, lon, "gps"
    lat, lon = _adsb_home()
    if lat is not None:
        return lat, lon, "home"
    if serving_geo:
        return serving_geo["lat"], serving_geo["lon"], "tower"
    return None, None, None


# ── Rendering ───────────────────────────────────────────────────────────
def _draw_no_modem(scr):
    scr.erase()
    h, w = scr.getmaxyx()
    msg = "4G module not powered on — use Power On first"
    tui.put(scr, h // 2, max(1, (w - len(msg)) // 2), msg, w - 2, _sev_attr("warn"))
    tui.put(scr, h - 1, 1, "q Back", w - 2, curses.color_pair(tui.C_FOOTER))
    scr.refresh()


def _draw_marker(scr, map_y, map_x, map_w, map_h, px, py, glyph, attr):
    """Place a single-char marker for a braille pixel coord, if on-screen."""
    cy_ch = map_y + py // 4
    cx_ch = map_x + px // 2
    if map_y <= cy_ch < map_y + map_h and map_x <= cx_ch < map_x + map_w:
        tui.put(scr, cy_ch, cx_ch, glyph, 1, attr)


def _draw_map(scr, state):
    scr.erase()
    h, w = scr.getmaxyx()
    dim = curses.color_pair(tui.C_DIM)
    hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
    map_attr = curses.color_pair(tui.C_HEADER)

    cell = state["cell"]
    geo = state["geo"]
    dev_lat = state["dev_lat"]
    dev_lon = state["dev_lon"]
    dev_src = state["dev_src"]
    cache = state["cache"]

    tui.put(scr, 0, 1, "CELLULAR TOWER MAP — SIM7600G-H / LTE", w - 2, hdr)

    if dev_lat is None:
        # No map center available — show sidebar-only info.
        _draw_sidebar(scr, state, sidebar_only=True)
        tui.put(scr, h - 1, 1, "no location — tower & device unmapped   q Back",
                w - 2, curses.color_pair(tui.C_FOOTER))
        scr.refresh()
        return

    range_nm = state["range_nm"]
    rng_s = f"range {range_nm}nm · src:{dev_src}"
    tui.put(scr, 0, max(1, w - len(rng_s) - 1), rng_s, len(rng_s), dim)

    map_x, map_y = 0, 1
    map_w, map_h = w, max(5, h - 2)
    canvas = tui.BrailleCanvas(map_w, map_h)

    # Basemap (reuses adsb renderer); guard so a basemap fault can't kill us.
    try:
        _draw_basemap_canvas(canvas, dev_lat, dev_lon, range_nm, LAYER_ALL)
    except Exception:
        pass

    # Device → serving-tower line.
    if geo:
        try:
            dpx, dpy = _ll_to_px(dev_lat, dev_lon, dev_lat, dev_lon,
                                 range_nm, canvas.pw, canvas.ph)
            tpx, tpy = _ll_to_px(geo["lat"], geo["lon"], dev_lat, dev_lon,
                                 range_nm, canvas.pw, canvas.ph)
            canvas.line(dpx, dpy, tpx, tpy)
        except Exception:
            pass

    for i, row in enumerate(canvas.render()):
        tui.put(scr, map_y + i, map_x, row, map_w, map_attr)

    # Previously-seen towers (dim), skipping the current serving cell.
    serving_key = None
    if cell:
        serving_key = _cache_key(cell["mccmnc"], cell["lac"], cell["cid"])
    for key, ent in cache.items():
        if key == serving_key:
            continue
        lat, lon = ent.get("lat"), ent.get("lon")
        if lat is None or lon is None:
            continue
        try:
            px, py = _ll_to_px(lat, lon, dev_lat, dev_lon, range_nm,
                               canvas.pw, canvas.ph)
        except Exception:
            continue
        _draw_marker(scr, map_y, map_x, map_w, map_h, px, py, "▫", dim)

    # Serving tower — colored by RSRP severity.
    if geo:
        sev = rsrp_severity(cell.get("rsrp") if cell else None)
        try:
            px, py = _ll_to_px(geo["lat"], geo["lon"], dev_lat, dev_lon,
                               range_nm, canvas.pw, canvas.ph)
            _draw_marker(scr, map_y, map_x, map_w, map_h, px, py, "▲",
                         _sev_attr(sev))
        except Exception:
            pass

    # Device marker.
    try:
        px, py = _ll_to_px(dev_lat, dev_lon, dev_lat, dev_lon, range_nm,
                           canvas.pw, canvas.ph)
        _draw_marker(scr, map_y, map_x, map_w, map_h, px, py, "◉",
                     curses.color_pair(tui.C_OK) | curses.A_BOLD)
    except Exception:
        pass

    _draw_sidebar(scr, state, sidebar_only=False)

    foot = "  ▲ tower  ◉ you  ▫ seen     q Back"
    tui.put(scr, h - 1, 1, foot, w - 2, curses.color_pair(tui.C_FOOTER))
    scr.refresh()


def _draw_sidebar(scr, state, sidebar_only):
    """Top-left/overlay text block: operator, cell IDs, signal, tower, dist."""
    h, w = scr.getmaxyx()
    dim = curses.color_pair(tui.C_DIM)
    item = curses.color_pair(tui.C_ITEM)
    hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD

    cell = state["cell"]
    geo = state["geo"]
    dev_lat, dev_lon = state["dev_lat"], state["dev_lon"]

    lines = []
    if not cell:
        lines.append(("no serving cell — searching…", _sev_attr("warn")))
    else:
        op = _operator_name(cell["mccmnc"])
        lines.append((f"{op}  band {cell['band']}", hdr))
        lines.append((f"ECI {cell['cid']} (eNB {cell['enb']}/{cell['sector']})",
                      item))
        lines.append((f"PCI {cell['pci']}  TAC {cell['lac']}", dim))
        rsrp = cell.get("rsrp")
        rsrq = cell.get("rsrq")
        snr = cell.get("snr")
        sig = f"RSRP {_fmt(rsrp,' dBm')}  RSRQ {_fmt(rsrq,' dB')}  SNR {_fmt(snr)}"
        lines.append((sig, _sev_attr(rsrp_severity(rsrp))))
        if geo:
            loc_bits = [b for b in (geo.get("city"), geo.get("region"),
                                    geo.get("country")) if b]
            loc_s = ", ".join(loc_bits) if loc_bits else "located"
            src = geo.get("source") or "?"
            lines.append((f"tower: {loc_s} [{src}]", dim))
            if dev_lat is not None:
                d = _distance_km(dev_lat, dev_lon, geo["lat"], geo["lon"])
                lines.append((f"distance: {d:.2f} km", item))
        else:
            lines.append(("tower location unavailable "
                          "(no internet / API limit)", _sev_attr("warn", False)))

    # Right-aligned overlay block when a map is present; top block otherwise.
    box_w = max((len(s) for s, _ in lines), default=0) + 2
    if sidebar_only:
        y0, x0 = 2, 2
    else:
        y0 = 1
        x0 = max(1, w - box_w - 1)
    for i, (s, attr) in enumerate(lines):
        yy = y0 + i
        if yy >= h - 1:
            break
        tui.put(scr, yy, x0, s, min(len(s), w - x0 - 1), attr)


def _fmt(v, suffix=""):
    return "--" if v is None else f"{v:.0f}{suffix}"


def _operator_name(mccmnc):
    return {
        "310260": "T-Mobile US", "310410": "AT&T", "311480": "Verizon",
        "310120": "Sprint",
    }.get(mccmnc, mccmnc)


# ── Screen loop ─────────────────────────────────────────────────────────
def run_cellular_map(scr):
    """Live cellular serving-tower map (SIM7600G-H)."""
    js = open_gamepad()
    try:
        tui.init_gauge_colors()
    except Exception:
        pass

    idx = _find_modem_index()
    if idx is None:
        try:
            while True:
                _draw_no_modem(scr)
                scr.timeout(1000)
                key, gp = _tui_input_loop(scr, js)
                if key in (ord("q"), ord("Q"), 27) or gp == "back":
                    break
        finally:
            if js:
                js.close()
            scr.timeout(100)
        return

    # Warm the basemaps once (best-effort) so the first frame has detail.
    try:
        _load_global_basemap()
    except Exception:
        pass

    cache = load_tower_cache()
    state = {
        "cell": None, "geo": None,
        "dev_lat": None, "dev_lon": None, "dev_src": None,
        "range_nm": RANGE_NM_DEFAULT, "cache": cache,
    }
    frame = 0
    scr.timeout(1000)
    try:
        while True:
            try:
                if frame % POLL_FRAMES == 0:
                    cell = parse_cpsi(_read_cpsi())
                    state["cell"] = cell
                    if cell:
                        geo = geolocate_cell(
                            cell["mccmnc"], cell["lac"], cell["cid"],
                            mcc=cell["mcc"], mnc=cell["mnc"], cache=cache)
                        state["geo"] = geo
                        upsert_serving(cache, cell, geo)
                        save_tower_cache(cache)
                        # Pre-load hires basemap near the device if we have one.
                        d_lat, d_lon, d_src = device_location(idx, geo)
                        state["dev_lat"] = d_lat
                        state["dev_lon"] = d_lon
                        state["dev_src"] = d_src
                        if d_lat is not None:
                            try:
                                _load_hires_basemap(d_lat, d_lon)
                            except Exception:
                                pass
                    else:
                        state["geo"] = None
                        d_lat, d_lon, d_src = device_location(idx, None)
                        state["dev_lat"] = d_lat
                        state["dev_lon"] = d_lon
                        state["dev_src"] = d_src
                _draw_map(scr, state)
            except Exception:
                pass

            scr.timeout(1000)
            key, gp = _tui_input_loop(scr, js)
            if key in (ord("q"), ord("Q"), 27) or gp == "back":
                break
            frame += 1
    finally:
        if js:
            js.close()
        scr.timeout(100)


HANDLERS = {"_cellular_map": run_cellular_map}
