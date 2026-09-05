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
    cmap: dict[int, str] = {}
    if mode == "cluster":
        rel = _relations(world)
        for f in rel["factions"].values():
            for i, c in enumerate(f["clusters"]):
                for mid in c["members"]:
                    cmap[mid] = chr(ord("A") + i) if i < 26 else "?"
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
                if mode == "cluster":
                    lab = cmap.get(t["id"])
                    if t.get("is_capital"):
                        row.append(col(f, f"{f}{CAPITAL}"))
                    else:
                        row.append(col(f, f"{f}{lab}") if lab else col(f, TOWN))
                elif mode == "all":
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


def _compass(dx: float, dy: float) -> str:
    """8-wind bearing, screen convention (matches the ASCII map: +x East,
    +y South since row 0 is the top)."""
    import math as _math
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return "here"
    ang = _math.degrees(_math.atan2(dx, -dy))  # 0=N, clockwise
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int((ang + 22.5) % 360 // 45)]


def _cluster_of(world: dict, tid: int) -> str | None:
    """Cluster letter (A=biggest) for a town id, via _relations."""
    rel = _relations(world)
    for f in rel["factions"].values():
        for i, c in enumerate(f["clusters"]):
            if tid in c["members"]:
                return chr(ord("A") + i) if i < 26 else "?"
    return None


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
                      "dist": round(best_foe[0]), "pop": round(best_foe[1]["population"]),
                      "dir": _compass(best_foe[1]["x"] - t["x"], best_foe[1]["y"] - t["y"])} if best_foe else None,
            "own": {"id": best_own[1]["id"], "dist": round(best_own[0]),
                      "dir": _compass(best_own[1]["x"] - t["x"], best_own[1]["y"] - t["y"])} if best_own else None,
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
            if g not in neigh or d < neigh[g]["dist"]:
                neigh[g] = {"dist": round(d), "dir": _compass(u["x"] - cx, u["y"] - cy)}
        cap = next((t for t in own if t.get("is_capital")), None)
        cap_off = None
        if cap:
            cap_off = {"dist": round(math.hypot(cap["x"] - cx, cap["y"] - cy)),
                       "dir": _compass(cap["x"] - cx, cap["y"] - cy)}
        # clusters: LEADER (greedy ball-covering, pop-desc seeds, R=150km).
        # Beats single-linkage (chains via stepping-stones into snakes),
        # DBSCAN (same chaining via density-reachability), k-means (needs
        # k upfront + random init breaks determinism). Radius bounded by R
        # guaranteed; loners form singleton clusters (frontier outposts stay
        # visible, not noise). Deterministic: pop-desc, id tiebreak.
        clusters: list = []
        rem = sorted(own, key=lambda t: (-t["population"], t["id"]))
        while rem:
            seed = rem.pop(0)
            members = [seed]
            for u in list(rem):
                if math.hypot(u["x"] - seed["x"], u["y"] - seed["y"]) <= 150:
                    members.append(u)
                    rem.remove(u)
            mx = sum(m["x"] for m in members) / len(members)
            my = sum(m["y"] for m in members) / len(members)
            rad = max(round(math.hypot(m["x"] - mx, m["y"] - my)) for m in members)
            clusters.append({"n": len(members),
                             "pop": round(sum(m["population"] for m in members)),
                             "centroid": [round(mx), round(my)],
                             "radius": rad,
                             "members": [m["id"] for m in members]})
        clusters.sort(key=lambda c: -c["pop"])
        for i, c in enumerate(clusters):
            # label + capital-relative bearing ("C0, 5 towns NW of capital")
            c["label"] = f"C{i}"
            if cap:
                c["from_capital"] = {"dist": round(math.hypot(c["centroid"][0] - cap["x"], c["centroid"][1] - cap["y"])),
                                       "dir": _compass(c["centroid"][0] - cap["x"], c["centroid"][1] - cap["y"])}
        rel["factions"][str(f)] = {"centroid": [round(cx), round(cy)],
                                    "spread": round(spread), "neighbors": neigh,
                                    "capital_offset": cap_off, "clusters": clusters}
    # nearest-foe-cluster per cluster ("which enemy blob threatens mine")
    allc = [(f, c) for f in rel["factions"] for c in rel["factions"][f]["clusters"]]
    for f, c in allc:
        best = None
        for g, o in allc:
            if g == f:
                continue
            d = math.hypot(o["centroid"][0] - c["centroid"][0], o["centroid"][1] - c["centroid"][1])
            if best is None or d < best[0]:
                best = (d, g, o)
        if best:
            d, g, o = best
            c["foe"] = {"faction": int(g), "cluster": o["label"], "dist": round(d),
                          "dir": _compass(o["centroid"][0] - c["centroid"][0], o["centroid"][1] - c["centroid"][1])}
    return rel


def _views(world: dict) -> dict:
    """Subject-centric 8-ray first-hit per faction capital (raycast:
    benchmark winner 8/8 at 137 tokens — first-hit-only mimics human
    perception; empty directions mean open space). Rays hit towns then
    armies, nearest first per compass octant."""
    towns = world.get("towns", [])
    armies = world.get("armies", [])
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    # screen convention (matches map + _compass): N=(0,-1), clockwise
    vecs = {"N": (0.0, -1.0), "NE": (0.7071, -0.7071), "E": (1.0, 0.0), "SE": (0.7071, 0.7071), "S": (0.0, 1.0), "SW": (-0.7071, 0.7071), "W": (-1.0, 0.0), "NW": (-0.7071, -0.7071)}
    views: dict = {}
    caps = [t for t in towns if t.get("is_capital")]
    for cap in caps:
        cx, cy = cap["x"], cap["y"]
        rays: dict = {}
        for i, name in enumerate(dirs):
            dx, dy = vecs[name]
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


def _score(world: dict, cost: float) -> dict:
    out: dict = {}
    for f in {t["faction"] for t in world.get("towns", [])} | {a["faction"] for a in world.get("armies", [])}:
        pop = sum(t["population"] for t in world["towns"] if t["faction"] == f)
        na = sum(1 for a in world["armies"] if a["faction"] == f)
        out[str(f)] = round(pop + na * cost)
    return out


def as_json(world: dict, header: dict, turn: int, gx: int, gy: int, mode: str, turns: dict | None = None, deltas: list | None = None) -> str:
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
    if turns is not None and deltas:
        # score deltas at symmetric offsets (past+future; null off-record)
        cost = header.get("army_cost", 1000)
        now = _score(world, cost)
        dd: dict = {}
        for d in deltas:
            for key, tt in ((f"-{d}", turn - d), (f"+{d}", turn + d)):
                if tt in turns:
                    then = _score(turns[tt], cost)
                    # then-minus-now: past negative (was lower), future
                    # positive (will be higher) — reads as change-from-here
                    dd[key] = {f: round(then.get(f, 0) - now.get(f, 0))
                               for f in set(now) | set(then)}
                else:
                    dd[key] = None
        payload["deltas"] = dd
    if _COMPACT[0]:
        return json.dumps(payload, separators=(",", ":"))
    return json.dumps(payload, indent=1)


_COMPACT = [False]


def autopsy(path: str, t0: int, t1: int) -> str:
    """Death ledger over [t0, t1]: who fed whom where (onesie detector).
    Kills attribute to the nearest town (defender site); >= 3 losses by
    one faction at one town in-window raises a ONESIES alert."""
    import math as _math
    towns: list = []
    losses: dict = {}  # (loser, town_id) -> [turns]
    tkills: dict = {}  # town_id -> owner faction (latest)
    takes: list = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "world" not in rec:
                continue
            t = rec.get("turn", 0)
            w = rec["world"]
            if t <= t1:
                towns = w.get("towns", towns)
                for x in towns:
                    tkills[x["id"]] = x["faction"]
            if not (t0 <= t <= t1):
                continue
            for e in rec.get("events", []):
                k = e.get("kind")
                if k == "battle":
                    fac = {c["id"]: c["faction"] for c in e.get("combatants", [])}
                    for kid in e.get("killed", []):
                        lf = fac.get(kid)
                        if lf is None:
                            continue
                        site = min(towns, key=lambda u: _math.hypot(u["x"] - e["x"], u["y"] - e["y"]),
                                   default=None) if towns else None
                        tid = site["id"] if site else -1
                        losses.setdefault((lf, tid), []).append(t)
                elif k in ("town_capture", "town_death"):
                    takes.append((t, k, e))
    lines = [f"autopsy {t0}-{t1}:"]
    for (lf, tid), ts in sorted(losses.items(), key=lambda kv: -len(kv[1])):
        owner = tkills.get(tid, "?")
        flag = "  <-- ONESIES" if len(ts) >= 3 else ""
        lines.append(f"  F{lf} lost {len(ts)} @ town {tid} (F{owner}) t{min(ts)}-{max(ts)}{flag}")
    for t, k, e in takes:
        lines.append(f"  t{t} {k}: {e}")
    if len(lines) == 1:
        lines.append("  (no deaths)")
    return "\n".join(lines)


def report(path: str) -> str:
    """Full-game brief (loop step 1 in one command): activity, stagnation,
    onesies, punishable thin towns, verdict lines. Rederives viewer
    feedback without watching 10000 turns."""
    import math as _math
    prints: dict = {}
    samples: dict = {}  # turn -> (towns, armies) every 250t
    founds: dict = {}
    caps: dict = {}
    battled: dict = {}  # army id -> battles joined
    track: dict = {}  # army id -> [faction, lastx, lasty, static_since, march_km]
    static_max: dict = {}  # army id -> longest static run (turns)
    towns: list = []
    owners: dict = {}  # town id -> last-known faction (dead towns vanish)
    final: dict = {}
    losses: dict = {}
    maxt = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "world" not in rec:
                continue
            t = rec.get("turn", 0)
            maxt = max(maxt, t)
            w = rec["world"]
            towns = w.get("towns", towns)
            final = w
            for x in towns:
                owners[x["id"]] = x["faction"]
            if t % 250 == 0:
                # sparse snapshots for opportunity windows (towns+armies)
                samples[t] = ([dict(u) for u in towns],
                              [dict(a) for a in w.get("armies", [])])
            seen = set()
            for a in w.get("armies", []):
                aid, fac, x, y = a["id"], a["faction"], round(a["x"]), round(a["y"])
                seen.add(aid)
                if aid not in track:
                    track[aid] = [fac, x, y, t, 0.0]
                    static_max[aid] = 0
                else:
                    tr = track[aid]
                    tr[0] = fac
                    tr[4] += _math.hypot(x - tr[1], y - tr[2])
                    if x == tr[1] and y == tr[2]:
                        static_max[aid] = max(static_max[aid], t - tr[3])
                    else:
                        tr[1], tr[2], tr[3] = x, y, t
            for e in rec.get("events", []):
                k = e.get("kind")
                if k == "army_spawn":
                    prints[e.get("faction", "?")] = prints.get(e.get("faction", "?"), 0) + 1
                elif k == "town_spawn":
                    founds[e.get("faction", "?")] = founds.get(e.get("faction", "?"), 0) + 1
                elif k == "town_capture":
                    # capturer = new owner of the town (event carries town id)
                    caps[e.get("new_faction", e.get("faction", "?"))] = caps.get(e.get("new_faction", e.get("faction", "?")), 0) + 1
                elif k == "battle":
                    fac = {c["id"]: c["faction"] for c in e.get("combatants", [])}
                    for c in e.get("combatants", []):
                        battled[c["id"]] = battled.get(c["id"], 0) + 1
                    for kid in e.get("killed", []):
                        lf = fac.get(kid)
                        if lf is None:
                            continue
                        site = min(towns, key=lambda u: _math.hypot(u["x"] - e["x"], u["y"] - e["y"]),
                                   default=None) if towns else None
                        tid = site["id"] if site else -1
                        losses.setdefault((lf, tid), []).append(t)
    feas = {t["faction"] for t in towns} | set(prints) | set(founds)
    lines = [f"report {path.split('/')[-1]} ({maxt} turns):"]
    lines.append("activity (prints/foundings/captures):")
    for f in sorted(feas, key=str):
        mates = [aid for aid, tr in track.items() if tr[0] == f]
        idle = sum(1 for aid in mates if static_max.get(aid, 0) > 500 and battled.get(aid, 0) == 0)
        march = round(sum(tr[4] for aid in mates for tr in [track[aid]]))
        # Churn rate (r85: mobility vs waste): km per army per 100t
        # (march speed 50/t = 5000/100t). Sustained >100 with zero
        # takes = shuttling; war mobility runs 100-500 with takes.
        churn = round(march / max(1, len(mates)) / max(1, maxt) * 100, 1) if mates else 0
        lines.append(f"  F{f}: {prints.get(f, 0)} prints / {founds.get(f, 0)} foundings / "
                     f"{caps.get(f, 0)} captures / {idle} idle armies (>500t static, 0 battles) / {march}km marched / churn {churn}")
    lines.append("stagnation (static >500t, 0 battles):")
    stagn = [(aid, static_max[aid], track[aid]) for aid in track
             if static_max.get(aid, 0) > 500 and battled.get(aid, 0) == 0]
    stagn.sort(key=lambda r: -r[1])
    for aid, run, tr in stagn[:12]:
        near = min(towns, key=lambda u: _math.hypot(u["x"] - tr[1], u["y"] - tr[2]),
                   default=None) if towns else None
        at = f" @ town {near['id']} (F{near['faction']})" if near and _math.hypot(near["x"] - tr[1], near["y"] - tr[2]) < 30 else f" @ void ({tr[1]},{tr[2]})"
        lines.append(f"  army {aid} (F{tr[0]}) static {run}t{at}")
    if not stagn:
        lines.append("  (none)")
    lines.append("onesies (>=3 losses, one faction, one town):")
    any1 = False
    for (lf, tid), ts in sorted(losses.items(), key=lambda kv: -len(kv[1])):
        if len(ts) < 3:
            continue
        owner = owners.get(tid, "?")
        lines.append(f"  F{lf} lost {len(ts)} @ town {tid} (F{owner}) t{min(ts)}-{max(ts)}")
        any1 = True
    if not any1:
        lines.append("  (none)")
    lines.append("punishable (final state: foe town, 0 garrison, idle foe stack <300km):")
    garr: dict = {}
    for a in final.get("armies", []):
        for u in towns:
            if u["faction"] == a["faction"] and _math.hypot(u["x"] - a["x"], u["y"] - a["y"]) <= 15:
                garr[u["id"]] = garr.get(u["id"], 0) + 1
                break
    idle_stacks = [(a["id"], a["faction"], a["x"], a["y"]) for a in final.get("armies", [])
                   if static_max.get(a["id"], 0) > 500]
    any2 = False
    for u in towns:
        if garr.get(u["id"], 0) > 0:
            continue
        for aid, fac, x, y in idle_stacks:
            if fac == u["faction"]:
                continue
            d = _math.hypot(u["x"] - x, u["y"] - y)
            if d < 300:
                lines.append(f"  town {u['id']} (F{u['faction']}, pop {round(u['population'])}) empty, "
                             f"idle F{fac} stack {round(d)}km away (army {aid})")
                any2 = True
                break
    if not any2:
        lines.append("  (none)")
    lines.append("opportunities (empty town + foe stack <300km, over time):")
    # window per (town, foe faction): consecutive 250t samples with the
    # town garrison-free and a 3+ foe stack in range.
    open_w: dict = {}
    shut: list = []
    for t in sorted(samples):
        stowns, sarmies = samples[t]
        garr: dict = {}
        for a in sarmies:
            for u in stowns:
                if u["faction"] == a["faction"] and _math.hypot(u["x"] - a["x"], u["y"] - a["y"]) <= 15:
                    garr[u["id"]] = garr.get(u["id"], 0) + 1
                    break
        stacks: dict = {}  # (faction, cell) -> count
        for a in sarmies:
            stacks.setdefault((a["faction"], round(a["x"] / 30), round(a["y"] / 30)), []).append(a["id"])
        big = {k: v for k, v in stacks.items() if len(v) >= 3}
        hit: set = set()
        for u in stowns:
            if garr.get(u["id"], 0) > 0:
                continue
            for (fac, _cx, _cy), aids in big.items():
                if fac == u["faction"]:
                    continue
                a0 = next(a for a in sarmies if a["id"] == aids[0])
                d = _math.hypot(u["x"] - a0["x"], u["y"] - a0["y"])
                if d < 300:
                    hit.add((u["id"], fac))
        for key in list(open_w):
            if key not in hit:
                shut.append((key, open_w.pop(key)))
        for key in hit:
            if key not in open_w:
                u = next(x for x in stowns if x["id"] == key[0])
                open_w[key] = [t, t, round(u["population"]), u["faction"]]
            else:
                open_w[key][1] = t
                u = next((x for x in stowns if x["id"] == key[0]), None)
                if u is not None:
                    open_w[key][2] = max(open_w[key][2], round(u["population"]))
    for key, w_ in open_w.items():
        shut.append((key, w_))
    shut.sort(key=lambda r: -(r[1][1] - r[1][0]))
    any3 = False
    for (tid, fac), (t0, t1, peak, owner) in shut[:15]:
        if t1 - t0 < 250:
            continue
        lines.append(f"  town {tid} (F{owner}, peak {peak}) empty {t1 - t0}t (t{t0}-{t1}) vs idle F{fac} stack")
        any3 = True
    if not any3:
        lines.append("  (none sustained)")
    return "\n".join(lines)


def lead(path: str) -> str:
    """Score timeline + lead flips (loop step 1 for comebacks): pop /
    towns / armies per faction per millennium, lead column, FLIP lines
    naming who took the lead and when."""
    header, turns = load_turns(path)
    if not turns:
        return "no turns found"
    out = [f"lead {path.split('/')[-1]}:"]
    prev = None
    for m in range(0, 10001, 1000):
        t = min(turns, key=lambda k: abs(k - m))
        w = turns[t]
        pops = {}
        for f in (0, 1, 2, 3, 4):
            tw = [x for x in w["towns"] if x["faction"] == f]
            na = sum(1 for x in w["armies"] if x["faction"] == f)
            pops[f] = (len(tw), round(sum(x["population"] for x in tw)), na)
        cur = max(range(5), key=lambda f: pops[f][1])
        cells = " ".join(f"F{f}:{pops[f][0]}t/{pops[f][1]}/{pops[f][2]}a" for f in range(5))
        tag = ""
        if prev is not None and cur != prev:
            tag = f"  <-- FLIP F{prev}->F{cur}"
        out.append(f"t{t}: {cells} LEAD=F{cur}{tag}")
        prev = cur
    return "\n".join(out)


def flip(path: str, faction: int, t0: int, t1: int) -> str:
    """Events around a flip window for faction F's collapse (or rise):
    town takes/deaths, battles, plus F's prints in-window (did it react?)
    and F's army count arc. Answers 'what did they do wrong/right?'."""
    header, turns = load_turns(path)
    if not turns:
        return "no turns found"
    evmap: dict = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if "world" in r:
                evmap[r.get("turn", 0)] = r.get("events", [])
    out = [f"flip F{faction} {t0}-{t1}:"]
    for t in sorted(turns):
        if not (t0 <= t <= t1):
            continue
        w = turns[t]
        evs = evmap.get(t, [])
        nf = sum(1 for x in w["towns"] if x["faction"] == faction)
        na = sum(1 for x in w["armies"] if x["faction"] == faction)
        for e in evs:
            k = e.get("kind")
            if k in ("town_capture", "town_death") and e.get("old_faction", e.get("faction")) == faction:
                out.append(f"  t{t} LOST {k} town{e.get('id')} ->F{e.get('new_faction', '')} pop={round(e.get('population', 0))} @({e.get('x', 0):.0f},{e.get('y', 0):.0f})")
            elif k == "town_capture" and e.get("new_faction") == faction:
                out.append(f"  t{t} TOOK town{e.get('id')} from F{e.get('old_faction')} pop={round(e.get('population', 0))}")
            elif k == "battle":
                mine = [c for c in e.get("combatants", []) if c["faction"] == faction]
                if mine:
                    foes = ",".join(f"F{c['faction']}:{c['id']}" for c in e.get("combatants", []) if c["faction"] != faction)
                    out.append(f"  t{t} battle {len(mine)}v({foes}) killed={e.get('killed')} @({e.get('x', 0):.0f},{e.get('y', 0):.0f})")
        if t % 250 == 0:
            out.append(f"  [t{t} F{faction}: {nf}t/{na}a]")
    return "\n".join(out)


def fog(path: str, faction: int, turn: int) -> str:
    """What faction F had observed by turn T (bot-view replay): per town
    last-seen pop/faction/alive + staleness + GHOSTS (dead-unseen) +
    MISSED (alive-unseen). Answers 'what did the bot see?' without
    guessing from truth."""
    import math as _math
    los = 150.0
    seen: dict = {}  # town id -> [turn, pop, faction, alive]
    aseens: dict = {}  # foe army id -> [turn, x, y]
    lastpos: dict = {}  # town id -> (x, y) last truth position
    truth_towns: list = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "world" not in rec:
                los = float(rec.get("line_of_sight", los) or los)
                continue
            t = rec.get("turn", 0)
            if t > turn:
                break
            w = rec["world"]
            truth_towns = w.get("towns", truth_towns)
            for x in truth_towns:
                lastpos[x["id"]] = (x["x"], x["y"])
            obs = [(x["x"], x["y"]) for x in w.get("towns", []) if x["faction"] == faction]
            obs += [(a["x"], a["y"]) for a in w.get("armies", []) if a["faction"] == faction]
            if not obs:
                continue
            for u in w.get("towns", []):
                if min(_math.hypot(u["x"] - ox, u["y"] - oy) for ox, oy in obs) <= los:
                    seen[u["id"]] = [t, round(u["population"]), u["faction"], True]
            live = {x["id"] for x in w.get("towns", [])}
            for tid, (st, sp, sf, sa) in list(seen.items()):
                if tid not in live and sa and tid in lastpos:
                    # vanished: death observed iff eyes on the site now
                    tx, ty = lastpos[tid]
                    if min(_math.hypot(tx - ox, ty - oy) for ox, oy in obs) <= los:
                        seen[tid] = [t, 0, sf, False]
            for a in w.get("armies", []):
                if a["faction"] == faction:
                    continue
                if min((_math.hypot(a["x"] - ox, a["y"] - oy) for ox, oy in obs), default=1e18) <= los:
                    aseens[a["id"]] = [t, round(a["x"]), round(a["y"])]
    lines = [f"fog F{faction} @ t{turn} (LOS {los:.0f}):"]
    lines.append("towns observed:")
    for tid, (st, sp, sf, sa) in sorted(seen.items()):
        age = turn - st
        live_now = any(x["id"] == tid for x in truth_towns)
        tag = ""
        if not sa and live_now:
            tag = "  <-- GHOST? (seen dead, alive now: refounded unseen)"
        elif sa and not live_now:
            tag = "  <-- GHOST (dead unseen: bot still sees it alive!)"
        elif age > 150:
            tag = f"  <-- stale ({age}t)"
        lines.append(f"  town {tid}: F{sf} pop {sp} seen t{st}{' DEAD' if not sa else ''}{tag}")
    lines.append("truth towns never observed:")
    any_m = False
    for u in truth_towns:
        if u["id"] not in seen:
            lines.append(f"  town {u['id']}: F{u['faction']} pop {round(u['population'])} @ ({round(u['x'])},{round(u['y'])})")
            any_m = True
    if not any_m:
        lines.append("  (none)")
    lines.append("foe armies last seen:")
    if aseens:
        for aid, (st, x, y) in sorted(aseens.items()):
            lines.append(f"  army {aid}: t{st} @ ({x},{y}) ({turn - st}t ago)")
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ASCII viewer for jsonl recordings")
    ap.add_argument("recording")
    ap.add_argument("--turns", default="0", help="comma-separated turn numbers (default: last)")
    ap.add_argument("--size", default="50x50", help="GRID WxH (default 50x50, square like the map)")
    ap.add_argument("--mode", default="glyph", choices=["glyph", "pop", "faction", "all", "cluster"])
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--compact", action="store_true", help="compact JSON (no indent, token discipline)")
    ap.add_argument("--deltas", default="100,10,1", help="score-delta offsets (symmetric past+future, comma-separated)")
    ap.add_argument("--format", default="ascii", choices=["ascii", "acjson", "text", "json", "autopsy", "report", "fog", "lead", "flip"],
                    help="ascii: text grid (text kept as alias); acjson: Augmented Cartesian JSON (json kept as alias); autopsy: death ledger over --window; report: full-game brief; fog: what a faction observed (--faction, --turn); lead: score timeline + lead flips; flip: events around a flip window (--window A-B, --faction F context)")
    ap.add_argument("--faction", default="0", help="fog format: faction to observe as")
    ap.add_argument("--window", default="", help="autopsy window TURNS, e.g. 7800-8000 (default: last 1000)")
    args = ap.parse_args(argv)
    _COMPACT[0] = args.compact
    if args.format in ("json", "acjson"):
        args.format = "acjson"
    elif args.format not in ("autopsy", "report", "fog", "lead", "flip"):
        args.format = "ascii"
    if args.format == "fog":
        t = int(args.turns.split(",")[0]) if args.turns != "last" else -1
        if t < 0:
            maxt = 0
            with open(args.recording) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if "world" in r:
                            maxt = max(maxt, r.get("turn", 0))
                    except Exception:
                        pass
            t = maxt
        print(fog(args.recording, int(args.faction), t))
        return 0
    if args.format == "report":
        print(report(args.recording))
        return 0
    if args.format == "lead":
        print(lead(args.recording))
        return 0
    if args.format == "flip":
        if args.window and "-" in args.window:
            t0, t1 = (int(v) for v in args.window.split("-", 1))
        else:
            t1, t0 = 8000, 7000
        print(flip(args.recording, int(args.faction), t0, t1))
        return 0
    if args.format == "autopsy":
        if args.window and "-" in args.window:
            t0, t1 = (int(v) for v in args.window.split("-", 1))
        else:
            # default: last 1000 turns
            maxt = 0
            with open(args.recording) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if "world" in r:
                            maxt = max(maxt, r.get("turn", 0))
                    except Exception:
                        pass
            t1, t0 = maxt, max(0, maxt - 1000)
        print(autopsy(args.recording, t0, t1))
        return 0
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
            print(as_json(turns[t], header, t, gx, gy, args.mode, turns,
                          [int(x) for x in args.deltas.split(",") if x.strip()]))
            continue
        print(render(turns[t], header, gx, gy, args.mode, color))
        print(footer(turns[t], header, t, color, args.mode))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
