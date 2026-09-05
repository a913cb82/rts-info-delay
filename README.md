# rl_game_min

A minimal deterministic strategy game: five bots fight over towns on a
2D map. No randomness anywhere — same code, same game, every time.

## Quickstart

```bash
source .venv/bin/activate
# run a 3000-turn game with all five bots
PYTHONPATH=src python - <<'EOF'
import json, sys
from pathlib import Path
from engine.config import GameConfig
from runner.main import run_game
d = json.loads(Path("maps/empty.json").read_text())
d["max_turns"] = 3000
cfg = GameConfig.from_dict(d)
teams = {0: "pro", 1: "greedy", 2: "aggressive", 3: "expander", 4: "turtle"}
run_game(cfg, {f: [sys.executable, "-m", f"bots.{n}"] for f, n in teams.items()},
         Path("recordings/empty_3000.jsonl"))
EOF
cp recordings/empty_3000.jsonl viewer/public/empty_3000.jsonl
# watch it (dev server on 5173)
cd viewer && npx vite --port 5173 --strictPort
# → http://localhost:5173/?game=empty_3000.jsonl&names=pro,greedy,aggressive,expander,turtle
```

```bash
python -m pytest tests/                        # full suite (~4s)
PYTHONPATH=src python benchmarks/scenario_bench.py      # fast bot suite (~2s)
PYTHONPATH=src python benchmarks/strategic_bench.py     # slow suite (~9s)
```

## The game

**Goal.** Highest score at the end. Score = Σ town population +
1000 per army. A faction is eliminated when it has no capital and no
commander (viceroy) in flight.

**Pieces.** Towns have population, an owner, and a capital flag. Armies
belong to a faction and move 50 km/turn. That's it — no resources, no
tech, no terrain.

**A turn** runs seven phases: command → propagation → movement →
combat → captures → economy → knowledge.

**Orders** (all ride messengers at 150 km/turn, so distance means lag):

- `TRAIN <town>` — pay 1000 pop, spawn an army (needs ≥1000 pop left).
- `MOVE_TO <army> <x> <y>` — march there.
- `BUILD <army> <x> <y>` — consume the army: found a new town (pop 500)
  on empty land, or add pop to your own town.
- `MOVE_CAPITAL <x> <y>` — abandon your capital, send the commander
  marching; if he arrives he founds a new capital. Lose him and you're
  beheaded for good.

**Combat.** Armies count nearby enemies: any strict outnumbering (2v1,
3v2) kills clean with zero casualties; equal numbers (1v1 *and* 2v2)
annihilate everybody.

**Captures.** An unopposed army at a town flips it: population halved,
capital flag removed. Captures never create capitals — beheading is
permanent. Only `BUILD` founds new towns.

**Economy.** Towns grow logistically (~a few pop/turn); below 500 pop a
town dies. A train-then-build cycle costs ~1500 score and repays over
hundreds of turns — spending, not income, is the scarce resource.

**Fog of war.** Bots never see the map or the truth — only delayed
reports. Each turn they learn what their own towns/armies can see
(150 km), delivered late by distance to their capital, and nothing from
before their last landing. After moving capital they forget everything
and re-learn from scratch. Click a faction name in the viewer header to
see its live field of view.

## Bots

One line each; full guide in `docs/BOTS.md`, plans in `docs/BOT_PLAN.md`:

- **greedy** — raids whatever pays, recycles idlers.
- **aggressive** — seeks the leader, attacks in packs.
- **expander** — settles everywhere, accepts decapitation.
- **turtle** — hoards behind threat-responsive bars, evacs when doomed.
- **pro** — no personality: counter-punches duels, pressures wars.

## Layout

- `src/engine/` — rules: step phases, movement, combat, economy, ledger.
- `src/runner/` — game loop: bot subprocesses, clocks, intel delivery, records.
- `src/bots/` — the five personalities + shared machinery (`common.py`).
- `maps/` — `empty.json`, `full.json`, `scenarios/` (fast suite),
  `strategic/` (slow suite).
- `benchmarks/` — `scenario_bench.py`, `strategic_bench.py`, `bench_suite.py`.
- `viewer/` — turn-by-turn replay UI (map, fog overlay, score graph).
- `tests/` — engine, runner, and bot suites.
- `docs/` — `BOTS.md` (guide), `BOT_PLAN.md` (roadmap), `BOT_BENCH.md`
  (numbers), `BOT_TIME.md` (clocks), `BOT_WORKLOG.md` (history),
  `EVENT_REWORK.md` (intel pipeline spec), `TESTS.md` (test protocol).
