#!/usr/bin/env python3
"""ASCII viewer for jsonl game recordings.

Usage:
    python benchmarks/ascii_view.py recordings/empty_10000.jsonl --turns 1000,5000,10000 [--size 100x40] [--mode glyph|pop|faction]

Quantizes the map into an X by Y grid and draws one glyph per cell:
    empty   : '·'
    army    : '▲' (faction color)
    stack   : '▲' + xN label (3+ same-faction armies in one cell)
    town    : '●' (faction color)
    capital : '◆' (faction color)
    clash   : '*' (2+ factions in one cell — battles at a glance)

Priority on collision: clash > capital > town > stack > army.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

# ANSI faction colors (match viewer palette order 0..4)
COLORS = ["\033[94m", "\033[92m", "\033[91m", "\033[93m", "\033[95m"]
RESET = "\033[0m"
DIM = "\033[2m"
BOLD_RED = "\033[1;91m"

EMPTY = "·"
ARMY = "▲"
TOWN = "●"
CAPITAL = "◆"
CLASH = "*"


def pop_bucket(pop: float) -> int:
    """Log-scale pop bucket 1-9: doublings from founding size (~500).
    1=0.5k 2=1k 3=2k 4=4k 5=8k 6=16k 7=32k 8=64k 9=128k+."""
    if pop <= 0:
        return 0
    return min(9, max(1, int(math.log2(max(1.0, pop) / 500.0)) + 1))


def load_turns(path: str) -> tuple[dict, dict[int, dict]]:
    header: dict = {}
    turns: dict[int, dict] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "world" not in rec:
                header = rec
                continue
            turns[rec["turn"]] = rec["world"]
    return header, turns


def quantize(x: float, y: float, w: float, h: float, gx: int, gy: int) -> tuple[int, int]:
    cx = min(gx - 1, max(0, int(x / w * gx)))
    cy = min(gy - 1, max(0, int(y / h * gy)))
    return cx, cy


def render(world: dict, header: dict, gx: int, gy: int, mode: str, color: bool = True) -> str:
    w, h = header.get("map_size", [1000, 1000])
    # cell -> entities
    towns: dict[tuple[int, int], list[dict]] = {}
    armies: dict[tuple[int, int], list[dict]] = {}
    for t in world.get("towns", []):
        towns.setdefault(quantize(t["x"], t["y"], w, h, gx, gy), []).append(t)
    for a in world.get("armies", []):
        armies.setdefault(quantize(a["x"], a["y"], w, h, gx, gy), []).append(a)

    def col(f: int, s: str) -> str:
        return f"{COLORS[f % len(COLORS)]}{s}{RESET}" if color else s

    lines: list[str] = []
    for cy in range(gy):
        row: list[str] = []
        for cx in range(gx):
            key = (cx, cy)
            ts = towns.get(key, [])
            aa = armies.get(key, [])
            facs = {t["faction"] for t in ts} | {a["faction"] for a in aa}
            if len(facs) >= 2:
                if mode == "all":
                    row.append(f"{BOLD_RED}**{RESET}" if color else "**")
                else:
                    row.append(f"{BOLD_RED}{CLASH}{RESET}" if color else CLASH)
            elif ts:
                t = max(ts, key=lambda t: t["population"])
                f = t["faction"]
                if mode == "all":
                    # two-char cells: faction + type/pop (town=F+bucket,
                    # capital=F+◆, buckets log-scale)
                    if t.get("is_capital"):
                        row.append(col(f, f"{f}{CAPITAL}"))
                    else:
                        row.append(col(f, f"{f}{pop_bucket(t['population'])}"))
                elif mode == "pop":
                    row.append(col(f, str(pop_bucket(t["population"]))))
                elif mode == "faction":
                    row.append(col(f, str(f)))
                elif t.get("is_capital"):
                    row.append(col(f, CAPITAL))
                else:
                    row.append(col(f, TOWN))
            elif aa:
                f0 = aa[0]["faction"]
                same = all(a["faction"] == f0 for a in aa)
                if mode == "all":
                    if not same:
                        row.append(f"{BOLD_RED}**{RESET}" if color else "**")
                    elif len(aa) >= 3:
                        n = min(9, len(aa))
                        row.append(col(f0, f"{f0}{n}"))  # faction + count
                    else:
                        row.append(col(f0, f"{f0}{ARMY}"))
                elif mode == "faction":
                    row.append(col(f0, str(f0)))
                elif mode == "pop":
                    row.append(f"{DIM}{ARMY}{RESET}" if color else ARMY)
                elif len(aa) >= 3:
                    # stack label overflows the cell (no padding — rows stay
                    # aligned, the xN just sticks out right, capped at edge)
                    row.append(col(f0, ARMY) + (f"x{len(aa)}" if cx + 4 < gx else ""))
                else:
                    row.append(col(f0, ARMY))
            else:
                if mode == "all":
                    row.append("  ")
                else:
                    row.append(f"{DIM}{EMPTY}{RESET}" if color else EMPTY)
        # strip padding artifacts, join
        lines.append("".join(row))
    return "\n".join(lines)


def footer(world: dict, header: dict, turn: int, color: bool = True, mode: str = "glyph") -> str:
    cost = header.get("army_cost", 1000)
    parts = [f"turn {turn}"]
    for f in sorted({t["faction"] for t in world.get("towns", [])} |
                    {a["faction"] for a in world.get("armies", [])}):
        pop = sum(t["population"] for t in world["towns"] if t["faction"] == f)
        nt = sum(1 for t in world["towns"] if t["faction"] == f)
        na = sum(1 for a in world["armies"] if a["faction"] == f)
        cap = next((t for t in world["towns"] if t["faction"] == f and t.get("is_capital")), None)
        label = f"F{f} pop={pop:.0f} towns={nt} armies={na}" + (f" cap={cap['population']:.0f}" if cap else "")
        parts.append(f"{COLORS[f % len(COLORS)]}{label}{RESET}" if color else label)
    if mode == "all":
        legend = (f"F+T cells: 0-4 faction + type (▲ army, F9 stack of 9+, "
                  f"F1-F9 town log-pop, F{CAPITAL} capital)  ** clash\n"
                  f"log-pop: doublings from 500 (1=0.5k 3=2k 5=8k 7=32k 9=128k+)")
    else:
        legend = f"{TOWN} town  {CAPITAL} capital  {ARMY} army(+xN stack)  {BOLD_RED if color else ''}*{RESET if color else ''} clash  {EMPTY} empty"
    return "  ".join(parts) + "\n" + legend


def _relations(world: dict) -> dict:
    """Precomputed spatial relations (no LLM math needed — the GeoJSON
    trap: models can't 'just look at coords and know'). Per town:
    nearest foe/own + distances. Per faction: centroid + neighbors.
    Game-agnostic shape (any positioned entities with faction/pop)."""
    towns = world.get("towns", [])
    rel: dict = {"towns": {}, "factions": {}}
    for t in towns:
        best_foe = None
        best_own = None
        for u in towns:
            if u["id"] == t["id"]:
                continue
            d = math.hypot(u["x"] - t["x"], u["y"] - t["y"])
            if u["faction"] != t["faction"]:
                if best_foe is None or d < best_foe[0]:
                    best_foe = (d, u)
            elif best_own is None or d < best_own[0]:
                best_own = (d, u)
        rel["towns"][str(t["id"])] = {
            "foe": {"id": best_foe[1]["id"], "faction": best_foe[1]["faction"],
                      "dist": round(best_foe[0]), "pop": round(best_foe[1]["population"]) } if best_foe else None,
            "own": {"id": best_own[1]["id"], "dist": round(best_own[0])} if best_own else None,
        }
    facs = sorted({t["faction"] for t in towns})
    for f in facs:
        own = [t for t in towns if t["faction"] == f]
        cx = sum(t["x"] for t in own) / len(own)
        cy = sum(t["y"] for t in own) / len(own)
        spread = max(math.hypot(t["x"] - cx, t["y"] - cy) for t in own)
        neigh: dict = {}
        for u in towns:
            if u["faction"] == f:
                continue
            d = math.hypot(u["x"] - cx, u["y"] - cy)
            g = str(u["faction"])
            if g not in neigh or d < neigh[g]:
                neigh[g] = round(d)
        rel["factions"][str(f)] = {"centroid": [round(cx), round(cy)],
                                    "spread": round(spread), "neighbors": neigh}
    return rel


def _views(world: dict) -> dict:
    """Subject-centric 8-ray first-hit per faction capital (raycast:
    benchmark winner 8/8 at 137 tokens — first-hit-only mimics human
    perception; empty directions mean open space). Rays hit towns then
    armies, nearest first per compass octant."""
    towns = world.get("towns", [])
    armies = world.get("armies", [])
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    views: dict = {}
    caps = [t for t in towns if t.get("is_capital")]
    for cap in caps:
        cx, cy = cap["x"], cap["y"]
        rays: dict = {}
        for i, name in enumerate(dirs):
            ang = math.pi / 2 - i * math.pi / 4  # N=up(+y?) use math berthed octants
            dx, dy = math.cos(ang), math.sin(ang)
            best = None
            for t in towns:
                if t["id"] == cap["id"]:
                    continue
                vx, vy = t["x"] - cx, t["y"] - cy
                dist = math.hypot(vx, vy)
                if dist < 1e-9:
                    continue
                # octant test: angle within 22.5 deg of ray
                dot = (vx * dx + vy * dy) / dist
                if dot > math.cos(math.pi / 8):
                    tag = f"{'C' if t.get('is_capital') else 'T'}{t['id']}f{t['faction']}"
                    if best is None or dist < best[0]:
                        best = (dist, f"{tag}@{round(dist)}")
            for a in armies:
                vx, vy = a["x"] - cx, a["y"] - cy
                dist = math.hypot(vx, vy)
                if dist < 1e-9:
                    continue
                dot = (vx * dx + vy * dy) / dist
                if dot > math.cos(math.pi / 8):
                    tag = f"A{a['id']}f{a['faction']}"
                    if best is None or dist < best[0]:
                        best = (dist, f"{tag}@{round(dist)}")
            rays[name] = best[1] if best else "-"
        views[str(cap["faction"])] = {"from": [round(cx), round(cy)], "rays": rays}
    return views


def as_json(world: dict, header: dict, turn: int, gx: int, gy: int, mode: str) -> str:
    """Augmented Cartesian JSON: sparse non-empty cells, each tagged with
    cartesian grid coords plus full entity data (kind, faction, pop,
    count, ids). Same quantization + collision priority as the grid."""
    w, h = header.get("map_size", [1000, 1000])
    towns: dict[tuple[int, int], list[dict]] = {}
    armies: dict[tuple[int, int], list[dict]] = {}
    for t in world.get("towns", []):
        towns.setdefault(quantize(t["x"], t["y"], w, h, gx, gy), []).append(t)
    for a in world.get("armies", []):
        armies.setdefault(quantize(a["x"], a["y"], w, h, gx, gy), []).append(a)
    cells = []
    for cy in range(gy):
        for cx in range(gx):
            key = (cx, cy)
            ts = towns.get(key, [])
            aa = armies.get(key, [])
            if not ts and not aa:
                continue
            facs = {t["faction"] for t in ts} | {a["faction"] for a in aa}
            cell: dict = {"x": cx, "y": cy}
            if len(facs) >= 2:
                cell.update(kind="clash", factions=sorted(facs),
                            town_ids=[t["id"] for t in ts],
                            army_ids=[a["id"] for a in aa])
            elif ts:
                t = max(ts, key=lambda t: t["population"])
                cell.update(kind="capital" if t.get("is_capital") else "town",
                            faction=t["faction"], pop=round(t["population"]),
                            town_ids=[t["id"] for t in ts],
                            bucket=pop_bucket(t["population"]))
            else:
                f0 = aa[0]["faction"]
                if not all(a["faction"] == f0 for a in aa):
                    cell.update(kind="clash", factions=sorted(facs),
                                army_ids=[a["id"] for a in aa])
                else:
                    cell.update(kind="stack" if len(aa) >= 3 else "army",
                                faction=f0, count=len(aa),
                                army_ids=[a["id"] for a in aa])
            cells.append(cell)
    facs_out = {}
    for f in sorted({t["faction"] for t in world.get("towns", [])} |
                     {a["faction"] for a in world.get("armies", [])}):
        cap = next((t for t in world["towns"] if t["faction"] == f and t.get("is_capital")), None)
        facs_out[str(f)] = {
            "pop": round(sum(t["population"] for t in world["towns"] if t["faction"] == f)),
            "towns": sum(1 for t in world["towns"] if t["faction"] == f),
            "armies": sum(1 for a in world["armies"] if a["faction"] == f),
            "capital_pop": round(cap["population"]) if cap else 0,
        }
    payload = {"turn": turn, "grid": {"w": gx, "h": gy, "map": [w, h]},
                       "mode": mode, "cells": cells, "factions": facs_out,
                       "relations": _relations(world), "views": _views(world)}
    if _COMPACT[0]:
        return json.dumps(payload, separators=(",", ":"))
    return json.dumps(payload, indent=1)


_COMPACT = [False]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ASCII viewer for jsonl recordings")
    ap.add_argument("recording")
    ap.add_argument("--turns", default="0", help="comma-separated turn numbers (default: last)")
    ap.add_argument("--size", default="50x50", help="GRID WxH (default 50x50, square like the map)")
    ap.add_argument("--mode", default="glyph", choices=["glyph", "pop", "faction", "all"])
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--compact", action="store_true", help="compact JSON (no indent, token discipline)")
    ap.add_argument("--format", default="ascii", choices=["ascii", "acjson", "text", "json"],
                    help="ascii: text grid (text kept as alias); acjson: Augmented Cartesian JSON (json kept as alias)")
    args = ap.parse_args(argv)
    _COMPACT[0] = args.compact
    if args.format in ("json", "acjson"):
        args.format = "acjson"
    else:
        args.format = "ascii"
    gx, gy = (int(v) for v in args.size.lower().split("x"))
    color = not args.no_color and sys.stdout.isatty()
    header, turns = load_turns(args.recording)
    if not turns:
        print("no turns found", file=sys.stderr)
        return 1
    if args.turns == "last":
        wanted = [max(turns)]
    else:
        wanted = [int(t) for t in args.turns.split(",")]
    for t in wanted:
        if t not in turns:
            near = min(turns, key=lambda k: abs(k - t))
            print(f"(turn {t} missing, showing {near})", file=sys.stderr)
            t = near
        if args.format == "acjson":
            print(as_json(turns[t], header, t, gx, gy, args.mode))
            continue
        print(render(turns[t], header, gx, gy, args.mode, color))
        print(footer(turns[t], header, t, color, args.mode))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
