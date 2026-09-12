# Realism baseline — current engine scored (2026-09-12)

Harness: `benchmarks/growth_realism.py` (15 scenarios, pure integration —
setup → run → observe → closeness score 0..1, composite = mean) +
`benchmarks/realism_ref.json` (bands) + `benchmarks/growth_systems.py`
(`--system NAME` plugs candidates; suite file never edited to pass).
Engine: `experiment/realistic-growth` (econ identical to `main`).
Calendar: 1 turn = 1 week. Runtime ~6s wall (checks ~1s; rest shared
numpy/numba import + the 15k-turn recovery cap loop).

## Score: composite 22.7/100 (expected-red baseline, suite v3)

| scenario | value | target | score |
|---|---|---|---|
| village_rate (@300,@1000) | −100.00, 5.26 | [0.1, 0.5] | 0.0 |
| recovery (ringed 5k→10k) | never (>288y) | [40, 150] | 0.0 |
| viability | 1/3 | 3/3 | 33.3 |
| infill | −2.33/0.50 | > 0 | 0.0 |
| hierarchy | 0.900 | 1.0 | 90.0 |
| market_penalty (@15/@50km) | 0.72 (0.28) | ≤ 0.25 | 5.4 |
| sustain (vill/mkt/reg) | 0/0/0 | 1/1/1 | 0.0 |
| urban (@80k 10y) | +0.85 | ≤ 0 | 15.0 |
| gapfill | −90/20 | > 0 | 0.0 |
| sinkflow (s/f/sh/b) | 0.00/0.42/0.50/0.35 | 1/1/1/1 | 31.8 |
| access | −4.038 | ≥ 1.05 | 0.0 |
| returns (coupled) | 0.444 | ≥ 1 | 44.4 |
| macro (H,U-b,U-m,V) | H −19k,−1k,−6k,−28k | H first, H≥0 | 16.7 |
| hinterland (lone/fed) | +4.64%/0.09 | ≤0 / 1 | 4.4 |
| perf | 0.93ms; 5 | < 10; ≤ 5 | 100.0 |

## What the numbers say

- **Hinterland is the headline.** Lone 10k grows +4.64%/yr (must shrink:
  no farmland, no town); the ringed recovery *never happens* — with its
  hinterland present the town stalls below 10k, i.e. farmed neighbours
  prevent regrowth, the exact inverse of reality. `hinterland` 4.4.
- **Villages can't be subjects.** `village_rate`'s 300 half reports
  −100%: the patient dies on day one (floor 500), so natural increase
  is unmeasurable where it matters most. Trajectory company below the
  floor dies turn 1 (caught live: first `recovery` draft read lone-like
  749t) — scenario fixtures now use ≥500 company, documented in-code.
- **Density ceiling restated as ranking.** Every macro archetype is
  negative at 30/km²; H (−19k) loses to uniform-big (−1k). A cap-lift
  sustains but still ranks uniform first — the discrimination holds.
- **Partial credit lands where it's honest.** `hierarchy` 90 (uniform
  wins by 11%, not 11×), `returns` 44 (coupled doubling keeps 44% of
  parity), `sinkflow` 32 (SHARE/FUEL/BOOKS partial, SINK zero),
  `urban` 15 (near-zero, wrong sign). The suite's
  best current behaviors are all "less bad," none good.
- **Perf untouched.** 0.93ms / 5 params — binds every proposal.

## Standing rules (suite v3 contract)

- Scenarios assert behavior; isolated towns only at self-feeding sizes.
- Scores are closeness (bands fall off log- or linear-distance, one-sided
  defeats scale to the free-growth stakes); no binary verdicts.
- Ref ranges frozen; new mechanics = new `--system`, never suite edits.
- Deferred (need ontologies): shock insurance, catchment areas,
  service co-location, water trade — see plan.
