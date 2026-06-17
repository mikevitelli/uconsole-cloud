"""Reusable TUI components for curses-based monitors.

Extracted from console.py's run_live_monitor to enable shared use
across ESP32 monitor, battery test monitor, and future TUI screens.
"""

import curses
import math
from collections import deque

# ── Constants ──────────────────────────────────────────────────────────

DEFAULT_GRAPH_EXP = 0.7   # scaling exponent for area/line graphs
DEFAULT_HIST_SIZE = 120    # default history buffer length

# Gauge color pair IDs (call init_gauge_colors() after curses.start_color())
C_OK = 20
C_WARN = 21
C_CRIT = 22
C_RX = 23       # NET download trace — cyan
C_TX = 24       # NET upload trace — magenta

# Standard color pair IDs (initialized by console.py's apply_theme)
C_HEADER = 1
C_CAT = 2
C_ITEM = 3
C_SEL = 4
C_DESC = 5
C_BORDER = 6
C_FOOTER = 7
C_STATUS = 8
C_DIM = 9


# ── Gauge Color Init ──────────────────────────────────────────────────

def init_gauge_colors():
    """Initialize C_OK/C_WARN/C_CRIT color pairs. Call once after curses.start_color()."""
    curses.init_pair(C_OK,   curses.COLOR_GREEN,   -1)
    curses.init_pair(C_WARN, curses.COLOR_YELLOW,  -1)
    curses.init_pair(C_CRIT, curses.COLOR_RED,     -1)
    curses.init_pair(C_RX,   curses.COLOR_CYAN,    -1)
    curses.init_pair(C_TX,   curses.COLOR_MAGENTA, -1)


# ── History Buffer ────────────────────────────────────────────────────

def make_history(max_len=DEFAULT_HIST_SIZE):
    """Create a new history buffer (deque with maxlen)."""
    return deque(maxlen=max_len)


def push(buf, val, max_len=DEFAULT_HIST_SIZE):
    """Append value to history buffer. Works with deque (auto-trims) and list."""
    buf.append(val)
    if isinstance(buf, list) and len(buf) > max_len:
        del buf[:len(buf) - max_len]


# ── Safe Curses Write ─────────────────────────────────────────────────

def put(scr, y, x, text, n, attr):
    """Safe curses write — clips text and catches errors."""
    try:
        scr.addnstr(y, x, text[:n], n, attr)
    except curses.error:
        pass


# ── BrailleCanvas ─────────────────────────────────────────────────────

class BrailleCanvas:
    """2x4 dot-matrix canvas using Unicode braille characters."""
    DOTS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]

    def __init__(self, cw, ch):
        self.cw, self.ch = cw, ch
        self.pw, self.ph = cw * 2, ch * 4
        self.grid = [[0] * cw for _ in range(ch)]

    def set(self, px, py):
        if 0 <= px < self.pw and 0 <= py < self.ph:
            self.grid[py // 4][px // 2] |= self.DOTS[py % 4][px % 2]

    def line(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self.set(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def render(self):
        return ["".join(chr(0x2800 | self.grid[cy][cx])
                        for cx in range(self.cw)) for cy in range(self.ch)]

    def dot_count(self):
        total = 0
        for row in self.grid:
            for cell in row:
                total += bin(cell).count('1')
        return total


# ── Graph Generators ──────────────────────────────────────────────────

def make_area(hist, cw, ch, max_val=100, graph_exp=DEFAULT_GRAPH_EXP):
    """Filled area graph — connected line with solid fill below."""
    c = BrailleCanvas(cw, ch)
    data = list(hist)[-c.pw:]
    prev = None
    for i, v in enumerate(data):
        v = max(0, min(max_val, v))
        if max_val > 0 and v > 0:
            scaled = (v / max_val) ** graph_exp
            py = c.ph - 1 - max(1, int(scaled * (c.ph - 1)))
        else:
            py = c.ph - 1
        if prev is not None:
            c.line(i - 1, prev, i, py)
        for fy in range(py, c.ph):
            c.set(i, fy)
        prev = py
    return c.render()


def make_line(hist, cw, ch, max_val=100, graph_exp=DEFAULT_GRAPH_EXP):
    """Single line graph — oscilloscope style, one trace, no fill. Render two of
    these and overlay them to get independently-colored traces (a braille cell
    can only hold one color, so dual-color needs separate layers)."""
    c = BrailleCanvas(cw, ch)
    data = list(hist)[-c.pw:]
    prev = None
    for i, v in enumerate(data):
        v = max(0, min(max_val, v))
        if max_val > 0 and v > 0:
            scaled = (v / max_val) ** graph_exp
            py = c.ph - 1 - max(1, int(scaled * (c.ph - 1)))
        else:
            py = c.ph - 1
        if prev is not None:
            c.line(i - 1, prev, i, py)
        else:
            c.set(i, py)
        prev = py
    return c.render()


def make_lines(h1, h2, cw, ch, max_val=100, graph_exp=DEFAULT_GRAPH_EXP):
    """Dual line graph — oscilloscope style, two traces, no fill."""
    c = BrailleCanvas(cw, ch)
    for hist in [h1, h2]:
        data = list(hist)[-c.pw:]
        prev = None
        for i, v in enumerate(data):
            v = max(0, min(max_val, v))
            if max_val > 0 and v > 0:
                scaled = (v / max_val) ** graph_exp
                py = c.ph - 1 - max(1, int(scaled * (c.ph - 1)))
            else:
                py = c.ph - 1
            if prev is not None:
                c.line(i - 1, prev, i, py)
            else:
                c.set(i, py)
            prev = py
    return c.render()


def make_mirror(h_up, h_dn, cw, ch, max_val=100, graph_exp=DEFAULT_GRAPH_EXP):
    """Mirrored oscilloscope. ``ch`` should be EVEN so the two halves are
    symmetric: ``h_up`` traces upward from a thin center line, ``h_dn`` downward.
    Uses connected LINE traces (sharp, defined spikes) rather than solid fill.
    Returns ``(rows, split)`` — ``rows[:split]`` is the up-trace, ``rows[split:]``
    the down-trace — so the caller colors each half (position separates them
    even when the two colors are close)."""
    c = BrailleCanvas(cw, ch)
    half = ch // 2
    center = half * 4                       # axis sits on the char-row boundary
    up_span = max(1, center - 1)
    dn_span = max(1, c.ph - center - 1)
    # No separate baseline — each trace rests ON the center line when idle and
    # lifts into a spike where there's activity, so it reads as a single line.
    prev = None                             # up-trace: line rising from the axis
    for i, v in enumerate(list(h_up)[-c.pw:]):
        v = max(0, min(max_val, v))
        s = (v / max_val) ** graph_exp if max_val > 0 else 0
        py = max(0, (center - 1) - int(s * up_span))
        if prev is not None:
            c.line(i - 1, prev, i, py)
        else:
            c.set(i, py)
        prev = py
    prev = None                             # down-trace: line dropping from the axis
    for i, v in enumerate(list(h_dn)[-c.pw:]):
        v = max(0, min(max_val, v))
        s = (v / max_val) ** graph_exp if max_val > 0 else 0
        py = min(c.ph - 1, center + int(s * dn_span))
        if prev is not None:
            c.line(i - 1, prev, i, py)
        else:
            c.set(i, py)
        prev = py
    return c.render(), half


def make_arc(pct, cw, ch):
    """Semicircle arc gauge — retro dial indicator."""
    c = BrailleCanvas(cw, ch)
    cx = c.pw / 2
    cy = c.ph + 2
    radius = min(c.pw / 2 - 2, c.ph + 1)
    inner = radius * 0.55
    pct = max(0, min(100, pct))
    fill_end = math.pi * (1 - pct / 100)

    for px in range(c.pw):
        for py in range(c.ph):
            dx, dy = px - cx, cy - py
            if dy < 0:
                continue
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < inner - 0.5 or dist > radius + 0.5:
                continue
            angle = math.atan2(dy, dx)
            if angle < 0:
                continue
            on_edge = abs(dist - radius) < 1.0 or abs(dist - inner) < 1.0
            on_cap = (abs(angle) < 0.12 or abs(angle - math.pi) < 0.12) and inner <= dist <= radius
            in_fill = inner - 0.5 <= dist <= radius + 0.5 and angle >= fill_end
            if on_edge or on_cap or in_fill:
                c.set(px, py)

    # Tick marks at 25/50/75%
    for tp in [25, 50, 75]:
        ta = math.pi * (1 - tp / 100)
        for r in [radius + 1.5, inner - 1.5]:
            tx = int(cx + r * math.cos(ta))
            ty = int(cy - r * math.sin(ta))
            c.set(tx, ty)
            c.set(tx + 1, ty)

    # Needle at current value
    needle_a = math.pi * (1 - pct / 100)
    for r_step in range(int(inner) + 1, int(radius)):
        nx = int(cx + r_step * math.cos(needle_a))
        ny = int(cy - r_step * math.sin(needle_a))
        c.set(nx, ny)

    return c.render()


def make_liquid(pct, cw, ch, t=0, charging=False):
    """Liquid-fill battery gauge — a tank that fills from the bottom to ``pct``
    with an animated sine surface (sum of two sines). Amplitude is triangular
    (calm at 0%/100%, waviest mid-charge, d3-liquid-fill style); the surface
    scrolls with ``t`` and gets faster/choppier while ``charging``."""
    c = BrailleCanvas(cw, ch)
    pct = max(0, min(100, pct))
    H = c.ph
    base = H * (1 - pct / 100.0)
    if charging:
        amp = 2.6                                    # strong, level-independent agitation
        phase = t * 0.7
        base += 1.0 * math.sin(t * 0.2)              # slow slosh bob
        base = max(amp, base)                        # keep the surface visible even at ~100%
    else:
        amp = 2.6 * (1 - abs(pct - 50) / 50.0)       # triangular: calm/solid at 0% and 100%
        phase = t * 0.35
    lam_back = max(8.0, c.pw / 1.6)                  # ~1.6 long swells across width
    lam_front = max(5.0, c.pw / 3.4)                 # finer ripple on top
    for x in range(c.pw):
        surf = base - (amp * 0.6 * math.sin(2 * math.pi * x / lam_back + phase)
                       + amp * 0.4 * math.sin(2 * math.pi * x / lam_front - phase * 1.7))
        for y in range(max(0, int(round(surf))), H):
            c.set(x, y)
    return c.render()


def make_vwave(hist, cw, ch, vmin=3.0, vmax=4.2):
    """Single-trace voltage waveform — linear scale, no fill."""
    c = BrailleCanvas(cw, ch)
    data = list(hist)[-c.pw:]
    prev = None
    vrange = vmax - vmin
    for i, v in enumerate(data):
        v = max(vmin, min(vmax, v))
        frac = (v - vmin) / vrange if vrange > 0 else 0
        py = c.ph - 1 - int(frac * (c.ph - 1))
        if prev is not None:
            c.line(i - 1, prev, i, py)
        else:
            c.set(i, py)
        prev = py
    return c.render()


def make_waveform(samples, cw, ch, max_amp=32768):
    """Centered audio waveform — symmetric oscilloscope trace around midline."""
    c = BrailleCanvas(cw, ch)
    mid = c.ph // 2
    data = list(samples)[-c.pw:]
    prev = None
    for i, s in enumerate(data):
        s = max(-max_amp, min(max_amp, s))
        frac = s / max_amp if max_amp > 0 else 0
        py = mid - int(frac * (mid - 1))
        py = max(0, min(c.ph - 1, py))
        if prev is not None:
            c.line(i - 1, prev, i, py)
        else:
            c.set(i, py)
        prev = py
    return c.render()


# ── Panel Drawing ─────────────────────────────────────────────────────

def panel_top(scr, y, x, width, title="", detail="",
              border_pair=None, title_pair=None, detail_pair=None):
    """Draw rounded panel top border with optional title and detail."""
    if border_pair is None:
        border_pair = curses.color_pair(C_BORDER)
    if title_pair is None:
        title_pair = curses.color_pair(C_CAT) | curses.A_BOLD
    if detail_pair is None:
        detail_pair = curses.color_pair(C_ITEM) | curses.A_BOLD
    brd = border_pair
    if title:
        t = f" {title} "
        if detail:
            d = f" {detail} "
            # Panel total width: "╭─" + t + "─"*fill + d + "─╮"
            # = 2 + len(t) + fill + len(d) + 2  → fill = width - 4 - len(t) - len(d)
            fill = width - 4 - len(t) - len(d)
            line = "╭─" + t + "─" * max(1, fill) + d + "─╮"
        else:
            line = "╭─" + t + "─" * (width - 4 - len(t)) + "─╮"
        put(scr, y, x, line, width, brd)
        put(scr, y, x + 3, t, len(t), title_pair)
        if detail:
            dpos = x + width - 2 - len(d)
            put(scr, y, dpos, d, len(d), detail_pair)
    else:
        put(scr, y, x, "╭" + "─" * (width - 2) + "╮", width, brd)


def panel_side(scr, y, x, width, border_pair=None):
    """Draw left and right panel borders."""
    if border_pair is None:
        border_pair = curses.color_pair(C_BORDER)
    put(scr, y, x, "│", 1, border_pair)
    put(scr, y, x + width - 1, "│", 1, border_pair)


def panel_bot(scr, y, x, width, border_pair=None):
    """Draw rounded panel bottom border."""
    if border_pair is None:
        border_pair = curses.color_pair(C_BORDER)
    put(scr, y, x, "╰" + "─" * (width - 2) + "╯", width, border_pair)


def gauge_bar(pct, width, thresh=(60, 85)):
    """Colored progress bar. Returns (bar_string, color_pair_id)."""
    pct = max(0, min(100, pct))
    f = int(width * pct / 100)
    bar = "█" * f + "░" * (width - f)
    col = C_CRIT if pct >= thresh[1] else C_WARN if pct >= thresh[0] else C_OK
    return bar, col
