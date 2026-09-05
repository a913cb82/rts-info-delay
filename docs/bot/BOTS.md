# Bots — current guide

Living reference for bot work: personalities as coded, shared machinery,
the intel model, and the mechanics that matter. Entry point: `README.md`.
Strategy: `GTO.md`. History lives in `BOT_WORKLOG.md`, numbers in
`BOT_BENCH.md`, open plans in `BOT_PLAN.md`, clock infrastructure in
`BOT_TIME.md`.

## Personalities

Five bots (`src/bots/`), distinct characters. `stub` is passive harness
furniture for scenarios, not a personality. There is no `random` bot
(retired pre-campaign, replaced by `pro`).

### greedy — The Raider
- Trains most eagerly: custom 1500 floor (vs 1600 shared) + overcrowding
  reps + pending guard. Same 1500 + distance rule, no fudge beyond it.
- Attacks nearest *viable* town: `pop × 0.5 > 700`, i.e. target pop > 1400
  (captured-half must clear the death floor + margin). Duel-only gating —
  in multi-faction wars every town is viable (denial-raids pay there).
- No actionable contact → first settler probes (S0 scout: 50 km hops,
  rubble-avoiding, found-fallback); later settlers expand (sites 80–300
  km); no site → march home for the +500 pop-add recycle. Holds one home
  vs inbound/second-wave (shared defense trio, below — ungated, unlike
  pro's duel-only hold).

### aggressive — The Conqueror
- Trains via `can_train_here` non-conservative (peak preserved except
  overcrowding emergencies).
- Targets by faction strength per km (leader-targeting: dent the leader),
  filtered through the same duel-only viability gate as greedy.
- Departure-sync: a lone army holds home while its town can retrench
  (pop ≥ 2× cost) when the target is defended, so packs arrive together;
  trickles vs undefended targets. Arrival-sync was tried and failed
  (1-turn decision + 1-turn messenger lag vs 50 km/turn) — sync departures,
  never arrivals.
- No actionable contact → scout-first like greedy (faction-ray sweep);
  no viable targets → chase foe armies at forecast positions; else expand
  (sites 120–340 km, moves now noted — the old branch forgot, causing
  zigzag re-dispatches). Keeps one home army vs inbound/second-wave like
  greedy (ungated), but never hoards beyond that: all-out is the character.

### expander — The Colonist
- Trains via `can_train_here` non-conservative. Guard rule keeps one home
  vs inbound/second-wave; otherwise every army is a settler, outward
  120–350 km (first probes as S0 scout). No evac by design — accepts
  decapitation, wins by spread.
- Chain behavior (each established town owes a settler) is emergent and
  kept as policy. Loses to early raids (proven), out-settles turtles
  (proven territorially, score lags: new towns start at 500).

### turtle — The Fortifier
- Threat-responsive bars per town: 1200 (ETA ≤ 4) / 1700 (≤ 10) / 2000
  (sleeping lightly while no threat shows anywhere) / 2600 (hoarding).
  Threat is per-town (armies imputed to the own town nearest *them*).
  One train per turn, max.
- Peacetime picket: single-town factions keep one blind army; multi-town
  factions hoard until threats show. KNOWN GAP: sub-1500 relaxed trains
  don't survive the 1000 cost (1200 − 1000 = 200 < 500) — the survive
  floor is specified in `BOT_PLAN.md`, not yet coded.
- Recall settlers to the capital when threatened (2v1 assembly) unless
  hopeless; cap-concentration (never split garrisons); threatened home
  armies hold position, never dispatch.
- MOVE_CAPITAL evac when hopeless + capital ≥ 2× cost, aimed away from
  the threat. Needs a 1-turn lead now (economy spawn); fails permanently
  if the viceroy dies. Builds close (40–140 km), one builder at a time.

### pro — No Personality
- Greedy base (1500 trains, recycle, duel home-hold) + leader-targeting +
  departure-sync + evac, gated by situation: counter-punch rope-a-dope in
  peer duels (hold-all vs field armies, counter the spent foe), pure
  pressure in big wars. Duel-only gating throughout (P5–P7 lessons).
- Empty-field economy: with no foes anywhere, holds and compounds
  (matches the 5254 policy optimum exactly). Judged solely on suite +
  full-game score.

## Shared machinery (`common.py`)

- `BotState`: seen-only world mirror (holds only delivered updates) +
  `turn/faction`; upsert parser (absolute create/update/remove, unknown
  kinds ignored, deaths clear trackers); `evac_ordered` flag + amnesia
  wipe on stream jump (world, trackers, plans, `last_seen`, trails);
  `_army_targets` (own MOVE_TO notes via `note_orders`, cleared on
  BUILD/death/arrival); `_pending_trains/_builds` confirmed by own
  `town_update` pop drops; `last_seen` delivery stamps + per-army
  position trails (foe velocity stands in for intent); `_prev_pop/_growth`
  (per-turn net deltas, reset on turn advance), overcrowding clusters
  (negative-growth towns within 150 km; smallest per cluster trains),
  memoized `stale_turns` (dist-to-capital/info_speed), fingerprint-gated
  standing-order replay + plan queue + clock effort (see `BOT_TIME.md`).
  `is_quiet`: any update breaks sleep.
- S0 scout (`_scout_id/_scout_leg`, hop notes in `_army_targets`): probe
  before founding, rubble-avoiding, viable/army contact hands to normal
  logic (stale hop note dropped); builds stages never found on scout
  waypoints. `drop_dead_notes` clears trail-stale notes (messenger-died
  orders strand otherwise). `order_move` quiescence gate: MOVE_TO only
  from converged intel (mid-course retargets of movers are structurally
  dead) — all 19 dispatch sites route through it.
- Defense trio (greedy/aggressive/expander/pro): `inbound_eta` (per-town
  inbound ETAs ≤ 8 turns; stationary foe guards excluded),
  `note_wave_watch` (vanished own army → hold one home 6 turns),
  `should_hold_home` (keep ≥1 army on a threatened town).
- `staging_eta` (shared): a known foe town inside home LOS (150 km) of an
  own town is raid staging → positioning-threat (recall/hold). Never a
  spend-signal: mustering costs 1000 against a town that may never
  produce force, while recall is free insurance. Turtle merges it into
  `threat_eta`; spend bars everywhere stay army-only.
- Turtle last-stand fires only when home defenders are strictly
  outnumbered (D < N) at ETA ≤ 3 — a defender that mutual-saves holds,
  never guts its own town (t9 lesson: spending kills as surely as raids).
- `find_build_site`: deterministic hash samples, scored by
  (min-dist-to-any-town desc, crowding asc), >20 km from every town.
  Reach per bot above; the spin is seeded by army id (`who`), never the
  turn — re-queries hold headings instead of roulette-retargeting.
- `BotForecast`: delay-compensated army positions
  (`forecast_army_pos`, `forecast_all_armies`); `with_my_orders`
  partially built, `with_en_route_orders` / `forecast_battles` stubs.
- Decide shape: greedy/pro run lazy trains→moves→builds stages (clock can
  truncate to trains-only); aggressive/expander/turtle run single loops.
  Deterministic throughout (`_hash`, no `random` module).

## Intel model (updates, not events)

The only honest mental model: **bots see snapshots, late — never events,
never the map**. Each turn the engine observes (line-of-sight discs,
`line_of_sight` 150 km, own entities always seen), stamps what was seen,
and delivers when each observation's delay releases
(`t + dist/capital/info_speed ≤ now`, exact) — but only observations
from turns at or after the faction's last landing S. Three gates
(tagged + released + ≥ S), no exceptions.

- **Wire**: `town_update{id,x,y,faction,population,is_capital}` (pop 0 =
  dead) and `army_update{id,x,y,faction,alive,is_viceroy}`
  (`alive False` = dead — that *is* the battle report). No intent, no
  battle events, no map, no seer lists. Newest passing snapshot wins per
  entity; unchanged snapshots stay silent, so quiet worlds cost ~nothing.
- **Flight**: a faction with a viceroy airborne is blind *and mute* —
  no turns sent, no orders read, clock frozen.
- **Landing**: the runner sets S and resets send-state; the bot wipes on
  its own remembered MOVE_CAPITAL order (stream jump = success, wipe
  everything; sequential = failure, carry on). Survivors re-announce
  paced by delay; the S−1 transient is never known; ghosts are
  impossible — the wiped bot has no memory for a corpse to haunt.
- **Deaths are uniform**: told-alive implies told-dead through the same
  three gates, no special cases. Force-counting is trustworthy; the +1
  doctrine can rely on it. Own capital (dist 0) is the only fresh reading.

## Mechanics that matter

- **Turn order**: command → propagation (messengers advance/deliver) →
  movement (50 km/turn, path-blocking stops at closest approach) →
  combat (simultaneous deaths + contested takes) → economy (growth, TRAIN spawns,
  BUILD consumes incl. viceroy founding, deaths) → knowledge (ledger
  generate + evict).
- **Combat (weakness)**: armies count enemies within 10 km; an army dies
  if any enemy in radius has weakness ≤ its own. 1v1 *and* 2v2 annihilate
  everybody; any strict outnumbering (2v1, 3v2) kills clean with zero
  casualties. +1 local superiority is the whole game.
- **Order lag** (all commands ride messengers at 150 km/turn): MOVE_TO
  measures capital→from, BUILD capital→site, TRAIN capital→town,
  MOVE_CAPITAL capital→capital (dist 0, same-turn delivery). FIFO per
  entity, dead letters dropped. Decisions span both legs: intel was stale
  coming in, the order is stale going out (~2× one-way lag round trip).
- **TRAIN** is one-shot (deduct, spawn iff pop ≥ 1000). Quirk: it credits
  the *pre-capture* owner — a town captured the same turn still spawns
  for its old faction at the enemy's expense.
- **Capture**: survivor within 10 km flips the town, pop halved, capital
  demoted. **Never creates capitals — beheading is permanent.**
- **MOVE_CAPITAL** is a pre-programmed TRAIN: messenger → economy execution
  (deduct, demote old capital *at train time*, spawn viceroy with march
  target) → normal march → a later economy BUILD-step founds (pop 500)
  and promotes. The viceroy marches *through* combat and can be
  intercepted; if it dies, the beheading is permanent. No capital exists
  mid-flight; second orders during flight die at send (no capital to
  target); if the capital falls before economy, the intent drops. Needs
  a 1-turn lead — same-turn rescue is structurally impossible.
- **Economy**: logistic 0.001·P·(1−P/100k) minus crowding, ~1–25 pop/turn
  realistic. A train→build cycle is −500 *now*; at these growth rates it
  repays over hundreds of turns. Spending is the scarce resource.
- **Score**: Σ pop + 1000·armies. Training converts 1000 pop to a 1000
  army (neutral); everything after that (trades, builds, compounding)
  decides whether it profited.

## Hard lessons (indexed, not repeated)

- Affordability ≠ desirability (forecast episode): gating *whether* a
  train is affordable without asking *what it's for* unlocks wasteful
  distant trains (−530 uniform). Demand gates are the open work.
- Delayed intel can't be outgrown: 4-turn growth (~+4) can't close 100+
  intel gaps at 1200+ bars. Stale-threshold failures need risk posture,
  not arithmetic.
- Mirrors break by intelligence, not timing: synchronized decisions come
  from identical thresholds + intel; jitter was tried on paper and
  rejected — foresee the 1v1, decline or convert it.
- The fudge postmortem: the old +400/turn distance buffer was load-bearing
  as a *spending brake*, not as staleness compensation. Its replacement
  must brake spending deliberately (demand), not accidentally.

## Gates for future work

Fast suite (`scenario_bench.py`, ~1.5s) per change; strategic suite
(`strategic_bench.py`, ~10s) at milestones; `empty_3000` rematch read as
a trade ledger; `pytest` green. Binding baselines: `BOT_BENCH.md` fog-era
table (campaign/delayed tables are record, not targets).
