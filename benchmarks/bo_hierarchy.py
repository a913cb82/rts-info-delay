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
from dataclasses import replace
from engine.config import GameConfig
from engine.world import Town
from hierarchy_opt import BASE_CFG, lattice
CFG = BASE_CFG

RMAX = 50.0
AREA = math.pi * RMAX * RMAX
TARGET = 100000.0
BAND = (0.5 * TARGET, 3.0 * TARGET)  # tiered stacks carry chef mouths
HEX = math.sqrt(3.0) / 2.0
LOG = "benchmarks/bo_hierarchy.jsonl"

# bounds in transformed coords: [ln s0, ln P0, ln f1, ln r1, ln f2, ln r2, ln f3, ln r3]
LO = np.array([math.log(2.5), math.log(100.0),
               math.log(2.5), 0.0, math.log(2.5), 0.0, math.log(2.5), 0.0])
HI = np.array([math.log(10.0), math.log(1000.0),
               math.log(200.0), math.log(10.0), math.log(200.0),
               math.log(10.0), math.log(200.0), math.log(10.0)])
RMIN = 1.0  # min size ratio (2.0 for gap-constrained runs; set in run())


def decode(u):
    x = LO + np.asarray(u, dtype=float) * (HI - LO)
    s0, P0 = math.exp(x[0]), math.exp(x[1])
    # Absolute spacings, densest-first; upstairs clipped to village grid.
    pairs = sorted((math.exp(x[2 + 2 * k]), math.exp(x[3 + 2 * k]))
                   for k in range(3))
    tiers = []
    P_prev = P0
    for (s, r) in pairs:
        s = max(s, s0)
        P_prev = P_prev * max(r, RMIN)
        tiers.append((s, P_prev))
    return s0, P0, tiers  # tiers densest-first: [(s1,P1),(s2,P2),(s3,P3)]


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


def layout(s0, P0, tiers, footprint=True):
    """Deterministic (s0,P0,tiers) -> spec; build() conventions mirrored:
    tiers on own offset lattices (densest +s/2 like towns, middle plain
    like regionals, sparsest +s/2), claimed top-down (sparsest first).
    footprint=True: each site clears 0.6*s0 around it; False: only exact
    overlaps are excluded. Villages fill the rest."""
    fr = 0.6 * s0 if footprint else 1e-9
    offs = [tiers[0][0] / 2.0, 0.0, tiers[2][0] / 2.0]
    claimed = []  # (x, y, pop), sparsest tier first
    # Center-first: the sparsest present tier seats its hub at the disc
    # center (symmetric hubs cover best, +0.014–0.02 measured) before the
    # lattice fills around it. Geometric convention, not a special case:
    # every tier still claims purely by spacing afterwards.
    for k in (2, 1, 0):
        s, P = tiers[k]
        if AREA / (HEX * s * s) < 1.0:
            continue  # absent tier (expected < 1 town)
        if k == 2:
            claimed.append((0.0, 0.0, P))
            # fall through: lattice fills around the hub (nearby sites
            # inside fr are excluded by the check below)
        for (x, y) in lattice(RMAX, s):
            xx = x + offs[k]  # no disc refilter: exact build() mirror
            if all(math.hypot(xx - cx, y - cy) > fr
                   for (cx, cy, _) in claimed):
                claimed.append((xx, y, P))
    vill = [(x, y, P0) for (x, y) in lattice(RMAX, s0)
            if all(math.hypot(x - cx, y - cy) > fr
                   for (cx, cy, _) in claimed)]
    return vill + [(x, y, p) for (x, y, p) in claimed]


def settled(spec, warm=3):
    towns = [Town(id=k, faction=0, x=500 + x, y=500 + y, population=p)
             for k, (x, y, p) in enumerate(spec)]
    tot0 = sum(t.population for t in towns)
    n2, _, _ = eco._step_core(towns, [2000, 2000], CFG)
    cold = (sum(n2) - tot0) / tot0 * 52.0 * 100.0
    for t, p in zip(towns, n2):
        t.population = float(p)
    for _ in range(warm - 1):
        n2, _, _ = eco._step_core(towns, [2000, 2000], CFG)
        for t, p in zip(towns, n2):
            t.population = float(p)
    tot1 = sum(t.population for t in towns)
    n2, _, _ = eco._step_core(towns, [2000, 2000], CFG)
    settled = (sum(n2) - tot1) / tot1 * 52.0 * 100.0
    return cold, settled, len(towns), tot0


REQUIRE = 0  # up-tiers that must be present (expected count >= 1); set in run()
FOOTPRINT = True  # site footprint (0.6*s0 clearing) vs exact-overlap only; set in run()


def evaluate(u):
    t0 = time.perf_counter()
    s0, P0, tiers = decode(u)
    if REQUIRE:
        pen = 0.0
        for (s, _) in tiers[:REQUIRE]:
            exp = AREA / (HEX * s * s)
            if exp < 1.0:
                pen += 5.0 * (1.0 - exp)
        if pen > 0.0:
            return {"s0": s0, "P0": P0, "tiers": tiers, "N": 0,
                    "total": 0.0, "rate": -pen, "cold": None,
                    "model": False, "dt": time.perf_counter() - t0}
    spec = layout(s0, P0, tiers, footprint=FOOTPRINT)
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


def run(n_init=24, n_iter=86, seed=0, log_path=LOG, min_ratio=1.0,
        require=0, footprint=True, melt=None, premium=None, gamma=None,
        starv=None, decay=None, cart=None, rmax=None, target=None, rural=None,
        p0min=None, noseeds=False, nseeds=None, xi=0.01):
    global RMIN, REQUIRE, LO, FOOTPRINT, CFG, RMAX, AREA, TARGET, BAND, NOSEEDS
    NOSEEDS = bool(noseeds)
    RMIN = float(min_ratio)
    REQUIRE = int(require)
    FOOTPRINT = bool(footprint)
    if rmax is not None:
        RMAX = float(rmax)
        AREA = math.pi * RMAX * RMAX
    if target is not None:
        TARGET = float(target)
        BAND = (0.5 * TARGET, 3.0 * TARGET)
    if melt is not None or premium is not None or gamma is not None or starv is not None or decay is not None or cart is not None or rural is not None:
        CFG = replace(BASE_CFG,
                      market_scaling=BASE_CFG.market_scaling if gamma is None else gamma,
                      max_improvement=BASE_CFG.max_improvement if premium is None else premium,
                      melt_per_km=BASE_CFG.melt_per_km if melt is None else melt,
                      starvation_elasticity=BASE_CFG.starvation_elasticity if starv is None else starv,
                      farm_decay_at_radius=BASE_CFG.farm_decay_at_radius if decay is None else decay,
                      cart_distance_km=BASE_CFG.cart_distance_km if cart is None else cart,
                      rural_density=BASE_CFG.rural_density if rural is None else rural)
    print(f"CFG: melt={CFG.melt_per_km} premium={CFG.max_improvement} "
          f"gamma={CFG.market_scaling} starv={CFG.starvation_elasticity} "
          f"decay={CFG.farm_decay_at_radius} cart={CFG.cart_distance_km} "
          f"footprint={FOOTPRINT}", flush=True)
    LO = LO.copy()
    LO[3] = LO[5] = LO[7] = math.log(RMIN)
    if p0min is not None:
        LO[1] = math.log(float(p0min))
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
    def seed_for(s0, P0, s1, r1, s2=200.0, r2=None, s3=None, r3=None):
        if r2 is None:
            r2 = RMIN
        s3 = 200.0 if s3 is None else s3
        r3 = RMIN if r3 is None else r3
        u = [(math.log(s0) - LO[0]) / (HI[0] - LO[0]),
             (math.log(P0) - LO[1]) / (HI[1] - LO[1]),
             (math.log(s1) - LO[2]) / (HI[2] - LO[2]),
             (math.log(r1) - LO[3]) / (HI[3] - LO[3]),
             (math.log(s2) - LO[4]) / (HI[4] - LO[4]),
             (math.log(r2) - LO[5]) / (HI[5] - LO[5]),
             (math.log(s3) - LO[6]) / (HI[6] - LO[6]),
             (math.log(r3) - LO[7]) / (HI[7] - LO[7])]
        return [min(1.0, max(0.0, v)) for v in u]
    seeds = [seed_for(4.0, 300.0, 64.0, 8.0),            # ~= s64/T2400
             seed_for(4.0, 300.0, 200.0, RMIN),           # flat
             seed_for(4.0, 300.0, 32.0, 8.0),             # ~= s32/T2400
             seed_for(4.0, 300.0, 18.0, 1000.0 / 300.0, 82.0, 8.0),  # GOAL
             seed_for(4.0, 300.0, 18.0, 2.0, 64.0, 8.0),  # province (bourgs+chefs)
             seed_for(4.0, 300.0, 18.0, 2.0, 80.0, 5.0, 150.0, 4.0),  # full 4-tier
             seed_for(4.0, 300.0, 18.0, 5.0 / 3.0, 80.0, 3.0, 150.0, 10.0),  # small-chef 4-tier
             seed_for(3.5, 300.0, 16.0, 5.0 / 3.0, 70.0, 5.0, 150.0, 4.0),  # dense 4-tier
             seed_for(3.5, 300.0, 14.0, 5.0 / 3.0, 80.0, 10.0, 150.0, 10.0),  # maxi-dense 4-tier
             seed_for(3.5, 300.0, 13.0, 5.0 / 3.0, 80.0, 6.0, 150.0, 20.0 / 3.0),  # dense-combo 4-tier
             seed_for(4.0, 300.0, 13.0, 5.0 / 3.0, 80.0, 6.0, 150.0, 20.0 / 3.0),  # dense-bourg 4-tier
             seed_for(4.0, 300.0, 13.0, 2.0, 70.0, 4.0),  # dense-bourg 3-tier (district)
             seed_for(4.0, 300.0, 18.0, 5.0 / 3.0, 80.0, 2.0, 150.0, 10.0)]  # hand-lead 4-tier
    seed_list = seeds if nseeds is None else seeds[:max(0, int(nseeds))]
    if not noseeds:
        for u in seed_list:
            ask_evaluate(u)

    sampler = qmc.LatinHypercube(d=D, seed=seed)
    for u in sampler.random(max(0, n_init - (0 if noseeds else len(seed_list)))):
        ask_evaluate(u.tolist())

    kern = (ConstantKernel(1.0, (1e-3, 1e3)) *
            Matern(length_scale=np.ones(D), length_scale_bounds=(1e-3, 50.0), nu=2.5) +
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
        if it % 10 == 0:  # ...re-optimized regularly, frozen otherwise
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
            imp = mu - best - xi
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
    ap.add_argument("--min-ratio", type=float, default=1.0)
    ap.add_argument("--require", type=int, default=0)
    ap.add_argument("--no-footprint", action="store_false", dest="footprint",
                    help="only exclude exact overlaps (no 0.6*s0 site footprint)")
    ap.add_argument("--melt", type=float, default=None)
    ap.add_argument("--premium", type=float, default=None)
    ap.add_argument("--gamma", type=float, default=None)
    ap.add_argument("--starv", type=float, default=None)
    ap.add_argument("--decay", type=float, default=None)
    ap.add_argument("--cart", type=float, default=None)
    ap.add_argument("--rural", type=float, default=None)
    ap.add_argument("--p0min", type=float, default=None)
    ap.add_argument("--noseeds", action="store_true")
    ap.add_argument("--nseeds", type=int, default=None)
    ap.add_argument("--xi", type=float, default=0.01)
    ap.add_argument("--rmax", type=float, default=None)
    ap.add_argument("--target", type=float, default=None)
    args = ap.parse_args()
    run(n_init=args.init, n_iter=args.iter, seed=args.seed,
        log_path=args.log, min_ratio=args.min_ratio, require=args.require,
        footprint=args.footprint, melt=args.melt, premium=args.premium,
        gamma=args.gamma, starv=args.starv, decay=args.decay, cart=args.cart,
        rmax=args.rmax, target=args.target, rural=args.rural, p0min=args.p0min,
        noseeds=args.noseeds, nseeds=args.nseeds, xi=args.xi)
