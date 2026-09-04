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
   Tests raid selectivity. Pre-campaign greedy FAILED this (attacked
   everything); fixed by the viability gate (skip_thin 2116→3467).
3. `recycle` — A 5000 + idle army, no enemies, 30 turns. Goal: 0 idle
   armies at end (BUILD pop-add or found). Tests garrison recycling.

### Expander (`maps/scenarios/expander_*.json`)
1. `settle` — A 3000, empty east, 60 turns. Goal: ≥2 towns.
2. `guard` — A 3000 vs live `aggressive` 3000 300km away, 80 turns. Goal:
   still owns capital at end. Tests home guard. Pre-campaign FAILED
   (marched settler out, lost capital undefended); fixed by guard rule.
3. `chain` — A 3000 + second town 2000 far east, 80 turns. Goal: ≥3 towns
   (each town owes a settler).

### Aggressive (`maps/scenarios/aggressive_*.json`)
1. `viable` — A 3000 vs B fat 4000 nearby, 80 turns. Goal: own B's town
   (halved 2000 holds). Tests basic winning attack.
2. `starve_trap` — A 3000 vs B thin 900, 80 turns. Goal: B still owns at
   end (restraint) + focal score kept. Pre-campaign FAILED (captured
   rubble); fixed by the viability gate (map redesigned: decoy + prize).
3. `pair` — A 5000 (affords 2 armies) vs B 3000 + B guard army, 80 turns.
   Goal: own B's town (needs 2v1 stacking to beat the defender).
   Pre-campaign FAILED (sent ones, traded); fixed by departure-sync.

### Turtle (`maps/scenarios/turtle_*.json`)
1. `defend` — A 3000 vs live `aggressive` 3000 250km away, 100 turns.
   Goal: still owns capital at end. Tests garrison defense.
2. `wake` — A 2000 (under 2600 rule) vs distant `aggressive`, 60 turns.
   Goal: ≥1 army by turn 40. Tests threat-responsive threshold.
   Pre-campaign FAILED (never trained under 2600); fixed by threat bars.
   LAPSED in the delayed-intel transition (scores 0 on current tree) —
   see Delayed-intel era below.
3. `cluster` — A capital 3000 + town 2000 100km away vs far `aggressive`,
   100 turns. Goal: own both at end (mutual support).

### Pro (`maps/scenarios/pro_*.json`, starts as greedy copy)
1. `opening` — fat neighbor + empty space, 80 turns. Goal: score (rewards
   raiding AND settling together).
2. `defense` — `turtle/defend` variant. Goal: survive + counter-take.
3. `endgame` — symmetric 2v2 towns 4000 each, 100 turns. Goal: higher
   score / eliminate B. Tests full combined game.

## Final scores (campaign complete 2026-09-04; fast sweep 1.2s, slow ~10s)

> Era note: every number below was measured under **instant intel**. The
> post-campaign engine (delayed pops/factions, beheading permanence,
> economy-phase MOVE_CAPITAL, no spawn immunity) moved several of them —
> see Delayed-intel era. Do not judge new work against this table.

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
(All instant-intel era; unrestored since — see Step 0 in `BOT_PLAN.md`.)

## Fog era (EVENT_REWORK landed, current tree)

Fast suite: raid_hold 3066 / recycle 6052 / skip_thin 2151 / settle 3066 /
chain 5250 / guard 3088 / viable 3088 / pair 5105 / trap 3165 / defend 3207 /
wake 2121 / cluster 5465 / opening 3242 / defense 3305 / endgame 8804.
Moved vs delayed-intel: defense 0→3305 and wake 0→2121 (the old since-hole
starved them; re-observation under S fixed it for free), defend 1109→3207,
cluster 2182→5465, recycle 4086→6052, endgame 4928→8804, guard 1624→3088.
Down: viable 3768→3088, skip_thin 3467→2151, trap 4040→3165,
opening 4316→3242 (raid judgment under fog — funnel for Step 2 trade
evaluator). Unchanged: raid_hold ~3066.
Strategic (focal pro): attrition 14552 / comeback 821 / endurance 7752 /
_outsettle 2687 / guard_duty 2360 / longpeace 5254 / opening 1391 /
siege 5324 / snowball 4851 / staleness 4007 / succession 1826; self-play
symmetric (endgame 8804-8804, defense 4402-4402 — determinism holds through
the new pipeline); Elo all-hold (20/20 defenses stand — noted, doctrine
work decides whether that matchup is broken or just defense-favored).
empty_3000 rematch (3000 turns): pro 9156 / greedy 3089 / aggressive 3376 /
expander 3376 / turtle 5232 — pro dominates where greedy took it pre-fog
(4992); fog changes everything, judged by Steps not scores.
This is the table new work is judged against (live scoreboard: BOT_PLAN.md).

## Delayed-intel era (post-campaign engine changes, current tree)

Fast suite on current tree: raid_hold 3173 / recycle 4086 / skip_thin 3467 /
settle 2114 / chain 4319 / guard 1624 / viable 3768 / pair 4303 / trap 4040 /
defend 1109 / wake 0 / cluster 2182 / opening 4316 / defense 0 / endgame 4928.
Moved vs the table above: defense 1109→0, wake 1060→0 (delayed-intel
casualties — stale pops miss train bars; the forecast episode showed this
needs risk posture, not arithmetic), endgame 3249→4928 (unattributed —
beheading permanence and/or intel timing; needs the Step 0 bisect if it
matters). Single-town scenarios identical (no distant intel involved).
This is the table new work is judged against until the Step 0 re-baseline
lands (live scoreboard: `BOT_PLAN.md`).

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
- **Turtle > Aggressive**: garrison makes raids unprofitable. Earned in
  campaign (`defend` HOLDS); lapsed on current tree only via the intel
  transition, not the doctrine.
- **Greedy** is outside the triangle (pure selfish raid economics).
- **Pro beats all**: at campaign end took turtle+expander, tied
  greedy/aggressive (Elo 1531/1529/1527 — the tie cluster, since broken
  by counter-punch; current-tree standing unrestored).

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

## Per-bot improvement ideas — ledger (campaign plan: all five landed)

The campaign build order (turtle defense → aggressive viability → greedy
selectivity → expander guard → pro tie-break) is complete; what follows
is the achieved-vs-open ledger. Open work now lives in `BOT_PLAN.md`
(Steps 0–6) — this section is record, not roadmap.

Achieved: greedy viability gate + recycle fix + shared home defense;
aggressive viability gate + departure-sync + leader-targeting; expander
guard + working settlers + chain-as-policy; turtle threat bars + picket +
evac + recall + cap-concentration; pro counter-punch + duel-gated rope,
home defense and viability + empty-field hold + evac.

Open (see `BOT_PLAN.md`): demand-gated trains (successor to the reverted
forecast episode); meeting forecast + computed arrival-sync; post-capture
doctrine; evac v2 + capital-sniping + settler-hunting; pro siege craft;
turtle survive floor (relaxed 1200-trains still suicide — Step 1).
Shared foundations landed (see `BOT_TIME.md`): incremental
update, staged decide, memoized staleness, quiet replay, plan queue,
clock effort, slim wire, measured margins. Bots also have carryover
backlogs, Fischer/byo-yomi clocks, and the ideas-1–6 test files.
