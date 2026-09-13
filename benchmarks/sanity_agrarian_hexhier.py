"""Does the decay model favour a hierarchical settlement layout?

Flat hex village lattice vs town hierarchies at controlled urban
fractions, 100k people, single-turn rates (services resolve in-turn).
Towns are placed on rings inside the region; villages fill the hex
lattice at 3.5 km spacing (decay model: c=0.9, p=2).
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


def hexpts(rmax, s):
    pts = []
    jm = int(rmax / (s * math.sqrt(3) / 2)) + 2
    for j in range(-jm, jm + 1):
        y = j * s * math.sqrt(3) / 2
        off = s / 2 if j % 2 else 0.0
        im = int((rmax - off) / s) + 2
        for i in range(-im, im + 1):
            x = off + i * s
            if x * x + y * y <= rmax * rmax + 1e-9:
                pts.append((x, y))
    pts.sort(key=lambda p: p[0] ** 2 + p[1] ** 2)
    return pts


def rate(spec):
    towns = [Town(id=k, faction=0, x=500 + x, y=500 + y, population=p)
             for k, (x, y, p) in enumerate(spec)]
    n2, _, _ = _step_core(towns, [2000, 2000], CFG)
    tot = sum(t.population for t in towns)
    return (sum(n2) - tot) / tot * 52.0 * 100.0


def show(label, n_vill, towns, s_v=3.5, rmax=34.0):
    pts = hexpts(rmax, s_v)[:n_vill]
    vill = (TOTAL - sum(p for _, _, p in towns)) / max(n_vill, 1)
    spec = [(x, y, vill) for x, y in pts] + list(towns)
    g = rate(spec)
    urban = 100.0 * sum(p for _, _, p in towns) / TOTAL if towns else 0.0
    print(f"  {label:36s} urban {urban:5.1f}%  {g:+.4f}%/yr")


if __name__ == "__main__":
    print("decay model, 100k, villages at 3.5 km hex spacing:")
    show("flat: 300 villages", 300, [])
    for n_t, T in [(1, 2400), (4, 2400), (9, 2400), (16, 1200),
                   (4, 4800), (9, 4800), (16, 2400), (25, 1200)]:
        n_v = round((TOTAL - n_t * T) / 360)
        towns = []
        for k in range(n_t):
            ang = 2 * math.pi * k / n_t
            rr = 0.62 * 34.0 if n_t > 1 else 0.0
            towns.append((rr * math.cos(ang), rr * math.sin(ang), T))
        show(f"{n_t} towns x {T} + {n_v} villages", n_v, towns)
