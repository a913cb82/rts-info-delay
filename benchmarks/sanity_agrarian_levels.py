"""Can 3- or 4-level hierarchies compete with a flat village mesh?

Hex village lattice (s_v, ~300 sites); each higher level samples every
q-th site (spacing x q, count / q^2); tier sizes are consecutive
multipliers of the village (m1, m2, ...). Villages size solved so the
total is 100k. Decay model (c=0.9, p=2), single-turn per-capita rate.
"""
import math
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.config import GameConfig
from engine.economy import _step_core
from engine.world import Town

CFG = replace(GameConfig(), farm_decay_at_radius=0.9, farm_decay_shape=2.0)
TOTAL = 100_000.0


def lattice(rmax, s):
    pts = []
    jm = int(rmax / (s * math.sqrt(3) / 2)) + 2
    for j in range(-jm, jm + 1):
        y = j * s * math.sqrt(3) / 2
        off = s / 2 if j % 2 else 0.0
        im = int((rmax - off) / s) + 2
        for i in range(-im, im + 1):
            x = off + i * s
            if x * x + y * y <= rmax * rmax + 1e-9:
                pts.append((i, j, x, y))
    return pts


def evaluate(s_v, qs, mults, n_target=300):
    cell = (math.sqrt(3) / 2) * s_v * s_v
    pts = lattice(math.sqrt(n_target * cell / math.pi), s_v)
    if len(pts) < 20:
        return None
    mods, cum = [1], 1
    for q in qs:
        cum *= q
        mods.append(cum)
    size_mult, z = [1.0], 1.0
    for m in mults:
        z *= m
        size_mult.append(z)
    tiers = []
    for (i, j, x, y) in pts:
        t = 0
        for k in range(1, len(mods)):
            if i % mods[k] == 0 and j % mods[k] == 0:
                t = k
        tiers.append(t)
    n = [tiers.count(k) for k in range(len(size_mult))]
    pv = TOTAL / sum(size_mult[t] * n[t] for t in range(len(n)))
    if pv < 40 or pv > 2500:
        return None
    towns = [Town(id=k, faction=0, x=500 + x, y=500 + y,
                  population=size_mult[tiers[k]] * pv)
             for k, (i, j, x, y) in enumerate(pts)]
    n2, _, _ = _step_core(towns, [2000, 2000], CFG)
    g = (sum(n2) - TOTAL) / TOTAL * 52.0 * 100.0
    urban = 100.0 * (1.0 - n[0] * pv / TOTAL)
    return g, urban, pv, n


if __name__ == "__main__":
    rows = []

    def add(s_v, qs, mults, level):
        r = evaluate(s_v, qs, mults)
        if r:
            rows.append((*r, level, s_v, qs, mults))

    for s_v in (3.0, 4.0, 5.0):
        add(s_v, (), (), 1)
        for q, m in [((2,), (2,)), ((2,), (4,)), ((3,), (2,)), ((3,), (4,)),
                     ((4,), (2,)), ((4,), (4,)), ((5,), (2,)), ((5,), (4,))]:
            add(s_v, q, m, 2)
        for q, m in [((2, 2), (2, 2)), ((2, 2), (2, 4)), ((3, 2), (2, 2)),
                     ((3, 3), (2, 2)), ((3, 3), (2, 4)), ((3, 3), (3, 3)),
                     ((4, 4), (2, 2)), ((4, 4), (2, 4)), ((4, 4), (3, 3)),
                     ((4, 5), (2, 2)), ((5, 5), (2, 2))]:
            add(s_v, q, m, 3)
        for q, m in [((3, 3, 3), (2, 2, 2)), ((3, 3, 3), (2, 2, 4)),
                     ((4, 4, 4), (2, 2, 2)), ((4, 4, 4), (2, 3, 3)),
                     ((4, 4, 5), (2, 2, 2)), ((5, 5, 5), (2, 2, 2))]:
            add(s_v, q, m, 4)
    best = {}
    for g, urban, pv, n, level, s_v, q, m in rows:
        if level not in best or g > best[level][0]:
            best[level] = (g, urban, pv, n, s_v, q, m)
    print("best per level count:")
    for level in sorted(best):
        g, urban, pv, n, s_v, q, m = best[level]
        print(f"  L={level}: {g:+.4f}%/yr  urban {urban:4.1f}%  P_v={pv:.0f}  "
              f"s_v={s_v} q={q} m={m} counts={n}")
