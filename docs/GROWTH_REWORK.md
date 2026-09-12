# Growth rework (2026-09-12)

The town growth model was refitted for realism and ported into the
engine. This is the one doc for that work: what the model is, what it
does, and how to measure it. Fitting detail/artifacts live in
`benchmarks/realism_fit/`; the visual summary is
`docs/realism_plots/realism_fit.png`.

## The model

```
g(P)   = a*P - (a/K)*P^2 - c*P^3                 # a lone town
W(i,j) = alpha*P_i*sig((P_j-P_i)/gate) * e^(-(d/rho)^2) * win(d)
       + mu*P_i*P_j/(P_i+P_j)*(P_i-P_j) * e^(-d/rho) * win(d)
net_i  = g(P_i) + sum_j W(i,j)
win(d) = sig(D^2/d^2 - D^2/(D^2-d^2)),  D = info_speed = 150 km
```

| param | config field | value | job |
|---|---|---|---|
| `a` | `population_growth` | 8.2e-05 | fertility (~0.4%/yr villages) |
| `K` | `land_capacity` | 3e5 | saturation; quadratic term `a/K` |
| `c` | `urban_sink` | 1e-14 | urban mortality; net negative past ~78k |
| `alpha` | `access_alpha` | 1.8e-05 | market access (bigger serves smaller) |
| `rho` | `kernel_scale` | 270 | shared kernel decay scale |
| `mu` | `migration_mu` | 2.7e-09 | gravity migration toward larger towns |
| — | `service_gate` | 30 | sigmoid width of "meaningfully bigger" |
| — | `town_min_population` | 0 | death floor (die at pop <= 0) |

Conventions: 1 turn = 1 week; game km are real km. `win` is a single
C-infinity curve with one constant: exactly 1 at d=0, exactly 0 at
d=150, all derivatives vanish at the rim. Pairs at d >= 150 km are
inert (hard bound, also the engine's neighbour cutoff). The only
discontinuity kept is the exact-stack rule (d=0: smaller town dies,
larger ignores) — maps never stack, and it keeps viceroy founding
merging into a friendly town.

What it changed, qualitatively:

- **Slow demographic clock**: villages ~0.4%/yr (was ~5%/yr).
- **No crowding tax**: equal neighbours coexist; gaps can be farmed.
- **Directed access**: bigger places lift smaller ones (market halo).
- **Migration circuit**: people drift to bigger towns; a big city
  drains its neighbours (shadow near, halo further out) and is itself
  fed by villages.
- **Villages live**: the 500 floor is gone; 200-400 hamlets persist.

## How it scores

`benchmarks/growth_realism.py` (16 scenarios, closeness 0..1, composite
= mean; frozen thresholds; `--system engine|fitted`):

| | engine before | engine now |
|---|---|---|
| composite | 0.224 | **0.949** |

Held-out `macro` 0.83; held-out CV (leave-fold, λ=0.02) 0.79 — that is
the honest generalisation number, not the in-sample 0.95. Remaining
sub-scores: `hierarchy` 0.82, `urban` 0.78, `hinterland` 0.80,
`sinkflow` 0.96. `hierarchy` vs `urban` is a structural tension of the
single-town curve (if 20k sinks, 34k sinks deeper), not a tuning miss.

Reproduce: `python benchmarks/growth_realism.py --system engine`;
`python benchmarks/growth_realism.py --system fitted`;
`python benchmarks/realism_plots.py` (regenerates the PNG).

## Companion change: BUILD yield

Same rework, same turn: a trained army (cost 1000 pop) now converts at
90% instead of 50%. `build_efficiency` 0.5 → 0.9, so BUILD and
MOVE_CAPITAL found towns at **900** pop and boost an existing town by
**+900**. Capture is unchanged (still halves): it no longer shares the
field — it reads the new `capture_loss` 0.5. Bots that priced captures
via `build_efficiency` need to switch to `capture_loss` (bot agent).

## Engine notes

- `src/engine/economy.py` holds the model; numba batch/row kernels and
  the cached distance matrix keep the old performance shape.
- All maps carry the new parameters explicitly (old crowding keys are
  gone), so a game cannot silently fall back to old values.
- Bots are untouched: their 500-pop survive floor still reads the
  legacy `config.death_threshold` property (`army_cost × build_efficiency`),
  separate from the engine floor. Bot-side retuning (expansion pricing
  now reads the slow clock) is the bot agent's task; three bot tests
  still encode the old economy.
