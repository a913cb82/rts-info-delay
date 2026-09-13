# Bots

Four demo bots (`src/bots/`: pro, aggressive, expander, turtle) — canonical lineup runs pro twice (factions 0+1)
playing a fully deterministic strategy game under fog of war. This folder
is organized around one thing: **the improvement loop**. Everything else
is one iteration of it, plus logs.

## The loop

One iteration = **fix the worst performer**. Repeat forever, on a branch
(`loop/<idea>`):

1. **Pick the target**: the WORST-PERFORMING personality = lowest live
   ordinal among the four main-tip package bots (`<p>-<HEAD>`, >=10
   games for a stable read; ties -> the larger gap to the next
   personality). State the pick + numbers in the worklog before coding.
2. **Watch** the canonical game (`METHODS.md`; `ascii_view.py report` /
   `lead` / `health`): activity, flips, indicators (`METHODS.md`).
3. **Story**: per bot, turn by turn (`flip -F` / `fog` / `autopsy`).
   Focus on the target personality: where does it concede games?
4. **Ideas** from the mistakes — **style-gated**: every idea must be
   congruent with the target's style (table below). Doctrine first,
   code second (`STRATEGY.md`). Sparks -> `STRATEGY.md`.
   **Leak, not premium**: prove the loss was -EV *ex ante* (a decision
   that was wrong given what was known: donations, stalls, freezes,
   deadlocks). A correct insurance that didn't pay out (guards vs a
   2-turn-away contact that sat; holds that bled but saved) is a PREMIUM
   — fixing it makes play luck-dependent (wins when threats sit, dies
   when they rush). Results-oriented fixes backfire; judge decisions by
   ex-ante EV, never by outcome alone.
   If an idea requires changing shared/other-package code, it is a PORT
   (`benchmarks/port.py`, explicit + justified) or it is out of scope.
5. **Code** one idea, INSIDE the target package
   (`src/bots/<p>/brain.py` | `core.py`) — package isolation means the
   other three personalities cannot regress by construction. **Commit
   first** (bots need IDs to play). Fast suite per change; `pytest`
   green; `liveness.py` clean.
6. **Rate** with the purist matchmaker (`matchmake.py --play N` —
   propose/play/update one at a time, uncertainty drives). Every game
   logged; clean trees only (`--dirty` = unlogged iteration). Grind the
   new brain to **>=15 games** before judging (seeded package bots keep
   their winner ratings; genuinely new brains start fresh).
7. **Merge** iff the target is **NO LONGER the worst**: its ordinal
   (>=15 games) exceeds the next-lowest personality's ordinal, AND the
   style invariants hold in the canonical game (table below). Package
   isolation guarantees the other three are untouched. If it fails,
   iterate on the branch (one idea at a time, measure, keep or revert).
   **Stuck-escape**: a target with >=3 fails + structural stuck-proof is
   PARKED (documented); the loop proceeds to the next-viable personality
   (best may be targeted when all others are parked — ladder rungs need
   the max). Worst-first stands for viable personalities.
8. **Generate** the canonical game to BOTH viewer spots (`recordings/`
   + `viewer/public/`, `md5sum` match).

## Two tracks (incremental AND bold — 80 needs both)

Incremental (above: worst-first tweaks, +3-5 each) grinds parity and
lifts the field toward ~60-65. It cannot reach 80 (mu 80+ needs 90%+ wins;
tweaks diminish + escalate; mid caps ~55 (can't beat strong), pro ~70-72).
80 needs BREAKTHROUGHS (+8-15: ladder rungs raising max, new architectures,
new mechanics). So the loop runs BOTH:

- **Bold track**: breakthrough experiments for max-raising rungs and new
  capability (fork-max-fix-worst-loss ladder rungs; full package rewrites;
  new architectures (search/MCTS/opponent-modeling/RL-scaffolding);
  new mechanics exploitation). Allowed the full package rewrite (still
  inside `src/bots/<p>/`, still style-gated, still package-isolated;
  cross-package ports explicit via `port.py`). Branches `loop/bold-<idea>`.
- **Research first**: no bold code before (i) internet literature (other
  games' bots — RTS fog-of-war (StarCraft/BWAPI), board-game search
  (MCTS/alpha-beta), POMDP/planning-under-uncertainty, opponent modeling,
  tempo/attrition theory) via `ketch`/subagents with cited notes, AND
  (ii) this-game mechanics deep-dives (combat weakness math, intel/mail
  delays, crowding/logistic optima like the 1.71M 1-player ceiling,
  take/muster timing) with measured exploits. Doctrine from first
  principles + literature, not vibes. Research notes -> worklog/BRAINSTORM.
- **Persistence**: bold gets 3+ iterations MINIMUM (refine, don't abandon
  on first fail). Tweaks fail fast (1 grind, keep/revert); bold matures
  (mechanism first (does it fire? survive?), tuning later (thresholds)).
  Judge trajectory + mechanism (autopsy: does it do the new thing? survive
  longer? take more?) not single-grind ordinal. Document each iteration
  (what refined, what learned). Giving up after 1 red grind is forbidden.
- **When bold**: stuck 3+ tweaks on a personality (mechanisms exhausted) OR
  ladder rung needed (max needs +8 (tweaks give +3-5)) OR new capability
  (intel/search/modeling the current architecture can't express). Otherwise
  incremental (cheaper, safer). Both tracks log to worklog; both rate >=15g;
  both merge on (ordinal up + style holds). Bold may take weeks (RL training,
  multi-iteration refinement) — that is expected and funded.

## Personalities & style invariants

The classification is a hard constraint: an iteration may make a bot
better, but never into a different archetype. Review with the canonical
game's report (`ascii_view.py report`) before merging.

| package | style | must hold (canonical game) |
|---|---|---|
| `pro` | compounder/economist | compounds (capital = top-pop town); <=1 well-spaced colony; avoids sustained raiding; no wide sprawl |
| `aggressive` | conqueror/predator | initiates captures/raids; forward staging; must be the field's most march-active early |
| `expander` | colonist | founds the most towns in the field; colonies are cheap/expendable; does not turtle |
| `turtle` | fortress/tall | guards every town; founds few, spaced, defensible towns; keeps armies home; no long-range early raids |

Invariant checks are reviewer gates, not automated assertions (they need
per-map calibration); note the observed numbers in the worklog entry.

Per-iteration gates (every loop through step 4): fast suite per change (~1.5s); strategic at milestones
(~10s); `pytest` green; judge vs fog-era table with margin; worklog entry
per change (before → after numbers). Full detail: `BOT_PLAN.md` (The loop).

## Everything else (one iteration + logs)

| You want to… | Read |
|---|---|
| This iteration's backlog | `BOT_PLAN.md` — doctrine + ordered open work |
| This iteration's numbers | `METHODS.md` — binding fog-era table, suites, methods |
| Past iterations | `BOT_WORKLOG.md` — append-only log, one entry per change |
| Past game reports | `archive/archive/EMPTY_10000.md` — war-verdict (superseded by latest report card) |
| Play well (strategy reference) | `STRATEGY.md` — optimal play, phase playbooks, personality diffs |
| Change bot code (current behavior) | `STRATEGY.md` — personalities as coded, shared machinery, intel model |
| Spend clock budget wisely | `METHODS.md` — Fischer-clock infrastructure (ideas 1–6, landed) |

## Last iteration (one page, rots fast — see worklog head)

- **Personalities:** 0=pro + 1=pro (GTO reference, mirror match) 2=aggressive
  (predator) 3=expander (sprawl) 4=turtle (fortress). `stub` is passive
  harness furniture. No randomness anywhere, ever.
- **Intel model:** snapshots, late — LOS 150km eyes, 150km/turn mail,
  three delivery gates (tagged + released + ≥ S). Bots never get the map.
- **Scoreboard:** `BOT_PLAN.md` (live) — empty_10000: pro 121678 /
  expander 75768 / greedy 1000 / aggressive 0 / turtle 0 (see latest
  report card in worklog). empty_3000 retired. Exam 23/23 all green.
- **Open milestones:** ALL plan Steps substantially done (2 all-five, 3
  meeting/tempo, 4 compositional, 5 hopeless/evac/snipe/guards, 6
  buzzer/strikes; recon + pickets shipped). Filed-futures in plan/GTO.
  Details: `BOT_PLAN.md`.
- **Strategy backbone:** compound → expand on payback math → fortress at
  saturation → production war → strip-mine flip. Full doctrine: `STRATEGY.md`.

Per-iteration gates (every loop through step 5):
1. Fast suite (`benchmarks/scenario_bench.py`, ~1.5s) per change.
2. Strategic suite (`benchmarks/strategic_bench.py`, ~10s) at milestones.
3. `empty_10000` rematch read as war ledger (~30s, quiet).
4. `pytest` green. Judge vs the fog-era table only, with margin
   (clock-driven order wobble ≈ ±50 on long games — run benches quiet).
5. Worklog entry per change (before → after numbers).

## File map (iterations + logs)

- `BOT_PLAN.md` — this iteration's backlog (doctrine + open work).
- `METHODS.md` — this iteration's numbers (binding table + suites).
- `BOT_WORKLOG.md` — iteration log (append-only — do not rewrite old entries).
- `METHODS.md` — how we analyze (ascii_view tool: modes, ACJSON, recipes).
- `archive/archive/EMPTY_10000.md` — old game report (superseded by latest report card).
- `STRATEGY.md` — strategy reference (doctrine companion, living).
- `STRATEGY.md` — implementation guide (code as it is).
- `METHODS.md` — clock infrastructure.
