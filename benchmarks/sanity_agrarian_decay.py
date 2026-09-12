"""Von Thuenen decay: does splitting a population into more small
settlements raise output/growth?

Yield within R falls as 1 - c*(d/R)^p; workers farm the best land
first (a_w = sigma/rho0 each), so per-worker output falls as a
settlement grows. rho0 is rescaled so the full ring's mean yield
still equals rural_density. c=0 is the old flat ring.
"""
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.config import GameConfig
from engine.economy import _step_core, production
from engine.world import Town

FLAT = GameConfig()
DECAY = replace(FLAT, farm_decay_at_radius=0.9, farm_decay_shape=2.0)
TOTAL = 100_000.0


def grid(n, step):
    side = math.ceil(math.sqrt(n))
    pts = []
    for i in range(side):
        for j in range(side):
            pts.append((300.0 + i * step, 300.0 + j * step))
            if len(pts) >= n:
                return pts
    return pts


def system_rate(pts, pop, cfg, map_size=(2000, 2000)):
    towns = [Town(id=i, faction=0, x=x, y=y, population=pop)
             for i, (x, y) in enumerate(pts)]
    _n, serv = _step_core(towns, list(map_size), cfg, None)
    n2, _ = _step_core(towns, list(map_size), cfg,
                       {t.id: float(v) for t, v in zip(towns, serv)})
    total = pop * len(towns)
    return (sum(n2) - total) / total * 52.0 * 100.0


if __name__ == "__main__":
    area = np.array([math.pi * FLAT.farm_radius_km ** 2])
    print("per-worker output by settlement size (decay):")
    for p in (100.0, 300.0, 800.0, 1500.0, 2400.0):
        y = float(production(DECAY, area, np.array([p]))[0])
        print(f"  P={p:6.0f}  Y={y:6.0f}  Y/P={y / p:.3f}")
    print("100k split into N equal villages (10 km spacing):")
    for n in (25, 42, 67, 125, 333, 667):
        print(f"  N={n:4d}  village {TOTAL / n:6.0f}  "
              f"growth {system_rate(grid(n, 10.0), TOTAL / n, DECAY):+.4f}%/yr")
    print("packing, 333 x 300:")
    for step in (10.0, 5.0, 3.5):
        print(f"  spacing {step:4.1f} km  growth "
              f"{system_rate(grid(333, step), TOTAL / 333, DECAY):+.4f}%/yr")
