#!/usr/bin/env python3
"""Builds the profile README and its SVG cards from scripts/content.json.

    python scripts/build.py          # README + every card
    python scripts/build.py live     # only the cards fed by the GitHub API (daily workflow)

GitHub renders README images without external requests, so every SVG embeds a subset of
the brand fonts (assets/fonts) holding just the glyphs it uses. Themed cards come in a
-light and -dark variant; the README picks one with <picture> and prefers-color-scheme.
"""
import base64
import io
import json
import os
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CONTENT = json.loads((ROOT / "scripts/content.json").read_text())
ICONS = json.loads((ASSETS / "icons.json").read_text())

# brand colours of marianmolnar.cz
BLUE, BLUE_HI, BLUE_DEEP, LIME, PAPER, INK = "#2A46E8", "#3654FF", "#151F8C", "#D6F279", "#F7F7F4", "#14161F"

THEMES = {
    "light": {
        "bg": PAPER, "line": "rgba(20,22,31,0.09)", "ink": INK, "muted": "#5D606B", "accent": BLUE,
        "chip": "rgba(20,22,31,0.05)", "empty": "#E7E7E1",
        "scale": ["#C7CFFA", "#8C9CF5", "#5168EF", BLUE],
    },
    "dark": {
        "bg": "#141720", "line": "rgba(255,255,255,0.09)", "ink": "#EDEEF2", "muted": "#9599A6", "accent": "#8C9BFF",
        "chip": "rgba(255,255,255,0.06)", "empty": "#1D2130",
        "scale": ["#222C6E", "#2F43B5", "#4D66F2", "#93A3FF"],
    },
}

FONTS = {
    "display": "oswald-500",
    "display-bold": "oswald-700",
    "body": "jakarta-400",
    "body-semi": "jakarta-600",
    "mono": "inconsolata-500",
}

LANG_COLORS = {"Swift": "#F05138", "JavaScript": "#F1E05A", "TypeScript": "#3178C6", "Python": "#3572A5", "Dart": "#00B4AB"}

_fonts = {}


def font(name):
    if name not in _fonts:
        _fonts[name] = TTFont(ASSETS / "fonts" / f"{FONTS[name]}.ttf")
    return _fonts[name]


def measure(s, name, size, tracking=0):
    f = font(name)
    cmap, hmtx = f.getBestCmap(), f["hmtx"]
    units = sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in s)
    return units / f["head"].unitsPerEm * size + tracking * len(s)


def wrap(s, name, size, width):
    lines, line = [], ""
    for word in s.split():
        candidate = f"{line} {word}".strip()
        if line and measure(candidate, name, size) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line]


def fit(s, name, size, width):
    """Truncates `s` with an ellipsis so it fits `width`."""
    if measure(s, name, size) <= width:
        return s
    while s and measure(s + "…", name, size) > width:
        s = s[:-1]
    return s.rstrip() + "…"


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.parts, self.defs, self.css = [], [], []
        self.glyphs = defaultdict(set)

    def __iadd__(self, part):
        self.parts.append(part)
        return self

    def text(self, x, y, s, name, size, fill, anchor="start", tracking=0, attrs=""):
        self.glyphs[name].update(s)
        extra = f' text-anchor="{anchor}"' if anchor != "start" else ""
        extra += f' letter-spacing="{tracking:g}"' if tracking else ""
        return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONTS[name]}" font-size="{size}" '
                f'fill="{fill}"{extra}{attrs}>{escape(s)}</text>')

    def render(self):
        faces = "".join(face(name, chars) for name, chars in self.glyphs.items())
        defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
        label = escape(self.label, {'"': "&quot;"})
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{label}">'
                f"<title>{escape(self.label)}</title><style>{faces}{''.join(self.css)}</style>"
                f"{defs}{''.join(self.parts)}</svg>\n")


def face(name, chars):
    f = TTFont(ASSETS / "fonts" / f"{FONTS[name]}.ttf")
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(text="".join(sorted(chars)))
    subsetter.subset(f)
    buf = io.BytesIO()
    f.flavor = "woff2"
    f.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:'{FONTS[name]}';src:url(data:font/woff2;base64,{data}) format('woff2')}}"


def arrow(x, y, size, color, width=2.4):
    """A north-east arrow whose bounding box starts at (x, y)."""
    s = size
    return (f'<path d="M{x:.1f} {y + s:.1f}L{x + s:.1f} {y:.1f}M{x + s * 0.28:.1f} {y:.1f}H{x + s:.1f}V{y + s * 0.72:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>')


def card(w, h, t, rx=24):
    return f'<rect x="0.75" y="0.75" width="{w - 1.5}" height="{h - 1.5}" rx="{rx}" fill="{t["bg"]}" stroke="{t["line"]}" stroke-width="1.5"/>'


def write(name, svg):
    (ASSETS / name).write_text(svg.render())
    print(f"  assets/{name}")


# ── cards ────────────────────────────────────────────────────────────────────────────────


def header():
    h = CONTENT["header"]
    W, H = 1280, 440
    svg = Svg(W, H, f"{h['name']}. {h['tagline']}")
    svg.defs += [
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE_HI}"/>'
        f'<stop offset=".45" stop-color="{BLUE}"/><stop offset="1" stop-color="{BLUE_DEEP}"/></linearGradient>',
        f'<clipPath id="clip"><rect width="{W}" height="{H}" rx="28"/></clipPath>',
    ]
    slot = 3  # seconds each word of the "I build" ticker stays up
    cycle = slot * len(h["builds"])
    svg.css.append(
        f".w{{opacity:0;animation:word {cycle}s infinite}}.w0{{opacity:1}}"
        + "".join(f".w{i}{{animation-delay:{i * slot}s}}" for i in range(1, len(h["builds"])))
        + f"@keyframes word{{0%{{opacity:0;transform:translateY(12px)}}"
        f"{100 / len(h['builds']) * 0.12:.1f}%,{100 / len(h['builds']) * 0.88:.1f}%{{opacity:1;transform:none}}"
        f"{100 / len(h['builds']):.1f}%,100%{{opacity:0;transform:translateY(-12px)}}}}"
        ".ring{transform-box:fill-box;transform-origin:center;animation:ring 2.4s ease-out infinite}"
        "@keyframes ring{from{transform:scale(1);opacity:.8}to{transform:scale(3.2);opacity:0}}"
        ".ghost{animation:drift 22s ease-in-out infinite alternate}@keyframes drift{to{transform:translateX(-70px)}}"
        "@media (prefers-reduced-motion:reduce){.w,.ring,.ghost{animation:none}.w0{opacity:1}}"
    )

    svg += '<g clip-path="url(#clip)">'
    svg += f'<rect width="{W}" height="{H}" fill="url(#bg)"/>'
    # ghost watermark, as in the hero on marianmolnar.cz
    surname = h["name"].split()[-1].upper()
    svg += '<g class="ghost">' + svg.text(40, 600, surname, "display-bold", 430, "#fff", attrs=' fill-opacity="0.07"') + "</g>"

    # top bar: location with a live dot, site on the right
    svg += f'<circle class="ring" cx="62" cy="64" r="6" fill="none" stroke="{LIME}" stroke-width="2"/>'
    svg += f'<circle cx="62" cy="64" r="6" fill="{LIME}"/>'
    svg += svg.text(82, 71, h["location"], "mono", 22, "#fff", tracking=2, attrs=' fill-opacity="0.8"')
    site_w = measure(h["site"], "mono", 22, 2)
    svg += svg.text(W - 84 - site_w, 71, h["site"], "mono", 22, "#fff", tracking=2, attrs=' fill-opacity="0.8"')
    svg += arrow(W - 70, 56, 13, "#fff", 2.2)

    # name with the lime full stop
    svg += svg.text(50, 262, h["name"], "display", 150, "#fff")
    svg += svg.text(50 + measure(h["name"], "display", 150) + 4, 262, ".", "display", 150, LIME)
    svg += svg.text(56, 322, h["tagline"], "body", 34, "#fff", attrs=' fill-opacity="0.86"')

    # bottom row: rotating "I build" ticker and facts
    svg += f'<line x1="56" y1="352" x2="{W - 56}" y2="352" stroke="#fff" stroke-opacity="0.18" stroke-width="1.5"/>'
    lead = "I BUILD"
    svg += svg.text(56, 398, lead, "mono", 22, "#fff", tracking=2, attrs=' fill-opacity="0.62"')
    ax = 56 + measure(lead, "mono", 22, 2) + 14
    svg += f'<path d="M{ax} 391H{ax + 22}M{ax + 15} 384L{ax + 22} 391L{ax + 15} 398" fill="none" stroke="{LIME}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    for i, word in enumerate(h["builds"]):
        svg += svg.text(ax + 40, 398, word, "mono", 22, LIME, tracking=2, attrs=f' class="w w{i}"')
    svg += svg.text(W - 56, 398, h["facts"], "mono", 22, "#fff", anchor="end", tracking=2, attrs=' fill-opacity="0.62"')
    svg += "</g>"
    write("header.svg", svg)


def heading(n, key, theme):
    t, title = THEMES[theme], CONTENT["sections"][key]
    W, H = 1280, 88
    svg = Svg(W, H, title)
    num = f"{n:02d}"
    svg += svg.text(2, 58, num, "mono", 24, t["accent"], tracking=1)
    x = 2 + measure(num, "mono", 24, 1) + 18
    svg += svg.text(x, 60, title, "display", 52, t["ink"])
    x += measure(title, "display", 52) + 28
    svg += f'<line x1="{x:.1f}" y1="40" x2="{W - 2}" y2="40" stroke="{t["accent"]}" stroke-opacity="0.3" stroke-width="2"/>'
    write(f"heading-{key}-{theme}.svg", svg)


def stack(theme):
    t, columns = THEMES[theme], CONTENT["stack"]
    W, pad, step = 1280, 48, 54
    rows = max(len(c["items"]) for c in columns)
    H = pad + 26 + 40 + rows * step + 18
    svg = Svg(W, H, "Stack: " + ", ".join(label for c in columns for _, label in c["items"]))
    svg += card(W, H, t)
    col_w = (W - 2 * pad) / len(columns)
    for i, column in enumerate(columns):
        x = pad + i * col_w
        svg += svg.text(x, pad + 22, column["title"].upper(), "display", 22, t["accent"], tracking=2.4)
        svg += f'<line x1="{x:.1f}" y1="{pad + 42}" x2="{x + col_w - 32:.1f}" y2="{pad + 42}" stroke="{t["accent"]}" stroke-opacity="0.25" stroke-width="1.5"/>'
        for j, (icon, label) in enumerate(column["items"]):
            y = pad + 70 + j * step
            data = ICONS[icon]
            svg += (f'<svg x="{x:.1f}" y="{y}" width="28" height="28" viewBox="{data["vb"]}">'
                    f'<path d="{data["d"]}" fill="{t["ink"]}" fill-opacity="0.72"/></svg>')
            svg += svg.text(x + 44, y + 22, label, "body", 24, t["ink"])
    write(f"stack-{theme}.svg", svg)


def work_card(project, theme, desc_lines):
    t = THEMES[theme]
    W, inset = 800, 14
    tw, th = W - 2 * inset, round((W - 2 * inset) * 10 / 16)
    lh, text_w = 36, W - 64
    title_y = inset + th + 60
    desc_y = title_y + 48
    chips_y = desc_y + (desc_lines - 1) * lh + 30
    H = chips_y + 38 + 30
    svg = Svg(W, H, f"{project['name']}: {project['description']}")
    clip = f"thumb-{project['slug']}"
    svg.defs.append(f'<clipPath id="{clip}"><rect x="{inset}" y="{inset}" width="{tw}" height="{th}" rx="14"/></clipPath>')
    svg += card(W, H, t, rx=22)

    image = base64.b64encode((ASSETS / "thumbs" / f"{project['slug']}.jpg").read_bytes()).decode()
    svg += (f'<image x="{inset}" y="{inset}" width="{tw}" height="{th}" preserveAspectRatio="xMidYMid slice" '
            f'clip-path="url(#{clip})" href="data:image/jpeg;base64,{image}"/>')
    svg += f'<rect x="{inset}" y="{inset}" width="{tw}" height="{th}" rx="14" fill="none" stroke="{t["line"]}" stroke-width="1.5"/>'
    kind = project["kind"].upper()
    kind_w = measure(kind, "mono", 17, 1.6) + 26
    svg += f'<rect x="{inset + 16}" y="{inset + 16}" width="{kind_w:.1f}" height="34" rx="17" fill="{INK}" fill-opacity="0.78"/>'
    svg += svg.text(inset + 29, inset + 39, kind, "mono", 17, "#fff", tracking=1.6)

    svg += svg.text(32, title_y, project["name"], "display", 44, t["ink"])
    title_end = 32 + measure(project["name"], "display", 44)
    label = fit(project["label"], "mono", 20, W - 32 - 22 - title_end - 36)
    svg += svg.text(W - 32 - 22, title_y - 3, label, "mono", 20, t["muted"], anchor="end")
    svg += arrow(W - 32 - 14, title_y - 18, 14, t["accent"], 2.2)

    for k, line in enumerate(wrap(project["description"], "body", 25, text_w)[:desc_lines]):
        svg += svg.text(32, desc_y + k * lh, line, "body", 25, t["muted"])

    x = 32
    for tech in project["tech"]:
        w = measure(tech, "mono", 19) + 28
        svg += f'<rect x="{x:.1f}" y="{chips_y}" width="{w:.1f}" height="38" rx="10" fill="{t["chip"]}" stroke="{t["line"]}"/>'
        svg += svg.text(x + 14, chips_y + 25, tech, "mono", 19, t["ink"])
        x += w + 10
    write(f"work-{project['slug']}-{theme}.svg", svg)


def oss_card(repo, theme):
    t = THEMES[theme]
    W, H = 1280, 136
    svg = Svg(W, H, f"{repo['name']}: {repo['description']}")
    svg += card(W, H, t, rx=20)
    svg += svg.text(40, 62, repo["name"], "display", 40, t["ink"])
    right = W - 40 - 14
    svg += arrow(right, 46, 14, t["accent"], 2.2)
    meta = []
    if repo["stars"]:
        meta.append(f"{repo['stars']} STAR" + ("S" if repo["stars"] != 1 else ""))
    if repo["language"]:
        meta.append(repo["language"].upper())
    meta_s = "  ·  ".join(meta)
    meta_w = measure(meta_s, "mono", 19, 1.4)
    svg += svg.text(right - 18, 60, meta_s, "mono", 19, t["muted"], anchor="end", tracking=1.4)
    if repo["language"]:
        svg += f'<circle cx="{right - 18 - meta_w - 14:.1f}" cy="53.5" r="6.5" fill="{LANG_COLORS.get(repo["language"], t["muted"])}"/>'
    svg += svg.text(40, 102, fit(repo["description"], "body", 24, W - 80), "body", 24, t["muted"])
    write(f"oss-{repo['repo'].lower()}-{theme}.svg", svg)


def activity_card(weeks, theme):
    t = THEMES[theme]
    W, pad, cell, gap = 1280, 48, 18, 4
    step = cell + gap
    days = [d for week in weeks for d in week]
    H = 438

    counts = [d["contributionCount"] for d in days]
    total = sum(counts)
    active = sum(1 for c in counts if c)
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current, tail = 0, counts[:-1] if counts and not counts[-1] else counts  # today may still be empty
    for c in reversed(tail):
        if not c:
            break
        current += 1
    best = max(days, key=lambda d: d["contributionCount"]) if total else None

    svg = Svg(W, H, f"{total} contributions in the last year, current streak {current} days, longest streak {longest} days")
    svg += card(W, H, t)

    stats = [(f"{total:,}".replace(",", " "), "CONTRIBUTIONS"), (str(active), "ACTIVE DAYS"),
             (str(current), "CURRENT STREAK, DAYS"), (str(longest), "LONGEST STREAK, DAYS")]
    svg += svg.text(W - pad, pad + 20, "LAST 12 MONTHS", "mono", 17, t["muted"], anchor="end", tracking=1.4)
    col_w = (W - 2 * pad) / len(stats)
    for i, (value, label) in enumerate(stats):
        x = pad + i * col_w
        svg += svg.text(x, pad + 64, value, "display", 74, t["accent"] if i == 0 else t["ink"])
        svg += svg.text(x + 2, pad + 98, label, "mono", 17, t["muted"], tracking=1.4)

    nonzero = sorted(c for c in counts if c)

    def level(c):
        if not c:
            return 0
        rank = sum(1 for n in nonzero if n < c) / len(nonzero)
        return min(4, int(rank * 4) + 1)

    grid_w = len(weeks) * step - gap
    gx, gy = (W - grid_w) / 2, 214
    last_month, last_x = None, -99
    for wi, week in enumerate(weeks):
        x = gx + wi * step
        month = week[0]["date"][5:7]
        if month != last_month and x - last_x > 3 * step and int(week[0]["date"][8:]) <= 7:
            svg += svg.text(x, gy - 16, MONTHS[int(month) - 1], "mono", 16, t["muted"], tracking=1)
            last_x = x
        last_month = month
        for day in week:
            c = day["contributionCount"]
            lv = level(c)
            fill = LIME if best and day is best else (t["scale"][lv - 1] if lv else t["empty"])
            svg += f'<rect x="{x:.1f}" y="{gy + day["weekday"] * step}" width="{cell}" height="{cell}" rx="4" fill="{fill}"/>'

    ly = gy + 7 * step + 34
    svg += svg.text(gx, ly, "LESS", "mono", 16, t["muted"], tracking=1)
    x = gx + measure("LESS", "mono", 16, 1) + 12
    for fill in [t["empty"], *t["scale"]]:
        svg += f'<rect x="{x:.1f}" y="{ly - 13}" width="14" height="14" rx="3" fill="{fill}"/>'
        x += 18
    svg += svg.text(x + 8, ly, "MORE", "mono", 16, t["muted"], tracking=1)
    if best:
        d = best["date"]
        note = f"BEST DAY  {best['contributionCount']} ON {int(d[8:])} {MONTHS[int(d[5:7]) - 1]} {d[:4]}"
        note_w = measure(note, "mono", 16, 1)
        svg += svg.text(gx + grid_w, ly, note, "mono", 16, t["muted"], anchor="end", tracking=1)
        svg += f'<rect x="{gx + grid_w - note_w - 26:.1f}" y="{ly - 13}" width="14" height="14" rx="3" fill="{LIME}"/>'
    write(f"activity-{theme}.svg", svg)


MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


# ── GitHub API ───────────────────────────────────────────────────────────────────────────


def token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def api(path, body=None):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as res:
        return json.load(res)


def calendar():
    query = ("query($login:String!){user(login:$login){contributionsCollection{contributionCalendar"
             "{weeks{contributionDays{date weekday contributionCount}}}}}}")
    data = api("graphql", {"query": query, "variables": {"login": CONTENT["login"]}})
    return [w["contributionDays"] for w in data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]]


def repos():
    for entry in CONTENT["oss"]:
        data = api(f"repos/{CONTENT['login']}/{entry['repo']}")
        yield {
            "repo": entry["repo"], "url": data["html_url"],
            "name": entry.get("name", data["name"]),
            "description": entry.get("description", data["description"] or ""),
            "language": data["language"], "stars": data["stargazers_count"],
        }


# ── README ───────────────────────────────────────────────────────────────────────────────


def picture(base, alt, width="100%"):
    alt = escape(alt, {'"': "&quot;"})
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{base}-dark.svg">'
            f'<img src="assets/{base}-light.svg" alt="{alt}" width="{width}"></picture>')


def readme():
    c, h = CONTENT, CONTENT["header"]
    links = " &nbsp;·&nbsp; ".join(f'<a href="{url}">{escape(label)}</a>' for label, url in c["links"])
    work = []
    for i in range(0, len(c["work"]), 2):
        pair = [f'<a href="{p["url"]}">{picture("work-" + p["slug"], p["name"] + ": " + p["description"], "49%")}</a>'
                for p in c["work"][i:i + 2]]
        work.append("<p>\n  " + "\n  ".join(pair) + "\n</p>")
    oss = "\n".join(f'<a href="https://github.com/{c["login"]}/{r["repo"]}">{picture("oss-" + r["repo"].lower(), r.get("name", r["repo"]))}</a><br>'
                    for r in c["oss"])
    question, cta, cta_url = c["outro"]

    text = f"""<!-- Generated by scripts/build.py from scripts/content.json. Edit those, not this file. -->

<a href="https://marianmolnar.cz"><img src="assets/header.svg" alt="{h['name']}. {h['tagline']}" width="100%"></a>

<p>{escape(c['intro'])}</p>

<p>{links}</p>

<br>

{picture("heading-work", c["sections"]["work"])}

{chr(10).join(work)}

<br>

{picture("heading-stack", c["sections"]["stack"])}

{picture("stack", "Stack: " + ", ".join(label for col in c["stack"] for _, label in col["items"]))}

<br>

{picture("heading-oss", c["sections"]["oss"])}

{oss}

<br>

{picture("heading-activity", c["sections"]["activity"])}

{picture("activity", "Contribution activity over the last 12 months")}

<br>

<p align="center"><sub>{escape(question)} <a href="{cta_url}"><b>{escape(cta)} →</b></a></sub></p>
"""
    (ROOT / "README.md").write_text(text)
    print("  README.md")


def main():
    live_only = sys.argv[1:] == ["live"]
    themes = list(THEMES)
    if not live_only:
        header()
        for n, key in enumerate(CONTENT["sections"], 1):
            for theme in themes:
                heading(n, key, theme)
        lines = max(len(wrap(p["description"], "body", 25, 800 - 64)) for p in CONTENT["work"])
        for project in CONTENT["work"]:
            for theme in themes:
                work_card(project, theme, lines)
        for theme in themes:
            stack(theme)
        readme()
    for repo in repos():
        for theme in themes:
            oss_card(repo, theme)
    weeks = calendar()
    for theme in themes:
        activity_card(weeks, theme)


if __name__ == "__main__":
    main()
