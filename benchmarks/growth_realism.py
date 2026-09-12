"""Growth-realism suite — pure integration tests, no unit probes.

Each item is a SCENARIO: set up towns, run them forward through a
GrowthSystem (benchmarks/growth_systems.py), observe the behavior,
score CLOSENESS to the historical expectation (0..1, 1 = inside the
reference range). Composite = mean score. No binary verdicts: the
number is the verdict.

Usage:
    python benchmarks/growth_realism.py                 # all, ~2s
    python benchmarks/growth_realism.py macro           # subset
    python benchmarks/growth_realism.py --system NAME   # SYSTEMS[NAME]
    python benchmarks/growth_realism.py --json          # + machine record

Rules for suite edits (frozen with the ref ranges): scenarios assert
BEHAVIOR (trajectories, outcomes), never mechanism; isolated towns are
used only at self-feeding sizes (<= ~1k) — anything bigger must have
its hinterland in the scenario. New mechanics register a system in
growth_systems.py; this file changes only to add scenarios, never to
pass one.
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

G = None  # active GrowthSystem, set in main
_next_id = [1]


def T(x, y, pop, faction=0):  # noqa: N802 - tiny town factory
    _next_id[0] += 1
    return Town(id=_next_id[0], faction=faction, x=float(x), y=float(y),
                population=float(pop))


# --- scoring primitives ------------------------------------------------

def band(v, lo, hi, log=False):
    """1.0 inside [lo,hi]; linear (or log-distance) falloff to 0 outside."""
    if lo <= v <= hi:
        return 1.0
    if log:
        if v <= 0 or lo <= 0:
            return 0.0
        lv, llo, lhi = math.log(v), math.log(lo), math.log(hi)
        d = llo - lv if v < lo else lv - lhi
        return max(0.0, 1.0 - d / ((lhi - llo) or 1.0))
    d = lo - v if v < lo else v - hi
    return max(0.0, 1.0 - d / ((hi - lo) or 1.0))


def onesided(v, scale):
    """1.0 if v >= 0, linear falloff to 0 at v = -scale."""
    if v >= 0:
        return 1.0
    return max(0.0, 1.0 + v / scale)


def clamp01(v):
    return max(0.0, min(1.0, v))


def realized_annual(town, turns):
    """Run one town forward, return realized annual %.

    Single-town only (all trajectory scenarios isolate the subject;
    company, if any, is built into the World's other towns and read via
    nets(), never by index). Death reports -100%."""
    w = World()
    w.towns.append(T(town.x, town.y, town.population, town.faction))
    p0 = town.population
    G.step(w, turns)
    if not w.towns or w.towns[0].population <= 0:
        return -100.0
    return ((w.towns[0].population / p0) ** (TURNS_PER_YEAR / turns) - 1.0) * 100.0


# --- scenarios ----------------------------------------------------------

def s1_village_rate():
    """Lone villages (300, 1000 — self-feeding sizes) over 10 years:
    natural increase must look agrarian, 0.1-0.5%/yr."""
    lo, hi = REF["longrun_growth_pct_per_yr"]["lo"], REF["longrun_growth_pct_per_yr"]["hi"]
    rates = [realized_annual(T(500, 500, p), 520) for p in (300, 1000)]
    s = sum(band(r, lo, hi, log=True) for r in rates) / 2
    return ("village_rate", "10y annual % @300,@1000",
            f"{rates[0]:.2f},{rates[1]:.2f}", f"[{lo},{hi}]", s,
            "isolated calibration lives ONLY at self-feeding sizes")


def s2_recovery():
    """Halved 5k town with intact hinterland (6x500 @30km) regrows to
    10k on a post-plague timescale, 40-150y. Ring at 500 (not 300:
    trajectory company below the death floor dies on turn 1 and the
    scenario silently degrades to lone recovery — 500 is the largest
    honest village until viability extends downward)."""
    lo, hi = REF["plague_halving_recovery_yr"]["lo"], REF["plague_halving_recovery_yr"]["hi"]
    ring = [(500 + 30 * math.cos(i * math.pi / 3), 500 + 30 * math.sin(i * math.pi / 3))
            for i in range(6)]
    towns = [T(500, 500, 5000)] + [T(x, y, 500) for x, y in ring]
    w = World()
    for t in towns:
        w.towns.append(T(t.x, t.y, t.population))
    turns = None
    for i in range(1, 15001):
        G.step(w, 1)
        if w.towns and w.towns[0].population >= 10000.0:
            turns = i
            break
    yrs = turns / TURNS_PER_YEAR if turns else float("inf")
    s = band(yrs, lo, hi) if turns else 0.0
    return ("recovery", "5k->10k yr (ringed)", f"{yrs:.1f}" if turns else ">288",
            f"[{lo},{hi}]", s, f"{turns} turns" if turns else "never")


def s3_viability():
    """Hamlets at 200/400/500 left alone a year: fraction that persist."""
    alive = 0
    pops = {}
    for p0 in (200, 400, 500):
        w = World()
        w.towns.append(T(500, 500, p0))
        G.step(w, TURNS_PER_YEAR)
        if w.towns:
            alive += 1
            pops[p0] = round(w.towns[0].population, 1)
        else:
            pops[p0] = None
    return ("viability", "alive after 52t", str(alive) + "/3", "3/3",
            alive / 3, f"{pops} (death {G.death_threshold})")


def s4_infill():
    """One 500 village midway between two 40k towns @150km: system total
    must rise by up to its free growth (full marks = zero crowding tax)."""
    base = [T(0, 0, 40000), T(150, 0, 40000)]
    with_v = [T(0, 0, 40000), T(150, 0, 40000), T(75, 0, 500)]
    d = sum(G.nets(with_v)) - sum(G.nets(base))
    free = G.isolated(500)
    s = clamp01(d / free) if free > 0 else 0.0
    return ("infill", "delta vs free gain", f"{d:+.2f}/{free:.2f}", "> 0", s,
            "farmed gaps must pay")


def s5_hierarchy():
    """Same people, same 4 sites (150km square): 34k+3x2k roof vs 4x10k
    uniform. Score = ratio to parity (hierarchical competitive = 1)."""
    pos = [(0, 0), (150, 0), (0, 150), (150, 150)]
    tu = sum(G.nets([T(x, y, 10000) for x, y in pos]))
    th = sum(G.nets([T(x, y, p) for (x, y), p in zip(pos, (34000, 2000, 2000, 2000))]))
    r = th / tu if tu > 0 else 0.0
    return ("hierarchy", "hier/uniform total", f"{r:.3f}", "1.0", clamp01(r),
            f"uniform={tu:.2f} hier={th:.2f}")


def s6_market_penalty():
    """Two 10k towns 15km apart: coexistence penalty over one neighbor."""
    towns = [T(0, 0, 10000), T(15, 0, 10000)]
    p = 1.0 - G.nets(towns)[0] / G.isolated(10000.0)
    cap = REF["market_penalty_at_spacing_max_frac"]
    s = 1.0 if p <= cap else max(0.0, 1.0 - (p - cap) / 0.5)
    p50 = 1.0 - G.nets([T(0, 0, 10000), T(50, 0, 10000)])[0] / G.isolated(10000.0)
    return ("market_penalty", "penalty @15km (@50km)", f"{p:.2f} ({p50:.2f})",
            f"<= {cap}", s, "market lattice must coexist")


def _macro_layouts():
    """Archetypes on a 100x100km tile, each 300k (30/km2). H: 784x250
    vill @3.6km + 25x2800 mkt @17.9km (cell centers) + 4x8500 reg @50km.
    U-big/U-mid/V uniform at 30k/2.5k/250. Deterministic."""
    VS = 3.57
    vill = [(1.8 + VS * i, 1.8 + VS * j, 250) for i in range(28) for j in range(28)]
    mkt = [(1.8 + VS * (2.5 + 5 * k), 1.8 + VS * (2.5 + 5 * m), 2800)
           for k in range(5) for m in range(5)]
    rc = [1.8 + VS * 4.5, 1.8 + VS * 18.5]
    reg = [(x, y, 8500) for x in rc for y in rc]
    pts = [(x, y) for x, y, _ in vill + mkt + reg]
    md = min(math.hypot(ax - bx, ay - by)
             for i, (ax, ay) in enumerate(pts) for bx, by in pts[i + 1:])
    assert md > 2.0, f"H-tile fixture collision: min pairwise {md:.4f}km"
    specs = {"H": vill + mkt + reg,
             "U-big": [(12.5 + 25 * i, 16.7 + 25 * j, 30000)
                       for i in range(4) for j in range(3)][:10],
             "U-mid": [(4.5 + 9.09 * i, 4.5 + 9.09 * j, 2500)
                       for i in range(11) for j in range(11)][:120],
             "V": [(1.25 + 2.5 * i, 1.67 + 3.33 * j, 250)
                   for i in range(40) for j in range(30)]}
    for spec in specs.values():
        assert sum(p for _, _, p in spec) == 300000
    return {k: [T(x, y, p) for x, y, p in spec] for k, spec in specs.items()}


def s7_sustain():
    """Reference tile: each tier's mean net >= 0 (villages AND markets
    AND regionals viable at 30/km2). Score = mean of tier sub-scores."""
    towns = _macro_layouts()["H"]
    nets = G.nets(towns)
    tiers = {"vill": (nets[:784], 784 * G.isolated(250)),
             "mkt": (nets[784:809], 25 * G.isolated(2800)),
             "reg": (nets[809:], 4 * G.isolated(8500))}
    ss = {}
    for k, (ns, free) in tiers.items():
        tot = sum(ns)
        ss[k] = onesided(tot, abs(free)) if free > 0 else (1.0 if tot >= 0 else 0.0)
    s = sum(ss.values()) / 3
    det = " + ".join(f"{k} {sum(nets if False else v[0]):+.0f}" for k, v in tiers.items())
    return ("sustain", "tier viability (vill/mkt/reg)", "/".join(f"{v:.0f}" for v in ss.values()),
            "1/1/1", s, det)


def s8_urban():
    """Lone cities at 20k/40k/80k over 10y: natural change must be <= 0
    at every size above self-feeding (town growth comes from migration,
    never from lone increase). Score = mean over sizes."""
    rates = [realized_annual(T(500, 500, p), 520) for p in (20000, 40000, 80000)]
    ss = [onesided(-r, 1.0) for r in rates]
    return ("urban", "10y natural % @20k,@40k,@80k",
            ",".join(f"{r:+.2f}" for r in rates), "<= 0 each",
            sum(ss) / 3, "graded graveyard: no size grows on its own")


def s9_gapfill():
    """41-town uniform optimum + 40 infill villages: system total must
    rise by up to the villages' free growth."""
    pts = []
    for i in range(6):
        for j in range(6):
            pts.append((50 + 150 * i, 50 + 150 * j))
    for j in range(5):
        pts.append((950, 50 + 150 * j))
    base = [T(x, y, 42000) for x, y in pts]
    full = list(base) + [T(x + 75, y, 500) for x, y in pts[:40]]
    d = sum(G.nets(full)) - sum(G.nets(base))
    free = 40 * G.isolated(500)
    s = clamp01(d / free) if free > 0 else 0.0
    return ("gapfill", "delta vs free gain", f"{d:+.0f}/{free:.0f}", "> 0", s,
            "econ-direct (bypasses BUILD 10km rule)")


def s10_sinkflow():
    """60k city ringed by 6x300 @30km: SINK (city's lone rate <= 0),
    FUEL (ringed city beats its lone rate), SHARE (villages pay),
    BOOKS (system within 25% of isolated sum). Mean of four."""
    rc = realized_annual(T(500, 500, 60000), 520)
    sink = onesided(-rc, 1.0)
    city, vill = 60000.0, 300.0
    ring = [T(500 + 30 * math.cos(i * math.pi / 3),
              500 + 30 * math.sin(i * math.pi / 3), vill) for i in range(6)]
    town_c = T(500, 500, city)
    coupled = G.nets([town_c] + ring)
    c_iso, v_iso = G.isolated(city), G.isolated(vill)
    c_cpl, v_cpl = coupled[0], sum(coupled[1:]) / 6
    fuel = clamp01(c_cpl / c_iso) if c_iso > 0 else (1.0 if c_cpl > 0 else 0.0)
    share = clamp01((v_iso - v_cpl) / v_iso) if v_iso > 0 else 0.0
    tot_iso, tot_cpl = c_iso + 6 * v_iso, sum(coupled)
    dev = abs(tot_cpl - tot_iso) / abs(tot_iso) if tot_iso else 1.0
    books = 1.0 if dev <= 0.25 else max(0.0, 1.0 - (dev - 0.25) / 0.5)
    s = (sink + fuel + share + books) / 4
    return ("sinkflow", "sink/fuel/share/books",
            "/".join(f"{v:.2f}" for v in (sink, fuel, share, books)),
            "1/1/1/1", s, f"city lone {rc:+.2f}%/yr; ringed {c_cpl:.1f}/{c_iso:.1f}")


def s11_access():
    """6x300 ring @10km with vs without a central 2500 market: ring must
    grow >= 1.05x better with the market (access bonus)."""
    need = REF["market_access_ratio"]["lo"]
    ring = [(10 * math.cos(i * math.pi / 3), 10 * math.sin(i * math.pi / 3))
            for i in range(6)]
    base = [T(x, y, 300) for x, y in ring]
    withm = [T(x, y, 300) for x, y in ring] + [T(0, 0, 2500)]
    m0 = sum(G.nets(base)) / 6
    m1 = sum(G.nets(withm)[:6]) / 6
    r = m1 / m0 if m0 > 0 else 0.0
    s = clamp01((r - 1) / (need - 1)) if need > 1 else (1.0 if r >= 1 else 0.0)
    return ("access", "ring w/ vs w/o market", f"{r:.3f}", f">= {need}", s,
            f"with {m1:.3f}/turn vs without {m0:.3f}/turn")


def s12_returns():
    """Town+hinterland systems doubled at fixed sites, swept across
    sizes (0.5k->1k through 4k->8k centers, villages scaled with): the
    best scale must more than double total (thresholds live somewhere
    in 0.5-8k; the sweep finds them without presuming where)."""
    best, det = 0.0, []
    for c, v in ((500, 150), (1000, 200), (2000, 400), (4000, 800)):
        pts = [(0, 0), (15, 0), (-15, 0), (0, 15), (0, -15)]
        A = [T(x, y, c if i == 0 else v) for i, (x, y) in enumerate(pts)]
        B = [T(x, y, 2 * c if i == 0 else 2 * v) for i, (x, y) in enumerate(pts)]
        ta, tb = sum(G.nets(A)), sum(G.nets(B))
        r = (tb / ta) / 2 if ta > 0 else 0.0
        best = max(best, r)
        det.append(f"{c}:{r:.2f}")
    return ("returns", "best doubled ratio/2", f"{best:.3f}", ">= 1",
            clamp01(best), ", ".join(det))


def s15_region():
    """6x2500 ring @30km with vs without a central 8500 regional:
    the access mirror one tier up (markets need regionals like villages
    need markets). Same ring-vs-ring control as s11. Radius 30km (not
    20): the control ring must be viable alone (+0.19/turn vs iso 2.44),
    else the comparison fires into an already-dead regime."""
    need = REF["market_access_ratio"]["lo"]
    ring = [(30 * math.cos(i * math.pi / 3), 30 * math.sin(i * math.pi / 3))
            for i in range(6)]
    base = [T(x, y, 2500) for x, y in ring]
    withr = [T(x, y, 2500) for x, y in ring] + [T(0, 0, 8500)]
    m0 = sum(G.nets(base)) / 6
    m1 = sum(G.nets(withr)[:6]) / 6
    r = m1 / m0 if m0 > 0 else 0.0
    s = clamp01((r - 1) / (need - 1)) if need > 1 else (1.0 if r >= 1 else 0.0)
    return ("region", "ring w/ vs w/o regional", f"{r:.3f}", f">= {need}", s,
            f"with {m1:.3f}/turn vs without {m0:.3f}/turn")


def s13_macro():
    """Four archetypes, equal pop + area: hierarchical tile must rank
    first AND sustain itself. Rank = archetypes beaten/3."""
    L = _macro_layouts()
    tots = {k: sum(G.nets(v)) for k, v in L.items()}
    beaten = sum(1 for k in ("U-big", "U-mid", "V") if tots["H"] > tots[k])
    rank = beaten / 3
    sust = onesided(tots["H"], 300.0)  # scale ~0.1%/turn of 300k
    s = (rank + sust) / 2
    val = ",".join(f"{k} {tots[k] / 1000:+.0f}k" for k in ("H", "U-big", "U-mid", "V"))
    return ("macro", "H,U-big,U-mid,V totals", val, "H first, H>=0", s,
            f"RANK {beaten}/3 SUST {sust:.2f}; H top/avg 23x (construction)")


def s14_hinterland():
    """Lone 10k town over 10y must shrink (no farmland, no town);
    the same town ringed by 8x300 @25km must grow. Mean of both."""
    lone = realized_annual(T(500, 500, 10000), 520)
    starve = onesided(-lone, 1.0)
    ring = [T(500 + 25 * math.cos(i * math.pi / 4),
              500 + 25 * math.sin(i * math.pi / 4), 300) for i in range(8)]
    towns = [T(500, 500, 10000)] + ring
    c_cpl = G.nets(towns)[0]
    c_iso = G.isolated(10000.0)
    fed = clamp01(c_cpl / c_iso) if c_iso > 0 else (1.0 if c_cpl > 0 else 0.0)
    return ("hinterland", "lone % / ringed frac", f"{lone:+.2f}%/{fed:.2f}",
            "<=0 / 1", (starve + fed) / 2,
            "towns above self-feeding size eat; villages feed")


def p1_perf():
    """500-town batch ms + counted params: the speed/simplicity ceiling."""
    rng = __import__("random").Random(7)
    towns = [T(rng.uniform(0, 1000), rng.uniform(0, 1000),
               rng.choice([500, 2000, 10000, 4000 * 10])) for _ in range(500)]
    ts = []
    for _ in range(3):
        t0 = time.perf_counter()
        G.nets(towns)
        ts.append((time.perf_counter() - t0) * 1000)
    ms = min(ts)
    sms = 1.0 if ms < 10.0 else max(0.0, 1.0 - (ms - 10.0) / 20.0)
    sps = 1.0 if G.nparams <= 5 else max(0.0, 1.0 - (G.nparams - 5) / 5.0)
    return ("perf", "batch ms; params", f"{min(ts):.2f}; {G.nparams}",
            "< 10; <= 5", min(sms, sps), f"{G.describe()} hot path")


SCENARIOS = [s1_village_rate, s2_recovery, s3_viability, s4_infill,
             s5_hierarchy, s6_market_penalty, s7_sustain, s8_urban,
             s9_gapfill, s10_sinkflow, s11_access, s12_returns,
             s13_macro, s14_hinterland, s15_region, p1_perf]


def main(argv):
    global G
    toks = argv[1:]
    sysname = "engine"
    rest = []
    skip = False
    for i, a in enumerate(toks):
        if skip:
            skip = False
            continue
        if a.startswith("--system="):
            sysname = a.split("=", 1)[1]
        elif a == "--system" and i + 1 < len(toks):
            sysname, skip = toks[i + 1], True
        else:
            rest.append(a)
    want = [a for a in rest if not a.startswith("-")]
    as_json = "--json" in argv
    if sysname not in SYSTEMS:
        print(f"unknown system {sysname!r} (have: {sorted(SYSTEMS)})")
        return 2
    G = SYSTEMS[sysname]
    print(f"system: {G.describe()}")
    rows = []
    for fn in SCENARIOS:
        name = fn.__name__.split("_", 1)[1]
        if want and name not in want and fn.__name__ not in want:
            continue
        rows.append((name,) + fn()[1:])
    w = 15
    print(f"{'SCENARIO':<{w}} {'METRIC':<26} {'VALUE':<22} {'TARGET':<14} SCORE")
    for name, metric, val, tgt, s, _ in rows:
        print(f"{name:<{w}} {metric:<26} {val:<22} {tgt:<14} {s * 100:5.1f}")
    print("--- detail ---")
    for name, _, _, _, _, det in rows:
        print(f"{name}: {det}")
    comp = sum(r[4] for r in rows) / len(rows) if rows else 0.0
    print(f"== composite {comp * 100:.1f}/100 over {len(rows)} scenarios ==")
    if as_json:
        print(json.dumps({"system": G.describe(), "composite": comp,
                          "scenarios": [{"scenario": n, "metric": m, "value": v,
                                         "target": t, "score": o, "detail": d}
                                        for n, m, v, t, o, d in rows]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
