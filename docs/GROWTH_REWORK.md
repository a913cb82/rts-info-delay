# Town growth: the agrarian economy

Each town lives off the land around it, trades food with its neighbours,
learns better methods from bigger towns, and grows or shrinks depending on
whether its people are fed. One turn is one week. This doc describes the
model as it stands, the settings it uses, the settlement patterns that grow
fastest, and the historical pattern it is measured against.

## How it works

### 1. Land — who farms what
Every scrap of farmland belongs to its nearest settlement. Land near home
yields fully; the far edge yields less, because walking there eats the day.
And hands limit you: each farmer feeds 1.3 mouths, so a town harvests
whichever is smaller — what its workers can farm, or what it owns.

        Y0 = decayed yield of the farmed disc (5 km radius)

- `farm_radius_km` = 5 — a day's walk to the fields and back
- `rural_density` = 30/km² — mouths an acre feeds at subsistence
  (England/France around 1600)
- `farm_decay_at_radius` = 0.9, `farm_decay_shape` = 2.0 — yields fade
  smoothly with distance from home

### 2. Services — farming eats first
Count the hands the harvest needed; everyone left over is a smith, weaver,
or trader. Farmers are the requirement, services are whoever remains —
and improved farms need fewer hands, so improvement frees services.

        serv = max(0, P − Y0/(1.3·(1 + last improvement)))

### 3. Improvement — skilled towns teach farms to yield more
**(a) Help (quantity).** Every service crew helps neighbours, fading with
distance (grain carts travel ~20 km a day; each 20 km halves what arrives).
Big crews count superlinearly — ten smiths together beat ten apart.

        mkt = Σ help · 2^(−d/20), running out to 150 km

- `cart_distance_km` = 20 — a day's cart trip
- `market_scaling` = 1.15 — big crews punch ~15% above weight

**(b) Methods (quality ceiling).** Help only matters if the *methods* exist.
Every town's teaching range grows smoothly with its size: 10 km (a day's
walk) at and below 1,000 people, ~60 km at 5,000, 150 km (the farthest word
travels) at and above 50,000. Small towns teach their patch, centers their
district, great cities their province. No teacher in range → capped low,
however much effort arrives.

        range(P) = 10 + 31·ln(P/1000) to 5k, then 60 + 39·ln(P/5000) to the 150 cap
        ceiling = mi · min(1, (best_in_range/2356)^(γ−1))

**(c) Memory.** Towns pass on what they received — this turn's offer is
services × (1 + last turn's improvement), so richness walks outward week by
week. A brand-new measurement starts from plain neighbours.

        offer = serv · (1 + last),    improvement = ceiling · mkt/(mkt + P)

### 4. Trade — hungry mouths eat first
Nearest pairs first: while one side holds more food per person, it sends
food until the two are even. Big or small, all mouths count the same — a
starving town eats before a comfortable village overeats, and no donor ever
drops below the town it feeds. Hauling loses some food on the way (carriers
eat, grain spoils, tolls take their cut), and less is lost when the receiver
is big enough to have real roads.

        sent f, arrived f·delta,    delta = exp(−tau·d)
        tau = melt·2356/(2356 + P_receiver)

- `melt_per_km` = 0.015 — about 1.5% lost per km (benchmarks; the game
  itself still runs lossless at 0.0 until bots are re-tested)

### 5. Births and deaths
Towns have a fixed number of surviving babies each year. Deaths fall when
food per person rises above need and climb steeply in hunger — so food acts
through deaths, not births. Break-even is ~21% over need: towns must be
overfed to hold their people.

        births = b·P,    deaths = m·P·(S/P)^−p

- `birth_rate` = 24/1000/yr surviving births (35 born × ~0.7 survive infancy)
- `death_rate` = 31/1000/yr; `starvation_elasticity` = 1.3 (half rations
  kill ~2.5× normal)

### 6. Migration — slow drift to the towns
A trickle of everyone (0.5%/yr) plus more mobile service folk (5% of
services) moves each year, uphill toward bigger towns that can feed the
arrivals. Every arrival is someone's departure — boomtowns grow on village
births. Nothing appears from nothing: only births and deaths change the
total number of people.

### 7. Death floor
Towns at 10 or fewer people vanish — too few hands to hold the fields.

## Settings (every one a real-world quantity)

| setting | value | meaning |
|---|---|---|
| `farm_radius_km` | 5 | nobody farms further than a day's walk |
| `rural_density` | 30 /km² | subsistence density, England/France c.1600 |
| `cart_distance_km` | 20 | carting doubles grain price over this distance |
| `turns_per_year` | 52 | one turn is one week |
| `farm_workers_yield` | 1.3 | mouths fed per farmer |
| `farm_decay_at_radius` / `farm_decay_shape` | 0.9 / 2.0 | far fields yield less, smoothly |
| `birth_rate` | 24 /1000/yr | surviving births per person per year |
| `death_rate` | 31 /1000/yr | deaths per person per year at full rations |
| `starvation_elasticity` | 1.3 | how steeply hunger kills |
| `max_improvement` | 0.25 | best methods grow ~25% more |
| `market_scaling` | 1.15 | big crews punch ~15% above weight |
| `migration_share` / `surplus_mobility` | 0.005 / 0.05 /yr | background drift / footloose services |
| `migration_scale_km` | 50 | moves fade with distance |
| `melt_per_km` | 0.015 | food lost per cart-km (benchmarks; game default 0.0) |
| `info_speed` | 150 | farthest anything travels or is seen (km/turn) |
| `town_min_population` | 10 | settlements at or below this die |

Derived: one full farm ring feeds ≈ 2,356 people — the yardstick for
service crews and road-building alike.

## What grows fastest

Growth is measured per person per year, settled (3 warmup turns, then
measured). Found by hand-built shapes plus search over spacings and sizes
(`benchmarks/hierarchy_opt.py`, `benchmarks/bo_hierarchy.py`).

### 100k district

| tier | count | size each | spacing | share |
|---|---|---|---|---|
| villages | ~300 | 300 | 4 km | ~85% |
| market towns | ~19 | 600 | 18 km | ~11% |
| center | 1 | 5,000 | central | ~5% |
| big city | 0 | — | — | — |

Land ~4,500 km² (~23/km²); growth +0.42/yr. Bourgs-only and a lone
mid-size town tie close behind; flat villages and lone giants lose.

### 1M province

| tier | count | size each | spacing | share |
|---|---|---|---|---|
| villages | ~3,000 | 300 | 4 km | ~90% |
| market towns | ~150 | 600 | 18 km | ~9% |
| centers | 1 | 5,000 | central | ~0.5% |
| regional capital | 0 | — | — | — |

Land ~43,700 km² (~23/km²); growth +0.44/yr. Bourgs-only ties (+0.43);
the single center is nearly a token — at this scale one hub cannot feed
a province through melting supply lines (a lone giant starves at −0.37).

### Closest to reality (needs pushy settings)

With strong agglomeration, high headroom, and cheap hauling
(γ1.3/prem.5/melt.005), upper tiers earn their keep and the 4-tier stack
ties for first (+0.79 vs +0.82 for uniform mid towns, flat +0.32):

| tier | count | size each | spacing | share |
|---|---|---|---|---|
| villages | ~3,000 | 300 | 4 km | ~84% |
| market towns | ~150 | 600 | 18 km | ~9% |
| centers | ~13 | 5,000 | ~64 km | ~6% |
| regional capital | 1 | 20,000 | central | ~2% |

Each tier owns a distinct teaching shed (bourgs their patch, centers
their district ~60 km, the regional its province ~114 km+) — that is what
pays for the fourth tier. At the standard settings above it still loses,
because extra big mouths cost more food than their saturated lift repays.

## Reality goals: 100k district and 1M province

What the model should reproduce (France c.1600, ~18M on 550k km²;
~40,000 parishes; anchors in `benchmarks/realism_ref.json`). A 100k area
is about one *election* (~3,000 km² at ~33/km²); a 1M area is a large
province (Normandy scale, ~30,000 km²). Same spacings at both scales —
only a top tier appears with scale.

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
empty).

## Where the model matches and misses

- **Market towns: exact.** ~150 bourgs at 1M, ~19 at 100k — count, size,
  and spacing all land on the anchors.
- **Centers and regionals: close, but only when pushed.** Standard
  settings grow one token center; the pushy settings grow 13 centers and
  a 20,000 regional, near the historical sizes and shares. Courts, church,
  walls, and rents — the non-food reasons cities exist — are still
  unmodeled, so upper tiers have to earn purely through food and teaching.
- **Villages: too many and too small.** ~3,000×300 vs ~1,700×~430, because
  founding a settlement costs nothing and near fields always reward one
  more split. Fixed costs per settlement (common pasture, church, mill,
  defence) would push villages up toward parish size.
- **Too spread out.** ~23/km² wall-to-wall vs ~33/km² nucleated with empty
  hills and woods between. Same missing member: without terrain or fixed
  costs the model tiles the map instead of clumping. Richer land does not
  fix this — 2.5× fertility grows bigger tops, not denser settlement.
- **A touch hot.** +0.4/yr at 100k vs 0–0.3 recorded; 1M runs at history's
  pace.

## Open items

- Settlement fixed costs (village size, density, nucleation).
- Non-food urban income (upper tiers at standard settings).
- Promote `melt_per_km` 0.015 to the game default (needs bot re-testing;
  9 bot-side tests still encode older economies — the bot agent's remit).
- Longer searches at 1M under the pushy settings (4-tier co-optimal on
  hand shapes; a search may refine sizes and spacings).
