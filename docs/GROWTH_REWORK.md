# Growth rework (2026-09-13)

Town growth is now an **agrarian economy**: land- and labour-limited
farming, conservative food trade, food-limited births, surplus-labour
migration, and market services. This doc is the one place for the
model, the parameters (all real-world quantities) and the sanity
results. The earlier fitted realism model (2026-09-12, `a/K/c` +
access/migration kernels) is superseded; its suite still runs via
`benchmarks/growth_realism.py --system fitted` and the plot at
`docs/realism_plots/realism_fit.png`.

## Constants (geography / game)

| symbol | config | value | real-world meaning |
|---|---|---|---|
| `R` | `farm_radius_km` | 5 | farm walking radius — nobody farms further |
| `rho` | `rural_density` | 30 /km² | subsistence rural density (England/France c.1600) |
| `Lc` | `cart_distance_km` | 20 | distance over which carting doubles grain price |
| — | `turns_per_year` | 52 | 1 turn = 1 week |
| `sf` | `farm_workers_yield` | 1.3 | people fed per farm worker |
| `b` | `birth_rate` | 24 /1000/yr | net surviving births (gross 35 × ~0.7 infant survival) |
| `m` | `death_rate` | 31 /1000/yr | crude death rate (towns must overfeed ~21% to hold) |
| `mi` | `max_improvement` | 0.25 | max farm-output improvement from market access |
| `th` | `migration_share` | 0.005 /yr | share of total population that emigrates |
| `nu` | `surplus_mobility` | 0.05 /yr | share of surplus labour that emigrates |
| `Lm` | `migration_scale_km` | 50 | migration distance scale |
| `melt` | `melt_per_km` | 0.015 | freight loss per km (carriers eat, spoilage, tolls in kind); big receivers lose less (roads) |
| `p` | `starvation_elasticity` | 1.3 | deaths scale as (S/P)^−p (half rations kill ~2.5×) |
| — | `town_min_population` | **10** | minimum settlement size (die at or below) |

Derived: `Y_ring = rho·πR²` ≈ 2356 people (one ring's food) = `P_market` (the famous-or-not crew line, and the roads reference for melt). Break-even is S/P ≈ 1.21 (net births ÷ deaths).

## Formulae (per turn)

```
curves      win(d;D) = sig(D^2/d^2 - D^2/(D^2-d^2))     D = info_speed
            c(d)     = 2^(-d/Lc) in reach, 0 beyond 3·Lc (~60 km)

land        area_i = Voronoi cell within R (nearest-farmer, sampled)
serv_j  = max(0, P_j - Y_j/sf)                          non-farm population
offer_j = serv_j * (1 + last_j)                       resell last turn's gain
mkt_i   = sum_j offer_j * c(d_ij)                     one hop/turn, n-hop over n
improvement_i = mi * mkt_i/(mkt_i + P_i)              soft-capped at mi
Y_i     = (1 + improvement_i) * min(rho*area_i, sf*P_i) production

Resell state: each town carries last_improvement (what it received last
turn; cold start 0 = plain pairwise). One accumulation per turn, so
market richness hops once per turn and n-hop chains accrue over n
turns — bounded by the soft cap, zero new parameters. _step_core (a
turn) advances the state; nets_for/crowding_net (queries) snapshot and
restore it, so rate measurement stays side-effect-free.

trade       nearest pair first; while the donor is better fed per head,
            move food toward (lossy) pairwise equality; donors never drop
            below recipients; arrival = sent × exp(−tau·d),
            tau = melt·Pm/(Pm + P_recipient) (big importers have roads)
            S_i = Y_i + imports_i                       food commanded

births      B_i = b*P_i                                 fixed net births
deaths      D_i = m*P_i * (S_i/P_i)^−p                  food acts via deaths

migration   out_i   = th*P_i + nu*max(0, P_i - Y_i/sf)
            attr_ij = max(0,P_j-P_i) * min(1,S_j/P_j) * e^(-d/Lm) * win(d)
            flow_ij = out_i * attr_ij / sum_k attr_ik
            net_ij  = flow_ij - flow_ji

update      P_i' = P_i + B_i - D_i + sum_j net_ij
```

Conservation: trade ships each surplus unit once (`Σimports = Σexports`,
unreached surplus simply not eaten); migration is origin-budgeted and
antisymmetric (people only move). Only births and deaths change the
total. Exact stacks keep the engine rule (smaller dies, larger ignores).

## Mechanics, in words and equations

### 1. Land — who farms what
Every scrap of land within 10 km belongs to its nearest settlement (split down the middle
with neighbours). Land near home yields fully; the far edge yields less (the trudge costs
time). And hands limit you: each farmer feeds 1.3 mouths, so a town farms whichever is
smaller — what its labour can work, or what it owns.

        Y0 = decayed yield of the farmed disc

- `farm_radius_km` = 5 — a day's walk to the fields and back
- `rural_density` = 30/km² — mouths an acre feeds at subsistence
- `farm_decay_at_radius` = 0.9, `farm_decay_shape` = 2.0 — far edge ~10% worse, smooth falloff
- `farm_workers_yield` = 1.3 — mouths fed per farmer

### 2. Services — farming eats first
Figure out the harvest, count the hands it needed, everyone else is a smith, weaver, or
trader. No decision involved: farmers are the requirement, services are whoever's left over.

        serv = max(0, P − Y0/(1.3·(1 + last improvement)))

### 3. Improvement — smiths make farms better (three parts)
**(a) Market (quantity).** Every service crew contributes help to neighbours within 60 km,
fading with distance (grain carts travel ~20 km/day). Big crews count superlinearly — ten
smiths together beat ten apart (division of labour). [Recalibration below picks 1.15 + 0.25 cap.]

        mkt = Σ serv-mass · 2^(−d/20)

- `cart_distance_km` = 20 — a day's cart trip; trade/market reach 3× that = 60 km
- `market_scaling` = 1.15 — big crews punch ~15% above weight

**(b) Frontier (quality ceiling).** Help only matters if the *methods* exist.
Your ceiling is set by the best crew close enough to learn from — and every
town's teaching range grows smoothly with its size: 10 km (a day's walk) at
and below 1,000 people, ~60 km at 5,000, 150 km (sight and mail range) at
and above 50,000. Small towns teach their patch, centers their district,
great cities their province. No teacher in range → capped low, however much
effort arrives.

        range(P) = 10 + 31·ln(P/1000) to 5k, then 60 + 39·ln(P/5000) to the 150 cap
        ceiling = mi · min(1, (best_in_range/2356)^(γ−1))

- `max_improvement` = 0.5 — best-practice methods grow ~50% more
- 2356 = a full ring's worth of specialists (the famous-or-not line)

**(c) Resell (memory).** Towns pass on what they received — this turn's offer is services ×
(1 + last turn's improvement), so richness walks one hop per week and fades per hop. Cold
start = plain neighbours.

        offer = serv · (1 + last),    Y = (1 + imp) · Y0
        imp = ceiling · mkt/(mkt + P)    (help per head, saturating)

### 4. Trade — hungry mouths eat first
Nearest pairs first: while one side is better fed, move food toward pairwise equality
(exact at melt = 0, lossy otherwise). Big or small,
all mouths equalise — a starving town eats before a comfortable village overeats, and nobody
is ever dragged below the mouth it feeds. Food is conserved except melt, which is tallied
(`S.sum() = prod.sum() − melted`).

        f = (sp_donor − sp_hungry) · P_i·P_j/(P_i + delta·P_j)    (food per head, sp = S/P)
        arrived = f · delta,    delta = exp(−tau·d)              (melt = 0: exact equality)

### 5. Babies and deaths — Malthus
Towns have a fixed number of surviving babies each year; deaths fall when food per person
rises above need and climb steeply in hunger. Break-even is ~21% over need (S/P ≈ 1.21),
so towns must be overfed to hold their people.

        births = b·P,    deaths = m·P·(S/P)^−p

- `birth_rate` = 24/1000/yr net surviving (gross 35 × ~0.7); `death_rate` = 31/1000/yr;
  `starvation_elasticity` = 1.3 (half rations kill ~2.5×)

### 6. Migration — drift to the towns
A trickle of everyone (0.5%/yr) plus more footloose service folk (5% of services) moves each
year, uphill toward bigger towns that can feed arrivals. Movers are conserved — every arrival
is someone's departure (which is why boomtowns grow on village births).

- `migration_share` = 0.005/yr background drift; `surplus_mobility` = 0.05 (service folk move
  10× more); range ~50–60 km

### 7. Death floor
Towns at 10 or fewer people vanish (too few hands to hold the fields).

- `town_min_population` = 10 (engine floor; bots still see the legacy 500)

One turn = one week (`turns_per_year` = 52). Net growth can never exceed babies-minus-deaths,
and food is conserved every turn — nothing comes from nothing; towns earn their keep by
teaching villages to grow more.

## Sanity results (3 archetype runs)

**Lone settlements** (3,000 turns ≈ 58 yrs):

| start | end | %/yr |
|---|---|---|
| village 300 | 315 | +0.08 |
| town 2,400 | 2,392 | −0.01 |
| city 20,000 | 10,448 | −1.12 |

**Equal population (4,200) in one 120 km region** (10,000 turns):

| structure | end | %/yr |
|---|---|---|
| 14 villages × 300 | 4,936 | +0.084 |
| 10 villages + 1,200 town | 4,936 | +0.084 |
| 6 villages + 2,400 town | 4,600 | +0.047 |
| 3 villages + 3,300 town | 4,222 | +0.003 |
| 1 town 4,200 | 3,061 | −0.164 |

**City systems, equal population 20,400 within carting range** (20,000 turns):

| structure | end | %/yr |
|---|---|---|
| 68 villages | 28,177 | +0.084 |
| **1×2,400 town + 60 villages** | **30,319** | **+0.103** |
| 1×4,800 town + 52 villages | 29,457 | +0.096 |
| 1×8,400 town + 40 villages | 27,428 | +0.077 |
| 1×12,000 town + 28 villages | 21,052 | +0.008 |
| 1 city 20,400 | 3,268 | −0.475 |

Findings: a **low urban fraction** (~12% market town) pays for itself
through market services and beats pure villages (+0.103 vs +0.084 %/yr);
oversized towns/cities starve and drag the system down; a 2,400 town is
already too big for only 1,800 rural neighbours. Towns are population
sinks (natural growth 0 when fed — they live on migration), which is
the intended urban-graveyard behaviour.

Run them: `python benchmarks/sanity_agrarian.py [turns]`,
`sanity_agrarian_struct.py`, `sanity_agrarian_city.py`.


### Town size and the farmland packing limit

A settlement's ring is `πR² ≈ 79 km²`. Within a town's carting reach
(`3·L_cart ≈ 60 km`) at most `π·60²/79 ≈ 144` villages fit without
overlapping farmland — 118 at 10 km hex spacing, which is the realistic
packing. One town replaces one lattice site; one-turn rates (turn 2,
services primed), 117 villages around it:

| town seed | young villages (300 pop, surplus 90) | mature villages (1,800, surplus 540) |
|---|---|---|
| 0 | +0.084 | +0.084 |
| 2,400 | +0.101 | +0.089 |
| 4,800 | **+0.113** | +0.102 |
| 9,600 | +0.107 | +0.113 |
| 14,400 | +0.098 | — |
| 24,000 | +0.083 | **+0.117** |
| 48,000 | — | +0.111 |

The optimal town is not a fixed 2,400: it scales with the villages'
**marketable surplus**, because the same service premium is a
percentage of a much larger harvest once farmland is full. Young
countryside (117 × 90 ≈ 10k surplus) supports towns up to ~10k with an
optimum near 5k; mature countryside (117 × 540 ≈ 63k surplus) supports
cities of tens of thousands with an optimum near 24k. That is the urban
transition: towns grow as the countryside matures.

Method note: one turn gives the exact instantaneous rate and the
equilibrium direction (`_step_core` is a pure function of the towns —
services resolve in-turn from unboosted yields, so there is no
warmup, no window, no oscillation); long runs are only needed to
quantify slow accumulation effects like town growth.


### Best growth layout for 100,000 people

Compactness and service coverage dominate. One-turn rates (top of
`benchmarks/sanity_agrarian_layout.py`), hex lattice at 10 km spacing
(cell 87 km² > ring 79, so no farmland overlap), villages within ~55 km
of a market town (carting reach 60 km):

| layout | villages | village pop | %/yr |
|---|---|---|---|
| 1×9,600 town + 120 villages | 120 | 753 | **+0.1161** |
| 1×9,600 + 100 villages | 100 | 904 | +0.1154 |
| 2×4,800 + 100 villages | 100 | 904 | +0.1152 |
| 1×9,600 + 80 villages | 80 | 1,130 | +0.1146 |
| 1×14,400 + 100 villages | 100 | 856 | +0.1136 |
| 1×9,600 + 60 villages | 60 | 1,507 | +0.1132 |
| villages only | 56 | 1,786 | +0.0840 |

Rules that fall out:

- **~10% urban**: one market town of ~10k (or two of ~5k) per 100k
  people; this is the smallest urban fraction that saturates the
  market-service premium (the town has ~7,800 non-farm people).
- **Villages of 700–1,200**, never above ~1,800 — the farm-labour cap;
  beyond it a settlement becomes land-limited and its per-capita growth
  falls (it then also has its own non-farm people, which lets dense big
  villages serve each other: a 48×2,100 lattice grows at ~0.088%/yr).
- **10 km minimum spacing** (ring packing) and **≤60 km to a market
  town**. The 100k compact layout spans a ~50 km radius; spreading the
  same people thinly (333×300 over ~95 km) drops growth to ~0.09–0.10%
  even with several towns, because distant villages lose services and
  trade.
- **Scale the town lattice, not the town size**: one market town per
  ~50–60 km radius (spacing ~100–120 km), each sized ~10% of its local
  population. A bigger single town only pays if the countryside is
  correspondingly bigger and mature (see the packing section above).


### Central France c.1600 vs the model (100,000 people)

Historical picture (Berry/Bourbonnais/Nivernais-Auvergne margins,
sources: Dupâquier, *Histoire de la population française*; de Vries,
*European Urbanization*; Goubert's Beauvaisis; Christaller's marketing
ranges; the anchors in `benchmarks/realism_ref.json`):

| tier | size | spacing | count for 100k |
|---|---|---|---|
| chef-lieu (petite ville) | 5,000–10,000 | — | 1 |
| bourgs / market towns | 300–1,500 | 10–20 km | 10–20 |
| villages / parishes | 150–400 | 2–5 km | 250–400 |
| hamlets, farms | <100 | — | remainder |

Region ~2,500–4,000 km² (25–40 people/km²); towns >2,000 hold ~8–12%
of the population; net growth ~0–0.2%/yr (the 17th-century plateau,
punctuated by subsistence crises).

Model optimum for 100k: 1 town 9,600 + 100 villages of 900, 10 km
spacing, ~8,800 km², ~10% urban. The urban fraction and the single
chef-lieu agree; the rural lattice does not — the model's villages are
3–6× too large and 2–5× too far apart, and it has no bourg tier.

Why, in model terms:

- **Reach.** The model's trade/service reach is `3·L_cart` = 60 km.
  History's is a day's return, 10–20 km. Rerun at one carting doubling
  (`benchmarks/sanity_agrarian_reach.py`): the town advantage collapses
  (+0.087 vs +0.084%/yr villages-only), because a 20 km shed cannot pay
  for a town.
- **Every settlement owns a full 5 km ring.** A model town needs
  `P > Y_ring/sf ≈ 1,812` before it has any non-farm people and can
  serve anyone. Historical bourgs of 500–1,500 had small territories and
  lived off surrounding villages — they were service centres with large
  non-farm shares. The model cannot represent that tier.

To reproduce the 1600s pattern: shorten the economic reach to ~20 km
and add a bourg mechanic (settlements whose farmland is smaller than a
full ring, so a small market town can still have net importers and
service capacity).

### Reality goals: 100k district and 1M province

What the model should reproduce (France c.1600, ~18M on 550k km²;
~40,000 parishes; anchors in `benchmarks/realism_ref.json`). A 100k
area is about one *election* (~3,000 km² at ~33/km²); a 1M area is a
large province (Normandy scale, ~30,000 km²). Same spacings at both
scales — only a top tier appears with scale:

100k district:

| tier | count | size each | spacing | share |
|---|---|---|---|---|
| parishes (village + hamlets) | ~200–250 | ~450 souls (center 150–400) | 2–5 km | ~72% |
| bourgs (weekly market) | ~15–25 | 500–1,500 | ~10–15 km | ~15% |
| chef-lieu (election seat) | 1 | 5–10k | central | ~5–10% |
| regional capital / great city | 0 | (25k+, 40–70 km apart — bigger than this area) | — | — |

1M province (×10, plus one tier that fits only at scale):

| tier | count | size each | spacing | share |
|---|---|---|---|---|
| parishes | ~1,700 | ~430 | 2–5 km | ~72% |
| bourgs | ~150 | ~900 | 10–15 km | ~13% |
| chef-lieux | ~9 | ~8k | ~50 km | ~7% |
| regional capital (*parlement* town) | 1 (–2) | 15–40k | — | ~3% |
| great city | usually 0 | (Paris 300k, Lyon ~45k are the exceptions) | — | — |

Notes: urban (2k+) ~8–12%; long-run growth ~0.3%/yr; south dispersed
(hamlets), north nucleated (the table is the northern pattern); settled
districts run denser than the 33 average (mountains/forest/heath sit
empty). Against the model: villages match (200 @ ~3 km ✓) but the
bourgs + chef-lieu + regional have no agricultural reason to exist —
they are administration, courts, church, walls, fairs. And the urban
graveyard (cities shrank 10–30%/yr naturally) is unmodeled, so our
towns face neither the cost nor the non-food reasons. Both gaps are
identified open modeling, not fit failures.



### Multiple towns: 10k primary + 5k secondaries + villages

One-turn rates for a 100k hierarchy (`benchmarks/sanity_agrarian_hier.py`):

| layout | compact (all villages within ~50 km) | thin spread (villages 300, region ~92 km) |
|---|---|---|
| 1×9,600 town | **+0.1154** | +0.0954 |
| + 2×2,400 secondaries | +0.1100 | +0.0989 |
| + 4×2,400 secondaries | — | **+0.1010** |
| + 2×4,800 secondaries | +0.1066 | +0.0993 |
| 1×10,000 + 3×5,000 | +0.1000 | +0.0989 |
| villages only | +0.0840 | +0.0840 |

- In a **compact** countryside (every village within one town's 60 km
  reach), secondary towns only duplicate services and add zero-growth
  urban population: one ~10k town wins.
- Secondary towns pay only when they **extend coverage** — thin, spread
  settlements beyond the primary's reach. Then small secondaries just
  above the non-farm threshold (~2,400; services start at
  `Y_ring/sf ≈ 1,812`) beat 5k ones: 4×2,400 (+0.1010) beats
  1×10,000+3×5,000 (+0.0989), because a 5k town's extra people add
  little saturated service and dilute growth.
- Rule: urban ≈ 10–15% of the population; one primary ≈10% of the
  total, secondaries ~2,400 placed in the coverage gaps (each village
  within 60 km of some town); never pay for 5k secondaries unless they
  cover new countryside.


### Von Thuenen distance decay (default on) — small settlements win

`farm_decay_at_radius` (c = 0.9) and `farm_decay_shape` (p = 2) replace
the flat 5 km ring with yield `rho0*(1 - c*(d/R)^p)`: workers farm the
best land
first (`a_w = sigma/rho0` km² each), so per-worker output falls with the
distance a settlement must reach; `rho0` is rescaled so the full ring's
mean yield still equals `rural_density`. `c=0` is the old flat ring.

Measured (c=0.9, p=2; `benchmarks/sanity_agrarian_decay.py`):

| settlement | Y/P |
|---|---|
| 100 | 1.282 |
| 300 | 1.247 |
| 800 | 1.158 |
| 1,500 | 1.034 |
| 2,400 | 0.874 |

100,000 people split into N equal villages (10 km spacing):

| N | village | system growth |
|---|---|---|
| 25 | 4,000 | −0.135%/yr |
| 42 | 2,381 | +0.020%/yr |
| 67 | 1,493 | +0.069%/yr |
| 125 | 800 | +0.096%/yr |
| **333** | **300** | **+0.105%/yr** |
| 667 | 150 | +0.102%/yr |

Packing matters: 333×300 at 3.5 km spacing gives +0.124%/yr vs
+0.105%/yr at 10 km — small villages farm only their ~7 km² near-field,
so they can pack tightly and serve each other through the short-range
market channel. The optimum village is ~300–500: smaller and the
non-farm service sector vanishes; bigger and the settlement starts
farming poor land.

Caveats if adopted as default: there is no minimum territory/fixed cost
per settlement (wood, pasture, church/mill), so the model keeps
subdividing until services fade (~150 people); and `rho0` rises to
`rural_density/(1-2c/(p+2))` (54.5/km² at c=0.9), so realized landscape
densities can exceed the 20–40/km² anchor unless c is tuned.


### How many hierarchy levels? (decay model)

Best configuration per hierarchy depth, 100k people, hex overlays of
coarser lattices (spacing x q, count / q²), tier sizes consecutive
multipliers of the village (`benchmarks/sanity_agrarian_levels.py`):

| levels | best %/yr | urban | P_village | shape of the best |
|---|---|---|---|---|
| 1 (flat) | **+0.1242** | 0% | 332 | 301 villages, 3 km spacing |
| 2 | +0.1215 | 7.1% | 321 | 290 villages + 11 towns (q=5, size 2x) |
| 3 | +0.1212 | 7.6% | 318 | + 1 regional (counts 290/10/1) |
| 4 | +0.1212 | 8.8% | 314 | + 1 capital (counts 290/10/0/1) |

Deeper hierarchies do not beat the flat mesh; they converge toward it.
The best ones are almost flat: towns only 2x the village, one per
~20 km, and the middle levels are empty (counts [290, 10, 0, 1]).
Rich central-place hierarchies (many towns, big regionals) lose much
more (at 20-40% urban, +0.10 down to +0.035%/yr).

Why: growth is rural, villages above ~300 already have small non-farm
sectors and serve each other at close spacing, and every person moved
into a town leaves near-field farming and does not reproduce (fed towns
have zero natural growth). Deeper tiers add no new service because the
premium saturates.

Deep hierarchies would need mechanisms the model lacks: agglomeration
economies (service output per non-farm person rising with town size),
institutional fixed costs (markets, courts, garrisons, cathedrals),
market-function gating (only towns provide services), inter-regional
trade in manufactures, or defence/administration. Historically,
central-place hierarchies existed for those reasons, not because they
maximised local demographic growth.


### Which `market_scaling` gives a realistic hierarchy?

Score of the growth-optimal 100k layout against the 1600s anchors
(village 150-400 @ 2-5 km, bourgs 300-1,500 @ 10-20 km, chef-lieu
5-10k, region 2.5-4k km², zipf 5-50), over the hierarchy search
(`benchmarks/sanity_agrarian_realism.py`):

Matched shapes, windowed rates (villages s_v=4/Pv=300; towns s32/T2400;
rmax=50; gaps = hierarchy − flat):

| gamma | premium 0.25 | premium 0.50 |
|---|---|---|
| 1.00 | +0.018 | +0.034 |
| 1.10 | +0.020 | +0.037 |
| 1.15 | +0.021 | +0.039 |
| 1.30 | +0.026 | +0.047 |
| 1.50 | +0.033 | +0.059 |

Correction: gamma is NOT a threshold — the hierarchy wins at gamma=1.0
too, once shapes are matched and rates are settled. What gamma sets is
the *margin*: higher gamma shifts services from villages to towns
(village contributions shrink as serv^gamma for serv << P_market), so
flat falls while the hierarchy holds, and the gap widens. The static
realism scorecard still describes the winning hierarchy shape (280
villages of 296 at 4 km, 20 market towns of 592 at 16 km, one
chef-lieu of 5,325 — 0.92 against the anchors).

Recommendation unchanged (`market_scaling = 1.15` anchor +
`max_improvement = 0.5` for a robust margin), justification updated: the
anchor value sets a strong hierarchy advantage, not the existence of
one.


### Scale: 1 million people with gamma=1.15, premium=0.5

The emergent hierarchy scales as a copy of the 100k one - counts x10,
tier sizes roughly constant (`benchmarks/sanity_agrarian_1m.py`):

| config | villages | market towns | regional | capital | urban | %/yr |
|---|---|---|---|---|---|---|
| flat 3,001 x 333 @ 3 km | 3,001 | - | - | - | 0% | **+0.1631** |
| q=(5,5,5) m=(2,2,5) @ 3.5 km | 2,882 x 318 @ 3.5 km | 114 x 636 @ 18 km | 4 x 1,271 @ 88 km | 1 x 6,357 | 8.4% | +0.1576 |
| q=(4,4,4) m=(2,3,3) @ 3.5 km | 2,818 x 309 @ 3.5 km | 172 x 617 @ 14 km | 10 x 1,852 @ 56 km | 1 x 5,556 | 13.0% | +0.1552 |

Those 1M numbers turned out to be wrong (see the retraction below).
With matched shapes and settled rates, the hierarchy wins decisively
at both scales:

| shape (matched) | ~110k region | ~1.05M region |
|---|---|---|
| flat villages | +0.1106 | +0.1144 |
| towns 2.4k / 32 km (~12% urban) | **+0.1444** | **+0.1489** |
| towns 9.6k / 64 km (~8-12% urban) | **+0.1447** | **+0.1498** |

Rankings are identical across scales: towns of a few thousand
covering the countryside every ~30-60 km beat flat by ~30% relative,
with ~8-13% urban. There is no scale flip.
- **The top of the system stays small.** The capital lands at
  2,500-7,400 - the service premium saturates at market-town scale.
  A 1600s province of 1M had chef-lieux of 10-30k; the model needs
  denser hinterlands, more agglomeration, or non-food urban functions
  to get there.

### Retraction: why the flip was an artifact (compound, both halves)

1. **The 2-turn protocol measured flat meshes at an oscillation peak.**
   Market services run on a one-turn lag (`serv` from last turn's
   production), and villages balanced near `prod/sf ~= P` flip their
   `max(0, ...)` service term on and off each turn. Flat meshes ring
   at +-40% forever (t2 +0.15 vs settled mean +0.11); hierarchies
   converge by t3-4 because the big town's services dominate. Every
   table measured with 2-turn snapshots overstates flat by ~30-40%.
   The fix is windowed means (warm 4 + span 6 == warm 10 + span 20);
   the oscillation itself is benign for populations (per-turn changes
   are tiny) but shows up as 2-cycle jitter in measured growth.
2. **The (q,m) grids compared different shapes.** Tying towns to the
   village lattice forced different urban fractions, sizes and town
   densities at the two scales (17% urban with a 5.3k top at 100k vs
   8.4% with a 6.4k top at 1M). The independent-lattice test above
   holds spacing, size and urban fraction fixed and the flip vanishes.
   (Replication of identical sheds is bit-exact across scales, as the
   mechanics demand — there are no global couplings.)

Cheap replacement: `benchmarks/hierarchy_opt.py` builds matched
shapes on a moderate region (N ~= 570, ~0.3 s/config, ~3 MB matrices)
and measures single-turn rates — the economy is a pure function of
the towns since the serv-lag removal, so one `_step_core` call is the
exact instantaneous rate (no warmup, no window, no oscillation).
Validated: its ranking matches the 1M region (N ~= 3150, ~5 s/config)
shape-for-shape.

Profiled costs (shared 3.8 GB box, numba on; load-sensitive, ±2x).
N=570: turns ~0.01 s (min-of-7, idle). N=2263 (60 km reach x 4 km
lattice ~= 1.8M pairs): steady ~125 ms, founding ~154 ms, death ~180 ms
— founding matches and death beats the incremental-era 140/206 ms;
steady carries ~+30 ms of honest equalize-loop cost (all pairs, since
any pair can flow; the old deficit kernel scanned ~none once settled)
plus the untouched migration floor (~55-70 ms here). Master at the
same N: steady 204, founding ~470-845, death ~416 ms.
Trade pair order is canonical — all in-reach (i, j) sorted by
(distance, i, j) — cached per geometry (steady turns never enumerate
or sort) and maintained incrementally (merge on append-at-end
founding, filter+remap once on death, full rebuild otherwise),
bit-exact in all paths (incremental == rebuild `array_equal`; reversed
ties give 0.0 diff; tables byte-identical). The frontier max fused
into one numba walk (was two Python loops). No dense N x N array
exists anywhere: one cached grid + 60 km neighbor lists (+ migration
weights) serve every kernel. Memory is O(N x local pairs).
Peak RSS at N=3150 is ~350 MB, down from ~900 MB.
Founding/destroying a single town is incremental, not a rebuild:
classify-on-miss (append-at-end founding inserts into neighbor lists,
single death remaps once; anything else rebuilds), land recomputed only
within 2R of the event via the verified-identical fallback loop.
Steady-state turns reuse every cache (early-return before any new code).
A full 7-shape 1M sweep runs ~40 s end to end (was ~3.5 min at 10
turns/config before the serv-lag removal). No dense N x N array exists
anywhere now: one cached grid + 60 km neighbor lists (+ migration
weights) serve every kernel. Memory is O(N x local pairs).
The land kernel is no longer O(n^2): per-town neighbor lists (towns
within 2R, from the cached cell grid) prune the inner loop from
N to ~20 candidates. Exact — bit-identical on twin towns at exactly
2R, exact stacks, ties, negative coords, and all benchmark shapes
(tripwire unchanged). The N x N removal is bit-exact at ALL scales:
same pair sets (same sqrt expression, same comparisons), same visit
orders — verified `array_equal` against the matrix version on 22
cases including the 3153-town benchmark. Quadrature points
(`_SAMPLE_K = 32`): isolated towns are exact at any
K; shared boundaries need K large enough that one point (pi*R^2/K km2)
stays small next to the smallest farmed area (~7 km2 for a 300-pop
village). Measured: K=8 errs up to 40% on small cells, K=16/32 a few
%, K=64/128 ~1-2% — while growth rankings are unchanged down to K=16
(labor-limited towns never touch their area). So 32 is the default
(4x kernel speedup over 128 at no ranking cost). Same idea as
combat/movement's SpatialHash grids, but as numpy CSR arrays (numba
can't do dict cells).
Guidance: screen at N ~= 500-600; keep 1M validations rare, one at a
time, with caches cleared between geometries (`eco._geo_cache`,
`eco._land_cache`). The engine itself needs no changes for this —
real games stay at hundreds of towns where every kernel is
milliseconds; the N x N matrices only bite in benchmark worlds.

Note on older tables: every growth table predating this section used
2-turn snapshots, which overstate flat meshes by ~30-40% (oscillation
peak) while hierarchy numbers are near-settled. Rankings where the
hierarchy won stand and are stronger than reported; close calls and
the exact optima (town/village sizes) should be re-run with
`hierarchy_opt.py` before being trusted.

### Optimal hierarchy: two levels suffice

Adding a third tier (9.6k regionals every 96 km) or a capital (6k,
20k) on top of the optimal 2-level pattern never helps — windowed
rates, matched shapes, both scales:

| shape | ~110k region | ~1.05M region |
|---|---|---|
| flat villages | +0.1106 | +0.1144 |
| + market towns 2.4k / 32 km | **+0.1444** | **+0.1489** |
| + regionals 9.6k / 96 km | +0.1388 | +0.1422 |
| + capital 6k | +0.1411 | +0.1482 |
| + capital 20k | +0.1307 | +0.1466 |

The extra urban population has zero natural growth when fed, so each
added tier dilutes faster than its extra services repay. Optimal:
**villages (300, 4 km hex) + market towns (~2.4k, every ~32 km)**,
~8-13% urban. Concretely: ~110k region (r=40 km, ~5,000 km2) holds
~360 villages + 7 market towns; ~1.05M region (r=118 km, ~43,700 km2)
holds ~3,090 villages + 55 market towns. A 9.6k regional tier or any
capital is dead weight for growth (they may still be wanted for
non-growth reasons: administration, defence — out of scope here).

## Hierarchy optimum: current vs legacy (100k and 1M)

Matched shapes, per-capita %/yr. Current cold = single turn from zero
state (plain pairwise); settled = 3 warmup turns (resell converges,
pops drift 0.009%) + measured turn. Legacy = master's stock
logistic+crowding, one turn (stateless). Absolute rates are NOT
comparable across systems (different models); rankings are.

100k region (N ~= 570):

| shape | levels | urb% | top | cold | settled | legacy |
|---|---|---|---|---|---|---|
| flat | 1 | 0.0 | 300 | +0.1521 | +0.1572 | −274.70 |
| s16/T600 | 2 | 12.1 | 600 | +0.1528 | +0.1576 | −275.62 |
| s32/T2400 | 2 | 9.0 | 2400 | +0.1530 | +0.1544 | −274.36 |
| s32/T2400+cap20k | 3 | 17.9 | 20000 | +0.1414 | +0.1418 | −272.04 |
| s64/T2400 | 2 | 1.4 | 2400 | +0.1556 | +0.1595 | −274.68 |
| s64/T9600 | 2 | 5.3 | 9600 | +0.1554 | +0.1577 | −273.38 |
| +regional 9.6k | 3 | 13.5 | 9600 | +0.1479 | +0.1486 | −274.90 |
| hier4 | 4 | 21.6 | 20000 | +0.1355 | +0.1357 | −58511348.56 |

1M region (N ~= 3150):

| shape | levels | urb% | top | cold | settled | legacy |
|---|---|---|---|---|---|---|
| flat | 1 | 0.0 | 300 | +0.1570 | +0.1614 | −699.83 |
| s16/T600 | 2 | 11.9 | 600 | +0.1574 | +0.1614 | −701.24 |
| s32/T2400 | 2 | 12.4 | 2400 | +0.1502 | +0.1511 | −694.96 |
| s32/T2400+cap20k | 3 | 14.1 | 20000 | +0.1477 | +0.1485 | −695.42 |
| s64/T2400 | 2 | 3.2 | 2400 | +0.1595 | +0.1618 | −697.68 |
| s64/T9600 | 2 | 11.7 | 9600 | +0.1511 | +0.1517 | −685.42 |
| +regional 9.6k | 3 | 17.7 | 9600 | +0.1426 | +0.1431 | −689.59 |
| hier4 | 4 | 19.1 | 20000 | +0.1402 | +0.1407 | −10988422.35 |

Current optimum (both scales, cold and settled agree): 2 levels —
300-person villages on a dense (~4 km) lattice + 2400-person market
towns spaced WIDE (~64 km, urban ~1–3%). Third/fourth tiers (20k
capitals, 9.6k regionals) lose everywhere: big mouths, thin gains,
dilution beats agglomeration. 9600-towns don't pay either (below flat
at 1M). Resell adds +0.001..0.004 systematically but overturns
nothing — deep hierarchy loses WITH the network effect, not for lack
of it. Rankings are scale-invariant.

Legacy: degenerate. Its crowding sums unbounded-range over hundreds of
neighbors (a lone pair at 4 km merely halves growth to +2.5%/yr; x570
neighbors = death spiral), and no agglomeration mechanism exists — a
2400-town next door only crowds, never benefits. So every dense layout
collapses at both scales (rankings meaningless; hier4 overflows), and
its in-envelope optimum is degenerate too: rate rises monotonically
with spacing toward the lone-village max (+5.18%/yr) — levels 1,
sizes small, spacings as-wide-as-possible. Real settlement (villages
at 2–5 km *with* towns) is unrepresentable. That gap is what the
rework fills.

## BO optimum, unconstrained (250 evals; family unified with build())

BO rewritten to `build()` conventions (tiers on own offset lattices,
0.6·s0 exclusion, top-down claiming, absent-gate at expected<1 town;
bit-exact vs `build()` on GOAL: N=575, pop=201900, +0.1477 both).
Absolute spacings, 8-D continuous, settled evals, total band only
([50k,300k] scope — tiered stacks carry chef mouths). No size/gap/
presence constraints: degenerate optima are model diagnoses, not
search failures.

250 evals (150 model): peak +0.1636 (villages 222@3.7 + 383@39 +
2817@83; gaps 1.7×/7.4×), still creeping (+0.151 at 110). No
structural consolidation across runs/seeds — the objective is a
plateau (~+0.15–0.164) with spikes, not a basin. Robust
basin-level claims: villages push small (P0 100–280, below the 300
assumption — no fixed costs means no lower bound except the death
floor; reality's 150–400 needs collective-goods scale the model
lacks); tops always present (2.8–24k, fame confirmed); mid tier
flat (200–2400 all tie). Hand GOAL sits in BO's log at +0.1477.
Tiered-constrained run (r≥2, T1+T2 required): +0.1579 (415@4 +
2435@59 + 6996@62, duplicate spacing — needs spacing-gap rule, not
 pursued: constraints would launder model prefs into priors).

## BO hierarchy optimum (settled, 100k regime; SUPERSEDED — see above)

Bayesian optimization over continuous densities/sizes (8-D: base
spacing/size + 3× (density-fraction, size-ratio); tiers vanish by
density falling out; total-pop band; settled = 3 warm + measured).
110 evals (~55 in-band), GP Matern+nugget, EI. Winner:

- Villages ~200 on a ~3 km lattice (not our assumed 300 @ 4 km!) +
a sprinkling of ~650-person towns (~1–7 per 100k, urb 0.3–2.4%):
+0.1616…0.1621 vs hand-best s64/T2400 +0.1595, flat +0.1572.
- Targeted checks on the winner baseline: pure flat +0.1603;
+seven 2400-towns +0.1589 (big towns HURT optimized villages —
dilution); +seven 650-towns +0.1616; one 650-town +0.1621.
- 3rd/4th tiers never pay (best 3-level +0.1606); cities/capitals are
dilution. Levels explored 1/2/3/4 (4-level tail thin: 2 evals).
- dense villages serve each other, so towns add less: agglomeration
shows diminishing returns to density. Sparse villages (300 @ 4 km)
need towns (+0.0023); dense ones (200 @ 3 km) barely do (+0.001).
- Winner sits inside realism anchors (25/km² rural, 2–5 km spacing,
150–400 size) — but urb ~0% vs the 8–12% anchor: towns exist in
reality for non-agricultural reasons (administration, defense,
trade nodes) the model lacks. Open gap, not a fit failure.
- Caveats: single seed (basins agree, all dense-small); count
rounding (±1 town); 1M transfer untested (spacings should transfer —
physics-set — counts scale; top size may scale).

## Negative result: services-from-boosted-yields (reverted)

Tried: staff farmers at expected boosted yields
(`serv = P - Y0/(sf·(1+last))`, migration surplus reuses serv; zero new
state/params; cold-start identical). Motivation: increasing-returns
engine for hierarchy (proven kind-not-degree: town services exactly
constant 136.55 across γ 0.8–2.0, mi, reach sweeps — no tuning moves
them). Result: mechanically sound (services 137→385 city-fed, 324
unfed, converged t3, towns stable) but the 100k optimum moved AWAY
from reality: everything rose (flat +0.1572→+0.1725) while deep tiers
stayed flat (hier4 +0.1357→+0.1357); flat–hier4 gap widened
0.022→0.037; goal mimic (bourgs+chef) +0.1455 vs flat +0.1725.
Lesson: the feedback rewards headroom (labor-tight villages 4×
services, saturated towns +5%) — it feeds the bottom, not the top.
Reverted to committed baseline; hierarchy needs gains concentrating
UPWARD (frontier-ceiling next candidate).

## Frontier + 100k optimum (matches economic tiers)

Saturation probe showed settled flat villages at mkt/P ≈ 3.6 (78% of
ceiling) — the ceiling binds, so a technique frontier bites. Built:
`frontier = min(1, (max nearby pool/P_market)^(gamma-1))`, max over
the daily-walk neighborhood (2·farm_radius = 10 km: skills need daily
face-to-face; goods weekly cart (market decay); trade commercial
trips — three nested rhythms, zero new params/scales). At gamma=1 the
frontier is exactly off; capped at mi (max stays max); 60 km lists
serve it (150 km rule safe). Suite green, no tripwire rebase.

Settled ranking flipped: s64/T2400 (+0.1494, 60 km frontier) led
first; local (10 km) frontier → GOAL bourgs+chef +0.1273 wins, then
s16 +0.1208, regional +0.1163, s64 +0.1152 (one hub de-isolates one
patch), flat +0.1119 last. Coverage efficiency decides: many-small
covers ground per mouth; few-big leaves capped gaps.

100k optimum vs reality: villages 300@4km ✓✓; bourgs 600–1000 @
15–18 km ✓ (reality 500–1500 @ 10–15; ours tiles efficiently, reality
over-dense from seigneurial market competition); chef monotone
8000→+0.1273, 5000→+0.1286, 3000→+0.1294, none→+0.1302 — the top
melts, centers >3000 are dead weight (mouths > patch lift). Chef is a
power-tier fact (election seat; lives in the game's power layer with
combat/capitals/score), not a growth optimum — exogenous boundary,
documented not hidden. BO's dense-village finding was
mechanism-conditional (pre-frontier); post-frontier 200@3km loses
(+0.1107 < +0.1119). Targeted shapes settle structure; BO reserved
for reopening structure, not refining numbers.

## 1M transfer + verdict (goal achieved for economic tiers)

`benchmarks/scale_1m.py`: same spacings at r=118, scaled counts
(deterministic FPS: 150 bourgs, 9 chefs, 1 regional 25k; lands on
~1.05M). Settled: bourgs-only +0.1267 > full-stack +0.1188 >
regional-shape +0.1152 > flat +0.1145. Tops melt at scale too (chefs
+ regional cost −0.008 together); hierarchy margin narrows vs 100k
(+0.004 vs +0.018 — scale favors flat interiors) but ranking holds.

Verdict: economic tiers match at both scales (villages 300@4km +
bourgs 600–1000@15–18km; counts scale, spacings hold); power tiers
(chefs, regionals) are dead weight growth-wise at both scales —
monotone melt measured twice. They are exogenous admin facts (power
layer: combat/capitals/score), not growth optima; no further
growth-only iteration can produce them (proven by monotonicity, not
assumed). 100k + 1M economic optima match the reality goals
reasonably; the remainder is objective scope, not mechanics.

## Equalize-trade + fame: 3 tiers at 100k, 4 at 1M (goal met)

Autopsy (GOAL settled): chef S/P = 1.000 exactly (trade filled deficits
and stopped), villages S/P ≈ 1.8 (birth-saturated — further lift
wasted), chef vital = 0; its −0.003 = land exclusion +
fecundity-destruction (movers 1.8→1.0), patch lift only +0.002.
Dilution −0.005 vs lift +0.002, arithmetic closed. Deeper diagnosis:
non-zero-sum (exports ignored) was load-bearing — towns ate free food.
Zero-sum exposes dilution; tiers must EARN mouths by growing the pie.

Trade rework (same 60km pairs, 150km rule safe): equalize S/P across
each pair nearest-first (exact pairwise equality, strictly-above only
— deficits fill, towns overfeed past subsistence, never inverts, never
starves donors); zero-sum asserted every turn (`S.sum()==prod.sum()`).
Per-unit marginal births are size-blind at equal S/P, so equalizing is
concave-optimal; town mouths breed instead of subsisting. Suite:
trade tests reframed (70/200/80/60 + efficiency), spatial perf test
fixed (was timing 500 full turns on a fitted-era 0.25s budget — now
times the geo build it claims).

Fame (zero new params): complete crews (serv > P_market) radiate
ceilings at commercial range (60km, word travels); smaller crews teach
only the daily-walk (10km). Cities fund districts via pie-growth, not
free lunch.

100k settled: GOAL bourgs+chef +0.1476 wins (chef removal → +0.1349,
so the 3rd tier is real, +0.013); regional +0.1458, cap20k +0.1344,
hier4 +0.1235, flat +0.1119 last. Tiers 300/1000/8000 (3.3×/8×).
1M (`scale_1m.py`): full-stack +0.1409 wins; bourgs-only +0.1327,
regional-shape +0.1386, flat +0.1145. Tiers 300/1000/8000/25000
(3.3×/8×/3.1×, counts 2985/150/9/1 ≈ reality). Tripwire green
throughout (γ=1 setups unaffected). All pairs within 60km lists — the
150km rule never approached.

## Recalibration: three tiers at 100k (melt + premium, 2026-09-13)

Engine changes since the sections above (were unchecked, now committed): net
births (`b` 35→24/1000 surviving; food acts through deaths, not births),
starvation deaths (`p` = 1.3), freight melt (`melt_per_km`, big receivers
have roads), farmers staffed at boosted yields. At the inherited screening
values (`melt` 0.005, `premium` 0.5) the 3-tier stack won by only +0.01 over
a lone giant — fragile. A ~16-run sweep on `benchmarks/hierarchy_opt.py`
(8 shapes incl. new 3-tier `goal` 1000@16+8000 and `lean` 600@18+5000, r38
district + r50 check) plus a 68-eval BO (`benchmarks/bo_r12.jsonl`, settled
rates) rebalanced the knobs. Assay changes: the 0.6·s0 site footprint is a
`--no-footprint` toggle (exact-overlap only when off); the capital special
case is gone (a center is just a site — `build_goal` holds by construction).

Sweep ledger (cold %/yr, best shape@rate; decisive rivals shown):

| # | config | best | rivals |
|---|---|---|---|
| 1 | base (melt .005, prem .5, γ1.15, p1.3) | lean +.83 | goal +.70, lone-9.6k +.69, flat +.43 |
| 2–5 | melt 0 / .01 / .02 / .03 | lean +.85/+.81/+.76/+.69 | lone giant +.75→+.18 (dies by .03) |
| 6 | γ1.0 | flat +.91 | hierarchy gone — ruled out (also unrealistic) |
| 7 | γ1.3 | lean +.83 | flat +.16 (upper-edge γ, gap huge) |
| 8 | prem .25 | lean +.45 | lone +.29, flat +.26 — historical pace |
| 9 | starv 0.8 | lean +.36 | flat +.05 |
| 10 | starv 1.8 | lean +1.20 | absurd hot — ruled out |
| 11–12 | melt .015/.02 + prem .25 | lean +.39/+.35 | lone +.08/−.05 (stagnates, then shrinks: needs its bourgs) |
| 13–14 | BO 20→68 evals at run-11 cfg | 280/518/1526, urb 4.9%, +.42 settled | flat +.38; hand lean +.49 settled (BO underexplored, ranking agrees: 3 levels, gaps 2–3×, tops small) |

Recommended (all realistic — priors in the table below): `melt_per_km` =
**0.015** (~1.5%/km food part of the doubling-every-20km cart cost),
`max_improvement` = **0.25** (config default; the 0.5 screening value ran
hot), `market_scaling` = **1.15** (anchor), `starvation_elasticity` = **1.3**.
`BASE_CFG` now carries melt 0.015 with premium at default; the engine
`GameConfig` default melt stays 0.0 (promotion needs gameplay/bot testing).

Optimum at these settings (footprint ON, settled, rescaled to a 100k district):

| tier | count | size each | spacing | share |
|---|---|---|---|---|
| villages | ~290 | 300 | 4 km | ~86% |
| market towns | ~12–15 | 600 | ~18 km | ~8–9% |
| center | 1 | ~5,000 | central | ~5% |
| big city | 0 | — | — | — |

Against the reality goals: village size/spacing match (ours carry no
hamlets — reality's ~450 souls include them); market-town count/size/spacing
match (15–25 × 500–1500 @10–15km); center size/share match (5–10k, 5–10%);
no big city matches. Urban sits at the top edge (~13% vs 8–12%). District
growth runs at history's pace (+0.35–0.49 vs 0–0.3 recorded).

Footprint verdict (same ground, R12 cfg): ON crowns the 3-tier stack
(+.49 vs +.42 two-tier, +.38 flat); OFF drops it to +.41 and two-tier wins
(+.42) — 27 overlapping villages freeload on town fields. ON's optimum is
higher (+.49 > +.42) because deleting an overlap always raises food per
head; OFF can at best tie by learning avoidance. Keep ON.

1M four-tier hunt (5 BO campaigns at r118, logs `bo_1m4_b1–b4.jsonl`):
max-push (γ1.3/prem.5/melt.005), control, mid-push (γ1.25/prem.35/melt.01),
reseed, extend-to-32 — no setting yields 4 tiers. Winners are 3-tier
(300/600@18/4800@64, urb ~15%) or, at control knobs, flat (hierarchy margin
narrows with scale). Genuine 4-tier candidates trail by 0.17–0.25; BO spends
spare tiers as phantoms (same top size filed twice) or shrinks the top /
blows urban past any cap. Verdict: the 4th tier needs a different objective
(score tops/urban directly) or mechanism (size-scaled fame, non-food urban
income), not stronger knobs.

Continuous fame implements the size-scaled half: range(P) as above (zero new
parameters; the market tail runs to the same 150km sight/mail rule so
far-fame carries real help). District optimum holds (lean 3-tier, settled
+0.39); at 1M under max-push knobs (γ1.3/prem.5/melt.005) the 4-tier
province stack (151×600 + 13×5000 + 20000) goes from +0.08 to a tie for
first (settled +0.79 vs +0.82 uniform-mid, flat +0.32) — upper tiers earn
their keep for the first time. Counts land near reality (151 bourgs vs
~150, 13 chefs vs ~9, regional 20k in range); villages stay small and
non-food urban income is still unmodeled.

Fertility ×2.5 (rural_density 30→75, log `bo_rural75.jsonl`): villages stay
~300 — decay rewards near-field smallness, so extra food becomes surplus,
not density — while tiers shift up (bourgs 600→1000, chefs 4800–8000 win,
growth +0.57, urban ~13–19%). Density is unchanged (~24/km²): it is set by
labour-footprint geometry, not fertility. 33/km² needs tighter spacing and
fixed settlement costs, not richer land.

## Status / open items

- Engine tests + integration are green; 9 bot-side tests still encode
  the old economy and are the bot agent's remit (`tests/bots/`).
- The realism suite (`growth_realism.py --system engine`) now measures
  the agrarian model through a compatibility adapter; its scores are
  not re-fitted yet (the suite was built for the fitted model).
- Calibration knobs with priors: `max_improvement` (0.05–0.5, anchor
  `market_access_ratio`), `farm_workers_yield` (1.2–1.5),
  `surplus_mobility` and `migration_share`.
- Migration budget is background + surplus: `out = th*P + nu*serv`
  (was `th*max(0,B-D) + nu*serv`). At th = 0.005/yr a village next to
  a town drains ~0.5%/yr gross (~-26% over a 58-year game) while the
  town grows ~+25% — steady urbanization, no boom-bust (all trajectories
  monotone). th = 0.01 halves villages in a game length (too hot);
  th = 0.002 is barely visible. Single-turn *total* growth tables are
  blind to this (migration is conservative — it reshuffles, and the
  table measures one turn from fixed populations).
- Recalibration (melt 0.015 + premium 0.25) committed with its BO log
  (`benchmarks/bo_r12.jsonl`); every growth table predating it used the
  old births/deaths and melt-free trade — rankings where deep tiers won
  stand, close calls should be re-run (done for the 100k optimum above).
- Open: settlement fixed costs (villages still ~300 vs ~430 — founding is
  free, so the model subdivides to the service floor); non-food urban income
  (upper counts closer now, but chefs/regional still need power-layer reasons
  at base knobs); longer BO at 1M under max-push (4-tier co-optimal on hand
  shapes — a search may refine sizes/spacings); promoting melt 0.015 to the
  engine default.
