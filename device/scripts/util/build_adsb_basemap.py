#!/usr/bin/env python3
"""Build the bundled ADS-B global basemap.

Downloads Natural Earth source data from the nvkelso/natural-earth-vector GitHub
mirror, simplifies coastlines, filters airports to major ones, and writes a
compact JSON file under device/lib/tui/adsb_basemap_global.json.

Re-run this whenever you want to update or tweak the bundled basemap.
"""

import json
import math
import os
import sys
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(REPO_ROOT, "device", "lib", "tui", "adsb_basemap_global.json")
NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"

SOURCES = {
    "coastline": f"{NE_BASE}/ne_50m_coastline.geojson",
    "airports":  f"{NE_BASE}/ne_10m_airports.geojson",
}

# Simplification tolerance (degrees). 0.05 ≈ 5.5 km — coarse enough to keep
# the bundle small but still recognizable at 50 nm zoom.
SIMPLIFY_EPS = 0.15

# Airport filter: only keep "major" / "mil" / "spaceport" types with scalerank low
AIRPORT_TYPES_KEEP = {"major", "mil", "mil/major", "military major"}
AIRPORT_SCALERANK_MAX = 4  # NE scalerank: 0=biggest, 9=tiniest


def fetch(url, cache_dir="/tmp"):
    name = os.path.basename(url)
    cache = os.path.join(cache_dir, name)
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        print(f"  using cached {cache}")
        return cache
    print(f"  fetching {url}")
    urllib.request.urlretrieve(url, cache)
    return cache


def simplify_line(coords, eps):
    """Drop points closer than eps degrees to the previous kept point."""
    if not coords:
        return []
    out = [coords[0]]
    for p in coords[1:]:
        last = out[-1]
        if abs(p[0] - last[0]) > eps or abs(p[1] - last[1]) > eps:
            out.append(p)
    if len(out) < 2:
        return []
    return out


def round_pts(line, decimals=3):
    return [[round(p[0], decimals), round(p[1], decimals)] for p in line]


def collect_lines(geojson, eps):
    out = []
    for feat in geojson["features"]:
        g = feat["geometry"]
        if g["type"] == "LineString":
            line = simplify_line(g["coordinates"], eps)
            if line:
                out.append(round_pts(line))
        elif g["type"] == "MultiLineString":
            for part in g["coordinates"]:
                line = simplify_line(part, eps)
                if line:
                    out.append(round_pts(line))
    return out


def collect_airports(geojson):
    out = []
    for feat in geojson["features"]:
        props = feat.get("properties", {})
        atype = (props.get("type") or "").lower()
        scalerank = props.get("scalerank", 99)
        if atype not in AIRPORT_TYPES_KEEP and scalerank > AIRPORT_SCALERANK_MAX:
            continue
        iata = props.get("iata_code") or props.get("abbrev") or ""
        name = props.get("name") or ""
        coords = feat["geometry"]["coordinates"]
        if not iata or len(iata) > 4:
            continue
        out.append({
            "code": iata.upper(),
            "name": name,
            "lat": round(coords[1], 4),
            "lon": round(coords[0], 4),
            "rank": scalerank,
        })
    # Dedup by IATA
    seen = {}
    for ap in out:
        if ap["code"] not in seen or ap["rank"] < seen[ap["code"]]["rank"]:
            seen[ap["code"]] = ap
    return sorted(seen.values(), key=lambda a: a["rank"])


def main():
    print("== ADS-B basemap builder ==")
    print(f"out: {OUT_PATH}")

    print("[1/3] fetching sources")
    coast_path = fetch(SOURCES["coastline"])
    apt_path = fetch(SOURCES["airports"])

    print("[2/3] processing")
    with open(coast_path) as f:
        coast = json.load(f)
    coastlines = collect_lines(coast, SIMPLIFY_EPS)
    coast_pts = sum(len(c) for c in coastlines)
    print(f"  coastlines: {len(coastlines)} segments, {coast_pts} points")

    with open(apt_path) as f:
        apt = json.load(f)
    airports = collect_airports(apt)
    print(f"  airports: {len(airports)} (filtered by type/scalerank)")

    bundle = {
        "version": 1,
        "schema": "uconsole-adsb-basemap",
        "layers": {
            "coastlines": coastlines,
            "airports": airports,
        },
    }

    print("[3/3] writing")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(bundle, f, separators=(",", ":"))
    size = os.path.getsize(OUT_PATH)
    print(f"  wrote {OUT_PATH}: {size} bytes ({size/1024:.1f} KB)")
    if size > 500_000:
        print(f"  WARNING: bundle exceeds 500 KB target — consider raising SIMPLIFY_EPS")
        sys.exit(1)


if __name__ == "__main__":
    main()
