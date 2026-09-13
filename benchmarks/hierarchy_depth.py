"""Does deeper hierarchy pay at FIXED urban budget? (1M region)

Reallocates the same urban population across 2/3/4 tiers and compares
windowed per-capita rates. This isolates depth (concentration) from
dilution (adding urban on top). Answers which parameter makes depth pay:
market_scaling (gamma) — superlinear service output is the necessary
condition; market_premium only scales the effect.

Usage: python benchmarks/hierarchy_depth.py [--rmax KM] [--gamma G]
       [--premium P] [--urban U]
"""
import math
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import engine.economy as eco
from engine.config import GameConfig
from engine.world import Town

BASE = replace(GameConfig(), farm_decay_at_radius=0.9, farm_decay_shape=2.0)
S_V = 4.0
P_V = 500.0


def lattice(rmax, s, ox=0.0, oy=0.0):
    pts = []
    jm = int(rmax / (s * math.sqrt(3) / 2)) + 2
    for j in range(-jm, jm + 1):
        y = j * s * math.sqrt(3) / 2 + oy
        off = s / 2 if j % 2 else 0.0
        im = int((rmax - off) / s) + 2
        for i in range(-im, im + 1):
            x = off + i * s + ox
            if x * x + y * y <= rmax * rmax + 1e-9:
                pts.append((x, y))
    return pts


def fps(cands, n, taken):
    chosen, pool = [], [p for p in cands]
    while len(chosen) < n and pool:
        if not taken and not chosen:
            best = min(pool, key=lambda p: math.hypot(*p))
        else:
            best = max(pool, key=lambda p: min(
                math.hypot(p[0] - q[0], p[1] - q[1]) for q in (taken + chosen)))
        chosen.append(best)
        pool.remove(best)
    return chosen


def build_budget(rmax, tier_shapes):
    """tier_shapes: [(size, count), ...]; villages fill the rest at 500."""
    taken, spec = [], []
    for T, n in tier_shapes:
        cands = [p for p in lattice(rmax, S_V)
                 if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 2.0 for q in taken)]
        pts = fps(cands, n, taken)
        for (x, y) in pts:
            taken.append((x, y))
            spec.append((x, y, T))
    vill = [(x, y, P_V) for (x, y) in lattice(rmax, S_V)
            if all(math.hypot(x - tx, y - ty) > 0.6 * S_V for (tx, ty) in taken)]
    return vill + spec


def rate(spec, map_size=(2000, 2000)):
    # Single turn is exact: _step_core carries no state across turns.
    towns = [Town(id=k, faction=0, x=500 + x, y=500 + y, population=p)
             for k, (x, y, p) in enumerate(spec)]
    tot = sum(t.population for t in towns)
    n2, _ = eco._step_core(towns, list(map_size), CFG)
    return (sum(n2) - tot) / tot * 52.0 * 100.0, len(towns)


def clear():
    eco._geo_cache["key"] = None
    eco._geo_cache["geo"] = None
    eco._land_cache["key"] = None
    eco._land_cache["areas"] = None


CFG = BASE_CFG = BASE


def main(rmax=118.0, gamma=1.15, premium=0.5):
    global CFG
    CFG = replace(BASE, market_scaling=gamma, market_premium=premium)
    print(f"{'tiers':>28} {'N':>5} {'urban%':>7} {'rate':>9}")
    # ~7.7% urban budget on ~1.68M: 54x2.4k | 40x2.4k+4x8.5k | 40x2.4k+3x8k+1x10k
    for label, tiers in [("2lvl: 54x2.4k", [(2400.0, 54)]),
                         ("3lvl: 40x2.4k+4x8.5k", [(2400.0, 40), (8500.0, 4)]),
                         ("4lvl: 40x2.4k+3x8k+1x10k",
                          [(2400.0, 40), (8000.0, 3), (10000.0, 1)])]:
        t0 = time.perf_counter()
        spec = build_budget(rmax, tiers)
        tot = sum(p for (_, _, p) in spec)
        urb = 100.0 * sum(p for (_, _, p) in spec if p > P_V) / tot
        clear()
        g, n = rate(spec)
        print(f"{label:>28} {n:5d} {urb:7.1f} {g:+9.4f}  ({time.perf_counter() - t0:.1f}s)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rmax", type=float, default=118.0)
    ap.add_argument("--gamma", type=float, default=1.15)
    ap.add_argument("--premium", type=float, default=0.5)
    a = ap.parse_args()
    main(rmax=a.rmax, gamma=a.gamma, premium=a.premium)
