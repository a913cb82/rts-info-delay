"""Black-box hierarchy optimum via Bayesian optimization (settled rates).

Rephrase that makes BO fit: no integers. Tier DENSITIES (log scale) +
size RATIOS (log scale) + base spacing/size, all continuous (8-D unit
cube). Counts round to int (deterministic FPS upgrade-in-place top-down;
micro-cliffs absorbed as GP nugget); tiers vanish by density falling
out; sizes ordered by construction; total-pop band enforced by smooth
penalty with FREE geometric pre-check (no model call outside the band).
GP Matérn+nugget, LHS init, EI over Sobol pool, JSONL log + resume.
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine.economy as eco
from engine.config import GameConfig
from engine.world import Town
from hierarchy_opt import BASE_CFG as CFG, lattice

RMAX = 50.0
AREA = math.pi * RMAX * RMAX
TARGET = 100000.0
BAND = (0.5 * TARGET, 2.0 * TARGET)
HEX = math.sqrt(3.0) / 2.0
LOG = "benchmarks/bo_hierarchy.jsonl"

# bounds in transformed coords: [ln s0, ln P0, ln f1, ln r1, ln f2, ln r2, ln f3, ln r3]
LO = np.array([math.log(2.5), math.log(100.0),
               math.log(1e-4), 0.0, math.log(1e-4), 0.0, math.log(1e-4), 0.0])
HI = np.array([math.log(10.0), math.log(1000.0),
               0.0, math.log(10.0), 0.0, math.log(10.0), 0.0, math.log(10.0)])


def decode(u):
    x = LO + np.asarray(u, dtype=float) * (HI - LO)
    s0, P0 = math.exp(x[0]), math.exp(x[1])
    tiers = []
    for k in range(3):
        tiers.append((math.exp(x[2 + 2 * k]), math.exp(x[3 + 2 * k])))
    return s0, P0, tiers  # tiers: [(f1,r1),(f2,r2),(f3,r3)]


def fps_subset(pts, n):
    """Deterministic spread subset (first = centermost, ties -> low index)."""
    m = len(pts)
    if n <= 0:
        return []
    if n >= m:
        return list(range(m))
    d2c = (pts[:, 0] ** 2 + pts[:, 1] ** 2)
    chosen = [int(np.argmin(d2c))]
    mind = ((pts[:, 0] - pts[chosen[0], 0]) ** 2 +
            (pts[:, 1] - pts[chosen[0], 1]) ** 2)
    for _ in range(1, n):
        nxt = int(np.argmax(mind))
        chosen.append(nxt)
        d2 = ((pts[:, 0] - pts[nxt, 0]) ** 2 +
              (pts[:, 1] - pts[nxt, 1]) ** 2)
        mind = np.minimum(mind, d2)
    return chosen


def layout(s0, P0, tiers):
    """Deterministic (s0,P0,tiers) -> spec [(x,y,pop)]; top-down upgrade."""
    pts = np.array(sorted(lattice(RMAX, s0)), dtype=float)
    m = len(pts)
    pops = np.full(m, P0)
    d_prev = 1.0 / (HEX * s0 * s0)
    P_prev = P0
    taken = np.zeros(m, dtype=bool)
    for f, r in tiers:
        d = d_prev * f
        P = P_prev * r
        cnt = int(round(d * AREA))
        if cnt > 0:
            avail = np.nonzero(~taken)[0]
            if len(avail):
                sub = fps_subset(pts[avail], min(cnt, len(avail)))
                idx = avail[np.array(sub, dtype=int)]
                pops[idx] = P
                taken[idx] = True
        d_prev, P_prev = d, P
    return [(float(pts[k, 0]), float(pts[k, 1]), float(pops[k])) for k in range(m)]


def settled(spec, warm=3):
    towns = [Town(id=k, faction=0, x=500 + x, y=500 + y, population=p)
             for k, (x, y, p) in enumerate(spec)]
    tot0 = sum(t.population for t in towns)
    n2, _ = eco._step_core(towns, [2000, 2000], CFG)
    cold = (sum(n2) - tot0) / tot0 * 52.0 * 100.0
    for t, p in zip(towns, n2):
        t.population = float(p)
    for _ in range(warm - 1):
        n2, _ = eco._step_core(towns, [2000, 2000], CFG)
        for t, p in zip(towns, n2):
            t.population = float(p)
    tot1 = sum(t.population for t in towns)
    n2, _ = eco._step_core(towns, [2000, 2000], CFG)
    settled = (sum(n2) - tot1) / tot1 * 52.0 * 100.0
    return cold, settled, len(towns), tot0


def evaluate(u):
    t0 = time.perf_counter()
    s0, P0, tiers = decode(u)
    spec = layout(s0, P0, tiers)
    tot = sum(p for (_, _, p) in spec)
    info = {"s0": s0, "P0": P0, "tiers": tiers, "N": len(spec), "total": tot}
    if tot < BAND[0] or tot > BAND[1]:
        rel = (BAND[0] - tot) / BAND[0] if tot < BAND[0] else (tot - BAND[1]) / BAND[1]
        info.update(rate=-1.0 - 100.0 * rel * rel, cold=None, model=False,
                    dt=time.perf_counter() - t0)
        return info
    eco._geo_cache.update(key=None, geo=None, grid=None)
    eco._land_cache.update(key=None, areas=None)
    try:
        cold, rate_settled, n, tot0 = settled(spec)
    except Exception as e:  # never kill a 10-minute search on one config
        info.update(rate=-1e6, cold=None, model=False, error=str(e)[:120],
                    dt=time.perf_counter() - t0)
        return info
    Pops = sorted({round(p) for (_, _, p) in spec})
    info.update(rate=rate_settled, cold=cold, model=True, levels=len(Pops),
                top=max(Pops), urban=100.0 * sum(p for (_, _, p) in spec if p > P0 + 1) / tot,
                dt=time.perf_counter() - t0)
    return info


def run(n_init=24, n_iter=86, seed=0, log_path=LOG):
    from scipy.stats import norm, qmc
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

    D = 8
    Xs, ys = [], []
    seen = set()
    if Path(log_path).exists():
        for line in open(log_path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            u = tuple(round(float(v), 9) for v in r["u"])
            if u not in seen:
                seen.add(u)
                Xs.append(list(u))
                ys.append(float(r["rate"]))
        print(f"resumed {len(Xs)} evals from {log_path}", flush=True)

    def log_eval(u, info):
        rec = {"u": [float(v) for v in u]}
        rec.update({k: (float(v) if isinstance(v, (int, float)) else v)
                    for k, v in info.items() if k != "tiers"})
        rec["tiers"] = [[float(a), float(b)] for (a, b) in info.get("tiers", [])]
        with open(log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def ask_evaluate(u):
        key = tuple(round(float(v), 9) for v in u)
        if key in seen:
            return None
        seen.add(key)
        info = evaluate(u)
        Xs.append(list(key))
        ys.append(info["rate"])
        log_eval(key, info)
        return info

    # seeds: known-good skeletons first (never regress reporting)
    def seed_for(s0, P0, f1, r1):
        u = [(math.log(s0) - LO[0]) / (HI[0] - LO[0]),
             (math.log(P0) - LO[1]) / (HI[1] - LO[1]),
             (math.log(f1) - LO[2]) / (HI[2] - LO[2]),
             (math.log(r1) - LO[3]) / (HI[3] - LO[3]),
             0.0, 0.0, 0.0, 0.0]
        return [min(1.0, max(0.0, v)) for v in u]
    seeds = [seed_for(4.0, 300.0, 0.0123, 8.0),   # ~= s64/T2400
             seed_for(4.0, 300.0, 1e-4, 1.0),      # flat
             seed_for(4.0, 300.0, 0.02, 8.0)]      # ~= s32/T2400
    for u in seeds:
        ask_evaluate(u)

    sampler = qmc.LatinHypercube(d=D, seed=seed)
    for u in sampler.random(max(0, n_init - len(seeds))):
        ask_evaluate(u.tolist())

    kern = (ConstantKernel(1.0, (1e-3, 1e3)) *
            Matern(length_scale=np.ones(D), length_scale_bounds=(1e-2, 10.0), nu=2.5) +
            WhiteKernel(noise_level=1e-4, noise_level_bounds=(1e-8, 1e-1)))
    gpr = GaussianProcessRegressor(kernel=kern, normalize_y=True,
                                   n_restarts_optimizer=2, random_state=seed)
    X = np.array(Xs)
    y = np.array(ys)
    gpr.fit(X, y)  # hypers optimized once here...
    frozen = gpr.kernel_
    it = 0
    while len(Xs) < n_init + n_iter:
        it += 1
        if it % 25 == 0:  # ...re-optimized occasionally, frozen otherwise
            gpr = GaussianProcessRegressor(kernel=frozen, normalize_y=True,
                                           n_restarts_optimizer=2,
                                           random_state=seed + it)
            gpr.fit(X, y)
            frozen = gpr.kernel_
        else:
            gpr = GaussianProcessRegressor(kernel=frozen, normalize_y=True,
                                           optimizer=None)
            gpr.fit(X, y)
        sob = qmc.Sobol(d=D, scramble=True, seed=seed + 1000 + it)
        C = sob.random_base2(m=12)  # 4096 candidates
        mu, sigma = gpr.predict(C, return_std=True)
        best = float(np.max(y))
        with np.errstate(divide="ignore", invalid="ignore"):
            imp = mu - best - 0.01
            z = np.where(sigma > 0, imp / np.maximum(sigma, 1e-12), 0.0)
            val = np.where(sigma > 0, imp * norm.cdf(z) + sigma * norm.pdf(z), 0.0)
        u = C[int(np.argmax(val))].tolist()
        info = ask_evaluate(u)
        X = np.array(Xs)
        y = np.array(ys)
        if info is not None and it % 10 == 0:
            b = int(np.argmax(y))
            print(f"iter {len(Xs)}: best={y[b]:+.4f} "
                  f"N={info.get('N')} s0={info.get('s0', 0):.2f} "
                  f"dt={info.get('dt', 0):.2f}s", flush=True)
    b = int(np.argmax(y))
    print(f"done: {len(Xs)} evals, best={y[b]:+.4f}", flush=True)
    return Xs[b], y[b]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", type=int, default=24)
    ap.add_argument("--iter", type=int, default=86)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log", type=str, default=LOG)
    args = ap.parse_args()
    run(n_init=args.init, n_iter=args.iter, seed=args.seed, log_path=args.log)
