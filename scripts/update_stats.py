"""Generate self-contained profile SVGs using GitHub APIs and Python's stdlib."""

import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

USERNAME = os.environ.get("PROFILE_USERNAME", "zaakyyz")
ASSETS = Path(__file__).resolve().parents[1] / "assets"
COLORS = ["#58a6ff", "#56e0b5", "#bc8cff", "#ffa657", "#f778ba", "#e3b341"]


def api(path, payload=None):
    token = os.environ.get("GH_TOKEN")
    if not token:
        token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    request = Request(
        "https://api.github.com/" + path,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "profile-cards"},
    )
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get("errors"):
        raise RuntimeError(result["errors"])
    return result


def text(x, y, value, size=14, color="#8b949e", weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(str(value))}</text>'


def card(title, height, body, subtitle):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}" role="img">'
        f'<title>{escape(title)}</title><desc>{escape(subtitle)}</desc>'
        f'<rect x=".5" y=".5" width="959" height="{height-1}" rx="16" fill="#0d1117" stroke="#30363d"/>'
        '<g font-family="Segoe UI,Arial,sans-serif">'
        + text(30, 39, title, 21, "#f0f6fc", 600)
        + text(30, 63, subtitle, 12)
        + body + '</g></svg>\n'
    )


def generate():
    user = api(f"users/{USERNAME}")
    repos = []
    page = 1
    while True:
        batch = api(f"users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        repos.extend(r for r in batch if not r["private"] and not r["fork"] and r["name"].lower() != USERNAME.lower())
        if len(batch) < 100:
            break
        page += 1
    query = """query($login:String!){user(login:$login){contributionsCollection{
      contributionCalendar{totalContributions weeks{contributionDays{date contributionCount weekday}}}
    }}}"""
    calendar = api("graphql", {"query": query, "variables": {"login": USERNAME}})["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y · UTC")
    metrics = [(len(repos), "Public original repos"), (sum(r["stargazers_count"] for r in repos), "Stars earned"), (user["followers"], "Followers"), (calendar["totalContributions"], "Contributions / year")]
    body = ""
    for i, (value, label) in enumerate(metrics):
        x = 30 + i * 232
        body += f'<rect x="{x}" y="86" width="204" height="101" rx="10" fill="#161b22"/>'
        body += text(x + 17, 132, f"{value:,}", 32, COLORS[i], 700) + text(x + 17, 163, label, 13)
    stats = card("GitHub statistics", 211, body, f"@{USERNAME} · Updated {stamp}")

    languages = Counter()
    for repo in repos:
        languages.update(api(f"repos/{USERNAME}/{repo['name']}/languages"))
    ranked = languages.most_common()
    if len(ranked) > 6:
        ranked = ranked[:5] + [("Other", sum(n for _, n in ranked[5:]))]
    total = sum(languages.values())
    body = ""
    x = 30.0
    for i, (name, count) in enumerate(ranked):
        width = 900 * count / total
        body += f'<rect x="{x:.2f}" y="88" width="{width:.2f}" height="15" fill="{COLORS[i]}"/>'
        x += width
        lx, ly = 30 + (i % 3) * 305, 138 + (i // 3) * 35
        body += f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{COLORS[i]}"/>'
        body += text(lx + 18, ly, f"{name}  {100*count/total:.1f}%", 13, "#c9d1d9")
    if not total:
        body += text(30, 125, "No public language data yet.")
    language_svg = card("Languages in my repositories", 205, body, "Share of code bytes · Public original repositories · Profile repository excluded")

    weeks = calendar["weeks"]
    body = ""
    step = min(16, 850 / max(len(weeks), 1))
    last_month = None
    for col, week in enumerate(weeks):
        for day in week["contributionDays"]:
            count = day["contributionCount"]
            fill = "#161b22" if count == 0 else ("#0e4429" if count < 3 else "#006d32" if count < 6 else "#26a641" if count < 10 else "#39d353")
            x, y = 62 + col * step, 108 + day["weekday"] * 17
            body += f'<rect x="{x:.2f}" y="{y}" width="{step-3:.2f}" height="13" rx="3" fill="{fill}"><title>{day["date"]}: {count} contributions</title></rect>'
        first = week["contributionDays"][0]["date"]
        month = first[:7]
        if month != last_month and col < len(weeks) - 2:
            body += text(62 + col * step, 94, datetime.strptime(first, "%Y-%m-%d").strftime("%b"), 11)
            last_month = month
    for row, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        body += text(29, 119 + row * 17, label, 10)
    body += text(30, 256, f"{calendar['totalContributions']:,} contributions in the last year", 13, "#c9d1d9")
    body += text(744, 256, "Less", 11)
    for i, fill in enumerate(["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]):
        body += f'<rect x="{776+i*18}" y="246" width="13" height="13" rx="3" fill="{fill}"/>'
    body += text(873, 256, "More", 11)
    activity = card("A year of building", 282, body, f"GitHub contribution calendar · Updated {stamp}")
    ASSETS.mkdir(exist_ok=True)
    # Fetch all data successfully before replacing any existing card.
    for name, content in [("stats.svg", stats), ("languages.svg", language_svg), ("activity.svg", activity)]:
        (ASSETS / name).write_text(content, encoding="utf-8")
    print(f"Updated 3 cards: {len(repos)} public original repos, {len(languages)} languages.")


if __name__ == "__main__":
    generate()
