# Bots — Strategy Plan

## Goals

- Every faction trains when it can afford it and builds steadily through every game.
- On empty.json (5 isolated capitals, 2000 turns) each faction founds 8+ new towns.
- On full.json (420 towns) every bot stays active, expands into low-density frontier,
  and contests territory through capture.
- All five bots keep distinct personalities while sharing reliable training,
  movement and building primitives.

## Shared Mechanics

- Map 1000×1000, 5 factions on pentagon R=280 around 500,500.
- Growth: logistic 0.001·P·(1−P/100k) with crowding multiplier (1−total),
  total = Σ asym·(d_eq/dist)^0.8 for neighbours within 150 km,
  d_eq = 0.1·√min(pop), asym = 1+0.01·ln(popB/popA).
  death_threshold = 500, pop_change is net end-of-economy-phase delta.
- Orders via messenger: remaining_dist = dist(capital, order_target)/150 turns.
  Delivered when ≤0; checks projected army position within 10 km of from_x,from_y.
  BUILD consumes army; if a town is within 10 km of the build point it gains 500
  pop, otherwise a new town spawns with 500 pop at the build point.
  Army speed 50 km/turn, interact_radius 10 km, info_speed 150 km/turn.
- Scoring = Σ pop + 1000·armies. Capture: surviving army within 10 km of enemy
  town flips it, pop *= 0.5.

## Shared Primitives in `common.py`

- `BotState` stores `world`, `turn`, `faction`, and a local
  `armyTargets: dict[army_id → (tx,ty)]` updated whenever the bot issues
  MOVE_TO and cleared on BUILD, army_death or arrival. `apply_events`
  extended to sync `has_target/target_x/target_y/is_fresh` from
  `army_move` and `army_spawn` events so `BotState` matches engine.
- `can_train_safely(town, conservative)`: survive threshold
  non-conservative pop ≥ 1600, conservative pop ≥ 2600 and outside
  35k–65k peak window, and pop ≤ 90k. `can_train_here` adds
  distance-aware extra 400 per turn of stale info and pending-TRAIN guard.
- Growth tracking: `BotState` stores `_prev_pop` and `_growth` per town
  from net pop_change; `overcrowded_clusters()` groups own towns with
  negative growth within 150 km, `should_train_for_overcrowding(town)`
  picks the smallest town per cluster (one train fixes the cluster).
- `find_build_site(state, config, ref_x, ref_y, salt)`: 20 deterministic
  samples angle = hash%3600/3600·2π, dist = 80–350 km from ref point
  (tuned per bot), clamped to map, scored by
  min_dist_to_any_town and crowding estimate (neighbours within 150 km).
  Accept only >20 km from every town (10 km + 10 km safety).
  Return best by (min_dist desc, crowding asc).
- `nearest_enemy_town` and `nearest_enemy_army_forecast` helpers
  reuse `_forecast_pos` for 1-turn prediction.

## Per-Bot Behaviour

### expander — The Colonist
- Train every town that passes `can_train_here` non-conservative;
  also trains 35k–65k peak towns only if `should_train_for_overcrowding`.
  Farm tier 8k–34k is preserved (not trained when growing >5/turn unless overcrowded).
- Idle armies (no target, no viceroy): find site expanding outward from
  army position (120–350 km, salt 11), MOVE_TO. If already moving and
  within 20 km of its target, BUILD at target. Always building, never
  wandering. Most prolific builder.

### random — The Wanderer
- Train via `can_train_here` with 50% peak throttle (skip if 35k–65k and hash%2==0); overcrowding emergency overrides peak block.
- Idle armies: 60% build (100–350 km from army), 40% wander to random
  own town. When moving, same BUILD-on-arrival rule as expander.

### turtle — The Fortifier
- Train only when every own town ≥2600 and none in 35k–65k peak,
  via `can_train_here` conservative (overcrowding emergency still allows
  one peak town per cluster), and only one train per turn.
- Build at most one army at a time, site 40–120 km from most populous
  own town. Otherwise garrison: idle armies drift to nearest own town
  if >20 km away.

### aggressive — The Conqueror
- Train via `can_train_here` non-conservative (peak preserved, overcrowding allowed).
- Combat: 1v1 results in equal deaths, 2v1 results in 0 deaths for the pair.
  Stacks armies for 2v1 by sending all idle armies to a single focal
  enemy town nearest own capital (info delay makes far coordination hard).
  Uses `BotForecast` to chase enemy armies at their delay-compensated position.
- Priority: if enemy towns exist, all idle armies MOVE_TO nearest enemy
  town (capture via proximity, never BUILD on enemy town); else if
  enemy armies exist MOVE_TO forecast position; else fall through to
  expander-style BUILD. Moving armies with has_target are left to arrive,
  no thrash.

### greedy — The Raider
- Train most aggressively via custom 1500 threshold plus `should_train_for_overcrowding` and pending guard.
- Same 2v1 stacking as aggressive when attacking, but build distances
  80–300 km (shorter than aggressive 120–340 km).
- Same priority as aggressive but with closer build distances when
  expanding (80–280 km) and willingness to train one band lower.
  Otherwise identical chase-then-build logic, ensuring the two fighters
  differ only in build reach and training eagerness.

## BotForecast (separate from BotState)

Constructed as `BotForecast(state, config)` each turn. Basic mode interpolates
any moving army forward by `dist(capital, army)/info_speed * army_speed` to
compensate info delay (needs target from latest `army_move` events). Helpers:
`forecast_army_pos(army, turns_ahead)`, `forecast_all_armies()`.

Advanced hooks (stubs for later): `with_my_orders(orders)` (clamps my movers
at target, predicts BUILD → town), `with_en_route_orders(orders)` (pending
BUILD messengers become towns), `forecast_battles()` (weakness check on
forecast positions).

## Ordering Protocol

1. Snapshot own towns and armies at start of `decide_orders`.
2. Emit TRAIN for qualifying towns first (pop deduction happens this turn,
   growth already accounted for in pop_change).
3. For each own army: skip viceroy with target; if has_target check
   distance to target — BUILD if ≤20 km else leave moving; if idle
   choose action per archetype and emit single order.
4. Deterministic via `_hash(turn, id, salt)` for all random choices,
   no `random` module in bots.

## Success Criteria

- Empty 2000-turn game: ≥40 total towns, every faction ≥6 towns,
  town_spawn ≥30, army_spawn ≥40, max faction pop spread stays reasonable.
- Full 500-turn game: all factions remain alive, score and settlement
  bars diverge per strategy, no bot stalls or crashes.
- `pytest` passes, deterministic replays identical.
