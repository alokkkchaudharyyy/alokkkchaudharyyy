"""
Builds the SVG cards used in the profile README.

    python tools/build_cards.py

Writes a light and a dark variant of every card into assets/.
Edit the text in the card functions or the colors in THEMES, then re-run.
"""

from pathlib import Path
import random

OUT = Path(__file__).resolve().parent.parent / "assets"

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
MONO_CHAR = 0.605  # widest common monospace advance, in em

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "panel": "#151b23",
        "border": "#30363d",
        "fg": "#f0f6fc",
        "fg2": "#9198a1",
        "fg3": "#6e7681",
        "accent": "#3fb950",
        "greens": ["#196c2e", "#2ea043", "#3fb950", "#56d364"],
        "tile": "#1b2129",
        "tile_stroke": "#0d1117",
        "slab_l": "#242b35",
        "slab_r": "#181e26",
        "glow": 0.16,
        "dots": 0.35,
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f6f8fa",
        "border": "#d1d9e0",
        "fg": "#1f2328",
        "fg2": "#59636e",
        "fg3": "#818b98",
        "accent": "#1a7f37",
        "greens": ["#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "tile": "#ebedf0",
        "tile_stroke": "#ffffff",
        "slab_l": "#dde2e7",
        "slab_r": "#cdd4db",
        "glow": 0.10,
        "dots": 0.45,
    },
}

LANG_COLORS = {
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "C++": "#f34b7d",
    "Python": "#3572a5",
    "SQL": "#e38c00",
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def shade(hex_color, f):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[k:k + 2], 16) for k in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c * f))) for c in (r, g, b)))


def pts(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def cube(cx, cy, a, h, color, s=0.82, cls="", delay=None):
    """Isometric block standing on the diamond centred at (cx, cy)."""
    w, v = a * s, a * s / 2
    T, R, B, L = (cx, cy - v), (cx + w, cy), (cx, cy + v), (cx - w, cy)
    up = lambda p: (p[0], p[1] - h)
    top, left, right = color, shade(color, 0.80), shade(color, 0.64)
    style = f' style="animation-delay:{delay:.2f}s"' if delay is not None else ""
    klass = f' class="{cls}"' if cls else ""
    return (
        f'<g{klass}{style}>'
        f'<polygon points="{pts([up(L), up(B), B, L])}" fill="{left}" stroke="{left}" stroke-width="0.6" stroke-linejoin="round"/>'
        f'<polygon points="{pts([up(B), up(R), R, B])}" fill="{right}" stroke="{right}" stroke-width="0.6" stroke-linejoin="round"/>'
        f'<polygon points="{pts([up(T), up(R), up(B), up(L)])}" fill="{top}" stroke="{top}" stroke-width="0.6" stroke-linejoin="round"/>'
        f'</g>'
    )


def frame(w, h, t, body, defs="", extra_css=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" role="img">
<style>
  .sans {{ font-family: {SANS}; }}
  .mono {{ font-family: {MONO}; }}
  .c {{ animation: rise .8s cubic-bezier(.2,.8,.2,1) both; }}
  .f {{ animation: fade .9s ease-out both; }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes fade {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
  {extra_css}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
<defs>
  <clipPath id="card"><rect width="{w}" height="{h}" rx="12"/></clipPath>
  {defs}
</defs>
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="11.5" fill="{t['bg']}" stroke="{t['border']}"/>
<g clip-path="url(#card)">
{body}
</g>
</svg>
"""


# ---------------------------------------------------------------- banner

def banner(t):
    W, H = 1000, 340
    x0 = 56

    # isometric contribution grid, a nod to the calendar further down the page
    n, m, a = 12, 6, 18
    ox, oy = 736, 104
    rng = random.Random(42)

    def centre(i, j):
        return ox + (i - j) * a, oy + (i + j + 1) * a / 2

    T = (ox, oy)
    Rr = (ox + n * a, oy + n * a / 2)
    Bb = (ox + (n - m) * a, oy + (n + m) * a / 2)
    Ll = (ox - m * a, oy + m * a / 2)
    slab = 9
    dn = lambda p: (p[0], p[1] + slab)

    parts = [
        f'<polygon points="{pts([Ll, Bb, dn(Bb), dn(Ll)])}" fill="{t["slab_l"]}"/>',
        f'<polygon points="{pts([Bb, Rr, dn(Rr), dn(Bb)])}" fill="{t["slab_r"]}"/>',
        f'<polygon points="{pts([T, Rr, Bb, Ll])}" fill="{t["tile"]}"/>',
    ]
    for i in range(n):
        for j in range(m):
            cx, cy = centre(i, j)
            parts.append(
                f'<polygon points="{pts([(cx, cy - a / 2), (cx + a, cy), (cx, cy + a / 2), (cx - a, cy)])}" '
                f'fill="{t["tile"]}" stroke="{t["tile_stroke"]}" stroke-width="1.5"/>'
            )

    heights = {1: (5, 9), 2: (12, 20), 3: (24, 38), 4: (44, 70)}
    cells = []
    for i in range(n):
        for j in range(m):
            r = rng.random()
            if r < 0.5:
                continue
            lvl = rng.choices([1, 2, 3, 4], weights=[40, 32, 20, 8])[0]
            cells.append((i, j, lvl, rng.uniform(*heights[lvl])))
    # a couple of hand-placed towers so the skyline always reads well
    for i, j, h in ((2, 2, 74), (6, 1, 92), (9, 4, 60)):
        cells = [c for c in cells if (c[0], c[1]) != (i, j)]
        cells.append((i, j, 4, h))

    for i, j, lvl, h in sorted(cells, key=lambda c: (c[0] + c[1], c[0])):
        cx, cy = centre(i, j)
        parts.append(cube(cx, cy, a, h, t["greens"][lvl - 1], cls="c", delay=0.35 + (i + j) * 0.05))

    gx, gy = ox + (n - m) * a / 2, oy + (n + m) * a / 4
    grid = "\n".join(parts)

    defs = f"""
  <radialGradient id="glow" cx="{gx}" cy="{gy}" r="260" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{t['accent']}" stop-opacity="{t['glow']}"/>
    <stop offset="1" stop-color="{t['accent']}" stop-opacity="0"/>
  </radialGradient>
  <pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse">
    <circle cx="2" cy="2" r="1" fill="{t['fg3']}"/>
  </pattern>
  <linearGradient id="fadeGrad" x1="0" x2="1" y1="0" y2="0">
    <stop offset="0.35" stop-color="#fff" stop-opacity="0"/>
    <stop offset="1" stop-color="#fff" stop-opacity="1"/>
  </linearGradient>
  <mask id="fade"><rect width="{W}" height="{H}" fill="url(#fadeGrad)"/></mask>"""

    css = """
  .cursor { animation: blink 1.1s steps(1) infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  .ring { animation: ping 2.2s cubic-bezier(0,0,.2,1) infinite; transform-box: fill-box; transform-origin: center; }
  @keyframes ping { 0% { transform: scale(1); opacity: .55; } 80%, 100% { transform: scale(2.8); opacity: 0; } }"""

    body = f"""
<rect width="{W}" height="{H}" fill="url(#dots)" opacity="{t['dots']}" mask="url(#fade)"/>
<rect width="{W}" height="{H}" fill="url(#glow)"/>
{grid}
<g class="f">
  <text x="{x0}" y="88" class="mono" font-size="15"><tspan fill="{t['accent']}">alok@nexera</tspan><tspan fill="{t['fg3']}">:~$</tspan> <tspan fill="{t['fg2']}">whoami</tspan> <tspan class="cursor" fill="{t['accent']}">&#9608;</tspan></text>
</g>
<g class="f" style="animation-delay:.12s">
  <text x="{x0 - 3}" y="160" class="sans" font-size="58" font-weight="700" letter-spacing="-1.5" fill="{t['fg']}">Alok Chaudhary</text>
</g>
<g class="f" style="animation-delay:.22s">
  <text x="{x0}" y="204" class="sans" font-size="22" fill="{t['fg2']}">Developer <tspan fill="{t['accent']}" font-weight="700">&#183;</tspan> Founder &amp; CEO at <tspan fill="{t['fg']}" font-weight="600" letter-spacing="1">NEXERA</tspan></text>
</g>
<g class="f" style="animation-delay:.32s">
  <text class="sans" font-size="17" fill="{t['fg3']}">
    <tspan x="{x0}" y="248">Building a student-driven ecosystem that brings</tspan>
    <tspan x="{x0}" y="272">education, events and community into one place.</tspan>
  </text>
</g>
<g class="f" style="animation-delay:.42s">
  <circle class="ring" cx="{x0 + 5}" cy="301" r="4.5" fill="{t['accent']}"/>
  <circle cx="{x0 + 5}" cy="301" r="4.5" fill="{t['accent']}"/>
  <text x="{x0 + 20}" y="306" class="mono" font-size="14" fill="{t['fg2']}">shipping NEXERA, one commit at a time</text>
</g>"""
    return frame(W, H, t, body, defs, css)


# ---------------------------------------------------------------- nexera

def nexera(t):
    W, H = 1000, 312
    x0 = 48
    pillars = [
        ("Education", "IPUNEX, structured learning and practice"),
        ("Events", "Tech events that bring builders together"),
        ("Community", "Students learning and growing together"),
    ]
    px, pw, ph, gap, py0 = 520, 432, 64, 12, 52

    rows = []
    for k, (title, sub) in enumerate(pillars):
        y = py0 + k * (ph + gap)
        # tiny stacked-block icon: one, two, three blocks
        icon = []
        a, unit = 10, 8
        cx, base = px + 34, y + ph / 2 + 4 + (k + 1) * unit / 2
        for level in range(k + 1):
            icon.append(cube(cx, base - level * unit, a, unit, t["greens"][min(3, level + 1)], s=1.0))
        rows.append(f"""
<g class="f" style="animation-delay:{0.2 + k * 0.1:.2f}s">
  <rect x="{px}" y="{y}" width="{pw}" height="{ph}" rx="10" fill="{t['panel']}" stroke="{t['border']}"/>
  {''.join(icon)}
  <text x="{px + 68}" y="{y + 28}" class="sans" font-size="17" font-weight="600" fill="{t['fg']}">{esc(title)}</text>
  <text x="{px + 68}" y="{y + 48}" class="sans" font-size="14" fill="{t['fg3']}">{esc(sub)}</text>
  <text x="{px + pw - 20}" y="{y + 38}" text-anchor="end" class="mono" font-size="12" fill="{t['fg3']}">0{k + 1}</text>
</g>""")

    body = f"""
<g class="f">
  <circle cx="{x0 + 4}" cy="71" r="4" fill="{t['accent']}"/>
  <text x="{x0 + 18}" y="76" class="mono" font-size="13" letter-spacing="2" fill="{t['fg3']}">FOUNDER &amp; CEO</text>
  <text x="{x0 - 3}" y="136" class="sans" font-size="56" font-weight="800" letter-spacing="9" fill="{t['fg']}">NEXERA</text>
  <text x="{x0}" y="172" class="sans" font-size="20" fill="{t['fg2']}">Shaping futures.</text>
  <text class="sans" font-size="16" fill="{t['fg3']}">
    <tspan x="{x0}" y="212">A student-driven ecosystem that brings education,</tspan>
    <tspan x="{x0}" y="236">events and community together. Home to IPUNEX.</tspan>
  </text>
  <text x="{x0}" y="272" class="mono" font-size="14" fill="{t['accent']}">nexeraofficial.in &#8599;</text>
</g>
{''.join(rows)}"""
    return frame(W, H, t, body)


# ---------------------------------------------------------------- stack

def stack(t):
    W = 1000
    x0, chip_x0 = 48, 214
    rows = [
        ("Languages", ["TypeScript", "JavaScript", "C++", "Python", "SQL"]),
        ("Frontend", ["Next.js", "React", "Tailwind CSS", "Framer Motion", "Three.js", "GSAP"]),
        ("Backend", ["Node.js", "Express", "Prisma", "PostgreSQL", "Redis", "Socket.IO"]),
        ("Infra & tools", ["Docker", "AWS", "Vercel", "PM2", "Playwright", "Vitest", "Git"]),
    ]
    fs, ch, gap, row_h, top = 14, 34, 8, 52, 40
    H = top * 2 + (len(rows) - 1) * row_h + ch

    out = []
    for r, (label, items) in enumerate(rows):
        y = top + r * row_h
        out.append(
            f'<text x="{x0}" y="{y + 22}" class="mono" font-size="12" letter-spacing="1.6" '
            f'fill="{t["fg3"]}">{esc(label.upper())}</text>'
        )
        x = chip_x0
        for k, name in enumerate(items):
            w = 30 + len(name) * fs * MONO_CHAR + 16
            dot = LANG_COLORS.get(name, t["accent"])
            out.append(f"""<g class="f" style="animation-delay:{0.1 + r * 0.08 + k * 0.03:.2f}s">
  <rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{ch}" rx="8" fill="{t['panel']}" stroke="{t['border']}"/>
  <circle cx="{x + 16:.1f}" cy="{y + ch / 2}" r="4" fill="{dot}"/>
  <text x="{x + 30:.1f}" y="{y + 22}" class="mono" font-size="{fs}" fill="{t['fg']}">{esc(name)}</text>
</g>""")
            x += w + gap
        assert x - gap <= W - 48, f"row '{label}' overflows ({x - gap:.0f}px)"
    return frame(W, H, t, "\n".join(out))


def main():
    OUT.mkdir(exist_ok=True)
    for name, build in (("banner", banner), ("nexera", nexera), ("stack", stack)):
        for theme, t in THEMES.items():
            (OUT / f"{name}-{theme}.svg").write_text(build(t), encoding="utf-8")
            print(f"assets/{name}-{theme}.svg")


if __name__ == "__main__":
    main()
