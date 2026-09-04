# Plan — `rl_game_min`

## Engine: Python

Core game logic in Python (`engine/` package). Game runner also Python — spawns bot subprocesses, manages stdin/stdout, enforces time limits. Bots in Python.

Use numpy for vectorised operations (spatial queries, distance matrices, crowding sums). Use numba `@njit` for hot loops (path blocking closest-approach, combat weakness checks).

## Defaults

1 turn = 1 week.

| Parameter | Value |
|---|---|
| map_size | [1000, 1000] km |
| map | CSV list of entities (see Starting map format) |

| Parameter | Value |
|---|---|
| max_turns | 500 |
| turn_time_ms | 1000 |

| Parameter | Value |
|---|---|
| info_speed | 150 km/turn |
| army_speed | 50 km/turn |
| army_cost | 1000 pop |
| interact_radius | 10 km |

| Parameter | Value |
|---|---|
| population_cap | 100000 pop |
| population_growth | 0.001 |  # fraction per week; peak = growth_rate × cap / 4 = 25 pop/week |
| build_efficiency | 0.5 |

| Parameter | Value |
|---|---|---|
| equilibrium_spacing | 0.4 km · pop⁻¹ᐟ² |
| crowding_decay | 0.3 |
| crowding_asymmetry | 0.006 |

## Map

Fixed rectangular, continuous positions (floats, km). Positions clamp at edges.

### Starting map format

CSV list of entities with coordinates:

```
x,y,type,population
100,200,A,500
300,400,B,10000
150,250,a,
350,450,b,
```

- `A-Z` = towns (letter = faction; own faction always A)
- `a-z` = armies (letter = faction; own faction always a)
- `population` = town pop (empty for armies)
- Coordinates in km
- Capital = first town per faction

## Entities

- **Armies**: id, faction, x, y. Move toward target at army_speed. ~1000 men.
- **Towns**: id, faction, x, y, population, is_capital. Towns die when population falls below army_cost × build_efficiency (500 pop).

## Town economy

- **Population growth**: `population += logistic(A) × [1 − Σ asym(A, B_i) × (d_eq_i / d_i)^crowding_decay]` summed over all other towns B_i witin `info_speed`.
  - `logistic(A) = population_growth × A × (1 − A / population_cap)` per turn
  - `d_eq_i = equilibrium_spacing × √min(A, B_i)` — equilibrium distance for the pair
  - `asym(A, B) = 1 + crowding_asymmetry × log(B / A)` — larger neighbours crowd more, smaller less
- **TRAIN**: population -= army_cost. Army spawns at town. Standing order.
- **BUILD (away from town)**: army consumed. New town at army position, population = army_cost × build_efficiency.
- **BUILD (on town)**: army consumed. Town population += army_cost × build_efficiency.
- **Death**: town dies when population < army_cost × build_efficiency (500 pop).

## Movement & path blocking

Armies move along straight line from start to destination. Paths checked against hostile entities:

- **Enemy armies**: if minimum distance between an army's path and any enemy army (moving or stationary) ≤ interact_radius, the moving army stops at closest approach. If both are moving and each path comes within radius of the other, both stop.
- **Enemy towns**: if army path comes within interact_radius of enemy town, army stops at closest approach point.

Closest approach: for P_i(t) = A + t·V_i, P_j(t) = B + t·V_j (t ∈ [0,1]), minimum at t* = clamp(-(D·E)/|E|², 0, 1) where D = B-A, E = V_j - V_i. Contacts resolve earliest-first. Stopped/dead party voids later contacts. Fresh spawns immune.

## Combat (weakness-based)

After all movement resolves. For each army, weakness = number of enemy armies within interact_radius. An army dies if any enemy within interact_radius has weakness ≤ its own weakness. Tie: both die.

- 2v1: outnumbered army dies, two attackers survive.
- 1v1: both die (mutual annihilation).
- 0 enemies: safe.

Deaths computed simultaneously from final positions.

## Information delay (eyes instant, mail slow)

Observation uses current positions: faction F observes entity E at turn t
iff any F entity is within `line_of_sight` of E (own entities always,
dist 0). Reporting uses distance to the *current* capital: F receives a
ledger entry iff (1) F observed it that turn (tag), (2) exact delay
`t + dist(entry, capital)/info_speed ≤ now` (not floor), (3) generation
turn ≥ S (last landing turn, 0 if never landed). At most one update per
entity per payload (newest passing wins); re-delivery only on snapshot
change (slim wire). Bots never receive the map — empty start, first
payload creates the own capital.

The ledger is a windowed (`diag/info_speed` turns) tagged generation log:
every observed entity gets an entry every turn (unobserved cost nothing);
vanished ids yield one death entry tagged with site observers, pruned past
the window. Deaths pass all three gates like everything else. No instant
intel anywhere — own capital (dist 0) is the only fresh reading.

Landing: engine sets nothing but the world (founding is economy's
BUILD-step); the runner detects own-capital founding in step events,
sets S, and resets send-state — without the reset, entities unchanged
since before the flight would compare equal and stay silent to a bot
that forgot them. Bot side: amnesia on its own remembered MOVE_CAPITAL
order (stream jump confirms success, sequential means failure). Mute is
the I/O skip; flight tags die in the S-filter unobserved.

## Order lag

All orders travel via messenger at info_speed. Delivered when messenger reaches target. FIFO per entity. Dead letters if target destroyed. MOVE_CAPITAL is a normal command whose target is the capital itself (distance 0, so delivered the same turn); it executes in economy as a pre-programmed TRAIN (deduct, demote old capital, spawn viceroy with its march target). The viceroy marches under normal movement and founds as the BUILD-step in economy (BUILD tolerance, consumed on success) — so it lives through combat: evacuating into contact means an interception battle first. No capital exists during the flight; a failed evac (viceroy dies) beheads permanently.

## Commands

| Command | Target | Effect |
|---|---|---|
| `MOVE_TO <army_id> <from_x> <from_y> <to_x> <to_y>` | Army | Walk toward (to_x,to_y). Standing order. |
| `TRAIN <town_id>` | Town | Population -= army_cost. Army spawns at town. Standing order. |
| `BUILD <army_id> <x> <y>` | Location | Army consumed. Found town (pop = army_cost × build_efficiency) or boost existing town (+ army_cost × build_efficiency pop). |
| `MOVE_CAPITAL <x> <y>` | Viceroy | Pre-programmed TRAIN (costs army_cost pop, demotes old capital at train time) + march to (x,y) + BUILD-step in economy. Founding consumes the viceroy; faction blind during flight. |

All commands are valid only if the commander faction owns the target. `BUILD` and `MOVE_TO` require the army to be within `interact_radius` of the command target when the command arrives — otherwise the command has no effect. `TRAIN` is sent to the town at (x,y) via messenger and executes on arrival. `MOVE_CAPITAL` is sent to the capital via messenger (distance 0, delivered same turn) and executes in economy like TRAIN; if the capital falls before economy, the order drops.

## Turn resolution

1. **Command**: factions submit orders.
2. **Propagation**: messengers advance. Deliveries resolve.
3. **Movement**: armies move toward targets. Path contacts stop armies early.
4. **Combat**: weakness kills. All deaths simultaneous.
5. **Economy**: population growth (logistic minus crowding). TRAIN spawns. BUILD consumes. Viceroy founding (the MOVE_CAPITAL BUILD-step).
6. **Knowledge**: generate tagged state updates for every observed entity. Evict old ledger entries.

## Game record format (JSONL)

Full world state every turn for replay/viewer. Trust assumption: the
record is written live during the game with undelayed truth, so bot
processes must be sandboxed from reading it (or it must be buffered to
game end) the day bots are untrusted — today they do no file/network I/O.

```
{"type":"config","map":[1000,1000],"info_speed":150.0,...}
{"type":"turn","turn":1,"world":{"armies":[...],"towns":[...]},"events":[...]}
```

Events (changes only):

| Event | Fields |
|---|---|
| `army_spawn` | id, faction, x, is_viceroy |
| `town_spawn` | id, faction, x, y, population, is_capital |
| `army_move` | id, x, y |
| `army_death` | id, x, y |
| `battle` | x, y, combatants: [{id, faction}], killed: [id] |

## Bot protocol

Persistent subprocesses. Bot tracks own world state. Runner sends only incremental updates.

### Startup
```
config <json_config_object>
faction <faction_id>
go
```

### Each turn
```
turn <turn_number>
<events>
go
```

Bot responds:
```
MOVE_TO <army_id> <from_x> <from_y> <to_x> <to_y>
TRAIN <town_id>
BUILD <army_id> <x> <y>
MOVE_CAPITAL <x> <y>
go
```

Timeout: runner kills process. No orders that turn or ever again.

During MOVE_CAPITAL flight the faction is blind and mute: the runner sends
it no turns and reads no orders (its clock frozen) until landing. Only the
viceroy's death while headless kills the faction (no capital and no viceroy
in flight → dead); if the old capital falls mid-flight the escaped viceroy
still founds and the bot survives.

On landing the runner sets S (last landing turn) and resets the faction's
send-state; the bot wipes on its own remembered MOVE_CAPITAL order (stream
jump confirms success, sequential means failure). Post-S payloads
re-announce survivors paced naturally by delay releases — no batch dump,
no backlog: takeovers and demotions arrive as ordinary faction changes,
deaths as `alive False` / pop 0, all filtered by tag+delay+S like
everything else. A transient seen at S−1 but gone by S is never known.
Ghosts are impossible a different way: the wiped bot has no memory for a
corpse to haunt.

### Game end
```
end <scores_json>
```

## Score

`total_town_population + army_cost × num_armies`

Captures never create capitals: a captured capital is demoted and beheading
is permanent — only MOVE_CAPITAL founds new capitals.

## Spatial optimisation

- **Spatial hash grid**: cell size ≥ interact_radius. Rebuilt each turn O(n). Queries O(k) where k = nearby entities.
- **Ledger window**: events sorted by time, eviction by pointer advance O(1) amortised.

## Viewer

TypeScript + Vite, single-page app. Canvas background + SVG entities.

### Features

- **Map**: canvas fills background. SVG overlay for towns (circles, radius ∝ √pop) and armies (triangles). Faction colours via golden-angle palette.
- **Controls**: pan/zoom (pointer drag, wheel, pinch), turn slider, play/pause, speed selector (0.5×–8×), fit-to-view button.
- **Sidebar**: per-faction town/army counts, total score, event log.
- **Timeline**: event markers (battles, spawns, deaths) as clickable dots on strip.
- **Tooltives**: hover entity → town pop/distances, army faction, battle participants.
- **Load**: file picker or `?game=path.jsonl`. JSONL streamed for large recordings.
- **Animation**: lerp positions between turns with ease-in-out. Spawn = grow-in at source. Death = shrink-out. Armies that move then die lerp to death position (from `army_death`/`battle` event, which equals final movement position) then shrink-fade — not vanish at start. `MOVE_CAPITAL` viceroy (`army_spawn` with `is_viceroy`) grows in at capital then lerps straight toward target each turn; on arrival lerps to destination then shrink-fades as `town_spawn` (new capital) grows in at same pos. Animate battles with lines between participants.

### Rendering

| Element | Shape | Size |
|---|---|---|---|
| town | circle | radius = 8 + 12 × √(pop / population_cap) |
| capital | circle + center dot | same + white dot |
| army | triangle | fixed size, stacked if co-located |
| battle | crossed lines | at battle position |

## Project layout

```
rl_game_min/
├── pyproject.toml
├── src/
│   ├── engine/   (config, world, spatial, ledger, combat, economy, movement, step, record)
│   ├── runner/   (main)
│   └── bots/     (random, greedy, stub)
├── tests/
│   ├── engine/   (test_config, test_world, test_economy, test_movement, test_combat, test_ledger, test_spatial, test_step, test_record)
│   ├── runner/   (test_main)
│   └── test_score.py, test_integration.py
└── viewer/
    ├── src/      (main, types, transform, color, styles)
    └── tests/    (transform, color, types)
```
