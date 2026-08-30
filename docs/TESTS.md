# Tests — `rl_game_min`

> Coverage audit of `docs/PLAN.md`. Each section below maps 1:1 to a PLAN heading.
> Existing tests flagged **FIX** were numerically or logically wrong; **NEW** fill gaps.

## 1. Defaults / Config

| # | Test | Input | Expected | Notes |
|---|---|---|---|---|
| X1 | Default values applied | no config overrides | map_size=[1000,1000], max_turns=500, turn_time_ms=1000, info_speed=150, army_speed=50, army_cost=1000, interact_radius=10, population_cap=100000, population_growth=0.001, build_efficiency=0.5, equilibrium_spacing=0.4, crowding_decay=0.3, crowding_asymmetry=0.006 | |
| X2 | Config overrides defaults | config json with `{"army_speed": 30}` | army_speed=30, others default | |
| X3 | Config field names match PLAN exactly | startup `config <json>` line | keys spelled `equilibrium_spacing`, `crowding_decay`, `crowding_asymmetry`, `population_cap` etc. (no `k`/`gamma`/`c`) | name mismatch breaks bots |
| X4 | No `num_factions` in config | config json | field absent; faction count inferred from map letters | regression |
| X5 | Map field is CSV entity list | config map | value is string `"x,y,type,population\n..."` not `terrain` | rename from rl_game |

## 2. Map

| # | Test | Input | Expected |
|---|---|---|---|
| P1 | CSV parsing — towns | `100,200,A,500` | town id assigned, faction=0 ('A'), x=100, y=200, pop=500 |
| P2 | CSV parsing — armies | `150,250,a,` | army id assigned, faction=0 ('a'), x=150, y=250, no pop |
| P3 | Faction letters mapped | `A-Z` towns, `a-z` armies, same letter = same faction | A/a → faction 0, B/b → faction 1, etc. |
| P4 | Own-faction perspective | faction 1 bot's view | its own entities relabelled A/a (capital always A-equivalent in its ledger view) |
| P5 | Capital = first town per faction | `A` at (0,0) then `A` at (100,100) for same faction | first has is_capital=true, second false |
| P6 | Capital per faction independent | 2 factions, each with 2 towns | each faction's first town is its capital (2 capitals total) |
| P7 | Continuous positions | coord `100.7, 200.3` | stored as float, not snapped to int |
| P8 | Edge clamping — move beyond map | army at (995,995), target (2000,2000), speed 50 | army clamps to (1000,1000) |
| P9 | Edge clamping — spawn beyond map (if allowed) | BUILD at (1001, 500) | town clamped to map edge or rejected (consistent choice) |
| P10 | Map size respected | map_size=[500,500], entity at (600,600) | clamped to [500,500] or rejected at parse |
| P11 | Population column required for towns | `100,200,A,` (missing) | parse error / default rejected |
| P12 | Army population column empty | `100,200,a,500` (has pop) | ignored or parse error — armies carry no pop |

## 3. Entities

| # | Test | Input | Expected |
|---|---|---|---|
| N1 | Army fields | spawned army | has id (unique), faction, x, y; moves at army_speed; count ~1000 men (army_cost) |
| N2 | Town fields | spawned town | id, faction, x, y, population, is_capital |
| N3 | Town death threshold | pop after economy step | dies when `< 500` (strictly below `army_cost × build_efficiency`), survives at `== 500` — **FIX**: was `≤ 500` |
| N4 | Town ids stable | town survives 10 turns | same id throughout |
| N5 | Army ids unique across factions | spawn 2 armies same turn, different factions | ids distinct |

## 4. Town economy — logistic (isolated)

| # | Test | Input | Expected | Notes |
|---|---|---|---|---|
| E1 | Village (500) isolated | pop=500, no neighbours | Δ = 0.001×500×(1−0.005)=0.4975 → 500.498 | |
| E2 | City at peak (50000) isolated | pop=50000 | Δ = 0.001×50000×0.5 = **25.0** → 50025 | **FIX**: was 1.3 |
| E3 | At cap (100000) | pop=100000 | Δ = 0 | |
| E4 | Over cap (120000) | pop=120000 | Δ = 0.001×120000×(−0.2)= **−24** → 119976 | **FIX**: was −0.24 |
| E5 | Annualised village ≈5.2% | run 52 turns from 500 isolated | 526 (±1) | compound logistic |
| E6 | Annualised city ≈2.6% | run 52 turns from 50000 isolated | ~51300 (±50) | near peak |
| E6b | Per-turn logistic formula exact | brute compute `population_growth * A * (1 - A/population_cap)` for A=500,1000,50000,100000 | matches engine to 1e-9 | unit test for `economy.py` |
| E6c | Logistic peak location | sweep A in [0,100000] | maximum at A=50000, value=25/week | |

## 5. Town economy — crowding (core formula)

PLAN: `net(A) = logistic(A) × [1 − Σ asym(A,B_i) × (d_eq_i/d_i)^crowding_decay]` over B_i **within `info_speed`** (150 km).

| # | Test | Input | Expected |
|---|---|---|---|
| E7 | Two villages at d_eq (8.94 km) | A=B=500, dist=0.4×√500=8.94 | net≈0 for both (balanced) |
| E8 | Two markets at d_eq (12.65 km) | A=B=1000, √1000×0.4=12.65 | net≈0 |
| E9 | Two cities at d_eq (89.44 km) | A=B=50000, √50000×0.4=89.44 | net≈0 |
| E10 | Symmetric pair closer than d_eq (6 km) | A=B=500, dist=6 (<8.94) | net < 0 (decay) |
| E11 | Symmetric pair farther than d_eq (12 km) | A=B=500, dist=12 | 0 < net < isolated (partial relief) |
| E12 | Village near city, village crowded | A=500, B=50000, dist=5 | net(A) strongly negative (asym>1) |
| E13 | City near village, city indifferent | A=50000, B=500, dist=5 | net(A) ≈ logistic(A) (asym<<1, d_eq=8.94 so ratio>1 but asym dampens) |
| E14 | Cross-size at small d_eq | A=500, B=50000, dist=8.94 | net≈0 (d_eq uses min=500) — **FIX**: was mis-placed at 8.9 (correct) |
| E15 | Market–provincial at its d_eq | A=1000, B=10000, min=1000 → d_eq=12.65 | net≈0 |
| E16 | Asymmetry direction | A=500, dist=10 fixed, B=50000 vs B=500 | larger B → more negative net for A |
| E17 | Asymmetry log scale | A=500, B=50000 (100×) vs B=1000 (2×) at same dist | 100× only slightly worse than 2× (log compression) |
| E18 | Symmetric asym=1 | A=B any pop | `1 + 0.006×log(1)=1` |
| E18b | Asymmetry numeric | A=500,B=50000 → asym=1+0.006×log(100)=1+0.006×4.605=1.0276 | engine matches |
| E18c | d_eq uses min | A=500,B=50000 → d_eq=0.4×√500=8.94 not √50000 | net same as two villages at same dist |
| E19 | Two neighbours sum | A centre, B1 and B2 both at d_eq opposite sides | Σ has 2 terms → net more negative than single-B case |
| E20 | Mixed near+far | B1 at 6 km (crowding), B2 at 20 km (relief) | net between B1-only and B2-only |
| E21 | No neighbours = isolated | single town on map | net=logistic |
| **E30** | **Cutoff at `info_speed` (NEW)** | A at (0,0), B at 151 km (just beyond 150), both 500 | B excluded from Σ → net=logistic(A) |
| **E31** | **Just inside cutoff (NEW)** | B at 149 km | B included → net < logistic |
| **E32** | **Far decay still felt — flat γ=0.3 (NEW)** | A=B=500, dist=100 km (≈11× d_eq) | `(8.94/100)^0.3 ≈ 0.52` → still 52% crowding weight, net meaningfully reduced vs isolated |
| **E33** | **Cannot skip distant pairs (NEW)** | 5 towns spread 80 km apart all 500 pop | each town's Σ has 4 distant terms, total crowding ≈ 4×0.5×logistic → strong even at 80 km |
| **E34** | **Three-body sum vs pairwise (NEW)** | A with B1=500 at 10 km, B2=500 at 10 km on same side | Σ = term1+term2, net = logistic×(1−sum), not pairwise sequential |

## 6. Town economy — death, TRAIN, BUILD

| # | Test | Input | Expected |
|---|---|---|---|
| E22 | Town at 499 dies | pop=499 after economy step, no recovery | removed from world |
| E23 | Town at 500 survives | pop=500 after economy step | survives (threshold is `<500`) |
| E24 | Isolated village never dies | pop=500, no neighbours, 100 turns | pop grows, never dips below 500 |
| E25 | BUILD on empty ground | army owned by faction at (100,200), `BUILD <id> 100 200` delivered | new town at (100,200), faction same, pop=500, is_capital=false, army removed |
| E26 | BUILD on existing town | army at town pos (town pop 2000) | town pop +=500 → 2500, army removed |
| E27 | BUILD consumes army | any BUILD | army array no longer contains id |
| E28 | BUILD distance fail | army at (0,0), target (20,0) (>10) when messenger arrives | no town created/boosted, army survives |
| E29 | TRAIN reduces pop | town pop 2000, `TRAIN <id>` arrives | pop=1000, army spawned |
| E30b | TRAIN spawns at town | town at (300,400) | new army at (300,400), faction same |
| E31b | TRAIN when pop=800 | town pop 800, TRAIN cost 1000 | pop → −200 then death check → town removed (**or** TRAIN rejected — pick one and document; current PLAN implies unconditional subtract then die) |
| E31c | TRAIN standing order | `TRAIN <id>` once, 3 turns pass, pop sufficient | spawns 3 armies over 3 turns (one per economy step) |
| E31d | TRAIN insufficient pop — no spawn? | town pop 400, TRAIN standing | if pop<1000, no army spawned (alternative spec) — **decision needed; test pins chosen behaviour** |
| E31e | TRAIN ownership check | enemy town id | command ignored |
| E31f | BUILD faction of new town | faction B army builds | new town faction=B |
| E31g | BUILD on enemy town? | army at enemy town position | still boosts that town? or ownership check fails? — PLAN says BUILD valid only if owns target? Need clarify: target is location, not town — so always valid if army owned |

## 7. Movement — basic

| # | Test | Input | Expected |
|---|---|---|---|
| M1 | Moves toward target | army (0,0), target (100,0), speed 50 | after 1 turn: (50,0) |
| M2 | Reaches short target | army (0,0), target (30,0) | (30,0) — stops, not overshoot |
| M3 | Does not overshoot | army (0,0), target (10,0) | (10,0) not (50,0) |
| M4 | No target stays put | army (50,50), no MOVE_TO | (50,50) |
| M5 | Diagonal short | army (0,0), target (3,4) (dist 5 < 50) | (3,4) |
| M6 | Edge clamping | army (5,5), target (-100,-100) | clamps to (0,0) after move |
| M6b | Exact speed distance | target exactly 50 away | reaches target in 1 turn |
| M6c | Standing order continues | MOVE_TO (100,0) from (0,0), no new orders | turn2 at (100,0) if map big enough, actually (50,0)→(100,0) over 2 turns |
| M6d | From field matches position | `MOVE_TO <id> <fx> <fy> <tx> <ty>` where (fx,fy) not near army actual pos | command ignored (stale) — **NEW: validates MOVE_TO from** |

## 8. Movement — path blocking (armies)

| # | Test | Input | Expected |
|---|---|---|---|
| M7 | Crosses stationary enemy within radius | A (0,0)→(100,0), enemy at (50,5) (dist 5) | A stops at closest approach ≈(50,0) |
| M8 | Head-on both moving | A (0,0)→(100,0), B (100,0)→(0,0), speed 50 each | both stop at ≈(50,0) (each path within radius of other) |
| M8b | Asymmetric approach (NEW) | A (0,0)→(100,0), B (50,50)→(50,150) — A passes near B start but B moves away | only A stops (B's path not near A's path) |
| M9 | Friendly does not block | A (0,0)→(100,0), friendly at (50,5) | A reaches (100,0) |
| M10 | Beyond radius passes | A (0,0)→(100,0), enemy at (50,20) | A reaches target |
| M11 | Earliest contact first | A (0,0)→(100,0), E1 (30,5), E2 (70,5) | stops at E1 (≈30,0) |
| M11b | Exact radius boundary (NEW) | enemy at dist exactly 10.0 | stops (≤ radius) |
| M11c | Just outside boundary (NEW) | enemy at dist 10.001 | passes |
| M11d | Moving enemy beyond radius at t* (NEW) | A→(100,0), B→ elsewhere, min dist 10.5 | no stop |
| M12 | Enemy town blocks | A→(200,0), enemy town at (100,3) | stops at ≈(100,0) |
| M13 | Far enemy town passes | town at (100,30) | reaches target |
| M14 | Stops at approach point not entity pos | A (0,0)→(200,0), town at (100,5) | stops at (100,0) not (100,5) |
| M14b | Friendly town does not block (NEW) | own town at (100,3) | passes |
| **M15** | **Earliest-first void (NEW + FIX)** | A would hit E1 at t=0.3 and E2 at t=0.7; but E2 is dead town already destroyed this turn's economy? Actually combat after movement, so economy/combat deaths don't void movement — only earlier **movement** stops void later | E2 ignored after E1 stop |
| **M16** | **Closest-approach formula numeric (NEW)** | D=(10,0), E=(−2,0) → t* = clamp(−(D·E)/\|E\|²)= clamp(20/4)=clamp(5)=1 → min at end | engine gives t*=1 |
| M16b | t* middle | D=(0,10), E=(0,−20) → t*=0.5 | min halfway |
| M16c | E=0 (parallel same velocity) | V_i==V_j → E=0 → t* =0 (no divide-by-zero) | handle as stationary distance check |
| M16d | t* clamped low | D·E positive → negative t* → clamp 0 | min at start |
| **M17** | **Fresh spawn immune (NEW)** | army spawned this turn at (50,0), A path through it | A not blocked, spawned army not moved |
| M17b | Fresh spawn also doesn't block towns | spawn at town path | no block |

## 9. Combat (weakness-based)

PLAN: `weakness = #enemy armies within interact_radius`; army dies if **any** enemy in radius has `weakness ≤ own weakness`; simultaneous.

| # | Test | Input | Expected |
|---|---|---|---|
| C1 | 1v1 mutual | 2 armies within 10 | both die |
| C2 | 2v1 | 2 (F_A) vs 1 (F_B) within 10 | single dies (weakness 2 vs enemies' 1), pair survives (weakness 1 vs enemy 2 → 2 ≤1 false) |
| C3 | 3v2 | 3 vs 2 within 10 | **2 die**, 3 survive — **FIX**: was “all 5 die” |
| C4 | Weakness counts correctness | single sees 2, each of pair sees 1 | single dies (enemy has 1 ≤2), pair survives (enemy has 2, 2 ≤1 false) — **FIX**: was inverted |
| C5 | No enemies safe | lone army | survives |
| C6 | Simultaneous snapshot | A kills B, B kills C in same radius, sequential removal would spare C | all die based on initial weaknesses |
| C7 | Allies counted correctly | 2 allies vs 1, same faction | as C2 |
| C7b | Multi-faction all enemies (NEW) | F_A:1, F_B:1, F_C:1 all within 10 → each sees 2 enemies | all die (each weakness=2, enemy has 2 ≤2) |
| C7c | Mixed distances (NEW) | A near B (5 away), B near C (5 away), A–C 15 apart (>10) | A sees only B (w=1), C sees only B (w=1), B sees A and C (w=2) → A dies? need compute: A enemy B(w=2) → 2≤1 false so A survives, same C survives, B enemy A(w=1) →1≤2 true so B dies → only middle dies |
| C7d | Exactly at radius (NEW) | enemies at 10.0 | counts as within (≤) |
| C7e | Just outside (NEW) | enemies at 10.001 | not counted |
| C8 | Chain (existing) | line of 3, all in radius | compute from formula — re-validate |
| C9 | 3 factions circle | 3 armies diff factions all within 10 | all die (each w=2) |
| C9b | 2v2 (NEW) | 2 vs 2 within 10 | all die (each w=2, enemy w=2 → 2≤2 true) — **important: even numbers annihilate** |
| C9c | Combat uses final positions after movement stops (NEW) | armies blocked at 10 apart vs would have met | weakness checked at stop positions, not intended targets |

## 10. Information delay

| # | Test | Input | Expected |
|---|---|---|---|
| I1 | Near event same turn | event dist 50, info_speed 150 → arrival 0.33 turns | visible at now ≥0.33 → turn 1's `turn` message includes it (if now is integer turn) |
| I2 | Far event delayed | dist 300 → 2.0 turns | visible 2 turns later |
| I3 | At capital immediate | dist 0 | visible next propagation step |
| I4 | Independent delays | 3 events at 10, 150, 300 km | visible at turns now+0, +1, +2 respectively |
| I5 | Ledger window retain | event at dist 800, max map ≈1414, info_speed 150 → window ≥ 9.4 turns | ledger retains ≥10 turns |
| I5b | No delivery during MOVE_CAPITAL flight (NEW) | capital flight turn 5→8 | events otherwise visible in that window are withheld until new capital established |
| I5c | Capital move changes dist (NEW) | event at (0,0), old capital (0,0) vs new capital (500,0) | after move, dist for old events recomputed? Actually ledger stores (t,x,y) so new capital distance matters for still-undelivered events |
| I5d | Event kind fields (NEW) | any event logged | has t (turn), x, y, kind, payload; dist uses event x,y |
| I5e | Faction-specific visibility (NEW) | 2 factions, event near F_A capital, far from F_B | F_A sees early, F_B late |

## 11. Order lag

| # | Test | Input | Expected |
|---|---|---|---|
| L1 | Travel time 1 turn | order at (0,0) to target 100 km away, speed 150 → 0.67 turns | delivered by next turn's propagation (turn+1) — **FIX**: was inconsistent with L2 |
| L2 | Same-turn if very close | target 10 km away → 0.07 turns | delivered same turn's propagation |
| L3 | FIFO per entity | 2 MOVE_TO to same army, sent turns 0 and 1, second target farther but queued | executes in send order, second overwrites first after first applied |
| L4 | Dead letter — army death | order to army that dies in combat before delivery | discarded, no error |
| L4b | Dead letter — army consumed by BUILD (NEW) | order to army that was BUILD-consumed | discarded |
| L4c | Dead letter — town death (NEW) | TRAIN to town that died from pop loss | discarded |
| L5 | Standing order persists | MOVE_TO once | army continues toward target each turn until new MOVE_TO |
| L5b | TRAIN standing repeats (NEW) | TRAIN once | spawns each economy step until cancelled |
| L5c | Messenger pursuit (NEW) | order to moving army; messenger targets current pos not send-time pos | messenger intercepts; if army moves away, delivery delayed but still follows |
| L5d | FIFO across movement (NEW) | army moving, two orders queued; first changes direction | second starts from new course, not original |
| L5e | MOVE_CAPITAL instant exception (NEW) | MOVE_CAPITAL command | executes instantly at capital, no messenger created |

## 12. Commands

| # | Test | Input | Expected |
|---|---|---|---|
| O1 | MOVE_TO sets course | `MOVE_TO <id> 0 0 100 100` delivered, army owned, within radius of dest? | army target set to (to_x,to_y), moves next movement phase |
| O2 | MOVE_TO distance check | army pos (0,0), cmd `MOVE_TO <id> 0 0 100 100` but dest (100,100) is 141 away (>10) at delivery time **vs** actual rule: army must be within interact_radius of command target when it arrives — target is (to_x,to_y)? Or (from_x,from_y)? **PIN**: decide and test both interpretations explicitly | if dist(army, to) >10 → ignored; army course unchanged |
| O2b | MOVE_TO from validation (NEW) | `MOVE_TO <id> 999 999 100 100` where army not near (999,999) | ignored as stale (from mismatch > epsilon) |
| O3 | MOVE_TO replaces | army moving to A, new MOVE_TO to B delivered | course changes to B |
| O3b | MOVE_TO ownership fail (NEW) | try MOVE_TO on enemy army id | ignored |
| O4 | BUILD empty ground | `BUILD <army_id> 50 50` army at (50,50) | new town at (50,50) pop 500, same faction, army removed |
| O5 | BUILD on own town | army co-located with own town | town pop +=500 |
| O5b | BUILD on enemy town — what happens? (NEW) | army at enemy town pos | **must decide**: either boost enemy town (weird) or forbid — test pins choice |
| O6 | BUILD distance fail | army at (0,0), BUILD 20 0 | no town, army survives |
| O6b | BUILD ownership of army (NEW) | BUILD <enemy_army_id> … | ignored (not owned) |
| O7 | BUILD consumes | after success | army gone |
| O8 | MOVE_CAPITAL instant | `MOVE_CAPITAL 200 200` from capital | guard army raised immediately before propagation; costs 1000 pop from capital (pop −=1000) |
| O9 | MOVE_CAPITAL guard | capital pop 5000 | pop→4000, guard at capital pos with is_viceroy=true |
| O9b | MOVE_CAPITAL guard moves at army_speed (NEW) | guard path to (200,200) | advances 50/turn |
| O10 | MOVE_CAPITAL blind | during flight 3 turns | faction ledger deliveries =0 even for nearby events |
| O10b | MOVE_CAPITAL insufficient pop? (NEW) | capital pop 400 | MOVE_CAPITAL rejected or capital dies? Must decide and test |
| O11 | MOVE_CAPITAL founds | guard arrives | new town at dest, pop 500? or transferred? is_capital=true, old capital is_capital=false |
| O11b | Old capital demoted (NEW) | after arrival | exactly one capital per faction |
| O11c | Multiple MOVE_CAPITAL queued (NEW) | second sent during flight | first in flight blocks second? or rejected while blind |
| O12 | All invalid commands ignored (NEW) | `FOO`, `MOVE_TO` missing args, bad id | no crash, no state change |
| O13 | Multiple commands per turn (NEW) | `TRAIN 1`, `MOVE_TO 2 0 0 10 10`, `BUILD 3 5 5` then `go` | all three processed in order |

## 13. Turn resolution order

PLAN: 1 Command → 2 Propagation → 3 Movement → 4 Combat → 5 Economy → 6 Knowledge

| # | Test | Input | Expected |
|---|---|---|---|
| T1 | Command before movement | order delivered same turn as move | army moves according to new course this turn |
| T2 | Combat after movement | armies would meet at (50,0) | combat checks final (50,0) not start positions |
| T3 | Economy after combat | loan? Actually crowding vs combat: dead armies don't affect growth (they never did) — but TRAIN/BUILD in economy after combat means newly spawned armies don't fight this turn |
| T4 | Knowledge logs after economy+combat (NEW) | battle at turn 5 | ledger entry t=5 visible only via delay, not instantly |
| T5 | Fresh spawns immune this turn (NEW) | TRAIN spawns army adjacent to enemy | spawned army not in combat check this turn, and doesn't block movement |
| T6 | Eviction last (NEW) | ledger window slides | events no longer deliverable are evicted after knowledge phase |
| T7 | Full sequence determinism (NEW) | run 10 turns with scripted orders | replay via record matches step-by-step |

## 14. Game record format (JSONL)

| # | Test | Input | Expected |
|---|---|---|---|
| R1 | First line is config | read line 1 | JSON with `type:"config"`, contains map, info_speed, army_speed, interact_radius, population_cap, etc. |
| R2 | Subsequent lines are turns | line 2+ | `type:"turn"`, fields `turn` (int), `world:{armies:[],towns:[]}`, `events:[]` |
| R3 | All turns present | max_turns=10, game ends at 10 | exactly 10 turn lines (plus config) |
| R4 | Events changes only | turn with no battles | events=[] but world still full |
| R5 | World complete | any turn | armies have id,faction,x,y; towns have id,faction,x,y,population,is_capital |
| R5b | Event fields correct (NEW) | trigger each kind | `army_spawn:{id,faction,x,is_viceroy}`, `town_spawn:{id,faction,x,y,population,is_capital}`, `army_move:{id,x,y}`, `army_death:{id,x,y}`, `battle:{x,y,combatants:[{id,faction}],killed:[id]}` |
| R5c | JSONL line-delimited (NEW) | cat file | one JSON object per line, no outer array, no trailing comma |
| R5d | Deterministic output (NEW) | run twice | byte-identical JSONL |
| R5e | Turn numbers sequential (NEW) | scan file | 1..T with no gaps |
| R5f | Config echoes all defaults (NEW) | check keys | every PLAN default present as key |

## 15. Bot protocol

| # | Test | Input | Expected |
|---|---|---|---|
| B1 | Startup — config | first line to bot stdin | `config <json>` with full config |
| B2 | Startup — faction | second line | `faction <id>` (int) |
| B3 | Startup — go | third line | `go` |
| B4 | Per turn — header | each turn | `turn <n>` line followed by events (incremental, ledger-filtered for that faction), then `go` |
| B5 | Bot response parsed | bot prints `MOVE_TO 1 0 0 100 100` + `go` | runner delivers to propagation |
| B5b | All command types parsed (NEW) | bot prints one of each: MOVE_TO/TRAIN/BUILD/MOVE_CAPITAL | each routed correctly |
| B6 | Timeout kills | bot sleeps > turn_time_ms | process killed, no orders this turn, **and all future turns** (dead) |
| B6b | Timeout mid-game permanence (NEW) | bot times out turn 5, game continues to 10 | turns 6..10 receive no orders from that faction |
| B7 | Go terminator required (NEW) | bot prints orders without `go` then timeout | orders ignored for that turn |
| B8 | Incremental updates only (NEW) | turn 10 | bot receives only events since last turn (ledger-visible), not full world — bot must track state |
| B9 | End message | game over | `end <scores_json>` on bot stdin, scores = {faction: score} |
| B9b | End after timeout still sent? (NEW) | timed-out bot | still receives `end` before SIGKILL? or not — pin choice |
| B10 | Malformed bot line ignored (NEW) | bot prints `MOVE_TO garbage` | no crash, line skipped |
| B11 | Unknown faction id in bot output (NEW) | bot orders enemy army | ignored (ownership check) |

## 16. Score

| # | Test | Input | Expected |
|---|---|---|---|
| S1 | Formula | 3 towns 1000+2000+500=3500, 2 armies ×1000=2000 | 5500 |
| S2 | Only alive counted | kill 1 town (pop 1000) | score drops by 1000 |
| S3 | At start | 1 town 500 + 1 army 1000 | 1500 |
| S3b | Empty faction (NEW) | faction with 0 towns 0 armies | 0 |
| S3c | BUILD vs score (NEW) | army (1000) → town (500): before 1000 army score, after 500 town score → net −500 | BUILD has score cost |
| S3d | TRAIN vs score (NEW) | town 2000 → 1000 + new army 1000 | before 2000, after 2000 (wash) — TRAIN score-neutral |

## 17. Spatial optimisation / correctness

| # | Test | Input | Expected |
|---|---|---|---|
| H1 | Same cell if within radius | 2 entities 5 km apart, cell size ≥10 | same or adjacent cell (never missed) |
| H2 | Query returns all in radius (vs brute) | 100 random entities | hash neighbour query result == brute `dist ≤ interact_radius` set |
| H3 | Rebuild clears old cells | entities move 100 km | old cell empty, new cell occupied |
| H4 | Cell size ≥ interact_radius invariant | config interact_radius=10 | grid cell_size = max(cell_size, 10) — assertion |
| H4b | Crowding sum via hash vs brute (NEW) | 20 towns random positions | hash-accelerated Σ (filter within info_speed) equals brute Σ to 1e-9 |
| H4c | Performance not O(n²) (NEW) | 500 towns | crowding step < 100 ms (sanity, not strict) |

## 18. Ledger

| # | Test | Input | Expected |
|---|---|---|---|
| G1 | Logged with correct tuple | any event | stored as (t,x,y,kind,payload) |
| G2 | Visible within delay | event dist 10, speed 150, now=t+1 | included in faction's `turn` events |
| G3 | Not yet visible if far | event dist 300, now=t+1 | excluded |
| G4 | Evicted when undeliverable to anyone | event older than max_dist/info_speed + grace | removed from deque |
| G5 | Window = max_delay × info_speed (NEW) | max_dist = diagonal ≈1414, info_speed 150 → window ≈10 | stored window ≥10, no premature eviction |
| G5b | Sorted by time (NEW) | log 3 events out-of-order delivery attempts | ledger iterates in t order |
| G5c | Eviction O(1) pointer (NEW) | advance 100 turns | eviction loop advances pointer, not full scan |

## 19. Determinism

| # | Test | Input | Expected |
|---|---|---|---|
| D1 | Identical runs byte-identical | same map+config, 50 turns, no bots | JSONL identical |
| D2 | Deterministic with bots | same bots (deterministic greedy) | identical |
| D3 | Float stable | crowding with γ=0.3, repeated 100× | bit-identical pop values |
| D3b | No hidden randomness (NEW) | grep engine for `random`, `np.random`, `os.urandom` | none in engine/ |
| D3c | Turn order stable (NEW) | same contacts at same t* | earliest-first tie-break by id (deterministic) |

## 20. Viewer

| # | Test | Input | Expected |
|---|---|---|---|
| V1 | Loads JSONL | select `game.jsonl` via picker or `?game=` URL | map renders, no crash |
| V2 | Town radius ∝ √pop | pop 500 vs 50000 | radius = 4+6×√(pop/100000) → 4.42 vs 8.24 px |
| V3 | Capital marker | town is_capital=true | circle + white centre dot |
| V4 | Army triangle | army entity | fixed-size triangle, faction colour (golden-angle) |
| V5 | Stacked armies | 3 armies same pos | stacked offset, count badge “×3” |
| V6 | Battle crossed lines | battle event at (100,100) | X marker at battle pos |
| V7 | Pan/zoom | drag, wheel, pinch, double-click fit | transform updates, entities stay in world coords |
| V8 | Turn slider + play/pause + speed | 0.5×–8× selector, space toggles | visualTurn lerps with ease-in-out between turns |
| V9 | Sidebar counts | turn with 2 towns 3 armies for F_A | shows “F_A: 2T 3A score=…” |
| V10 | Timeline markers | battle/spawn/death events | dots on strip at correct fractional position, click seeks |
| V11 | Tooltip | hover town/army/battle | shows pop/distances, faction, participants |
| V12 | Animation lerp | between turn N and N+1, army moves 50 km | at 50% progress army at 25 km |
| V12b | Move→death lerp (NEW) | army at (0,0) turn N, moves to (50,0) then dies (army_death/battle at (50,0)) turn N+1 | lerps 0→1 from (0,0) to (50,0), then shrink-fade at (50,0); not vanish at (0,0) nor pop at (50,0) without transit |
| V12c | Stationary→death lerp (NEW) | army at (30,30) both turns, dies turn N+1 | no transit, shrink-fade at (30,30) |
| V12d | Blocked move→death lerp (NEW) | army path blocked at (20,0) then dies there (death pos = blocked pos) | lerps to (20,0) (blocked point) not to intended target (100,0) |
| V13 | Spawn grow-in / death shrink-out | army_spawn / army_death | fade/scale animation, not pop |
| V13b | Move→death vs missing endpoint (NEW) | lerp code uses `world` arrays only (dead army absent N+1) | must fall back to `army_death` event position for endpoint; test fails if lerps to (0,0) or NaN |
| V13c | Two armies same pos, one dies (NEW) | stack at (50,0) turn N: 2 armies; turn N+1: 1 survives at (50,0), 1 dies at (50,0) | survivor stays, dead one fades at same pos; stack count animates 2→1 |
| V13d | Viceroy grow-in then straight move (NEW) | `MOVE_CAPITAL` 200 200 from capital (100,100); turn N: viceroy `army_spawn is_viceroy` at (100,100); turn N+1: viceroy at (135,135) (50 km toward target) | turn N→N+1 lerp grows in at (100,100) at t=0 then slides to (135,135) at t=1; not teleport, not missing first step |
| V13e | Viceroy arrival → town (NEW) | viceroy at (180,180) turn N, target (200,200); turn N+1: viceroy absent, `town_spawn is_capital` at (200,200) + `army_death` at (200,200) | viceroy lerps (180,180)→(200,200) then shrink-fades at (200,200) as town grows in at same pos; no gap or overlap |
| V13f | Viceroy vs normal spawn move (NEW) | TRAIN spawn at (100,100) stationary 1 turn vs viceroy that moves same turn | TRAIN lerp stays at (100,100) with grow-in; viceroy lerp shows transit — both start with grow-in, only viceroy translates |
| V14 | Large JSONL streaming | 500-turn game, 50k events | loads without OOM, turns seekable |
| V15 | File picker fallback | no `?game=` | shows picker prompt, not blank |

## 21. Cross-cutting / integration

| # | Test | Input | Expected |
|---|---|---|---|
| Z1 | Full game no bots, growth only | 2 towns far apart (300 km), 50 turns | both grow per logistic, no deaths, no combat |
| Z2 | Full game with blocking + combat | 2 factions armies march at each other | movement stops, combat kills correctly, score updates |
| Z3 | Crowding can kill town over many turns | 5 towns clustered at 5 km, 100 turns | at least one dies (net negative sustained) |
| Z4 | Viewer replays record exactly | run game → load in viewer | entity counts per turn match world arrays |
| Z5 | Bot sees delayed world, acts on stale data | bot greedy based on its ledger view | orders arrive late, may target dead entities (dead letters) |

## 22. Medium-level component tests

> Each test creates a world, runs `step()` or a system function end-to-end, and checks the result. Faster than integration tests (Z), but exercise full systems not individual formulas. All tests below use default `GameConfig` unless noted.

### Entities (N)

| # | Test | Input | Expected |
|---|---|---|---|
| N6 | 10 armies spawned have unique ids | spawn 10 armies via world.allocate_id | all 10 ids distinct |
| N7 | Town survives 10 step() calls | town pop 2000, no neighbours, run step() 10 times | town still present, same id, pop > 2000 |
| N8 | Army removed after BUILD | army at (100,100), apply_build | army no longer in world.armies |
| N9 | Town removed when pop hits 0 | town pop 500, set pop=0 directly, run economy | town removed from world.towns |

### Economy — full step interaction (E)

| # | Test | Input | Expected |
|---|---|---|
| E35 | Isolated town grows over 10 steps | town pop 500 at (500,500), no other entities, run step() 10 times | pop > 500 (growing) |
| E36 | Two close towns crowd each other | A at (0,0) pop 1000, B at (5,0) pop 1000, run step() 10 times | both pops lower than if isolated (crowding reduces growth) |
| E37 | Town dies mid-game | town pop 600, set pop=499, run economy step | town absent from world.towns |
| E38 | BUILD then growth | army builds new town (pop 500), run 10 more steps | new town grows, pop > 500 |
| E39 | TRAIN then recovery | town pop 3000, TRAIN (pop→2000), run 10 steps | pop recovers above 2000 (growth > train cost per turn) |
| E40 | Standing TRAIN repeats | town pop 5000, standing TRAIN order, run 3 economy steps | 3 armies spawned, town pop reduced by 3000 |
| E41 | BUILD on existing town extends life | town pop 600 (near death), army builds on it (pop→1100), run 10 steps | town survives, pop > 1100 |
| E42 | Crowding + growth equilibrium | 3 towns at 8 km apart all pop 500, run 100 steps | pops converge toward similar values (crowding balances) |

### Movement — full step interaction (M)

| # | Test | Input | Expected |
|---|---|---|
| M18 | Army marches 200 km over 4 turns | army at (0,0) target (200,0), speed 50, run step() 4 times | army at (200,0) after 4 steps |
| M19 | Army blocked then resumes | army A at (0,0)→(200,0), enemy B at (100,5), B removed after turn 1 (dies), A continues turn 2 | A stops at ~(100,0) turn 1, then moves toward (200,0) turn 2 |
| M20 | Movement before combat in step | army A at (0,0)→(50,0), enemy B at (60,0), run step() once | A moves to (50,0), combat checks (50,0) vs (60,0), both within radius → both die |
| M21 | Army clamps at map edge | army at (50,50) target (−100,−100), run step() | army at (0,0) (clamped) |
| M22 | Fresh spawn doesn't block movement | army A at (0,0)→(200,0), new army B spawned at (100,5) this turn, run step() | A reaches (200,0) (B is immune) |
| M23 | Two armies head-on both stop | A at (0,0)→(100,0), B at (100,0)→(0,0), run step() | both at ~(50,0) |
| M24 | Army moves then fights same turn | A at (0,0)→(10,0), B at (15,0) stationary, run step() | A moves to (10,0), combat at (10,0) vs (15,0), both die |

### Combat — full step interaction (C)

| # | Test | Input | Expected |
|---|---|---|
| C10 | 2v1 over 2 turns | A1 at (0,0), A2 at (5,0) faction 0; B at (100,0) faction 1 target (0,0); run step() 2 times | B marches toward A, stops at ~(50,0), then combat: B dies, A1 and A2 survive |
| C11 | Dead armies removed from world | 1v1 within radius, run step() | world.armies has 0 entries |
| C12 | Multiple simultaneous battles | A1 at (0,0) vs B1 at (5,0); A2 at (500,0) vs B2 at (505,0); run step() | both pairs resolve independently, all 4 die |
| C13 | Fresh spawns don't fight | TRAIN spawns army adjacent to enemy, run step() same turn | spawned army not in combat check |
| C14 | Score reflects combat deaths | 2 armies (score 2000), combat kills both, run step() | score 0 |

### Turn resolution — full step() ordering (T)

| # | Test | Input | Expected |
|---|---|---|
| T8 | step() returns events from all phases | world with army, town, standing orders, run step() | events list contains movement + combat + economy events (not empty) |
| T9 | Dead armies removed before economy | army at (0,0) vs enemy at (5,0), town at (200,200) pop 2000; run step() | economy runs on world without dead army |
| T10 | Economy after combat | army on top of town (army dies), town pop grows same turn | town survives, army gone |
| T11 | Knowledge after economy | town spawns army via TRAIN, run step() | army_spawn event in ledger after economy phase |
| T12 | Fresh spawns immune to combat | TRAIN spawns army next to enemy, run step() | spawned army survives its first turn |
| T13 | Multiple systems in one step | army builds town + another army marches + combat elsewhere | all three effects visible in world after step |
| T14 | step() with no orders | world with armies and towns, no commands, run step() | armies don't move (no target), economy runs, no errors |

### Ledger — full step interaction (G)

| # | Test | Input | Expected |
|---|---|---|
| G6 | Ledger accumulates over 10 steps | world with 2 towns, run step() 10 times | ledger.events has entries from multiple turns |
| G7 | Events visible after correct delay | event at (0,0), faction capital at (50,0), info_speed 150 | event visible at turn t+1 (dist 50, 50/150 = 0.33 turns) |
| G8 | Old events evicted after window | run 20 steps, check ledger size | ledger doesn't grow unboundedly |
| G9 | Events sorted by time | log events from turns 1,3,2 (out of order), iterate | ledger.events sorted by turn number |

### Score — full game interaction (S)

| # | Test | Input | Expected |
|---|---|---|
| S4 | Score grows as towns grow | 1 town pop 500, no armies, run 50 steps | score at turn 50 > score at turn 0 |
| S5 | BUILD costs score | army (1000 score) builds town (500 score) | score drops by 500 |
| S6 | TRAIN is score-neutral | town pop 2000 (2000 score), TRAIN → pop 1000 + army 1000 | score unchanged |
| S7 | Multi-faction score tracked separately | 2 factions with different towns | each faction's score = own towns pop + own armies × cost |

### Commands — full step interaction (O)

| # | Test | Input | Expected |
|---|---|---|
| O14 | MOVE_TO then step() moves army | army at (0,0), MOVE_TO target (100,0), run step() | army at (50,0) after 1 step |
| O15 | BUILD then step() creates town | army at (100,100), BUILD, run step() | new town at (100,100), army gone |
| O16 | TRAIN then step() spawns army | town pop 2000, TRAIN, run step() | new army at town pos, town pop 1000 |
| O17 | Multiple commands in one step | MOVE_TO + TRAIN + BUILD, run step() | all three effects applied |
| O18 | Invalid commands ignored | army at (0,0), BUILD at (100,100) (too far), run step() | no town created, army survives |
| O19 | Standing orders persist | MOVE_TO once, run step() 5 times | army continues moving each step |

### Info delay — full step interaction (I)

| # | Test | Input | Expected |
|---|---|---|
| I6 | Event visible after 1 turn if close | event at (0,0), capital at (10,0), info_speed 150, run step() | event visible in next step's turn message |
| I7 | Event delayed 2 turns if far | event at (0,0), capital at (300,0), info_speed 150, run step() | event not visible until turn+2 |
| I8 | Capital blind during MOVE_CAPITAL | MOVE_CAPITAL in flight, events logged | events not delivered until arrival |
| I9 | Ledger window holds events | run 15 turns, max map diagonal ~1414, info_speed 150 | events from turn 1 still in ledger at turn 10 |

### Order lag — full step interaction (L)

| # | Test | Input | Expected |
|---|---|---|
| L6 | Messenger delivers next turn if close | order from (0,0) to army at (10,0), info_speed 150 | delivered in 1 turn |
| L7 | Messenger takes 2 turns if far | order from (0,0) to army at (200,0), info_speed 150 | delivered in 2 turns |
| L8 | Dead letter on army death | order to army, army dies in combat before delivery | order discarded, no crash |
| L9 | Standing order persists across steps | MOVE_TO once, run 3 steps | army continues moving all 3 steps |
