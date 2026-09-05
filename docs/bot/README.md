# Bots

Five demo bots (`src/bots/`: pro, greedy, aggressive, expander, turtle)
playing a fully deterministic strategy game under fog of war. This folder
is the complete reference for bot improvement work.

## Start here

| You want to… | Read |
|---|---|
| Play well (strategy reference) | `GTO.md` — optimal play, phase playbooks, personality diffs |
| Change bot code (current behavior) | `BOTS.md` — personalities as coded, shared machinery, intel model |
| Know what to build next | `BOT_PLAN.md` — doctrine + ordered open work (Steps 0–6) |
| Judge a change by numbers | `BOT_BENCH.md` — binding fog-era table, suites, methods (run quiet) |
| Spend clock budget wisely | `BOT_TIME.md` — Fischer-clock infrastructure (ideas 1–6, landed) |
| See what was tried | `BOT_WORKLOG.md` — append-only history, one entry per change |

## Current state (one page)

- **Personalities:** 0=pro (GTO reference) 1=greedy (skipper) 2=aggressive
  (predator) 3=expander (sprawl) 4=turtle (fortress). `stub` is passive
  harness furniture. No randomness anywhere, ever.
- **Intel model:** snapshots, late — LOS 150km eyes, 150km/turn mail,
  three delivery gates (tagged + released + ≥ S). Bots never get the map.
- **Scoreboard:** `BOT_PLAN.md` (live) — empty_3000: pro 6263 / greedy
  5688 / expander 5200 / aggressive 3089 / turtle 2297 (equilibrium-tight;
  sloshes — judge mechanisms + suites). Exam 23/23 all green.
- **Open milestones:** ALL plan Steps substantially done (2 all-five, 3
  meeting/tempo, 4 compositional, 5 hopeless/evac/snipe/guards, 6
  buzzer/strikes; recon + pickets shipped). Filed-futures in plan/GTO.
  Details: `BOT_PLAN.md`.
- **Strategy backbone:** compound → expand on payback math → fortress at
  saturation → production war → strip-mine flip. Full doctrine: `GTO.md`.

## Workflow (gates for every change)

1. Fast suite (`benchmarks/scenario_bench.py`, ~1.5s) per change.
2. Strategic suite (`benchmarks/strategic_bench.py`, ~10s) at milestones.
3. `empty_3000` rematch read as a trade ledger (~4s).
4. `pytest` green. Judge vs the fog-era table only, with margin
   (clock-driven order wobble ≈ ±50 on long games — run benches quiet).
5. Worklog entry per change (before → after numbers).

## File map

- `GTO.md` — strategy reference (this folder's doctrine companion).
- `BOTS.md` — implementation guide (code as it is).
- `BOT_PLAN.md` — roadmap (doctrine + Steps + scoreboard).
- `BOT_BENCH.md` — measurements (binding table + suites + history).
- `BOT_TIME.md` — clock infrastructure.
- `BOT_WORKLOG.md` — history (append-only — do not rewrite old entries).
