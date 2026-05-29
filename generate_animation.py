#!/usr/bin/env python3
"""
generate_animation.py
Generates a custom animated SVG: a spaceship that flies across the GitHub
contribution grid and destroys each commit square with a laser beam.

Usage:
    python generate_animation.py \
        --username sadidata \
        --token $GITHUB_TOKEN \
        --output dist/contribution-destroyer.svg
        """

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import requests

# ── Constants ────────────────────────────────────────────────────────────────

CELL          = 11          # px per contribution cell
GAP           = 3           # px gap between cells
WEEKS         = 53          # columns shown
DAYS          = 7           # rows
GRID_X        = 60          # left offset (room for day labels)
GRID_Y        = 30          # top offset
CELL_STEP     = CELL + GAP  # 14 px per step
SVG_W         = GRID_X + WEEKS * CELL_STEP + 40
SVG_H         = GRID_Y + DAYS * CELL_STEP + 80

COLORS = {
      0: "#161b22",    # empty
      1: "#0e4429",    # level 1
      2: "#006d32",    # level 2
      3: "#26a641",    # level 3
      4: "#39d353",    # level 4
}

SHIP_W        = 28
SHIP_H        = 18
LASER_COLOR   = "#ff4500"
EXPLOSION_CLR = "#ff6b35"
BG_COLOR      = "#0d1117"
LABEL_COLOR   = "#8b949e"
SHIP_COLOR    = "#00b4d8"
ACCENT        = "#00b4d8"

# ── GitHub API ────────────────────────────────────────────────────────────────

def fetch_contributions(username: str, token: str) -> List[List[int]]:
      """
          Fetch the last 52 weeks of contribution data via GitHub GraphQL API.
              Returns a list of 53 weeks, each week a list of 7 days (0-4 level).
                  """
      query = """
      query($login: String!) {
        user(login: $login) {
          contributionsCollection {
            contributionCalendar {
              weeks {
                contributionDays {
                  contributionCount
                  date
                }
              }
            }
          }
        }
      }
      """
      headers = {
          "Authorization": f"Bearer {token}",
          "Content-Type": "application/json",
      }
      resp = requests.post(
          "https://api.github.com/graphql",
          json={"query": query, "variables": {"login": username}},
          headers=headers,
          timeout=30,
      )
      resp.raise_for_status()
      data = resp.json()

    weeks_raw = (
              data["data"]["user"]["contributionsCollection"]
              ["contributionCalendar"]["weeks"]
    )

    grid = []
    for week in weeks_raw[-WEEKS:]:
              days = week["contributionDays"]
              levels = []
              for day in days:
                            c = day["contributionCount"]
                            if c == 0:
                                              levels.append(0)
elif c <= 2:
                levels.append(1)
elif c <= 5:
                levels.append(2)
elif c <= 9:
                levels.append(3)
else:
                levels.append(4)
          # pad to 7 if needed
          while len(levels) < DAYS:
                        levels.append(0)
                    grid.append(levels)

    # Pad to WEEKS columns
    while len(grid) < WEEKS:
              grid.insert(0, [0] * DAYS)

    return grid


# ── SVG helpers ───────────────────────────────────────────────────────────────

def cell_center(col: int, row: int) -> Tuple[float, float]:
      x = GRID_X + col * CELL_STEP + CELL / 2
      y = GRID_Y + row * CELL_STEP + CELL / 2
      return x, y


def ship_path() -> str:
      """Return SVG path for a small spaceship pointing right (→)."""
      return (
          "M0,-9 L18,0 L0,9 L4,4 L-6,4 L-6,-4 L4,-4 Z"
          # Main body + cockpit
      )


# ── Animation logic ───────────────────────────────────────────────────────────

def collect_targets(grid: List[List[int]]) -> List[Tuple[int, int, int]]:
      """
          Returns list of (col, row, level) for every non-empty cell,
              sorted in scan order: left→right, top→bottom.
                  """
      targets = []
      for col, week in enumerate(grid):
                for row, level in enumerate(week):
                              if level > 0:
                                                targets.append((col, row, level))
                                    # Sort: sweep column by column
                                    targets.sort(key=lambda t: (t[0], t[1]))
                      return targets


def build_svg(grid: List[List[int]], username: str) -> str:
      targets    = collect_targets(grid)
      n_targets  = len(targets)

    # ── Timing ──────────────────────────────────────────────────────────────
      MOVE_DUR   = 0.45   # s per cell-to-cell move
    LASER_DUR  = 0.15   # s laser travels
    EXPLODE_DUR= 0.30   # s explosion
    PAUSE_END  = 1.5    # s pause at end before loop

    # Build a timeline: list of events (time, type, data)
    t = 0.0
    events = []  # (t_start, event_type, col, row, level)

    ship_x, ship_y = cell_center(0, 0)  # start top-left

    for i, (col, row, level) in enumerate(targets):
              cx, cy = cell_center(col, row)
              # Move ship to fire position (left of target)
              fire_x = cx - SHIP_W
              fire_y = cy
              dx = abs(fire_x - ship_x)
              dy = abs(fire_y - ship_y)
              dist = math.hypot(dx, dy) / CELL_STEP
              move_t = max(0.2, dist * MOVE_DUR * 0.18)

        events.append({
                      "t": t,
                      "type": "move",
                      "from_x": ship_x, "from_y": ship_y,
                      "to_x":   fire_x, "to_y":   fire_y,
                      "dur":    move_t,
        })
        t += move_t

        # Fire laser
        events.append({
                      "t": t,
                      "type": "laser",
                      "sx": fire_x + SHIP_W / 2, "sy": fire_y,
                      "ex": cx, "ey": cy,
                      "dur": LASER_DUR,
        })

        # Explosion
        events.append({
                      "t": t + LASER_DUR * 0.7,
                      "type": "explode",
                      "col": col, "row": row, "level": level,
                      "dur": EXPLODE_DUR,
        })

        t += LASER_DUR + EXPLODE_DUR * 0.4

        ship_x, ship_y = fire_x, fire_y

    total_dur = t + PAUSE_END

    # ── Build SVG ────────────────────────────────────────────────────────────
    lines = []
    a = lines.append

    a(f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{SVG_W}" height="{SVG_H}" '
            f'viewBox="0 0 {SVG_W} {SVG_H}">')

    a(f'  <rect width="{SVG_W}" height="{SVG_H}" fill="{BG_COLOR}" rx="6"/>')

    # ── Defs ─────────────────────────────────────────────────────────────────
    a('  <defs>')

    # Glow filter for laser
    a('''  <filter id="laser-glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>''')

    # Glow filter for ship
    a('''  <filter id="ship-glow" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="3" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>''')

    # Explosion filter
    a('''  <filter id="explode-glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="4" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>''')

    # Radial gradient for explosion
    a(f'''  <radialGradient id="exp-grad">
        <stop offset="0%"   stop-color="#ffff00" stop-opacity="1"/>
            <stop offset="40%"  stop-color="{EXPLOSION_CLR}" stop-opacity="0.9"/>
                <stop offset="100%" stop-color="#ff0000" stop-opacity="0"/>
                  </radialGradient>''')

    # Ship gradient
    a(f'''  <linearGradient id="ship-grad" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%"   stop-color="{SHIP_COLOR}"/>
            <stop offset="100%" stop-color="#ffffff"/>
              </linearGradient>''')

    a('  </defs>')

    # ── Stars background ─────────────────────────────────────────────────────
    import random
    rng = random.Random(42)
    for _ in range(60):
              sx = rng.randint(0, SVG_W)
              sy = rng.randint(0, SVG_H - 30)
              sr = rng.uniform(0.4, 1.2)
              op = rng.uniform(0.2, 0.7)
              dur2 = rng.uniform(1.5, 4.0)
              a(f'  <circle cx="{sx}" cy="{sy}" r="{sr:.1f}" fill="white" opacity="{op:.2f}">'
                f'<animate attributeName="opacity" values="{op:.2f};{op*0.3:.2f};{op:.2f}" '
                f'dur="{dur2:.1f}s" repeatCount="indefinite"/></circle>')

    # ── Day labels ───────────────────────────────────────────────────────────
    day_names = ["Mon", "", "Wed", "", "Fri", "", ""]
    for i, name in enumerate(day_names):
              if name:
                            y = GRID_Y + i * CELL_STEP + CELL
                            a(f'  <text x="{GRID_X - 5}" y="{y}" text-anchor="end" '
                              f'font-family="Fira Code,monospace" font-size="8" '
                              f'fill="{LABEL_COLOR}">{name}</text>')

          # ── Month labels ─────────────────────────────────────────────────────────
          # (simplified: just show every 4 weeks)
    now = datetime.now(tz=timezone.utc)
    for w in range(0, WEEKS, 4):
              d = now - timedelta(weeks=WEEKS - w)
              label = d.strftime("%b")
              lx = GRID_X + w * CELL_STEP
              a(f'  <text x="{lx}" y="{GRID_Y - 5}" '
                f'font-family="Fira Code,monospace" font-size="8" '
                f'fill="{LABEL_COLOR}">{label}</text>')

    # ── Static contribution grid ─────────────────────────────────────────────
    # We draw all cells; destroyed ones will be animated to disappear
    a('  <g id="grid">')
    for col, week in enumerate(grid):
              for row, level in enumerate(week):
                            rx = GRID_X + col * CELL_STEP
                            ry = GRID_Y + row * CELL_STEP
                            color = COLORS[level]
                            a(f'    <rect id="c{col}_{row}" x="{rx}" y="{ry}" '
                              f'width="{CELL}" height="{CELL}" rx="2" fill="{color}"/>')
                    a('  </g>')

    # ── Animate destroyed cells ──────────────────────────────────────────────
    for ev in events:
              if ev["type"] != "explode":
                            continue
                        col, row = ev["col"], ev["row"]
        t_start  = ev["t"]
        dur      = ev["dur"]
        rx = GRID_X + col * CELL_STEP
        ry = GRID_Y + row * CELL_STEP

        # The cell fades + scales to 0 on explosion
        a(f'  <rect x="{rx}" y="{ry}" width="{CELL}" height="{CELL}" rx="2" '
                    f'fill="{COLORS[ev["level"]]}" opacity="0">'
                    f'  <animate attributeName="opacity" values="0;0;1;0" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+0.05)/total_dur:.4f};{(t_start+dur)/total_dur:.4f}" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'</rect>')

        # Hide the original cell at explosion time
        a(f'  <animate xlink:href="#c{col}_{row}" attributeName="opacity" '
                    f'  values="1;1;0;0" '
                    f'  keyTimes="0;{t_start/total_dur:.4f};{(t_start+0.05)/total_dur:.4f};1" '
                    f'  dur="{total_dur:.2f}s" repeatCount="indefinite"/>')

    # ── Explosion bursts ─────────────────────────────────────────────────────
    for ev in events:
              if ev["type"] != "explode":
                            continue
                        col, row = ev["col"], ev["row"]
        cx, cy   = cell_center(col, row)
        t_start  = ev["t"]
        dur      = ev["dur"]

        # Main explosion circle
        a(f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="0" '
                    f'fill="url(#exp-grad)" filter="url(#explode-glow)" opacity="0">'
                    f'  <animate attributeName="r" values="0;0;{CELL*1.8:.0f};0" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur*0.5)/total_dur:.4f};{(t_start+dur)/total_dur:.4f}" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'  <animate attributeName="opacity" values="0;0;1;0" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur*0.3)/total_dur:.4f};{(t_start+dur)/total_dur:.4f}" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'</circle>')

        # Spark particles
        for angle in range(0, 360, 60):
                      rad = math.radians(angle)
                      ex2 = cx + math.cos(rad) * CELL * 2.5
                      ey2 = cy + math.sin(rad) * CELL * 2.5
                      a(f'  <line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" '
                        f'stroke="{EXPLOSION_CLR}" stroke-width="1.5" opacity="0" '
                        f'filter="url(#laser-glow)">'
                        f'  <animate attributeName="x2" values="{cx:.1f};{cx:.1f};{ex2:.1f};{ex2:.1f}" '
                        f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur*0.6)/total_dur:.4f};1" '
                        f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                        f'  <animate attributeName="y2" values="{cy:.1f};{cy:.1f};{ey2:.1f};{ey2:.1f}" '
                        f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur*0.6)/total_dur:.4f};1" '
                        f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                        f'  <animate attributeName="opacity" values="0;0;1;0" '
                        f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur*0.2)/total_dur:.4f};{(t_start+dur)/total_dur:.4f}" '
                        f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                        f'</line>')

    # ── Laser beams ──────────────────────────────────────────────────────────
    for ev in events:
              if ev["type"] != "laser":
                            continue
                        sx, sy = ev["sx"], ev["sy"]
        ex2, ey2 = ev["ex"], ev["ey"]
        t_start  = ev["t"]
        dur      = ev["dur"]

        a(f'  <line x1="{sx:.1f}" y1="{sy:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" '
                    f'stroke="{LASER_COLOR}" stroke-width="2.5" opacity="0" '
                    f'stroke-linecap="round" filter="url(#laser-glow)">'
                    f'  <animate attributeName="x2" values="{sx:.1f};{sx:.1f};{ex2:.1f};{ex2:.1f}" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur)/total_dur:.4f};1" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'  <animate attributeName="y2" values="{sy:.1f};{sy:.1f};{ey2:.1f};{ey2:.1f}" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur)/total_dur:.4f};1" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'  <animate attributeName="opacity" values="0;0;1;0;0" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur*0.3)/total_dur:.4f};{(t_start+dur)/total_dur:.4f};1" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'</line>')

        # Laser core (brighter, thinner)
        a(f'  <line x1="{sx:.1f}" y1="{sy:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" '
                    f'stroke="#ffffff" stroke-width="1" opacity="0">'
                    f'  <animate attributeName="x2" values="{sx:.1f};{sx:.1f};{ex2:.1f};{ex2:.1f}" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur)/total_dur:.4f};1" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'  <animate attributeName="y2" values="{sy:.1f};{sy:.1f};{ey2:.1f};{ey2:.1f}" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur)/total_dur:.4f};1" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'  <animate attributeName="opacity" values="0;0;0.8;0;0" '
                    f'    keyTimes="0;{t_start/total_dur:.4f};{(t_start+dur*0.3)/total_dur:.4f};{(t_start+dur)/total_dur:.4f};1" '
                    f'    dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
                    f'</line>')

    # ── Spaceship ────────────────────────────────────────────────────────────
    # Build full ship position timeline
    move_events = [ev for ev in events if ev["type"] == "move"]
    if move_events:
              x_vals  = []
        y_vals  = []
        kt_vals = []

        # Start position
        x_vals.append(str(move_events[0]["from_x"]))
        y_vals.append(str(move_events[0]["from_y"]))
        kt_vals.append("0")

        for ev in move_events:
                      kt_start = f"{ev['t']/total_dur:.4f}"
                      kt_end   = f"{(ev['t'] + ev['dur'])/total_dur:.4f}"
                      x_vals  += [str(ev["from_x"]), str(ev["to_x"])]
                      y_vals  += [str(ev["from_y"]), str(ev["to_y"])]
                      kt_vals += [kt_start, kt_end]

        # Final position + hold to end
        last = move_events[-1]
        x_vals.append(str(last["to_x"]))
        y_vals.append(str(last["to_y"]))
        kt_vals.append("1")

        x_str  = ";".join(x_vals)
        y_str  = ";".join(y_vals)
        kt_str = ";".join(kt_vals)

        ship_start_x = float(move_events[0]["from_x"])
        ship_start_y = float(move_events[0]["from_y"])

        a(f'  <g id="ship" transform="translate({ship_start_x:.1f},{ship_start_y:.1f})" '
                    f'filter="url(#ship-glow)">')
        a(f'    <animateTransform attributeName="transform" type="translate" '
                    f'      values="{";".join(f"{x},{y}" for x,y in zip(x_vals, y_vals))}" '
                    f'      keyTimes="{kt_str}" '
                    f'      dur="{total_dur:.2f}s" repeatCount="indefinite" '
                    f'      calcMode="linear"/>')

        # Ship body
        a(f'    <path d="{ship_path()}" fill="url(#ship-grad)" opacity="0.95"/>')

        # Engine glow
        a(f'    <ellipse cx="-7" cy="0" rx="5" ry="3" fill="{SHIP_COLOR}" opacity="0.6">'
                    f'      <animate attributeName="rx" values="5;7;4;6;5" dur="0.4s" repeatCount="indefinite"/>'
                    f'      <animate attributeName="opacity" values="0.6;0.9;0.4;0.8;0.6" dur="0.4s" repeatCount="indefinite"/>'
                    f'    </ellipse>')

        # Cockpit
        a(f'    <ellipse cx="8" cy="0" rx="4" ry="2.5" fill="#e0f7ff" opacity="0.8"/>')
        a('  </g>')

    # ── Title / Footer ───────────────────────────────────────────────────────
    footer_y = SVG_H - 12
    a(f'  <text x="{SVG_W // 2}" y="{footer_y}" text-anchor="middle" '
            f'font-family="Fira Code,monospace" font-size="9" fill="{LABEL_COLOR}">'
            f'  {username} · Contribution Destroyer · {n_targets} commits obliterated'
            f'</text>')

    a('</svg>')

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
      parser = argparse.ArgumentParser(description="Generate contribution destroyer SVG")
    parser.add_argument("--username", required=True)
    parser.add_argument("--token",    required=True)
    parser.add_argument("--output",   default="dist/contribution-destroyer.svg")
    args = parser.parse_args()

    print(f"[*] Fetching contributions for @{args.username}...")
    grid = fetch_contributions(args.username, args.token)

    total = sum(1 for week in grid for level in week if level > 0)
    print(f"[*] Found {total} non-empty cells across {len(grid)} weeks")

    print("[*] Generating SVG animation...")
    svg = build_svg(grid, args.username)

    out_path = args.output
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
              f.write(svg)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"[+] SVG written to {out_path} ({size_kb:.1f} KB)")
    print(f"[+] Animation duration: ~{total * 0.6:.0f}s for {total} targets")


if __name__ == "__main__":
      main()
