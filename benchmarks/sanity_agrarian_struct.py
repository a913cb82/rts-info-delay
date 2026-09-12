"""Structure test: same 4,200 people, same 120x120 km region.

village-only vs villages + market town of increasing size vs one big
town (and a far-town control). Which structure grows best over T turns?
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
TURNS = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
OUT = Path(f"/tmp/agrarian_struct_{TURNS}.jsonl")
OUT.unlink(missing_ok=True)
TOTAL = 4200.0


def run(name, spec):
    w = World()
    w.map_size = [1000, 1000]
    w.towns = [Town(id=i, faction=0, x=float(x), y=float(y),
                    population=float(p), is_capital=(i == 0))
               for i, (x, y, p) in enumerate(spec)]
    p0 = sum(t.population for t in w.towns)
    t0 = time.perf_counter()
    for _ in range(TURNS):
        apply_growth(w, CFG)
    pops = sorted((t.population for t in w.towns), reverse=True)
    total = sum(pops)
    res = {"name": name, "turns": TURNS, "p0": p0, "total": round(total, 1),
           "growth_pct_per_yr": round(((total / p0) ** (52.0 / TURNS) - 1) * 100, 4),
           "n": len(pops), "top": [round(p) for p in pops[:4]],
           "median": round(pops[len(pops) // 2]) if pops else 0,
           "elapsed_s": round(time.perf_counter() - t0, 1)}
    with OUT.open("a") as f:
        f.write(json.dumps(res) + "\n")
    print(f"{name:22s} n={res['n']:3d} total {res['total']:8.0f} "
          f"({res['growth_pct_per_yr']:+.4f}%/yr) top {res['top']} "
          f"med {res['median']} ({res['elapsed_s']}s)", flush=True)


def cluster(n_villages, village_pop, town_pop):
    """One town at center (if town_pop>0) + n villages on rings <=60 km."""
    spec = []
    if town_pop > 0:
        spec.append((500.0, 500.0, town_pop))
    for i in range(n_villages):
        ang = 2 * math.pi * i / max(n_villages, 1)
        rad = 25.0 + 10.0 * (i % 3)
        spec.append((500.0 + rad * math.cos(ang), 500.0 + rad * math.sin(ang),
                     village_pop))
    return spec


def main():
    # 14 villages of 300 (no town)
    run("14_villages", cluster(14, 300.0, 0.0))
    # villages + town, equal total population
    run("10v_plus_1200town", cluster(10, 300.0, 1200.0))
    run("6v_plus_2400town", cluster(6, 300.0, 2400.0))
    run("3v_plus_3300town", cluster(3, 300.0, 3300.0))
    run("1_town_4200", [(500.0, 500.0, TOTAL)])
    print(f"jsonl: {OUT}")


if __name__ == "__main__":
    main()
