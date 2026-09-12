"""Growth-realism benchmark — engine-direct, no bots, deterministic.

Scores the *growth model* (src/engine/economy.py) against 1600s
anchors in benchmarks/realism_ref.json. Synthetic layouts bypass
BUILD so the growth formula is tested separately from the build rule.

Calendar: 1 turn = 1 week (TURNS_PER_YEAR = 52). Distances: game km.

Usage:
    python benchmarks/growth_realism.py            # all checks
    python benchmarks/growth_realism.py infill     # one check
    python benchmarks/growth_realism.py --json     # + machine record

Exit 0 always (this is a ruler, not a gate);_verdicts are in the table.
Current engine is the expected-red baseline: most checks FAIL.
"""

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from engine import economy as eco  # noqa: E402
from engine.config import GameConfig  # noqa: E402
from engine.world import Town, World  # noqa: E402

TURNS_PER_YEAR = 52
REF = json.loads((ROOT / "benchmarks" / "realism_ref.json").read_text())

_cfg = GameConfig()  # defaults match maps/*.json econ params
_next_id = [1]


def T(x, y, pop, faction=0):  # noqa: N802 - tiny town factory
    _next_id[0] += 1
    return Town(id=_next_id[0], faction=faction, x=float(x), y=float(y),
                population=float(pop))


def annual_pct(net, pop):
    return net / pop * TURNS_PER_YEAR * 100.0


def r1_growth_rate():
    """Isolated-town annual growth vs historical 0.1-0.5%/yr."""
    lo, hi = REF["longrun_growth_pct_per_yr"]["lo"], REF["longrun_growth_pct_per_yr"]["hi"]
    rows = []
    for p in (500, 2000, 10000, 40000, 80000):
        rows.append((p, annual_pct(eco.logistic(float(p), _cfg), float(p))))
    probe = [v for p, v in rows if p in (2000, 10000)]
    ok = all(lo <= v <= hi for v in probe)
    det = ", ".join(f"{p}:{v:.2f}%/yr" for p, v in rows)
    return ("growth_rate", "annual % @2k,10k", f"{probe[0]:.2f},{probe[1]:.2f}",
            f"[{lo},{hi}]", ok, det)


def r2_recovery():
    """Halve a 10k town; recovery time vs post-plague 40-150y."""
    lo, hi = REF["plague_halving_recovery_yr"]["lo"], REF["plague_halving_recovery_yr"]["hi"]
    w = World()
    w.towns.append(T(500, 500, 5000))
    target = 10000.0
    turns = None
    for i in range(1, 20001):
        eco.apply_growth(w, _cfg)
        if w.towns and w.towns[0].population >= target:
            turns = i
            break
    yrs = turns / TURNS_PER_YEAR if turns else float("inf")
    return ("recovery", "5k->10k yr", f"{yrs:.1f}" if turns else ">384",
            f"[{lo},{hi}]", turns is not None and lo <= yrs <= hi,
            f"{turns} turns" if turns else "never (cap 20k turns)")


def r3_viability():
    """Villages at 200/400/500 must persist a full year."""
    alive = {}
    for p0 in (200, 400, 500):
        w = World()
        w.towns.append(T(500, 500, p0))
        for _ in range(TURNS_PER_YEAR):
            eco.apply_growth(w, _cfg)
            if not w.towns:
                break
        alive[p0] = round(w.towns[0].population, 1) if w.towns else None
    ok = all(v is not None for v in alive.values())
    return ("viability", "pop after 52t", str(alive), "all alive", ok,
            f"death_threshold={_cfg.death_threshold}")


def r4_infill():
    """A 500-pop village midway between two 40k towns 150km apart
    must raise total net growth (new farmland worked)."""
    base = [T(0, 0, 40000), T(150, 0, 40000)]
    with_v = [T(0, 0, 40000), T(150, 0, 40000), T(75, 0, 500)]
    tot0 = sum(eco.crowding_nets_batch(base, _cfg))
    tot1 = sum(eco.crowding_nets_batch(with_v, _cfg))
    d = tot1 - tot0
    return ("infill", "delta total net/turn", f"{d:+.2f}", "> 0", d > 0,
            f"base={tot0:.2f} with-village={tot1:.2f} (village own ~+0.5)")


def r5_hierarchy():
    """Same people, same 4 sites (150km square): 4x10k vs 34k+3x2k.
    Realistic agglomeration should keep the hierarchical roof
    competitive; pure concavity crushes it."""
    pos = [(0, 0), (150, 0), (0, 150), (150, 150)]
    uni = [T(x, y, 10000) for x, y in pos]
    hier = [T(x, y, p) for (x, y), p in zip(pos, (34000, 2000, 2000, 2000))]
    tu = sum(eco.crowding_nets_batch(uni, _cfg))
    th = sum(eco.crowding_nets_batch(hier, _cfg))
    r = th / tu if tu else 0
    return ("hierarchy", "hier/uniform total", f"{r:.3f}", ">= 0.900", r >= 0.9,
            f"uniform={tu:.2f} hier={th:.2f}")


def r6_market_penalty():
    """A 10k neighbour at historical market spacing (15km) must not
    gut a 10k town's growth."""
    cap = REF["market_penalty_at_spacing_max_frac"]
    out = []
    for d in (15, 50):
        towns = [T(0, 0, 10000), T(d, 0, 10000)]
        iso = eco.logistic(10000.0, _cfg)
        net = eco.crowding_net(towns[0], towns, _cfg)
        out.append((d, 1.0 - net / iso))
    ok = out[0][1] <= cap
    return ("market_penalty", "penalty @15km,@50km",
            f"{out[0][1]:.2f},{out[1][1]:.2f}", f"@15 <= {cap}", ok,
            "fraction of isolated growth destroyed by one neighbour")


def r7_density():
    """Filled optimum 41x42k = 1.72M on 1M km2 vs 20-40/km2."""
    lo, hi = REF["rural_density_per_km2"]["lo"], REF["rural_density_per_km2"]["hi"]
    dens = 41 * 42000 / 1e6
    capmax = 41 * 100000 / 1e6
    ok = lo <= dens <= hi
    return ("density", "pop/km2 (cap-max)", f"{dens:.2f} ({capmax:.1f})",
            f"[{lo},{hi}]", ok, "1.71M solo optimum; cap-max still fails = structural")


def r8_urban():
    """Isolated 80k town should grow *slower per capita* than pure
    logistic predicts (urban graveyard 10-30% natural decrease)."""
    need = REF["urban_natural_decrease_pct"]["lo"] / 100.0
    percap = eco.logistic(80000.0, _cfg) / 80000.0
    percap_pred = 0.001 * (1.0 - 80000.0 / 100000.0)  # logistic identity
    extra = 1.0 - percap / percap_pred  # 0.0: no force beyond logistic
    return ("urban", "extra big-city penalty", f"{extra:.3f}", f">= {need:.2f}",
            extra >= need, "per-capita 80k vs logistic prediction")


def _grid41():
    pts = []
    for i in range(6):
        for j in range(6):
            pts.append((50 + 150 * i, 50 + 150 * j))
    for j in range(5):  # 41 total, min pairwise 150km
        pts.append((950, 50 + 150 * j))
    return pts


def r9_gapfill():
    """41-town uniform optimum + 40 infill villages: total must rise."""
    pts = _grid41()
    base = [T(x, y, 42000) for x, y in pts]
    full = list(base) + [T(x + 75, y, 500) for x, y in pts[:40]]
    tot0 = sum(eco.crowding_nets_batch(base, _cfg))
    tot1 = sum(eco.crowding_nets_batch(full, _cfg))
    d = tot1 - tot0
    # known solo optimum inequality (worklog 2026-09-12): top 81k / avg 42k
    ineq = 81000 / 42000
    need = REF["zipf_top_to_median_ratio"]["lo"]
    ok = d > 0 and ineq >= need
    return ("gapfill", "infill delta/turn; top/avg", f"{d:+.1f}; {ineq:.1f}x",
            f"> 0; >= {need}x", ok,
            f"base={tot0:.0f} filled={tot1:.0f}; econ-direct (bypasses BUILD 10km rule)")


def p1_perf():
    """500-town batch growth ms + econ surface size."""
    rng = __import__("random").Random(7)
    towns = [T(rng.uniform(0, 1000), rng.uniform(0, 1000),
               rng.choice([500, 2000, 10000, 40000])) for _ in range(500)]
    ts = []
    for _ in range(3):
        t0 = time.perf_counter()
        eco.crowding_nets_batch(towns, _cfg)
        ts.append((time.perf_counter() - t0) * 1000)
    ms = min(ts)
    nparams = 5  # growth, cap, eq_spacing, decay, asymmetry
    ok = ms < 10.0
    return ("perf", "500-town batch min-ms; params", f"{ms:.2f}; {nparams}",
            "< 10.0; <= 5", ok, "numba batch path; hard fail if formula leaves it")


def r10_sinkflow():
    """Great towns are sinks fuelled by migration (urban graveyard +
    rural-surplus circuit). Four sub-asserts, all must hold:
    SINK: isolated 80k annual natural growth <= 0 (above the ref sink
      threshold a town must not grow on its own);
    FUEL: a 60k city ringed by 6x300 villages (30km) nets ABOVE its
      isolated rate (fed by inflow);
    SHARE: ring villages net BELOW their isolated rate (they export);
    BOOKS: system total within 25% of the isolated sum (migration
      redistributes; only the urban penalty destroys).
    Deliberately API-agnostic: whatever mechanics land (flows in the
    economy phase or elsewhere), trajectories through apply_growth /
    crowding_nets_batch must show this. Current engine has no flows —
    crowding only destroys — so it fails."""
    sink_ann = annual_pct(eco.logistic(80000.0, _cfg), 80000.0)
    sink_ok = sink_ann <= 0.0
    city, vill = 60000.0, 300.0
    ring = [T(500 + 30 * math.cos(i * math.pi / 3),
              500 + 30 * math.sin(i * math.pi / 3), vill) for i in range(6)]
    town_c = T(500, 500, city)
    coupled = eco.crowding_nets_batch([town_c] + ring, _cfg)
    c_iso, v_iso = eco.logistic(city, _cfg), eco.logistic(vill, _cfg)
    c_cpl, v_cpl = coupled[0], sum(coupled[1:]) / 6
    fuel_ok = c_cpl > c_iso
    share_ok = v_cpl < v_iso
    tot_iso, tot_cpl = c_iso + 6 * v_iso, sum(coupled)
    books_ok = abs(tot_cpl - tot_iso) / abs(tot_iso) <= 0.25 if tot_iso else False
    ok = sink_ok and fuel_ok and share_ok and books_ok
    val = (f"sink {sink_ann:+.2f}%; city {c_cpl:.1f}/{c_iso:.1f}; "
           f"vill {v_cpl:.2f}/{v_iso:.2f}; tot {tot_cpl:.1f}/{tot_iso:.1f}")
    return ("sinkflow", "sink%; city; vill; tot", val,
            "<=0; cpl>iso; cpl<iso; +-25%", ok,
            f"SINK {'ok' if sink_ok else 'FAIL'} FUEL {'ok' if fuel_ok else 'FAIL'} "
            f"SHARE {'ok' if share_ok else 'FAIL'} BOOKS {'ok' if books_ok else 'FAIL'}")


CHECKS = [r1_growth_rate, r2_recovery, r3_viability, r4_infill,
          r5_hierarchy, r6_market_penalty, r7_density, r8_urban,
          r9_gapfill, r10_sinkflow, p1_perf]


def main(argv):
    want = [a for a in argv[1:] if not a.startswith("-")]
    as_json = "--json" in argv
    rows = []
    for fn in CHECKS:
        name = fn.__name__.split("_", 1)[1]
        if want and name not in want and fn.__name__ not in want:
            continue
        rows.append((fn.__name__,) + fn())
    fails = sum(1 for r in rows if not r[5])
    w = 16
    print(f"{'CHECK':<{w}} {'METRIC':<26} {'VALUE':<22} {'TARGET':<14} VERDICT")
    for _, name, metric, val, tgt, ok, _ in rows:
        print(f"{name:<{w}} {metric:<26} {val:<22} {tgt:<14} {'PASS' if ok else 'FAIL'}")
    print("--- detail ---")
    for _, name, _, _, _, _, det in rows:
        print(f"{name}: {det}")
    print(f"== {len(rows) - fails}/{len(rows)} PASS ({fails} FAIL) ==")
    if as_json:
        print(json.dumps([{"check": n, "metric": m, "value": v,
                           "target": t, "pass": o, "detail": d}
                          for _, n, m, v, t, o, d in rows]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
