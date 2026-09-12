# Realism baseline — current engine scored (2026-09-12)

Harness: `benchmarks/growth_realism.py` + `benchmarks/realism_ref.json`
+ `benchmarks/growth_systems.py` (generic `GrowthSystem` interface —
checks score `SYSTEMS["engine"]`, never engine internals directly).
Engine: `experiment/realistic-growth` (econ identical to `main`).
Calendar: 1 turn = 1 week. Runtime: **~2s wall** (~0.5s checks, rest the
shared numpy/numba import every bench pays).

## Score: 2/14 PASS (expected-red baseline, suite v2)

| check | value | target | verdict |
|---|---|---|---|
| growth_rate (annual % @2k,10k) | 5.10, 4.68 | [0.1, 0.5] | FAIL |
| recovery (5k→10k) | 14.4 yr (748t) | [40, 150] | FAIL |
| viability (200/400/500 after 52t) | dead/dead/526 | all alive | FAIL |
| infill (village delta/turn) | −2.33 | > 0 | FAIL |
| hierarchy (hier/uniform) | 0.900 | ≥ 0.900 | PASS (borderline) |
| market_penalty (@15km,@50km) | 0.72, 0.28 | @15 ≤ 0.25 | FAIL |
| sustain (min tier mean net) | reg −538.0 | ≥ 0 each | FAIL |
| urban (extra big-city penalty) | −0.000 | ≥ 0.10 | FAIL |
| gapfill (infill Δ) | −89.8 | > 0 | FAIL |
| sinkflow (sink%; city; vill; tot) | +1.04%; 10.1/24.0; 0.15/0.30; 11.0/25.8 | ≤0; cpl>iso; cpl<iso; ±25% | FAIL |
| access (ring vill w/ vs w/o market) | −4.038 | ≥ 1.05 | FAIL |
| returns (max net(2P)/2net(P)) | 0.990 | ≥ 1.000 | FAIL |
| macro (H,U-big,U-mid,V totals) | H −19k,U −1k,−6k,V −28k | H first, H≥0 | FAIL |
| perf (500-town ms; params) | 1.19; 5 | < 10; ≤ 5 | PASS |

## What the numbers say

- **Demographic time runs ~10× too fast.** Isolated growth 4.7–5.2%/yr
  vs 0.1–0.5 historical; plague-halving recovers in 14 years vs 40–150.
  The logistic `r=0.001/turn` is strategy-time, not population-time.
- **Villages cannot exist.** Death `<500` kills 200/400 outright; the
  `BUILD` 10km merge rule (noted in plan §3) separately forbids 3–4km
  packing even if they lived.
- **Infill is punished.** A 500-pop midpoint village (+0.5 own growth)
  costs its two 40k neighbours ~2.8 via crowding: net −2.33. At scale,
  40 villages on the 41-town optimum cost −89.8/turn. The model's
  answer to "farm the gaps" is "don't" — the core hierarchy failure.
- **Crowding radius is enormous.** One 10k neighbour at market spacing
  (15km) destroys 72% of growth; at 50km still 28%. Even the "optimal"
  150km lattice keeps only ~1/3 of isolated growth (315 vs 999/turn).
  Map never escapes interaction range.
- **No urban graveyard.** Isolated 80k matches the rural-trend
  extrapolation exactly (extra −0.000 vs ≥0.10): big cities pay no
  disease/fuel cost beyond the shared curve.
- **Benefit side absent.** `access` −4.04: a market at 10km drives ring
  villages to −0.060/turn vs +0.015 without it (needs ≥1.05×).
  `returns` 0.990: growth is concave at every tested size — no scale
  threshold anywhere.
- **Macro: wrong winner, nobody sustainable.** At equal pop (300k) on
  equal area (100×100km) the hierarchical tile (−19k) loses to
  uniform-big (−1k); every archetype is negative at 30/km². A bare
  cap-lift would sustain but still rank uniform first — the
  discrimination `macro` exists for. Per-tier: villages −15.9,
  markets −188.6, regionals −538.0 (graded collapse).
- **The sink has no circuit.** `sinkflow` fails 3 of 4 sub-asserts: an
  isolated 80k town still grows (+1.04%/yr) instead of shrinking; a
  ringed 60k city nets 10.1 vs 24.0 isolated (neighbours only hurt —
  nothing flows in); system total collapses 25.8→11.0 (−57%) instead
  of redistributing within ±25%. (SHARE passes spuriously: crowding
  suppresses villages with the same sign as exporting.) The bench
  demands the full de Vries circuit — sink + fuel + share + books —
  deliberately API-agnostic: whatever mechanics land, trajectories
  through `GrowthSystem.nets/step` must show it.
- **hierarchy 0.900 is a borderline PASS, not a win.** Threshold was set
  pre-run; uniform still beats hierarchical roofs by 11% at fixed sites,
  and gapfill shows the hierarchy that matters (dense smalls) failing
  hard. Treating this as pass-with-asterisk.
- **Retired constants (v1→v2).** Old `density` (41×42k → 1.72/km²,
  cap-max 4.1, vs 20–40) and old `gapfill` inequality half (top/avg
  1.9× vs ≥5×) scored frozen numbers from the previous optimum, not
  the candidate system — they could never move. Superseded by
  `sustain` (per-tier viability of the reference tile) and `macro`
  (ranking + H built Zipf 23× as a construction check). Fixture
  hygiene: H-tile asserts min pairwise separation >2.0km (caught a
  market/regional coincidence at (25,25) reading −95M through the
  1e-9 distance floor).

## Frozen

Thresholds in-harness + ranges in `realism_ref.json` are now frozen;
future systems are scored by them via `--system NAME`, not fitted to
them. Perf guardrail binds any proposal. Suite contract:
checks touch only `GrowthSystem.isolated/nets/step` (+Towns for
layout); new mechanics register in `growth_systems.py`, never edit
`growth_realism.py` to pass it.

## Next (needs user approval before implementing)

Mechanics candidates, in suggested order: (1) demographic-time growth
(slower `r`, recalibrated to %/yr); (2) village viability (lower death
floor / small-town growth shape); (3) crowding-radius/infill sign +
market-access bonus (the hierarchy fix — biggest design surface);
(4) urban graveyard + migration circuit; (5) BUILD 10km exemption +
1km grid (approved queue, plan §3). Threshold/lumpy services ride
with (3). No proposal touches bots until its engine-direct score moves.
