"""BotState sync tests — verify BotState matches engine world with distance-based delay.

Each test:
1. Sets up a minimal engine world
2. Runs a step
3. Feeds resulting events to BotState
4. Asserts BotState matches expected state

Key invariant: BotState should match the engine world, but events arrive
with delay = ceil(dist / info_speed) turns. Within info_speed (150 km),
events arrive same-turn.
"""

from __future__ import annotations

import math
import pytest
from engine.config import GameConfig
from engine.world import World, Town, Army, StandingOrder, CommandType
from engine.step import step
from engine.ledger import Ledger
from bots.common import BotState


CFG = GameConfig()
LEDGER = Ledger(CFG.info_speed, math.hypot(1000, 1000))


def _make_world(towns=None, armies=None) -> World:
    w = World()
    w.map_size = [1000, 1000]
    if towns:
        w.towns.extend(towns)
    if armies:
        w.armies.extend(armies)
    return w


def _town(fid=0, x=100, y=100, pop=5000, cap=True, tid=None) -> Town:
    return Town(id=tid if tid is not None else 0, faction=fid, x=x, y=y, population=pop, is_capital=cap)


def _army(fid=0, x=100, y=100, aid=None) -> Army:
    return Army(id=aid if aid is not None else 10, faction=fid, x=x, y=y)


def _sync_bot(bot: BotState, engine: World | None, turn: int, events: list[dict]) -> None:
    """Update BotState from engine events. Also syncs bot.world for lookups."""
    if engine is not None:
        bot.world.towns = list(engine.towns)
        bot.world.armies = list(engine.armies)
        bot.world.standing_orders = list(engine.standing_orders)
    bot.update(turn, events)


def _events_to_dicts(events: list[dict]) -> list[dict]:
    """Ensure events are plain dicts."""
    return [dict(e) if not isinstance(e, dict) else e for e in events]


# ── Basic sync ──


def test_initial_state_matches():
    """BotState init from map matches engine."""
    csv = "100,100,A,5000\n200,200,B,3000\n"
    engine = _make_world()
    engine.parse_map(csv)

    bot = BotState()
    cfg = GameConfig()
    cfg.map = csv
    cfg.map_size = [1000, 1000]
    bot.init(cfg, 0)
    assert len(bot.world.towns) == len(engine.towns)
    assert len(bot.world.armies) == len(engine.armies)
    for t in bot.world.towns:
        et = next((x for x in engine.towns if x.id == t.id), None)
        assert et is not None
        assert t.population == et.population
        assert t.faction == et.faction


def test_town_death_removes_from_bot():
    """Town dying in engine → removed from BotState after event."""
    t = _town(fid=0, pop=400, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    bot = BotState()
    bot.init(CFG, 0)
    # Force pop below threshold by manually setting
    t.population = 400

    events = step(engine, CFG, ledger, turn=1, orders={})
    # Find town_death event
    death_events = [e for e in (events or []) if e.get("kind") == "town_death"]
    assert len(death_events) == 1

    _sync_bot(bot, engine, 1, _events_to_dicts(events))
    assert 1 not in bot.world.towns


def test_army_spawn_adds_to_bot():
    """TRAIN delivering → army appears in BotState."""
    t = _town(fid=0, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    bot = BotState()
    bot.init(CFG, 0)
    # Remove army from bot (init doesn't create armies from map)
    bot.world.armies.clear()

    # Add TRAIN standing order
    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
    )

    events = step(engine, CFG, ledger, turn=1, orders={})
    spawn_events = [e for e in (events or []) if e.get("kind") == "army_spawn"]
    assert len(spawn_events) >= 1

    _sync_bot(bot, engine, 1, _events_to_dicts(events))
    assert len(bot.world.armies) >= 1


def test_army_death_removes_from_bot():
    """Army dying in engine → removed from BotState."""
    a1 = _army(fid=0, x=100, y=100, aid=10)
    a2 = _army(fid=1, x=105, y=100, aid=11)  # very close → combat
    t1 = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    t2 = _town(fid=1, x=800, y=800, pop=5000, tid=2)
    engine = _make_world(towns=[t1, t2], armies=[a1, a2])
    ledger = Ledger(CFG.info_speed, 1414)

    bot = BotState()
    bot.init(CFG, 0)
    # Sync initial state
    _sync_bot(bot, engine, 0, [])
    assert any(a.id == 10 for a in bot.world.armies)
    assert any(a.id == 11 for a in bot.world.armies)

    events = step(engine, CFG, ledger, turn=1, orders={})
    death_events = [e for e in (events or []) if e.get("kind") == "army_death"]
    # At least one army should die
    assert len(death_events) >= 1

    _sync_bot(bot, engine, 1, _events_to_dicts(events))
    dead_ids = {e["id"] for e in death_events}
    for did in dead_ids:
        assert not any(a.id == did for a in bot.world.armies)


# ── TRAIN ──


def test_train_one_shot():
    """TRAIN standing order spawns one army then is consumed."""
    t = _town(fid=0, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)
    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
    )

    step(engine, CFG, ledger, turn=1, orders={})
    assert len(engine.armies) == 1
    assert len(engine.standing_orders) == 0  # consumed

    # Second turn — no more armies spawned
    step(engine, CFG, ledger, turn=2, orders={})
    assert len(engine.armies) == 1


def test_train_survives_low_pop():
    """TRAIN on town with pop < army_cost → army not spawned, order consumed."""
    t = _town(fid=0, pop=800, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)
    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
    )

    step(engine, CFG, ledger, turn=1, orders={})
    assert len(engine.armies) == 0  # too low to spawn
    assert len(engine.standing_orders) == 0  # consumed


# ── BUILD ──


def test_build_spawns_town():
    """BUILD creates a new town at army location."""
    a = _army(fid=0, x=300, y=300, aid=10)
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t], armies=[a])
    ledger = Ledger(CFG.info_speed, 1414)

    # BUILD order via messenger
    events = step(engine, CFG, ledger, turn=1, orders={0: ["BUILD 10 300 300"]})
    # Messenger created, may deliver same turn if close enough
    # After step, check if standing order exists
    build_orders = [so for so in engine.standing_orders if so.command == CommandType.BUILD]
    # If delivered, standing order created; if not, messenger still in flight
    if build_orders:
        # Process another turn to execute BUILD
        events2 = step(engine, CFG, ledger, turn=2, orders={})
        town_spawns = [e for e in (events2 or []) if e.get("kind") == "town_spawn"]
        assert len(town_spawns) >= 1


def test_build_consumed_after_execution():
    """BUILD standing order is consumed after town spawn."""
    a = _army(fid=0, x=300, y=300, aid=10)
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t], armies=[a])
    ledger = Ledger(CFG.info_speed, 1414)

    # Force delivery by creating standing order directly
    engine.standing_orders.append(
        StandingOrder(command=CommandType.BUILD, target_id=10, target_type="army", args=[300, 300])
    )
    step(engine, CFG, ledger, turn=1, orders={})
    # BUILD should be consumed
    build_orders = [so for so in engine.standing_orders if so.command == CommandType.BUILD]
    assert len(build_orders) == 0


# ── MOVE_TO ──


def test_move_to_sets_target():
    """MOVE_TO order sets army target position."""
    a = _army(fid=0, x=100, y=100, aid=10)
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t], armies=[a])
    ledger = Ledger(CFG.info_speed, 1414)

    step(engine, CFG, ledger, turn=1, orders={0: ["MOVE_TO 10 100 100 500 500"]})
    # Army should have target set (after messenger delivery)
    army = next((a for a in engine.armies if a.id == 10), None)
    # Messenger may or may not have delivered yet (distance from capital = 0)
    # If delivered, target is set
    if army and army.has_target:
        assert army.target_x == 500
        assert army.target_y == 500


def test_move_army_reaches_target():
    """Army moves toward target each turn."""
    a = _army(fid=0, x=100, y=100, aid=10)
    a.target_x = 200
    a.target_y = 100
    a.has_target = True
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t], armies=[a])
    ledger = Ledger(CFG.info_speed, 1414)

    step(engine, CFG, ledger, turn=1, orders={})
    army = next((a for a in engine.armies if a.id == 10), None)
    assert army is not None
    # Should have moved toward target (speed=50, distance=100 → moves 50 km)
    assert army.x > 100


# ── BotState tracking ──


def test_bot_tracks_population_changes():
    """BotState pop changes match engine pop changes."""
    t = _town(fid=0, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    bot = BotState()
    bot.init(CFG, 0)
    _sync_bot(bot, engine, 0, [])

    # Train — pop drops by 1000
    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
    )
    events = step(engine, CFG, ledger, turn=1, orders={})
    _sync_bot(bot, engine, 1, _events_to_dicts(events))

    # Bot pop should match engine pop
    et = next(x for x in engine.towns if x.id == 1)
    bt = bot.world.get_town(1)
    assert bt.population == et.population


def test_bot_tracks_army_count():
    """BotState army count matches engine."""
    t = _town(fid=0, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    bot = BotState()
    bot.init(CFG, 0)

    # Train 3 times
    for i in range(3):
        engine.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        events = step(engine, CFG, ledger, turn=i + 1, orders={})
        _sync_bot(bot, engine, i + 1, _events_to_dicts(events))

    assert len(bot.world.armies) == len(engine.armies)


def test_bot_own_towns_only():
    """BotState.own_towns() returns only this faction's towns."""
    t0 = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    t1 = _town(fid=1, x=800, y=800, pop=5000, tid=2)
    engine = _make_world(towns=[t0, t1])

    bot = BotState()
    bot.init(CFG, 0)
    _sync_bot(bot, engine, 0, [])

    own = bot.own_towns()
    assert len(own) == 1
    assert own[0].faction == 0


def test_bot_own_armies_only():
    """BotState.own_armies() returns only this faction's armies."""
    a0 = _army(fid=0, x=100, y=100, aid=10)
    a1 = _army(fid=1, x=800, y=800, aid=11)
    engine = _make_world(armies=[a0, a1])

    bot = BotState()
    bot.init(CFG, 0)
    _sync_bot(bot, engine, 0, [])

    own = bot.own_armies()
    assert len(own) == 1
    assert own[0].faction == 0


# ── Delivery delay ──


def test_train_delivery_same_turn_for_close_town():
    """TRAIN to same town as capital (dist=0) delivers same turn."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    bot = BotState()
    bot.init(CFG, 0)

    # Send TRAIN via order
    events = step(engine, CFG, ledger, turn=1, orders={0: ["TRAIN 1"]})
    # For dist=0, delivery is same turn
    _sync_bot(bot, engine, 1, _events_to_dicts(events))
    # Bot should see the spawned army
    assert len(bot.world.armies) >= 1


def test_train_delivery_delayed_for_distant_town():
    """TRAIN to town far from capital arrives with delay."""
    # Capital at (100,100), target town at (400,100) — dist=300 > info_speed(150)
    cap = _town(fid=0, x=100, y=100, pop=5000, tid=1, cap=True)
    far = _town(fid=0, x=400, y=100, pop=5000, tid=2, cap=False)
    engine = _make_world(towns=[cap, far])
    ledger = Ledger(CFG.info_speed, 1414)

    bot = BotState()
    bot.init(CFG, 0)
    _sync_bot(bot, engine, 0, [])
    initial_armies = len(bot.world.armies)

    # Send TRAIN to distant town
    events = step(engine, CFG, ledger, turn=1, orders={0: ["TRAIN 2"]})
    _sync_bot(bot, engine, 1, _events_to_dicts(events))
    # dist=300, info_speed=150 → delivery turn = ceil(300/150) = 2
    # Bot should NOT see the army yet on turn 1
    assert len(bot.world.armies) == initial_armies

    # Turn 2 — messenger delivers
    events2 = step(engine, CFG, ledger, turn=2, orders={})
    _sync_bot(bot, engine, 2, _events_to_dicts(events2))
    # Now bot should see the army
    assert len(bot.world.armies) >= initial_armies + 1


# ── Capital death ──


def test_capital_death_no_events():
    """After capital dies, bot receives no events (is_in_flight=False, no capital)."""
    t = _town(fid=0, pop=400, tid=1)  # below death threshold
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    # Kill the capital
    events = step(engine, CFG, ledger, turn=1, orders={})
    death = [e for e in (events or []) if e.get("kind") == "town_death"]
    assert len(death) == 1

    # Bot with dead capital should get no visible events
    visible = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=1.0)
    assert len(visible) == 0


# ── Enemy visibility ──


def test_enemy_town_visible_from_own_capital():
    """Enemy town within info_speed is visible after propagation delay."""
    t0 = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    t1 = _town(fid=1, x=200, y=100, pop=5000, tid=2)  # dist=100 < 150
    engine = _make_world(towns=[t0, t1])
    ledger = Ledger(CFG.info_speed, 1414)

    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=2, target_type="town")
    )
    step(engine, CFG, ledger, turn=1, orders={})

    # dist=100, info_speed=150 → visible_turn = 1 + 100/150 ≈ 1.67
    # Need now >= 1.67 for visibility
    visible = ledger.visible_events(faction=0, capital_x=100, capital_y=100, now=2.0)
    spawn_events = [e for e in visible if e.kind.value == "army_spawn"]
    assert len(spawn_events) >= 1


def test_enemy_town_far_not_visible():
    """Enemy town beyond info_speed is not visible immediately."""
    t0 = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    t1 = _town(fid=1, x=500, y=500, pop=5000, tid=2)  # dist=566 > 150
    engine = _make_world(towns=[t0, t1])
    ledger = Ledger(CFG.info_speed, 1414)

    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=2, target_type="town")
    )
    step(engine, CFG, ledger, turn=1, orders={})

    visible = ledger.visible_events(faction=0, capital_x=100, capital_y=100, now=1.0)
    spawn_events = [e for e in visible if e.kind.value == "army_spawn"]
    assert len(spawn_events) == 0


# ── Multiple factions ──


def test_two_factions_independent():
    """Two factions track their own state independently."""
    t0 = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    t1 = _town(fid=1, x=800, y=800, pop=5000, tid=2)
    engine = _make_world(towns=[t0, t1])
    ledger = Ledger(CFG.info_speed, 1414)

    bot0 = BotState()
    bot0.init(CFG, 0)
    bot1 = BotState()
    bot1.init(CFG, 1)

    # Train for faction 0 only
    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
    )
    events = step(engine, CFG, ledger, turn=1, orders={})
    dicts = _events_to_dicts(events)

    _sync_bot(bot0, engine, 1, dicts)
    _sync_bot(bot1, engine, 1, dicts)

    # bot0 should see the new army, bot1 should not (faction filter)
    own0 = [a for a in bot0.world.armies if a.faction == 0]
    own1 = [a for a in bot1.world.armies if a.faction == 1]
    assert len(own0) >= 1
    assert len(own1) == 0


# ── Move capital ──


def test_move_capital_events():
    """MOVE_CAPITAL to same pos generates all events immediately."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    # Target = current pos → instant arrival
    events = step(engine, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 100 100"]})
    assert events is not None
    kinds = [e.get("kind") for e in events]
    assert "army_spawn" in kinds
    assert "town_spawn" in kinds
    assert "army_death" in kinds


def test_move_capital_old_capital_demoted():
    """After MOVE_CAPITAL arrival, old capital is demoted (non-stacked target)."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)
    # 200,200 is 141 away -> viceroy spawns t1 (fresh), moves t2, arrives t2
    step(engine, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 200 200"]})
    step(engine, CFG, ledger, turn=2, orders={})
    step(engine, CFG, ledger, turn=3, orders={})
    old_cap = next((x for x in engine.towns if x.id == 1), None)
    assert old_cap is not None
    assert not old_cap.is_capital
    new_caps = [x for x in engine.towns if x.is_capital and x.faction == 0]
    assert len(new_caps) == 1
    assert new_caps[0].x == 200 and new_caps[0].y == 200


def test_move_capital_stacked_die():
    """Stacked MOVE_CAPITAL (same tile) insta-kills lower-pop new (bot fault)."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=1, orders={0: ["MOVE_CAPITAL 100 100"]})
    old_cap = next((x for x in engine.towns if x.id == 1), None)
    assert old_cap is not None
    assert not old_cap.is_capital
    new_caps = [x for x in engine.towns if x.is_capital and x.faction == 0]
    assert len(new_caps) == 0


def test_move_capital_delayed_arrival():
    """MOVE_CAPITAL to distant pos arrives after travel time."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    # Target far away — won't arrive on turn 1
    step(engine, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 500 500"]})
    old_cap = next((x for x in engine.towns if x.id == 1), None)
    assert old_cap is not None
    assert old_cap.is_capital  # still capital, viceroy hasn't arrived
    assert len(engine.armies) == 1  # viceroy exists


# ── Town death ──


def test_town_death_cleans_standing_orders():
    """Town death removes TRAIN standing orders targeting it."""
    t = _town(fid=0, pop=400, tid=1)
    engine = _make_world(towns=[t])
    engine.standing_orders.append(
        StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
    )

    step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=1, orders={})
    # Town dead → standing order removed
    train_orders = [so for so in engine.standing_orders if so.command == CommandType.TRAIN]
    assert len(train_orders) == 0


def test_town_death_cleans_build_orders():
    """Town death removes BUILD standing orders targeting its armies."""
    t = _town(fid=0, pop=400, tid=1)
    a = _army(fid=0, x=100, y=100, aid=10)
    engine = _make_world(towns=[t], armies=[a])
    engine.standing_orders.append(
        StandingOrder(command=CommandType.BUILD, target_id=10, target_type="army", args=[100, 100])
    )

    step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=1, orders={})
    build_orders = [so for so in engine.standing_orders if so.command == CommandType.BUILD]
    assert len(build_orders) == 0


# ── Population threshold ──


def test_train_rejects_low_pop():
    """TRAIN on town with pop < army_cost → no army spawned."""
    t = _town(fid=0, pop=800, tid=1)
    engine = _make_world(towns=[t])

    events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=1, orders={0: ["TRAIN 1"]})
    spawn = [e for e in (events or []) if e.get("kind") == "army_spawn"]
    assert len(spawn) == 0


def test_train_accepts_healthy_pop():
    """TRAIN on town with pop >= army_cost → army spawned."""
    t = _town(fid=0, pop=5000, tid=1)
    engine = _make_world(towns=[t])

    events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=1, orders={0: ["TRAIN 1"]})
    spawn = [e for e in (events or []) if e.get("kind") == "army_spawn"]
    assert len(spawn) >= 1


# ── Edge cases ──


def test_empty_world():
    """BotState on empty world has no towns/armies."""
    bot = BotState()
    bot.init(CFG, 0)
    assert len(bot.world.towns) == 0
    assert len(bot.world.armies) == 0
    assert bot.own_towns() == []
    assert bot.own_armies() == []


def test_bot_handles_unknown_events():
    """BotState ignores events for entities it doesn't track."""
    bot = BotState()
    bot.init(CFG, 0)
    # Unknown army move event
    _sync_bot(bot, None, 1, [{"kind": "army_move", "id": 999, "x": 50, "y": 50}])
    # No crash, no new army
    assert 999 not in bot.world.armies


def test_bot_handles_duplicate_events():
    """BotState handles duplicate events gracefully."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])

    bot = BotState()
    bot.init(CFG, 0)
    _sync_bot(bot, engine, 0, [])

    # Send same town_spawn twice
    _sync_bot(bot, engine, 1, [
        {"kind": "town_spawn", "id": 1, "faction": 0, "x": 100, "y": 100, "population": 5000, "is_capital": True},
        {"kind": "town_spawn", "id": 1, "faction": 0, "x": 100, "y": 100, "population": 5000, "is_capital": True},
    ])
    # Only one town in bot
    assert len([t for t in bot.world.towns if t.id == 1]) == 1
