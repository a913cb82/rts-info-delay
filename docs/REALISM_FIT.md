# Growth fit — results (2026-09-12)

Fitted a merged growth system to the frozen realism suite, with a
**hard 150 km interaction bound** (game requirement + engine
efficiency) and **all parameters at 2 significant figures**.
Branch `experiment/realistic-growth`. Suite unchanged; candidate
plugged in as `benchmarks/candidate_growth.py` (`--system fitted`).

## Final model (5 free parameters, all 2 s.f.)

```
g(P)   = a*P - (a/3e5)*P^2 - c*P^3
W(i,j) = [ alpha*P_i*sig((P_j-P_i)/30)
         + mu*P_i*P_j*(P_i-P_j)/(P_i+P_j)*e^(-d/rho) ] * win(d)
net_i  = g(P_i) + sum_j W(i,j);   P <- max(P + net, 0)

win(d) = 1                         d <= 120 km
       = smoothstep taper         120 < d < 150 km
       = 0                        d >= 150 km   (HARD BOUND)
```

| param | value | job |
|---|---|---|
| `a` | 8.2e-05 | fertility (~0.35-0.4%/yr at village sizes) |
| `c` | 1.0e-14 | urban sink (net negative past ~30k) |
| `alpha` | 1.8e-05 | market access (per-capita, direction gate at parity, width 30) |
| `rho` | 2.7e+02 km | shared range: Gaussian access, exponential migration |
| `mu` | 2.7e-09 | gravity migration toward larger towns |
| derived | `b = a/3e5` | land/saturation (K = 300k) |

Hard bound: pairs at 160 km are **exactly** inert (verified: nets at
160 km equal isolated nets bit-for-bit). The taper means a pair at
exactly 150 km contributes 0, engine-style `d <= 150` pairs at 149 km
contribute at ~13% (access) / ~5% (migration) of their near value with
zero derivative at the edge — no kink.

## Progression (full-16 suite mean, quiet)

| system | params | mean (/1) |
|---|---|---|
| engine (baseline) | 5 | 0.224 |
| merged equations, untuned prior | 10 | 0.662 |
| + random search + NM (unbounded) | 10 | 0.893 |
| + structure ablation/refit | 5 | 0.948 |
| + hard 150 km bound + local refit | 5 | 0.950 |
| + **2-s.f. quantisation** (+lattice descent) | 5 | **0.949** |

## Final scores (suite, 0..1 closeness)

| scenario | engine | fitted |
|---|---|---|
| village_rate | 0.00 | **1.00** |
| recovery | 0.00 | **1.00** |
| viability | 0.33 | **1.00** |
| infill | 0.00 | **1.00** |
| hierarchy | 0.90 | 0.82 |
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
| perf | 1.00 | **1.00** (1.2 ms, 5 params) |
| **composite** | **0.224** | **0.949** |

## Choices investigated (this round)

- **Hard bound cost nothing.** Evaluating the pre-bound fit with the
  window applied: composite 0.9500 (from 0.9478) — the taper clipped
  only weak tails; the `hierarchy` fixture (150 km) even improved as
  the refit raised `rho` (105 → 270 km) to flatten the interior.
- **Sigma width (`m=30`) is unidentifiable in this suite.** Sweep on
  the bound-refit: m = 10/20/30/50/100/200/500 gave
  0.9540/0.9540/0.9540/0.9539/0.9539/0.9537/0.9533 (train mean), and
  freeing the centre (`theta` 0-1000) never beat 0.953. Kept 30, now
  with evidence rather than assumption.
- **2 significant figures cost ~0.0003 and diens recovered it.** Full
  quantisation 0.9537; lattice descent (last-digit steps) 0.9541 vs
  0.9540 continuous. Quantisation is therefore free regularisation
  here, not a trade.
- **Lambda/1-SE.** CV with the final structure: lambda = 0.02 → 0.792
  (SE 0.078); lambda = 0.1 → 0.787 (SE 0.080). Within 1 SE and same
  parameter count; 0.02 kept by the point estimate.

## Cross-validation (Level 2)

K=4 force-balanced folds, warm-started NM (fev 40) per fold; `macro`
and `perf` never fitted (`perf` is timing-noisy under the pool):

| lambda | CV mean | SE | food / transport / materials / structure |
|---|---|---|---|
| 0.02 | **0.792** | 0.078 | 1.00 / 0.66 / 0.82 / 0.68 |
| 0.10 | 0.787 | 0.080 | 1.00 / 0.66 / 0.82 / 0.66 |

Generalisation gap: in-sample 0.95 vs CV 0.79 — the 14 behavioural
scenarios are correlated; **CV is the honest number**. Held-out exam:
`macro` 0.83 (never in fit or CV). `perf` 1.0 quiet.

## Structural findings

- **`hierarchy` vs `urban` are opposed in any smooth single-town curve**
  (`g/P = a-bP-cP^2` declines monotonically past its peak: if 20k is a
  sink, 34k is a deeper one). The fit lands at 0.82/0.78 — this family's
  ceiling, not a tuning miss.
- **`recovery` passes through system-level access, not migration**:
  six 500-villages hold only 3000 people, not enough to double a 5k
  town; the throughput is the access term.
- **`sinkflow/SHARE` (villages pay near cities) remains partial**: it
  fights the access term at city scale; net 0.96 via SINK/FUEL/BOOKS.

## Caveats

- Fitted hypothesis, not validated mechanics: 14 correlated scenarios,
  5 parameters. CV 0.79 is the number to trust.
- Suite quirks exploitable by a fit: `hierarchy` clamps a ratio of
  possibly-negative totals; `perf` timing is load-sensitive (kept out
  of fitting, evaluated quiet).
- `urban`/`hinterland` ~0.8 is structural for this family; resolving it
  needs a shape where mid-size towns sink *and* nearby villages lift
  them (a two-regime base curve, not a tuning change).
- Artifacts: `benchmarks/realism_fit/` (search trace, NM runs, sigma
  sweep, quantisation log, CV folds, final eval).
