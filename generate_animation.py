#!/usr/bin/env python3
"""
generate_animation.py - Contribution Destroyer SVG Generator
Uses REST API to count commits per repo per day, displayed on grid.
Spaceship destroys each active cell.
"""
import argparse
import math
import os
import random
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests

CELL = 11
GAP = 3
WEEKS = 53
DAYS = 7
GRID_X = 50
GRID_Y = 28
STEP = CELL + GAP
SVG_W = GRID_X + WEEKS * STEP + 30
SVG_H = GRID_Y + DAYS * STEP + 60

COLORS = {0: "#161b22", 1: "#0e4429", 2: "#006d32", 3: "#26a641", 4: "#39d353"}

WEEKDAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6
}


def fetch_contributions(username, token):
    """
    Fetch contribution data using GraphQL contributionCalendar.
    If it returns too few cells, augment with REST commit counts.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Step 1: Get the GraphQL calendar grid
    gql = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays {
            contributionCount
            date
            weekday
          }
        }
      }
    }
  }
}
"""
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": gql, "variables": {"login": username}},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"[!] GraphQL errors: {data['errors']}")

    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    total_gql = cal["totalContributions"]
    print(f"[*] GraphQL reports {total_gql} contributions")

    # Build date->count map from GQL
    date_count = {}
    for week in cal["weeks"]:
        for day in week["contributionDays"]:
            if day["contributionCount"] > 0:
                date_count[day["date"]] = day["contributionCount"]

    # Step 2: Also pull REST events for last 90 days to count commits per day
    print("[*] Fetching REST events to supplement...")
    event_counts = defaultdict(int)
    page = 1
    while page <= 5:
        resp = requests.get(
            f"https://api.github.com/users/{username}/events",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        if resp.status_code != 200:
            break
        events = resp.json()
        if not events:
            break
        for ev in events:
            if ev.get("type") == "PushEvent":
                date_str = ev["created_at"][:10]
                # Count number of commits in this push
                commits = ev.get("payload", {}).get("commits", [])
                commit_count = len(commits) if commits else 1
                event_counts[date_str] += commit_count
        page += 1

    print(f"[*] REST events found dates: {dict(event_counts)}")

    # Merge: use REST counts where GQL has 0
    for date_str, count in event_counts.items():
        if date_str not in date_count:
            date_count[date_str] = count
        else:
            # Use max of both
            date_count[date_str] = max(date_count[date_str], count)

    print(f"[*] Final date_count: {date_count}")

    # Build 53-week grid (Sun-Sat columns, Mon=0..Sun=6 rows)
    now = datetime.now(tz=timezone.utc)
    # Find the start of the grid (53 weeks ago, aligned to Sunday)
    grid_start = now - timedelta(weeks=WEEKS)
    # Align to start of week (Monday)
    grid_start = grid_start - timedelta(days=grid_start.weekday())
    grid_start = grid_start.replace(hour=0, minute=0, second=0, microsecond=0)

    grid = []
    for w in range(WEEKS):
        week_levels = []
        for d in range(DAYS):
            day = grid_start + timedelta(weeks=w, days=d)
            date_str = day.strftime("%Y-%m-%d")
            c = date_count.get(date_str, 0)
            lvl = 0 if c == 0 else (1 if c <= 2 else (2 if c <= 5 else (3 if c <= 9 else 4)))
            week_levels.append(lvl)
        grid.append(week_levels)

    total_active = sum(1 for w in grid for lv in w if lv > 0)
    print(f"[*] Grid has {total_active} active cells")
    return grid


def cx(col):
    return GRID_X + col * STEP + CELL / 2


def cy(row):
    return GRID_Y + row * STEP + CELL / 2


def build_svg(grid, username):
    targets = [(c, r, grid[c][r]) for c in range(len(grid)) for r in range(DAYS) if grid[c][r] > 0]
    targets.sort(key=lambda t: (t[0], t[1]))
    n = len(targets)

    MOVE_SPEED = 0.08
    LASER_DUR = 0.14
    EXPLODE_DUR = 0.22
    PAUSE = 3.0

    events = []
    t = 0.0
    sx, sy = cx(0), cy(0)

    for col, row, level in targets:
        tx = cx(col) - 22
        ty = cy(row)
        dist = math.hypot(abs(tx - sx), abs(ty - sy)) / STEP
        mv = max(0.10, dist * MOVE_SPEED)
        events.append({"t": t, "type": "move", "fx": sx, "fy": sy, "tx": tx, "ty": ty, "dur": mv})
        t += mv
        events.append({"t": t, "type": "laser", "sx": tx + 11, "sy": ty, "ex": cx(col), "ey": cy(row), "dur": LASER_DUR})
        events.append({"t": t + LASER_DUR * 0.6, "type": "explode", "col": col, "row": row, "level": level, "dur": EXPLODE_DUR})
        t += LASER_DUR + EXPLODE_DUR * 0.3
        sx, sy = tx, ty

    total = t + PAUSE
    lines = []
    a = lines.append

    a(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}">')
    a(f'<rect width="{SVG_W}" height="{SVG_H}" fill="#0d1117" rx="6"/>')
    a('<defs>')
    a('<filter id="glow"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    a('<filter id="xglow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    a('<radialGradient id="eg"><stop offset="0%" stop-color="#ffff00"/><stop offset="40%" stop-color="#ff6b35" stop-opacity="0.9"/><stop offset="100%" stop-color="#ff0000" stop-opacity="0"/></radialGradient>')
    a('<linearGradient id="sg" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#00b4d8"/><stop offset="100%" stop-color="#ffffff"/></linearGradient>')
    a('</defs>')

    rng = random.Random(42)
    for _ in range(55):
        sx2 = rng.randint(0, SVG_W)
        sy2 = rng.randint(0, SVG_H - 20)
        r2 = rng.uniform(0.3, 1.1)
        op = rng.uniform(0.2, 0.7)
        d2 = rng.uniform(1.5, 4.0)
        a(f'<circle cx="{sx2}" cy="{sy2}" r="{r2:.1f}" fill="white" opacity="{op:.2f}"><animate attributeName="opacity" values="{op:.2f};{op*0.3:.2f};{op:.2f}" dur="{d2:.1f}s" repeatCount="indefinite"/></circle>')

    day_names = ["Mon", "", "Wed", "", "Fri", "", ""]
    for i, dn in enumerate(day_names):
        if dn:
            a(f'<text x="{GRID_X-4}" y="{GRID_Y + i*STEP + CELL}" text-anchor="end" font-family="Fira Code,monospace" font-size="8" fill="#8b949e">{dn}</text>')

    now2 = datetime.now(tz=timezone.utc)
    for w in range(0, WEEKS, 4):
        d = now2 - timedelta(weeks=WEEKS - w)
        lbl = d.strftime("%b")
        a(f'<text x="{GRID_X + w*STEP}" y="{GRID_Y-4}" font-family="Fira Code,monospace" font-size="8" fill="#8b949e">{lbl}</text>')

    a('<g id="grid">')
    for col, week in enumerate(grid):
        for row, level in enumerate(week):
            rx2 = GRID_X + col * STEP
            ry2 = GRID_Y + row * STEP
            a(f'<rect id="c{col}_{row}" x="{rx2}" y="{ry2}" width="{CELL}" height="{CELL}" rx="2" fill="{COLORS[level]}"/>')
    a('</g>')

    for ev in events:
        if ev["type"] != "explode":
            continue
        col2, row2 = ev["col"], ev["row"]
        ts = ev["t"]
        dur = ev["dur"]
        a(f'<animate xlink:href="#c{col2}_{row2}" attributeName="opacity" values="1;1;0;0" keyTimes="0;{ts/total:.4f};{(ts+0.04)/total:.4f};1" dur="{total:.2f}s" repeatCount="indefinite"/>')
        ox, oy = cx(col2), cy(row2)
        a(f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="0" fill="url(#eg)" filter="url(#xglow)" opacity="0"><animate attributeName="r" values="0;0;{CELL*1.8:.0f};0" keyTimes="0;{ts/total:.4f};{(ts+dur*0.5)/total:.4f};{(ts+dur)/total:.4f}" dur="{total:.2f}s" repeatCount="indefinite"/><animate attributeName="opacity" values="0;0;1;0" keyTimes="0;{ts/total:.4f};{(ts+dur*0.3)/total:.4f};{(ts+dur)/total:.4f}" dur="{total:.2f}s" repeatCount="indefinite"/></circle>')
        for ang in range(0, 360, 60):
            rad = math.radians(ang)
            ex2 = ox + math.cos(rad) * CELL * 2.4
            ey2 = oy + math.sin(rad) * CELL * 2.4
            a(f'<line x1="{ox:.1f}" y1="{oy:.1f}" x2="{ox:.1f}" y2="{oy:.1f}" stroke="#ff6b35" stroke-width="1.5" opacity="0" filter="url(#glow)"><animate attributeName="x2" values="{ox:.1f};{ox:.1f};{ex2:.1f};{ex2:.1f}" keyTimes="0;{ts/total:.4f};{(ts+dur*0.6)/total:.4f};1" dur="{total:.2f}s" repeatCount="indefinite"/><animate attributeName="y2" values="{oy:.1f};{oy:.1f};{ey2:.1f};{ey2:.1f}" keyTimes="0;{ts/total:.4f};{(ts+dur*0.6)/total:.4f};1" dur="{total:.2f}s" repeatCount="indefinite"/><animate attributeName="opacity" values="0;0;1;0" keyTimes="0;{ts/total:.4f};{(ts+dur*0.2)/total:.4f};{(ts+dur)/total:.4f}" dur="{total:.2f}s" repeatCount="indefinite"/></line>')

    for ev in events:
        if ev["type"] != "laser":
            continue
        lsx, lsy = ev["sx"], ev["sy"]
        lex, ley = ev["ex"], ev["ey"]
        ts = ev["t"]
        dur = ev["dur"]
        for sw, col3, opacity3 in [(2.5, "#ff4500", "0;0;1;0;0"), (1.0, "#ffffff", "0;0;0.9;0;0")]:
            kt = f"0;{ts/total:.4f};{(ts+dur*0.3)/total:.4f};{(ts+dur)/total:.4f};1"
            a(f'<line x1="{lsx:.1f}" y1="{lsy:.1f}" x2="{lsx:.1f}" y2="{lsy:.1f}" stroke="{col3}" stroke-width="{sw}" opacity="0" stroke-linecap="round" filter="url(#glow)"><animate attributeName="x2" values="{lsx:.1f};{lsx:.1f};{lex:.1f};{lex:.1f}" keyTimes="0;{ts/total:.4f};{(ts+dur)/total:.4f};1" dur="{total:.2f}s" repeatCount="indefinite"/><animate attributeName="y2" values="{lsy:.1f};{lsy:.1f};{ley:.1f};{ley:.1f}" keyTimes="0;{ts/total:.4f};{(ts+dur)/total:.4f};1" dur="{total:.2f}s" repeatCount="indefinite"/><animate attributeName="opacity" values="{opacity3}" keyTimes="{kt}" dur="{total:.2f}s" repeatCount="indefinite"/></line>')

    move_evs = [e for e in events if e["type"] == "move"]
    if move_evs:
        xs = [str(move_evs[0]["fx"])]
        ys = [str(move_evs[0]["fy"])]
        kts = ["0"]
        for e in move_evs:
            k1 = f"{e['t']/total:.4f}"
            k2 = f"{(e['t']+e['dur'])/total:.4f}"
            xs += [str(e["fx"]), str(e["tx"])]
            ys += [str(e["fy"]), str(e["ty"])]
            kts += [k1, k2]
        xs.append(str(move_evs[-1]["tx"]))
        ys.append(str(move_evs[-1]["ty"]))
        kts.append("1")
        vals = ";".join(f"{x},{y}" for x, y in zip(xs, ys))
        kt_str = ";".join(kts)
        a(f'<g filter="url(#glow)"><animateTransform attributeName="transform" type="translate" values="{vals}" keyTimes="{kt_str}" dur="{total:.2f}s" repeatCount="indefinite" calcMode="linear"/>')
        a('<path d="M0,-8 L18,0 L0,8 L3,3 L-5,3 L-5,-3 L3,-3 Z" fill="url(#sg)" opacity="0.95"/>')
        a('<ellipse cx="-6" cy="0" rx="5" ry="2.5" fill="#00b4d8" opacity="0.6"><animate attributeName="rx" values="5;7;4;6;5" dur="0.35s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.6;0.9;0.4;0.8;0.6" dur="0.35s" repeatCount="indefinite"/></ellipse>')
        a('<ellipse cx="7" cy="0" rx="3.5" ry="2" fill="#e0f7ff" opacity="0.8"/>')
        a('</g>')

    a(f'<text x="{SVG_W//2}" y="{SVG_H-10}" text-anchor="middle" font-family="Fira Code,monospace" font-size="9" fill="#8b949e">{username} · {n} commits obliterated</text>')
    a('</svg>')
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--output", default="dist/contribution-destroyer.svg")
    args = parser.parse_args()
    print(f"[*] Fetching contributions for @{args.username}...")
    grid = fetch_contributions(args.username, args.token)
    total = sum(1 for w in grid for lv in w if lv > 0)
    print(f"[*] {total} active cells will be destroyed")
    print("[*] Generating SVG...")
    svg = build_svg(grid, args.username)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"[+] Written {os.path.getsize(args.output)/1024:.1f}KB -> {args.output}")


if __name__ == "__main__":
    main()
