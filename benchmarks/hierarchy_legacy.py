"""Hierarchy optimum: legacy system on master (stock config, one turn).

Same specs as hierarchy_compare.py (lattice/build duplicated verbatim;
N/total columns cross-check identity across systems). Legacy model is
stateless (logistic + crowding), so one turn is the settled rate. Must
run in a process whose sys.path sees ONLY master's src (module name
collision with the worktree's engine package).
"""
import math
import sys
import time

sys.path.insert(0, "/home/acbraith/projects/rl_game_min/src")
assert "engine" not in sys.modules
import engine.economy as eco
from engine.config import GameConfig
from engine.world import Town

assert not hasattr(GameConfig(), "max_improvement"), "wrong engine (worktree?)"
CFG = GameConfig()
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


def build_regional(rmax):
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
    ("hier4", 32.0, 2400.0, 20000.0),
]


def spec_of(label, rmax):
    for lab, s_t, T, cap in SHAPES:
        if lab == label:
            if lab.startswith("+regional"):
                return build_regional(rmax)
            if lab == "hier4":
                return build(rmax, s_t, T, cap, 96.0, 9600.0)
            return build(rmax, s_t, T, cap)
    raise KeyError(label)


def main(rmax=50.0):
    print(f"{'shape':>18} {'N':>5} {'pop':>9} {'legacy':>9}")
    for lab, _, _, _ in SHAPES:
        t0 = time.perf_counter()
        spec = spec_of(lab, rmax)
        towns = [Town(id=k, faction=0, x=500 + x, y=500 + y, population=p)
                 for k, (x, y, p) in enumerate(spec)]
        tot = sum(t.population for t in towns)
        nets = eco.crowding_nets_batch(towns, CFG)
        g = sum(nets) / tot * 52.0 * 100.0
        dt = time.perf_counter() - t0
        print(f"{lab:>18} {len(spec):5d} {tot:9.0f} {g:+9.4f}  ({dt:.1f}s)",
              flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rmax", type=float, default=50.0)
    args = ap.parse_args()
    main(rmax=args.rmax)
