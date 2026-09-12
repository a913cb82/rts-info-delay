"""Fit the candidate growth system to the realism suite (Level 1 + 2).

Level 1 (parameters): black-box minimisation of
    loss = 1 - mean(scenario scores) + lambda * penalty(params)
where penalty = group L1 on amplitudes (alpha, gamma, mu, c) toward 0
+ ridge on shape params toward their prior scales, + soft box walls.
Optimizer: parallel random search -> Nelder-Mead multi-start (scipy).

Level 2 (hyperparameters): lambda grid x K=4 force-balanced folds over
the 15 training scenarios (macro held out entirely), warm-started CV;
select by the 1-SE rule; refit; report once on macro.

Usage (workers = 8):
    python benchmarks/fit_growth.py search --n 800 --out fit/search.json
    python benchmarks/fit_growth.py nm --x0 fit/search.json --fev 300 --out fit/nm.json
    python benchmarks/fit_growth.py cv --x0 fit/nm.json --fev 60 --out fit/cv.json
    python benchmarks/fit_growth.py eval --x0 fit/nm.json [--macro]
"""

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import growth_realism as gr  # noqa: E402
from candidate_growth import (AMPLITUDES, BOX, MIG_GRAV, MIG_LIN,  # noqa: E402
                              NAMES, PRIOR, SHAPES, FittedGrowth,
                              from_log10, to_log10)

NAMES_ALL = [fn.__name__.split("_", 1)[1] for fn in gr.SCENARIOS]
# perf is a guardrail (timing is noisy under the fitting pool), evaluated
# separately on a quiet run, never part of the fitted objective.
TRAIN = [n for n in NAMES_ALL if n not in ("macro", "perf")]

# discrete hyperparameter grid (model variants); amplitudes re-scaled per
# migration variant because mu's units differ
VARIANTS = [
    {"tag": "grav", "mig": MIG_GRAV, "theta0": False, "share": False, "mfix": 0.0},
    {"tag": "grav+theta0", "mig": MIG_GRAV, "theta0": True, "share": False, "mfix": 0.0},
    {"tag": "grav+shared", "mig": MIG_GRAV, "theta0": False, "share": True, "mfix": 0.0},
    {"tag": "grav+both", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 0.0},
    {"tag": "lean7", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0},
    {"tag": "lean6", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0,
     "bfixK": 1e5},
    {"tag": "lean5", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0,
     "bfixK": 1e5, "nogamma": True},
    {"tag": "lean6z", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0,
     "nogamma": True},
    {"tag": "K300", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0,
     "bfixK": 3e5, "nogamma": True},
    {"tag": "K1e6", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0,
     "bfixK": 1e6, "nogamma": True},
    {"tag": "Kinf", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0,
     "bfixK": 1e15, "nogamma": True},
    {"tag": "thr", "mig": MIG_GRAV, "theta0": False, "share": False, "mfix": 30.0},
    {"tag": "thr+shared", "mig": MIG_GRAV, "theta0": False, "share": True, "mfix": 30.0},
    {"tag": "thr+theta0", "mig": MIG_GRAV, "theta0": True, "share": False, "mfix": 30.0},
    {"tag": "thr+both", "mig": MIG_GRAV, "theta0": True, "share": True, "mfix": 30.0},
    {"tag": "lin", "mig": MIG_LIN, "theta0": False, "share": False, "mfix": 0.0},
]
BOX_GRAV = dict(BOX, mu=(-11.0, -6.0))
BOX_LIN = BOX
FOLDS = {
    "food": ["village_rate", "viability", "infill", "gapfill", "sustain"],
    "transport": ["market_penalty", "access", "region"],
    "materials": ["recovery", "hinterland", "urban"],
    "structure": ["returns", "hierarchy", "sinkflow"],
}
_ = {s for f in FOLDS.values() for s in f}
assert _ == set(TRAIN), _ ^ set(TRAIN)


def make_system(params, variant=None):
    v = variant or VARIANTS[0]
    return FittedGrowth(params, variant=v["mig"], theta0=v["theta0"],
                        share=v["share"], mfix=v.get("mfix", 0.0),
                        bfixK=v.get("bfixK", 0.0), nogamma=v.get("nogamma", False))


def scores_for(params, names, variant=None):
    gr.G = make_system(params, variant)
    out = {}
    for fn in gr.SCENARIOS:
        nm = fn.__name__.split("_", 1)[1]
        if nm in names:
            out[nm] = fn()[4]
    return out


def penalty(params, lam, variant=None):
    amu = dict(AMPLITUDES)
    if variant and variant["mig"] == MIG_GRAV:
        amu["mu"] = 1e-8
    pen = 0.0
    for k, s in amu.items():
        pen += lam * params[k] / s
    for k, s in SHAPES.items():
        pen += lam * 0.1 * (math.log10(params[k] / s)) ** 2
    return pen


def get_variant(tag):
    for v in VARIANTS:
        if v["tag"] == tag:
            return v
    raise SystemExit(f"unknown variant {tag!r}; have {[v['tag'] for v in VARIANTS]}")


def loss_fn(x, names, lam, variant=None):
    pen = 0.0
    box = BOX_GRAV if variant and variant["mig"] == MIG_GRAV else BOX_LIN
    for k, v in zip(NAMES, x):
        lo, hi = box[k]
        pen += 10.0 * (max(0.0, lo - v) ** 2 + max(0.0, v - hi) ** 2)
    params = from_log10(x)
    pen += penalty(params, lam, variant)
    sc = scores_for(params, names, variant)
    return (1.0 - sum(sc.values()) / len(sc) + pen), sc


def _worker(payload):
    x, names, lam, variant = payload
    try:
        return loss_fn(list(x), names, lam, variant)
    except Exception as e:  # noqa: BLE001
        return 5.0, {"error": str(e)}


def unpack_x0(path):
    d = json.loads(Path(path).read_text())
    best = d["best"] if isinstance(d, dict) and "best" in d else d
    return list(best["x"]) if isinstance(best, dict) else list(best), d


def cmd_search(a):
    tags = a.variants.split(",") if a.variants else [a.variant]
    variants = [get_variant(t) for t in tags]
    rng = np.random.default_rng(a.seed)
    xs, vs = [], []
    for v in variants:
        box = BOX_GRAV if v["mig"] == MIG_GRAV else BOX_LIN
        base = dict(PRIOR)
        if v["mig"] == MIG_GRAV:
            base["mu"] = 3e-8
        xs.append(to_log10(base))
        vs.append(v)
        for _ in range(2):
            xs.append([rng.uniform(*box[k]) for k in NAMES])
            vs.append(v)
    for i in range(a.n):
        v = variants[i % len(variants)]
        box = BOX_GRAV if v["mig"] == MIG_GRAV else BOX_LIN
        xs.append([rng.uniform(*box[k]) for k in NAMES])
        vs.append(v)
    payloads = [(x, TRAIN, a.lam, v) for x, v in zip(xs, vs)]
    res = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (loss, sc) in enumerate(ex.map(_worker, payloads, chunksize=4)):
            res.append({"x": xs[i], "loss": loss, "scores": sc,
                        "variant": vs[i]["tag"]})
            if (i + 1) % 100 == 0:
                best = min(res, key=lambda r: r["loss"])
                print(f"[{i + 1}/{len(xs)}] {time.time() - t0:.0f}s best "
                      f"{best['loss']:.4f} ({best['variant']})", flush=True)
    res.sort(key=lambda r: r["loss"])
    out = {"lam": a.lam, "variants": tags, "names": TRAIN,
           "results": res[:100], "best": res[0], "elapsed_s": time.time() - t0}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"best loss {res[0]['loss']:.4f} ({res[0]['variant']}) -> {a.out}")
    for v in tags:
        top = next((r for r in res if r["variant"] == v), None)
        if top:
            print(f"  {v:<13} best {top['loss']:.4f}")


def nm_run(x0, names, lam, fev, variant=None):
    from scipy.optimize import minimize

    def f(x):
        return loss_fn(list(x), names, lam, variant)[0]

    r = minimize(f, np.array(x0, dtype=float), method="Nelder-Mead",
                 options={"maxfev": fev, "xatol": 1e-4, "fatol": 1e-6})
    return list(r.x), float(r.fun), int(r.nfev)


def _nm_worker(payload):
    x0, names, lam, fev, variant = payload
    try:
        x, loss, nfev = nm_run(x0, names, lam, fev, variant)
        return {"x": x, "loss": loss, "nfev": nfev}
    except Exception as e:  # noqa: BLE001
        return {"x": list(x0), "loss": 5.0, "error": str(e)}


def cmd_nm(a):
    variant = get_variant(a.variant)
    base, prev = unpack_x0(a.x0)
    rng = np.random.default_rng(a.seed + 1)
    starts = [base]
    for _ in range(a.starts - 1):
        starts.append([v + rng.normal(0, a.jitter) for v in base])
    payloads = [(s, TRAIN, a.lam, a.fev, variant) for s in starts]
    with ProcessPoolExecutor(max_workers=min(a.workers, len(payloads))) as ex:
        res = list(ex.map(_nm_worker, payloads))
    res.sort(key=lambda r: r["loss"])
    out = {"lam": a.lam, "variant": a.variant, "names": TRAIN,
           "best": res[0], "all": res}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    sc = scores_for(from_log10(res[0]["x"]), TRAIN, variant)
    print(f"best loss {res[0]['loss']:.4f} mean score "
          f"{sum(sc.values()) / len(sc):.4f} -> {a.out}")


def cmd_cv(a):
    variant = get_variant(a.variant)
    base, prev = unpack_x0(a.x0)
    jobs = []
    for fold, held in FOLDS.items():
        train = [n for n in TRAIN if n not in held]
        jobs.append((fold, held, train))
    payloads = [(base, train, a.lam, a.fev, variant) for _, _, train in jobs]
    with ProcessPoolExecutor(max_workers=len(payloads)) as ex:
        fits = list(ex.map(_nm_worker, payloads))
    out = {"lam": a.lam, "variant": a.variant, "folds": {}, "cv": 0.0}
    tot, n = 0.0, 0
    for (fold, held, _), fit in zip(jobs, fits):
        sc = scores_for(from_log10(fit["x"]), held, variant)
        m = sum(sc.values()) / len(sc)
        out["folds"][fold] = {"held": held, "score": m, "scores": sc,
                              "x": fit["x"], "fit_loss": fit["loss"]}
        tot += m
        n += 1
        print(f"fold {fold:<10} held-out score {m:.4f}", flush=True)
    out["cv"] = tot / n
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"CV ({a.lam}) = {out['cv']:.4f} -> {a.out}")


def cmd_explore(a):
    """Targeted local sweep around a base point; appends every eval to a
    JSONL log (incremental record), prints a ranked table."""
    import itertools
    variant = get_variant(a.variant)
    base, _ = unpack_x0(a.x0)
    sets = []
    for spec in a.set:
        k, vals = spec.split("=", 1)
        sets.append((k, [float(v) for v in vals.split(",")]))
    combos = list(itertools.product(*[v for _, v in sets]))
    xs, tags = [], []
    for combo in combos:
        x = list(base)
        for (k, _), v in zip(sets, combo):
            x[NAMES.index(k)] = math.log10(v)
        xs.append(x)
        tags.append(dict(zip([k for k, _ in sets], combo)))
    payloads = [(x, TRAIN, a.lam, variant) for x in xs]
    res = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (loss, sc) in enumerate(ex.map(_worker, payloads, chunksize=2)):
            mean = sum(sc.values()) / len(sc) if "error" not in sc else 0.0
            rec = {"variant": variant["tag"], "tags": tags[i], "x": xs[i],
                   "loss": loss, "mean": mean, "scores": sc}
            res.append(rec)
            with open(a.out, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
    res.sort(key=lambda r: -r["mean"])
    print(f"{len(res)} evals in {time.time() - t0:.0f}s (logged {a.out})")
    for r in res[:8]:
        gap = {k: round(v, 3) for k, v in r["tags"].items()}
        print(f"  mean {r['mean']:.4f} loss {r['loss']:.4f} {gap}")


def cmd_eval(a):
    variant = get_variant(a.variant)
    x, _ = unpack_x0(a.x0)
    names = NAMES_ALL if a.macro else TRAIN
    sc = scores_for(from_log10(x), names, variant)
    for k in names:
        print(f"  {k:<15} {sc[k]:.3f}")
    print(f"mean over {len(names)}: {sum(sc.values()) / len(sc):.4f}")
    print("params:", json.dumps({k: from_log10(x)[k] for k in NAMES}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("--n", type=int, default=800)
    s.add_argument("--lam", type=float, default=0.05)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--workers", type=int, default=8)
    s.add_argument("--variant", default="grav")
    s.add_argument("--variants", default="")
    s.add_argument("--out", default="fit/search.json")
    s.set_defaults(fn=cmd_search)
    m = sub.add_parser("nm")
    m.add_argument("--x0", required=True)
    m.add_argument("--lam", type=float, default=0.05)
    m.add_argument("--starts", type=int, default=8)
    m.add_argument("--fev", type=int, default=300)
    m.add_argument("--workers", type=int, default=8)
    m.add_argument("--variant", default="grav")
    m.add_argument("--jitter", type=float, default=0.25)
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--out", default="fit/nm.json")
    m.set_defaults(fn=cmd_nm)
    c = sub.add_parser("cv")
    c.add_argument("--x0", required=True)
    c.add_argument("--lam", type=float, default=0.05)
    c.add_argument("--fev", type=int, default=60)
    c.add_argument("--workers", type=int, default=8)
    c.add_argument("--variant", default="grav")
    c.add_argument("--out", default="fit/cv.json")
    c.set_defaults(fn=cmd_cv)
    e = sub.add_parser("eval")
    e.add_argument("--x0", required=True)
    e.add_argument("--macro", action="store_true")
    e.add_argument("--variant", default="grav")
    e.set_defaults(fn=cmd_eval)
    x = sub.add_parser("explore")
    x.add_argument("--x0", required=True)
    x.add_argument("--set", action="append", default=[],
                   help="name=v1,v2,... (linear values; any name in NAMES)")
    x.add_argument("--lam", type=float, default=0.02)
    x.add_argument("--workers", type=int, default=8)
    x.add_argument("--variant", default="grav")
    x.add_argument("--out", default="fit/explore.jsonl")
    x.set_defaults(fn=cmd_explore)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
