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

Turn-based. Each turn consists of phases:

#### Command
- Bot receives newly visible updates
- Bot submits orders

#### Propagation
- Order messengers move 150km towards destinations
- Order recipients receive orders

#### Movement
- Armies move in ordered direction
- Armies and towns block enemy armies

#### Combat
- Armies fight each other
- Weakness = #enemies within 10km
- An army dies if any enemy in range has weakness <= its own
- Towns are taken by the lowest-weakness nearby army's faction
    - Tie across factions leads to no capture
    - Population halves on capture and capitals demoted to normal towns

#### Economy
- Towns grow logistically, with crowding from nearby towns
- Towns under 500 population die
- Armies with build orders found new towns or boost existing towns

#### Knowledge
- Updates generated for every observed army and town, tagged by timestamp and faction visibility

### Details

- Score = Σ town population + 1000 per army. Highest score at end wins.
- Growth per turn: `0.001·P·(1 − P/100000) × (1 − Σ crowding)` at population `P`
    -  `crowding = (1 + 0.01·ln(Pn/P)) × (0.1·√min(Pn,P) / d)^0.8` for neighbour with population `Pn` at distance `d <= 150km`
- Eliminated when no capital and no viceroy in flight.
- Armies and towns have 150km line of sight, mail travels 150km/turn to/from the capital.
- `MOVE_TO`/`BUILD` are discarded unless the army is within 10km of the target on arrival.
- Towns can only `TRAIN` one army per turn (additional `TRAIN` commands are discarded)
- Viceroy in flight receives no information during flight, and only information on events which happened after new capital was founded.

| Order          | Syntax                               | Effect                                                  |
|----------------|--------------------------------------|---------------------------------------------------------|
| `TRAIN`        | `TRAIN <town>`                       | −1000 pop, spawn an army                                |
| `MOVE_TO`      | `MOVE_TO <army> <fx> <fy> <tx> <ty>` | march to `(tx, ty)`                                     |
| `BUILD`        | `BUILD <army> <x> <y>`               | consumes army: found pop-500 town, or +500 pop          |
| `MOVE_CAPITAL` | `MOVE_CAPITAL <x> <y>`               | viceroy marches out, founds new capital on arrival      |

## Bots

Bots run as separate processes and communicate with the engine by stdin and stdout.

Bots are allocated a time budget and killed if exhausted:
- 1 second of initial time
- Once initial time exhausted, 100ms max time bank which refills 10ms every turn

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

Events sent for every entity visible, delayed by `info_speed`
- `town_update` (`id,x,y,faction,population,is_capital`, pop 0 = dead)
- `army_update` (`id,x,y,faction,alive,is_viceroy`).
- `end` instead of a block means the game is over (or you are muted mid-flight: no block at all).

### Output Format

One order per line, then `go`. Missing `go` past the clock budget kills the bot.

## Layout

- `src/engine/` — game rules.
- `src/runner/` — game loop.
- `src/bots/` — demo bots.
- `maps/` — game maps.
- `benchmarks/` — bot performance and runtime performance benchmarks.
- `viewer/` — replay UI.
- `tests/` — engine, runner, and bot tests.
- `docs/` — development work planning and recording (`docs/bot/` — bot strategy, guide, roadmap, benchmarks).
