"""Forage benchmark scenarios: armies eating along their march path.

Interface under test (to be implemented in engine.economy):
    apply_forage(world, S, segments, config) -> {army_id: eaten}
      world:    World (towns give positions; armies give sizes)
      S:        np.ndarray[float], food stocks aligned with world.towns
                (modified in place)
      segments: {army_id: (x0, y0, x1, y1)} traversed this turn
      returns:  food eaten per army (<= size * 1.0 each)

Scales x situations:
  small (~250 towns, r38 disc) and large (~3000 towns, r118 disc), each with:
    plain  — 1 army marching over empty ground (few in range, many outside)
    dense  — 1 army marching through dense towns (many in, many out)
    crowded— 50 armies over dense towns (stress + determinism)
    camped — 10 stationary armies sitting on towns (disc, not stadium)

Run:  PYTHONPATH=src python benchmarks/forage_bench.py
"""

import sys
import time

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "benchmarks")

from engine.config import GameConfig
from engine.world import Army, Town, World

R_SMALL = 38.0
R_LARGE = 118.0
NEED_PER_MOUTH = 1.0  # same rate as civilians


def lattice(rmax, s):
    pts = []
    row = 0
    y = -rmax
    while y <= rmax + 1e-9:
        off = (s / 2.0) if (row % 2) else 0.0
        x = -rmax + off
        while x <= rmax + 1e-9:
            if x * x + y * y <= rmax * rmax:
                pts.append((x, y))
            x += s
        y += s * 0.8660254
        row += 1
    return pts


def make_world(town_pts, pop, armies):
    w = World()
    w.map_size = [1000, 1000]
    for k, (x, y) in enumerate(town_pts):
        w.towns.append(Town(id=k, faction=0, x=x, y=y,
                            population=float(pop)))
    for j, (x, y, size) in enumerate(armies):
        w.armies.append(Army(id=1000 + j, faction=1,
                             x=x, y=y, size=float(size)))
    return w
    return w


def make_stocks(world, cover=1.2):
    return np.array([t.population * cover for t in world.towns])


def march(x0, x1, y=0.0):
    return (x0, y, x1, y)


def scenario_plain(rmax, spacing):
    """One army across empty ground: few towns in range, many outside."""
    towns = lattice(rmax, spacing)
    armies = [(-rmax + 5, 0.0, 500.0)]
    w = make_world(towns, 300.0, armies)
    segs = {1000: march(-rmax + 5, rmax - 5)}
    return w, make_stocks(w), segs


def scenario_dense(rmax, spacing):
    """One army through dense towns: many in range, many outside."""
    towns = lattice(rmax, spacing)
    armies = [(-rmax + 5, 0.0, 800.0)]
    w = make_world(towns, 300.0, armies)
    segs = {1000: march(-rmax + 5, rmax - 5)}
    return w, make_stocks(w), segs


def scenario_crowded(rmax, spacing, narmies=50):
    """Many armies over dense towns: stress + determinism check."""
    towns = lattice(rmax, spacing)
    armies = []
    for j in range(narmies):
        y = -rmax + 10 + j * (2 * rmax - 20) / max(narmies - 1, 1)
        armies.append((-rmax + 5, y, 600.0))
    w = make_world(towns, 300.0, armies)
    segs = {1000 + j: march(-rmax + 5, rmax - 5, y)
            for j, (_, y, _) in enumerate(armies)}
    return w, make_stocks(w), segs


def scenario_camped(rmax, spacing, narmies=10):
    """Stationary armies on towns: disc foraging, no movement."""
    towns = lattice(rmax, spacing)
    w = make_world(towns, 300.0, [])
    spots = [(t.x, t.y) for t in w.towns[:narmies]]
    for j, (x, y) in enumerate(spots):
        w.armies.append(Army(id=1000 + j, faction=1,
                             x=x, y=y, size=200.0))
    segs = {1000 + j: (x, y, x, y) for j, (x, y) in enumerate(spots)}
    return w, make_stocks(w), segs


SCENARIOS = [
    ("small-plain", scenario_plain, (R_SMALL, 4.0)),
    ("small-dense", scenario_dense, (R_SMALL, 4.0)),
    ("small-crowded", scenario_crowded, (R_SMALL, 4.0)),
    ("small-camped", scenario_camped, (R_SMALL, 4.0)),
    ("large-plain", scenario_plain, (R_LARGE, 4.0)),
    ("large-dense", scenario_dense, (R_LARGE, 4.0)),
    ("large-crowded", scenario_crowded, (R_LARGE, 4.0)),
    ("large-camped", scenario_camped, (R_LARGE, 4.0)),
]


def check(name, w, S0, S1, eaten, cfg):
    stock_lost = S0.sum() - S1.sum()
    eaten_total = sum(eaten.values())
    assert abs(stock_lost - eaten_total) < 1e-6 * max(S0.sum(), 1.0), \
        f"{name}: conservation violated ({stock_lost} vs {eaten_total})"
    assert (S1 >= -1e-9).all(), f"{name}: negative stock"
    for a in w.armies:
        assert eaten.get(a.id, 0.0) <= a.size * NEED_PER_MOUTH + 1e-9, \
            f"{name}: army {a.id} overate"
    # Camped armies eat their whole need (sitting on full towns).
    if name.endswith("camped"):
        for a in w.armies:
            assert abs(eaten[a.id] - a.size * NEED_PER_MOUTH) < 1e-6, \
                f"{name}: camped army {a.id} short ({eaten[a.id]})"
    # Marching armies must find food along the path (not starve on plenty).
    if name.endswith("dense"):
        a = w.armies[0]
        assert eaten[a.id] > 0.5 * a.size * NEED_PER_MOUTH, \
            f"{name}: marching army starved on dense ground"
    return stock_lost


def main():
    from engine.economy import apply_forage
    cfg = GameConfig()
    print(f"{'scenario':<15} {'towns':>6} {'armies':>7} {'eaten':>10}  ms/call", flush=True)
    total_ms = 0.0
    for name, fn, args in SCENARIOS:
        w, S, segs = fn(*args)
        S0 = S.copy()
        apply_forage(w, S, segs, cfg)  # warmup (caches, numba)
        S = S0.copy()
        reps = 5
        t0 = time.perf_counter()
        for _ in range(reps):
            S = S0.copy()
            eaten = apply_forage(w, S, segs, cfg)
        ms = (time.perf_counter() - t0) / reps * 1000
        total_ms += ms
        lost = check(name, w, S0, S, eaten, cfg)
        # Determinism: twice more must match bit-for-bit.
        S2 = S0.copy()
        e2 = apply_forage(w, S2, segs, cfg)
        assert (S2 == S).all() and e2.keys() == eaten.keys() and \
            all(e2[k] == eaten[k] for k in eaten), f"{name}: nondeterministic"
        print(f"{name:<15} {len(w.towns):>6} {len(w.armies):>7} "
              f"{lost:>10.0f}  {ms:>7.2f}", flush=True)
    print(f"total {total_ms:.1f} ms/call over {len(SCENARIOS)} scenarios", flush=True)


if __name__ == "__main__":
    main()
