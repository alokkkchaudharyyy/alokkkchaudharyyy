"""
Builds every SVG used in the profile README.

    python tools/profile.py static          # hero, project tiles, NEXERA card, headers, buttons, footer
    python tools/profile.py live <login>    # terminal, Agent Bridge tile and contribution city (live data)

Live mode uses GITHUB_TOKEN when it is set (GitHub Actions provides one) and
falls back to public endpoints otherwise.
"""

import base64
import datetime as dt
import json
import math
import os
import random
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS, METRICS, TOOLS = ROOT / "assets", ROOT / "metrics", ROOT / "tools"

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
CW = 0.6  # monospace advance in em

# personal palette: synthwave dusk
BG0, PANEL, LINE = "#05060a", "#0c0f17", "#1f2433"
FG, FG2, FG3 = "#eef2f8", "#9aa4b5", "#5f6b7d"
CYAN, PINK, AMBER = "#22d3ee", "#f472b6", "#fbbf24"
VIOLET, SKY, ROSE, ORANGE, LIME = "#a78bfa", "#38bdf8", "#fb7185", "#fb923c", "#a3e635"
RAMP = ["#155e75", "#0891b2", "#22d3ee", "#f472b6"]  # contribution levels 1..4

# NEXERA's own brand, used only on the NEXERA card
NX_INDIGO, NX_TEAL = "#6366f1", "#0be5ba"

LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "C++": "#f34b7d", "Python": "#3572a5",
    "C": "#555555", "Java": "#b07219", "Go": "#00add8", "Rust": "#dea584", "SQL": "#e38c00",
    "Dart": "#00b4ab", "PLpgSQL": "#336790", "Kotlin": "#a97bff", "Swift": "#f05138",
    "PHP": "#4f5d95", "C#": "#178600", "Ruby": "#701516", "Objective-C": "#438eff",
}
IGNORED_LANGS = {"HTML", "CSS", "SCSS", "Shell", "Batchfile", "PowerShell", "Dockerfile", "Procfile", "CMake", "Makefile"}


# ------------------------------------------------------------------ helpers

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def shade(hex_color, f):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[k:k + 2], 16) for k in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c * f))) for c in (r, g, b)))


def pts(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def cube(cx, cy, a, h, color, s=0.86, cls="", style=""):
    """Isometric block standing on the diamond centred at (cx, cy)."""
    w, v = a * s, a * s / 2
    T, R, B, L = (cx, cy - v), (cx + w, cy), (cx, cy + v), (cx - w, cy)
    up = lambda p: (p[0], p[1] - h)
    attrs = (f' class="{cls}"' if cls else "") + (f' style="{style}"' if style else "")
    return (
        f"<g{attrs}>"
        f'<polygon points="{pts([up(L), up(B), B, L])}" fill="{shade(color, .72)}"/>'
        f'<polygon points="{pts([up(B), up(R), R, B])}" fill="{shade(color, .52)}"/>'
        f'<polygon points="{pts([up(T), up(R), up(B), up(L)])}" fill="{color}" stroke="{shade(color, 1.3)}" stroke-width="0.6"/>'
        f"</g>"
    )


BASE_CSS = f"""
  .sans {{ font-family: {SANS}; }}
  .mono {{ font-family: {MONO}; }}
  .in {{ animation: fadein .8s cubic-bezier(.2,.8,.2,1) both; }}
  .rise {{ animation: rise .9s cubic-bezier(.2,.8,.2,1) both; }}
  .blink {{ animation: blink 1s steps(1) infinite; }}
  .pulse {{ animation: pulse 2.4s ease-in-out infinite; }}
  .ping {{ animation: ping 2.2s cubic-bezier(0,0,.2,1) infinite; transform-box: fill-box; transform-origin: center; }}
  .bob {{ animation: bob 6s ease-in-out infinite; }}
  .twinkle {{ animation: twinkle 3s ease-in-out infinite; }}
  .drift {{ animation: drift linear infinite; }}
  @keyframes fadein {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(26px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes blink {{ 50% {{ opacity: 0; }} }}
  @keyframes pulse {{ 0%, 100% {{ opacity: .4; }} 50% {{ opacity: 1; }} }}
  @keyframes ping {{ 0% {{ transform: scale(1); opacity: .7; }} 80%, 100% {{ transform: scale(3); opacity: 0; }} }}
  @keyframes bob {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-12px); }} }}
  @keyframes twinkle {{ 0%, 100% {{ opacity: .15; }} 50% {{ opacity: .9; }} }}
  @keyframes drift {{ from {{ transform: translateX(0); }} to {{ transform: translateX(var(--d, -200px)); }} }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
"""

GLOW_DEFS = """
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>"""


def svg(w, h, body, defs="", css="", label="", rx=16, comet=None, frame=True, accent=CYAN):
    """A dark card with a subtle border, HUD corners and an optional running light."""
    deco = ""
    if frame:
        deco = f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="url(#cardbg)" stroke="{LINE}"/>'
        c, k = 14, 18
        for x, y, dx, dy in ((c, c, 1, 1), (w - c, c, -1, 1), (c, h - c, 1, -1), (w - c, h - c, -1, -1)):
            deco += f'<path d="M{x} {y + dy * k} V{y} H{x + dx * k}" stroke="{accent}" stroke-opacity=".6" stroke-width="1.5"/>'
        if comet:
            deco += (
                f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{rx}" pathLength="1000" fill="none" '
                f'stroke="url(#cometg)" stroke-width="2" stroke-linecap="round" stroke-dasharray="140 860" filter="url(#glow)">'
                f'<animate attributeName="stroke-dashoffset" from="1000" to="0" dur="7s" repeatCount="indefinite"/></rect>'
            )
        if label:
            deco += (
                f'<g class="in"><text x="40" y="52" class="mono" font-size="13" letter-spacing="3" fill="{FG3}">'
                f'<tspan fill="{accent}">[ {esc(label[0])} ]</tspan>  {esc(label[1])}</text></g>'
            )
    c1, c2 = comet or (CYAN, PINK)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" role="img">
<style>{BASE_CSS}{css}</style>
<defs>
  <linearGradient id="cardbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{PANEL}"/><stop offset="1" stop-color="{BG0}"/></linearGradient>
  <linearGradient id="cometg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>
  <clipPath id="clip"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>
  {GLOW_DEFS}
  {defs}
</defs>
{deco}
<g clip-path="url(#clip)">
{body}
</g>
</svg>
"""


def write(path, content):
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(path.relative_to(ROOT).as_posix(), f"{len(content) / 1024:.0f} KB")


def chips(x, y, items, color, fs=12):
    out = []
    for name in items:
        w = len(name) * fs * CW + 22
        out.append(
            f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="24" rx="12" fill="{color}" fill-opacity=".1" stroke="{color}" stroke-opacity=".4"/>'
            f'<text x="{x + 11:.1f}" y="{y + 16}" class="mono" font-size="{fs}" fill="{color}">{esc(name)}</text>'
        )
        x += w + 8
    return "".join(out)


# ------------------------------------------------------------------ hero

def typing(phrases, x, y, fs, type_s=0.065, hold=1.9, erase_s=0.025, gap=0.5):
    """Terminal-style typing loop with one shared cursor, driven by SMIL so it runs everywhere."""
    cw = fs * CW
    starts, t = [], 0.0
    for p in phrases:
        starts.append(t)
        t += 0.3 + len(p) * (type_s + erase_s) + hold + gap
    total = t
    width_keys, texts = [(0.0, 0.0)], []
    for k, p in enumerate(phrases):
        t0, n = starts[k] + 0.3, len(p)
        for i in range(n + 1):
            width_keys.append((t0 + i * type_s, i * cw))
        t_hold = t0 + n * type_s + hold
        for i in range(n, -1, -1):
            width_keys.append((t_hold + (n - i) * erase_s, i * cw))
        vis = ";".join("1" if j == k else "0" for j in range(len(phrases)))
        times = ";".join(f"{starts[j] / total:.4f}" for j in range(len(phrases)))
        texts.append(
            f'<text x="{x}" y="{y}" class="mono" font-size="{fs}" fill="{FG}" textLength="{n * cw:.1f}" '
            f'lengthAdjust="spacingAndGlyphs" opacity="{1 if k == 0 else 0}">{esc(p)}'
            f'<animate attributeName="opacity" values="{vis}" keyTimes="{times}" dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"/></text>'
        )
    keys = sorted({round(t / total, 4): w for t, w in width_keys}.items())
    assert keys[-1][0] <= 1
    kt = ";".join(f"{t:.4f}" for t, _ in keys)
    widths = ";".join(f"{w:.1f}" for _, w in keys)
    xs = ";".join(f"{x + w:.1f}" for _, w in keys)
    return f"""
<clipPath id="typeclip"><rect x="{x}" y="{y - fs}" height="{fs * 1.5}" width="0">
  <animate attributeName="width" values="{widths}" keyTimes="{kt}" dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"/>
</rect></clipPath>
<g clip-path="url(#typeclip)">{''.join(texts)}</g>
<rect y="{y - fs * 0.82}" width="{cw * 0.9:.1f}" height="{fs * 1.02:.1f}" fill="{CYAN}" class="blink" x="{x}">
  <animate attributeName="x" values="{xs}" keyTimes="{kt}" dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"/>
</rect>"""


def hero():
    W, H = 1000, 470
    rng = random.Random(7)
    hz = 318

    stars = "".join(
        f'<circle cx="{rng.uniform(10, W - 10):.0f}" cy="{rng.uniform(10, hz - 40):.0f}" r="{rng.uniform(.5, 1.6):.1f}" '
        f'fill="#fff" class="twinkle" style="animation-delay:-{rng.uniform(0, 3):.1f}s;animation-duration:{rng.uniform(2, 5):.1f}s"/>'
        for _ in range(100)
    )
    verticals = "".join(
        f'<line x1="{500 + k * 9}" y1="{hz}" x2="{500 + k * 85}" y2="{H}" stroke="{PINK}" stroke-opacity=".35"/>'
        for k in range(-24, 25)
    )
    horizontals = "".join(
        f'<line x1="0" x2="{W}" y1="{hz}" y2="{hz}" stroke="{PINK}" stroke-opacity=".6" class="floor" style="animation-delay:-{k * 0.4:.1f}s"/>'
        for k in range(8)
    )
    # synthwave sun with cut bands
    bands = "".join(f'<rect x="360" y="{hz - 62 + k * 13}" width="280" height="{2 + k * 1.3:.1f}" fill="#000"/>' for k in range(5))

    def cluster(ox, oy, spec, colors, a=20, delay=0):
        out = []
        for (i, j, levels) in sorted(spec, key=lambda c: (c[0] + c[1], c[0])):
            cx, cy = ox + (i - j) * a, oy + (i + j) * a / 2
            for lv in range(levels):
                out.append(cube(cx, cy - lv * a * 0.9, a, a * 0.9, colors[min(len(colors) - 1, lv)], s=0.92))
        return f'<g class="bob" style="animation-delay:-{delay}s">{"".join(out)}</g>'

    left = cluster(105, 338, [(0, 0, 3), (1, 0, 2), (0, 1, 1), (1, 1, 4), (2, 1, 1), (1, 2, 2)], ["#0e7490", "#06b6d4", CYAN, "#a5f3fc"])
    right = cluster(890, 330, [(0, 0, 2), (1, 0, 4), (0, 1, 3), (1, 1, 1), (2, 0, 1), (0, 2, 1)], ["#9d174d", "#db2777", PINK, "#fbcfe8"], delay=3)
    floaters = "".join(
        f'<g class="bob" style="animation-delay:-{d}s;animation-duration:{dur}s">{cube(x, y, 9, 9, c, s=1)}</g>'
        for x, y, d, dur, c in ((300, 110, 1, 5, CYAN), (700, 90, 2.5, 7, PINK), (90, 90, 4, 6, AMBER),
                                (930, 300, 1.5, 5.5, VIOLET), (60, 280, 3, 6.5, PINK), (860, 120, 2, 6, CYAN))
    )
    shadows = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="70" ry="14" fill="{c}" opacity=".25" filter="url(#soft)" class="pulse"/>'
        for x, y, c in ((120, 420, CYAN), (905, 412, PINK))
    )

    phrases = [
        "Full-stack developer.",
        "Founder & CEO at NEXERA.",
        "Building tools for AI agents.",
        "Turning ideas into shipped products.",
    ]
    fs = 22
    tx = 500 - (max(len(p) for p in phrases) + 2) * fs * CW / 2

    css = f"""
  .floor {{ animation: floor 3.2s cubic-bezier(.55,0,1,.45) infinite; }}
  @keyframes floor {{ from {{ transform: translateY(0); opacity: 0; }} 15% {{ opacity: .8; }} to {{ transform: translateY({H - hz}px); opacity: 1; }} }}"""

    defs = f"""
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#020208"/><stop offset=".55" stop-color="#0d0820"/><stop offset="1" stop-color="#1f0a2e"/></linearGradient>
  <radialGradient id="halo" cx="500" cy="{hz}" r="460" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{PINK}" stop-opacity=".28"/><stop offset=".5" stop-color="{VIOLET}" stop-opacity=".08"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
  <linearGradient id="sun" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{AMBER}"/><stop offset=".6" stop-color="{ORANGE}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>
  <mask id="sunmask"><rect width="{W}" height="{hz}" fill="#fff"/>{bands}</mask>
  <linearGradient id="floorfade" x1="0" y1="{hz}" x2="0" y2="{H}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".35" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>
  <mask id="floormask"><rect y="{hz}" width="{W}" height="{H - hz}" fill="url(#floorfade)"/></mask>
  <linearGradient id="horizon" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset=".3" stop-color="{CYAN}"/><stop offset=".7" stop-color="{PINK}"/><stop offset="1" stop-color="{PINK}" stop-opacity="0"/></linearGradient>
  <linearGradient id="name" x1="0" y1="0" x2="1" y2="0" gradientUnits="objectBoundingBox">
    <stop offset="0" stop-color="#ffffff"/><stop offset=".35" stop-color="{CYAN}"/><stop offset=".65" stop-color="{PINK}"/><stop offset="1" stop-color="#ffffff"/>
    <animateTransform attributeName="gradientTransform" type="translate" values="-1 0;1 0" dur="6s" repeatCount="indefinite"/>
  </linearGradient>"""

    body = f"""
<rect width="{W}" height="{H}" fill="url(#sky)"/>
<rect width="{W}" height="{H}" fill="url(#halo)"/>
{stars}
<circle cx="500" cy="{hz}" r="120" fill="{PINK}" opacity=".35" filter="url(#soft)"/>
<circle cx="500" cy="{hz}" r="120" fill="url(#sun)" mask="url(#sunmask)" opacity=".92"/>
<rect x="0" y="{hz}" width="{W}" height="{H - hz}" fill="#0a0414"/>
<g mask="url(#floormask)">{verticals}{horizontals}</g>
<rect x="0" y="{hz - 1}" width="{W}" height="2" fill="url(#horizon)" filter="url(#glow)"/>
{shadows}
<g class="rise" style="animation-delay:.2s">{left}</g>
<g class="rise" style="animation-delay:.35s">{right}</g>
{floaters}

<g class="in">
  <circle cx="42" cy="38" r="4" fill="{CYAN}"/><circle cx="42" cy="38" r="4" fill="{CYAN}" class="ping"/>
  <text x="56" y="43" class="mono" font-size="13" letter-spacing="2.5" fill="{FG2}">SYS://ALOK</text>
  <text x="{W - 40}" y="43" text-anchor="end" class="mono" font-size="13" letter-spacing="2.5" fill="{FG2}">STATUS <tspan fill="{AMBER}">SHIPPING</tspan></text>
</g>
<g class="in" style="animation-delay:.1s">
  <text x="500" y="112" text-anchor="middle" class="mono" font-size="16" letter-spacing="8" fill="{CYAN}">HELLO WORLD, I'M</text>
</g>
<g class="in" style="animation-delay:.25s">
  <text x="500" y="192" text-anchor="middle" class="sans" font-size="78" font-weight="800" letter-spacing="3" fill="{PINK}" opacity=".5" filter="url(#soft)">ALOK CHAUDHARY</text>
  <text x="500" y="192" text-anchor="middle" class="sans" font-size="78" font-weight="800" letter-spacing="3" fill="url(#name)">ALOK CHAUDHARY</text>
</g>
<g class="in" style="animation-delay:.45s">
  <rect x="{tx - 18:.1f}" y="222" width="{W - 2 * tx + 36:.1f}" height="46" rx="10" fill="#05030c" fill-opacity=".72" stroke="{LINE}"/>
  <text x="{tx:.1f}" y="252" class="mono" font-size="{fs}" fill="{PINK}">&gt;</text>
  {typing(phrases, tx + 2 * fs * CW, 252, fs)}
</g>"""
    return svg(W, H, body, defs, css, frame=False, rx=18)


# ------------------------------------------------------------------ project tiles

def pill_width(text, fs=11, spacing=1.5):
    return 23 + len(text) * (fs * CW + spacing) + 14


def tile(w, h, accent, tag, title, meta, desc, stack, motif, stat="", link=True, defs="", css=""):
    lines = "".join(f'<tspan x="28" y="{206 + k * 22}">{esc(t)}</tspan>' for k, t in enumerate(desc))
    body = f"""
<rect width="{w}" height="{h}" fill="url(#tglow)"/>
{motif}
<g class="in">
  <rect x="28" y="28" width="{pill_width(tag):.0f}" height="24" rx="12" fill="{accent}" fill-opacity=".14" stroke="{accent}" stroke-opacity=".5"/>
  <circle cx="41" cy="40" r="3.5" fill="{accent}" class="pulse"/>
  <text x="51" y="44" class="mono" font-size="11" letter-spacing="1.5" fill="{accent}">{esc(tag)}</text>
</g>
<g class="in" style="animation-delay:.15s">
  <text x="27" y="112" class="sans" font-size="30" font-weight="800" letter-spacing="-.5" fill="{FG}">{esc(title)}</text>
  <rect x="28" y="126" width="36" height="3" rx="1.5" fill="{accent}"/>
  <text x="28" y="154" class="mono" font-size="12" letter-spacing="1" fill="{FG3}">{esc(meta)}</text>
  <text class="sans" font-size="14.5" fill="{FG2}">{lines}</text>
  {chips(28, h - 62, stack, accent)}
  {f'<text x="{w - 28}" y="{h - 45}" text-anchor="end" class="mono" font-size="12.5" fill="{FG}">{esc(stat)}</text>' if stat else ''}
  {f'<text x="{w - 28}" y="44" text-anchor="end" class="mono" font-size="16" fill="{accent}">&#8599;</text>' if link else ''}
</g>"""
    tglow = f'<radialGradient id="tglow" cx="{w * .8:.0f}" cy="40" r="{w * .7:.0f}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{accent}" stop-opacity=".16"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient>'
    return svg(w, h, body, tglow + defs, css, accent=accent, comet=(accent, shade(accent, .6)))


def portfolio_tile():
    W, H = 1000, 320
    x0, x1, y0, y1 = 520, 972, 24, 296
    ridges = [
        ([(0, 190), (60, 120), (110, 150), (170, 70), (230, 140), (300, 95), (360, 150), (452, 110), (452, 272), (0, 272)], "#3b1d4a"),
        ([(0, 210), (80, 160), (150, 190), (220, 130), (290, 185), (370, 150), (452, 190), (452, 272), (0, 272)], "#2a1236"),
        ([(0, 240), (100, 205), (190, 235), (280, 200), (380, 232), (452, 215), (452, 272), (0, 272)], "#170a20"),
    ]
    mountains = "".join(
        f'<polygon points="{pts([(x0 + x, y0 + y) for x, y in r])}" fill="{c}"/>' for r, c in ridges
    )
    snow = "".join(
        f'<polygon points="{pts([(x0 + px, y0 + py), (x0 + px - 16, y0 + py + 22), (x0 + px + 14, y0 + py + 20)])}" fill="#fde7f3" opacity=".85"/>'
        for px, py in ((170, 70), (300, 95), (60, 120))
    )
    clouds = "".join(
        f'<g class="drift" style="--d:{-300 - k * 60}px;animation-duration:{26 + k * 9}s;animation-delay:-{k * 7}s">'
        f'<ellipse cx="{x0 + 80 + k * 150}" cy="{y0 + 60 + k * 18}" rx="{46 - k * 6}" ry="9" fill="#fff" opacity=".12"/>'
        f'<ellipse cx="{x0 + 110 + k * 150}" cy="{y0 + 54 + k * 18}" rx="{30 - k * 4}" ry="8" fill="#fff" opacity=".1"/></g>'
        for k in range(3)
    )
    road = f"M{x0 + 30} {y0 + 268} C{x0 + 140} {y0 + 236} {x0 + 210} {y0 + 262} {x0 + 300} {y0 + 236} S{x0 + 420} {y0 + 226} {x0 + 452} {y0 + 230}"
    motif = f"""
<g>
  <clipPath id="world"><rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="14"/></clipPath>
  <g clip-path="url(#world)">
    <rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="url(#dusk)"/>
    <circle cx="{x0 + 330}" cy="{y0 + 120}" r="40" fill="url(#psun)" opacity=".95"/>
    <circle cx="{x0 + 330}" cy="{y0 + 120}" r="60" fill="{ORANGE}" opacity=".25" filter="url(#soft)"/>
    {clouds}
    {mountains}{snow}
    <path d="{road}" stroke="{AMBER}" stroke-opacity=".55" stroke-width="2" stroke-dasharray="6 6"/>
    <circle r="5" fill="{AMBER}" filter="url(#glow)"><animateMotion dur="7s" repeatCount="indefinite" path="{road}" rotate="auto"/></circle>
  </g>
  <rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="14" stroke="{ORANGE}" stroke-opacity=".35"/>
</g>"""
    defs = f"""
  <linearGradient id="dusk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b1035"/><stop offset=".6" stop-color="#6b2147"/><stop offset="1" stop-color="#c2410c"/></linearGradient>
  <linearGradient id="psun" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{AMBER}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>"""
    body_tag = "LIVE · 3D PORTFOLIO"
    lines = "".join(f'<tspan x="40" y="{184 + k * 22}">{esc(t)}</tspan>' for k, t in enumerate([
        "My portfolio as an explorable 3D world, set in a",
        "Himalayan valley. Projects, lab, career and",
        "achievements, every part of it in 3D.",
    ]))
    body = f"""
<rect width="{W}" height="{H}" fill="url(#tglow)"/>
{motif}
<g class="in">
  <rect x="40" y="40" width="{pill_width(body_tag):.0f}" height="24" rx="12" fill="{ORANGE}" fill-opacity=".14" stroke="{ORANGE}" stroke-opacity=".5"/>
  <circle cx="53" cy="52" r="3.5" fill="{ORANGE}" class="pulse"/>
  <text x="63" y="56" class="mono" font-size="11" letter-spacing="1.5" fill="{ORANGE}">{esc(body_tag)}</text>
  <text x="38" y="138" class="sans" font-size="44" font-weight="800" letter-spacing="-1" fill="url(#ptitle)">World of Alok</text>
  <text class="sans" font-size="15.5" fill="{FG2}">{lines}</text>
  {chips(40, 262, ["Three.js", "Next.js 16", "WebGL"], ORANGE)}
  <rect x="306" y="258" width="176" height="32" rx="16" fill="{ORANGE}"/>
  <text x="394" y="279" text-anchor="middle" class="mono" font-size="13" font-weight="700" fill="#1a0800">Explore it &#8599;</text>
</g>"""
    defs += f"""
  <radialGradient id="tglow" cx="300" cy="60" r="600" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{ORANGE}" stop-opacity=".12"/><stop offset="1" stop-color="{ORANGE}" stop-opacity="0"/></radialGradient>
  <linearGradient id="ptitle" x1="0" x2="1"><stop offset="0" stop-color="{AMBER}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>"""
    return svg(W, H, body, defs, accent=ORANGE, comet=(AMBER, PINK))


def agent_bridge_tile(version="", installs=None):
    a = VIOLET
    path_go, path_back = "M332 72 H392", "M392 106 H332"
    packets = "".join(
        f'<rect x="-6" y="-4" width="12" height="8" rx="2" fill="{a}" filter="url(#glow)">'
        f'<animateMotion dur="2.4s" begin="{k * .8}s" repeatCount="indefinite" path="{path_go}"/></rect>'
        for k in range(3)
    )
    acks = "".join(
        f'<circle r="4" fill="{LIME}"><animateMotion dur="2.4s" begin="{1.2 + k * 1.2}s" repeatCount="indefinite" path="{path_back}"/></circle>'
        for k in range(2)
    )
    motif = f"""
<g class="in" style="animation-delay:.2s">
  <rect x="244" y="50" width="88" height="74" rx="10" fill="#120d22" stroke="{a}" stroke-opacity=".6"/>
  <text x="288" y="80" text-anchor="middle" class="mono" font-size="12" fill="{FG}">agent</text>
  <text x="288" y="98" text-anchor="middle" class="mono" font-size="10" fill="{FG3}">plans</text>
  <rect x="392" y="50" width="72" height="74" rx="10" fill="#120d22" stroke="{a}" stroke-opacity=".6"/>
  <text x="428" y="80" text-anchor="middle" class="mono" font-size="12" fill="{FG}">IDE</text>
  <text x="428" y="98" text-anchor="middle" class="mono" font-size="10" fill="{FG3}">builds</text>
  <path d="{path_go}" stroke="{a}" stroke-opacity=".5" stroke-dasharray="3 4"/>
  <path d="{path_back}" stroke="{LIME}" stroke-opacity=".4" stroke-dasharray="3 4"/>
  <text x="362" y="62" text-anchor="middle" class="mono" font-size="9" fill="{a}">task</text>
  <text x="362" y="122" text-anchor="middle" class="mono" font-size="9" fill="{LIME}">done</text>
  {packets}{acks}
</g>"""
    stat = f"v{version} · {installs:,} installs" if installs else ""
    return tile(490, 330, a, "VS CODE EXTENSION", "Agent Bridge", "Open VSX · MIT",
                ["Lets Claude Code or any AI agent hand tasks to", "your IDE's AI chat, and know when they're done."],
                ["JavaScript", "VS Code API"], motif, stat)


def nexera_app_tile():
    a = AMBER
    cards = "".join(
        f'<rect x="338" y="{52 + k * 30}" width="64" height="22" rx="5" fill="{c}" fill-opacity=".85"/>'
        f'<rect x="344" y="{58 + k * 30}" width="{24 + (k % 3) * 8}" height="4" rx="2" fill="#000" fill-opacity=".45"/>'
        f'<rect x="344" y="{66 + k * 30}" width="18" height="3" rx="1.5" fill="#000" fill-opacity=".3"/>'
        for k, c in enumerate([AMBER, "#a78bfa", "#fb923c", CYAN, AMBER, PINK, "#a78bfa", "#fb923c"])
    )
    motif = f"""
<g class="bob" style="animation-duration:7s">
  <rect x="324" y="26" width="92" height="150" rx="16" fill="#0d0a04" stroke="{a}" stroke-opacity=".7" stroke-width="1.5"/>
  <rect x="356" y="32" width="28" height="5" rx="2.5" fill="{a}" fill-opacity=".5"/>
  <clipPath id="screen"><rect x="332" y="44" width="76" height="124" rx="8"/></clipPath>
  <g clip-path="url(#screen)">
    <g>{cards}<animateTransform attributeName="transform" type="translate" values="0 0;0 -120" dur="6s" repeatCount="indefinite"/></g>
  </g>
</g>
<ellipse cx="370" cy="196" rx="60" ry="8" fill="{a}" opacity=".2" filter="url(#soft)"/>"""
    return tile(490, 330, a, "FLUTTER · ANDROID", "Nexera App", "Google Play · APK",
                ["The NEXERA mobile app: IPUNEX notes and PYQs,", "video courses, SkillX DSA practice and doubts."],
                ["Flutter", "Dart", "Android"], motif)


def okeanos_tile():
    a = SKY
    x0, y0, w, h = 236, 64, 196, 104
    bands = ["#fb923c", "#f59e0b", "#14b8a6", "#0891b2", "#0369a1", "#0c4a6e", "#082f49"]
    layer = "".join(
        f'<rect x="{x0}" y="{y0 + k * h / len(bands):.1f}" width="{w}" height="{h / len(bands) + .5:.1f}" fill="{c}" opacity=".85"/>'
        for k, c in enumerate(bands)
    )
    wave = f"M{x0 - 200} {y0}"
    for x in range(-200, w + 201, 8):
        wave += f" L{x0 + x} {y0 + 4 * math.sin(x / 14):.1f}"
    wave += f" L{x0 + w + 200} {y0 - 20} L{x0 - 200} {y0 - 20} Z"
    motif = f"""
<g class="in" style="animation-delay:.2s">
  <clipPath id="sea"><rect x="{x0}" y="{y0 - 10}" width="{w}" height="{h + 10}" rx="8"/></clipPath>
  <g clip-path="url(#sea)">
    {layer}
    <path d="{wave}" fill="{PANEL}"><animateTransform attributeName="transform" type="translate" values="0 0;-88 0" dur="3s" repeatCount="indefinite"/></path>
  </g>
  <rect x="{x0}" y="{y0 - 10}" width="{w}" height="{h + 10}" rx="8" stroke="{a}" stroke-opacity=".4"/>
  <text x="{x0 + w + 8}" y="{y0 + 8}" class="mono" font-size="9.5" fill="{FG3}">0 m</text>
  <text x="{x0 + w + 8}" y="{y0 + h}" class="mono" font-size="9.5" fill="{FG3}">1000 m</text>
  <g class="bob" style="animation-duration:5s">
    <rect x="{x0 + 92}" y="24" width="28" height="12" rx="2" fill="{FG2}"/>
    <rect x="{x0 + 70}" y="27" width="20" height="6" fill="{a}"/><rect x="{x0 + 122}" y="27" width="20" height="6" fill="{a}"/>
    <path d="M{x0 + 106} 38 L{x0 + 80} {y0 - 2} M{x0 + 106} 38 L{x0 + 132} {y0 - 2}" stroke="{a}" stroke-opacity=".5" stroke-dasharray="2 3" class="pulse"/>
  </g>
</g>"""
    return tile(490, 330, a, "SIH 2026 · TEAM", "Okeanos", "SIH26066 · MoES",
                ["Rebuilds the North Indian Ocean's temperature", "down to 1000 m from satellite surface data alone."],
                ["Python", "PyTorch", "XGBoost"], motif, link=False)


def netwm_tile():
    a = ROSE
    nodes = [(262, 60), (310, 40), (300, 100), (360, 74), (410, 44), (420, 108), (460, 76), (350, 130)]
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4), (3, 5), (4, 6), (5, 6), (2, 7), (7, 5)]
    lines = "".join(f'<line x1="{nodes[i][0]}" y1="{nodes[i][1]}" x2="{nodes[j][0]}" y2="{nodes[j][1]}" stroke="{FG3}" stroke-opacity=".6"/>' for i, j in edges)
    dots = "".join(
        f'<circle cx="{x}" cy="{y}" r="5" fill="{a if k in (3, 5) else FG2}"/>'
        + (f'<circle cx="{x}" cy="{y}" r="5" fill="{a}" class="ping" style="animation-delay:{k * .4:.1f}s"/>' if k in (3, 5) else "")
        for k, (x, y) in enumerate(nodes)
    )
    flow = "".join(
        f'<circle r="2.5" fill="{a}"><animateMotion dur="{1.6 + k * .3:.1f}s" repeatCount="indefinite" '
        f'path="M{nodes[i][0]} {nodes[i][1]} L{nodes[j][0]} {nodes[j][1]}"/></circle>'
        for k, (i, j) in enumerate([(0, 1), (2, 3), (3, 5), (4, 6)])
    )
    motif = f'<g class="in" style="animation-delay:.2s">{lines}{flow}{dots}</g>'
    return tile(490, 330, a, "SIH 2026 · TEAM", "NetWM", "PS 26153 · NTRO",
                ["Forecasts network attacks 5 minutes ahead with a", "world model. PR-AUC 0.677 vs 0.139 baseline."],
                ["Python", "PyTorch", "FastAPI"], motif)


def wa_guard_tile():
    a = "#25d366"  # WhatsApp green, this tile only
    x0, y0, w, h = 520, 32, 452, 286
    bx = x0 + 20

    def bubble(y, bh, bw, who, who_col, lines, fill="#111a22", extra=""):
        text = "".join(f'<tspan x="{bx + 14}" y="{y + 38 + k * 19}">{t}</tspan>' for k, t in enumerate(lines))
        return (
            f'<rect x="{bx}" y="{y}" width="{bw}" height="{bh}" rx="12" fill="{fill}"/>'
            f'<text x="{bx + 14}" y="{y + 19}" class="mono" font-size="10.5" fill="{who_col}">{esc(who)}</text>'
            f'<text class="sans" font-size="13.5" fill="{FG}">{text}</text>{extra}'
        )

    link = f'<tspan fill="{SKY}" text-decoration="underline">'
    spam = bubble(150, 66, 300, "+91 98xxx xxx21", FG3,
                  ["Join fast!! free passes, link here", f'{link}chat.whatsapp.com/Kx7Q9...</tspan>'])
    kept = bubble(230, 50, 300, "Team Nexera", a, [f'Register: {link}nexera.in/events/hackfest</tspan>'],
                  extra=f'<rect x="{bx + 316}" y="{230 + 15}" width="62" height="20" rx="10" fill="{a}" fill-opacity=".15" stroke="{a}" stroke-opacity=".5"/>'
                        f'<text x="{bx + 347}" y="{230 + 29}" text-anchor="middle" class="mono" font-size="10.5" fill="{a}">kept &#10003;</text>')
    motif = f"""
<g class="in" style="animation-delay:.2s">
  <rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="14" fill="#070d0b" stroke="{a}" stroke-opacity=".35"/>
  <circle cx="{x0 + 34}" cy="{y0 + 24}" r="14" fill="{a}" fill-opacity=".15"/>
  <path d="M{x0 + 34} {y0 + 15} l7 3 v5 c0 4.5 -3 7.5 -7 9 c-4 -1.5 -7 -4.5 -7 -9 v-5 Z" stroke="{a}" stroke-width="1.6" stroke-linejoin="round"/>
  <text x="{x0 + 58}" y="{y0 + 22}" class="sans" font-size="14" font-weight="700" fill="{FG}">IPUNEX · Nexera</text>
  <text x="{x0 + 58}" y="{y0 + 38}" class="mono" font-size="10" fill="{FG3}">guard active · delete-only</text>
  <circle cx="{x0 + w - 62}" cy="{y0 + 24}" r="4" fill="{a}" class="pulse"/>
  <text x="{x0 + w - 20}" y="{y0 + 28}" text-anchor="end" class="mono" font-size="11" letter-spacing="1" fill="{a}">LIVE</text>
  <line x1="{x0}" x2="{x0 + w}" y1="{y0 + 48}" y2="{y0 + 48}" stroke="{a}" stroke-opacity=".2"/>
  {bubble(92, 48, 260, "Riya", PINK, ["Sem 3 notes are up on the app"])}
  <g class="wspam" opacity="0">{spam}
    <rect x="{bx}" y="150" width="300" height="66" rx="12" stroke="{ROSE}" stroke-width="1.5" class="wflag" opacity="0"/>
    <text x="{bx + 316}" y="187" class="mono wflag" font-size="10.5" fill="{ROSE}" opacity="0">spam link</text>
  </g>
  <g class="wgone" opacity="0">
    <rect x="{bx}" y="150" width="236" height="40" rx="12" fill="#0d1318" stroke="{FG3}" stroke-opacity=".4" stroke-dasharray="3 3"/>
    <text x="{bx + 14}" y="175" class="sans" font-size="13" font-style="italic" fill="{FG3}">&#8856; deleted by guard in 4s</text>
  </g>
  <g class="wkept">{kept}</g>
</g>"""
    css = """
  .wspam { animation: wspam 9s infinite; }
  .wflag { animation: wflag 9s infinite; }
  .wgone { animation: wgone 9s infinite; }
  .wkept { animation: wkept 9s infinite; }
  @keyframes wspam { 0%, 8% { opacity: 0; } 14%, 44% { opacity: 1; } 50%, 100% { opacity: 0; } }
  @keyframes wflag { 0%, 26% { opacity: 0; } 30%, 36% { opacity: 1; } 39% { opacity: .3; } 42%, 100% { opacity: 1; } }
  @keyframes wgone { 0%, 48% { opacity: 0; } 54%, 94% { opacity: 1; } 100% { opacity: 0; } }
  @keyframes wkept { 0%, 60% { opacity: 0; } 66%, 94% { opacity: 1; } 100% { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .wgone, .wkept { opacity: 1; } }
"""
    return tile(1000, 350, a, "WHATSAPP BOT · 24/7", "WA Spam Guard", "Delete-only · 6 per minute cap",
                ["Keeps NEXERA's WhatsApp groups clean 24/7 from a",
                 "spare Android phone. Spam and invite links vanish in",
                 "seconds, while admins, team and Nexera links stay."],
                ["Node.js", "Baileys", "Termux"], motif, link=False, css=css)


# ------------------------------------------------------------------ NEXERA card (its own brand)

ICONS = {
    "book": "M3 5.5c3-1.6 6.3-1.6 9 .5 2.7-2.1 6-2.1 9-.5V19c-3-1.4-6.3-1.4-9 .6-2.7-2-6-2-9-.6Z M12 6v13.6",
    "bolt": "M13.5 2 4.5 13.5H11L10 22l9.5-12H13Z",
    "users": "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M2 21c0-4 3-6.5 7-6.5s7 2.5 7 6.5 M17 3.5a3.5 3.5 0 0 1 0 7 M19 14.5c2 .6 3.5 2.6 3.5 6",
}


def nexera():
    W, H = 1000, 360
    x0 = 48
    logo = base64.b64encode((TOOLS / "nexera_logo.jpg").read_bytes()).decode()
    pillars = [
        ("book", "Education", "IPUNEX notes, PYQs, courses and SkillX"),
        ("bolt", "Events", "Tech events that bring builders together"),
        ("users", "Community", "Students learning and growing together"),
    ]
    px, pw, ph, gap, py0 = 548, 404, 72, 14, 80
    tiles = []
    for k, (icon, title, sub) in enumerate(pillars):
        y = py0 + k * (ph + gap)
        tiles.append(f"""
<g class="in" style="animation-delay:{.35 + k * .12:.2f}s">
  <rect x="{px}" y="{y}" width="{pw}" height="{ph}" rx="12" fill="#0d0e1f" stroke="{NX_INDIGO}" stroke-opacity=".45"/>
  <rect x="{px + 20}" y="{y + 14}" width="44" height="44" rx="10" fill="{NX_TEAL}" fill-opacity=".1" stroke="{NX_TEAL}" stroke-opacity=".4"/>
  <g transform="translate({px + 30} {y + 24})"><path d="{ICONS[icon]}" stroke="{NX_TEAL}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></g>
  <text x="{px + 82}" y="{y + 32}" class="sans" font-size="18" font-weight="700" fill="{FG}">{esc(title)}</text>
  <text x="{px + 82}" y="{y + 54}" class="sans" font-size="14" fill="{FG2}">{esc(sub)}</text>
</g>""")
    defs = f"""
  <clipPath id="orb"><circle cx="{x0 + 40}" cy="118" r="40"/></clipPath>
  <radialGradient id="nglow" cx="200" cy="120" r="380" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{NX_INDIGO}" stop-opacity=".22"/><stop offset="1" stop-color="{NX_INDIGO}" stop-opacity="0"/></radialGradient>
  <linearGradient id="word" x1="0" x2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#c7c8ff"/></linearGradient>"""
    body = f"""
<rect width="{W}" height="{H}" fill="url(#nglow)"/>
<g class="in" style="animation-delay:.1s">
  <circle cx="{x0 + 40}" cy="118" r="52" fill="{NX_INDIGO}" opacity=".35" filter="url(#soft)" class="pulse"/>
  <image x="{x0}" y="78" width="80" height="80" clip-path="url(#orb)" href="data:image/jpeg;base64,{logo}" xlink:href="data:image/jpeg;base64,{logo}"/>
  <circle cx="{x0 + 40}" cy="118" r="40" stroke="{NX_TEAL}" stroke-opacity=".6" stroke-width="1.5"/>
  <text x="{x0 + 104}" y="114" class="sans" font-size="44" font-weight="900" letter-spacing="8" fill="url(#word)">NEXERA</text>
  <text x="{x0 + 106}" y="142" class="mono" font-size="12.5" letter-spacing="2" fill="{NX_TEAL}">MY STARTUP · FOUNDER &amp; CEO</text>
  <text x="{x0}" y="204" class="sans" font-size="22" font-weight="300" fill="{FG}">Shaping futures.</text>
  <text class="sans" font-size="15.5" fill="{FG2}">
    <tspan x="{x0}" y="240">A student-driven ecosystem that brings education,</tspan>
    <tspan x="{x0}" y="263">events and community together for college students.</tspan>
  </text>
  <rect x="{x0}" y="290" width="206" height="36" rx="18" fill="{NX_INDIGO}"/>
  <text x="{x0 + 103}" y="313" text-anchor="middle" class="mono" font-size="14" font-weight="700" fill="#fff">nexeraofficial.in &#8599;</text>
</g>
{''.join(tiles)}"""
    return svg(W, H, body, defs, label=("03", "COMPANY"), comet=(NX_INDIGO, NX_TEAL), accent=NX_INDIGO)


# ------------------------------------------------------------------ small pieces

def header(num, title, sub="", color=CYAN):
    W, H = 1000, 70
    body = f"""
<g class="in">
  <text x="4" y="42" class="mono" font-size="15" letter-spacing="3" fill="{FG2}"><tspan fill="{color}">[ {num} ]</tspan>  {esc(title)}</text>
  <line x1="{4 + (len(title) + 8) * 15 * CW + 40:.0f}" x2="{W - 4}" y1="37" y2="37" stroke="url(#hl)" stroke-width="1.5"/>
  <circle cx="{W - 6}" cy="37" r="3" fill="{PINK}" class="pulse" filter="url(#glow)"/>
  {f'<text x="{W - 4}" y="62" text-anchor="end" class="mono" font-size="12" fill="{FG3}">{esc(sub)}</text>' if sub else ''}
</g>"""
    defs = f'<linearGradient id="hl" x1="0" x2="1"><stop offset="0" stop-color="{color}" stop-opacity=".9"/><stop offset="1" stop-color="{PINK}" stop-opacity=".1"/></linearGradient>'
    return svg(W, H, body, defs, frame=False, rx=0)


BUTTON_ICONS = {
    "globe": '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c2.6 2.8 3.9 6 3.9 9.5s-1.3 6.7-3.9 9.5c-2.6-2.8-3.9-6-3.9-9.5s1.3-6.7 3.9-9.5Z"/>',
    "linkedin": '<rect x="2.5" y="2.5" width="19" height="19" rx="4"/><path d="M7.5 10.5v6M7.5 7.4v.1M11.5 16.5v-6M11.5 13c0-1.6 1.1-2.6 2.5-2.6s2.5 1 2.5 2.6v3.5"/>',
    "mail": '<rect x="2.5" y="4.5" width="19" height="15" rx="3"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/>',
    "cube": '<path d="M12 2.5 21 7.5v9L12 21.5 3 16.5v-9Z M3 7.5l9 5 9-5 M12 12.5v9"/>',
}


def button(icon, text, color, primary=False):
    w = 64 + len(text) * 15 * CW + 26
    H = 52
    fill, stroke, tcol = (color, color, "#05060a") if primary else ("#0c0f17", color, FG)
    icol = "#05060a" if primary else color
    body = f"""
<rect x="1" y="1" width="{w - 2:.0f}" height="{H - 2}" rx="12" fill="{fill}" stroke="{stroke}" stroke-opacity="{1 if primary else .55}"/>
<g transform="translate(22 14)" stroke="{icol}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none">{BUTTON_ICONS[icon]}</g>
<text x="58" y="32" class="mono" font-size="15" font-weight="700" fill="{tcol}">{esc(text)}</text>"""
    return svg(round(w), H, body, frame=False, rx=12)


def footer():
    W, H = 1000, 200
    waves = []
    for k, (amp, period, op, dur, col) in enumerate(((14, 250, .6, 9, CYAN), (20, 340, .45, 13, PINK), (10, 190, .35, 7, VIOLET))):
        y0 = 132 + k * 14
        d = f"M0 {y0}"
        for x in range(0, 2 * W + 1, 10):
            d += f" L{x} {y0 + amp * math.sin(2 * math.pi * x / period):.1f}"
        d += f" L{2 * W} {H} L0 {H} Z"
        waves.append(f'<path d="{d}" fill="{col}" fill-opacity="{op * .22:.3f}" stroke="{col}" stroke-opacity="{op}" stroke-width="1.2" class="drift" style="--d:-1000px;animation-duration:{dur}s"/>')
    body = f"""
{''.join(waves)}
<g class="in">
  <text x="500" y="62" text-anchor="middle" class="mono" font-size="15" letter-spacing="7" fill="{CYAN}">THANKS FOR STOPPING BY</text>
  <text x="500" y="96" text-anchor="middle" class="sans" font-size="20" fill="{FG}">Let's build something that matters.</text>
</g>"""
    return svg(W, H, body, frame=True, rx=16)


def build_static():
    write(ASSETS / "hero.svg", hero())
    write(ASSETS / "header-projects.svg", header("02", "PROJECTS", "things I have built and shipped"))
    write(ASSETS / "project-portfolio.svg", portfolio_tile())
    write(ASSETS / "project-nexera-app.svg", nexera_app_tile())
    write(ASSETS / "project-okeanos.svg", okeanos_tile())
    write(ASSETS / "project-netwm.svg", netwm_tile())
    write(ASSETS / "project-wa-guard.svg", wa_guard_tile())
    write(ASSETS / "nexera.svg", nexera())
    write(ASSETS / "header-stack.svg", header("04", "TECH ARSENAL", "tools I build with every day"))
    write(ASSETS / "header-snake.svg", header("06", "COMMIT SNAKE", "eats my contributions, redrawn daily", PINK))
    write(ASSETS / "footer.svg", footer())
    write(ASSETS / "btn-portfolio.svg", button("cube", "Portfolio", CYAN, primary=True))
    write(ASSETS / "btn-linkedin.svg", button("linkedin", "LinkedIn", SKY))
    write(ASSETS / "btn-email.svg", button("mail", "Email", PINK))
    write(ASSETS / "btn-nexera.svg", button("globe", "NEXERA", AMBER))


# ------------------------------------------------------------------ live data

def http(url, data=None, token=None, raw=False):
    headers = {"User-Agent": "profile-builder", "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*"}
    if token and "api.github.com" in url:
        headers["Authorization"] = f"bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as r:
        body = r.read()
    return body if raw == "bytes" else body.decode() if raw else json.loads(body)


LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
CAL_QUERY = """query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  weeks { contributionDays { date contributionCount contributionLevel } } } } } }"""


def calendar(login, token):
    if token:
        try:
            p = http("https://api.github.com/graphql", {"query": CAL_QUERY, "variables": {"login": login}}, token)
            weeks = p["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
            return [(dt.date.fromisoformat(d["date"]), d["contributionCount"], LEVELS[d["contributionLevel"]])
                    for w in weeks for d in w["contributionDays"]]
        except Exception as e:
            print(f"GraphQL failed ({e}), using the public page instead")
    html = http(f"https://github.com/users/{login}/contributions", raw=True)
    tips = {m.group(1): m.group(2) for m in re.finditer(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', html)}
    days = []
    for tag in re.findall(r"<td\b[^>]*\bdata-date=[^>]*>", html):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
        n = re.match(r"\s*(\d+)", tips.get(a.get("id", ""), ""))
        days.append((dt.date.fromisoformat(a["data-date"]), int(n.group(1)) if n else 0, int(a.get("data-level", 0))))
    return sorted(days)


def all_time(login, token, first_year):
    """Total contributions across every year since the account was created."""
    years = list(range(first_year, dt.date.today().year + 1))
    if token:
        try:
            parts = " ".join(
                f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") '
                f"{{ contributionCalendar {{ totalContributions }} }}" for y in years
            )
            p = http("https://api.github.com/graphql", {"query": f'{{ user(login: "{login}") {{ {parts} }} }}'}, token)
            return sum(v["contributionCalendar"]["totalContributions"] for v in p["data"]["user"].values())
        except Exception as e:
            print(f"all-time GraphQL failed ({e})")
    total = 0
    for y in years:
        html = http(f"https://github.com/users/{login}/contributions?from={y}-01-01&to={y}-12-31", raw=True)
        m = re.search(r"([\d,]+)\s+contributions?\s+in\s+" + str(y), html)
        total += int(m.group(1).replace(",", "")) if m else 0
    return total


def profile_data(login, token):
    user = http(f"https://api.github.com/users/{login}", token=token)
    langs = {}
    try:
        repos = http(f"https://api.github.com/users/{login}/repos?per_page=100&type=owner", token=token)
        for r in repos:
            if r["fork"] or r["name"].lower() == login.lower():
                continue
            for name, size in http(r["languages_url"], token=token).items():
                if name not in IGNORED_LANGS:
                    langs[name] = langs.get(name, 0) + size
    except Exception as e:
        print(f"language lookup failed ({e})")
    return user, langs


def streaks(days):
    longest = run = 0
    for _, c, _ in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and days[-1][1] == 0 else days
    for _, c, _ in reversed(tail):
        if not c:
            break
        current += 1
    return current, longest


def plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


# ------------------------------------------------------------------ terminal

GLYPHS = {
    "A": [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "C": [".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX"],
}


def monogram(text, cx, cy, cell=15, gap=3):
    """Pixel-font initials, like neofetch's text logos."""
    step = cell + gap
    width = len(text) * 5 * step + (len(text) - 1) * step - gap
    x0, y0 = cx - width / 2, cy - (7 * step - gap) / 2
    out, k = [], 0
    for n, ch in enumerate(text):
        for r, row in enumerate(GLYPHS[ch]):
            for c, on in enumerate(row):
                if on == "X":
                    x, y = x0 + (n * 6 + c) * step, y0 + r * step
                    out.append(f'<rect class="rise" style="animation-delay:{.3 + k * .025:.2f}s" x="{x:.1f}" y="{y:.1f}" '
                               f'width="{cell}" height="{cell}" rx="3.5" fill="url(#mono)"/>')
                    k += 1
    scan = f'<rect x="{x0 - 10:.0f}" y="{y0:.0f}" width="{width + 20:.0f}" height="3" fill="#fff" opacity=".35" class="scan"/>'
    return f'<g filter="url(#glow)">{"".join(out)}</g>{scan}', y0, 7 * step - gap


def terminal(user, langs, days, lifetime):
    W, H = 1000, 540
    total = sum(c for _, c, _ in days)
    current, longest = streaks(days)
    created = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).date()
    uptime = (dt.date.today() - created).days
    top = sorted(langs.items(), key=lambda kv: -kv[1])

    acx, acy = 185, 250
    art, my, mh = monogram("AC", acx, acy)

    kx, vx, y0, step = 360, 470, 160, 27
    rows_ = [
        ("Role", "Developer · Founder & CEO, NEXERA", FG),
        ("Mail", "alokchaudhary@nexeraofficial.in", PINK),
        ("Uptime", f"{uptime:,} days on GitHub", FG),
        ("Shell", " · ".join(n for n, _ in top[:3]) or "TypeScript", FG),
        ("Stack", "Next.js · Flutter · Node.js · Postgres", FG),
        ("Commits", f"{total:,} last year · {lifetime:,} all time", AMBER),
        ("Streak", f"{plural(current, 'day')} now · {longest} best", FG),
        ("Repos", f"{user.get('public_repos', 0)} public · {plural(user.get('followers', 0), 'follower')}", FG),
    ]
    lines = []
    for k, (key, val, col) in enumerate(rows_):
        y = y0 + k * step
        lines.append(
            f'<g class="in" style="animation-delay:{.6 + k * .09:.2f}s">'
            f'<text x="{kx}" y="{y}" class="mono" font-size="16" font-weight="700" fill="{CYAN}">{esc(key)}</text>'
            f'<text x="{vx}" y="{y}" class="mono" font-size="16" fill="{col}">{esc(val)}</text></g>'
        )

    ly = y0 + len(rows_) * step
    top5 = top[:5] or [("TypeScript", 1)]
    tot = sum(v for _, v in top5)
    bar, legend, x, bw = [], [], vx, 470
    for name, size in top5:
        w = bw * size / tot
        bar.append(f'<rect x="{x:.1f}" y="{ly - 12}" width="{max(w - 2, 2):.1f}" height="10" rx="2" fill="{LANG_COLORS.get(name, VIOLET)}"/>')
        x += w
    lx, row = vx, 0
    for name, size in top5:
        label = f"{name} {100 * size / tot:.0f}%"
        if lx + 14 + len(label) * 12.5 * CW > W - 40:
            lx, row = vx, row + 1
        yy = ly + 18 + row * 20
        legend.append(f'<circle cx="{lx + 5}" cy="{yy - 5}" r="4" fill="{LANG_COLORS.get(name, VIOLET)}"/>'
                      f'<text x="{lx + 14}" y="{yy}" class="mono" font-size="12.5" fill="{FG2}">{esc(label)}</text>')
        lx += 14 + len(label) * 12.5 * CW + 18
    lang = (f'<g class="in" style="animation-delay:{.6 + len(rows_) * .09:.2f}s">'
            f'<text x="{kx}" y="{ly}" class="mono" font-size="16" font-weight="700" fill="{CYAN}">Langs</text>'
            f'{"".join(bar)}{"".join(legend)}</g>')
    palette = "".join(
        f'<rect x="{kx + k * 34}" y="{ly + 50 + row * 20}" width="30" height="16" rx="3" fill="{c}"/>'
        for k, c in enumerate(["#1f2433", ROSE, LIME, AMBER, SKY, VIOLET, CYAN, FG])
    )

    defs = f"""
  <linearGradient id="mono" x1="{acx - 110}" y1="{acy - 70}" x2="{acx + 110}" y2="{acy + 70}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{CYAN}"/><stop offset=".55" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>
  <linearGradient id="name2" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>"""
    css = f"""
  .scan {{ animation: scan 3.5s ease-in-out infinite; }}
  @keyframes scan {{ 0%, 100% {{ transform: translateY(0); opacity: 0; }} 10%, 90% {{ opacity: .35; }} 50% {{ transform: translateY({mh - 3}px); }} }}"""
    body = f"""
<rect x="1" y="1" width="{W - 2}" height="44" fill="#10131c"/>
<line x1="1" x2="{W - 1}" y1="45.5" y2="45.5" stroke="{LINE}"/>
<circle cx="30" cy="23" r="6.5" fill="#ff5f57"/><circle cx="52" cy="23" r="6.5" fill="#febc2e"/><circle cx="74" cy="23" r="6.5" fill="#28c840"/>
<text x="500" y="28" text-anchor="middle" class="mono" font-size="13" fill="{FG3}">~/alokkkchaudharyyy</text>
<text x="{W - 40}" y="28" text-anchor="end" class="mono" font-size="12" fill="{FG3}"><tspan fill="{CYAN}">[ 01 ]</tspan> WHOAMI</text>
<ellipse cx="{acx:.0f}" cy="{acy:.0f}" rx="120" ry="90" fill="{VIOLET}" opacity=".2" filter="url(#soft)" class="pulse"/>
{art}
<text x="{acx}" y="{my + mh + 46:.0f}" text-anchor="middle" class="mono" font-size="12" letter-spacing="4" fill="{FG3}">DEV · FOUNDER</text>
<g class="in" style="animation-delay:.2s">
  <text x="{kx}" y="88" class="mono" font-size="16"><tspan fill="{PINK}">~</tspan><tspan fill="{FG3}"> $</tspan><tspan fill="{FG}"> neofetch</tspan></text>
  <text x="{kx}" y="124" class="mono" font-size="20" font-weight="700" fill="url(#name2)">Alok Chaudhary</text>
  <text x="{kx}" y="142" class="mono" font-size="16" fill="{FG3}">{'-' * 14}</text>
</g>
{''.join(lines)}
{lang}
<g class="in" style="animation-delay:1.6s">{palette}
  <text x="{kx + 8 * 34 + 12}" y="{ly + 63 + row * 20}" class="mono" font-size="16" fill="{PINK}">$<tspan class="blink" fill="{CYAN}"> &#9608;</tspan></text>
</g>"""
    return svg(W, H, body, defs, css, rx=16)


# ------------------------------------------------------------------ contribution city

def city(days):
    lead = (days[0][0].weekday() + 1) % 7
    cells = [(((d - days[0][0]).days + lead) // 7, ((d - days[0][0]).days + lead) % 7, d, c, lv) for d, c, lv in days]
    weeks = cells[-1][0] + 1

    W, a, slab = 1000, 13, 10
    ox, oy = 56 + 7 * a, 104
    H = oy + (weeks + 7) * a // 2 + slab + 56

    def centre(i, j):
        return ox + (i - j) * a, oy + (i + j + 1) * a / 2

    T, R = (ox, oy), (ox + weeks * a, oy + weeks * a / 2)
    B, L = (ox + (weeks - 7) * a, oy + (weeks + 7) * a / 2), (ox - 7 * a, oy + 7 * a / 2)
    dn = lambda p: (p[0], p[1] + slab)

    floor = [
        f'<polygon points="{pts([L, B, dn(B), dn(L)])}" fill="#1a1230"/>',
        f'<polygon points="{pts([B, R, dn(R), dn(B)])}" fill="#120c22"/>',
        f'<polygon points="{pts([T, R, B, L])}" fill="#0d0b18" stroke="{VIOLET}" stroke-opacity=".45"/>',
    ]
    for i, j, *_ in cells:
        cx, cy = centre(i, j)
        floor.append(f'<polygon points="{pts([(cx, cy - a / 2), (cx + a, cy), (cx, cy + a / 2), (cx - a, cy)])}" '
                     f'fill="#100e1d" stroke="#221d38" stroke-width="1"/>')

    peak = max(c for *_, c, _ in cells) or 1
    towers = []
    for i, j, d, c, lv in sorted(cells, key=lambda x: (x[0] + x[1], x[0])):
        if c:
            cx, cy = centre(i, j)
            towers.append(cube(cx, cy, a, 5 + 64 * math.log1p(c) / math.log1p(peak), RAMP[max(1, lv) - 1], cls="rise",
                               style=f"animation-delay:{.2 + i * .022:.2f}s"))

    total = sum(c for _, c, _ in days)
    current, longest = streaks(days)
    best = max(days, key=lambda d: d[1])
    active = sum(1 for _, c, _ in days if c)
    sx, ex = 640, W - 48
    stats = [
        ("CURRENT STREAK", plural(current, "day")),
        ("LONGEST STREAK", plural(longest, "day")),
        ("BEST DAY", f"{best[1]} on {best[0]:%b} {best[0].day}" if best[1] else "none yet"),
        ("ACTIVE DAYS", f"{active} of {len(days)}"),
    ]
    rows = "".join(
        f'<g class="in" style="animation-delay:{.4 + k * .1:.2f}s">'
        f'<text x="{sx}" y="{214 + k * 30}" class="mono" font-size="12.5" letter-spacing="1.5" fill="{FG3}">{lab}</text>'
        f'<text x="{ex}" y="{214 + k * 30}" text-anchor="end" class="mono" font-size="15" font-weight="700" fill="{FG}">{esc(val)}</text></g>'
        for k, (lab, val) in enumerate(stats)
    )
    swatches = "".join(
        f'<rect x="{104 + k * 18}" y="{H - 52}" width="12" height="12" rx="3" fill="{c}"/>'
        for k, c in enumerate(["#100e1d"] + RAMP)
    )
    body = f"""
<rect width="{W}" height="{H}" fill="url(#cityglow)"/>
{''.join(floor)}
<g filter="url(#glow)">{''.join(towers)}</g>
<g class="in" style="animation-delay:.2s">
  <text x="{sx - 3}" y="152" class="sans" font-size="64" font-weight="800" fill="{PINK}" opacity=".45" filter="url(#soft)">{total:,}</text>
  <text x="{sx - 3}" y="152" class="sans" font-size="64" font-weight="800" fill="url(#num)">{total:,}</text>
  <text x="{sx}" y="180" class="mono" font-size="13" letter-spacing="2" fill="{CYAN}">CONTRIBUTIONS, LAST 12 MONTHS</text>
</g>
{rows}
<g class="in" style="animation-delay:.6s">
  <text x="56" y="{H - 41}" class="mono" font-size="11" letter-spacing="1.5" fill="{FG3}">LESS</text>
  {swatches}
  <text x="{104 + 5 * 18 + 4}" y="{H - 41}" class="mono" font-size="11" letter-spacing="1.5" fill="{FG3}">MORE</text>
  <text x="56" y="{H - 70}" class="mono" font-size="12" fill="{FG3}">{days[0][0]:%b %Y} to {days[-1][0]:%b %Y}</text>
</g>"""
    defs = (f'<radialGradient id="cityglow" cx="480" cy="{H * .6:.0f}" r="520" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".14"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>'
            f'<linearGradient id="num" x1="0" x2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="{CYAN}"/></linearGradient>')
    return svg(W, H, body, defs, label=("05", "CONTRIBUTION CITY"), rx=16)


def build_live(login):
    token = os.environ.get("GITHUB_TOKEN")
    days = calendar(login, token)
    user, langs = profile_data(login, token)
    lifetime = all_time(login, token, int(user["created_at"][:4]))
    write(METRICS / "terminal.svg", terminal(user, langs, days, lifetime))
    write(METRICS / "city.svg", city(days))
    try:
        ext = http("https://open-vsx.org/api/alokkkchaudharyyy/agent-bridge")
        write(METRICS / "project-agent-bridge.svg", agent_bridge_tile(ext.get("version", ""), ext.get("downloadCount")))
    except Exception as e:
        print(f"Open VSX lookup failed ({e})")
        write(METRICS / "project-agent-bridge.svg", agent_bridge_tile())
    print(f"{sum(c for _, c, _ in days)} last year, {lifetime} all time")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "static":
        build_static()
    elif mode == "live" and len(sys.argv) > 2:
        build_live(sys.argv[2])
    else:
        sys.exit(__doc__)
