"""TUI module: cellular signal monitor (SIMCom SIM7600G-H / 4G modem).

Live LTE signal view in the style of the antenna array monitor. Plots two
smoothed braille traces over time — RSRP (primary) and RSSI — with an
autoranged y-axis, plus a current numeric readout colored by severity.
Self-contained (own mmcli parsers) so a fault here can only ever hide this
one menu entry.

  q Back
"""
import curses
import math
import re
import subprocess
import time
from collections import deque

from tui.framework import _tui_input_loop, open_gamepad
import tui_lib as tui

DBM_FLOOR, DBM_CEIL = -125, -45
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ── Pure parsers / helpers ──────────────────────────────────────────────
def strip_ansi(text):
    return _ANSI.sub("", text or "")


def _fnum(text, pat):
    """Parse a float following `pat`; tolerate `--` / missing → None."""
    m = re.search(pat, text)
    if not m:
        return None
    raw = m.group(1)
    if raw.startswith("-") and not re.match(r"-?\d", raw):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_signal(text):
    """Parse `mmcli -m N --signal-get` LTE block.

    Lines look like:  rssi: -78.00 dBm / rsrq: -19.00 dB /
    rsrp: -115.00 dBm / s/n: -5.60 dB  (values may be `--`).
    """
    text = strip_ansi(text)
    return {
        "rssi": _fnum(text, r"rssi:\s*(-{2}|-?\d+(?:\.\d+)?)"),
        "rsrp": _fnum(text, r"rsrp:\s*(-{2}|-?\d+(?:\.\d+)?)"),
        "rsrq": _fnum(text, r"rsrq:\s*(-{2}|-?\d+(?:\.\d+)?)"),
        "snr":  _fnum(text, r"s/n:\s*(-{2}|-?\d+(?:\.\d+)?)"),
    }


def parse_info(text):
    """Parse header fields from `mmcli -m N`."""
    text = strip_ansi(text)
    out = {"operator": None, "tech": None, "quality": None}
    m = re.search(r"operator name:\s*(.+)", text)
    if m:
        out["operator"] = m.group(1).strip()
    m = re.search(r"access tech:\s*(.+)", text)
    if m:
        out["tech"] = m.group(1).strip()
    m = re.search(r"signal quality:\s*(\d+)\s*%", text)
    if m:
        out["quality"] = int(m.group(1))
    return out


def parse_modem_index(text):
    """First /Modem/N from `mmcli -L`; require SIM7600 if any line names it."""
    text = strip_ansi(text)
    best = None
    for m in re.finditer(r"/Modem/(\d+)\b(.*)", text):
        idx, rest = int(m.group(1)), m.group(2)
        if "SIM7600" in rest or "SIMCOM" in rest.upper():
            return idx
        if best is None:
            best = idx
    return best


def smooth(values, alpha=0.35):
    """Exponential moving average — tames per-poll jitter."""
    out, s = [], None
    for v in values:
        s = v if s is None else alpha * v + (1 - alpha) * s
        out.append(s)
    return out


def autorange(*series, pad=0.15, min_span=10.0):
    vals = [v for s in series for v in s]
    if not vals:
        return (-120.0, -60.0)
    lo, hi = min(vals), max(vals)
    if hi - lo < min_span:
        mid = (hi + lo) / 2
        lo, hi = mid - min_span / 2, mid + min_span / 2
    p = (hi - lo) * pad
    return (max(DBM_FLOOR, lo - p), min(DBM_CEIL, hi + p))


def _ribbon_rows(hist_p, hist_s, cw, ch, lo, hi):
    """Plot two traces (primary RSRP, secondary RSSI) as braille points."""
    c = tui.BrailleCanvas(cw, ch)
    dp, ds = list(hist_p)[-c.pw:], list(hist_s)[-c.pw:]

    def ym(v):
        if hi == lo:
            return c.ph // 2
        return max(0, min(c.ph - 1, round((hi - v) / (hi - lo) * (c.ph - 1))))

    for i, v in enumerate(dp):
        c.set(i, ym(v))
    for i, v in enumerate(ds):
        c.set(i, ym(v))
    return c.render()


# ── Severity ────────────────────────────────────────────────────────────
def rsrp_severity(v):
    if v >= -90:
        return "ok"
    if v >= -105:
        return "warn"
    return "bad"


def rsrq_severity(v):
    if v >= -10:
        return "ok"
    if v >= -15:
        return "warn"
    return "bad"


def snr_severity(v):
    if v >= 10:
        return "ok"
    if v >= 0:
        return "warn"
    return "bad"


def _sev_attr(sev, bold=True):
    pair = {"ok": tui.C_OK, "warn": tui.C_WARN, "bad": tui.C_CRIT}.get(sev, tui.C_DIM)
    a = curses.color_pair(pair)
    return a | curses.A_BOLD if bold else a


# ── Data gathering ──────────────────────────────────────────────────────
def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return ""


def find_modem():
    return parse_modem_index(_run(["mmcli", "-L"]))


def _fmt(v, suffix=""):
    return "--" if v is None else f"{v:.0f}{suffix}"


# ── Render ──────────────────────────────────────────────────────────────
def _draw_no_modem(scr):
    scr.erase()
    h, w = scr.getmaxyx()
    msg = "4G module not powered on — use Power On first"
    tui.put(scr, h // 2, max(1, (w - len(msg)) // 2), msg, w - 2,
            _sev_attr("warn"))
    tui.put(scr, h - 1, 1, "q Back", w - 2, curses.color_pair(tui.C_FOOTER))
    scr.refresh()


def _draw(scr, info, sig, ui):
    scr.erase()
    h, w = scr.getmaxyx()
    hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
    dim = curses.color_pair(tui.C_DIM)
    y = 0

    tui.put(scr, y, 1, "CELLULAR SIGNAL — SIM7600G-H / LTE", w - 2, hdr)
    y += 1
    op = info.get("operator") or "—"
    tech = (info.get("tech") or "—").upper()
    qual = info.get("quality")
    qual_s = f"{qual}%" if qual is not None else "--"
    tui.put(scr, y, 1, f"{op} · {tech} · {qual_s}", w - 2, dim)
    y += 2

    p, s = ui["hist_p"], ui["hist_s"]
    if len(p):
        sp = smooth(list(p))
        ss = smooth(list(s)) if len(s) else sp
        lo, hi = autorange(sp, ss)
        sev = rsrp_severity(sp[-1])
        cw = max(8, w - 9)
        rows = _ribbon_rows(sp, ss, cw, 4, lo, hi)
        n = len(rows)
        for i, r in enumerate(rows):
            tag = (f"{hi:>4.0f} ┤" if i == 0 else
                   f"{lo:>4.0f} ┤" if i == n - 1 else "     │")
            tui.put(scr, y, 0, f"{tag} {r}", w - 2, _sev_attr(sev, bold=False))
            y += 1
    else:
        tui.put(scr, y, 1, "collecting signal…", w - 2, dim)
        y += 1
    y += 1

    rsrp, rsrq, snr, rssi = (sig.get("rsrp"), sig.get("rsrq"),
                             sig.get("snr"), sig.get("rssi"))
    if rsrp is not None:
        tui.put(scr, y, 1, f"RSRP {_fmt(rsrp, ' dBm')}", w - 2,
                _sev_attr(rsrp_severity(rsrp)))
    else:
        tui.put(scr, y, 1, "RSRP --", w - 2, dim)
    y += 1
    if rsrq is not None:
        tui.put(scr, y, 1, f"RSRQ {_fmt(rsrq, ' dB')}", w - 2,
                _sev_attr(rsrq_severity(rsrq)))
    else:
        tui.put(scr, y, 1, "RSRQ --", w - 2, dim)
    y += 1
    if snr is not None:
        tui.put(scr, y, 1, f"SNR  {_fmt(snr, ' dB')}", w - 2,
                _sev_attr(snr_severity(snr)))
    else:
        tui.put(scr, y, 1, "SNR  --", w - 2, dim)
    y += 1
    tui.put(scr, y, 1, f"RSSI {_fmt(rssi, ' dBm')}", w - 2, dim)
    y += 1

    tui.put(scr, h - 1, 1, "q Back   h Help", w - 2, curses.color_pair(tui.C_FOOTER))
    scr.refresh()


def _draw_help(scr):
    """Reference guide for the LTE signal metrics (toggled with 'h')."""
    scr.erase()
    h, w = scr.getmaxyx()
    hdr = curses.color_pair(tui.C_CAT) | curses.A_BOLD
    dim = curses.color_pair(tui.C_DIM)
    ok = curses.color_pair(tui.C_OK)
    wn = curses.color_pair(tui.C_WARN)
    bad = curses.color_pair(tui.C_CRIT)
    state = {"y": 0}

    tui.put(scr, state["y"], 1, "CELLULAR SIGNAL — METRIC GUIDE", w - 2, hdr)
    state["y"] += 2

    def metric(name, full, desc, scale):
        if state["y"] >= h - 2:
            return
        tui.put(scr, state["y"], 1, f"{name}  {full}", w - 2, hdr)
        state["y"] += 1
        tui.put(scr, state["y"], 3, desc, w - 4, dim)
        state["y"] += 1
        x = 3
        for text, attr in scale:
            tui.put(scr, state["y"], x, text, len(text), attr)
            x += len(text)
        state["y"] += 2

    metric("RSRP", "Ref Signal Received Power (dBm)",
           "LTE reference-signal power — the main strength metric.",
           [("≥-90 good", ok), ("  -90..-105 fair", wn), ("  <-105 weak", bad)])
    metric("RSRQ", "Ref Signal Received Quality (dB)",
           "Quality = RSRP/RSSI; reflects interference & cell load.",
           [("≥-10 good", ok), ("  -10..-15 fair", wn), ("  <-15 poor", bad)])
    metric("SNR", "Signal-to-Noise Ratio (dB)",
           "Signal vs noise+interference — drives throughput.",
           [("≥10 good", ok), ("  0..10 fair", wn), ("  <0 poor", bad)])
    metric("RSSI", "Received Signal Strength Ind. (dBm)",
           "Total band power (signal+noise+interf); less precise for LTE.",
           [("reference only", dim)])

    tui.put(scr, h - 1, 1, "h/q close", w - 2, curses.color_pair(tui.C_FOOTER))
    scr.refresh()


def run_cellular_signal(scr):
    """Live LTE signal monitor (SIM7600G-H)."""
    js = open_gamepad()
    try:
        tui.init_gauge_colors()
    except Exception:
        pass

    idx = find_modem()
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

    # Enable signal polling (ignore errors).
    _run(["mmcli", "-m", str(idx), "--signal-setup=2"])

    ui = {"hist_p": deque(maxlen=200), "hist_s": deque(maxlen=200)}
    info = {"operator": None, "tech": None, "quality": None}
    sig = {"rssi": None, "rsrp": None, "rsrq": None, "snr": None}
    frame = 0
    show_help = False
    try:
        while True:
            try:
                if frame % 2 == 0:
                    info = parse_info(_run(["mmcli", "-m", str(idx)]))
                sig = parse_signal(_run(["mmcli", "-m", str(idx), "--signal-get"]))
                if sig.get("rsrp") is not None:
                    ui["hist_p"].append(sig["rsrp"])
                if sig.get("rssi") is not None:
                    ui["hist_s"].append(sig["rssi"])
                if show_help:
                    _draw_help(scr)
                else:
                    _draw(scr, info, sig, ui)
            except Exception:
                pass

            scr.timeout(1000)
            key, gp = _tui_input_loop(scr, js)
            if key in (ord("q"), ord("Q"), 27) or gp == "back":
                break
            if key in (ord("h"), ord("H")):
                show_help = not show_help
            frame += 1
    finally:
        if js:
            js.close()
        scr.timeout(100)


# ── Monitor-dashboard parsers ──────────────────────────────────────────
def parse_state(text):
    """`state:` from `mmcli -m N` (connected / registered / …)."""
    text = strip_ansi(text)
    m = re.search(r"^\s*\|\s*state:\s*(\S+)", text, re.M)
    if not m:
        m = re.search(r"\bstate:\s*(\S+)", text)
    return m.group(1).strip() if m else None


def parse_registration(text):
    """`registration:` from `mmcli -m N` (home / roaming / …)."""
    text = strip_ansi(text)
    m = re.search(r"registration:\s*(\S+)", text)
    return m.group(1).strip() if m else None


def parse_bearer_paths(text):
    """Every /Bearer/N referenced by `mmcli -m N`."""
    text = strip_ansi(text)
    return [int(n) for n in re.findall(r"/Bearer/(\d+)\b", text)]


def parse_bearer_conn(text):
    """Parse a connected bearer dump → APN / ip type / address / gateway.

    Scopes address+gateway to the IPv6 configuration block when present so
    we report the routable v6 address (matches wwan0)."""
    text = strip_ansi(text)
    out = {"connected": False, "apn": None, "ip_type": None,
           "address": None, "gateway": None}
    m = re.search(r"connected:\s*(\S+)", text)
    out["connected"] = bool(m and m.group(1).strip() == "yes")
    m = re.search(r"\bapn:\s*(.+)", text)
    if m:
        out["apn"] = m.group(1).strip()
    m = re.search(r"ip type:\s*(.+)", text)
    if m:
        out["ip_type"] = m.group(1).strip()
    # Prefer the IPv6 configuration block; fall back to first address/gateway.
    v6 = re.search(r"IPv6 configuration(.*?)(?:----|\Z)", text, re.S)
    scope = v6.group(1) if v6 else text
    m = re.search(r"address:\s*([0-9a-fA-F:.]+)", scope)
    if m:
        out["address"] = m.group(1).strip()
    m = re.search(r"gateway:\s*([0-9a-fA-F:.]+)", scope)
    if m:
        out["gateway"] = m.group(1).strip()
    return out


def find_connected_bearer(idx):
    """Return dict from the connected bearer of modem `idx`, or empty dict."""
    paths = parse_bearer_paths(_run(["mmcli", "-m", str(idx)]))
    for b in paths:
        info = parse_bearer_conn(_run(["mmcli", "-b", str(b)]))
        if info.get("connected") and info.get("address"):
            return info
    # Fall back to any connected bearer even without a v6 address.
    for b in paths:
        info = parse_bearer_conn(_run(["mmcli", "-b", str(b)]))
        if info.get("connected"):
            return info
    return {}


def _wwan_bytes(iface="wwan0"):
    """(rx_bytes, tx_bytes) for an interface; 0,0 if unreadable."""
    rx = tx = 0
    try:
        rx = int(open(f"/sys/class/net/{iface}/statistics/rx_bytes").read())
        tx = int(open(f"/sys/class/net/{iface}/statistics/tx_bytes").read())
    except Exception:
        pass
    return rx, tx


def _ping6(target, iface="wwan0"):
    """Single IPv6 ping → (ok, latency_ms). Blocks up to ~1s."""
    try:
        out = subprocess.run(
            ["ping6", "-c1", "-W1", "-I", iface, target],
            capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return (False, None)
    ok = "1 received" in out or " 0% packet loss" in out
    ms = None
    m = re.search(r"time=([\d.]+)\s*ms", out)
    if m:
        try:
            ms = float(m.group(1))
        except ValueError:
            ms = None
    return (ok, ms)


def _rsrp_to_pct(rsrp):
    """Map RSRP dBm (-120..-60) onto 0..100 for the area sparkline."""
    if rsrp is None:
        return 0
    return max(0, min(100, (rsrp - (-120)) / ((-60) - (-120)) * 100))


def run_cellular_monitor(scr):
    """Live 4G modem dashboard (SIM7600G-H) — system-monitor style."""
    js = open_gamepad()
    try:
        tui.init_gauge_colors()
    except Exception:
        pass

    idx = find_modem()
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

    # Enable periodic signal refresh once.
    _run(["mmcli", "-m", str(idx), "--signal-setup=2"])

    rsrp_h, rx_h, tx_h = tui.make_history(), tui.make_history(), tui.make_history()
    prev_rx = prev_tx = prev_time = 0
    info = {"operator": None, "tech": None, "quality": None}
    sig = {"rssi": None, "rsrp": None, "rsrq": None, "snr": None}
    state = reg = None
    bearer = {}
    link = {"v6_ok": None, "nat64_ok": None, "ms": None}
    frame = 0

    scr.timeout(1000)
    try:
        while True:
            try:
                now = time.time()
                modem_txt = _run(["mmcli", "-m", str(idx)])
                info = parse_info(modem_txt)
                state = parse_state(modem_txt)
                reg = parse_registration(modem_txt)
                sig = parse_signal(_run(["mmcli", "-m", str(idx), "--signal-get"]))
                if sig.get("rsrp") is not None:
                    tui.push(rsrp_h, _rsrp_to_pct(sig["rsrp"]))

                # Bearer lookup is heavy — refresh every ~5 frames.
                if frame % 5 == 0 or not bearer:
                    bearer = find_connected_bearer(idx)

                # wwan0 throughput (cheap, every frame).
                rx_now, tx_now = _wwan_bytes("wwan0")
                dt = now - prev_time if prev_time > 0 else 1
                rx_rate = (rx_now - prev_rx) / dt if prev_time > 0 else 0
                tx_rate = (tx_now - prev_tx) / dt if prev_time > 0 else 0
                rx_rate = max(0, rx_rate)
                tx_rate = max(0, tx_rate)
                prev_rx, prev_tx, prev_time = rx_now, tx_now, now
                tui.push(rx_h, min(100, math.log1p(rx_rate) * 10))
                tui.push(tx_h, min(100, math.log1p(tx_rate) * 10))

                # Reachability — blocking pings only every ~15 frames.
                if frame % 15 == 0:
                    v6_ok, v6_ms = _ping6("2001:4860:4860::8888")
                    nat_ok, nat_ms = _ping6("64:ff9b::8.8.8.8")
                    link["v6_ok"] = v6_ok
                    link["nat64_ok"] = nat_ok
                    link["ms"] = v6_ms if v6_ms is not None else nat_ms

                _draw_monitor(scr, info, sig, state, reg, bearer, link,
                              rsrp_h, rx_h, tx_h, rx_rate, tx_rate, frame)
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


def _draw_monitor(scr, info, sig, state, reg, bearer, link,
                  rsrp_h, rx_h, tx_h, rx_rate, tx_rate, tick):
    scr.erase()
    h, w = scr.getmaxyx()

    val = curses.color_pair(tui.C_ITEM) | curses.A_BOLD
    dim = curses.color_pair(tui.C_DIM) | curses.A_DIM
    brd = curses.color_pair(tui.C_BORDER)
    grp = curses.color_pair(tui.C_HEADER)
    hdr = curses.color_pair(tui.C_HEADER) | curses.A_BOLD

    pw = w - 1          # single-column panel width (fits ~53-col uConsole)
    gw = pw - 4         # graph/gauge width inside a panel
    GR = 3              # area-graph rows
    lx = 0

    # ── Header ──
    op = info.get("operator") or "—"
    tech = (info.get("tech") or "—").upper()
    reg_s = reg or "—"
    qual = info.get("quality")
    qual_s = f"{qual}%" if qual is not None else "--%"
    hdr_l = f"  📡 {op} · {tech} · reg:{reg_s}"
    hdr_r = f"{qual_s}  "
    fill = w - len(hdr_l) - len(hdr_r)
    tui.put(scr, 0, 0, hdr_l + "─" * max(1, fill) + hdr_r, w, brd)
    tui.put(scr, 0, 2, f"📡 {op} · {tech} · reg:{reg_s}", len(hdr_l) - 2, hdr)
    tui.put(scr, 0, w - len(hdr_r), hdr_r, len(hdr_r), val)

    y = 1

    # ── SIGNAL panel ──
    qual_v = qual if qual is not None else 0
    tui.panel_top(scr, y, lx, pw, "SIGNAL", f"{qual_s}")
    y += 1
    tui.panel_side(scr, y, lx, pw)
    bar, col = tui.gauge_bar(qual_v, gw, thresh=(40, 70))
    tui.put(scr, y, lx + 2, bar, gw, curses.color_pair(col))
    y += 1
    for row_str in tui.make_area(rsrp_h, gw, GR, max_val=100):
        tui.panel_side(scr, y, lx, pw)
        tui.put(scr, y, lx + 2, row_str, gw, grp)
        y += 1
    # Readout row, each value colored by severity.
    tui.panel_side(scr, y, lx, pw)
    rssi, rsrp = sig.get("rssi"), sig.get("rsrp")
    rsrq, snr = sig.get("rsrq"), sig.get("snr")
    cx = lx + 2
    cx = _put_kv(scr, y, cx, "RSSI", _fmt(rssi), dim, w); cx += 1
    cx = _put_kv(scr, y, cx, "RSRP", _fmt(rsrp),
                 _sev_attr(rsrp_severity(rsrp)) if rsrp is not None else dim, w); cx += 1
    cx = _put_kv(scr, y, cx, "RSRQ", _fmt(rsrq),
                 _sev_attr(rsrq_severity(rsrq)) if rsrq is not None else dim, w); cx += 1
    cx = _put_kv(scr, y, cx, "SNR",
                 ("--" if snr is None else f"{snr:.1f}"),
                 _sev_attr(snr_severity(snr)) if snr is not None else dim, w)
    y += 1
    tui.panel_bot(scr, y, lx, pw)
    y += 1

    # ── CONNECTION panel ──
    tui.panel_top(scr, y, lx, pw, "CONNECTION", state or "—")
    y += 1
    tui.panel_side(scr, y, lx, pw)
    st = (state or "").lower()
    st_attr = _sev_attr("ok") if st == "connected" else _sev_attr("warn")
    tui.put(scr, y, lx + 2, f"state {state or '--'}", gw, st_attr)
    y += 1
    tui.panel_side(scr, y, lx, pw)
    apn = bearer.get("apn") or "--"
    iptype = bearer.get("ip_type") or "--"
    tui.put(scr, y, lx + 2, f"APN {apn} ({iptype})", gw, val)
    y += 1
    tui.panel_side(scr, y, lx, pw)
    addr = bearer.get("address") or "--"
    tui.put(scr, y, lx + 2, _trunc(f"wwan0 {addr}/64", gw), gw, dim)
    y += 1
    tui.panel_side(scr, y, lx, pw)
    gw_ip = bearer.get("gateway") or "--"
    tui.put(scr, y, lx + 2, _trunc(f"gw {gw_ip}", gw), gw, dim)
    y += 1
    tui.panel_bot(scr, y, lx, pw)
    y += 1

    # ── THROUGHPUT panel ──
    dn = rx_rate * 8 / 1e6
    up = tx_rate * 8 / 1e6
    tui.panel_top(scr, y, lx, pw, "THROUGHPUT", f"↓{dn:.1f} ↑{up:.1f} Mbit/s")
    y += 1
    for row_str in tui.make_lines(rx_h, tx_h, gw, GR):
        tui.panel_side(scr, y, lx, pw)
        tui.put(scr, y, lx + 2, row_str, gw, grp)
        y += 1
    tui.panel_side(scr, y, lx, pw)
    tui.put(scr, y, lx + 2, f"↓ {dn:.2f} Mbit/s", 18,
            curses.color_pair(tui.C_STATUS))
    tui.put(scr, y, lx + 2 + (gw // 2), f"↑ {up:.2f} Mbit/s", 18,
            curses.color_pair(tui.C_CAT))
    y += 1
    tui.panel_bot(scr, y, lx, pw)
    y += 1

    # ── LINK panel ──
    if y < h - 2:
        tui.panel_top(scr, y, lx, pw, "LINK")
        y += 1
        tui.panel_side(scr, y, lx, pw)
        cx = lx + 2
        cx = _put_status(scr, y, cx, "IPv6", link.get("v6_ok"))
        cx += 2
        cx = _put_status(scr, y, cx, "NAT64", link.get("nat64_ok"))
        cx += 2
        ms = link.get("ms")
        ms_s = f"ping {ms:.0f}ms" if ms is not None else "ping --"
        tui.put(scr, y, cx, ms_s, gw, dim)
        y += 1
        tui.panel_bot(scr, y, lx, pw)

    # ── Footer ──
    footer = f" 📡 t{tick}  1s refresh  q Back "
    tui.put(scr, h - 1, 0, "─" * w, w, brd)
    fx = max(0, (w - len(footer)) // 2)
    tui.put(scr, h - 1, fx, footer, len(footer), brd)
    scr.refresh()


def _put_kv(scr, y, x, key, valstr, attr, w):
    """Draw `key valstr` (dim key, colored value); return next x."""
    dim = curses.color_pair(tui.C_DIM) | curses.A_DIM
    seg = f"{key} "
    if x < w - 1:
        tui.put(scr, y, x, seg, w - 1 - x, dim)
    x += len(seg)
    if x < w - 1:
        tui.put(scr, y, x, valstr, w - 1 - x, attr)
    return x + len(valstr)


def _put_status(scr, y, x, label, ok):
    """Draw `●label OK/✗` colored ok/bad; return next x."""
    if ok is None:
        dot, mark, attr = "●", "…", curses.color_pair(tui.C_DIM) | curses.A_DIM
    elif ok:
        dot, mark, attr = "●", "OK", _sev_attr("ok")
    else:
        dot, mark, attr = "●", "✗", _sev_attr("bad")
    seg = f"{dot}{label} {mark}"
    tui.put(scr, y, x, seg, len(seg) + 2, attr)
    return x + len(seg)


def _trunc(s, n):
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


HANDLERS = {
    "_cellular_signal": run_cellular_signal,
    "_cellular_monitor": run_cellular_monitor,
}
