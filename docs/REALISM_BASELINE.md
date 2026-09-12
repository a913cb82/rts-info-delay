# Realism baseline — current engine scored (2026-09-12)

Harness: `benchmarks/growth_realism.py` + `benchmarks/realism_ref.json`.
Engine: `experiment/realistic-growth` @ `a5f47b5` (econ identical to `main`).
Calendar: 1 turn = 1 week. Runtime: **1.5s** (numba import included).

## Score: 2/11 PASS (expected-red baseline)

| check | value | target | verdict |
|---|---|---|---|
| growth_rate (annual % @2k,10k) | 5.10, 4.68 | [0.1, 0.5] | FAIL |
| recovery (5k→10k) | 14.4 yr (748t) | [40, 150] | FAIL |
| viability (200/400/500 after 52t) | dead/dead/526 | all alive | FAIL |
| infill (village delta/turn) | −2.33 | > 0 | FAIL |
| hierarchy (hier/uniform) | 0.900 | ≥ 0.900 | PASS (borderline) |
| market_penalty (@15km,@50km) | 0.72, 0.28 | @15 ≤ 0.25 | FAIL |
| density (pop/km², cap-max) | 1.72 (4.1) | [20, 40] | FAIL |
| urban (extra big-city penalty) | 0.000 | ≥ 0.10 | FAIL |
| sinkflow (sink%; city; vill; tot) | +1.04%; 10.1/24.0; 0.15/0.30; 11.0/25.8 | ≤0; cpl>iso; cpl<iso; ±25% | FAIL |
| gapfill (infill Δ; top/avg) | −89.8; 1.9× | > 0; ≥ 5× | FAIL |
| perf (500-town ms; params) | 1.16; 5 | < 10; ≤ 5 | PASS |

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
- **No urban graveyard.** Isolated 80k per-capita growth is exactly the
  logistic prediction (extra penalty 0.000 vs ≥0.10): big cities pay no
  disease/fuel cost beyond the shared curve.
- **Density ceiling is structural.** Filled optimum 1.7/km², cap-max
  4.1/km², vs 20–40 historical. No parameter tweak inside
  `r/K/crowding` reaches the target while keeping towns ≤100k on a
  1M-km² map — the bottom tier (villages) is missing, not mis-tuned.
- **The sink has no circuit.** `sinkflow` fails 3 of 4 sub-asserts: an
  isolated 80k town still grows (+1.04%/yr) instead of shrinking; a
  ringed 60k city nets 10.1 vs 24.0 isolated (neighbours only hurt —
  nothing flows in); system total collapses 25.8→11.0 (−57%) instead
  of redistributing within ±25%. (SHARE passes spuriously: crowding
  suppresses villages with the same sign as exporting.) The bench
  demands the full de Vries circuit — sink + fuel + share + books —
  deliberately API-agnostic: whatever mechanics land, trajectories
  through the economy phase must show it.
- **hierarchy 0.900 is a borderline PASS, not a win.** Threshold was set
  pre-run; uniform still beats hierarchical roofs by 11% at fixed sites,
  and gapfill shows the hierarchy that matters (dense smalls) failing
  hard. Treating this as pass-with-asterisk.

## Frozen

Thresholds in-harness + ranges in `realism_ref.json` are now frozen;
future mechanics are scored by them, not fitted to them. Perf guardrail
(1.16ms, 5 params) binds any proposal.

## Next (needs user approval before implementing)

Mechanics candidates, in suggested order: (1) demographic-time growth
(slower `r`, recalibrated to %/yr); (2) village viability (lower death
floor / small-town growth shape); (3) crowding radius + infill sign
(the hierarchy fix — biggest design surface); (4) urban graveyard term;
(5) BUILD 10km exemption + 1km grid (approved queue, plan §3).
No proposal touches bots until its engine-direct score moves.
