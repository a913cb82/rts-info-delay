"""Cheap optimal-hierarchy test: matched shapes on a moderate region.

Why this design (see docs/GROWTH_REWORK.md "scale" notes):
- Whole-world per-capita rates are exact and comparable ACROSS shapes
  built on the same region (same edges). Never compare shapes built on
  different regions or with different urban fractions and call it scale.
- One `_step_core` call resolves a whole turn (land -> services ->
  improvement -> trade -> births -> migration). Towns carry one state
  (last_improvement, cold start 0), so a single turn gives the exact
  cold-start (plain pairwise) rate; settled rates need ~3 warmup turns
  (see hierarchy_compare.py). No windows.
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
                   market_scaling=1.3, max_improvement=0.5, melt_per_km=0.005)
# Closest-to-reality calibration (see docs/GROWTH_REWORK.md): strong
# agglomeration, high headroom, cheap hauling. Upper tiers only earn
# their keep with all three at once.
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


def build(rmax, s_t, T, s_r=0.0, R=0.0, footprint=True):
    fr = 0.6 * S_V if footprint else 1e-9  # town occupies a site vs exact overlap only
    vill = lattice(rmax, S_V)
    towns = []
    if s_t:
        towns = [(x + s_t / 2, y, T) for (x, y) in lattice(rmax, s_t)]
    if s_r:
        towns += [(x, y, R) for (x, y) in lattice(rmax, s_r)]
    spec = [(x, y, P_V) for (x, y) in vill
            if all(math.hypot(x - tx, y - ty) > fr for (tx, ty, _) in towns)]
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
    eco._geo_cache["grid"] = None
    eco._land_cache["key"] = None
    eco._land_cache["areas"] = None


def build_goal(rmax, footprint=True):
    # 3-tier GOAL: villages 300@4km + bourgs 1000@16km + chef 8000 center.
    # The chef is just a site (no special logic); its 8km clearance from
    # the bourg lattice holds by construction, villages clear around both.
    fr = 0.6 * S_V if footprint else 1e-9
    bpts = [(x + 8.0, y, 1000.0) for (x, y) in lattice(rmax, 16.0)]
    cpts = [(0.0, 0.0, 8000.0)]
    taken = [(x, y) for (x, y, _) in bpts + cpts]
    vill = [(x, y, P_V) for (x, y) in lattice(rmax, S_V)
            if all(math.hypot(x - tx, y - ty) > fr for (tx, ty) in taken)]
    return vill + bpts + cpts


def build_goal_lean(rmax, footprint=True):
    # Lean 3-tier: villages 300@4km + bourgs 600@18km + chef 5000 center
    # (~11% urban — the reality-share version of the GOAL stack).
    fr = 0.6 * S_V if footprint else 1e-9
    bpts = [(x + 9.0, y, 600.0) for (x, y) in lattice(rmax, 18.0)]
    cpts = [(0.0, 0.0, 5000.0)]
    taken = [(x, y) for (x, y, _) in bpts + cpts]
    vill = [(x, y, P_V) for (x, y) in lattice(rmax, S_V)
            if all(math.hypot(x - tx, y - ty) > fr for (tx, ty) in taken)]
    return vill + bpts + cpts


def build_province(rmax, footprint=True):
    # 1M province stack: villages 300@4km + bourgs 600@18km +
    # chefs 5000@64km (60km fame sheds just touch) + one 20000 regional.
    # Top-down: regional, then chefs, then bourgs, villages fill the rest.
    fr = 0.6 * S_V if footprint else 1e-9
    taken = [(0.0, 0.0)]
    chefs = []
    for (x, y) in lattice(rmax, 64.0):
        xx = x + 32.0
        if all(math.hypot(xx - cx, y - cy) > fr for (cx, cy) in taken):
            chefs.append((xx, y, 5000.0))
            taken.append((xx, y))
    bourgs = []
    for (x, y) in lattice(rmax, 18.0):
        xx = x + 9.0
        if all(math.hypot(xx - cx, y - cy) > fr for (cx, cy) in taken):
            bourgs.append((xx, y, 600.0))
            taken.append((xx, y))
    vill = [(x, y, P_V) for (x, y) in lattice(rmax, S_V)
            if all(math.hypot(x - tx, y - ty) > fr for (tx, ty) in taken)]
    return vill + bourgs + chefs + [(0.0, 0.0, 20000.0)]


def build_regional(rmax, footprint=True):
    # 2.4k towns every 32 km + 9.6k regionals every 96 km + villages elsewhere
    fr = 0.6 * S_V if footprint else 1e-9
    inter = 2.0 if footprint else 1e-9
    tpts = [(x + 16.0, y, 2400.0) for (x, y) in lattice(rmax, 32.0)]
    rpts = [(x, y, 9600.0) for (x, y) in lattice(rmax, 96.0)
            if all(math.hypot(x - tx, y - ty) > inter for (tx, ty, _) in tpts)]
    taken = [(x, y) for (x, y, _) in tpts + rpts]
    vill = [(x, y, P_V) for (x, y) in lattice(rmax, S_V)
            if all(math.hypot(x - tx, y - ty) > fr for (tx, ty) in taken)]
    return vill + tpts + rpts


SHAPES = [
    ("flat", 0.0, 0.0),
    ("s16/T600", 16.0, 600.0),
    ("s32/T2400", 32.0, 2400.0),
    ("s64/T2400", 64.0, 2400.0),
    ("s64/T9600", 64.0, 9600.0),
    ("+regional 9.6k", 0.0, 0.0),
    ("+goal 3-tier", 0.0, 0.0),
    ("+goal lean", 0.0, 0.0),
    ("+province", 0.0, 0.0),
]


def main(rmax=50.0, gamma=None, premium=None, footprint=True,
         melt=None, starv=None, decay=None, cart=None, rural=None):
    cfg = BASE_CFG
    if gamma is not None or premium is not None or melt is not None or starv is not None or decay is not None or cart is not None or rural is not None:
        cfg = replace(BASE_CFG,
                      market_scaling=BASE_CFG.market_scaling if gamma is None else gamma,
                      max_improvement=BASE_CFG.max_improvement if premium is None else premium,
                      melt_per_km=BASE_CFG.melt_per_km if melt is None else melt,
                      starvation_elasticity=BASE_CFG.starvation_elasticity if starv is None else starv,
                      farm_decay_at_radius=BASE_CFG.farm_decay_at_radius if decay is None else decay,
                      cart_distance_km=BASE_CFG.cart_distance_km if cart is None else cart,
                      rural_density=BASE_CFG.rural_density if rural is None else rural)
    print(f"{'shape':>18} {'N':>5} {'urban%':>7} {'rate':>9}")
    rows = []
    for label, s_t, T in SHAPES:
        t0 = time.perf_counter()
        if label.startswith("+regional"):
            spec = build_regional(rmax, footprint)
        elif label.startswith("+province"):
            spec = build_province(rmax, footprint)
        elif label.startswith("+goal lean"):
            spec = build_goal_lean(rmax, footprint)
        elif label.startswith("+goal"):
            spec = build_goal(rmax, footprint)
        else:
            spec = build(rmax, s_t, T, footprint=footprint)
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
    ap.add_argument("--no-footprint", action="store_false", dest="footprint",
                    help="only exclude exact overlaps (no 0.6*s0 site footprint)")
    ap.add_argument("--melt", type=float, default=None)
    ap.add_argument("--starv", type=float, default=None)
    ap.add_argument("--decay", type=float, default=None)
    ap.add_argument("--cart", type=float, default=None)
    ap.add_argument("--rural", type=float, default=None)
    sys.exit(main(**vars(ap.parse_args())))
