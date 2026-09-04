# Bot scenario benchmarks + improvement plan

## Goal
Per-bot scenario suites (disjoint map sets) that run in seconds and
discriminate each personality's weaknesses. Used to score the 5 bots
(greedy, expander, aggressive, turtle, pro) before/after improvements.
`random` is retired, replaced by `pro` (no personality constraints).

## Design rules
- Focal bot is always faction 0 (A). Opponents: `stub` (passive) unless the
  scenario needs a live enemy (`aggressive` as raider).
- 2 factions per scenario (fast spawns), 30–100 turns, starting pops at or
  above train thresholds so action starts by turn ~5 (no 1000-turn waits).
- Each scenario: `{map, bots, turns, focal, goal}`. Goal types: `own_town`,
  `towns_ge`, `survive_capital`, `score_ge`, `enemy_owns` (restraint),
  `armies_zero` (no idlers).
- Runner: `benchmarks/scenario_bench.py`. Full sweep target < 60s.

## Suites (3 maps each, disjoint)

### Greedy (`maps/scenarios/greedy_*.json`)
1. `raid_hold` — A 3000 vs B 3000, 200km apart, 60 turns. Goal: own B's
   town at end (halved 1500 holds). Tests profitable-raid execution.
2. `skip_thin` — A 3000 vs B 800 (halves to 400, starves), 60 turns. Goal:
   B still owns its town at end AND focal score high (no wasted army).
   Tests raid selectivity. Current greedy FAILS (attacks everything).
3. `recycle` — A 5000 + idle army, no enemies, 30 turns. Goal: 0 idle
   armies at end (BUILD pop-add or found). Tests garrison recycling.

### Expander (`maps/scenarios/expander_*.json`)
1. `settle` — A 3000, empty east, 60 turns. Goal: ≥2 towns.
2. `guard` — A 3000 vs live `aggressive` 3000 300km away, 80 turns. Goal:
   still owns capital at end. Tests home guard. Current FAILS (marches
   settler out, loses capital undefended).
3. `chain` — A 3000 + second town 2000 far east, 80 turns. Goal: ≥3 towns
   (each town owes a settler).

### Aggressive (`maps/scenarios/aggressive_*.json`)
1. `viable` — A 3000 vs B fat 4000 nearby, 80 turns. Goal: own B's town
   (halved 2000 holds). Tests basic winning attack.
2. `starve_trap` — A 3000 vs B thin 900, 80 turns. Goal: B still owns at
   end (restraint) + focal score kept. Current FAILS (captures rubble).
3. `pair` — A 5000 (affords 2 armies) vs B 3000 + B guard army, 80 turns.
   Goal: own B's town (needs 2v1 stacking to beat the defender).
   Current FAILS (sends ones, trades).

### Turtle (`maps/scenarios/turtle_*.json`)
1. `defend` — A 3000 vs live `aggressive` 3000 250km away, 100 turns.
   Goal: still owns capital at end. Tests garrison defense.
2. `wake` — A 2000 (under 2600 rule) vs distant `aggressive`, 60 turns.
   Goal: ≥1 army by turn 40. Tests threat-responsive threshold.
   Current FAILS (never trains under 2600).
3. `cluster` — A capital 3000 + town 2000 100km away vs far `aggressive`,
   100 turns. Goal: own both at end (mutual support).

### Pro (`maps/scenarios/pro_*.json`, starts as greedy copy)
1. `opening` — fat neighbor + empty space, 80 turns. Goal: score (rewards
   raiding AND settling together).
2. `defense` — `turtle/defend` variant. Goal: survive + counter-take.
3. `endgame` — symmetric 2v2 towns 4000 each, 100 turns. Goal: higher
   score / eliminate B. Tests full combined game.

## Baselines (2026-09-04, current code — 8/15 in 2.1s)

| Bot | Scenario | Result | Key stat |
|---|---|---|---|
| greedy | raid_hold | PASS | holds B capital |
| greedy | recycle | PASS | 0 idle |
| greedy | skip_thin | FAIL | captures thin town, it starves (town gone) |
| expander | settle | PASS | 3 towns |
| expander | chain | PASS | 4 towns |
| expander | guard | FAIL | capital LOST (settler marched out undefended) |
| aggressive | viable | PASS | holds fat town |
| aggressive | pair | PASS | 2nd wave takes it after 1v1 trade (not stacking!) |
| aggressive | starve_trap | FAIL | captures 900 town, it starves |
| turtle | defend | FAIL | capital LOST (no garrison) |
| turtle | wake | FAIL | never trains (2000 < 2600 rule; aggressive kills t9) |
| turtle | cluster | FAIL | holds 1/2 (exclave undefended) |
| pro | opening | PASS | 4 towns (raid + 2 settles) |
| pro | defense | PASS | capital held |
| pro | endgame | FAIL | 2245–2245 mirror tie vs greedy (no symmetry-break) |

## Per-bot improvement ideas (tailored to the failures above)

### Greedy — learn selectivity, recycle idlers
- `skip_thin` fix: pre-compute `target.pop × (1 − build_efficiency) > death_threshold + margin` before marching; skip (or denial-raid deliberately) otherwise.
- `recycle` already passes; extend to mid-game idlers (armies 17/18 in empty3000 stood down the war): no enemy in range → BUILD pop-add into nearest own town.
- Raid commitment plans (idea 5): lock target, re-evaluate only on military intel (cuts the 11-turn dither seen on long marches).

### Expander — guard the homeland, pipeline settlers
- `guard` fix: never leave capital empty while forecast shows enemy inside N-turn march; settler waits or escorts.
- Score build sites (enemy distance × growth room × own support), not first-fit.
- Chain rule: each town past 1500 owes one settler (already emergent in `chain`, make it policy).
- Pre-issued succession marches: lineage survives decapitation by design (commander rule makes this the expander's signature mechanic).

### Aggressive — viability gating, real stacking
- `starve_trap` fix: same halve-vs-floor check as greedy, inverted into doctrine — never take rubble without a settler-army one march behind (two-wave plan).
- `pair` passes via waves today; true 2v1 arrival-sync should show in `viable` margins and `pro_endgame`: pair arrivals, don't trickle.
- Target selection: weight by leader score (dent greedy), not just nearest (farming irrelevance while the leader compounds).
- Forecast-gated offensives: don't leave home empty while a raid is plausibly inbound (no garrison — character stays all-out).

### Turtle — wake up, garrison, cluster
- `wake` fix: threat-responsive threshold (2600 peace → ~1200 as inbound ETA shrinks).
- `defend` fix: one home army after first contact; a garrison forces a real battle instead of a free capture.
- `cluster` fix: settle within mutual-support range; emergency last-turn train when the capital is about to fall (rules be damned, it's falling anyway).

### Pro — combine everything, break symmetry
- Starts as greedy copy: passes `opening`/`defense` by inheritance.
- `endgame` tie-break: needs what no tier has — combined arms (raid + settle + guard in one game), multi-wave planning, and leader-targeting. Build by porting each tier's fixed behavior behind a situation selector: defend when threatened (turtle), expand when safe (expander), raid when profitable (greedy), kill when advantageous (aggressive).
- Pro is the only bot allowed to ignore personality; judge it solely on the suite + full-game score.
