"""TUI module: battery_lib — pure battery/power logic (no curses).

Live AXP228 telemetry, the ``battery.*`` config schema with safe defaults,
build-profile presets, hard safety clamps, and the udev-rule generator used by
the privileged applier.  Kept curses-free so it is unit-testable and runnable
standalone (``python3 battery_lib.py`` prints live telemetry + the composed
Power/Battery screen for this device).

Phase 1 scope: telemetry (A), build profile (B), charge (C), discharge
protection (D).  Performance (E) and advanced (F) rows are shown disabled.
"""

import glob
import os

try:
    from tui.framework import load_config, save_config_multi
except Exception:  # standalone / test mode
    load_config = None
    save_config_multi = None

PSY = "/sys/class/power_supply"
BAT = os.path.join(PSY, "axp20x-battery")
AC = os.path.join(PSY, "axp22x-ac")

# ── Safety clamps (mirrored in the applier — never trust the config blindly) ──
CLAMP = {
    "charge_current_ma": (300, 2000),   # AXP HW max 2100; we cap at 2000
    "shutdown_mv": (3000, 3700),        # per-cell resting; never below 3.0 V
    "warn_mv": (3100, 3900),
    "voff_mv": (3000, 3300),            # voltage_min: gauge ref, clamp >= 3.0 V
    "capacity_mah": (500, 20000),
}
CHARGE_LIMITS = (4100, 4200)            # voltage_max: kernel allows only these

# ── Build-profile presets (per-cell millivolts) ──
PROFILES = {
    "18650":   {"chemistry": "liion", "cells": 1, "charge_limit_mv": 4200,
                "shutdown_mv": 3450, "warn_mv": 3600, "charge_current_ma": 900},
    "lipo_1s": {"chemistry": "lipo",  "cells": 1, "charge_limit_mv": 4200,
                "shutdown_mv": 3400, "warn_mv": 3550, "charge_current_ma": 900},
    "li_2s":   {"chemistry": "liion", "cells": 2, "charge_limit_mv": 4200,
                "shutdown_mv": 3400, "warn_mv": 3550, "charge_current_ma": 900},
    "custom":  {},
}
PROFILE_LABELS = {"18650": "18650", "lipo_1s": "1S LiPo",
                  "li_2s": "2S 21700", "custom": "Custom"}

DEFAULTS = {
    "profile": "custom",
    "chemistry": "lipo",
    "cells": 1,
    "capacity_mah": 3500,
    "voltage_display": "per_cell",
    "charge_limit_mv": 4200,
    "charge_current_ma": 900,
    "warn_mv": 3550,
    "shutdown_mv": 3400,
    "monitor_poll_s": 30,
    "power_profile": "balanced",
    "voff_mv": None,
}


# ── sysfs helpers ──
def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def _read_int(path):
    v = _read(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def read_telemetry():
    """Live AXP228 battery state. Returns a dict; missing fields are None."""
    uv = _read_int(os.path.join(BAT, "voltage_now"))      # microvolts
    ua = _read_int(os.path.join(BAT, "current_now"))      # microamps
    uw = _read_int(os.path.join(BAT, "power_now"))        # microwatts
    cap = _read_int(os.path.join(BAT, "capacity"))
    status = _read(os.path.join(BAT, "status")) or "Unknown"
    ac_online = _read(os.path.join(AC, "online"))
    v = uv / 1e6 if uv is not None else None
    a = ua / 1e6 if ua is not None else None
    w = uw / 1e6 if uw is not None else (abs(v * a) if v and a else None)
    return {
        "voltage": v,
        "current": a,
        "power": w,
        "capacity": cap,
        "status": status,
        "on_ac": ac_online == "1",
        "voltage_max": (_read_int(os.path.join(BAT, "voltage_max")) or 0) / 1e6 or None,
        "voltage_min": (_read_int(os.path.join(BAT, "voltage_min")) or 0) / 1e6 or None,
        "charge_current_ma": (_read_int(os.path.join(BAT, "constant_charge_current")) or 0) // 1000 or None,
    }


# ── config load + clamps ──
def _clamp(key, val):
    lo, hi = CLAMP[key]
    return max(lo, min(hi, int(val)))


def load_battery_cfg():
    """Merge DEFAULTS with the user's ``battery.*`` block from console.json."""
    cfg = dict(DEFAULTS)
    if load_config is not None:
        user = (load_config() or {}).get("battery", {})
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
    return cfg


def apply_profile(cfg, name):
    """Return cfg with a profile's presets applied (Custom leaves values as-is)."""
    out = dict(cfg)
    out["profile"] = name
    out.update(PROFILES.get(name, {}))
    return out


def save_battery_cfg(cfg):
    """Persist clamped battery.* back to console.json (no-op in standalone mode)."""
    safe = dict(cfg)
    for key in ("charge_current_ma", "shutdown_mv", "warn_mv", "capacity_mah"):
        if safe.get(key) is not None:
            safe[key] = _clamp(key, safe[key])
    if safe.get("voff_mv") is not None:
        safe["voff_mv"] = _clamp("voff_mv", safe["voff_mv"])
    if safe.get("charge_limit_mv") not in CHARGE_LIMITS:
        safe["charge_limit_mv"] = 4200
    if save_config_multi is not None:
        save_config_multi({"battery": safe})
    return safe


# ── applier backend: turn config into the udev rule (dry-run safe) ──
def gen_udev_rule(cfg):
    """Generate the persistent 99-uconsole-battery.rules content from config.

    Uses sysfs ATTR writes only — never raw i2cset (those don't persist and
    bypass the kernel's 4.2 V / current guards).
    """
    cur_ua = _clamp("charge_current_ma", cfg["charge_current_ma"]) * 1000
    vmax_uv = (cfg["charge_limit_mv"] if cfg["charge_limit_mv"] in CHARGE_LIMITS
               else 4200) * 1000
    parts = [
        'KERNEL=="axp20x-battery"',
        'ATTR{constant_charge_current_max}="%d"' % cur_ua,
        'ATTR{constant_charge_current}="%d"' % cur_ua,
        'ATTR{voltage_max}="%d"' % vmax_uv,
    ]
    if cfg.get("voff_mv") is not None:
        parts.append('ATTR{voltage_min}="%d"' % (_clamp("voff_mv", cfg["voff_mv"]) * 1000))
    return ", ".join(parts) + "\n"


# ── screen composition (pure → reused by curses draw + the text demo) ──
def _fmt_v(mv, cells):
    return "%.2f V" % (mv / 1000.0 * cells)


def compose_screen(cfg, tele, width=46):
    """Return the Power/Battery screen as a list of (text, kind) rows.

    kind ∈ {head, cat, row, ro, adv, note} — the curses layer maps kind→color;
    the text demo prints them plainly.
    """
    cells = cfg["cells"]
    L = []
    L.append(("POWER / BATTERY", "head"))

    # A — telemetry
    L.append(("A · TELEMETRY", "cat"))
    v = tele["voltage"]
    pc = (v / cells) if v else None
    L.append(("  voltage        %s%s" % (
        "%.2f V" % v if v else "—",
        "  (%.2f/cell)" % pc if pc and cells > 1 else ""), "ro"))
    L.append(("  current        %s" % ("%+.2f A" % tele["current"] if tele["current"] is not None else "—"), "ro"))
    L.append(("  charge         %s%%  ·  %s  ·  %s" % (
        tele["capacity"] if tele["capacity"] is not None else "—",
        tele["status"],
        "%.1f W" % tele["power"] if tele["power"] else "—"), "ro"))

    # B — build profile
    L.append(("B · BUILD PROFILE", "cat"))
    L.append(("  Profile        %s" % PROFILE_LABELS.get(cfg["profile"], cfg["profile"]), "row"))
    L.append(("  Cells · Cap    %dS · %d mAh" % (cells, cfg["capacity_mah"]), "row"))

    # C — charge
    L.append(("C · CHARGE  (sysfs)", "cat"))
    lim = cfg["charge_limit_mv"]
    L.append(("  Charge limit   %s" % (
        "Longevity 4.1V  ★" if lim == 4100 else "Full 4.2V"), "row"))
    L.append(("  Max current    %d mA" % cfg["charge_current_ma"], "row"))

    # D — discharge protection
    L.append(("D · DISCHARGE PROTECTION", "cat"))
    L.append(("  Warn at        %s / cell %d mV" % (_fmt_v(cfg["warn_mv"], cells), cfg["warn_mv"]), "row"))
    L.append(("  Shutdown at    %s / cell %d mV" % (_fmt_v(cfg["shutdown_mv"], cells), cfg["shutdown_mv"]), "row"))

    # E/F — later phases (shown disabled)
    L.append(("E · PERFORMANCE / SAG", "cat"))
    L.append(("  Power profile  %s   (Phase 2)" % cfg["power_profile"], "ro"))
    L.append(("F · ADVANCED ⚠", "cat"))
    L.append(("  VOFF · recalibrate           (Phase 3)", "ro"))
    return L


# ── editable rows (Phase 1) — the curses layer drives these ──
def editable_rows():
    """Ordered list of (key, label, kind) the screen lets you change in P1."""
    return [
        ("profile", "Profile", "cycle"),
        ("capacity_mah", "Capacity mAh", "int"),
        ("charge_limit_mv", "Charge limit", "toggle"),
        ("charge_current_ma", "Max current", "int"),
        ("warn_mv", "Warn at", "int"),
        ("shutdown_mv", "Shutdown at", "int"),
    ]


def cycle_value(cfg, key):
    """Return cfg after cycling/toggling a value (used by Enter on a row)."""
    out = dict(cfg)
    if key == "profile":
        order = list(PROFILES.keys())
        nxt = order[(order.index(cfg["profile"]) + 1) % len(order)]
        out = apply_profile(out, nxt)
    elif key == "charge_limit_mv":
        out[key] = 4100 if cfg[key] == 4200 else 4200
        out["profile"] = "custom"
    return out


def bump_value(cfg, key, delta):
    """Return cfg after nudging an int field by delta (with clamp)."""
    out = dict(cfg)
    step = {"charge_current_ma": 150, "warn_mv": 50, "shutdown_mv": 50,
            "capacity_mah": 100}.get(key, 50)
    base = cfg.get(key) or 0
    val = base + delta * step
    if key in CLAMP:
        val = _clamp(key, val)
    out[key] = val
    if key != "capacity_mah":
        out["profile"] = "custom"
    return out


if __name__ == "__main__":
    # Standalone demo: live telemetry + composed screen for THIS device.
    tele = read_telemetry()
    cfg = load_battery_cfg()
    print("=== live AXP228 telemetry ===")
    for k, val in tele.items():
        print("  %-18s %s" % (k, val))
    print("\n=== composed Power/Battery screen ===")
    bar = "+" + "-" * 46 + "+"
    print(bar)
    for text, kind in compose_screen(cfg, tele):
        mark = {"head": "#", "cat": ">", "ro": " ", "row": "·", "adv": "!"}.get(kind, " ")
        print("| %s %-42s |" % (mark, text[:42]))
    print(bar)
    print("\n=== udev rule the applier would write (dry-run) ===")
    print(gen_udev_rule(cfg).strip())
