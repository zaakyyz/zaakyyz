"""Generate the self-contained language SVG for the profile."""

import json
import os
import re
import subprocess
from collections import Counter
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


def generate():
    repos = []
    page = 1
    while True:
        batch = api(f"users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        repos.extend(r for r in batch if not r["private"] and not r["fork"] and r["name"].lower() != USERNAME.lower())
        if len(batch) < 100:
            break
        page += 1

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

    ASSETS.mkdir(exist_ok=True)
    cards = [("languages.svg", language_svg)]
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
    print(f"Updated language card: {len(repos)} public original repos, {len(languages)} languages.")


if __name__ == "__main__":
    generate()
