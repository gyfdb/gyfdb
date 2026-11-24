"""Builds stats/stats.svg and stats/languages.svg from the GitHub API.

Needs STATS_TOKEN (classic PAT with repo + read:org + read:user).
Run with --offline data.json to render from a saved dump instead.
"""

import datetime as dt
import json
import os
import sys
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────

EXCLUDE_REPOS = {"gyfdb/RBXSRC"}          # not my code, would make me 60% C++
EXCLUDE_LANGS = set()                     # e.g. {"HTML", "Makefile"}
RENAME = {"Lua": "luau"}                  # all my lua is luau anyway
COLORS = {"rust": "#F74C00", "luau": "#00A2FF"}
TOP = 5                                   # anything past this goes in "other"
OUT = "stats"

# ── API ───────────────────────────────────────────────────────────────────────

def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['STATS_TOKEN']}", "User-Agent": "gyfdb-stats"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        sys.exit(f"graphql: {body['errors']}")
    return body["data"]


USER_Q = """{ viewer { login createdAt followers { totalCount }
  pullRequests { totalCount } issues { totalCount } } }"""

REPOS_Q = """query($cursor: String) { viewer {
  repositories(first: 100, after: $cursor, isFork: false,
               ownerAffiliations: [OWNER, ORGANIZATION_MEMBER, COLLABORATOR]) {
    pageInfo { hasNextPage endCursor }
    nodes { nameWithOwner isPrivate owner { login } stargazerCount
      languages(first: 25) { edges { size node { name color } } } } } } }"""

COMMITS_Q = """query($from: DateTime!, $to: DateTime!) { viewer {
  contributionsCollection(from: $from, to: $to) { totalCommitContributions } } }"""


def fetch():
    v = gql(USER_Q)["viewer"]

    repos, cursor = [], None
    while True:
        page = gql(REPOS_Q, cursor=cursor)["viewer"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    repos = [r for r in repos if r["nameWithOwner"] not in EXCLUDE_REPOS]

    # contributionsCollection only covers a year at a time
    commits = 0
    start = dt.datetime.fromisoformat(v["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        cc = gql(COMMITS_Q, **{"from": start.isoformat(), "to": end.isoformat()})
        commits += cc["viewer"]["contributionsCollection"]["totalCommitContributions"]
        start = end

    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            if name in EXCLUDE_LANGS:
                continue
            key = RENAME.get(name, name.lower())
            size, color = langs.get(key, (0, e["node"]["color"]))
            langs[key] = (size + e["size"], COLORS.get(key, color or "#8b8b8b"))

    mine = [r for r in repos if r["owner"]["login"] == v["login"]]
    return {
        "since": v["createdAt"][:4],
        "commits": commits,
        "prs": v["pullRequests"]["totalCount"],
        "issues": v["issues"]["totalCount"],
        "followers": v["followers"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": len(repos),
        "mine": len(mine),
        "orgs": len(repos) - len(mine),
        "private": sum(r["isPrivate"] for r in repos),
        "languages": [[k, s, c] for k, (s, c) in sorted(langs.items(), key=lambda x: -x[1][0])],
    }

# ── Render ────────────────────────────────────────────────────────────────────

# matches the 1280x320 banner templates (Default + gyfdb)
W, H = 1280, 320
SANS = "'Segoe UI', 'Segoe UI Variable', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "Consolas, 'Cascadia Mono', 'JetBrains Mono', 'DejaVu Sans Mono', monospace"
SHAPE = ("M0 24C0 10.7452 10.7452 0 24 0H1256C1269.25 0 1280 10.7452 1280 24V296C1280 309.255 "
         "1269.25 320 1256 320H24C10.7452 320 0 309.255 0 296V24Z")
# left-side 12px inside stroke, same mask trick figma exports
STROKE = ("M0 0H1280H0ZM1280 320H0H1280ZM24 320C4.11775 320 -12 303.882 -12 284V36C-12 16.1177 "
          "4.11775 0 24 0C17.3726 0 12 10.7452 12 24V296C12 309.255 17.3726 320 24 320ZM1280 0V320V0Z")
THEMES = {
    "default": dict(bg=("#1E1511", "#2B1E17"), glow="#E3B04B", bar="#E3B04B", chip="#E3B04B",
                    title="#EFE3D1", sub="#B9A68F"),
    "gyfdb": dict(bg=("#111E18", "#172B23"), glow="#4BE3D6", bar="#3FB6AD", chip="#4BE3D6",
                  title="#D1EFEB", sub="#8FB9B1"),
}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def chips(items, t, y=208):
    out, x = [], 64
    for it in items:
        w = round(20 + len(it) * 7.7)
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="29" rx="14.5" fill="{t["chip"]}" fill-opacity="0.14"/>'
                   f'<rect x="{x+.5}" y="{y+.5}" width="{w-1}" height="28" rx="14" stroke="{t["chip"]}" stroke-opacity="0.5" fill="none"/>'
                   f'<text x="{x + w/2}" y="{y+19.5}" text-anchor="middle" font-family="{MONO}" font-size="14" fill="{t["title"]}">{esc(it)}</text>')
        x += w + 10
    return "".join(out)


def banner(theme, title, sub, chip_items, art):
    t = THEMES[theme]
    return f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs>
<mask id="inside" fill="white"><path d="{SHAPE}"/></mask>
<clipPath id="c"><path d="{SHAPE}"/></clipPath>
<linearGradient id="lg" x1="0" y1="0" x2="150.588" y2="602.353" gradientUnits="userSpaceOnUse"><stop stop-color="{t["bg"][0]}"/><stop offset="1" stop-color="{t["bg"][1]}"/></linearGradient>
<radialGradient id="rg" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(1280 320) rotate(-178.351) scale(2919.71 913.467)"><stop stop-color="{t["glow"]}"/><stop offset="1" stop-opacity="0"/></radialGradient>
</defs>
<g clip-path="url(#c)">
<path d="{SHAPE}" fill="black"/>
<path d="{SHAPE}" fill="url(#lg)" fill-opacity="0.5"/>
<path d="{SHAPE}" fill="url(#rg)" fill-opacity="0.25"/>
<text x="64" y="126" font-family="{SANS}" font-weight="700" font-size="66" letter-spacing="-1" fill="{t["title"]}">{esc(title)}</text>
<text x="66" y="168" font-family="{SANS}" font-size="24" fill="{t["sub"]}">{esc(sub)}</text>
{chips(chip_items, t)}
{art(t)}
</g>
<path d="{STROKE}" fill="{t["bar"]}" mask="url(#inside)"/>
</svg>'''


def stats_svg(d):
    tiles = [("commits", d["commits"]), ("pull requests", d["prs"]),
             ("repos", d["repos"]), ("stars", d["stars"])]

    def art(t):
        out = []
        for i, (label, val) in enumerate(tiles):
            x = 700 + (i % 2) * 270
            y = 56 + (i // 2) * 112
            out.append(f'<rect x="{x}" y="{y}" width="254" height="96" rx="16" fill="{t["chip"]}" fill-opacity="0.08"/>'
                       f'<rect x="{x+.5}" y="{y+.5}" width="253" height="95" rx="15.5" stroke="{t["chip"]}" stroke-opacity="0.3" fill="none"/>'
                       f'<text x="{x+24}" y="{y+56}" font-family="{SANS}" font-weight="700" font-size="44" fill="{t["title"]}">{val:,}</text>'
                       f'<text x="{x+24}" y="{y+80}" font-family="{MONO}" font-size="15" fill="{t["sub"]}">{label}</text>')
        return "".join(out)

    return banner("gyfdb", "github stats", f"on github since {d['since']}",
                  [f"{d['mine']} mine", f"{d['orgs']} in orgs", f"{d['private']} private",
                   f"{d['followers']} followers"], art)


def langs_svg(d):
    langs = d["languages"]
    total = sum(s for _, s, _ in langs)
    shown = langs[:TOP]
    rest = total - sum(s for _, s, _ in shown)
    if rest > 0:
        shown.append(["other", rest, "#6b5f55"])

    def art(t):
        bx, bw, by = 700, 524, 70
        out = [f'<clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="18" rx="9"/></clipPath><g clip-path="url(#bar)">']
        x = bx
        for _, s, c in shown:
            w = bw * s / total
            out.append(f'<rect x="{x:.2f}" y="{by}" width="{w+0.5:.2f}" height="18" fill="{c}"/>')
            x += w
        out.append("</g>")
        for i, (name, s, c) in enumerate(shown):
            lx = bx + (i % 2) * 272
            ly = 140 + (i // 2) * 48
            out.append(f'<circle cx="{lx+8}" cy="{ly-6}" r="8" fill="{c}"/>'
                       f'<text x="{lx+26}" y="{ly}" font-family="{MONO}" font-size="18" fill="{t["title"]}">{esc(name)}</text>'
                       f'<text x="{lx+252}" y="{ly}" text-anchor="end" font-family="{MONO}" font-size="18" fill="{t["sub"]}">{100*s/total:.1f}%</text>')
        return "".join(out)

    return banner("default", "languages", f"across {d['repos']} repos, forks not counted",
                  [n for n, _, _ in langs[:3]] + ["by bytes"], art)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--offline":
        data = json.load(open(sys.argv[2]))
    else:
        data = fetch()
    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/stats.svg", "w", encoding="utf-8").write(stats_svg(data))
    open(f"{OUT}/languages.svg", "w", encoding="utf-8").write(langs_svg(data))
    print(f"{data['repos']} repos, {data['commits']} commits, {len(data['languages'])} languages")
