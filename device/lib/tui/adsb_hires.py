"""ADS-B hi-res basemap fetcher.

Background-thread download of Natural Earth 1:10m vector data, clipped to a
bounding box around the user's home coordinates and cached on disk. Non-blocking
to the live-map render loop.
"""

import json
import math
import os
import threading
import urllib.request

NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"

LAYER_SOURCES = {
    "coastlines": (f"{NE_BASE}/ne_10m_coastline.geojson",                        "lines"),
    "countries":  (f"{NE_BASE}/ne_10m_admin_0_boundary_lines_land.geojson",      "lines"),
    "states":     (f"{NE_BASE}/ne_10m_admin_1_states_provinces_lines.geojson",   "lines"),
    "lakes":      (f"{NE_BASE}/ne_10m_lakes.geojson",                            "polys"),
    "rivers":     (f"{NE_BASE}/ne_10m_rivers_lake_centerlines.geojson",          "lines"),
    "airports":   (f"{NE_BASE}/ne_10m_airports.geojson",                         "airports"),
}

CACHE_DIR = os.path.expanduser("~/.config/uconsole")
BBOX_PAD_LAT = 5.0  # degrees
BBOX_PAD_LON = 7.0


def _hires_key(home_lat, home_lon):
    return f"{int(round(home_lat))}_{int(round(home_lon))}"


def cache_path_for(home_lat, home_lon):
    return os.path.join(CACHE_DIR, f"adsb_basemap_hires_{_hires_key(home_lat, home_lon)}.json")


def _bbox(home_lat, home_lon):
    return (home_lat - BBOX_PAD_LAT, home_lat + BBOX_PAD_LAT,
            home_lon - BBOX_PAD_LON, home_lon + BBOX_PAD_LON)


def _line_intersects_bbox(coords, bbox):
    lat_min, lat_max, lon_min, lon_max = bbox
    for lon, lat in coords:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


def _clip_lines(geojson, bbox):
    """Extract line segments inside bbox from LineString/MultiLineString features."""
    out = []
    for feat in geojson.get("features", []):
        g = feat.get("geometry") or {}
        gtype = g.get("type")
        coords_list = []
        if gtype == "LineString":
            coords_list = [g["coordinates"]]
        elif gtype == "MultiLineString":
            coords_list = g["coordinates"]
        for coords in coords_list:
            if not coords:
                continue
            if _line_intersects_bbox(coords, bbox):
                out.append([[round(p[0], 4), round(p[1], 4)] for p in coords])
    return out


def _clip_polys_as_lines(geojson, bbox):
    """Extract polygon outlines (lakes) as line segments."""
    out = []
    for feat in geojson.get("features", []):
        g = feat.get("geometry") or {}
        gtype = g.get("type")
        polys = []
        if gtype == "Polygon":
            polys = [g["coordinates"]]
        elif gtype == "MultiPolygon":
            polys = g["coordinates"]
        for poly in polys:
            for ring in poly:
                if _line_intersects_bbox(ring, bbox):
                    out.append([[round(p[0], 4), round(p[1], 4)] for p in ring])
    return out


def _clip_airports(geojson, bbox):
    lat_min, lat_max, lon_min, lon_max = bbox
    out = []
    for feat in geojson.get("features", []):
        g = feat.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"]
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            continue
        props = feat.get("properties", {})
        iata = (props.get("iata_code") or props.get("abbrev") or "").upper()
        if not iata or len(iata) > 4:
            continue
        out.append({
            "code": iata,
            "name": props.get("name") or "",
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "rank": props.get("scalerank", 9),
        })
    return out


def _fetch_url(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_worker(home_lat, home_lon, state):
    """Runs in a daemon thread. Updates state dict in place."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        bbox = _bbox(home_lat, home_lon)
        bundle = {"version": 1, "schema": "uconsole-adsb-basemap", "layers": {}}
        for layer, (url, kind) in LAYER_SOURCES.items():
            state["msg"] = f"fetching {layer}…"
            data = _fetch_url(url)
            if kind == "lines":
                bundle["layers"][layer] = _clip_lines(data, bbox)
            elif kind == "polys":
                bundle["layers"][layer] = _clip_polys_as_lines(data, bbox)
            elif kind == "airports":
                bundle["layers"][layer] = _clip_airports(data, bbox)
        # atomic write
        out_path = cache_path_for(home_lat, home_lon)
        tmp_path = out_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(bundle, f, separators=(",", ":"))
        os.replace(tmp_path, out_path)
        state["status"] = "ok"
        state["msg"] = f"cached {os.path.basename(out_path)}"
        state["banner_dismissed"] = False
        state["_invalidate"] = True
    except Exception as e:
        state["status"] = "error"
        state["msg"] = str(e)[:80]
        state["banner_dismissed"] = False


def start_fetch(home_lat, home_lon, state):
    """Kick off a background fetch. Idempotent — does nothing if one is running."""
    if state.get("status") == "running":
        return
    state["status"] = "running"
    state["msg"] = "starting…"
    state["banner_dismissed"] = False
    t = threading.Thread(target=_fetch_worker, args=(home_lat, home_lon, state), daemon=True)
    t.start()


def poll_fetch_state(state, home_lat, home_lon, basemap_singleton):
    """Called from the live-map render loop. Invalidates basemap cache when fetch finishes."""
    if state.get("_invalidate"):
        basemap_singleton["hires"] = None
        basemap_singleton["hires_key"] = None
        state["_invalidate"] = False


def cache_exists(home_lat, home_lon):
    return os.path.exists(cache_path_for(home_lat, home_lon))
