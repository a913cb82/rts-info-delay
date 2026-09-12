"""Growth-realism benchmark — engine-direct, no bots, deterministic.

Scores the *growth model* (src/engine/economy.py) against 1600s
anchors in benchmarks/realism_ref.json. Synthetic layouts bypass
BUILD so the growth formula is tested separately from the build rule.

Calendar: 1 turn = 1 week (TURNS_PER_YEAR = 52). Distances: game km.

Usage:
    python benchmarks/growth_realism.py            # all checks
    python benchmarks/growth_realism.py infill     # one check
    python benchmarks/growth_realism.py --json     # + machine record
    python benchmarks/growth_realism.py --system candidate  # score a
      GrowthSystem from benchmarks/growth_systems.py (default: engine)

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
sys.path.insert(0, str(ROOT / "benchmarks"))

from engine.world import Town, World  # noqa: E402
from growth_systems import SYSTEMS  # noqa: E402

TURNS_PER_YEAR = 52
REF = json.loads((ROOT / "benchmarks" / "realism_ref.json").read_text())

G = None  # active GrowthSystem (benchmarks/growth_systems.py), set in main
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
        rows.append((p, annual_pct(G.isolated(float(p)), float(p))))
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
        G.step(w)
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
            G.step(w)
            if not w.towns:
                break
        alive[p0] = round(w.towns[0].population, 1) if w.towns else None
    ok = all(v is not None for v in alive.values())
    return ("viability", "pop after 52t", str(alive), "all alive", ok,
            f"death_threshold={G.death_threshold}")


def r4_infill():
    """A 500-pop village midway between two 40k towns 150km apart
    must raise total net growth (new farmland worked)."""
    base = [T(0, 0, 40000), T(150, 0, 40000)]
    with_v = [T(0, 0, 40000), T(150, 0, 40000), T(75, 0, 500)]
    tot0 = sum(G.nets(base))
    tot1 = sum(G.nets(with_v))
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
    tu = sum(G.nets(uni))
    th = sum(G.nets(hier))
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
        iso = G.isolated(10000.0)
        net = G.nets(towns)[0]
        out.append((d, 1.0 - net / iso))
    ok = out[0][1] <= cap
    return ("market_penalty", "penalty @15km,@50km",
            f"{out[0][1]:.2f},{out[1][1]:.2f}", f"@15 <= {cap}", ok,
            "fraction of isolated growth destroyed by one neighbour")


def _macro_layouts():
    """Archetype layouts on a 100x100km tile, each 300k pop (30/km2,
    mid historical range). H: hierarchical (784x250 vill @3.6km +
    36x2000 mkt @16.7km + 4x8000 reg @50km). U-big/U-mid/V: uniform
    at 30k/2.5k/250. Deterministic grids; shared by r7 (tier
    sustainability) and r13 (structure ranking)."""
    VS = 3.57  # village cell; markets/regionals sit at cell CENTERS so
    # every tier stands >= 2.5km (half cell diagonal) from every village:
    # markets on a 5-cell period (17.85km), regionals off-period (~50km).
    vill = [(1.8 + VS * i, 1.8 + VS * j, 250)
            for i in range(28) for j in range(28)]
    mkt = [(1.8 + VS * (2.5 + 5 * k), 1.8 + VS * (2.5 + 5 * m), 2800)
           for k in range(5) for m in range(5)]
    rc = [1.8 + VS * 4.5, 1.8 + VS * 18.5]
    reg = [(x, y, 8500) for x in rc for y in rc]
    specs = {"H": vill + mkt + reg,
             "U-big": [(12.5 + 25 * i, 16.7 + 25 * j, 30000)
                       for i in range(4) for j in range(3)][:10],
             "U-mid": [(4.5 + 9.09 * i, 4.5 + 9.09 * j, 2500)
                       for i in range(11) for j in range(11)][:120],
             "V": [(1.25 + 2.5 * i, 1.67 + 3.33 * j, 250)
                   for i in range(40) for j in range(30)]}
    pts = [(x, y) for x, y, _ in vill + mkt + reg]
    md = min(math.hypot(ax - bx, ay - by)
             for i, (ax, ay) in enumerate(pts) for bx, by in pts[i + 1:])
    assert md > 2.0, f"H-tile fixture collision: min pairwise {md:.4f}km"
    assert sum(p for _, _, p in specs["H"]) == 300000
    assert sum(p for _, _, p in specs["U-big"]) == 300000
    assert sum(p for _, _, p in specs["U-mid"]) == 300000
    assert sum(p for _, _, p in specs["V"]) == 300000
    return {k: [T(x, y, p) for x, y, p in spec] for k, spec in specs.items()}


def r7_sustain():
    """Every tier of the reference tile must sustain itself: mean net
    >= 0 for villages AND markets AND regionals at historical density
    (30/km2). Replaces the old static 41x42k constant, which scored the
    previous system instead of the candidate one."""
    towns = _macro_layouts()["H"]
    nets = G.nets(towns)
    tiers = {"vill": sum(nets[:784]) / 784, "mkt": sum(nets[784:809]) / 25,
             "reg": sum(nets[809:]) / 4}
    worst = min(tiers, key=tiers.get)
    ok = all(v >= 0 for v in tiers.values())
    return ("sustain", "min tier mean net/turn",
            f"{worst} {tiers[worst]:+.2f}", ">= 0 each", ok,
            " + ".join(f"{k} {v:+.1f}" for k, v in tiers.items()))


def r8_urban():
    """Isolated 80k town must grow *slower per capita* than the system's
    own rural trend predicts (urban graveyard 10-30%). The trend is fit
    at small sizes (1k, 4k: per-capita assumed linear in pop) and
    extrapolated — generic over any smooth base curve, so this tests the
    specifically-urban penalty, not saturation."""
    need = REF["urban_natural_decrease_pct"]["lo"] / 100.0
    y1, y2 = G.isolated(1000.0) / 1000.0, G.isolated(4000.0) / 4000.0
    b = (y1 - y2) / 3000.0
    if b > 0:
        pred = 80000.0 * (y1 + b * 1000.0 - b * 80000.0)
        how = "rural-trend extrapolation"
    else:  # per-capita still rising at 4k: fall back to the 4k rate itself
        pred = 80000.0 * y2
        how = "fallback vs 4k rate (rising per-capita at small sizes)"
    extra = 1.0 - G.isolated(80000.0) / pred if pred > 0 else 0.0
    return ("urban", "extra big-city penalty", f"{extra:.3f}", f">= {need:.2f}",
            extra >= need, how)


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
    tot0 = sum(G.nets(base))
    tot1 = sum(G.nets(full))
    d = tot1 - tot0
    ok = d > 0
    return ("gapfill", "infill delta/turn", f"{d:+.1f}", "> 0", ok,
            f"base={tot0:.0f} filled={tot1:.0f}; econ-direct (bypasses BUILD 10km rule). "
            "Inequality half retired to r13_macro (old 81k/42k constants removed).")


def p1_perf():
    """500-town batch growth ms + econ surface size."""
    rng = __import__("random").Random(7)
    towns = [T(rng.uniform(0, 1000), rng.uniform(0, 1000),
               rng.choice([500, 2000, 10000, 40000])) for _ in range(500)]
    ts = []
    for _ in range(3):
        t0 = time.perf_counter()
        G.nets(towns)
        ts.append((time.perf_counter() - t0) * 1000)
    ms = min(ts)
    ok = ms < 10.0 and G.nparams <= 5
    return ("perf", "500-town batch min-ms; params", f"{ms:.2f}; {G.nparams}",
            "< 10.0; <= 5", ok,
            f"{G.describe()} hot path; hard fail if a system leaves the batch shape")


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
    sink_ann = annual_pct(G.isolated(80000.0), 80000.0)
    sink_ok = sink_ann <= 0.0
    city, vill = 60000.0, 300.0
    ring = [T(500 + 30 * math.cos(i * math.pi / 3),
              500 + 30 * math.sin(i * math.pi / 3), vill) for i in range(6)]
    town_c = T(500, 500, city)
    coupled = G.nets([town_c] + ring)
    c_iso, v_iso = G.isolated(city), G.isolated(vill)
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


def r11_market_access():
    """Villages ringed (10km) around a 2500 market town must outgrow the
    identical ring with no market (day-return-trip access bonus).
    Ring-vs-ring controls for village-village crowding, isolating the
    market effect."""
    need = REF["market_access_ratio"]["lo"]
    ring = [(10 * math.cos(i * math.pi / 3), 10 * math.sin(i * math.pi / 3))
            for i in range(6)]
    base = [T(x, y, 300) for x, y in ring]
    withm = [T(x, y, 300) for x, y in ring] + [T(0, 0, 2500)]
    m0 = sum(G.nets(base)) / 6
    m1 = sum(G.nets(withm)[:6]) / 6
    r = m1 / m0 if m0 > 0 else float("-inf")
    return ("access", "ring vill w/ vs w/o market", f"{r:.3f}",
            f">= {need}", r >= need,
            f"with {m1:.3f}/turn vs without {m0:.3f}/turn (iso 0.30)")


def r12_returns():
    """Increasing returns somewhere: some town must more than double its
    isolated net when its pop doubles (threshold goods need scale).
    Pure concavity (current logistic) fails every pair. Tests the base
    curve only; placed threshold effects belong to r11/r13."""
    best, det = 0.0, []
    for p in (1000, 1500, 2000, 2500, 5000):
        r = G.isolated(2 * p) / (2 * G.isolated(p))
        best = max(best, r)
        det.append(f"{p}:{r:.3f}")
    return ("returns", "max net(2P)/2net(P)", f"{best:.3f}", ">= 1.000",
            best >= 1.0, ", ".join(det))


def r13_macro():
    """Structure ranking: the hierarchical tile must outgrow uniform-big,
    uniform-mid and all-village archetypes at equal pop (300k) on equal
    area (100x100km) — AND sustain itself (total >= 0). Joint test that
    hierarchy is optimal, not merely allowed. Discriminates real fixes
    from cap-raising: a bare K lift sustains but still ranks uniform first."""
    L = _macro_layouts()
    tots = {k: sum(G.nets(v)) for k, v in L.items()}
    rank_ok = tots["H"] > max(tots["U-big"], tots["U-mid"], tots["V"])
    sust_ok = tots["H"] >= 0
    ok = rank_ok and sust_ok
    val = ",".join(f"{k} {tots[k] / 1000:+.0f}k" for k in ("H", "U-big", "U-mid", "V"))
    return ("macro", "H,U-big,U-mid,V totals", val, "H first, H>=0", ok,
            f"RANK {'ok' if rank_ok else 'FAIL'} SUST {'ok' if sust_ok else 'FAIL'}; "
            f"H top/avg {8500 / (300000 / 813):.0f}x (Zipf-built, construction check)")


CHECKS = [r1_growth_rate, r2_recovery, r3_viability, r4_infill,
          r5_hierarchy, r6_market_penalty, r7_sustain, r8_urban,
          r9_gapfill, r10_sinkflow, r11_market_access, r12_returns,
          r13_macro, p1_perf]


def main(argv):
    global G
    want = [a for a in argv[1:] if not a.startswith("-")]
    as_json = "--json" in argv
    sysname = "engine"
    for a in argv[1:]:
        if a.startswith("--system"):
            sysname = a.split("=", 1)[1] if "=" in a else argv[argv.index(a) + 1]
    if sysname not in SYSTEMS:
        print(f"unknown system {sysname!r} (have: {sorted(SYSTEMS)})")
        return 2
    G = SYSTEMS[sysname]
    print(f"system: {G.describe()}")
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
