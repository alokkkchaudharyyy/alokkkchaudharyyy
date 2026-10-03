"""
Renders the isometric contribution calendar shown in the profile README.

    python tools/build_calendar.py <login>                  # live data
    python tools/build_calendar.py <login> --json data.json # saved GraphQL response

Uses GITHUB_TOKEN for the GraphQL API when it is set (GitHub Actions provides
one automatically) and falls back to the public contributions page otherwise.
Writes metrics/calendar-dark.svg and metrics/calendar-light.svg.
"""

import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from build_cards import THEMES, cube, frame, pts

OUT = Path(__file__).resolve().parent.parent / "metrics"

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}"""


def parse_graphql(payload):
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [
        (dt.date.fromisoformat(d["date"]), d["contributionCount"], LEVELS[d["contributionLevel"]])
        for w in weeks
        for d in w["contributionDays"]
    ]


def via_graphql(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return parse_graphql(payload)


def via_html(login):
    req = urllib.request.Request(
        f"https://github.com/users/{login}/contributions",
        headers={"User-Agent": "profile-calendar"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode()
    tips = {
        m.group(1): m.group(2)
        for m in re.finditer(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', html)
    }
    days = []
    for tag in re.findall(r"<td\b[^>]*\bdata-date=[^>]*>", html):
        attr = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
        n = re.match(r"\s*(\d+)", tips.get(attr.get("id", ""), ""))
        days.append((dt.date.fromisoformat(attr["data-date"]), int(n.group(1)) if n else 0, int(attr.get("data-level", 0))))
    if not days:
        raise RuntimeError("no contribution data found on the public page")
    return days


def load(login, json_path=None):
    if json_path:
        return parse_graphql(json.loads(Path(json_path).read_text(encoding="utf-8")))
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        try:
            return via_graphql(login, token)
        except Exception as e:  # keep the profile fresh even if the API call fails
            print(f"GraphQL failed ({e}), using the public page instead")
    return via_html(login)


def stats(days):
    days = sorted(days)
    total = sum(c for _, c, _ in days)
    longest = run = 0
    for _, c, _ in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and days[-1][1] == 0 else days  # today may still be empty
    for _, c, _ in reversed(tail):
        if not c:
            break
        current += 1
    best = max(days, key=lambda d: d[1])
    return total, current, longest, best


def fmt_day(d):
    return f"{d:%b} {d.day}"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def render(days, t):
    days = sorted(days)
    first = days[0][0]
    lead = (first.weekday() + 1) % 7  # Sunday = 0, like GitHub
    cells = [((d - first).days + lead, d, c, lvl) for d, c, lvl in days]
    cells = [(k // 7, k % 7, d, c, lvl) for k, d, c, lvl in cells]
    weeks = cells[-1][0] + 1

    W, a, slab = 1000, 13, 8
    ox, oy = 56 + 7 * a, 64
    H = oy + (weeks + 7) * a // 2 + slab + 44

    def centre(i, j):
        return ox + (i - j) * a, oy + (i + j + 1) * a / 2

    T = (ox, oy)
    R = (ox + weeks * a, oy + weeks * a / 2)
    B = (ox + (weeks - 7) * a, oy + (weeks + 7) * a / 2)
    L = (ox - 7 * a, oy + 7 * a / 2)
    dn = lambda p: (p[0], p[1] + slab)

    parts = [
        f'<polygon points="{pts([L, B, dn(B), dn(L)])}" fill="{t["slab_l"]}"/>',
        f'<polygon points="{pts([B, R, dn(R), dn(B)])}" fill="{t["slab_r"]}"/>',
        f'<polygon points="{pts([T, R, B, L])}" fill="{t["tile"]}"/>',
    ]
    for i, j, *_ in cells:
        cx, cy = centre(i, j)
        parts.append(
            f'<polygon points="{pts([(cx, cy - a / 2), (cx + a, cy), (cx, cy + a / 2), (cx - a, cy)])}" '
            f'fill="{t["tile"]}" stroke="{t["tile_stroke"]}" stroke-width="1.2"/>'
        )

    peak = max(c for *_, c, _ in cells) or 1
    for i, j, d, c, lvl in sorted(cells, key=lambda x: (x[0] + x[1], x[0])):
        if not c:
            continue
        h = 4 + 50 * (c / peak) ** 0.55
        cx, cy = centre(i, j)
        parts.append(cube(cx, cy, a, h, t["greens"][max(1, lvl) - 1], cls="c", delay=0.15 + i * 0.022))

    total, current, longest, best = stats(days)
    sx, ex = 668, W - 48
    rows = [
        ("Current streak", plural(current, "day")),
        ("Longest streak", plural(longest, "day")),
        ("Best day", f"{best[1]} on {fmt_day(best[0])}" if best[1] else "None yet"),
    ]
    stat_rows = "\n".join(
        f'<text x="{sx}" y="{204 + k * 28}" class="sans" font-size="15" fill="{t["fg2"]}">{label}</text>'
        f'<text x="{ex}" y="{204 + k * 28}" text-anchor="end" class="mono" font-size="14" fill="{t["fg"]}">{value}</text>'
        for k, (label, value) in enumerate(rows)
    )

    swatches = "".join(
        f'<rect x="{104 + k * 18}" y="{H - 52}" width="12" height="12" rx="3" fill="{color}"/>'
        for k, color in enumerate([t["tile"]] + t["greens"])
    )

    body = f"""
{chr(10).join(parts)}
<g class="f">
  <circle cx="{sx + 4}" cy="65" r="4" fill="{t['accent']}"/>
  <text x="{sx + 18}" y="70" class="mono" font-size="13" letter-spacing="2" fill="{t['fg3']}">CONTRIBUTIONS</text>
  <text x="{sx - 2}" y="128" class="sans" font-size="48" font-weight="700" letter-spacing="-1" fill="{t['fg']}">{total:,}</text>
  <text x="{sx}" y="156" class="sans" font-size="16" fill="{t['fg3']}">in the last year</text>
  <line x1="{sx}" x2="{ex}" y1="176.5" y2="176.5" stroke="{t['border']}"/>
  {stat_rows}
</g>
<g class="f" style="animation-delay:.3s">
  <text x="56" y="{H - 41}" class="mono" font-size="11" letter-spacing="1.5" fill="{t['fg3']}">LESS</text>
  {swatches}
  <text x="{104 + 5 * 18 + 4}" y="{H - 41}" class="mono" font-size="11" letter-spacing="1.5" fill="{t['fg3']}">MORE</text>
  <text x="56" y="{H - 70}" class="mono" font-size="12" fill="{t['fg3']}">{first:%b %Y} to {days[-1][0]:%b %Y}</text>
</g>"""
    return frame(W, H, t, body)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    login = sys.argv[1]
    json_path = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    days = load(login, json_path)
    OUT.mkdir(exist_ok=True)
    for theme, t in THEMES.items():
        (OUT / f"calendar-{theme}.svg").write_text(render(days, t), encoding="utf-8")
        print(f"metrics/calendar-{theme}.svg")
    total, current, longest, best = stats(days)
    print(f"{len(days)} days, {total} contributions, streak {current}, longest {longest}, best {best[1]}")


if __name__ == "__main__":
    main()
