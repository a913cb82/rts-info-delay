"""Cheap optimal-hierarchy test: matched shapes on a moderate region.

Why this design (see docs/GROWTH_REWORK.md "scale" notes):
- Whole-world per-capita rates are exact and comparable ACROSS shapes
  built on the same region (same edges). Never compare shapes built on
  different regions or with different urban fractions and call it scale.
- The economy is a pure function of the towns: one `_step_core` call
  resolves a whole turn (land -> services -> trade -> births ->
  migration) with no cross-turn state, so a single turn gives the
  exact instantaneous rate. No warmup, no windows.
- Towns on an independent lattice (spacing s_t, size T); villages fill
  the rest. ~600 towns, ~10 turns, ~1-2 s per config, ~1 MB matrices.

Usage: python benchmarks/hierarchy_opt.py [--rmax KM] [--turns N]
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

BASE_CFG = replace(GameConfig(), farm_decay_at_radius=0.9, farm_decay_shape=2.0,
                   market_scaling=1.15, market_premium=0.5)
CFG = BASE_CFG
S_V = 4.0
P_V = 300.0


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


def build(rmax, s_t, T, capital=0.0, s_r=0.0, R=0.0):
    vill = lattice(rmax, S_V)
    towns = []
    if s_t:
        towns = [(x + s_t / 2, y, T) for (x, y) in lattice(rmax, s_t)]
    if s_r:
        towns += [(x, y, R) for (x, y) in lattice(rmax, s_r)]
    if capital:
        towns.append((0.0, 0.0, capital))
    spec = [(x, y, P_V) for (x, y) in vill
            if all(math.hypot(x - tx, y - ty) > 0.6 * S_V for (tx, ty, _) in towns)]
    spec += [(x, y, p) for (x, y, p) in towns]
    return spec


def rate(spec, map_size=(2000, 2000), cfg=None):
    # Single turn: _step_core is a pure function of (towns, config),
    # so this is exact (no warmup, no window, no oscillation possible).
    cfg = cfg or CFG
    towns = [Town(id=k, faction=0, x=500 + x, y=500 + y, population=p)
             for k, (x, y, p) in enumerate(spec)]
    tot = sum(t.population for t in towns)
    n2, _ = eco._step_core(towns, list(map_size), cfg)
    return (sum(n2) - tot) / tot * 52.0 * 100.0, len(towns)


def clear():
    eco._geo_cache["key"] = None
    eco._geo_cache["geo"] = None
    eco._land_cache["key"] = None
    eco._land_cache["areas"] = None


def build_regional(rmax):
    # 2.4k towns every 32 km + 9.6k regionals every 96 km + villages elsewhere
    tpts = [(x + 16.0, y, 2400.0) for (x, y) in lattice(rmax, 32.0)]
    rpts = [(x, y, 9600.0) for (x, y) in lattice(rmax, 96.0)
            if all(math.hypot(x - tx, y - ty) > 2.0 for (tx, ty, _) in tpts)]
    taken = [(x, y) for (x, y, _) in tpts + rpts]
    vill = [(x, y, P_V) for (x, y) in lattice(rmax, S_V)
            if all(math.hypot(x - tx, y - ty) > 0.6 * S_V for (tx, ty) in taken)]
    return vill + tpts + rpts


SHAPES = [
    ("flat", 0.0, 0.0, 0.0),
    ("s16/T600", 16.0, 600.0, 0.0),
    ("s32/T2400", 32.0, 2400.0, 0.0),
    ("s32/T2400+cap20k", 32.0, 2400.0, 20000.0),
    ("s64/T2400", 64.0, 2400.0, 0.0),
    ("s64/T9600", 64.0, 9600.0, 0.0),
    ("+regional 9.6k", 0.0, 0.0, 0.0),
]


def main(rmax=50.0, gamma=None, premium=None):
    cfg = BASE_CFG
    if gamma is not None or premium is not None:
        cfg = replace(BASE_CFG,
                      market_scaling=BASE_CFG.market_scaling if gamma is None else gamma,
                      market_premium=BASE_CFG.market_premium if premium is None else premium)
    print(f"{'shape':>18} {'N':>5} {'urban%':>7} {'rate':>9}")
    rows = []
    for label, s_t, T, cap in SHAPES:
        t0 = time.perf_counter()
        if label.startswith("+regional"):
            spec = build_regional(rmax)
        else:
            spec = build(rmax, s_t, T, cap)
        tot = sum(p for (_, _, p) in spec)
        urb = 100.0 * sum(p for (_, _, p) in spec if p > P_V) / tot
        clear()
        g, n = rate(spec, cfg=cfg)
        dt = time.perf_counter() - t0
        rows.append((g, label, n, urb, dt))
        print(f"{label:>18} {n:5d} {urb:7.1f} {g:+9.4f}  ({dt:.1f}s)")
    best = max(rows)
    flat = [r for r in rows if r[1] == "flat"][0]
    print(f"best: {best[1]} {best[0]:+.4f} vs flat {flat[0]:+.4f} "
          f"(gap {best[0] - flat[0]:+.4f})")
    assert best[0] > flat[0], "hierarchy should beat flat under gamma=1.15"
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rmax", type=float, default=50.0)
    ap.add_argument("--gamma", type=float, default=None)
    ap.add_argument("--premium", type=float, default=None)
    sys.exit(main(**vars(ap.parse_args())))
