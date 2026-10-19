#!/usr/bin/env python3
"""Render the profile README cards into assets/:

  dark_mode.svg / light_mode.svg            neofetch-style card with the ASCII portrait
  dark_languages.svg / light_languages.svg  most used languages
  dark_streak.svg / light_streak.svg        contribution streak

Stats come from the GitHub GraphQL API when ACCESS_TOKEN is set; otherwise the
last values saved in assets/stats.json are reused so the cards never break.
Edit PROFILE below to change what the card says.
"""
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
USER = os.environ.get("USER_NAME", "mohmmedwee")
WIDTH = 60  # characters in the right-hand column
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Amman")
except Exception:  # tzdata missing: Jordan is fixed UTC+3
    LOCAL_TZ = dt.timezone(dt.timedelta(hours=3))

# None = blank line, ("-", title) = section header, (key, value) = dotted row.
# "{name}" values are filled from the fetched stats.
PROFILE = [
    ("@", "mohmmedwee@eloustah"),
    ("OS", "macOS, Linux"),
    ("Uptime", "{uptime}"),
    ("Host", "Amman, Jordan"),
    ("Role", "Full-Stack Developer"),
    ("Focus", "Web apps, APIs & AI tooling"),
    None,
    ("Languages.Code", "PHP, Python, TypeScript, JavaScript"),
    ("Languages.Frameworks", "Laravel, React, Vue.js, Node.js"),
    ("Languages.Data", "MySQL, Redis"),
    ("AI", "LLM agents, Whisper, OCR"),
    None,
    ("-", "Contact"),
    ("Website", "eloustah.com"),
    ("GitHub", "github.com/mohmmedwee"),
    None,
    ("-", "GitHub Stats"),
    ("Repos", "{repos}"),
    ("Commits", "{commits}"),
    ("Contributions (past year)", "{past_year}"),
    ("Followers", "{followers}"),
]

THEMES = {
    "dark": dict(bg="#161b22", border="#30363d", text="#c9d1d9", muted="#8b949e", key="#ffa657",
                 value="#a5d6ff", dots="#616e7f", title="#58a6ff", accent="#fb8c00"),
    "light": dict(bg="#f6f8fa", border="#d0d7de", text="#24292f", muted="#57606a", key="#953800",
                  value="#0a3069", dots="#c2cfde", title="#0969da", accent="#bc4c00"),
}
SANS = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"


def graphql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['ACCESS_TOKEN']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats():
    user = graphql(
        """query($login: String!) {
             user(login: $login) {
               createdAt
               followers { totalCount }
               repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount }
               repositoriesContributedTo(includeUserRepositories: false, privacy: PUBLIC,
                 contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY, PULL_REQUEST_REVIEW]) { totalCount }
             }
           }""",
        {"login": USER},
    )["user"]

    # Stars and languages over public, non-fork repos; languages weighted by bytes.
    stars, sizes, colors, cursor = 0, {}, {}, None
    while True:
        page = graphql(
            """query($login: String!, $after: String) {
                 user(login: $login) {
                   repositories(first: 100, after: $after, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
                     pageInfo { hasNextPage endCursor }
                     nodes {
                       stargazerCount
                       languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
                         edges { size node { name color } }
                       }
                     }
                   }
                 }
               }""",
            {"login": USER, "after": cursor},
        )["user"]["repositories"]
        for repo in page["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                sizes[name] = sizes.get(name, 0) + edge["size"]
                colors[name] = edge["node"]["color"] or "#8b949e"
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    total = sum(sizes.values()) or 1
    languages = [
        {"name": name, "color": colors[name], "percent": round(100 * size / total, 1)}
        for name, size in sorted(sizes.items(), key=lambda kv: -kv[1])[:8]
    ]

    # contributionsCollection spans at most one year, so walk the account year by year.
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    commits, days, start = 0, {}, created
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        coll = graphql(
            """query($login: String!, $from: DateTime!, $to: DateTime!) {
                 user(login: $login) {
                   contributionsCollection(from: $from, to: $to) {
                     totalCommitContributions
                     restrictedContributionsCount
                     contributionCalendar { weeks { contributionDays { date contributionCount } } }
                   }
                 }
               }""",
            {"login": USER, "from": start.isoformat(), "to": end.isoformat()},
        )["user"]["contributionsCollection"]
        commits += coll["totalCommitContributions"] + coll["restrictedContributionsCount"]
        for week in coll["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
        start = end

    return {
        "created": created.date().isoformat(),
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
        "commits": commits,
        "languages": languages,
        "days": dict(sorted(days.items())),
    }


def load_stats():
    cache = ASSETS / "stats.json"
    if os.environ.get("ACCESS_TOKEN"):
        stats = fetch_stats()
        cache.write_text(json.dumps(stats, indent=1) + "\n")
        return stats
    return json.loads(cache.read_text())


def uptime(since, today):
    years = today.year - since.year - ((today.month, today.day) < (since.month, since.day))
    anniversary = since.replace(year=since.year + years)
    months = (today.year - anniversary.year) * 12 + today.month - anniversary.month - (today.day < anniversary.day)
    month_mark = anniversary.month - 1 + months
    month_start = anniversary.replace(year=anniversary.year + month_mark // 12, month=month_mark % 12 + 1)
    days = (today - month_start).days
    plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


def streaks(days, today):
    """Return (total, current, current_range, longest, longest_range) from {date: count}."""
    dates = sorted(dt.date.fromisoformat(d) for d in days if dt.date.fromisoformat(d) <= today)
    counts = {d: days[d.isoformat()] for d in dates}
    total = sum(counts.values())

    longest, longest_range, run_start, run = 0, None, None, 0
    for d in dates:
        if counts[d]:
            run_start = d if run == 0 else run_start
            run += 1
            if run > longest:
                longest, longest_range = run, (run_start, d)
        else:
            run = 0

    # A streak isn't broken until today ends, so start counting from yesterday if today is empty.
    cursor = today if counts.get(today) else today - dt.timedelta(days=1)
    current, end = 0, cursor
    while counts.get(cursor):
        current += 1
        cursor -= dt.timedelta(days=1)
    current_range = (cursor + dt.timedelta(days=1), end) if current else None
    return total, current, current_range, longest, longest_range


def fmt_date(d, today):
    return d.strftime("%b %-d") if d.year == today.year else d.strftime("%b %-d, %Y")


def fmt_range(r, today):
    if not r:
        return ""
    a, b = r
    return fmt_date(a, today) if a == b else f"{fmt_date(a, today)} - {fmt_date(b, today)}"


def card_lines(values):
    """Yield the right-hand column as lists of (css class, text) spans."""
    for row in PROFILE:
        if row is None:
            yield []
            continue
        key, value = row
        value = value.format(**values)
        if key == "@":
            yield [(None, value + " " + "—" * (WIDTH - len(value) - 1))]
        elif key == "-":
            yield [(None, f"- {value} " + "—" * (WIDTH - len(value) - 3))]
        else:
            dots = WIDTH - len(key) - len(value) - 5
            assert dots > 0, f"card row too long by {1 - dots} chars: {key}: {value}"
            yield [("cc", ". "), ("key", key), (None, ":"), ("cc", " " + "." * max(dots, 1) + " "), ("value", value)]


def render_card(theme, values, art):
    t = THEMES[theme]
    out = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        '<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,Menlo,monospace" '
        'width="985px" height="550px" font-size="16px">',
        "<style>",
        "@font-face {src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback'; "
        "font-display: swap; -webkit-size-adjust: 109%; size-adjust: 109%;}",
        f".key {{fill: {t['key']};}} .value {{fill: {t['value']};}} .cc {{fill: {t['dots']};}}",
        "text, tspan {white-space: pre;}",
        "</style>",
        f'<rect width="985px" height="550px" fill="{t["bg"]}" rx="15"/>',
        f'<text x="15" y="30" fill="{t["text"]}">',
    ]
    for i, line in enumerate(art):
        out.append(f'<tspan x="15" y="{30 + 20 * i}">{escape(line)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="390" y="30" fill="{t["text"]}">')
    for i, spans in enumerate(card_lines(values)):
        inner = "".join(
            escape(text) if cls is None else f'<tspan class="{cls}">{escape(text)}</tspan>' for cls, text in spans
        )
        out.append(f'<tspan x="390" y="{30 + 20 * i}">{inner}</tspan>')
    out.append("</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_languages(theme, languages):
    t = THEMES[theme]
    rows = (len(languages) + 1) // 2
    height = 95 + 25 * rows
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" viewBox="0 0 495 {height}" font-family="{SANS}">',
        f'<rect x="0.5" y="0.5" width="494" height="{height - 1}" rx="4.5" fill="{t["bg"]}" stroke="{t["border"]}"/>',
        f'<text x="25" y="35" font-size="18" font-weight="600" fill="{t["title"]}">Most Used Languages</text>',
        '<clipPath id="bar"><rect x="25" y="55" width="445" height="8" rx="4"/></clipPath>',
        '<g clip-path="url(#bar)">',
    ]
    x = 25.0
    for lang in languages:
        w = 445 * lang["percent"] / 100
        out.append(f'<rect x="{x:.2f}" y="55" width="{w + 0.5:.2f}" height="8" fill="{lang["color"]}"/>')
        x += w
    out.append("</g>")
    for i, lang in enumerate(languages):
        cx, cy = 25 + 235 * (i // rows), 90 + 25 * (i % rows)
        out.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{lang["color"]}"/>')
        out.append(
            f'<text x="{cx + 18}" y="{cy}" font-size="13" fill="{t["text"]}">{escape(lang["name"])} '
            f'<tspan fill="{t["muted"]}">{lang["percent"]:.1f}%</tspan></text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_streak(theme, stats, today):
    t = THEMES[theme]
    total, current, current_range, longest, longest_range = streaks(stats["days"], today)
    created = dt.date.fromisoformat(stats["created"])
    num = lambda x, y, n, fill: f'<text x="{x}" y="{y}" text-anchor="middle" font-size="28" font-weight="700" fill="{fill}">{n:,}</text>'
    label = lambda x, y, s, fill, size=14, weight=400: (
        f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{size}" font-weight="{weight}" fill="{fill}">{escape(s)}</text>'
    )
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" font-family="{SANS}">',
        f'<rect x="0.5" y="0.5" width="494" height="194" rx="4.5" fill="{t["bg"]}" stroke="{t["border"]}"/>',
        f'<line x1="165" y1="28" x2="165" y2="170" stroke="{t["border"]}"/>',
        f'<line x1="330" y1="28" x2="330" y2="170" stroke="{t["border"]}"/>',
        num(82.5, 79, total, t["text"]),
        label(82.5, 120, "Total Contributions", t["text"]),
        label(82.5, 145, f"{fmt_date(created, today)} - Present", t["muted"], 12),
        f'<circle cx="247.5" cy="71" r="40" fill="none" stroke="{t["accent"]}" stroke-width="5"/>',
        num(247.5, 81, current, t["text"]),
        label(247.5, 140, "Current Streak", t["accent"], 14, 700),
        label(247.5, 165, fmt_range(current_range, today), t["muted"], 12),
        num(412.5, 79, longest, t["text"]),
        label(412.5, 120, "Longest Streak", t["text"]),
        label(412.5, 145, fmt_range(longest_range, today), t["muted"], 12),
        "</svg>",
    ]
    return "\n".join(out) + "\n"


def main():
    stats = load_stats()
    today = dt.datetime.now(LOCAL_TZ).date()
    year_ago = (today - dt.timedelta(days=365)).isoformat()
    values = {
        "uptime": uptime(dt.date.fromisoformat(stats["created"]), today),
        "repos": f"{stats['repos']:,}",
        "stars": f"{stats['stars']:,}",
        "contributed": f"{stats['contributed']:,}",
        "commits": f"{stats['commits']:,}",
        "past_year": f"{sum(n for d, n in stats['days'].items() if d > year_ago):,}",
        "followers": f"{stats['followers']:,}",
    }
    art = (ASSETS / "ascii.txt").read_text().splitlines()
    for theme in THEMES:
        prefix = "dark" if theme == "dark" else "light"
        (ASSETS / f"{prefix}_mode.svg").write_text(render_card(theme, values, art))
        (ASSETS / f"{prefix}_languages.svg").write_text(render_languages(theme, stats["languages"]))
        (ASSETS / f"{prefix}_streak.svg").write_text(render_streak(theme, stats, today))


if __name__ == "__main__":
    main()
