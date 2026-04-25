#!/usr/bin/env python3
"""Generate dummy war-drive CSV data for UI testing.

Simulates a walking path with WiFi APs scattered along the route.
Use for testing the webdash map and TUI map view indoors.

Modes:
    --static [minutes]    Write a complete session CSV (default 8 min path).
    --live [minutes]      Append rows in real time at ~1 Hz to simulate a
                          session in progress; webdash live view will
                          pick up new points on each poll.
    --clean               Remove demo CSVs from the log dir.

Center the walk around your current GPS fix if available, else NYC.
"""

import argparse
import math
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone


LOG_DIR = os.path.expanduser("~/esp32/marauder-logs")
DEMO_PREFIX = "wardrive-DEMO-"


ESSID_POOL = [
    "Spectrum_3f21", "Verizon_8A2B1C", "ATTu6RdbYs", "NETGEAR42",
    "Starbucks WiFi", "TMOBILE-6C30", "dlink-AB12", "xfinitywifi",
    "MySpectrumWiFi-5G", "eero", "BellCanada9988", "TP-Link_4821",
    "SpectrumSetup-83", "Verizon_KQH7CT", "Linksys00042", "NYC_Free_WiFi",
    "Starlink-42", "HomeBase_2.4G", "HomeBase_5G", "CapitalOne_cafe",
    "PrettyFly_WiFi", "Not your iPhone", "FBI Surveillance Van",
    "SurveillanceVan", "(hidden)", "Gotham4411", "cloudrouter",
    "LaGuardia_Guest", "SubwayFree", "PublicWiFi_NYC", "DroppedPacketsInc",
    "TellMyWifiLoveHer", "LANdlordOfTheFlies", "GetOffMyLAN", "IDontKnow",
    "Router? I barely knew her", "The LAN Before Time", "Skynet",
    "Pretty Fly for a Wi-Fi", "It Hurts When IP", "404_NetworkUnavailable",
]


def get_current_position():
    """Try to read current lat/lon from gpsd; fall back to NYC."""
    try:
        out = subprocess.run(
            ["gpspipe", "-w", "-n", "10", "-x", "3"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        import json as _json
        for line in out.splitlines():
            try:
                d = _json.loads(line)
            except Exception:
                continue
            if d.get("class") == "TPV" and d.get("mode", 0) >= 2:
                lat = d.get("lat")
                lon = d.get("lon")
                if lat is not None and lon is not None:
                    return lat, lon, True
    except Exception:
        pass
    return 40.7128, -74.0060, False  # NYC City Hall fallback


def generate_walk_path(start_lat, start_lon, total_s, step_s=1.0):
    """Random-walk path with momentum. Returns list of (ts, lat, lon)."""
    M_PER_DEG_LAT = 111320.0
    lon_scale = math.cos(math.radians(start_lat))

    pts = []
    lat, lon = start_lat, start_lon
    # Walking speed ~1.3 m/s (human pace); segments ~2-8 m per sample
    bearing = random.uniform(0, 2 * math.pi)
    n = int(total_s / step_s)
    t0 = time.time() - total_s
    for i in range(n):
        # Occasionally turn
        if random.random() < 0.08:
            bearing += random.gauss(0, 0.7)
        elif random.random() < 0.4:
            bearing += random.gauss(0, 0.1)
        # Speed 1.0-1.8 m/s
        speed = random.uniform(1.0, 1.8)
        dist_m = speed * step_s
        dlat = (dist_m * math.cos(bearing)) / M_PER_DEG_LAT
        dlon = (dist_m * math.sin(bearing)) / (M_PER_DEG_LAT * lon_scale)
        lat += dlat
        lon += dlon
        pts.append((t0 + i * step_s, lat, lon, speed, bearing))
    return pts


def scatter_aps(path, density=0.08, max_offset_m=25):
    """Place APs at random offsets from random path points."""
    M_PER_DEG_LAT = 111320.0
    aps = []
    rng = random.Random()
    ap_count = max(20, int(len(path) * density * len(ESSID_POOL) / 40))
    used_bssids = set()
    used_essids = set()
    for _ in range(ap_count):
        anchor = rng.choice(path)
        lat, lon = anchor[1], anchor[2]
        lon_scale = math.cos(math.radians(lat))
        # Random offset within max_offset_m
        off_m = rng.uniform(0, max_offset_m)
        theta = rng.uniform(0, 2 * math.pi)
        dlat = (off_m * math.cos(theta)) / M_PER_DEG_LAT
        dlon = (off_m * math.sin(theta)) / (M_PER_DEG_LAT * lon_scale)
        ap_lat = lat + dlat
        ap_lon = lon + dlon
        # Unique BSSID
        while True:
            b = ":".join(f"{rng.randint(0, 255):02x}" for _ in range(6))
            if b not in used_bssids:
                break
        used_bssids.add(b)
        essid = rng.choice(ESSID_POOL)
        if essid in used_essids and essid != "(hidden)":
            essid = f"{essid}_{rng.randint(10, 99)}"
        used_essids.add(essid)
        aps.append({
            "bssid": b,
            "essid": essid,
            "channel": rng.choice([1, 1, 6, 6, 6, 11, 11, 36, 44, 149]),
            "lat": ap_lat,
            "lon": ap_lon,
            "tx_dbm": rng.uniform(17, 22),  # typical AP Tx power
        })
    return aps


def compute_rssi(ap, observer_lat, observer_lon):
    """Free-space-ish RSSI approximation with multipath jitter."""
    M_PER_DEG_LAT = 111320.0
    lon_scale = math.cos(math.radians(observer_lat))
    dlat_m = (ap["lat"] - observer_lat) * M_PER_DEG_LAT
    dlon_m = (ap["lon"] - observer_lon) * M_PER_DEG_LAT * lon_scale
    dist_m = max(1.0, math.sqrt(dlat_m ** 2 + dlon_m ** 2))
    # log-distance path loss
    rssi = ap["tx_dbm"] - 40 - 25 * math.log10(dist_m)
    rssi += random.gauss(0, 3.5)  # multipath
    return max(-92, min(-25, int(rssi)))


def simulate_sightings(path, aps, horizon_m=120, per_step_rate=0.6):
    """For each path point, yield sighting rows for nearby APs."""
    M_PER_DEG_LAT = 111320.0
    for ts, lat, lon, speed, _bearing in path:
        lon_scale = math.cos(math.radians(lat))
        for ap in aps:
            dlat_m = (ap["lat"] - lat) * M_PER_DEG_LAT
            dlon_m = (ap["lon"] - lon) * M_PER_DEG_LAT * lon_scale
            dist_m = math.sqrt(dlat_m ** 2 + dlon_m ** 2)
            if dist_m > horizon_m:
                continue
            # Stronger APs more likely to be seen each scan
            p = per_step_rate * math.exp(-dist_m / 60)
            if random.random() > p:
                continue
            rssi = compute_rssi(ap, lat, lon)
            yield {
                "ts": ts, "lat": lat, "lon": lon, "speed": speed,
                "ap": ap, "rssi": rssi,
            }


def write_csv_header(f):
    f.write("timestamp_iso,bssid,essid,channel,rssi,"
            "lat,lon,altitude,speed,gps_mode,sats_used,first_seen\n")


def write_row(f, sighting, first_seen):
    ts_iso = datetime.fromtimestamp(
        sighting["ts"], tz=timezone.utc).isoformat(timespec="seconds")
    ap = sighting["ap"]
    essid = ap["essid"]
    if "," in essid or '"' in essid:
        essid = '"' + essid.replace('"', '""') + '"'
    row = ",".join([
        ts_iso, ap["bssid"], essid, str(ap["channel"]),
        str(sighting["rssi"]),
        f"{sighting['lat']:.6f}", f"{sighting['lon']:.6f}",
        "42.0", f"{sighting['speed']:.2f}", "3", "8",
        "1" if first_seen else "0",
    ])
    f.write(row + "\n")


def cmd_static(minutes):
    total_s = int(minutes * 60)
    lat0, lon0, live = get_current_position()
    print(f"Center: {lat0:.5f},{lon0:.5f}  (gps fix: {live})")
    path = generate_walk_path(lat0, lon0, total_s)
    aps = scatter_aps(path)
    print(f"Path points: {len(path)}   Planted APs: {len(aps)}")

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path_csv = os.path.join(LOG_DIR, f"{DEMO_PREFIX}{stamp}.csv")
    seen = set()
    count = 0
    with open(path_csv, "w") as f:
        write_csv_header(f)
        for s in simulate_sightings(path, aps):
            first = s["ap"]["bssid"] not in seen
            seen.add(s["ap"]["bssid"])
            write_row(f, s, first)
            count += 1
    print(f"Wrote {count} sightings ({len(seen)} unique APs) to {path_csv}")


def cmd_live(minutes):
    """Write rows in real time at ~1 Hz. Use for testing live UI."""
    total_s = int(minutes * 60)
    lat0, lon0, live = get_current_position()
    print(f"Center: {lat0:.5f},{lon0:.5f}  (gps fix: {live})")
    path = generate_walk_path(lat0, lon0, total_s, step_s=1.0)
    aps = scatter_aps(path)
    print(f"Planned: {len(path)}s walk, {len(aps)} APs in area.")

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path_csv = os.path.join(LOG_DIR, f"{DEMO_PREFIX}{stamp}.csv")
    print(f"Writing live to: {path_csv}")
    print("Open https://uconsole.local/wardrive in a browser.")
    print("Ctrl+C to stop early.\n")

    seen = set()
    emitted = 0
    t_start = time.time()
    try:
        with open(path_csv, "w", buffering=1) as f:
            write_csv_header(f)
            for i, step in enumerate(path):
                ts_real, lat, lon, speed, _ = step
                now = time.time()
                # Rewrite timestamp to "now" for live feel
                step_live = (now, lat, lon, speed, 0)
                # Build sightings for this single step only
                step_aps = simulate_sightings([step_live], aps,
                                              horizon_m=120, per_step_rate=0.75)
                step_count = 0
                for s in step_aps:
                    first = s["ap"]["bssid"] not in seen
                    seen.add(s["ap"]["bssid"])
                    write_row(f, s, first)
                    step_count += 1
                    emitted += 1
                print(f"\r[{i + 1:4d}/{len(path)}] "
                      f"{step_count:2d} sightings  "
                      f"{len(seen):3d} unique APs  "
                      f"{emitted} rows    ",
                      end="", flush=True)
                # Sleep until next simulated second
                target = t_start + (i + 1)
                delay = target - time.time()
                if delay > 0:
                    time.sleep(delay)
    except KeyboardInterrupt:
        print("\n-- interrupted --")
    print(f"\nDone. {emitted} rows, {len(seen)} APs. File: {path_csv}")


def cmd_clean():
    n = 0
    try:
        for fn in os.listdir(LOG_DIR):
            if fn.startswith(DEMO_PREFIX):
                os.unlink(os.path.join(LOG_DIR, fn))
                n += 1
    except FileNotFoundError:
        pass
    print(f"Removed {n} demo file(s).")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("static", help="Write one complete demo CSV")
    s.add_argument("minutes", type=float, nargs="?", default=8.0)
    l = sub.add_parser("live", help="Append rows in real time (~1 Hz)")
    l.add_argument("minutes", type=float, nargs="?", default=5.0)
    sub.add_parser("clean", help="Remove demo CSV files")
    args = ap.parse_args()

    if args.mode == "static":
        cmd_static(args.minutes)
    elif args.mode == "live":
        cmd_live(args.minutes)
    elif args.mode == "clean":
        cmd_clean()


if __name__ == "__main__":
    main()
