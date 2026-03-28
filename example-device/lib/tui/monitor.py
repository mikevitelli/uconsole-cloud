"""TUI module: monitor"""

import curses
import json
import math
import os
import re
import subprocess
import time

from tui.framework import (
    C_BORDER,
    C_CAT,
    C_DIM,
    C_HEADER,
    C_ITEM,
    C_STATUS,
    _tui_input_loop,
    load_config,
    open_gamepad,
)
import tui_lib as tui


def run_live_monitor(scr):
    """Real-time system dashboard — retro-futuristic style."""
    HIST = 120
    GRAPH_EXP = 0.7  # scaling exponent (0.5=sqrt aggressive, 1.0=linear)

    cpu_h, mem_h, temp_h, bat_h, rx_h, tx_h, volt_h = [tui.make_history() for _ in range(7)]
    prev_rx = prev_tx = prev_time = 0

    js = open_gamepad()
    scr.timeout(1000)

    tui.init_gauge_colors()
    def net_bytes():
        rx = tx = 0
        try:
            for ln in open("/proc/net/dev"):
                if ":" not in ln or "lo:" in ln:
                    continue
                p = ln.split()
                rx += int(p[1])
                tx += int(p[9])
        except Exception:
            pass
        return rx, tx

    tick = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        now = time.time()

        # ── Layout — 2×3 panel grid ──
        mid = w // 2
        pw_l = mid - 1          # left panel width
        pw_r = w - mid - 1      # right panel width
        gw_l = pw_l - 4         # graph width inside left panels
        gw_r = pw_r - 4         # graph width inside right panels

        hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
        lbl = curses.color_pair(C_CAT) | curses.A_BOLD
        val = curses.color_pair(C_ITEM) | curses.A_BOLD
        dim = curses.color_pair(C_DIM) | curses.A_DIM
        brd = curses.color_pair(C_BORDER)
        grp = curses.color_pair(C_HEADER)  # graphs use header color

        # ── Scanline header ──
        ts = time.strftime("%H:%M:%S")
        up_s = 0
        try:
            up_s = float(open("/proc/uptime").read().split()[0])
        except Exception:
            pass
        up_h_val = int(up_s // 3600)
        up_m_val = int((up_s % 3600) // 60)

        hdr_l = f"  ◈ UCONSOLE"
        hdr_r = f"{ts}  up {up_h_val}h{up_m_val:02d}m  "
        hdr_fill = w - len(hdr_l) - len(hdr_r)
        hdr_mid = "─" * max(1, hdr_fill)
        tui.put(scr, 0, 0, hdr_l + hdr_mid + hdr_r, w, brd)
        tui.put(scr, 0, 2, " ◈ UCONSOLE", 11, hdr)
        tui.put(scr, 0, w - len(hdr_r), hdr_r, len(hdr_r), val)

        # ═══════════════════════════════════════════════════════
        # ── Collect all data first ──
        # ═══════════════════════════════════════════════════════

        # CPU
        cpu_pct = 0
        loads = ["0", "0", "0"]
        nproc = ncpu = 0
        freq = fmax = 0
        try:
            loads = open("/proc/loadavg").read().split()
            ncpu = os.cpu_count() or 4
            cpu_pct = min(100, float(loads[0]) / ncpu * 100)
            nproc = int(loads[3].split("/")[1]) if "/" in loads[3] else 0
        except Exception:
            ncpu = os.cpu_count() or 4
        tui.push(cpu_h, cpu_pct)
        try:
            freq = int(open("/sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq").read()) // 1000
            fmax = int(open("/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq").read()) // 1000
        except Exception:
            pass

        # MEM
        mem_pct = 0
        mi = {}
        try:
            for ln in open("/proc/meminfo"):
                p = ln.split()
                if len(p) >= 2:
                    mi[p[0].rstrip(":")] = int(p[1])
            total_mem = mi.get("MemTotal", 1)
            avail_mem = mi.get("MemAvailable", 0)
            used_mem = total_mem - avail_mem
            mem_pct = used_mem * 100 // total_mem
        except Exception:
            total_mem = used_mem = 0
        tui.push(mem_h, mem_pct)

        # TEMP
        temp_c = 0
        try:
            temp_c = int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
        except Exception:
            pass
        tui.push(temp_h, min(100, temp_c))
        gov = ""
        try:
            gov = open("/sys/devices/system/cpu/cpufreq/policy0/scaling_governor").read().strip()
        except Exception:
            pass

        # BAT
        bat_pct = bat_v = bat_i = 0
        bat_status = ""
        try:
            bat_pct = int(open("/sys/class/power_supply/axp20x-battery/capacity").read())
            bat_status = open("/sys/class/power_supply/axp20x-battery/status").read().strip()
            bat_v = int(open("/sys/class/power_supply/axp20x-battery/voltage_now").read()) / 1e6
            bat_i = int(open("/sys/class/power_supply/axp20x-battery/current_now").read()) / 1e3
        except Exception:
            pass
        # vest% — Nitecore NL1834 measured discharge curve (2026-03-27)
        v = bat_v
        if v <= 3.0:
            bat_vest = 0
        elif v < 3.1:
            bat_vest = int((v - 3.0) / 0.1 * 15)
        elif v < 3.2:
            bat_vest = int(15 + (v - 3.1) / 0.1 * 35)
        elif v < 3.3:
            bat_vest = int(50 + (v - 3.2) / 0.1 * 10)
        elif v < 3.4:
            bat_vest = int(60 + (v - 3.3) / 0.1 * 10)
        elif v < 3.6:
            bat_vest = int(70 + (v - 3.4) / 0.2 * 10)
        elif v < 3.8:
            bat_vest = int(80 + (v - 3.6) / 0.2 * 10)
        else:
            bat_vest = min(100, int(90 + (v - 3.8) / 0.25 * 10))
        # Pick display % based on config: auto (default), vest, or capacity
        gauge_mode = load_config().get("bat_gauge", "auto")
        if gauge_mode == "vest":
            bat_display = bat_vest
        elif gauge_mode == "capacity":
            bat_display = bat_pct
        else:  # auto: vest when discharging, capacity when charging
            bat_display = bat_vest if bat_status == "Discharging" else bat_pct
        tui.push(bat_h, bat_display)
        tui.push(volt_h, bat_v)

        # NET
        rx_now, tx_now = net_bytes()
        dt_n = now - prev_time if prev_time > 0 else 1
        rx_rate = (rx_now - prev_rx) / dt_n / 1024 if prev_time > 0 else 0
        tx_rate = (tx_now - prev_tx) / dt_n / 1024 if prev_time > 0 else 0
        prev_rx, prev_tx, prev_time = rx_now, tx_now, now
        tui.push(rx_h, min(100, math.log1p(rx_rate) * 10))
        tui.push(tx_h, min(100, math.log1p(tx_rate) * 10))

        # DSK
        dp = du_d = da_d = dt_d = 0
        try:
            s = os.statvfs("/")
            dt_d = s.f_blocks * s.f_frsize
            df_d = s.f_bfree * s.f_frsize
            du_d = dt_d - df_d
            da_d = s.f_bavail * s.f_frsize
            dp = du_d * 100 // max(1, dt_d)
        except Exception:
            pass

        # WiFi
        ssid = ip_addr = signal = ""
        try:
            ssid = subprocess.check_output(["iwgetid", "-r"], stderr=subprocess.DEVNULL, timeout=1).decode().strip()
            ip_addr = subprocess.check_output(["hostname", "-I"], timeout=1).decode().split()[0]
        except Exception:
            pass
        try:
            iwout = subprocess.check_output(["iwconfig", "wlan0"], stderr=subprocess.DEVNULL, timeout=1).decode()
            m = re.search(r'Signal level=(\S+)', iwout)
            signal = f"{m.group(1)}dBm" if m else ""
        except Exception:
            pass

        # TOP processes
        top_procs = []
        try:
            top_out = subprocess.check_output(
                ["ps", "-eo", "%cpu,rss,comm", "--sort=-%cpu", "--no-headers"],
                timeout=2
            ).decode().strip().splitlines()
            count = 0
            for tl in top_out:
                parts = tl.split(None, 2)
                if len(parts) >= 3 and not parts[2].strip().endswith("ps"):
                    top_procs.append((
                        f"{min(100.0, float(parts[0])):.1f}",
                        int(parts[1]) // 1024,
                        parts[2][:18]
                    ))
                    count += 1
                    if count >= 7:
                        break
        except Exception:
            pass

        # ═══════════════════════════════════════════════════════
        # ── Render panels ──
        # ═══════════════════════════════════════════════════════

        GR = 4          # graph rows for area charts
        ARC_R = 5       # arc gauge rows
        lx = 0          # left panel x
        rx = mid        # right panel x

        # ────────── LEFT: CPU — area graph ──────────
        y = 1
        tui.panel_top(scr, y, lx, pw_l, "CPU", f"{cpu_pct:.1f}%  {freq}/{fmax}MHz")
        y += 1
        # Gauge bar
        tui.panel_side(scr, y, lx, pw_l)
        bar, col = tui.gauge_bar(cpu_pct, gw_l)
        tui.put(scr, y, lx + 2, bar, gw_l, curses.color_pair(col))
        y += 1
        # Area graph
        for row_str in tui.make_area(cpu_h, gw_l, GR):
            tui.panel_side(scr, y, lx, pw_l)
            tui.put(scr, y, lx + 2, row_str, gw_l, grp)
            y += 1
        tui.panel_side(scr, y, lx, pw_l)
        tui.put(scr, y, lx + 2, f"load {loads[0]} {loads[1]} {loads[2]}  {ncpu}×core  {nproc} procs", pw_l - 4, dim)
        y += 1
        tui.panel_bot(scr, y, lx, pw_l)
        y += 1

        # ────────── LEFT: MEM — area graph ──────────
        tui.panel_top(scr, y, lx, pw_l, "MEM", f"{mem_pct}%  {used_mem // 1024}M/{total_mem // 1024}M")
        y += 1
        tui.panel_side(scr, y, lx, pw_l)
        bar, col = tui.gauge_bar(mem_pct, gw_l)
        tui.put(scr, y, lx + 2, bar, gw_l, curses.color_pair(col))
        y += 1
        for row_str in tui.make_area(mem_h, gw_l, GR):
            tui.panel_side(scr, y, lx, pw_l)
            tui.put(scr, y, lx + 2, row_str, gw_l, grp)
            y += 1
        buffers = mi.get("Buffers", 0) // 1024
        cached = mi.get("Cached", 0) // 1024
        swapused = (mi.get("SwapTotal", 0) - mi.get("SwapFree", 0)) // 1024
        tui.panel_side(scr, y, lx, pw_l)
        tui.put(scr, y, lx + 2, f"buf {buffers}M  cache {cached}M  swap {swapused}M", pw_l - 4, dim)
        y += 1
        tui.panel_bot(scr, y, lx, pw_l)
        y += 1

        # ────────── LEFT: DSK — segmented gauge ──────────
        tui.panel_top(scr, y, lx, pw_l, "DSK", f"{dp}%  {du_d // (1024**3)}G/{dt_d // (1024**3)}G")
        y += 1
        tui.panel_side(scr, y, lx, pw_l)
        bar, col = tui.gauge_bar(dp, gw_l, (70, 90))
        tui.put(scr, y, lx + 2, bar, gw_l, curses.color_pair(col))
        y += 1
        # Tick scale under gauge
        tui.panel_side(scr, y, lx, pw_l)
        ticks = ""
        for t in range(0, 101, 10):
            pos = int(gw_l * t / 100)
            ticks += " " * (pos - len(ticks)) + "│"
        tui.put(scr, y, lx + 2, ticks[:gw_l], gw_l, dim)
        y += 1
        tui.panel_side(scr, y, lx, pw_l)
        scale = "0%"
        scale += " " * (gw_l // 4 - len(scale)) + "25%"
        scale += " " * (gw_l // 2 - len(scale)) + "50%"
        scale += " " * (3 * gw_l // 4 - len(scale)) + "75%"
        scale += " " * (gw_l - 1 - len(scale)) + "100%"
        tui.put(scr, y, lx + 2, scale[:gw_l], gw_l, dim)
        y += 1
        tui.panel_bot(scr, y, lx, pw_l)
        y += 1

        # ────────── LEFT: TOP — proportional bars ──────────
        if y < h - 2:
            tui.panel_top(scr, y, lx, pw_l, "TOP", "by CPU")
            y += 1
            bar_w = gw_l - 20
            for cpup, rss, name in top_procs:
                if y >= h - 2:
                    break
                tui.panel_side(scr, y, lx, pw_l)
                pct_f = float(cpup)
                fill = int(bar_w * pct_f / max(100, pct_f + 1))
                pbar = "▓" * fill
                tui.put(scr, y, lx + 2, f"{name:<12s}", 12, val)
                tui.put(scr, y, lx + 15, pbar, bar_w, grp)
                tui.put(scr, y, lx + 16 + bar_w, f"{cpup:>5}% {rss:>4}M", 11, dim)
                y += 1
            tui.panel_bot(scr, y, lx, pw_l)

        # ────────── RIGHT: TEMP — area graph ──────────
        ry = 1
        tz = "COOL" if temp_c < 45 else "WARM" if temp_c < 60 else "HOT!"
        tui.panel_top(scr, ry, rx, pw_r, "TEMP", f"{temp_c:.1f}°C  {tz}")
        ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        bar, col = tui.gauge_bar(temp_c, gw_r, (55, 70))
        tui.put(scr, ry, rx + 2, bar, gw_r, curses.color_pair(col))
        ry += 1
        for row_str in tui.make_area(temp_h, gw_r, GR):
            tui.panel_side(scr, ry, rx, pw_r)
            tui.put(scr, ry, rx + 2, row_str, gw_r, grp)
            ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        tui.put(scr, ry, rx + 2, f"governor: {gov}", pw_r - 4, dim)
        ry += 1
        tui.panel_bot(scr, ry, rx, pw_r)
        ry += 1

        # ────────── RIGHT: BAT — arc gauge ──────────
        bat_icon = "⚡" if bat_status == "Charging" else "▼" if bat_display <= 20 else "●"
        tui.panel_top(scr, ry, rx, pw_r, "BAT", f"{bat_icon}{bat_display}%  {bat_v:.3f}V")
        ry += 1
        # Arc gauge — centered in panel
        arc_w = min(gw_r, 40)
        arc_rows = tui.make_arc(bat_display, arc_w, ARC_R)
        arc_x = rx + 2 + (gw_r - arc_w) // 2
        bcol = tui.C_CRIT if bat_display <= 15 else tui.C_WARN if bat_display <= 30 else tui.C_OK
        for row_str in arc_rows:
            tui.panel_side(scr, ry, rx, pw_r)
            tui.put(scr, ry, arc_x, row_str, arc_w, curses.color_pair(bcol))
            ry += 1
        # Percentage centered under arc
        tui.panel_side(scr, ry, rx, pw_r)
        pct_str = f"{bat_display}%"
        tui.put(scr, ry, rx + 2 + (gw_r - len(pct_str)) // 2, pct_str, len(pct_str), val)
        ry += 1
        # Status details
        tui.panel_side(scr, ry, rx, pw_r)
        tui.put(scr, ry, rx + 2, f"{bat_status}  {bat_i:+.0f}mA", pw_r - 4, dim)
        ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        if gauge_mode == "vest":
            alt_label, alt_pct = "gauge", bat_pct
        elif gauge_mode == "capacity":
            alt_label, alt_pct = "vest", bat_vest
        else:
            alt_label = "vest" if bat_status == "Charging" else "gauge"
            alt_pct = bat_vest if bat_status == "Charging" else bat_pct
        tui.put(scr, ry, rx + 2, f"{alt_label}: {alt_pct}%", pw_r - 4, dim)
        ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        if bat_i != 0 and bat_status == "Discharging":
            cap_mah = 6800
            remain_h = (bat_display / 100 * cap_mah) / abs(bat_i)
            tui.put(scr, ry, rx + 2, f"~{remain_h:.1f}h remaining  ({abs(bat_i):.0f}mA draw)", pw_r - 4, dim)
        elif bat_status == "Charging":
            chg_rate = 0
            try:
                chg_rate = int(open("/sys/class/power_supply/axp20x-battery/constant_charge_current").read()) // 1000
            except Exception:
                pass
            tui.put(scr, ry, rx + 2, f"charge rate: {chg_rate}mA", pw_r - 4, dim)
        else:
            tui.put(scr, ry, rx + 2, "", pw_r - 4, dim)
        ry += 1
        # Voltage waveform — line trace showing voltage trend over time
        if len(volt_h) > 1:
            tui.panel_side(scr, ry, rx, pw_r)
            ry += 0  # voltage waveform follows directly
            for row_str in tui.make_vwave(volt_h, gw_r, 2):
                tui.panel_side(scr, ry, rx, pw_r)
                tui.put(scr, ry, rx + 2, row_str, gw_r, curses.color_pair(bcol))
                ry += 1
        tui.panel_bot(scr, ry, rx, pw_r)
        ry += 1

        # ────────── RIGHT: NET — oscilloscope dual-line ──────────
        rxs = f"{rx_rate:.0f}" if rx_rate < 1000 else f"{rx_rate/1024:.1f}M"
        txs = f"{tx_rate:.0f}" if tx_rate < 1000 else f"{tx_rate/1024:.1f}M"
        tui.panel_top(scr, ry, rx, pw_r, "NET", f"↓{rxs} ↑{txs} KB/s")
        ry += 1
        for row_str in tui.make_lines(rx_h, tx_h, gw_r, GR):
            tui.panel_side(scr, ry, rx, pw_r)
            tui.put(scr, ry, rx + 2, row_str, gw_r, grp)
            ry += 1
        # Legend + baseline
        tui.panel_side(scr, ry, rx, pw_r)
        tui.put(scr, ry, rx + 2, "─" * gw_r, gw_r, dim)
        ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        tui.put(scr, ry, rx + 2, "⠉ rx  ", 6, curses.color_pair(C_STATUS))
        tui.put(scr, ry, rx + 9, "⠉ tx", 4, curses.color_pair(C_CAT))
        if ssid:
            wifi_info = f"  {ssid}  {ip_addr}  {signal}"
            tui.put(scr, ry, rx + 14, wifi_info, pw_r - 16, dim)
        ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        tui.put(scr, ry, rx + 2, f"total ↓{rx_now // (1024**2)}MB ↑{tx_now // (1024**2)}MB", pw_r - 4, dim)
        ry += 1
        tui.panel_bot(scr, ry, rx, pw_r)

        # ── Footer ──
        footer = f" ◈ t{tick}  1s refresh  B Back "
        tui.put(scr, h - 1, 0, "─" * w, w, brd)
        fx = (w - len(footer)) // 2
        tui.put(scr, h - 1, fx, footer, len(footer), brd)

        scr.refresh()
        tick += 1

        key, gp = _tui_input_loop(scr, js)
        if key == ord("q") or key == ord("Q") or gp == "back":
            break

    if js:
        js.close()
    scr.timeout(100)

def run_esp32_monitor(scr):
    """Real-time ESP32 sensor dashboard — retro-futuristic style."""
    import urllib.request

    HIST = 120
    API_URL = "http://localhost:8080/api/esp32"

    temp_h = tui.make_history()
    mem_h = tui.make_history()

    js = open_gamepad()
    scr.timeout(2000)
    tui.init_gauge_colors()

    tick = 0
    last_data = {}

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # ── Fetch data from webdash API ──
        data = last_data.copy()
        try:
            resp = urllib.request.urlopen(API_URL, timeout=2)
            data = json.loads(resp.read())
            last_data = data.copy()
        except Exception:
            pass

        online   = data.get("online", False)
        temp_c   = data.get("temp_c", 0)
        temp_f   = data.get("temp_f", 0)
        free_kb  = data.get("free_kb", 0)
        ip_addr  = data.get("ip", "--")
        age      = data.get("age", -1)
        touches  = data.get("touches", {})

        tui.push(temp_h, temp_c)
        tui.push(mem_h, free_kb)

        # ── Layout — 2-column panel grid ──
        mid = w // 2
        pw_l = mid - 1
        pw_r = w - mid - 1
        gw_l = pw_l - 4
        gw_r = pw_r - 4
        GR = 4
        ARC_R = 5

        hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
        lbl = curses.color_pair(C_CAT) | curses.A_BOLD
        val = curses.color_pair(C_ITEM) | curses.A_BOLD
        dim = curses.color_pair(C_DIM) | curses.A_DIM
        brd = curses.color_pair(C_BORDER)
        grp = curses.color_pair(C_HEADER)

        # ── Scanline header ──
        ts = time.strftime("%H:%M:%S")
        if online:
            status_str = "●ONLINE"
            status_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
        else:
            status_str = "○OFFLINE"
            status_attr = curses.color_pair(tui.C_CRIT) | curses.A_BOLD

        hdr_l = "  ◈ ESP32"
        hdr_r = f"{ts}  {status_str}  "
        hdr_fill = w - len(hdr_l) - len(hdr_r)
        hdr_mid = "─" * max(1, hdr_fill)
        tui.put(scr, 0, 0, hdr_l + hdr_mid + hdr_r, w, brd)
        tui.put(scr, 0, 2, " ◈ ESP32", 8, hdr)
        tui.put(scr, 0, w - len(hdr_r), hdr_r, len(hdr_r), status_attr)

        lx = 0
        rx = mid

        # ────────── LEFT: TEMP — area graph ──────────
        y = 1
        tz = "COOL" if temp_c < 45 else "WARM" if temp_c < 60 else "HOT!"
        tui.panel_top(scr, y, lx, pw_l, "TEMP", f"{temp_c:.1f}°C  {tz}")
        y += 1
        temp_pct = max(0, min(100, temp_c * 100 / 80))
        tui.panel_side(scr, y, lx, pw_l)
        bar, col = tui.gauge_bar(temp_pct, gw_l, (55, 70))
        tui.put(scr, y, lx + 2, bar, gw_l, curses.color_pair(col))
        y += 1
        for row_str in tui.make_area(temp_h, gw_l, GR, max_val=80):
            tui.panel_side(scr, y, lx, pw_l)
            tui.put(scr, y, lx + 2, row_str, gw_l, grp)
            y += 1
        tui.panel_side(scr, y, lx, pw_l)
        tui.put(scr, y, lx + 2, f"range: 0-80°C  {temp_f:.1f}°F", pw_l - 4, dim)
        y += 1
        tui.panel_bot(scr, y, lx, pw_l)
        y += 1

        # ────────── LEFT: CONN — arc gauge ──────────
        # Freshness: 100% when age<=3s, fades to 0% at 30s
        if age < 0:
            fresh_pct = 0
        elif age <= 3:
            fresh_pct = 100
        else:
            fresh_pct = max(0, int(100 - (age - 3) * 100 / 27))

        tui.panel_top(scr, y, lx, pw_l, "CONN", ip_addr)
        y += 1
        arc_w = min(gw_l, 40)
        arc_rows = tui.make_arc(fresh_pct, arc_w, ARC_R)
        arc_x = lx + 2 + (gw_l - arc_w) // 2
        ccol = tui.C_CRIT if fresh_pct <= 15 else tui.C_WARN if fresh_pct <= 40 else tui.C_OK
        for row_str in arc_rows:
            tui.panel_side(scr, y, lx, pw_l)
            tui.put(scr, y, arc_x, row_str, arc_w, curses.color_pair(ccol))
            y += 1
        # Freshness % centered under arc
        tui.panel_side(scr, y, lx, pw_l)
        fpct = f"{fresh_pct}%"
        tui.put(scr, y, lx + 2 + (gw_l - len(fpct)) // 2, fpct, len(fpct), val)
        y += 1
        tui.panel_side(scr, y, lx, pw_l)
        age_str = f"{age}s ago" if age >= 0 else "no data"
        tui.put(scr, y, lx + 2, f"last update: {age_str}", pw_l - 4, dim)
        y += 1
        tui.panel_side(scr, y, lx, pw_l)
        tui.put(scr, y, lx + 2, "WiFi: Big Parma - 2.4GHz", pw_l - 4, dim)
        y += 1
        tui.panel_bot(scr, y, lx, pw_l)

        # ────────── RIGHT: RAM — area graph ──────────
        ry = 1
        mem_max = 300
        mem_pct = max(0, min(100, (mem_max - free_kb) * 100 / mem_max)) if mem_max > 0 else 0
        tui.panel_top(scr, ry, rx, pw_r, "RAM", f"{free_kb}/{mem_max} KB")
        ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        bar, col = tui.gauge_bar(100 - mem_pct, gw_r)  # invert: high free = good
        tui.put(scr, ry, rx + 2, bar, gw_r, curses.color_pair(col))
        ry += 1
        for row_str in tui.make_area(mem_h, gw_r, GR, max_val=mem_max):
            tui.panel_side(scr, ry, rx, pw_r)
            tui.put(scr, ry, rx + 2, row_str, gw_r, grp)
            ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        tui.put(scr, ry, rx + 2, "heap free  ESP32-D0WD-V3", pw_r - 4, dim)
        ry += 1
        tui.panel_bot(scr, ry, rx, pw_r)
        ry += 1

        # ────────── RIGHT: TOUCH — indicator grid ──────────
        tui.panel_top(scr, ry, rx, pw_r, "TOUCH")
        ry += 1
        t0 = touches.get("touch0", False)
        t3 = touches.get("touch3", False)
        t4 = touches.get("touch4", False)
        t7 = touches.get("touch7", False)

        def touch_str(name, active):
            icon = "●" if active else "○"
            return name, icon, active

        for row_pins in [(("T0", t0), ("T3", t3)), (("T4", t4), ("T7", t7))]:
            tui.panel_side(scr, ry, rx, pw_r)
            col_w = gw_r // 2
            for ci, (pname, pval) in enumerate(row_pins):
                px = rx + 2 + ci * col_w
                icon = "●" if pval else "○"
                icon_col = curses.color_pair(tui.C_OK) | curses.A_BOLD if pval else dim
                tui.put(scr, ry, px, f"  {pname}  ", 6, val)
                tui.put(scr, ry, px + 6, icon, 1, icon_col)
                if pval:
                    tui.put(scr, ry, px + 8, "touched", 7, curses.color_pair(tui.C_OK))
            ry += 1

        tui.panel_side(scr, ry, rx, pw_r)
        ry += 1
        tui.panel_side(scr, ry, rx, pw_r)
        tui.put(scr, ry, rx + 2, "● = touched  ○ = idle", pw_r - 4, dim)
        ry += 1
        tui.panel_bot(scr, ry, rx, pw_r)

        # ── Footer ──
        footer = f" ◈ t{tick}  2s refresh  B Back "
        tui.put(scr, h - 1, 0, "─" * w, w, brd)
        fx = (w - len(footer)) // 2
        tui.put(scr, h - 1, fx, footer, len(footer), brd)

        scr.refresh()
        tick += 1

        key, gp = _tui_input_loop(scr, js)
        if key == ord("q") or key == ord("Q") or gp == "back":
            break

    if js:
        js.close()
    scr.timeout(100)
