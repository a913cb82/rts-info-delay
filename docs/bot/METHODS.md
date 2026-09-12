# Bot methods (numbers + suites + clock + analysis + indicators)

This file is METHODS: numbers and how we measure. Roadmap lives in
`BOT_PLAN.md`; loop overview lives in `README.md`; change log lives in
`BOT_WORKLOG.md`. Merged from `METHODS.md` (numbers + suites),
`METHODS.md` (clock infra), `METHODS.md` (ascii tool + web viewer),
`METHODS.md` (indicator definitions) — the four originals are
untouched; internal cross-links among them now point at
`METHODS.md#anchors` below.

- [Binding numbers](#binding-numbers) — the ONE table that gates merges.
- [Suites](#suites) — fast / strategic / pytest / liveness / FFA + budgets.
- [Clock](#clock) — Fischer infra, ideas 1–6 (all landed).
- [Analysis](#analysis) — ascii_view recipes + web viewer + adaptive/target-duration.
- [Indicators](#indicators) — bot-error indicator definitions (verbatim).

Suites are instruments, not scripture — tune them freely to measure
whatever behavior the current step cares about (add scenarios, reshape
maps, split or merge suites). Budgets: fast stays <5s, slow <30s. When a
scenario stops discriminating, replace it; when a step needs a fixture
that doesn't exist (demand pricing, muster math, buzzer flips), build it.

---

## Binding numbers

> BINDING: the fog-era table below is the exact table from `METHODS.md`
> (fog era, EVENT_REWORK landed), copied verbatim. It gates merges; the
> live scoreboard is `BOT_PLAN.md`. Every other number in this file is
> record — do not judge new work against record tables.

### Fog era (EVENT_REWORK landed — BINDING table, current tree) — verbatim

New work is judged against this table (live scoreboard: BOT_PLAN.md),
with margin: `effort()` branches on wall-clock bank, so loaded runs
wobble (empty_3000 scored 3086 and 3136 on the same tree) — run benches
quiet, ignore sub-~50 long-game deltas. RED QUEEN RULE: bindings are
FLOORS with slack, not ceilings — every bot improving tightens symmetric
wars (margins compress as dumb foes get smart; old fat margins are
unrepeatable). Judge RELATIVE (ranks/margins) + mechanisms + suites;
absolute shortfalls up to ~1000 on war maps are doctrine-redistribution
until a mechanism says otherwise. Re-run STRATEGIC every commit; run
suites twice post-change (JIT first-runs lie).
Fast suite: raid_hold 4658 / recycle 6083 / skip_thin 3888 / settle 3122 /
chain 5327 / guard 2631 / viable 5251 / pair 5798 / trap 5494 /
defend 2904 (400t, pickets) / wake 2121 / cluster 5465 /
opening 5251 / defense 1115 (honest mutuals; concentration filed) /
endgame 7708 (strikes take; filed mass next). Known wobblers (cadence):
recycle +-200, guard_duty +-500, void_contact +-300, longpeace +-500 —
run quiet, judge with margin. History below is record, not binding.
Since landing: movement streams fixed (bots see own armies — foundings
work, E1 done), scout-first probing restored all raid takes (pair/viable/
raid_hold/trap/skip_thin goal-PASS), quiescence gating steadied orders.
Founding costs show at <=100t horizons (~-500 + lost compounding each);
raid numbers read takes, not sits. recycle horizon 30→60 (idle army
probes first, founds far ~t55).
Strategic (focal pro): attrition 14552 / comeback 821 / endurance 7752 /
_outsettle 1830 (3v1 towns — scout tax in a 200t sprint, timing not shape) /
guard_duty 3249 (holds 300t vs 8000-aggressive: outcome-muster +
war-footing hold, no mystery evac) / longpeace 5254 /
opening 1391 / siege 5324 / snowball 4851 / staleness 4007 / succession 1826;
void_contact 5136 (take: scout finds B, raids, +founding) / void_settle 2933
(4 towns); self-play symmetric; Elo: greedy 1515 / aggressive 1515 /
pro 1501 / turtle 1498 / expander 1470 — raiders take, holders hold,
pro on top (demand-gated muster). Verdict for Step 5: the old all-hold was attacker-passivity
(no contact, no takes), not defense-favored mechanics; with contact the
takes come. empty_3000 rematch: pro 9156 (still sits — last blind bot) /
turtle 6637 / expander 4227 / aggressive 3766 (took greedy's capital!) /
greedy 3136 (exiled north, 2 towns — lineage via scouting). 8 foundings,
11 deaths, first contact t2750. A real game now: found, meet, take.
This is the table new work is judged against (live scoreboard: BOT_PLAN.md).
Next bot work (ordered, see BOT_PLAN.md): Step 2 trade evaluator scoped by
the selectivity bleed (skip_thin/trap/viable), then the Elo all-hold
verdict, then Steps 3–6; scouting ships inside Step 2, counter-intel
parked after the evaluator.

### How to judge vs the binding table

- Run benches quiet; ignore sub-~50 long-game deltas (wall-clock wobble).
- RED QUEEN RULE: bindings are FLOORS with slack, not ceilings — every
  bot improving tightens symmetric wars; old fat margins are unrepeatable.
- Judge RELATIVE (ranks/margins) + mechanisms + suites; absolute
  shortfalls up to ~1000 on war maps are doctrine-redistribution until a
  mechanism says otherwise.
- Re-run STRATEGIC every commit; run suites twice post-change (JIT
  first-runs lie).
- Known wobblers (cadence): recycle ±200, guard_duty ±500,
  void_contact ±300, longpeace ±500 — run quiet, judge with margin.
- GTO exam (`benchmarks/gto_exam.py`, below) NEVER gates (a ceiling, not
  a floor) — judge game truth in the suites.

### GTO exam (`benchmarks/gto_exam.py`, scored, non-blocking)

How GTO is pro, in one number: decide-level doctrine fixtures (scripted
intel in, orders out), parameterized over geometries so passing needs
the RULE, not the point. Expected to fail where Steps haven't landed —
the failures are the roadmap. Baseline was 6/14; now 23/23 ALL GREEN: muster 10/10 (horizon +
deterrent + JIT pins), pricing 3/3, selectivity 4/4 (snipe tie-break),
escape 2/2, intel 1/1, endgame 3/3 (no-settle split + blitz +
buzzer strikes). The instrument is complete; extend it (new doctrine
-> new fixtures) as the frontier moves. Never gate on it (a ceiling, not a floor) —
judge game truth in the suites; challenge fixtures with numbers.

### Record tables (not binding — history only)

#### Campaign scores (instant-intel era, record — complete 2026-09-04; fast sweep 1.2s, slow ~10s)

> Every number below was measured under **instant intel**. Record only —
> do not judge new work against this table.

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

#### Delayed-intel era (superseded interim, record)

Superseded by the fog-era table when EVENT_REWORK landed (Step 0 DONE).
Fast suite under the interim engine: raid_hold 3173 / recycle 4086 / skip_thin 3467 /
settle 2114 / chain 4319 / guard 1624 / viable 3768 / pair 4303 / trap 4040 /
defend 1109 / wake 0 / cluster 2182 / opening 4316 / defense 0 / endgame 4928.
Moved vs the table above: defense 1109→0, wake 1060→0 (delayed-intel
casualties — stale pops miss train bars; the forecast episode showed this
needs risk posture, not arithmetic), endgame 3249→4928 (unattributed —
beheading permanence and/or intel timing; needs the Step 0 bisect if it
matters). Single-town scenarios identical (no distant intel involved).

#### Starting baselines (pre-campaign, for the record)

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

#### Slower suite results (instant-intel era, record; strategic_bench.py — 8.3s total, budget <30s)

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

---

## Suites

Goal: per-bot scenario suites (disjoint map sets) that run in seconds and
discriminate each personality's weaknesses. Used to score the 5 bots
(greedy, expander, aggressive, turtle, pro) before/after improvements.
`random` is retired, replaced by `pro` (no personality constraints).

Design rules:
- Focal bot is always faction 0 (A). Opponents: `stub` (passive) unless the
  scenario needs a live enemy (`aggressive` as raider).
- 2 factions per scenario (fast spawns), 30–100 turns, starting pops at or
  above train thresholds so action starts by turn ~5 (no 1000-turn waits).
- Each scenario: `{map, bots, turns, focal, goal}`. Scoring is final
  focal-faction score only (pop + 1000×armies, same as game score).
  Scenario `goal` fields are retained in the JSON as documentation of
  what each map was built to test, but the number that counts is score.
- Runner: `benchmarks/scenario_bench.py`. Full sweep target < 60s.

### Fast suite — tactical scenarios (15 maps, 3 per bot, disjoint)

`benchmarks/scenario_bench.py` — fast sweep, budget <5s (measured 1.2–1.7s).
Runner also takes a single file for issue-targeted repro (see cut_scenario below).
What it gates: single decisions over 30–100 turns (one raid, one settle,
one defense). Judge game truth here; the GTO exam never gates.

#### Greedy (`maps/scenarios/greedy_*.json`)
1. `raid_hold` — A 3000 vs B 3000, 200km apart, 60 turns. Goal: own B's
   town at end (halved 1500 holds). Tests profitable-raid execution.
2. `skip_thin` — A 3000 vs B 800 (halves to 400, starves), 60 turns. Goal:
   B still owns its town at end AND focal score high (no wasted army).
   Tests raid selectivity. Pre-campaign greedy FAILED this (attacked
   everything); fixed by the viability gate (skip_thin 2116→3467).
3. `recycle` — A 5000 + idle army, no enemies, 30 turns. Goal: 0 idle
   armies at end (BUILD pop-add or found). Tests garrison recycling.

#### Expander (`maps/scenarios/expander_*.json`)
1. `settle` — A 3000, empty east, 60 turns. Goal: ≥2 towns.
2. `guard` — A 3000 vs live `aggressive` 3000 300km away, 80 turns. Goal:
   still owns capital at end. Tests home guard. Pre-campaign FAILED
   (marched settler out, lost capital undefended); fixed by guard rule.
3. `chain` — A 3000 + second town 2000 far east, 80 turns. Goal: ≥3 towns
   (each town owes a settler).

#### Aggressive (`maps/scenarios/aggressive_*.json`)
1. `viable` — A 3000 vs B fat 4000 nearby, 80 turns. Goal: own B's town
   (halved 2000 holds). Tests basic winning attack.
2. `starve_trap` — A 3000 vs B thin 900, 80 turns. Goal: B still owns at
   end (restraint) + focal score kept. Pre-campaign FAILED (captured
   rubble); fixed by the viability gate (map redesigned: decoy + prize).
3. `pair` — A 5000 (affords 2 armies) vs B 3000 + B guard army, 80 turns.
   Goal: own B's town (needs 2v1 stacking to beat the defender).
   Pre-campaign FAILED (sent ones, traded); fixed by departure-sync.

#### Turtle (`maps/scenarios/turtle_*.json`)
1. `defend` — A 3000 vs live `aggressive` 3000 250km away, 100 turns.
   Goal: still owns capital at end. Tests garrison defense.
2. `wake` — A 2000 (under 2600 rule) vs distant `aggressive`, 60 turns.
   Goal: ≥1 army by turn 40. Tests threat-responsive threshold.
   Pre-campaign FAILED (never trained under 2600); fixed by threat bars.
   Lapsed under delayed intel (scored 0); re-observation under S fixed it
   in the fog era (wake 2121).
3. `cluster` — A capital 3000 + town 2000 100km away vs far `aggressive`,
   100 turns. Goal: own both at end (mutual support).

#### Pro (`maps/scenarios/pro_*.json`, starts as greedy copy)
1. `opening` — fat neighbor + empty space, 80 turns. Goal: score (rewards
   raiding AND settling together).
2. `defense` — `turtle/defend` variant. Goal: survive + counter-take.
3. `endgame` — symmetric 2v2 towns 4000 each, 100 turns. Goal: higher
   score / eliminate B. Tests full combined game.

### Strategic suite (11 maps, 150–1000 turns)

The 15 maps test single decisions over 30–100 turns: one raid, one
settle, one defense. They cannot see compounding (the 1100-turn wait
before the first train in empty3000), multi-war campaigns, succession
after commander death (expander t1183), staleness compensation at range,
clock-bank management over thousands of turns, or five personalities
interacting. A bot can ace all 15 and still misevaluate a 3000-turn game.

Since maps cost ~110ms (and even 1000-turn games cost ~2s), the answer is
more scenarios, not longer iteration. The strategic set (11 maps, all
2-faction, 150–1000 turns) ships in `maps/strategic/`, run by
`benchmarks/strategic_bench.py` (~10s, budget <30s). Re-run STRATEGIC
every commit. What it gates: compounding, multi-war campaigns,
succession, delay compensation at range, long defense, generalship.

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

### Cheap suite (<5s, rho +0.59*) — the quick gate

`benchmarks/cheap.py [--bot X]`: ffa/feast-2000 (~3s, agency vs
passives + one live mid) + strategic/snowball (~0.8s, solo closing
drill), composite = z-sum with frozen corr baselines. *+0.59 measured
at feast-3000t; 2000t separation confirmed on 4 diverse bots
(champ leads) — full re-validation deferred (compute costs!).
2000t favors turtles slightly (attackers en route) — known bias.
What it gates: fast pre-commit signal. Now checks runner stderr for
crash/eof + timeout and fails loud (see liveness below).

### Pytest suite (unit + integration)

`pytest tests/bots/` (convention: new tests go in `tests/bots/`;
integration-level — drive `bot_main` or `BotState` over scripted
stdin/event streams — not white-box unit tests; never edit existing
tests for clock work, add new files). What it gates: decision-level
correctness over scripted fixtures; the pytest suite unit-tests
decisions, never full-game liveness (that gap is what liveness.py covers).

### Liveness suite (full-game crash gate)

`benchmarks/liveness.py` runs a 4000t x 5-bot empty game and exits 1 on
any death (~6s, slow-suite tier). What it gates: fatal crashes over full
games (a None-order crash killed 3/4 personalities at their first settle
for dozens of commits; fixed 262b0f5 — no score suite noticed because
cheap.py read only scores and never stderr; feast/snowball stop before /
never reach the lethal path). Buggy code: 3 DEAD exit 1; fixed: clean
exit 0.

### FFA Elo (`benchmarks/elo.py [N]`, default 6)

No 1v1s (different game than FFA). Each 5-player game yields 10
pairwise results from placements (1st beats 4, 2nd beats 3...),
K=16 with margin weight (blowouts to 1.5x). Ratings per faction
slot (F0-pro vs F1-pro tracked separately — positional!). 6 games
≈ 60 pairs ≈ 5 min (≈10x the data rate of 1v1s).
What it gates: FFA standing; direct Elo (stays in the SLOW tier).

### Correlation rebuild (n=17 bots, Spearman vs FFA elo) — suite membership evidence

Measured with `benchmarks/corr.py` (every map x 17 historic bots).
Sprints <3000t don't separate (old bots sleep — all tie at standby
scores); 3000t single-slot F0 works (same slot = fair, rotation 5x
cost unjustified). Contested maps are noise (brawl -0.83 at n=6);
agency-dominated maps predict (feast/open).
KEEP (rho>0.15): ffa/feast +0.56, strategic/snowball +0.44,
ffa/open +0.43, scenarios/aggressive_pair +0.31,
strategic/endurance +0.21, scenarios/aggressive_starve_trap +0.19,
strategic/void_contact +0.19, strategic/expander_outsettle +0.16.
CUT (misleading): turtle_cluster -0.50, expander_settle -0.48,
turtle_wake -0.42, expander_chain -0.41, turtle_defend -0.49,
pro_endgame -0.33, attrition -0.24, guard_duty -0.21.
CUT (zero signal): comeback/opening (constant scores, NaN).
FAST (5s): positive-rho scenario maps only. SLOW (30s): kept
strategic maps + feast/open + selfplay; elo-lite stays (direct Elo).

### Logging + ratings discipline (applies to every suite game)

Log-everything rule: every real game runs through `elo_field.py --field ...`
(it appends field+scores+timestamp to `elo_games.jsonl`, updates `elos.json`).
Bare `run_game` is for tests/smoke only. Canonical regens: field the
canonical lineup with record to /tmp, then `cp` to both viewer
locations. Duels/analysis games: same (record to /tmp). 50 logged +
~40 pre-log unrecoverable (ratings include them, details gone).

OpenSkill (Bradley-Terry-Full) ratings: Elo replaced by OpenSkill
`BradleyTerryFull` (native FFA: whole placement vector updates at once,
no pairwise decomposition; mu/sigma belief + tau drift for evolving bots;
defaults mu=25 sigma=25/3). `elos.json` holds {mu, sigma, games};
display = ordinal (mu-3σ). Recomputed from all 50 logged games
(`/tmp/elos_elo_backup.json` keeps the Elo era). `elo_field.py --field ...`
unchanged (append-only log).

Clean-tree rule (bot IDs must be honest): logged games (elo_field/matchmake)
ALWAYS run clean worktrees — name-sha IDs the exact code. `cheap.py`/`ffa_bench.py`
default to clean HEAD too; pass `--dirty` to iterate on the workspace (fast,
unlogged, ID means nothing). Duels/analysis: copy the pattern
(worktree cmds via elo_field helpers), never bare workspace python when the
conclusion will be attributed to a commit.

Cross-commit caveat: historical bots run FULLY on-commit (worktree engine +
brains, current venv python). Wire protocol drift can kill ancients against
the HEAD engine — deaths count (0 score), noted not excused. Engine stays
HEAD only as the referee.

### cut_scenario (issue-targeted repro)

`cut_scenario.py REC --turn T --before N --focal F --teams ... --goal ...
--out maps/scenarios/x.json`: snapshots truth N turns before an issue
into a runnable scenario (towns/armies as map CSV, engine config from
header). Run it via scenario_bench (single file) pre/post-fix to
confirm. Limitation: bot mirrors start empty (positions replay, minds
don't — blood/trails/notes lost). Pair with fog (what did it see?) to
judge memory-dependence.

### Bash bots (language-agnostic runner)

`run_game` takes `{faction: argv-list | bash-string}`. Strings run via
`bash -c` (pipes, env, any executable — verified with a shell camper
bot playing 50 turns). Protocol is line-based over stdio (config /
faction / go, then turn frames); see `src/runner/main.py`.

### Suite TODO (from the modern-vs-era review, 2026-09)

Evidence: a fatal crash (None order, fixed 262b0f5) killed 3/4
personalities at their first settle (t1130-1776) for dozens of commits.
No suite noticed: cheap.py read only scores and never stderr; feast
(2000t) and snowball (500t) stop before / never reach the lethal path;
the pytest suite unit-tests decisions, never full-game liveness.
Also: the verify-window change (assault_verified 800->2000) produced
BYTE-IDENTICAL cheap-suite scores (2210/1800/1559/2743) — the suite has
no scenario exercising stale-intel packs, so it cannot see that class.

DONE: cheap.py now checks runner stderr for crash/eof + timeout and
fails loud; benchmarks/liveness.py runs a 4000t x 5-bot empty game and
exits 1 on any death (~6s, slow-suite tier). Buggy code: 3 DEAD exit 1;
fixed: clean exit 0.

TODO (ranked):
1. Scenario: stale-intel pack. Contact -> 1000t darkness -> assert the
   assembled pack marches (verifies assault_verified window + scout
   refresh). Currently zero coverage.
2. Scenario: self-TRAIN survival. Lone town near the floor with delayed
   pop beliefs; assert no town dies from its own TRAIN (observed
   expander t2182/2183, pro t2915).
3. Scenario: expansion gates. Crowded map + one armed foe scout; assert
   serial bots still settle (reprint_ok / support-ratio blind spots).
4. Long-horizon (10k) micro-scenario in the SLOW tier for exile
   stalls/freezes (turtle 1t/0a 3000t+).
5. Re-validate any addition against corr.py (rho >= current 0.59).
Anti-goal: scenarios must stay deterministic and quiet-box safe.

### Per-bot improvement ideas — ledger (campaign plan: all five landed)

The campaign build order (turtle defense → aggressive viability → greedy
selectivity → expander guard → pro tie-break) is complete; what follows
is the achieved-vs-open ledger. Open work now lives in `BOT_PLAN.md`
(Steps 0–6) — this section is record, not roadmap.

Achieved: greedy viability gate + recycle fix + shared home defense;
aggressive viability gate + departure-sync + leader-targeting; expander
guard + working settlers + chain-as-policy; turtle threat bars + picket +
evac + recall + cap-concentration; pro counter-punch + duel-gated rope,
home defense and viability + empty-field hold + evac.

Open work: `BOT_PLAN.md` Steps 1–6. Shared foundations landed (see
[Clock](#clock)): incremental update, staged decide, memoized staleness,
quiet replay, plan queue, clock effort, slim wire, measured margins.

### Personality triangle (doctrine)

- **Aggressive > Expander**: raid kills the settler faction before it
  compounds. Proven: `expander_guard` (capital falls), empty3000 t1183.
- **Expander > Turtle**: out-settle the sleeper. Proven territorially:
  `expander_outsettle` towns_held 3v2 at 200 AND 500 turns — but score
  still trails (1856v2441, 2499v3232) because new towns start at 500 and
  turtle never spends. Score converts only with raiding follow-through
  (future expander work: raid turtle's fat capital with built force).
- **Turtle > Aggressive**: garrison makes raids unprofitable. Earned in
  campaign (`defend` HOLDS); lapsed under delayed intel, restored in the
  fog era (defend 3207) — the doctrine, not the transition, was right.
- **Greedy** is outside the triangle (pure selfish raid economics).
- **Pro beats all**: at campaign end took turtle+expander, tied
  greedy/aggressive (Elo 1531/1529/1527 — the tie cluster, since broken
  by counter-punch; current-tree standing unrestored).

Each edge has its natural metric (raid success / survival / towns_held);
score is the recorded baseline number, doctrine notes are the reading.

---

## Clock

Bots run under a Fischer clock (cap `turn_time_ms`, +`time_increment_ms`/turn).
These six ideas cut think cost or spend the bank deliberately. Status: all six implemented (commits below).
Benchmarks: `benchmarks/bot_bench.py` (quiet turn + 2000-event backlog).

### 1. Incremental BotState — DONE (`0f171dd`)
Measured: quiet update 0.016→0.010ms; heavy backlog ~85ms (unchanged —
dominated by engine `apply_events` index rebuilds, out of scope for bot-only
work; verified by same-process A/B after a false thermal regression scare).
Growth is now folded per applied event and reset on turn advance, which also
fixed a real inconsistency the new tests caught (chunked updates used to
re-baseline growth per chunk).
Apply only each turn's event delta to cached projections instead of replaying
and re-syncing trackers over the full visible state.
- Tests: equivalence — incremental update equals full replay over scripted
  event sequences (spawn/capture/death/move interleavings); N-turn
  randomized-sequence property test asserting identical world snapshots.

### 2. Anytime decide with staged prefixes — DONE (greedy pilot)
`decide_stages` (trains/moves/builds) + lazy `decide_orders`; 3000-turn game
plays the same story (single pre-existing ±1 wire flip at t1110, final
within 0.04%). Other tiers keep their loops; promote on evidence.
Priority-ordered stages (trains → defense → attacks → expansion → micro),
each checkpointing `should_yield()` and flushing its orders before the next
stage starts, so an abort keeps the important prefix.
- Tests: injected early deadline after stage k yields exactly the first-k-stages
  prefix of the full run; empty-prefix test (deadline on entry → no orders,
  still replies `go`); stage-order test (a train is never dropped for a raid).

### 3. Memoized staleness math — DONE (`0f171dd`)
`BotState.stale_turns` keyed by (turn, capital id+pos); `BotForecast` has a
per-instance memo. Cache-bust test does marked world surgery + `mark_dirty`,
mirroring the production mutation contract.
Cache per-town compensation (`dist/capital/info_speed`), growth, and crowding
estimates keyed by (town_id, turn); recompute only on new info.
- Tests: cache-hit equivalence (memoized == recomputed over a full game);
  invalidation tests (each event kind touching a town busts exactly that
  town's entries, nothing else); stale-read test (no entry survives a
  MOVE_CAPITAL resync).

### 4. Skip stable turns — DONE
`cached_or_decide` replays standing orders on quiet turns (~1.4µs vs ~0.2ms
decide); military kinds bust, partial-backlog turns never cache. Wired into
`bot_main`, so all five tiers get it. Caught live: the first version cached
`[]` on turn 1 and replayed it for 3000 turns (idle game — growth never
busted the cache). Fixed with a decide-relevant fingerprint (quantized
pops/positions, membership, pending trackers, 25-turn heartbeat): replay
requires fingerprint stability, so affordability changes force fresh decides.
If a turn's payload carries no new military information (no creations,
removals, or faction changes — only unchanged or ticked snapshots),
re-issue standing orders without running decide; bank the +10ms.
- Tests: quiet-turn replay (orders identical to full decide across 50 idle
  turns); cache-bust test (each military event kind forces a full decide);
  bank test (clock balance rises over a quiet stretch, never exceeds cap).

### 5. Bulk think + cached plans — DONE (mechanism)
`push_plan`/`_live_plan`: verbatim orders until turn expiry or new military
intel. No tier pushes plans yet — that is strategy work (when to plan), the
plumbing and its tests are in place.
On quiet turns with a full bank, run deep work once (forecasting, wide
build-site search) and store a queue of standing orders with trigger
conditions; near-empty turns pop the next precomputed order.
- Tests: plan-execution equivalence (K quiet turns from plan == K live
  decides); trigger tests (new intel invalidates the plan and forces fresh
  decide); expiry test (stale plans never issue).

### 6. Clock-aware aggression — DONE (greedy pilot)
`effort()`: None→full, <25ms→low. Low clock = trains stage only (measured
0.088→0.016ms on a rich state, trains-only verified subset). `bot_main` sets
`clock_budget_ms` from the Fischer clock line each turn.
Condition effort on the bank: low clock → precomputed/safe moves only;
full bank → expensive searches (coordination, wide site search).
- Tests: same state at low vs full clock (safe-only subset vs full orders);
  threshold boundary tests; monotonicity (more bank never yields fewer safe
  orders).

### Decided (not in 1–6)

- **8 wire slimming — IMPLEMENTED.** Populations go out as absolute ints
  inside `town_update`; the send-state diff resends only changed snapshots.
  Wire error bounded <1, never compounds (engine floats + record file
  untouched; bot assigns absolutely). Measured:
  278→198 B/bot-turn (−29%); 3000-turn scores 11077→11073 (single ±1
  threshold flip at t1110, final within 0.04%).
- **9 margins — IMPLEMENTED, measured.** Instant round-trip med 0.15ms, p99
  0.45ms, max 11ms spike/1000. Total unusable 8ms (3 flush + 5 think),
  down from 30ms double margin. The 11ms spike is why it is 8, not 2–3.
- **10 engine standing orders — REJECTED.** Engine stays simple; the
  equivalent lives bot-side as plan caches (idea 5). Revisit only with data
  showing round-trips dominate a thinking bot's clock.

### After the campaign: intel-era work (superseded by EVENT_REWORK)

The event-shape machinery this section once described (landing rebuild
payloads, per-turn town snapshots, `TOWN_DEATH` kind, builder-returns-[]
mute) was deleted by the rework — see `STRATEGY.md` intel model and
the (since-deleted) EVENT_REWORK plan. What survived into the fog era: `stale_turns`
compensation (load-bearing), quiet-turn replay (any update breaks sleep),
plan queue, clock effort. The worklog entries stand as record.

### Conventions
- New tests go in `tests/bots/`; integration-level (drive `bot_main` or
  `BotState` over scripted stdin/event streams), not white-box unit tests.
- Never edit existing tests for these; add new files.
- Each idea lands with its tests green plus a paired benchmark (ms/turn per
  bot on the 3000-turn empty game) before/after.

---

## Analysis

Loop step 2 runs on one tool: `benchmarks/ascii_view.py` (plus the web
viewer at `http://localhost:5173/` for watching replays).

### ASCII grid (human)

```bash
python benchmarks/ascii_view.py recordings/empty_10000.jsonl \
  --turns 5000 --size 50x50 --no-color --mode all
```

- `--mode`: `glyph` (shapes: ● town ◆ capital ▲ army ×N stack * clash),
  `pop` (log buckets: doublings from 500), `faction` (digits),
  `all` (2-char F+T cells: faction + type/pop/count), `cluster`
  (faction + cluster letter).
- `--size WxH` (default 50x50, square like the map).
- Footer: per-faction pop/towns/armies/capital pop + legend.

### ACJSON (LLM): `--format acjson`

Augmented Cartesian JSON — same quantization + collision priority as
the grid, so both agree cell-for-cell. Sparse non-empty cells (x/y +
kind/faction/pop/ids) plus precomputed geometry (no LLM math):

- `relations`: per town nearest foe/own (dist/dir/pop); per faction
  centroid/spread/neighbors/capital-offset/named clusters (label, pop,
  centroid, radius, members, capital bearing, nearest foe cluster).
- `views`: per-capital 8-ray first-hit (`N: T17f3@147`, `-` = open).
- `deltas`: score at symmetric offsets (`--deltas 100,10,1`,
  then-minus-now, null off-record).
- `--compact` for token discipline.

### Standard analysis (report card recipe)

1. Report: `--format report` (full-game brief in one command: activity
   per faction, stagnation list, onesies, punishable thin towns).
   Start here — it rederives viewer feedback without watching.
2. Quartiles: `--turns 2500,5000,7500,10000 --format acjson --compact`
   (factions + deltas + clusters tell the arc).
2. Fog (`--format fog --faction F --turns T`: what the bot saw — ghosts/staleness first, truth second).
3. Autopsy: `--format autopsy --window 7800-8000` (death ledger:
   who fed whom where; `ONESIES` flags >= 3 losses by one faction
   at one town — the suicide detector; default last 1000 turns).
4. Full sweep (11 snapshots) when quartiles show something odd.
5. ascii `--mode all` at war turns (who stood where).
6. Event ledger (`town_spawn/death/capture`, battles) per millennium.
7. Per-bot well/badly + filed ideas → worklog report card.

### lead / flip (lead-change analysis)

- `ascii_view.py REC --format lead`: pop/towns/armies per faction per
  millennium + FLIP lines (who took the lead, when).
- `ascii_view.py REC --format flip --faction F --window A-B`: F's lost
  towns, takes, battles with counts/coords, plus F's town/army arc
  (did it react?). Pair with `fog --faction F --turns T` (what did it
  see?) for full Hunter's-loop diagnosis.

### Health (`--format health`) — start here for self-diagnosis

Run `--format health` first: all [indicators](#indicators) in one
command; drill down with the tools listed per indicator.

### Playback speeds (viewer)

Controls: 0.5× … 8× (tweened), then turbo tiers 16× / 64× / 256× / 1024×
/ 4096×. Above 4× the per-turn tween is skipped (a jump shows the same
thing for less work) and the scene redraws at most every 50 ms while
turns keep advancing every animation frame — playback rate is decoupled
from render cost (draw() is dominated by SVG/DOM churn and the 10k-point
score graph, none of which need 60 Hz). Pausing/stepping always draws.
4096× clears a 10k-turn game in ~1s on this box.

### Adaptive playback ("auto" speed)

This game is bursty: in the quad recording 59% of all action falls in 10%
of the turns (t3000-4000). The viewer can steer playback speed by action:

- Enable with the **auto** checkbox (or `&auto=1` in the URL). The speed
  select then means the QUIET/max speed; while action is near, playback
  drops to ~2x and ramps back up after.
- Action signal = weighted events per turn: capture 3, battle 3,
  founding 2, town death 2, army train 1, army death 1. Weights are
  module constants (`AUTO_FULL`, `AUTO_SLOW`, `AUTO_LOOKAHEAD`,
  `AUTO_LINGER`, `AUTO_STEP_CAP` in `viewer/src/main.ts`).
- Faction-aware: with a faction selected via the fog selector the signal
  is THAT faction's action (watch one bot's war); with none selected it
  is global (any action slows playback).
- Lookahead 5 turns (brake BEFORE the burst) + linger 8 (stay slowed
  through the aftermath); braking is fast (0.5/frame), release slow
  (0.08/frame). Under auto, turns advance at most 12/frame so a burst
  can never be skipped between frames.
- The live effective multiplier is shown next to the checkbox.

#### Target-duration mode (fit the replay into N seconds)

The `auto` control's second select sets a total runtime (reactive / 15s /
30s / 1 / 2 / 5 / 10 min; URL `&auto=60`). The viewer builds a smooth
per-turn speed profile — triangular kernel around every action burst
(lookahead 5, linger 8) — and solves for the quiet speed so the summed
per-turn times hit the target exactly (binary search, 80 iterations).

Action = **fighting and territorial change only** (training is not
action): battle 3, town capture 3, town build 2, town destroy 2. Each
event raises a raised-cosine (Hann) kernel over +/-20 turns (context
either side, no kinks); the intensity is normalized to the game's 98th
percentile so the loudest bursts reach the floor.

Smoothing: the raw speed profile is passed through a **log-space cone
filter** (|delta ln speed| <= ln 1.20 per turn). That filter IS the
transition: it preserves the slow action valley and makes the ramp a
geometric, perceptually even accelerate/decelerate, so the effective
multiplier never jumps, and the ramp is long enough that the floor is
reached BEFORE the burst (10-50 turns of run-in depending on target).

The intensity full-weight is 2 (a single town build/death), so EVERY
action event reaches the slow floor (with 3, build-weight events peaked
at 0.67 and played ~100x). Action speed: **2x preferred, 3x, 4x max**;
if a target cannot fit even at 4x the replay overruns the target rather
than hiding the action (the readout's tooltip shows the actual length).
Quiet has no floor and runs to **65536x**. Turns advance from a
cumulative wall-clock schedule. Observed on quad_10000:

    target  action  quiet    total   wall<=4x  speed at action turns
     15s     4x    65536x    38s      5.2s     4x (target overrun)
     30s     4x    65536x    38s      5.2s     4x (target overrun)
     60s     3x     1032x    60s     16.4s     3x
    120s     2x      215x   120s     44.1s     2x
    300s     2x       43x   300s     53.2s     2x
    600s     2x       19x   600s     57.7s     2x

Faction-aware: select a faction (fog selector) and the profile is built
from THAT faction's action only; recomputed on selection/target change.
Manual seeks re-anchor the schedule clock.

Interpolation: at 4x and slower turns tween (entities lerp between frames)
for continuous motion; in target mode the tween spans the turn's own
schedule interval (dt) so it never moves-then-holds; stepping one turn
with the arrows/buttons also tweens; jumps (scrub, >4x) render directly.

---

## Indicators

> Verbatim from `METHODS.md`: every pattern users flagged as
> "indicative of bad bot behavior", with thresholds, tools, and meanings.
> Run `--format health` first (all in one command); drill down with the
> listed tools.

### 1. Onesies (`autopsy`, health)

>=3 losses, one faction, one town. Means: suicide raids (blind floor
fail), remuster races (W=0 vs printers), re-fed assaults (no blood),
fratricides (stale-mirror flips). Healthy: 0. Watch: 1-2 (fast flips
unknowable). Sick: >2.

### 2. Idle armies (`report`, health)

Static >100t with 0 battles. Means: note-locks (held with nothing
wanting/releasing), parking lots (arrived patrols freeze), print-
patrol-print treadmills, pack-train stalls. Healthy: ~0-3. Every
body works every turn (guards noted home, leftovers micro-patrol).

### 3. Churn (`report`: km/army/100t)

March speed 50/t = 5000/100t. War mobility runs 100-500 WITH takes.
Takes-less motion >100 sustained = shuttling (pendulum/alternation/
redeploys — see breaker). Patrol spirals read high per-scout; judge
per-faction with takes context.

### 4. Pure 1v1s (health)

Exactly-2-combatant battles. Field ones (both die, nothing saved) =
scout-meetings (bend hops off foe armies) or 1v1 chases (need 2v1).
Town 1v1 mutuals (guard dies, town lives) are CORRECT (N-for-N saves
rich towns) — not errors. Healthy: ~0 field.

### 5. Mover-dies suicides (health)

Loser moved last (arrived into death). Pack-scale version: failed
assaults (all attackers die, town lives) = stale-S underestimates +
defeat-in-detail (sync!) + unseen re-feeds (attempt-cap!). Healthy: 0.

### 6. Quiet windows (health: 500t blocks, no found/cap, rivals alive)

Means: demand desert (nothing wants prints), dark (no sel), verify
freeze (stale + verify = peace), endgame done (one empire left —
correct quiet). Investigate every quiet block with rivals alive:
fog (did they see?), lead (who led?), flip (what broke?).

### 7. Train-deaths (health)

army_spawn + town_death same town within 2 turns, no battle. Bot
error, always: overtrain past floors (bare-convert vs transit!),
mutual-save misjudgment. Healthy: 0.

### 8. Lead flips (`lead`, `flip`)

Not errors per se — analyse what the loser did wrong / winner did
right (thin sprawl? naked towns? first-packer vs guarded sprawl?).
Every flip gets a flip-window audit.

### 9. Punishable (`report`)

Final state: foe town, 0 garrison, idle foe stack <300km. Means:
packs never formed (notes? verify? support?). Healthy: none.

### Verdicts (health)

- healthy: none of the above fire.
- watch: 1v1s >10, any onesies/quiet blocks.
- SICK: any suicides/train-deaths, onesies >2, quiet blocks >6.
