"""Generate self-contained profile SVGs using GitHub APIs and Python's stdlib."""

import json
import os
import re
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
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


def contribution_streaks(days, today):
    """Return the current and longest runs of days with contributions."""
    longest = (0, None, None)
    run_start = previous = None
    run_length = 0
    for day in sorted(day for day, count in days.items() if count > 0 and day <= today):
        if previous is None or day != previous + timedelta(days=1):
            run_start = day
            run_length = 0
        run_length += 1
        previous = day
        if run_length > longest[0]:
            longest = (run_length, run_start, day)

    current = (run_length, run_start, previous) if previous in (today, today - timedelta(days=1)) else (0, None, None)
    return current, longest


def date_span(start, end):
    if start is None:
        return "No active streak"
    if start == end:
        return start.strftime("%d %b %Y")
    if start.year == end.year:
        return f"{start:%d %b} – {end:%d %b %Y}"
    return f"{start:%d %b %Y} – {end:%d %b %Y}"


def stats_card(total, member_since, current, longest, stamp):
    current_count, current_start, current_end = current
    longest_count, longest_start, longest_end = longest
    body = (
        '<rect x=".5" y=".5" width="959" height="224" rx="16" fill="#0d1117" stroke="#30363d"/>'
        '<path d="M320 28v169M640 28v169" stroke="#30363d" stroke-width="1.5"/>'
        f'<text x="160" y="82" text-anchor="middle" font-size="44" fill="#58a6ff" font-weight="700">{total:,}</text>'
        '<text x="160" y="121" text-anchor="middle" font-size="17" fill="#f0f6fc">Total Contributions</text>'
        f'<text x="160" y="155" text-anchor="middle" font-size="13" fill="#8b949e">{member_since} – Present</text>'
        '<circle cx="480" cy="76" r="49" fill="none" stroke="#58a6ff" stroke-width="6"/>'
        f'<text x="480" y="89" text-anchor="middle" font-size="38" fill="#f0f6fc" font-weight="700">{current_count}</text>'
        '<text x="480" y="151" text-anchor="middle" font-size="17" fill="#f0f6fc" font-weight="600">Current Streak</text>'
        f'<text x="480" y="180" text-anchor="middle" font-size="13" fill="#8b949e">{escape(date_span(current_start, current_end))}</text>'
        f'<text x="800" y="82" text-anchor="middle" font-size="44" fill="#58a6ff" font-weight="700">{longest_count}</text>'
        '<text x="800" y="121" text-anchor="middle" font-size="17" fill="#f0f6fc">Longest Streak</text>'
        f'<text x="800" y="155" text-anchor="middle" font-size="13" fill="#8b949e">{escape(date_span(longest_start, longest_end))}</text>'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="225" viewBox="0 0 960 225" role="img">'
        '<title>GitHub contribution and streak statistics</title>'
        f'<desc>Updated {escape(stamp)}. Total {total:,}; current streak {current_count} days; longest streak {longest_count} days.</desc>'
        '<g font-family="Segoe UI,Arial,sans-serif">' + body + '</g></svg>\n'
    )


def generate():
    user = api(f"users/{USERNAME}")
    member_since = datetime.strptime(user["created_at"][:10], "%Y-%m-%d").strftime("%d %b %Y")
    repos = []
    page = 1
    while True:
        batch = api(f"users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        repos.extend(r for r in batch if not r["private"] and not r["fork"] and r["name"].lower() != USERNAME.lower())
        if len(batch) < 100:
            break
        page += 1
    query = """query($login:String!){user(login:$login){contributionsCollection{
      contributionYears
      contributionCalendar{totalContributions weeks{contributionDays{date contributionCount weekday}}}
    }}}"""
    collection = api("graphql", {"query": query, "variables": {"login": USERNAME}})["data"]["user"]["contributionsCollection"]
    calendar = collection["contributionCalendar"]
    now = datetime.now(timezone.utc)
    yearly_query = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
      contributionsCollection(from:$from,to:$to){contributionCalendar{
        totalContributions weeks{contributionDays{date contributionCount}}
      }}
    }}"""
    all_time_total = 0
    days = {}
    for year in collection["contributionYears"]:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = min(now, datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1))
        yearly = api("graphql", {"query": yearly_query, "variables": {
            "login": USERNAME, "from": start.isoformat(), "to": end.isoformat(),
        }})["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        all_time_total += yearly["totalContributions"]
        for week in yearly["weeks"]:
            for day in week["contributionDays"]:
                day_date = date.fromisoformat(day["date"])
                if day_date.year == year and day_date <= now.date():
                    days[day_date] = day["contributionCount"]
    stamp = now.strftime("%d %b %Y · UTC")
    current, longest = contribution_streaks(days, now.date())
    stats = stats_card(all_time_total, member_since, current, longest, stamp)

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
    activity = card("GitHub Activity", 282, body, f"GitHub contribution calendar · Updated {stamp}")
    ASSETS.mkdir(exist_ok=True)
    # Fetch all data successfully before replacing any existing card.
    cards = [("streak-stats.svg", stats), ("languages.svg", language_svg), ("activity.svg", activity)]
    for name, content in cards:
        (ASSETS / name).write_text(content, encoding="utf-8")
    readme_path = ASSETS.parent / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    for name, content in cards:
        version = sha256(content.encode("utf-8")).hexdigest()[:12]
        pattern = rf"assets/{re.escape(name)}(?:\?v=[0-9a-f]{{12}})?"
        readme, matches = re.subn(pattern, f"assets/{name}?v={version}", readme)
        if matches != 1:
            raise RuntimeError(f"Expected one README image reference for {name}, found {matches}")
    if readme != readme_path.read_text(encoding="utf-8"):
        readme_path.write_text(readme, encoding="utf-8")
    print(f"Updated 3 cards: {len(repos)} public original repos, {len(languages)} languages.")


if __name__ == "__main__":
    generate()
