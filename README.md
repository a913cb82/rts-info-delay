# rl_game_min

Strategy game with fog of war and information delay.

You only see what messengers report to the capital. Your armies only receive orders when messengers reach them.

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

## The game

### Overview

Turn based. Each turn consists of phases:

#### Command
- Bot receives newly visible events
- Bot submits orders

#### Propagation
- Order messengers move 150km towards destinations
- Order recipients receive orders

#### Movement
- Armies move in ordered direction
- Armies and Towns block enemy armies

#### Combat
- Armies fight each other
- Weakness = # enemy armies within 10km
- If Army weakness <= weakness of any enemy within 10km, Army dies

#### Captures
- Enemy Army near Town changes ownership and halves population

#### Economy
- Towns grow logistically, with crowding effect from other nearby towns
- Towns under 500 population die
- Armies with build orders build new Towns or boost existing Towns

#### Knowledge
- Events generated for every Army and Town and tagged by timestamp and faction visibility

### Details

- Score = town population + 1000 per army. Highest score at max turns wins.
- Eliminated with no capital and no viceroy in flight.
- Orders: `TRAIN <town>` (costs 1000 pop), `MOVE_TO <army> <fx> <fy> <tx> <ty>`,
  `BUILD <army> <x> <y>` (founds a pop-500 town, or adds pop to own town),
  `MOVE_CAPITAL <x> <y>` (commander marches out, founds on arrival).
- Only `BUILD` founds towns. Captures never promote. Beheading is permanent.
- Bots see delayed reports only: 150km sight, mail travels 150km/turn to
  the capital, nothing from before the last landing.

## Bots

Bots run as separate processes and communicate with the engine by stdin and stdout.

### Input Format

Line protocol. Startup block, then one block per turn:

```
config {rules + map_size, never the map}
faction <n>
go
turn <t>
clock <budget_ms>
{event json, one per line}
go
```

Events: `town_update` (`id,x,y,faction,population,is_capital`, pop 0 =
dead) and `army_update` (`id,x,y,faction,alive,is_viceroy`). No positions
for unseen things, no destinations, no battles. `end` instead of a block
means the game is over (or you are muted mid-flight: no block at all).

### Output Format

One order per line (see Details), then `go`. Unknown commands and bad
numbers are ignored. Missing `go` past the clock budget kills the bot
(timeout counts as dead, orders dropped).

## Layout

- `src/engine/` — game rules.
- `src/runner/` — game loop.
- `src/bots/` — demo bots.
- `maps/` — game maps
- `benchmarks/` — bot performance and runtime performance benchmarks.
- `viewer/` — replay UI.
- `tests/` — engine, runner, and bot tests.
- `docs/` — development work planning and recording.
