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
- Each scenario: `{map, bots, turns, focal, goal}`. Scoring is final
  focal-faction score only (pop + 1000×armies, same as game score).
  Scenario `goal` fields are retained in the JSON as documentation of
  what each map was built to test, but the number that counts is score.
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

## Final scores (campaign complete 2026-09-04; fast sweep 1.2s, slow ~10s)

| Scenario | Before | After | Δ | What changed |
|---|---|---|---|---|
| greedy_raid_hold | 3176 | 3172 | flat | correct already |
| greedy_recycle | 3592 | 4086 | +494 | settlers actually BUILD (latent note_move bug) |
| greedy_skip_thin | 2116 | 3467 | +1351 | viability gate; map redesigned (scarcity prices restraint) |
| expander_settle | 2114 | 2114 | flat | correct already |
| expander_chain | 4319 | 4319 | flat | emergent, now policy |
| expander_guard | 2000 | 1624 | holds* | was capital LOST; now holds + settles (*score lower, position won) |
| aggressive_viable | 3771 | 3771 | flat | correct already |
| aggressive_pair | 3782 | 4317 | +535 | departure-sync: clean 2v1, guard dies alone |
| aggressive_starve_trap | 2159 | 4038 | +1879 | viability gate; map redesigned (decoy + prize) |
| turtle_defend | 548 | 1109 | holds | was capital LOST; now holds (mutual annihilation) |
| turtle_wake | 0 | 1060 | alive | was killed t9; now lineages (+evac when rich enough) |
| turtle_cluster | 2730 | 2186 | -544 | accepted: baseline held by accident, now holds by design |
| pro_opening | 3240 | 4316 | +1076 | leader-target + full doctrine |
| pro_defense | 1109 | 1109 | holds | holds |
| pro_endgame | 2245 | 3249 | +1004 | counter-punch breaks the mirror (out-settles; takes still future) |

Slow suite: efficiency 59%→100% (= policy optimum 5254); succession 0→611;
snowball 3748→5681; attrition 4226 (held); endurance 3089 (foes tougher now);
Elo all-draws at 3000/60t (structural): pro 1501 / greedy 1501 /
aggressive 1500 / turtle 1499 / expander 1499 — nobody concedes anything.

## Starting baselines (pre-campaign, for the record)

| Scenario | Score | Notes |
|---|---|---|
| greedy_raid_hold | 3176 | holds B capital |
| greedy_recycle | 3592 | no idlers |
| greedy_skip_thin | 2116 | captures thin town, it starves (wasted army) |
| expander_settle | 2114 | 3 towns |
| expander_chain | 4319 | 4 towns |
| expander_guard | 2000 | capital LOST, headless town regrows |
| aggressive_viable | 3771 | holds fat town |
| aggressive_pair | 3782 | 2nd wave takes it after 1v1 trade (not stacking!) |
| aggressive_starve_trap | 2159 | captures 900 town, it starves |
| turtle_defend | 548 | capital LOST |
| turtle_wake | 0 | never trains; killed t9 |
| turtle_cluster | 2733 | holds 1/2 |
| pro_opening | 3240 | 4 towns (raid + 2 settles) |
| pro_defense | 1109 | survives, barely |
| pro_endgame | 2245 | mirror tie vs greedy |

Reading the gaps: selectivity costs greedy ~1000 (3176→2116) and
aggressive ~1600 (3771→2159); guard failure costs expander ~2300
(chain 4319 → guard 2000); turtle's three maps span 0–2733 (highest
variance, most headroom); pro ties its mirror (nothing learned yet).

## Why the tactical suite is not enough (and what covers the rest)

The 15 maps test single decisions over 30–100 turns: one raid, one
settle, one defense. They cannot see compounding (the 1100-turn wait
before the first train in empty3000), multi-war campaigns, succession
after commander death (expander t1183), staleness compensation at range,
clock-bank management over thousands of turns, or five personalities
interacting. A bot can ace all 15 and still misevaluate a 3000-turn game.

Since maps cost ~110ms (and even 1000-turn games cost ~2s), the answer is
more scenarios, not longer iteration. Planned strategic set (~10 maps,
all 2-faction, 150–1000 turns, est. total <20s):

| Scenario | Setup | Tests | Turns |
|---|---|---|---|
| `succession` | focal loses capital ~t15, settler en route | posthumous lineage score at 200 | 200 |
| `snowball` | focal takes first capital early | compounding at 500 | 500 |
| `comeback` | focal poor 500 vs rich 5000 turtle | economy + raiding from behind | 500 |
| `longpeace` | 2 growers, far apart, no contact | pure train cadence on the logistic curve | 1000 |
| `attrition` | symmetric 3v3 towns vs greedy | combined arms | 500 |
| `staleness` | enemy 800km away | delay-compensated distant raid | 300 |
| `siege` | many thin towns around | restraint at scale (no rubble) | 300 |
| `guard_duty` | rich aggressive vs focal, 300 turns | long defense | 300 |
| `opening` | 1200 starts (action by t50) | early economy | 150 |
| `endurance` | 1000-turn free play vs mixed pair | generalship | 1000 |

Plus `empty_3000` itself (~4s, 5 bots) as the integration gate. Fast
sweep stays tactical (<5s); full sweep incl. strategic stays <30s.

## Personality triangle (doctrine)

- **Aggressive > Expander**: raid kills the settler faction before it
  compounds. Proven: `expander_guard` (capital falls), empty3000 t1183.
- **Expander > Turtle**: out-settle the sleeper. Proven territorially:
  `expander_outsettle` towns_held 3v2 at 200 AND 500 turns — but score
  still trails (1856v2441, 2499v3232) because new towns start at 500 and
  turtle never spends. Score converts only with raiding follow-through
  (future expander work: raid turtle's fat capital with built force).
- **Turtle > Aggressive**: garrison makes raids unprofitable. ASPIRATIONAL
  — `turtle_defend` currently fails (no garrison). The edge to earn.
- **Greedy** is outside the triangle (pure selfish raid economics).
- **Pro beats all**: currently takes turtle+expander, ties greedy/aggressive
  (Elo 1531/1529/1527 — the tie cluster to break).

Each edge has its natural metric (raid success / survival / towns_held);
score is the recorded baseline number, doctrine notes are the reading.

## Slower suite results (strategic_bench.py — 8.3s total, budget <30s)

Strategic maps (focal pro): succession 0 (head-on meeting engagement
lost; lineage lesson), guard_duty 0 (overrun by 8000-aggressive),
snowball 3748, staleness 4654, siege 3347, opening 1391, comeback 821,
attrition 4226, endurance 6424, longpeace 3124 (efficiency 59% of policy
optimum 5254), outsettle 1856 (towns 3v2 — see triangle).
Policy optimum (in-process, 1.7s): best = hold/never-train, 5254.
Self-play: 0-diff mirrors (stable, uninformative). Elo home-and-away:
pro 1531 / greedy 1529 / aggressive 1527 / expander 1457 / turtle 1456
— everyone takes turtle, otherwise mutual failure (the tie cluster).
Fast suite: 15 maps, 1.7s total (budget <5s).

## Per-bot improvement ideas (tailored to the failures above)

Build order (each step must move its suite numbers before the next
starts): turtle defense → aggressive viability → greedy selectivity →
expander guard → pro tie-break. Rationale: turtle's garrison closes the
T>A triangle edge everything else assumes; viability gating is shared
doctrine for both raiders; pro integrates last.
Shared foundations already landed (see `BOT_TIME.md`): incremental
update, staged decide, memoized staleness, quiet replay, plan queue,
clock effort, slim wire, measured margins. Bots also have carryover
backlogs, Fischer/byo-yomi clocks, and the ideas-1–6 test files.

### Greedy — learn selectivity, recycle idlers (triangle: outside, pure raid economics)
- `skip_thin` fix: pre-compute `target.pop × (1 − build_efficiency) > death_threshold + margin` before marching; skip (or denial-raid deliberately) otherwise.
- `recycle` already passes; extend to mid-game idlers (armies 17/18 in empty3000 stood down the war): no enemy in range → BUILD pop-add into nearest own town.
- Raid commitment plans (idea 5): lock target, re-evaluate only on military intel (cuts the 11-turn dither seen on long marches).

### Expander — guard the homeland, pipeline settlers (triangle: beats turtle by out-settling 3v2; loses to aggressive raids)
- `guard` fix: never leave capital empty while forecast shows enemy inside N-turn march; settler waits or escorts.
- Score build sites (enemy distance × growth room × own support), not first-fit.
- Chain rule: each town past 1500 owes one settler (already emergent in `chain`, make it policy).
- Pre-issued succession marches: lineage survives decapitation by design (commander rule makes this the expander's signature mechanic).

### Aggressive — viability gating, real stacking (triangle: beats expander by raiding first; loses to turtle garrisons once they exist)
- `starve_trap` fix: same halve-vs-floor check as greedy, inverted into doctrine — never take rubble without a settler-army one march behind (two-wave plan).
- `pair` passes via waves today; true 2v1 arrival-sync should show in `viable` margins and `pro_endgame`: pair arrivals, don't trickle.
- Target selection: weight by leader score (dent greedy), not just nearest (farming irrelevance while the leader compounds).
- Forecast-gated offensives: don't leave home empty while a raid is plausibly inbound (no garrison — character stays all-out).

### Turtle — wake up, garrison, cluster (triangle: beats aggressive by making raids fail; loses to expander's spread. HIGHEST priority — closes the triangle)
- `wake` fix: threat-responsive threshold (2600 peace → ~1200 as inbound ETA shrinks).
- `defend` fix: one home army after first contact; a garrison forces a real battle instead of a free capture.
- `cluster` fix: settle within mutual-support range; emergency last-turn train when the capital is about to fall (rules be damned, it's falling anyway).

### Pro — combine everything, break symmetry (triangle: beats all)
- Starts as greedy copy: passes `opening`/`defense` by inheritance.
- `endgame` tie-break: needs what no tier has — combined arms (raid + settle + guard in one game), multi-wave planning, and leader-targeting. Build by porting each tier's fixed behavior behind a situation selector: defend when threatened (turtle), expand when safe (expander), raid when profitable (greedy), kill when advantageous (aggressive).
- Pro is the only bot allowed to ignore personality; judge it solely on the suite + full-game score.
- Scoreboard to beat: Elo tie cluster 1531/1529/1527, endgame 2245–2245, efficiency 59% (longpeace 3124/5254). First milestone: take a side-game off greedy.
