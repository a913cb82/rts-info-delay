# Bots

Four demo bots (`src/bots/`: pro, aggressive, expander, turtle) — canonical lineup runs pro twice (factions 0+1)
playing a fully deterministic strategy game under fog of war. This folder
is organized around one thing: **the improvement loop**. Everything else
is one iteration of it, plus logs.

## The loop (the main event)

Repeat forever:
1. **Watch** the current canonical game (`recordings/empty_10000.jsonl`
   — the viewer location; `benchmarks/ascii_view.py`, how: `VIEWER.md`):
   `report` (activity/stagnation), `lead` (timeline + flips), `health`
   (indicators — see INDICATORS.md).
2. **Story** per bot: what did each do, turn by turn? (`flip --faction
   F` for collapses/rises, `fog` for what it saw, `autopsy` for deaths.)
   Write the report card.
3. **Right/wrong**: for each bot, what worked (improve the correct
   decisions!) and what failed (lead flips get full audits: what did
   the loser do wrong / winner do right?).
4. **Brainstorm** ideas per bot from the mistakes + improvements
   (doctrine first, code second; GTO.md §9 personalities stay skewed,
   pro stays reference). Log sparks in BRAINSTORM.md.
5. **Bench** (cut_scenario N turns before an issue for targeted repro;
   edit fast/slow suites if an idea needs new coverage).
6. **Iterate** one idea per bot (measure vs table + rematch; suites
   twice, quiet box — JIT first-runs lie).
7. **Rate** with the purist matchmaker (`matchmake.py --play N`:
   propose-1/play-1/update-1 sequentially; info-optimal fields from
   predict_draw + sigma — no count hacks, uncertainty drives). Pool =
   every unique brain ever (dedup by bots/ content hash, random
   included). EVERY game goes through matchmake/elo_field (appends to
   elo_games.jsonl) — no bare run_game for real games. Target: pool
   all at 3+ games; the champ bar is expander-84b32be ordinal (~44).
8. **Branch-first**: improvement loops run on a branch, committed
   BEFORE any games (bots need IDs to play). Merge gate: max-branch-
   ordinal beats master. On regression the next loop chooses: rebase
   the idea onto master, or fork the branch further — a real decision,
   recorded in BOT_WORKLOG.md. Every merge leaves the pool at 3+ games
   (new brains ground first) with ratings+replot committed.
9. **Analyze** HEAD bots vs the table (where do they lose? which
   matchups? duels vs the champ with recordings + autopsy).
10. **Generate** the new canonical game (`empty_10000` ~30s, quiet box)
   and write it to BOTH viewer locations (`recordings/empty_10000.jsonl`
   for ascii_view + `viewer/public/empty_10000.jsonl` for the web UI —
   the UI serves its own bundled copy, stale copies lie!). Verify:
   `md5sum` both match. The UI cache-busts fetches, but hard-refresh
   once if in doubt. (`empty_3000` retired.)

Per-iteration gates (every loop through step 4): fast suite per change (~1.5s); strategic at milestones
(~10s); `pytest` green; judge vs fog-era table with margin; worklog entry
per change (before → after numbers). Full detail: `BOT_PLAN.md` (The loop).

## Everything else (one iteration + logs)

| You want to… | Read |
|---|---|
| This iteration's backlog | `BOT_PLAN.md` — doctrine + ordered open work |
| This iteration's numbers | `BOT_BENCH.md` — binding fog-era table, suites, methods |
| Past iterations | `BOT_WORKLOG.md` — append-only log, one entry per change |
| Past game reports | `EMPTY_10000.md` — war-verdict (superseded by latest report card) |
| Play well (strategy reference) | `GTO.md` — optimal play, phase playbooks, personality diffs |
| Change bot code (current behavior) | `BOTS.md` — personalities as coded, shared machinery, intel model |
| Spend clock budget wisely | `BOT_TIME.md` — Fischer-clock infrastructure (ideas 1–6, landed) |

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
  saturation → production war → strip-mine flip. Full doctrine: `GTO.md`.

Per-iteration gates (every loop through step 5):
1. Fast suite (`benchmarks/scenario_bench.py`, ~1.5s) per change.
2. Strategic suite (`benchmarks/strategic_bench.py`, ~10s) at milestones.
3. `empty_10000` rematch read as war ledger (~30s, quiet).
4. `pytest` green. Judge vs the fog-era table only, with margin
   (clock-driven order wobble ≈ ±50 on long games — run benches quiet).
5. Worklog entry per change (before → after numbers).

## File map (iterations + logs)

- `BOT_PLAN.md` — this iteration's backlog (doctrine + open work).
- `BOT_BENCH.md` — this iteration's numbers (binding table + suites).
- `BOT_WORKLOG.md` — iteration log (append-only — do not rewrite old entries).
- `VIEWER.md` — how we analyze (ascii_view tool: modes, ACJSON, recipes).
- `EMPTY_10000.md` — old game report (superseded by latest report card).
- `GTO.md` — strategy reference (doctrine companion, living).
- `BOTS.md` — implementation guide (code as it is).
- `BOT_TIME.md` — clock infrastructure.
