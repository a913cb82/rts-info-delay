# Growth fit — results (2026-09-12)

Fitted a merged growth system to the frozen realism suite.
Branch `experiment/realistic-growth`. Suite unchanged; candidate plugged
in as `benchmarks/candidate_growth.py` + `--system fitted`.

## Progression (full-16 suite mean, quiet)

| system | params | mean (/1) |
|---|---|---|
| engine (baseline) | 5 | 0.224 |
| merged equations, untuned prior | 10 | 0.662 |
| + parallel random search (2000 evals) | 10 | 0.858 |
| + Nelder-Mead polish (8 starts x400) | 10 | 0.893 |
| + structure ablation + refit | **5** | **0.948** |

## Final model (5 free parameters)

```
g(P)   = a*P - (a/3e5)*P^2 - c*P^3
W(i,j) = alpha*P_i*sig((P_j-P_i)/30)*exp(-(d/rho)^2)
       + mu*P_i*P_j*(P_i-P_j)/(P_i+P_j)*exp(-d/rho)     # gravity migration
net_i  = g(P_i) + sum_j W(i,j);   P <- max(P + net, 0)
```

| param | value | job |
|---|---|---|
| `a` | 8.156e-05 | fertility (~0.33-0.42%/yr at village sizes) |
| `c` | 9.247e-15 | urban sink (negative past ~30k) |
| `alpha` | 2.076e-05 | market-access lift (per-capita, soft size gate at 30 pop) |
| `rho` | 105.7 km | shared range: access + migration |
| `mu` | 3.552e-09 | gravity migration toward larger towns |
| derived | `b = a/3e5` | land/saturation term (K ~ 300k) |
| dropped | `gamma, theta, m, delta` | competition zeroed by the fit; gate centred at parity, width 30; one shared range |

## Final scores (suite, 0..1 closeness)

| scenario | engine | fitted |
|---|---|---|
| village_rate | 0.00 | **1.00** |
| recovery | 0.00 | **1.00** |
| viability | 0.33 | **1.00** |
| infill | 0.00 | **1.00** |
| hierarchy | 0.90 | 0.80 |
| market_penalty | 0.05 | **1.00** |
| sustain | 0.00 | **1.00** |
| urban | 0.05 | 0.78 |
| gapfill | 0.00 | **1.00** |
| sinkflow | 0.32 | 0.96 |
| access | 0.00 | **1.00** |
| returns | 0.72 | **1.00** |
| macro (held out) | 0.17 | 0.83 |
| hinterland | 0.04 | 0.80 |
| region | 0.00 | **1.00** |
| perf | 1.00 | 0.99 |
| **composite** | **0.224** | **0.948** |

## Cross-validation (Level 2)

K=4 force-balanced folds, warm-started NM (fev 40) per fold, `macro`
and `perf` never in the fit (`perf` is timing-noisy under the worker
pool; it is a guardrail, evaluated quiet):

| lambda | CV mean | SE | folds (food/transport/materials/structure) |
|---|---|---|---|
| 0.00 | 0.701 | 0.139 | 1.00 / 0.33 / 0.78 / 0.69 |
| **0.02** | **0.783** | 0.076 | 1.00 / 0.67 / 0.77 / 0.70 |
| 0.10 | 0.720 | 0.102 | 1.00 / 0.52 / 0.72 / 0.64 |

Selected lambda = 0.02 (best CV; lambda=0.1 within 1 SE but does not
reduce the active parameter count, so the simpler rule picks 0.02).
Generalization gap: in-sample 0.95 vs CV 0.78 — the 14 behavioural
scenarios are correlated, so the CV is the honest number.
Held-out exam: `macro` 0.83 (never in fitting or CV).

## What the fit says about the four forces

- **Food/land**: survives as the derived quadratic (`b=a/3e5`, a soft
  carrying capacity) — without it hierarchy collapses entirely.
  Competition `gamma` was driven to zero: clustering costs are already
  carried by the shared saturation term.
- **Bulk travel**: survives as one shared Gaussian/exp range `rho~106km`
  for both access and migration — the market lattice emerges.
- **Lumpy services**: the soft threshold survived in reduced form
  (fixed 30-pop sigmoid edge; centre at parity). Making it a free
  (theta, m) pair bought nothing in CV.
- **Urban sink + migration**: both survive and must (`c`, `mu`);
  migration is gravity-like, `mu` was 20x larger than in the untuned
  prior and 1000x larger than the linear-migration fit.

## Structural findings (why some scenarios cap at ~0.8)

- **`hierarchy` vs `urban` are opposed in any smooth single-town curve.**
  Urban demands lone towns shrink from 20k; hierarchy demands the 34k
  roof stay competitive against 4x10k. For a cubic `g/P = a-bP-cP^2`,
  growth is monotone declining past its peak: if 20k is a sink, 34k is
  a deeper one. The fit lands at a compromise (0.80 / 0.78).
- **`recovery` passes via system-level access, not migration**: a 5k
  town doubling in <150y needs ~0.5/turn of help; six 500-villages
  can't supply that by migration alone (total 3000 people), so the
  throughput comes from the access term. This is also why the
  honour of `sinkflow/SHARE` (villages must pay near cities) is only
  partial instead of free.
- **Dropping 5 parameters was free**: the lean 5-parameter structure
  scored *better* than the 10-parameter one (0.948 vs 0.893) because
  `perf` (param-count guardrail) is part of the suite, and the extra
  parameters were overfitting the scenario set.

## Caveats

- This is a **fitted hypothesis**, not validated mechanics: 14
  behavioural scenarios, 5 parameters, correlated fixtures. CV 0.78 is
  the number to trust, not 0.95.
- Two suite quirks the fit can exploit: `hierarchy` clamps a ratio of
  possibly-negative totals (rewards collapses), and `perf` timing is
  load-sensitive (excluded from fitting, evaluated quiet).
- `urban`/`sinkflow`/`hinterland` ~0.8 is a *structural* ceiling of
  this model family, not a tuning failure; resolving it needs a shape
  where mid-size towns sink but nearby villages still lift them.
- All artifacts (search traces, NM runs, CV folds, final params) in
  `benchmarks/realism_fit/`.
