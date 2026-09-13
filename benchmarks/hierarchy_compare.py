"""Hierarchy optimum: current system, cold vs settled, 100k vs 1M.

Compares matched shapes (1/2/3/4 levels) by per-capita growth. Cold =
single turn from zero state (plain pairwise, == hierarchy_opt table).
Settled = 3 warmup turns (resell converges, pops drift ~0.01%) then the
measured turn. Master/legacy numbers come from hierarchy_legacy.py
(same specs, separate process); N/total columns cross-check identity.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine.economy as eco
from engine.world import Town
from hierarchy_opt import BASE_CFG as CFG, P_V, SHAPES, build, build_regional, clear

SHAPES4 = SHAPES + [("hier4", 32.0, 2400.0, 20000.0)]  # +96km/9.6k tier below


def spec_of(label, rmax):
    for lab, s_t, T, cap in SHAPES4:
        if lab == label:
            if lab.startswith("+regional"):
                return build_regional(rmax)
            if lab == "hier4":
                return build(rmax, s_t, T, cap, 96.0, 9600.0)
            return build(rmax, s_t, T, cap)
    raise KeyError(label)


def run(spec, map_size=(2000, 2000), cfg=None, warm=3):
    cfg = cfg or CFG
    towns = [Town(id=k, faction=0, x=500 + x, y=500 + y, population=p)
             for k, (x, y, p) in enumerate(spec)]
    tot0 = sum(t.population for t in towns)
    n2, _, _ = eco._step_core(towns, list(map_size), cfg)
    cold = (sum(n2) - tot0) / tot0 * 52.0 * 100.0
    for t, p in zip(towns, n2):
        t.population = float(p)
    for _ in range(warm - 1):
        n2, _, _ = eco._step_core(towns, list(map_size), cfg)
        for t, p in zip(towns, n2):
            t.population = float(p)
    drift = (sum(t.population for t in towns) - tot0) / tot0 * 100.0
    dlast = max(abs(t.last_improvement) for t in towns)
    n2, _, _ = eco._step_core(towns, list(map_size), cfg)
    tot1 = sum(t.population for t in towns)
    settled = (sum(n2) - tot1) / tot1 * 52.0 * 100.0
    dlast2 = max(abs(t.last_improvement) for t in towns)
    return cold, settled, drift, abs(dlast2 - dlast)


def main(rmax=50.0):
    print(f"{'shape':>18} {'N':>5} {'pop':>9} {'urb%':>6} {'top':>7} "
          f"{'cold':>8} {'settled':>8} {'drift%':>7} {'dlast':>7}")
    for lab, _, _, _ in SHAPES4:
        t0 = time.perf_counter()
        spec = spec_of(lab, rmax)
        tot = sum(p for (_, _, p) in spec)
        urb = 100.0 * sum(p for (_, _, p) in spec if p > P_V) / tot
        top = max(p for (_, _, p) in spec)
        clear()
        cold, settled, drift, dl = run(spec)
        dt = time.perf_counter() - t0
        print(f"{lab:>18} {len(spec):5d} {tot:9.0f} {urb:6.1f} {top:7.0f} "
              f"{cold:+8.4f} {settled:+8.4f} {drift:+7.3f} {dl:7.1e}  ({dt:.1f}s)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rmax", type=float, default=50.0)
    args = ap.parse_args()
    main(rmax=args.rmax)
