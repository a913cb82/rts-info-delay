"""Agrarian-economy sanity checks: which settlement structures grow best?

Runs the new engine economy (apply_growth only) on hand-built scenarios
and reports end population, size distribution and growth. Small numbers:
6-8 archetypes, one horizon, no sweeps.
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.config import GameConfig
from engine.economy import apply_growth
from engine.world import Town, World

CFG = GameConfig()
TURNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
OUT = Path(f"/tmp/agrarian_sanity_{TURNS}.jsonl")
OUT.unlink(missing_ok=True)


def make(towns, map_size=(1000, 1000)):
    w = World()
    w.map_size = list(map_size)
    w.towns = [Town(id=i, faction=0, x=float(x), y=float(y), population=float(p),
                    is_capital=(i == 0))
               for i, (x, y, p) in enumerate(towns)]
    return w


def run(name, towns):
    w = make(towns)
    p0 = sum(t.population for t in w.towns)
    t0 = time.perf_counter()
    for turn in range(1, TURNS + 1):
        apply_growth(w, CFG)
    pops = sorted((t.population for t in w.towns), reverse=True)
    total = sum(pops)
    res = {
        "name": name, "turns": TURNS,
        "n_start": len(towns), "n_end": len(pops),
        "p0": round(p0, 1), "total": round(total, 1),
        "growth_pct_per_yr": round(((total / p0) ** (52.0 / TURNS) - 1) * 100, 3),
        "top": [round(p) for p in pops[:5]],
        "median": round(pops[len(pops) // 2]) if pops else 0,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    with OUT.open("a") as f:
        f.write(json.dumps(res) + "\n")
    print(f"{name:24s} n {res['n_start']:3d}->{res['n_end']:3d}  "
          f"total {res['total']:8.0f} ({res['growth_pct_per_yr']:+.2f}%/yr)  "
          f"top {res['top']}  ({res['elapsed_s']}s)", flush=True)


def ring(cx, cy, n, radius, pop, start_id=0):
    return [(cx + radius * math.cos(2 * math.pi * i / n),
             cy + radius * math.sin(2 * math.pi * i / n), pop) for i in range(n)]


def grid(x0, y0, nx, ny, step, pop):
    return [(x0 + i * step, y0 + j * step, pop)
            for i in range(nx) for j in range(ny)]


def main():
    V, T, C = 300.0, 2400.0, 20000.0
    # lone settlement classes
    run("lone_village_300", [(500, 500, V)])
    run("lone_town_2400", [(500, 500, T)])
    run("lone_city_20000", [(500, 500, C)])
    # land competition at 3.5 km vs independent at 150 km
    run("pair_3p5km", [(496.5, 500, V), (503.5, 500, V)])
    run("pair_150km", [(350, 500, V), (500, 500, V)])
    # market effect at fixed population (1 town + 6 villages vs 7 villages)
    run("town_ring_30km", [(500, 500, T)] + ring(500, 500, 6, 30, V))
    run("village_ring_30km", [(500 + 30 * math.cos(2 * math.pi * i / 6),
                               500 + 30 * math.sin(2 * math.pi * i / 6), V) for i in range(6)]
        + [(500, 500, V)])
    # city with a village hinterland
    run("city_24villages_50km", [(500, 500, C)] + ring(500, 500, 24, 50, V))
    # same 8,000 people, four structures
    run("same8000_one_town", [(500, 500, 8000)])
    run("same8000_four_towns", grid(300, 300, 2, 2, 200, 2000.0))
    run("same8000_26_villages", grid(100, 100, 6, 5, 100, 8000.0 / 30))
    run("same8000_town_19villages", [(150, 150, T)]
        + grid(300, 150, 5, 4, 120, (8000.0 - T) / 20))
    # density: 36 villages at 3.5 km (share land) vs 100 km (independent)
    run("lattice_dense_3p5km", grid(500, 500, 6, 6, 3.5, V))
    run("lattice_sparse_100km", grid(100, 100, 6, 6, 100, V))
    # hierarchy: 16 market towns + 64 villages vs 80 villages (equal start count not pop)
    run("hierarchy_16towns_64vill", grid(200, 200, 4, 4, 200, T) + grid(150, 150, 8, 8, 100, V))
    run("flat_80_villages", grid(50, 50, 10, 8, 90, V))
    print(f"jsonl: {OUT}")


if __name__ == "__main__":
    main()
