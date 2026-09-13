"""1M-province scale transfer: same spacings as the 100k optimum, scaled counts.

Builds flat / regional-shape / bourgs-only / full-stack (bourgs + chefs +
regional) at r=118 and compares settled per-capita growth. Settles whether
the economic tiers transfer and whether power tiers (chefs, regional) pay
at province scale. All placement deterministic (sorted lattice, FPS subsets).
"""
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import engine.economy as eco
from engine.world import Town
from hierarchy_opt import BASE_CFG as CFG, build, build_regional, lattice
from bo_hierarchy import fps_subset

R = 118.0
MAP = [20000, 20000]
TURNS = 6


def _villages(tier_pts, pops, pts):
    out = []
    for k in range(len(pts)):
        if pops[k] > 300.0:
            out.append((float(pts[k, 0]), float(pts[k, 1]), float(pops[k])))
        elif all(math.hypot(pts[k, 0] - x, pts[k, 1] - y) > 2.4
                 for (x, y) in tier_pts):
            out.append((float(pts[k, 0]), float(pts[k, 1]), 300.0))
    return out


def full_stack():
    pts = np.array(sorted(lattice(R, 4.0)))
    pops = np.full(len(pts), 300.0)
    taken = np.zeros(len(pts), bool)
    rc = int(np.argmin((pts ** 2).sum(axis=1)))
    pops[rc] = 25000.0
    taken[rc] = True
    for cnt, P in ((9, 8000.0), (150, 1000.0)):
        avail = np.nonzero(~taken)[0]
        idx = avail[np.array(fps_subset(pts[avail], cnt))]
        pops[idx] = P
        taken[idx] = True
    return _villages(pts[taken], pops, pts)


def bourgs_only():
    pts = np.array(sorted(lattice(R, 4.0)))
    pops = np.full(len(pts), 300.0)
    idx = np.array(fps_subset(pts, 150))
    pops[idx] = 1000.0
    return _villages(pts[idx], pops, pts)


def run(label, spec):
    t0 = time.perf_counter()
    towns = [Town(id=k, faction=0, x=5000 + x, y=5000 + y, population=p)
             for k, (x, y, p) in enumerate(spec)]
    tot0 = sum(t.population for t in towns)
    urb = 100.0 * sum(p for (_, _, p) in spec if p > 300) / tot0
    rate = None
    for _ in range(TURNS):
        n2, _, _ = eco._step_core(towns, MAP, CFG)
        tot1 = sum(t.population for t in towns)
        rate = (sum(n2) - tot1) / tot1 * 52.0 * 100.0
        for t, p in zip(towns, n2):
            t.population = float(p)
    print(f"{label:18s} N={len(spec):5d} pop={tot0:8.0f} urb={urb:4.1f}% "
          f"settled={rate:+.4f} ({time.perf_counter() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    run("flat-1M", build(R, 0.0, 0.0, 0.0))
    run("regional-shape-1M", build_regional(R))
    run("bourgs-only-1M", bourgs_only())
    run("full-stack-1M", full_stack())
