#!/usr/bin/env python3
"""One-shot cleaner: remove state-border line segments drawn over open water.

Uses Natural Earth 1:110m country polygons as a land mask. For each state
border line, splits into segments at water transitions, keeping only land
segments. Writes the cleaned bundle back in-place (backup saved as .bak).

Usage:
  clean-basemap-water.py                    # clean all hires bundles
  clean-basemap-water.py <bundle.json>      # clean one specific bundle
  clean-basemap-water.py --also-global      # also clean the global-lite basemap
"""
import glob
import json
import os
import shutil
import sys

COUNTRIES_FILE = "/tmp/ne110_countries.geojson"


def load_land_polygons(path):
    """Load country geometries as list of rings (each ring = [[lon,lat], ...])."""
    data = json.load(open(path))
    rings = []
    for feat in data.get("features", []):
        g = feat.get("geometry") or {}
        t = g.get("type")
        if t == "Polygon":
            rings.append(g["coordinates"][0])  # outer ring only
        elif t == "MultiPolygon":
            for poly in g["coordinates"]:
                rings.append(poly[0])  # outer ring
    return rings


def point_in_ring(pt, ring):
    """Ray-cast: is pt inside the closed ring? pt = [lon, lat]."""
    x, y = pt[0], pt[1]
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def point_on_land(pt, land_rings, bbox_cache):
    """True if pt is inside any land ring."""
    x, y = pt[0], pt[1]
    for i, ring in enumerate(land_rings):
        bb = bbox_cache[i]
        if not (bb[0] <= x <= bb[1] and bb[2] <= y <= bb[3]):
            continue
        if point_in_ring(pt, ring):
            return True
    return False


def clean_states(states, land_rings):
    """Split each state border line at water crossings; keep only land segments."""
    # Pre-compute bbox per ring for fast skip
    bbox_cache = []
    for ring in land_rings:
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        bbox_cache.append((min(xs), max(xs), min(ys), max(ys)))

    new_lines = []
    removed_segs = 0
    kept_segs = 0
    for line in states:
        if len(line) < 2:
            new_lines.append(line)
            continue
        current = [line[0]]
        for i in range(1, len(line)):
            a = line[i - 1]
            b = line[i]
            mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
            if point_on_land(mid, land_rings, bbox_cache):
                current.append(b)
                kept_segs += 1
            else:
                if len(current) >= 2:
                    new_lines.append(current)
                current = [b]
                removed_segs += 1
        if len(current) >= 2:
            new_lines.append(current)
    return new_lines, kept_segs, removed_segs


def clean_bundle(bundle_path, land_rings):
    data = json.load(open(bundle_path))
    states = data.get("layers", {}).get("states", [])
    n_orig = len(states)
    if n_orig == 0:
        print(f"  {bundle_path}: no states layer, skipping")
        return
    new_states, kept, removed = clean_states(states, land_rings)
    data["layers"]["states"] = new_states

    # Back up original once
    bak = bundle_path + ".bak"
    if not os.path.exists(bak):
        shutil.copy(bundle_path, bak)

    json.dump(data, open(bundle_path, "w"), separators=(',', ':'))
    size = os.path.getsize(bundle_path) / 1024
    print(f"  {bundle_path}: states {n_orig} → {len(new_states)} lines   "
          f"segments kept {kept}, dropped {removed}   size {size:.0f} KB")


def main():
    args = sys.argv[1:]
    also_global = "--also-global" in args
    args = [a for a in args if a != "--also-global"]

    print("Loading country polygons from 1:110m Natural Earth...")
    land_rings = load_land_polygons(COUNTRIES_FILE)
    print(f"  {len(land_rings)} country rings loaded")

    targets = []
    if args:
        targets.extend(args)
    else:
        # All hires bundles in user's cache
        targets.extend(glob.glob(os.path.expanduser(
            "~/.config/uconsole/adsb_basemap_hires_*.json")))
    if also_global:
        for p in ("/home/mikevitelli/uconsole-cloud/device/lib/tui/adsb_basemap_global.json",
                  "/opt/uconsole/lib/tui/adsb_basemap_global.json",
                  "/home/mikevitelli/pkg/lib/tui/adsb_basemap_global.json"):
            if os.path.exists(p):
                targets.append(p)

    if not targets:
        print("No bundles found to clean.")
        return 1
    print(f"\nCleaning {len(targets)} bundle(s):")
    for t in targets:
        clean_bundle(t, land_rings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
