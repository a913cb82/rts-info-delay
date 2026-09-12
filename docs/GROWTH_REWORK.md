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
| `b` | `birth_rate` | 35 /1000/yr | crude birth rate |
| `m` | `death_rate` | 31 /1000/yr | crude death rate (`b−m` = 0.4%/yr) |
| `sm` | `market_premium` | 0.25 | max farm-output premium from market services |
| `th` | `migration_share` | 0.5 | share of natural increase that emigrates |
| `nu` | `surplus_mobility` | 0.05 /yr | share of surplus labour that emigrates |
| `Lm` | `migration_scale_km` | 50 | migration distance scale |
| — | `town_min_population` | **10** | minimum settlement size (die at or below) |

Derived: `Y_ring = rho·πR²` ≈ 2356 people (one ring's food), `h = b/m − 1` ≈ 0.13.

## Formulae (per turn)

```
curves      win(d;D) = sig(D^2/d^2 - D^2/(D^2-d^2))     D = info_speed
            c(d)     = 2^(-d/Lc) in reach, 0 beyond 3·Lc (~60 km)

land        area_i = Voronoi cell within R (nearest-farmer, sampled)
serv_j  = max(0, P_j - Y_j/sf)                          non-farm population
mkt_i   = sum_j serv_j * c(d_ij)
boost_i = sm * mkt_i/(mkt_i + P_i)                      services per head served
Y_i     = (1 + boost_i) * min(rho*area_i, sf*P_i)       production

trade       surplus_j = max(0, Y_j - P_j); deficit_i = max(0, P_i - Y_i)
            greedy nearest-first with hard caps (conservative)
            S_i = Y_i + imports_i                       food commanded

births      B_i = b*P_i * S_i/(S_i + h*P_i)             f=1 -> births=deaths
deaths      D_i = m*P_i

migration   out_i   = th*max(0,B_i-D_i) + nu*max(0, P_i - Y_i/sf)
            attr_ij = max(0,P_j-P_i) * min(1,S_j/P_j) * e^(-d/Lm) * win(d)
            flow_ij = out_i * attr_ij / sum_k attr_ik
            net_ij  = flow_ij - flow_ji

update      P_i' = P_i + B_i - D_i + sum_j net_ij
```

Conservation: trade ships each surplus unit once (`Σimports = Σexports`,
unreached surplus simply not eaten); migration is origin-budgeted and
antisymmetric (people only move). Only births and deaths change the
total. Exact stacks keep the engine rule (smaller dies, larger ignores).

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

Method note: one turn (two with the market-service lag) gives the
instantaneous rate and the equilibrium direction; long runs are only
needed to quantify slow accumulation effects like town growth.


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


### Von Thuenen distance decay (opt-in) — small settlements win

`farm_decay_at_radius` (c) and `farm_decay_shape` (p) replace the flat
5 km ring with yield `rho0*(1 - c*(d/R)^p)`: workers farm the best land
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

| gamma | premium 0.25 | premium 0.50 |
|---|---|---|
| 1.00 | flat wins, realism 0.48 | flat wins, realism 0.48 |
| 1.10 | flat wins (L4 competitive, 0.92) | L4 competitive, 0.92 |
| **1.15** | **L4 wins, realism 0.92** | **L4 wins, realism 0.92** |
| 1.2-3.0 | L4 wins, realism 0.92 | L4 wins, realism 0.92 |

The emergent hierarchy is the same for every gamma >= 1.15: **280
villages of 296 at 4 km, 20 market towns of 592 at 16 km, one
chef-lieu of 5,325** (~3,900 km², top/median ~18, ~17% non-farm).
It matches every anchor except "urban 8-12%", which counts only towns
>2,000 (the model then has ~5-7% in the chef-lieu; its 592-bourgs are
non-farm but not "urban" in that metric).

So: `market_scaling = 1.15` (the Bettencourt urban-scaling exponent) is
the natural value - the minimum at which the growth-optimal layout
becomes the central-place hierarchy - with `market_premium = 0.5` (top
of the market-access anchor) to make the hierarchy win robustly.
Higher gamma (1.5-2) keeps the same shape but strengthens the
hierarchy's advantage. The cost is growth: enabling gamma > 1 removes
village-to-village services, so the best achievable rate falls from
+0.1242 (flat, gamma 1, premium 0.25) / +0.1629 (flat, premium 0.5) to
+0.1193 / +0.1568.


### Scale: 1 million people with gamma=1.15, premium=0.5

The emergent hierarchy scales as a copy of the 100k one - counts x10,
tier sizes roughly constant (`benchmarks/sanity_agrarian_1m.py`):

| config | villages | market towns | regional | capital | urban | %/yr |
|---|---|---|---|---|---|---|
| flat 3,001 x 333 @ 3 km | 3,001 | - | - | - | 0% | **+0.1631** |
| q=(5,5,5) m=(2,2,5) @ 3.5 km | 2,882 x 318 @ 3.5 km | 114 x 636 @ 18 km | 4 x 1,271 @ 88 km | 1 x 6,357 | 8.4% | +0.1576 |
| q=(4,4,4) m=(2,3,3) @ 3.5 km | 2,818 x 309 @ 3.5 km | 172 x 617 @ 14 km | 10 x 1,852 @ 56 km | 1 x 5,556 | 13.0% | +0.1552 |

Two things change with scale:

- **The hierarchy stops winning.** At 100k the gamma=1.15 hierarchy
  edged the flat mesh (+0.1568 vs +0.1535); at 1M the flat mesh wins
  (+0.1631 vs +0.1576), because more villages make the mesh's mutual
  services more valuable while town services saturate. If a 1M world
  needs the hierarchy, gamma (or `market_premium`) has to be higher.
- **The top of the system stays small.** The capital lands at
  2,500-7,400 - the service premium saturates at market-town scale.
  A 1600s province of 1M had chef-lieux of 10-30k; the model needs
  denser hinterlands, more agglomeration, or non-food urban functions
  to get there.

The flat mesh remains the growth optimum; the realistic-looking 1M
hierarchy is `q=(5,5,5), m=(2,2,5)` at 3.5 km spacing (8.4% urban,
~31,000 km2).

## Status / open items

- Engine tests + integration are green; 9 bot-side tests still encode
  the old economy and are the bot agent's remit (`tests/bots/`).
- The realism suite (`growth_realism.py --system engine`) now measures
  the agrarian model through a compatibility adapter; its scores are
  not re-fitted yet (the suite was built for the fitted model).
- Calibration knobs with priors: `market_premium` (0.05–0.5, anchor
  `market_access_ratio`), `farm_workers_yield` (1.2–1.5),
  `surplus_mobility` and `migration_share`.
