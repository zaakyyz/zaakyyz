"""Generate a contribution card for the GitHub profile README."""

import json
import os
import re
import subprocess
from datetime import datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen


USERNAME = os.environ.get("PROFILE_USERNAME", "zaakyyz")
ROOT = Path(__file__).resolve().parents[1]


def contribution_calendar():
    token = os.environ.get("GH_TOKEN")
    if not token:
        token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    query = """query($login:String!){user(login:$login){contributionsCollection{
      contributionCalendar{totalContributions weeks{contributionDays{date}}}
    }}}"""
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": USERNAME}}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "profile-card",
        },
    )
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(result["errors"])
    return result["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def generate():
    calendar = contribution_calendar()
    count = calendar["totalContributions"]
    first_day = calendar["weeks"][0]["contributionDays"][0]["date"]
    since = datetime.strptime(first_day, "%Y-%m-%d").strftime("%d %b %Y")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="170" viewBox="0 0 960 170" role="img">'
        f'<title>GitHub contributions</title><desc>{count:,} contributions since {escape(since)}</desc>'
        '<rect x=".5" y=".5" width="959" height="169" rx="16" fill="#0d1117" stroke="#30363d"/>'
        '<g font-family="Segoe UI,Arial,sans-serif">'
        '<text x="30" y="43" font-size="22" fill="#f0f6fc" font-weight="600">Contributions</text>'
        f'<text x="30" y="119" font-size="55" fill="#58a6ff" font-weight="700">{count:,}</text>'
        f'<text x="30" y="149" font-size="16" fill="#8b949e">Since {escape(since)}</text>'
        '</g></svg>\n'
    )
    image_path = ROOT / "assets" / "stats.svg"
    image_path.write_text(svg, encoding="utf-8")

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    version = sha256(svg.encode("utf-8")).hexdigest()[:12]
    readme, matches = re.subn(
        r"assets/stats\.svg(?:\?v=[0-9a-f]{12})?",
        f"assets/stats.svg?v={version}",
        readme,
    )
    if matches != 1:
        raise RuntimeError(f"Expected one README image reference, found {matches}")
    if readme != readme_path.read_text(encoding="utf-8"):
        readme_path.write_text(readme, encoding="utf-8")
    print(f"Updated contribution card: {count:,} since {since}.")


if __name__ == "__main__":
    generate()
