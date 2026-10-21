"""
Builds every SVG used in the profile README.

    python tools/profile.py static          # hero, NEXERA card, headers, buttons, footer
    python tools/profile.py live <login>    # terminal and contribution city (live data)

Live mode uses GITHUB_TOKEN when it is set (GitHub Actions provides one) and
falls back to public endpoints otherwise.
"""

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
ASSETS, METRICS = ROOT / "assets", ROOT / "metrics"

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
CW = 0.6  # monospace advance in em, enforced with textLength where it matters

BG0, BG1 = "#04070b", "#08100d"
PANEL, LINE = "#0b1118", "#1b2a26"
FG, FG2, FG3 = "#e6edf3", "#93a1ad", "#5b6875"
G, G_DEEP, TEAL = "#39d353", "#1f6f33", "#2dd4bf"
GREENS = ["#196c2e", "#2ea043", "#3fb950", "#56d364"]

LANG_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "C++": "#f34b7d", "Python": "#3572a5",
    "C": "#555555", "Java": "#b07219", "Go": "#00add8", "Rust": "#dea584", "SQL": "#e38c00",
    "Dart": "#00b4ab", "PLpgSQL": "#336790", "Shell": "#89e051", "Kotlin": "#a97bff",
    "Swift": "#f05138", "PHP": "#4f5d95", "C#": "#178600", "Ruby": "#701516", "Objective-C": "#438eff",
}
IGNORED_LANGS = {"HTML", "CSS", "SCSS", "Shell", "Batchfile", "PowerShell", "Dockerfile", "Procfile"}


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
    left, right = shade(color, 0.72), shade(color, 0.52)
    attrs = (f' class="{cls}"' if cls else "") + (f' style="{style}"' if style else "")
    return (
        f"<g{attrs}>"
        f'<polygon points="{pts([up(L), up(B), B, L])}" fill="{left}"/>'
        f'<polygon points="{pts([up(B), up(R), R, B])}" fill="{right}"/>'
        f'<polygon points="{pts([up(T), up(R), up(B), up(L)])}" fill="{color}" stroke="{shade(color, 1.35)}" stroke-width="0.6"/>'
        f"</g>"
    )


BASE_CSS = f"""
  .sans {{ font-family: {SANS}; }}
  .mono {{ font-family: {MONO}; }}
  .in {{ animation: fadein .8s cubic-bezier(.2,.8,.2,1) both; }}
  .rise {{ animation: rise .9s cubic-bezier(.2,.8,.2,1) both; }}
  .blink {{ animation: blink 1s steps(1) infinite; }}
  .pulse {{ animation: pulse 2s ease-in-out infinite; }}
  .ping {{ animation: ping 2.2s cubic-bezier(0,0,.2,1) infinite; transform-box: fill-box; transform-origin: center; }}
  .bob {{ animation: bob 6s ease-in-out infinite; }}
  .twinkle {{ animation: twinkle 3s ease-in-out infinite; }}
  @keyframes fadein {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(26px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes blink {{ 50% {{ opacity: 0; }} }}
  @keyframes pulse {{ 0%, 100% {{ opacity: .45; }} 50% {{ opacity: 1; }} }}
  @keyframes ping {{ 0% {{ transform: scale(1); opacity: .7; }} 80%, 100% {{ transform: scale(3); opacity: 0; }} }}
  @keyframes bob {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-12px); }} }}
  @keyframes twinkle {{ 0%, 100% {{ opacity: .15; }} 50% {{ opacity: .9; }} }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
"""

GLOW_DEFS = """
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>"""


def svg(w, h, body, defs="", css="", label="", rx=16, comet=False, frame=True):
    """A dark card with a subtle border, HUD corners and an optional running light."""
    deco = ""
    if frame:
        deco = f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="url(#cardbg)" stroke="{LINE}"/>'
        c, k = 14, 18
        for x, y, dx, dy in ((c, c, 1, 1), (w - c, c, -1, 1), (c, h - c, 1, -1), (w - c, h - c, -1, -1)):
            deco += f'<path d="M{x} {y + dy * k} V{y} H{x + dx * k}" stroke="{G}" stroke-opacity=".55" stroke-width="1.5"/>'
        if comet:
            deco += (
                f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{rx}" pathLength="1000" fill="none" '
                f'stroke="url(#cometg)" stroke-width="2" stroke-linecap="round" stroke-dasharray="140 860" filter="url(#glow)">'
                f'<animate attributeName="stroke-dashoffset" from="1000" to="0" dur="7s" repeatCount="indefinite"/></rect>'
            )
        if label:
            deco += (
                f'<g class="in"><text x="40" y="52" class="mono" font-size="13" letter-spacing="3" fill="{FG3}">'
                f'<tspan fill="{G}">[ {esc(label[0])} ]</tspan>  {esc(label[1])}</text></g>'
            )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" role="img">
<style>{BASE_CSS}{css}</style>
<defs>
  <linearGradient id="cardbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{PANEL}"/><stop offset="1" stop-color="{BG0}"/></linearGradient>
  <linearGradient id="cometg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{G}"/></linearGradient>
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
<rect y="{y - fs * 0.82}" width="{cw * 0.9:.1f}" height="{fs * 1.02:.1f}" fill="{G}" class="blink" x="{x}">
  <animate attributeName="x" values="{xs}" keyTimes="{kt}" dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"/>
</rect>"""


def hero():
    W, H = 1000, 470
    rng = random.Random(7)
    hz = 318  # horizon

    stars = "".join(
        f'<circle cx="{rng.uniform(10, W - 10):.0f}" cy="{rng.uniform(10, hz - 30):.0f}" r="{rng.uniform(.5, 1.6):.1f}" '
        f'fill="#fff" class="twinkle" style="animation-delay:-{rng.uniform(0, 3):.1f}s;animation-duration:{rng.uniform(2, 5):.1f}s"/>'
        for _ in range(90)
    )

    verticals = "".join(
        f'<line x1="{500 + k * 9}" y1="{hz}" x2="{500 + k * 85}" y2="{H}" stroke="{G}" stroke-opacity=".28"/>'
        for k in range(-24, 25)
    )
    horizontals = "".join(
        f'<line x1="0" x2="{W}" y1="{hz}" y2="{hz}" stroke="{G}" stroke-opacity=".5" class="floor" style="animation-delay:-{k * 0.4:.1f}s"/>'
        for k in range(8)
    )

    def cluster(ox, oy, spec, a=20, delay=0):
        out = []
        for (i, j, levels) in sorted(spec, key=lambda c: (c[0] + c[1], c[0])):
            cx, cy = ox + (i - j) * a, oy + (i + j) * a / 2
            for lv in range(levels):
                out.append(cube(cx, cy - lv * a * 0.9, a, a * 0.9, GREENS[min(3, lv + 1)], s=0.92))
        return f'<g class="bob" style="animation-delay:-{delay}s">{"".join(out)}</g>'

    left = cluster(105, 338, [(0, 0, 3), (1, 0, 2), (0, 1, 1), (1, 1, 4), (2, 1, 1), (1, 2, 2)], delay=0)
    right = cluster(890, 330, [(0, 0, 2), (1, 0, 4), (0, 1, 3), (1, 1, 1), (2, 0, 1), (0, 2, 1)], delay=3)
    floaters = "".join(
        f'<g class="bob" style="animation-delay:-{d}s;animation-duration:{dur}s">{cube(x, y, 9, 9, GREENS[3], s=1)}</g>'
        for x, y, d, dur in ((300, 110, 1, 5), (700, 90, 2.5, 7), (90, 90, 4, 6), (930, 300, 1.5, 5.5), (60, 280, 3, 6.5))
    )
    shadows = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="70" ry="14" fill="{G}" opacity=".18" filter="url(#soft)" class="pulse"/>'
        for x, y in ((120, 420), (905, 412))
    )

    phrases = [
        "Full-stack developer.",
        "Founder & CEO at NEXERA.",
        "Building the future of student learning.",
        "Turning ideas into shipped products.",
    ]
    fs = 22
    longest = max(len(p) for p in phrases) + 2
    tx = 500 - longest * fs * CW / 2

    css = f"""
  .floor {{ animation: floor 3.2s cubic-bezier(.55,0,1,.45) infinite; }}
  @keyframes floor {{ from {{ transform: translateY(0); opacity: 0; }} 15% {{ opacity: .8; }} to {{ transform: translateY({H - hz}px); opacity: 1; }} }}"""

    defs = f"""
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#020407"/><stop offset=".68" stop-color="#06110b"/><stop offset="1" stop-color="#03140a"/></linearGradient>
  <radialGradient id="halo" cx="500" cy="{hz}" r="420" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{G}" stop-opacity=".30"/><stop offset="1" stop-color="{G}" stop-opacity="0"/></radialGradient>
  <linearGradient id="floorfade" x1="0" y1="{hz}" x2="0" y2="{H}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".35" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>
  <mask id="floormask"><rect y="{hz}" width="{W}" height="{H - hz}" fill="url(#floorfade)"/></mask>
  <linearGradient id="name" x1="0" y1="0" x2="1" y2="0" gradientUnits="objectBoundingBox">
    <stop offset="0" stop-color="#ffffff"/><stop offset=".45" stop-color="#b7f7c6"/><stop offset=".55" stop-color="{G}"/><stop offset="1" stop-color="#ffffff"/>
    <animateTransform attributeName="gradientTransform" type="translate" values="-1 0;1 0" dur="6s" repeatCount="indefinite"/>
  </linearGradient>
  <linearGradient id="nameBase" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d9fbe2"/></linearGradient>"""

    body = f"""
<rect width="{W}" height="{H}" fill="url(#sky)"/>
<rect width="{W}" height="{H}" fill="url(#halo)"/>
{stars}
<g mask="url(#floormask)">{verticals}{horizontals}</g>
<rect x="0" y="{hz - 1}" width="{W}" height="2" fill="{G}" opacity=".9" filter="url(#glow)"/>
<ellipse cx="500" cy="{hz}" rx="380" ry="10" fill="{G}" opacity=".35" filter="url(#soft)"/>
{shadows}
<g class="rise" style="animation-delay:.2s">{left}</g>
<g class="rise" style="animation-delay:.35s">{right}</g>
{floaters}

<g class="in">
  <circle cx="42" cy="38" r="4" fill="{G}"/><circle cx="42" cy="38" r="4" fill="{G}" class="ping"/>
  <text x="56" y="43" class="mono" font-size="13" letter-spacing="2.5" fill="{FG2}">SYS://NEXERA</text>
  <text x="{W - 40}" y="43" text-anchor="end" class="mono" font-size="13" letter-spacing="2.5" fill="{FG2}">STATUS <tspan fill="{G}">BUILDING</tspan></text>
</g>
<g class="in" style="animation-delay:.1s">
  <text x="500" y="120" text-anchor="middle" class="mono" font-size="16" letter-spacing="8" fill="{G}">HELLO WORLD, I'M</text>
</g>
<g class="in" style="animation-delay:.25s">
  <text x="500" y="200" text-anchor="middle" class="sans" font-size="78" font-weight="800" letter-spacing="3" fill="{G}" opacity=".55" filter="url(#soft)">ALOK CHAUDHARY</text>
  <text x="500" y="200" text-anchor="middle" class="sans" font-size="78" font-weight="800" letter-spacing="3" fill="url(#name)">ALOK CHAUDHARY</text>
</g>
<g class="in" style="animation-delay:.45s">
  <text x="{tx:.1f}" y="256" class="mono" font-size="{fs}" fill="{G}">&gt;</text>
  {typing(phrases, tx + 2 * fs * CW, 256, fs)}
</g>"""
    return svg(W, H, body, defs, css, frame=False, rx=18)


# ------------------------------------------------------------------ NEXERA

ICONS = {
    "book": "M3 5.5c3-1.6 6.3-1.6 9 .5 2.7-2.1 6-2.1 9-.5V19c-3-1.4-6.3-1.4-9 .6-2.7-2-6-2-9-.6Z M12 6v13.6",
    "bolt": "M13.5 2 4.5 13.5H11L10 22l9.5-12H13Z",
    "users": "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M2 21c0-4 3-6.5 7-6.5s7 2.5 7 6.5 M17 3.5a3.5 3.5 0 0 1 0 7 M19 14.5c2 .6 3.5 2.6 3.5 6",
}


def nexera():
    W, H = 1000, 400
    x0 = 48
    pillars = [
        ("book", "Education", "IPUNEX: structured learning and practice"),
        ("bolt", "Events", "Tech events that bring builders together"),
        ("users", "Community", "Students learning and growing together"),
    ]
    px, pw, ph, gap, py0 = 548, 404, 80, 16, 92
    tiles = []
    for k, (icon, title, sub) in enumerate(pillars):
        y = py0 + k * (ph + gap)
        tiles.append(f"""
<g class="in" style="animation-delay:{.35 + k * .12:.2f}s">
  <rect x="{px}" y="{y}" width="{pw}" height="{ph}" rx="12" fill="#0a1510" stroke="{G_DEEP}" stroke-opacity=".8"/>
  <rect x="{px}" y="{y + 18}" width="3" height="{ph - 36}" rx="1.5" fill="{G}" filter="url(#glow)"/>
  <rect x="{px + 22}" y="{y + 18}" width="44" height="44" rx="10" fill="{G}" fill-opacity=".1" stroke="{G}" stroke-opacity=".35"/>
  <g transform="translate({px + 32} {y + 28})"><path d="{ICONS[icon]}" stroke="{G}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></g>
  <text x="{px + 84}" y="{y + 36}" class="sans" font-size="19" font-weight="700" fill="{FG}">{esc(title)}</text>
  <text x="{px + 84}" y="{y + 59}" class="sans" font-size="14.5" fill="{FG2}">{esc(sub)}</text>
  <text x="{px + pw - 22}" y="{y + 36}" text-anchor="end" class="mono" font-size="12" fill="{G}" opacity=".7">0{k + 1}</text>
</g>""")

    defs = f"""
  <linearGradient id="word" x1="0" y1="0" x2="1" y2="0" gradientUnits="objectBoundingBox">
    <stop offset="0" stop-color="#ffffff"/><stop offset=".5" stop-color="{G}"/><stop offset="1" stop-color="#ffffff"/>
    <animateTransform attributeName="gradientTransform" type="translate" values="-1 0;1 0" dur="5s" repeatCount="indefinite"/>
  </linearGradient>
  <radialGradient id="nglow" cx="260" cy="190" r="320" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{G}" stop-opacity=".13"/><stop offset="1" stop-color="{G}" stop-opacity="0"/></radialGradient>"""

    body = f"""
<rect width="{W}" height="{H}" fill="url(#nglow)"/>
<g class="in" style="animation-delay:.1s">
  <rect x="{x0}" y="90" width="170" height="30" rx="15" fill="{G}" fill-opacity=".1" stroke="{G}" stroke-opacity=".45"/>
  <circle cx="{x0 + 18}" cy="105" r="4" fill="{G}"/><circle cx="{x0 + 18}" cy="105" r="4" fill="{G}" class="ping"/>
  <text x="{x0 + 32}" y="110" class="mono" font-size="12.5" letter-spacing="2" fill="{G}">FOUNDER &amp; CEO</text>
</g>
<g class="in" style="animation-delay:.2s">
  <text x="{x0 - 4}" y="200" class="sans" font-size="86" font-weight="900" letter-spacing="14" fill="{G}" opacity=".45" filter="url(#soft)">NEXERA</text>
  <text x="{x0 - 4}" y="200" class="sans" font-size="86" font-weight="900" letter-spacing="14" fill="url(#word)">NEXERA</text>
  <text x="{x0}" y="242" class="sans" font-size="24" font-weight="300" fill="{FG}">Shaping futures.</text>
  <text class="sans" font-size="16" fill="{FG2}">
    <tspan x="{x0}" y="284">A student-driven ecosystem that brings education,</tspan>
    <tspan x="{x0}" y="308">events and community together. Home to IPUNEX.</tspan>
  </text>
  <rect x="{x0}" y="332" width="206" height="36" rx="18" fill="{G}"/>
  <text x="{x0 + 103}" y="355" text-anchor="middle" class="mono" font-size="14" font-weight="700" fill="#04140a">nexeraofficial.in &#8599;</text>
</g>
{''.join(tiles)}"""
    return svg(W, H, body, defs, label=("02", "NOW BUILDING"), comet=True)


# ------------------------------------------------------------------ small pieces

def header(num, title, sub=""):
    W, H = 1000, 70
    body = f"""
<g class="in">
  <text x="4" y="42" class="mono" font-size="15" letter-spacing="3" fill="{FG2}"><tspan fill="{G}">[ {num} ]</tspan>  {esc(title)}</text>
  <line x1="{4 + (len(title) + 8) * 15 * CW + 34:.0f}" x2="{W - 4}" y1="37" y2="37" stroke="url(#hl)" stroke-width="1.5"/>
  <circle cx="{W - 6}" cy="37" r="3" fill="{G}" class="pulse" filter="url(#glow)"/>
  {f'<text x="{W - 4}" y="62" text-anchor="end" class="mono" font-size="12" fill="{FG3}">{esc(sub)}</text>' if sub else ''}
</g>"""
    defs = f'<linearGradient id="hl" x1="0" x2="1"><stop offset="0" stop-color="{G}" stop-opacity=".9"/><stop offset="1" stop-color="{G}" stop-opacity=".05"/></linearGradient>'
    return svg(W, H, body, defs, frame=False, rx=0)


BUTTON_ICONS = {
    "globe": '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c2.6 2.8 3.9 6 3.9 9.5s-1.3 6.7-3.9 9.5c-2.6-2.8-3.9-6-3.9-9.5s1.3-6.7 3.9-9.5Z"/>',
    "linkedin": '<rect x="2.5" y="2.5" width="19" height="19" rx="4"/><path d="M7.5 10.5v6M7.5 7.4v.1M11.5 16.5v-6M11.5 13c0-1.6 1.1-2.6 2.5-2.6s2.5 1 2.5 2.6v3.5"/>',
    "code": '<path d="m8 7-5 5 5 5M16 7l5 5-5 5M13.5 4l-3 16"/>',
}


def button(icon, text, primary=False):
    w = 64 + len(text) * 15 * CW + 26
    H = 52
    fill, stroke, color = (G, G, "#04140a") if primary else ("#0b1410", G_DEEP, FG)
    icol = "#04140a" if primary else G
    body = f"""
<rect x="1" y="1" width="{w - 2:.0f}" height="{H - 2}" rx="12" fill="{fill}" stroke="{stroke}"/>
<g transform="translate(22 14)" stroke="{icol}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none">{BUTTON_ICONS[icon]}</g>
<text x="58" y="32" class="mono" font-size="15" font-weight="700" fill="{color}">{esc(text)}</text>"""
    return svg(round(w), H, body, frame=False, rx=12)


def footer():
    W, H = 1000, 200
    waves = []
    for k, (amp, period, op, dur) in enumerate(((14, 250, .55, 9), (20, 340, .3, 13), (10, 190, .2, 7))):
        y0 = 132 + k * 14
        d = f"M0 {y0}"
        for x in range(0, 2 * W + 1, 10):
            d += f" L{x} {y0 + amp * math.sin(2 * math.pi * x / period):.1f}"
        d += f" L{2 * W} {H} L0 {H} Z"
        waves.append(
            f'<path d="{d}" fill="{G}" fill-opacity="{op * 0.25:.3f}" stroke="{G}" stroke-opacity="{op}" stroke-width="1.2" '
            f'class="wave" style="animation-duration:{dur}s"/>'
        )
    css = """
  .wave { animation: wave linear infinite; }
  @keyframes wave { from { transform: translateX(0); } to { transform: translateX(-1000px); } }"""
    body = f"""
<rect width="{W}" height="{H}" fill="url(#cardbg)"/>
{''.join(waves)}
<g class="in">
  <text x="500" y="62" text-anchor="middle" class="mono" font-size="15" letter-spacing="7" fill="{G}">THANKS FOR STOPPING BY</text>
  <text x="500" y="96" text-anchor="middle" class="sans" font-size="20" fill="{FG}">Let's build something that matters.</text>
</g>"""
    return svg(W, H, body, css=css, frame=True, rx=16)


def build_static():
    write(ASSETS / "hero.svg", hero())
    write(ASSETS / "nexera.svg", nexera())
    write(ASSETS / "header-stack.svg", header("03", "TECH ARSENAL", "tools I build with every day"))
    write(ASSETS / "header-snake.svg", header("05", "COMMIT SNAKE", "eats my contributions, redrawn daily"))
    write(ASSETS / "footer.svg", footer())
    write(ASSETS / "btn-website.svg", button("globe", "nexeraofficial.in", primary=True))
    write(ASSETS / "btn-linkedin.svg", button("linkedin", "LinkedIn"))
    write(ASSETS / "btn-projects.svg", button("code", "Projects"))


# ------------------------------------------------------------------ live data

def http(url, data=None, token=None, raw=False):
    headers = {"User-Agent": "profile-builder", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as r:
        body = r.read().decode()
    return body if raw else json.loads(body)


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
    return f"{n} {word}{'' if n == 1 else 's'}"


# ------------------------------------------------------------------ terminal

N_GLYPH = ["X...X", "XX..X", "XX..X", "X.X.X", "X..XX", "X..XX", "X...X"]


def terminal(user, langs, days):
    W, H = 1000, 520
    total = sum(c for _, c, _ in days)
    current, longest = streaks(days)
    created = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).date()
    uptime = (dt.date.today() - created).days

    # voxel "N", front-facing so it reads at a glance
    px_, d, ox, oy = 26, 10, 104, 196
    vox = []
    order = [(c, r) for r in range(6, -1, -1) for c in range(5) if N_GLYPH[r][c] == "X"]
    for k, (c, r) in enumerate(order):
        x, y = ox + c * px_, oy + r * px_
        col = GREENS[3 - min(3, r // 2)]
        vox.append(
            f'<g class="rise" style="animation-delay:{.3 + k * .04:.2f}s">'
            f'<polygon points="{pts([(x, y), (x + px_, y), (x + px_ + d, y - d), (x + d, y - d)])}" fill="{shade(col, 1.25)}"/>'
            f'<polygon points="{pts([(x + px_, y), (x + px_ + d, y - d), (x + px_ + d, y + px_ - d), (x + px_, y + px_)])}" fill="{shade(col, .55)}"/>'
            f'<rect x="{x}" y="{y}" width="{px_}" height="{px_}" fill="{col}" stroke="{shade(col, 1.4)}" stroke-width=".8"/></g>'
        )
    logo = f'<ellipse cx="{ox + 2.5 * px_}" cy="{oy + 7 * px_ + 34}" rx="105" ry="16" fill="{G}" opacity=".3" filter="url(#soft)" class="pulse"/>'            f'<g class="bob" style="animation-duration:7s"><g filter="url(#glow)">{"".join(vox)}</g></g>'

    kx, vx, y0, step = 360, 490, 168, 27
    rows = [
        ("OS", "NEXERA, student ecosystem"),
        ("Role", "Developer · Founder & CEO"),
        ("Host", "nexeraofficial.in"),
        ("Uptime", f"{uptime} days on GitHub"),
        ("Shell", " · ".join(n for n, _ in sorted(langs.items(), key=lambda kv: -kv[1])[:3]) or "TypeScript"),
        ("Stack", "Next.js · Node.js · Prisma · Postgres · Redis"),
        ("Commits", f"{total:,} contributions this year"),
        ("Streak", f"{plural(current, 'day')} now · {longest} best"),
        ("Repos", f"{user.get('public_repos', 0)} public · {plural(user.get('followers', 0), 'follower')}"),
    ]
    lines = []
    for k, (key, val) in enumerate(rows):
        y = y0 + k * step
        lines.append(
            f'<g class="in" style="animation-delay:{.6 + k * .09:.2f}s">'
            f'<text x="{kx}" y="{y}" class="mono" font-size="16" font-weight="700" fill="{G}">{esc(key)}</text>'
            f'<text x="{vx}" y="{y}" class="mono" font-size="16" fill="{FG}">{esc(val)}</text></g>'
        )

    # language bar
    ly = y0 + len(rows) * step
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:5] or [("TypeScript", 1)]
    tot = sum(v for _, v in top)
    bar, legend, x, bw = [], [], vx, 440
    for k, (name, size) in enumerate(top):
        w = bw * size / tot
        bar.append(f'<rect x="{x:.1f}" y="{ly - 12}" width="{max(w - 2, 2):.1f}" height="10" rx="2" fill="{LANG_COLORS.get(name, G)}"/>')
        x += w
    lx, row = vx, 0
    for name, size in top:
        label = f"{name} {100 * size / tot:.0f}%"
        if lx + 14 + len(label) * 12.5 * CW > W - 40:
            lx, row = vx, row + 1
        yy = ly + 18 + row * 20
        legend.append(f'<circle cx="{lx + 5}" cy="{yy - 5}" r="4" fill="{LANG_COLORS.get(name, G)}"/>'
                      f'<text x="{lx + 14}" y="{yy}" class="mono" font-size="12.5" fill="{FG2}">{esc(label)}</text>')
        lx += 14 + len(label) * 12.5 * CW + 18
    lang = (f'<g class="in" style="animation-delay:{.6 + len(rows) * .09:.2f}s">'
            f'<text x="{kx}" y="{ly}" class="mono" font-size="16" font-weight="700" fill="{G}">Langs</text>'
            f'{"".join(bar)}{"".join(legend)}</g>')

    palette = "".join(
        f'<rect x="{kx + k * 34}" y="{ly + 50 + row * 20}" width="30" height="16" rx="3" fill="{c}"/>'
        for k, c in enumerate(["#161b22", "#f85149", G, "#d29922", "#58a6ff", "#bc8cff", "#39c5cf", "#e6edf3"])
    )

    body = f"""
<rect x="1" y="1" width="{W - 2}" height="44" fill="#0e151d"/>
<line x1="1" x2="{W - 1}" y1="45.5" y2="45.5" stroke="{LINE}"/>
<circle cx="30" cy="23" r="6.5" fill="#ff5f57"/><circle cx="52" cy="23" r="6.5" fill="#febc2e"/><circle cx="74" cy="23" r="6.5" fill="#28c840"/>
<text x="500" y="28" text-anchor="middle" class="mono" font-size="13" fill="{FG3}">alok@nexera: ~/profile</text>
<text x="{W - 40}" y="28" text-anchor="end" class="mono" font-size="12" fill="{FG3}">[ 01 ] WHOAMI</text>
{logo}
<g class="in" style="animation-delay:.2s">
  <text x="{kx}" y="92" class="mono" font-size="16"><tspan fill="{G}">alok@nexera</tspan><tspan fill="{FG3}">:~$</tspan><tspan fill="{FG}"> neofetch</tspan></text>
  <text x="{kx}" y="128" class="mono" font-size="20" font-weight="700"><tspan fill="{G}">alok</tspan><tspan fill="{FG}">@</tspan><tspan fill="{G}">nexera</tspan></text>
  <text x="{kx}" y="146" class="mono" font-size="16" fill="{FG3}">{'-' * 16}</text>
</g>
{''.join(lines)}
{lang}
<g class="in" style="animation-delay:1.6s">{palette}
  <text x="{kx + 8 * 34 + 12}" y="{ly + 63 + row * 20}" class="mono" font-size="16" fill="{G}">$<tspan class="blink"> &#9608;</tspan></text>
</g>"""
    return svg(W, H, body, rx=16)


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
        f'<polygon points="{pts([L, B, dn(B), dn(L)])}" fill="#0f2418"/>',
        f'<polygon points="{pts([B, R, dn(R), dn(B)])}" fill="#0a1a11"/>',
        f'<polygon points="{pts([T, R, B, L])}" fill="#0b1510" stroke="{G}" stroke-opacity=".5"/>',
    ]
    for i, j, *_ in cells:
        cx, cy = centre(i, j)
        floor.append(f'<polygon points="{pts([(cx, cy - a / 2), (cx + a, cy), (cx, cy + a / 2), (cx - a, cy)])}" '
                     f'fill="#0d1a13" stroke="#173322" stroke-width="1"/>')

    peak = max(c for *_, c, _ in cells) or 1
    towers = []
    for i, j, d, c, lv in sorted(cells, key=lambda x: (x[0] + x[1], x[0])):
        if c:
            cx, cy = centre(i, j)
            towers.append(cube(cx, cy, a, 5 + 64 * math.log1p(c) / math.log1p(peak), GREENS[max(1, lv) - 1], cls="rise",
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
        for k, c in enumerate(["#0d1a13"] + GREENS)
    )

    body = f"""
<rect width="{W}" height="{H}" fill="url(#cityglow)"/>
{''.join(floor)}
<g filter="url(#glow)">{''.join(towers)}</g>
<g class="in" style="animation-delay:.2s">
  <text x="{sx - 3}" y="152" class="sans" font-size="64" font-weight="800" fill="{G}" opacity=".5" filter="url(#soft)">{total:,}</text>
  <text x="{sx - 3}" y="152" class="sans" font-size="64" font-weight="800" fill="{FG}">{total:,}</text>
  <text x="{sx}" y="180" class="mono" font-size="13" letter-spacing="2" fill="{G}">CONTRIBUTIONS THIS YEAR</text>
</g>
{rows}
<g class="in" style="animation-delay:.6s">
  <text x="56" y="{H - 41}" class="mono" font-size="11" letter-spacing="1.5" fill="{FG3}">LESS</text>
  {swatches}
  <text x="{104 + 5 * 18 + 4}" y="{H - 41}" class="mono" font-size="11" letter-spacing="1.5" fill="{FG3}">MORE</text>
  <text x="56" y="{H - 70}" class="mono" font-size="12" fill="{FG3}">{days[0][0]:%b %Y} to {days[-1][0]:%b %Y}</text>
</g>"""
    defs = f'<radialGradient id="cityglow" cx="480" cy="{H * .6:.0f}" r="520" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{G}" stop-opacity=".12"/><stop offset="1" stop-color="{G}" stop-opacity="0"/></radialGradient>'
    return svg(W, H, body, defs, label=("04", "CONTRIBUTION CITY"), rx=16)


def build_live(login):
    token = os.environ.get("GITHUB_TOKEN")
    days = calendar(login, token)
    user, langs = profile_data(login, token)
    write(METRICS / "terminal.svg", terminal(user, langs, days))
    write(METRICS / "city.svg", city(days))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "static":
        build_static()
    elif mode == "live" and len(sys.argv) > 2:
        build_live(sys.argv[2])
    else:
        sys.exit(__doc__)
