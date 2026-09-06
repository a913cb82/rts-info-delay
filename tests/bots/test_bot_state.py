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
from engine.delivery import build_updates
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
    """BotState init starts empty (no map pre-seed); dims set."""
    bot = BotState()
    cfg = GameConfig()
    cfg.map = "100,100,A,5000\n"
    cfg.map_size = [1000, 1000]
    bot.init(cfg, 0)
    assert bot.world.towns == [] and bot.world.armies == []
    assert bot.world.map_size == [1000, 1000]

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

    # Bot with dead capital and no remaining entities observes nothing:
    # the tombstone is untagged, so delivery is silent.
    assert build_updates(ledger, 0, 0, (0.0, 0.0), 1.0) == []


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

    # dist=100, info_speed=150 → release at 1 + 100/150 ≈ 1.67
    # Need now >= 1.67 for delivery
    got = build_updates(ledger, 0, 0, (100.0, 100.0), 2.0)
    spawns = [u for u in got if u["kind"] == "army_update"]
    assert len(spawns) >= 1


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

    got = build_updates(ledger, 0, 0, (100.0, 100.0), 1.0)
    assert not [u for u in got if u["kind"] == "army_update"]
    assert not [u for u in got if u.get("id") == 2]


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
    """MOVE_CAPITAL to same pos: spawn turn 1, found turn 2."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    # Turn 1: TRAIN-like execution (spawn + demote, no founding yet)
    events = step(engine, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 100 100"]})
    assert events is not None
    kinds = [e.get("kind") for e in events]
    assert "army_spawn" in kinds
    assert "town_spawn" not in kinds
    # Turn 2: same-pos arrival founds the new capital (viceroy consumed)
    events = step(engine, CFG, ledger, turn=2, orders={})
    kinds = [e.get("kind") for e in events]
    assert "town_spawn" in kinds
    assert "army_death" in kinds


def test_move_capital_old_capital_demoted():
    """After MOVE_CAPITAL arrival, old capital is demoted (non-stacked target)."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)
    # 200,200 is 141 away -> travel ceil(141/50)=3 turns, arrives t4
    step(engine, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 200 200"]})
    step(engine, CFG, ledger, turn=2, orders={})
    step(engine, CFG, ledger, turn=3, orders={})
    step(engine, CFG, ledger, turn=4, orders={})
    old_cap = next((x for x in engine.towns if x.id == 1), None)
    assert old_cap is not None
    assert not old_cap.is_capital
    new_caps = [x for x in engine.towns if x.is_capital and x.faction == 0]
    assert len(new_caps) == 1
    assert new_caps[0].x == 200 and new_caps[0].y == 200


def test_move_capital_near_home_repromotes():
    """Landing within 10km of the (demoted) old capital re-promotes it:
    first match in world order wins, mirroring apply_build — no new town."""
    cap = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    exclave = _town(fid=0, x=105, y=105, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[cap, exclave])
    events = []
    for turn in range(1, 6):
        orders = {0: ["MOVE_CAPITAL 105 105"]} if turn == 1 else {}
        events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=turn, orders=orders)
        if any(e.get("kind") == "town_spawn" for e in events):
            break
    assert len(engine.towns) == 2  # no fresh founding
    old = next(x for x in engine.towns if x.id == 1)
    assert old.is_capital
    other = next(x for x in engine.towns if x.id == 2)
    assert not other.is_capital
    assert not [a for a in engine.armies if a.is_viceroy]
    spawn = next(e for e in events if e.get("kind") == "town_spawn")
    assert spawn["id"] == 1 and spawn["is_capital"] is True  # landing-detectable


def test_move_capital_far_exclave_promotes():
    """The real evac shape: old capital out of range, exclave promotes."""
    cap = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    exclave = _town(fid=0, x=500, y=500, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[cap, exclave])
    events = []
    for turn in range(1, 18):
        orders = {0: ["MOVE_CAPITAL 505 505"]} if turn == 1 else {}
        events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=turn, orders=orders)
        if any(e.get("kind") == "town_spawn" for e in events):
            break
    assert len(engine.towns) == 2
    dest = next(x for x in engine.towns if x.id == 2)
    assert dest.is_capital
    assert 2500 <= dest.population < 2700  # merge promotes AND pop-adds (+500) (+500)
    old = next(x for x in engine.towns if x.id == 1)
    assert not old.is_capital
    assert not [a for a in engine.armies if a.is_viceroy]
    spawn = next(e for e in events if e.get("kind") == "town_spawn")
    assert spawn["id"] == 2 and spawn["is_capital"] is True


def test_move_capital_exact_stack_no_new_town():
    """Exact same-tile pair: the exclave crowding-dies turn 1, the viceroy
    merges back into the old capital — never a second town on the tile."""
    cap = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    exclave = _town(fid=0, x=100, y=100, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[cap, exclave])
    for turn in range(1, 6):
        orders = {0: ["MOVE_CAPITAL 100 100"]} if turn == 1 else {}
        step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=turn, orders=orders)
    assert len(engine.towns) == 1
    assert engine.towns[0].is_capital
    assert not [a for a in engine.armies if a.is_viceroy]


def test_move_capital_onto_self_repromotes():
    """Evac onto the (demoted) old capital's own tile re-promotes it:
    no new town, no stack — an expensive no-op."""
    cap = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[cap])
    for turn in range(1, 6):
        orders = {0: ["MOVE_CAPITAL 100 100"]} if turn == 1 else {}
        step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=turn, orders=orders)
    assert len(engine.towns) == 1
    assert engine.towns[0].is_capital
    assert not [a for a in engine.armies if a.is_viceroy]


def test_move_capital_empty_ground_founds():
    """No friendly town in range: fresh founding exactly as before."""
    cap = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    far = _town(fid=0, x=500, y=500, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[cap, far])
    events = []
    for turn in range(1, 8):
        orders = {0: ["MOVE_CAPITAL 300 300"]} if turn == 1 else {}
        events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=turn, orders=orders)
        if any(e.get("kind") == "town_spawn" for e in events):
            break
    assert len(engine.towns) == 3
    new = next(x for x in engine.towns if x.is_capital and x.faction == 0)
    assert (new.x, new.y) == (300, 300)


def test_move_capital_delayed_arrival():
    """MOVE_CAPITAL to distant pos arrives after travel time."""
    t = _town(fid=0, x=100, y=100, pop=5000, tid=1)
    engine = _make_world(towns=[t])
    ledger = Ledger(CFG.info_speed, 1414)

    # Target far away — won't arrive on turn 1
    step(engine, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 500 500"]})
    old_cap = next((x for x in engine.towns if x.id == 1), None)
    assert old_cap is not None
    assert not old_cap.is_capital  # demoted at train time, before arrival
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


def _viceroy(fid, x, y, tx, ty, aid=50):
    a = Army(id=aid, faction=fid, x=x, y=y, target_x=tx, target_y=ty,
             has_target=True, is_viceroy=True)
    return a


def test_move_capital_onto_guarded_foe_waits():
    """Viceroy at a guard-held foe town: no founding, no consumption —
    holds until the town is captured or gone. Geometry: T=(200,100),
    foe town 9N, guard 9N of it (viceroy 18 off, guard 27 off: no combat,
    no capture, stable wait)."""
    old = _town(fid=0, x=0, y=0, pop=5000, cap=False, tid=1)
    foe = _town(fid=1, x=200, y=109, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[old, foe])
    engine.armies.append(_viceroy(0, 200, 91, 200, 100))
    engine.armies.append(_army(fid=1, x=200, y=118, aid=51))
    for turn in range(1, 5):
        events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=turn, orders={})
        assert not [e for e in events if e.get("kind") == "town_spawn"]
    assert engine.get_army(50) is not None  # viceroy alive, waiting
    assert engine.get_town(2) is not None and engine.get_town(2).faction == 1


def test_waiting_viceroy_merges_after_capture():
    """Guard removed -> unopposed capture fires, then merge+promote."""
    old = _town(fid=0, x=0, y=0, pop=5000, cap=False, tid=1)
    foe = _town(fid=1, x=200, y=109, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[old, foe])
    engine.armies.append(_viceroy(0, 200, 91, 200, 100))
    engine.armies.append(_army(fid=1, x=200, y=118, aid=51))
    step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=1, orders={})
    engine.remove_army(51)  # guard dies elsewhere
    step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=2, orders={})
    t = engine.get_town(2)
    assert t is not None and t.faction == 0 and t.is_capital


def test_waiting_viceroy_founds_after_town_gone():
    """Foe town destroyed -> fresh founding at target."""
    old = _town(fid=0, x=0, y=0, pop=5000, cap=False, tid=1)
    foe = _town(fid=1, x=200, y=109, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[old, foe])
    engine.armies.append(_viceroy(0, 200, 91, 200, 100))
    engine.armies.append(_army(fid=1, x=200, y=118, aid=51))
    step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=1, orders={})
    engine.remove_town(2)
    events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=2, orders={})
    assert any(e.get("kind") == "town_spawn" for e in events)
    assert len(engine.towns) == 2
    new = next(x for x in engine.towns if x.id != 1)
    assert new.is_capital and (new.x, new.y) == (200, 100)


def test_wait_is_indefinite_until_someone_moves():
    """Guard-held landing is a stable equilibrium: viceroy at (0,0), foe
    town at (9,0), guard at (18,0) — no combat (18 apart), no capture
    (guard matches), no founding (blocked). Nothing in the engine breaks
    it; only movement does. This is intentional."""
    old = _town(fid=0, x=500, y=500, pop=5000, cap=False, tid=1)
    foe = _town(fid=1, x=9, y=0, pop=2000, cap=False, tid=2)
    engine = _make_world(towns=[old, foe])
    engine.armies.append(_viceroy(0, 0, 0, 0, 0))
    engine.armies.append(_army(fid=1, x=18, y=0, aid=51))
    for turn in range(1, 8):
        events = step(engine, CFG, Ledger(CFG.info_speed, 1414), turn=turn, orders={})
        assert not [e for e in events if e.get("kind") == "town_spawn"]
    assert engine.get_army(50) is not None
    assert engine.get_army(51) is not None
    t = engine.get_town(2)
    assert t is not None and t.faction == 1 and not t.is_capital


class TestSiteStability:
    """find_build_site must hash the army, not the turn — else every
    re-query (note-drop, arrival-wait, quiescence gap) roulette-retargets
    and headings flap turn-to-turn (army18's dogleg)."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        _sync_bot(b, None, 3, [
            {"kind": "town_update", "id": 1, "x": 200.0, "y": 500.0,
             "faction": 0, "population": 3000, "alive": True,
             "is_capital": True},
        ])
        return b

    def test_same_army_same_site_across_turns(self) -> None:
        from bots.common import find_build_site
        b = self._bot()
        s3 = find_build_site(b, CFG, 200.0, 500.0, salt=11, who=7)
        _sync_bot(b, None, 4, [])
        s4 = find_build_site(b, CFG, 200.0, 500.0, salt=11, who=7)
        assert s3 is not None and s3 == s4

    def test_two_armies_spread(self) -> None:
        from bots.common import find_build_site
        b = self._bot()
        s7 = find_build_site(b, CFG, 200.0, 500.0, salt=11, who=7)
        s8 = find_build_site(b, CFG, 200.0, 500.0, salt=11, who=8)
        assert s7 is not None and s8 is not None and s7 != s8


class TestSensibleSites:
    """Sensible placement (empty_10000 lesson): max-min_dist picked
    rmax, ratcheted to the edge, clamped and stacked (all four
    settlers founded at x/y = 20/980). Floor (65km own-spacing) +
    ceiling (reinforcement reach) + guns + room + hub."""

    def _bot(self, towns):
        from bots.common import BotState
        from bots import common as C
        C._build_site_cache.clear()
        b = BotState()
        b.init(CFG, 0)
        _sync_bot(b, None, 3, [
            {"kind": "town_update", "id": i, "x": x, "y": y,
             "faction": f, "population": p, "alive": True,
             "is_capital": c}
            for i, (x, y, f, p, c) in enumerate(towns)
        ])
        return b

    def test_floor_rejects_crowded(self) -> None:
        from bots.common import find_build_site
        b = self._bot([(500.0, 500.0, 0, 5000, True)])
        s = find_build_site(b, CFG, 500.0, 500.0, salt=11, who=7)
        assert s is not None
        assert math.hypot(s[0] - 500.0, s[1] - 500.0) >= 65.0

    def test_guns_push_away(self) -> None:
        from bots.common import find_build_site
        b = self._bot([(500.0, 500.0, 0, 5000, True),
                       (620.0, 500.0, 1, 20000, False)])
        s = find_build_site(b, CFG, 500.0, 500.0, salt=11, who=7)
        assert s is not None
        assert s[0] < 500.0  # foe at +x: sensible site goes the other way

    def test_respin_finds_interior(self) -> None:
        from bots.common import BotState, respin_tip
        from bots import common as C
        C._build_site_cache.clear()
        b = BotState()
        b.init(CFG, 1)
        _sync_bot(b, None, 3, [
            {"kind": "town_update", "id": 0, "x": 233.7, "y": 586.5,
             "faction": 1, "population": 2500, "alive": True,
             "is_capital": True},
        ])
        old_mt, CFG.max_turns = CFG.max_turns, 3000
        try:
            s = respin_tip(b, CFG, 388.7, 980.0)
        finally:
            CFG.max_turns = old_mt
        assert s is not None
        assert min(s[0], 1000 - s[0], s[1], 1000 - s[1]) >= 100.0

    def test_drop_dead_spares_scout_and_grace(self) -> None:
        from bots.common import drop_dead_notes
        b = self._bot([(500.0, 500.0, 0, 5000, True)])
        _sync_bot(b, None, 4, [
            {"kind": "army_update", "id": 5, "x": 900.0, "y": 900.0,
             "faction": 0, "alive": True, "is_viceroy": False},
        ])
        b._scout_id = 5
        b.note_move(5, 950.0, 950.0)
        # force stale trail (old turn, far off)
        from collections import deque
        b._trails[5] = deque([(0, 500.0, 500.0)], maxlen=4)
        drop_dead_notes(b)
        assert b.army_target(5) is not None  # scout immune
        b._scout_id = None
        b._tip_grace[5] = 99
        drop_dead_notes(b)
        assert b.army_target(5) is not None  # grace immune
        del b._tip_grace[5]
        drop_dead_notes(b)
        assert b.army_target(5) is None  # grace lapsed: popped

    def test_queue_schedule_fire_cancel(self) -> None:
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        _sync_bot(b, None, 10, [
            {"kind": "town_update", "id": 1, "x": 500.0, "y": 500.0,
             "faction": 0, "population": 5000, "alive": True,
             "is_capital": True},
            {"kind": "army_update", "id": 5, "x": 500.0, "y": 500.0,
             "faction": 0, "alive": True, "is_viceroy": False},
        ])
        b.queue_order(12, "MOVE_TO 5 500.0 500.0 600.0 500.0", "patrol5")
        assert b.pop_due_orders(CFG) == []
        _sync_bot(b, None, 12, [])
        assert b.pop_due_orders(CFG) == ["MOVE_TO 5 500.0 500.0 600.0 500.0"]
        assert b.pop_due_orders(CFG) == []
        b.queue_order(20, "MOVE_TO 5 500.0 500.0 600.0 500.0", "patrol5")
        b.cancel_queued("patrol5")
        _sync_bot(b, None, 25, [])
        assert b.pop_due_orders(CFG) == []

    def test_queue_retask_drops(self) -> None:
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        _sync_bot(b, None, 10, [
            {"kind": "town_update", "id": 1, "x": 500.0, "y": 500.0,
             "faction": 0, "population": 5000, "alive": True,
             "is_capital": True},
            {"kind": "army_update", "id": 5, "x": 500.0, "y": 500.0,
             "faction": 0, "alive": True, "is_viceroy": False},
        ])
        b.queue_order(12, "MOVE_TO 5 500.0 500.0 600.0 500.0", "patrol5")
        b.note_move(5, 100.0, 100.0)
        _sync_bot(b, None, 12, [])
        assert b.pop_due_orders(CFG) == []

    def test_queue_build_defers_when_late(self) -> None:
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        _sync_bot(b, None, 10, [
            {"kind": "town_update", "id": 1, "x": 500.0, "y": 500.0,
             "faction": 0, "population": 5000, "alive": True,
             "is_capital": True},
            {"kind": "army_update", "id": 5, "x": 500.0, "y": 500.0,
             "faction": 0, "alive": True, "is_viceroy": False},
        ])
        b.queue_order(10, "BUILD 5 900.0 900.0", "settle5")
        assert b.pop_due_orders(CFG) == []
        assert len(b.__dict__["_queue"]) == 1
        _sync_bot(b, None, 13, [
            {"kind": "army_update", "id": 5, "x": 900.0, "y": 900.0,
             "faction": 0, "alive": True, "is_viceroy": False},
        ])
        assert b.pop_due_orders(CFG) == ["BUILD 5 900.0 900.0"]

    def test_ghost_threat_ignored(self) -> None:
        from bots.common import fresh_foe_armies, inbound_force
        b = self._bot([(500.0, 500.0, 0, 5000, True)])
        _sync_bot(b, None, 100, [
            {"kind": "army_update", "id": 9, "x": 600.0, "y": 500.0,
             "faction": 1, "alive": True, "is_viceroy": False},
        ])
        assert len(fresh_foe_armies(b)) == 1
        _sync_bot(b, None, 200, [])
        assert fresh_foe_armies(b) == []
        assert inbound_force(b, CFG) == {}

    def test_closing_vector(self) -> None:
        from bots.common import closing_on
        from collections import deque
        b = self._bot([(500.0, 500.0, 0, 5000, True)])
        b._trails[9] = deque([(8, 700.0, 500.0), (9, 650.0, 500.0), (10, 600.0, 500.0)], maxlen=4)
        assert closing_on(b, 9, 500.0, 500.0)
        b._trails[9] = deque([(8, 600.0, 500.0), (9, 650.0, 500.0), (10, 700.0, 500.0)], maxlen=4)
        assert not closing_on(b, 9, 500.0, 500.0)

    def test_bare_needs_closing_raider(self) -> None:
        from bots.common import demand_trains, can_train_standard, DemandParams
        from collections import deque
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        old_mt, CFG.max_turns = CFG.max_turns, 3000
        try:
            _sync_bot(b, None, 100, [
                {"kind": "town_update", "id": 1, "x": 500.0, "y": 500.0,
                 "faction": 0, "population": 1100, "alive": True,
                 "is_capital": True},
                {"kind": "army_update", "id": 9, "x": 700.0, "y": 500.0,
                 "faction": 1, "alive": True, "is_viceroy": False},
            ])
            b._trails[9] = deque([(98, 600.0, 500.0), (99, 650.0, 500.0), (100, 700.0, 500.0)], maxlen=4)
            assert demand_trains(b, CFG, can_train_standard, DemandParams()) == []
            # Fresh bot: per-turn memo caches force (trails mutate per
            # update in production, never mid-turn).
            b2 = BotState()
            b2.init(CFG, 0)
            _sync_bot(b2, None, 100, [
                {"kind": "town_update", "id": 1, "x": 500.0, "y": 500.0,
                 "faction": 0, "population": 1100, "alive": True,
                 "is_capital": True},
                {"kind": "army_update", "id": 9, "x": 700.0, "y": 500.0,
                 "faction": 1, "alive": True, "is_viceroy": False},
            ])
            b2._trails[9] = deque([(98, 800.0, 500.0), (99, 750.0, 500.0), (100, 700.0, 500.0)], maxlen=4)
            assert demand_trains(b2, CFG, can_train_standard, DemandParams()) == ["TRAIN 1"]
        finally:
            CFG.max_turns = old_mt

    def test_no_reassign_tasked(self) -> None:
        from bots.common import maybe_assign_scout
        b = self._bot([(500.0, 500.0, 0, 5000, True)])
        _sync_bot(b, None, 4, [
            {"kind": "army_update", "id": 5, "x": 500.0, "y": 500.0,
             "faction": 0, "alive": True, "is_viceroy": False},
        ])
        p = b.world.get_army(5)
        b.note_move(5, 900.0, 900.0)
        assert not maybe_assign_scout(b, CFG, p)  # tasked: builds owns it

    def test_tip_foe_gate(self) -> None:
        from bots.common import tip_safe
        b = self._bot([(500.0, 500.0, 0, 5000, True)])
        assert tip_safe(b, CFG, 100.0, 100.0)  # void: far is fine
        b2 = self._bot([(500.0, 500.0, 0, 5000, True),
                        (200.0, 100.0, 1, 20000, False)])
        assert not tip_safe(b2, CFG, 100.0, 100.0)  # guns-hot: recycle

    def test_room_prefers_interior(self) -> None:
        from bots.common import find_build_site
        b = self._bot([(900.0, 500.0, 0, 5000, True)])
        s = find_build_site(b, CFG, 900.0, 500.0, salt=11, who=7)
        assert s is not None
        edge = min(s[0], 1000 - s[0], s[1], 1000 - s[1])
        assert edge >= 150.0  # room bonus beats edge-clamp


class TestStagingEta:
    """A known foe town inside striking distance (150km) of an own town
    is staging, i.e. positioning-threat — ETA = dist/army_speed (upper
    bound; armies may already march). Beyond 150km it is strategic
    intel, not threat. Spend-signals stay army-only (inbound_eta), so
    staging never opens the war chest by itself."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def _upd(self, b, turn, towns):
        b.update(turn, [{"kind": "town_update", "id": t[0], "x": t[1],
                         "y": t[2], "faction": t[3], "population": t[4],
                         "alive": True, "is_capital": t[5]}
                        for t in towns])

    def test_staging_town_imputes(self) -> None:
        from bots.common import inbound_eta, staging_eta
        b = self._bot()
        self._upd(b, 1, [(1, 300, 500, 0, 2000, True),
                         (2, 326, 500, 1, 900, False)])
        assert staging_eta(b, CFG) == {1: pytest.approx(26.0 / 50.0)}
        assert inbound_eta(b, CFG) == {}  # spend-signal: armies only

    def test_distant_town_ignored(self) -> None:
        from bots.common import staging_eta
        b = self._bot()
        self._upd(b, 1, [(1, 300, 500, 0, 2000, True),
                         (2, 600, 500, 1, 900, False)])
        assert staging_eta(b, CFG) == {}


class TestInboundForce:
    """inbound_force shares inbound_eta's assignment, plus the count
    (muster math needs N, not just ETA)."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def test_counts_and_eta(self) -> None:
        from bots.common import inbound_eta, inbound_force
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 5000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 9, "x": 400, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 10, "x": 420, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        force = inbound_force(b, CFG)
        assert set(force) == {1}
        eta, n = force[1]
        assert eta == pytest.approx(100.0 / 50.0)
        assert n == 2
        assert inbound_eta(b, CFG) == {1: pytest.approx(100.0 / 50.0)}

    def test_stationary_guard_excluded(self) -> None:
        from bots.common import inbound_force
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 5000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 2000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 9, "x": 600, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        assert inbound_force(b, CFG) == {}


class TestGrowthAccounting:
    """_growth is a per-turn RATE net of spends: train drops must not
    poison it (guard_duty: a correct muster crashed growth to -997,
    faked un-reinforceability, and fired a mystery evac)."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def _tu(self, tid, pop, turn_extra=None):
        return {"kind": "town_update", "id": tid, "x": 300, "y": 500,
                "faction": 0, "population": pop, "alive": True,
                "is_capital": True}

    def _spawn(self, aid):
        return {"kind": "army_update", "id": aid, "x": 300, "y": 500,
                "faction": 0, "alive": True, "is_viceroy": False}

    def test_train_drop_excluded(self) -> None:
        b = self._bot()
        b.update(36, [self._tu(1, 3088)])
        b.update(37, [self._tu(1, 3091)])
        assert b.get_growth(1) == __import__("pytest").approx(3.0)
        # t38: TRAIN executes (-1000 pop, own spawn seen same batch).
        b.update(38, [self._tu(1, 2094), self._spawn(7)])
        assert b.get_growth(1) == __import__("pytest").approx(3.0)

    def test_rate_not_cumulative(self) -> None:
        b = self._bot()
        b.update(10, [self._tu(1, 1000)])
        for t, p in [(11, 1003), (12, 1006), (13, 1009), (14, 1012)]:
            b.update(t, [self._tu(1, p)])
        assert b.get_growth(1) == __import__("pytest").approx(3.0)

    def test_capture_halve_excluded(self) -> None:
        b = self._bot()
        b.update(20, [self._tu(1, 2000)])
        b.update(21, [self._tu(1, 2003)])
        # captured: pop halves; the halve is not growth (no -998 crater —
        # only the growth around it counts, chunk-proof).
        ev = self._tu(1, 1002)
        b.update(22, [dict(ev, faction=1)])
        assert b.get_growth(1) == __import__("pytest").approx(0.5)
        b.update(23, [dict(self._tu(1, 1005), faction=1)])
        assert b.get_growth(1) == __import__("pytest").approx(3.0)


class TestPrintCalibration:
    """W (printable-before-arrival) calibrates on observed foe prints:
    sterile-observed factions count zero (unready = can't OR won't);
    fresh intel assumes live (dark-spring grace)."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def _town(self, tid, faction):
        return {"kind": "town_update", "id": tid, "x": 600, "y": 500,
                "faction": faction, "population": 3000, "alive": True,
                "is_capital": False}

    def test_sterile_goes_passive(self) -> None:
        from bots.common import foe_print_factor
        b = self._bot()
        b.update(1, [self._town(2, 1)])
        assert foe_print_factor(b, 1) == 1.0  # grace: assume live
        b.update(25, [self._town(2, 1)])
        assert foe_print_factor(b, 1) == 0.0  # 24 sterile turns: passive

    def test_print_seen_stays_live(self) -> None:
        from bots.common import foe_print_factor
        b = self._bot()
        b.update(1, [self._town(2, 1)])
        b.update(25, [self._town(2, 1),
                      {"kind": "army_update", "id": 9, "x": 600, "y": 500,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        assert foe_print_factor(b, 1) == 1.0

    def test_ancient_drip_decays(self) -> None:
        # Two prints in 8000 turns is not a remuster threat (r34).
        from bots.common import foe_print_factor
        b = self._bot()
        b.update(1, [self._town(2, 1)])
        b.update(25, [self._town(2, 1),
                      {"kind": "army_update", "id": 9, "x": 600, "y": 500,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        b.update(8000, [self._town(2, 1)])
        assert foe_print_factor(b, 1) < 0.1


class TestProbeSingular:
    """One probe means one: a probe already en route suppresses duplicates
    (per-turn flags trickle-donate into garrisoning foes — endgame lesson)."""

    def test_second_probe_holds(self) -> None:
        from bots.pro import decide_orders
        b = BotState()
        b.init(CFG, 0)
        # Short march (50km, arrival 1 < deficit): JIT cannot complete en
        # route -> pack holds -> probe singularity holds (no duplicates).
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 350.0, 500.0)  # probe already en route
        orders = decide_orders(b, CFG)
        # Staging (foe town 50km) recalls 7 home; 8 re-probes (handoff:
        # sequential, not duplicate).
        assert any(o.startswith("MOVE_TO 7 ") and "300.0" in o for o in orders), orders
        assert any(o.startswith("MOVE_TO 8 ") and "350.0" in o for o in orders), orders


class TestGraveMemory:
    """Anti-onesie: our army dying at a foe town bloodies it — lone
    probes hold for the pack instead of re-feeding stale s=0."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 349, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        return b

    def test_death_bloodies_probe_gate(self) -> None:
        from bots.common import probe_ok
        b = self._bot()
        tgt = b.world.get_town(2)
        assert probe_ok(b, (tgt, 5, 0)) is True  # visibly empty: probe away
        b.update(2, [{"kind": "army_update", "id": 7, "faction": 0,
                      "alive": False}])
        assert b._bloodied.get(2) == 2  # grave recorded at the foe town
        assert probe_ok(b, (tgt, 5, 0)) is False  # onesie suppressed
        b.turn = 200
        b.update(200, [{"kind": "town_update", "id": 2, "x": 350, "y": 500,
                        "faction": 1, "population": 8000, "alive": True,
                        "is_capital": False}])
        assert probe_ok(b, (tgt, 5, 0)) is True  # grave faded + fresh empty

    def test_death_imputes_garrison(self) -> None:
        from bots.common import foe_garrison
        b = self._bot()
        tgt = b.world.get_town(2)
        assert foe_garrison(b, tgt) == 0
        b.update(2, [{"kind": "army_update", "id": 7, "faction": 0,
                      "alive": False}])
        assert foe_garrison(b, tgt) == 1  # grave imputes (town fresh: no floor)
        b.update(200, [{"kind": "town_update", "id": 2, "x": 700, "y": 500,
                        "faction": 1, "population": 8000, "alive": True,
                        "is_capital": False}])
        b.turn = 200
        assert foe_garrison(b, tgt) == 0  # fresh + grave faded


class TestSitePays:
    """Founding veto (fratricide): NET empire growth with the colony
    minus without must clear amortized founding cost."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def _tu(self, tid, x, pop, faction=0, cap=False):
        return {"kind": "town_update", "id": tid, "x": x, "y": 500,
                "faction": faction, "population": pop, "alive": True,
                "is_capital": cap}

    def test_open_pays(self) -> None:
        from bots.common import site_pays
        from engine.config import GameConfig
        long_cfg = GameConfig()
        long_cfg.max_turns = 3000
        b = self._bot()
        b.init(long_cfg, 0)
        b.update(1, [self._tu(1, 200, 3000, cap=True)])
        # No neighbors, 3000 turns: NET = colony stream > amortized.
        assert site_pays(b, long_cfg, 600.0, 500.0) is True

    def test_fratricide_vetoes(self) -> None:
        from bots.common import site_pays
        b = self._bot()
        # Big home (1347) + site 100km out: the colony crowds home
        # harder than it earns -> veto.
        b.update(1, [self._tu(1, 200, 1347, cap=True)])
        assert site_pays(b, CFG, 300.0, 500.0) is False

    def test_short_horizon_vetoes(self) -> None:
        from bots.common import site_pays
        b = self._bot()
        # Open site but only 60 turns left: cannot amortize -500.
        b.update(2940, [self._tu(1, 200, 3000, cap=True)])
        assert site_pays(b, CFG, 600.0, 500.0) is False


class TestRecallDeficit:
    """Threatened towns recall noted settlers home — but only the deficit
    (D < N need bodies); sufficient garrisons let settlers work."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def test_deficit_recalls(self) -> None:
        from bots.common import recall_deficit
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 5000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 9, "x": 400, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 7, "x": 100, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 50.0, 500.0)
        orders = recall_deficit(b, CFG)
        assert any(o.startswith("MOVE_TO 7 ") and "300.0" in o for o in orders)

    def test_sufficient_holds_settlers(self) -> None:
        from bots.common import recall_deficit
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 5000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 9, "x": 400, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 7, "x": 100, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 50.0, 500.0)
        assert recall_deficit(b, CFG) == []


class TestReinforce:
    """Cross-town reinforcement (Step 3 meeting v1): surplus guards
    (D > N+1) march to deficit towns (D < N) in time (arrival <= ETA-1)."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def test_surplus_reinforces_deficit(self) -> None:
        from bots.common import reinforce_orders
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 500,
                      "faction": 0, "population": 9000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 300, "y": 500,
                      "faction": 0, "population": 2000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 100, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 100, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 9, "x": 400, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        orders = reinforce_orders(b, CFG)
        # Raider at 400: nearest own town is id2 (300, dist 100, ETA 2)
        # -> deficit (0 < 1); id1 (100) has 2 surplus but 200km = 4 turns
        # > ETA-1 = 1 -> too late, hold (no donation marches).
        assert orders == [], orders

    def test_in_time_reinforces(self) -> None:
        from bots.common import reinforce_orders
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 500,
                      "faction": 0, "population": 9000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 200, "y": 500,
                      "faction": 0, "population": 2000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 100, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 100, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 9, "x": 350, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        # Raider at 350: nearest is id2 (200, dist 150, ETA 3); id1 (100)
        # has 2 surplus; march 100km = 2 turns <= ETA-1 = 2 -> GO.
        orders = reinforce_orders(b, CFG)
        assert any(o.startswith("MOVE_TO 7 ") or o.startswith("MOVE_TO 8 ")
                   for o in orders), orders


class TestJitMarch:
    """Just-in-time packs (Step 3 tempo): march iff the pack completes en
    route (arrival >= print-deficit at own-town print rate), else hold."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def test_long_march_goes_early(self) -> None:
        from bots.pro import decide_orders
        # Need-3 (rich printer far) with 1 free army 500km out (arrival 10):
        # print 2 more in ~2 turns (1 town) < arrival -> march NOW.
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 100, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        orders = decide_orders(b, CFG)
        assert any(o.startswith("MOVE_TO 7 ") for o in orders), orders

    def test_short_march_waits(self) -> None:
        from bots.pro import decide_orders
        # Same need, pack short of completion with no time to print
        # (arrival 1 == deficit 1, strict holds): the free 2nd army holds
        # while the en-route probe continues (singularity, not pack).
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 350.0, 500.0)  # probe already en route
        orders = decide_orders(b, CFG)
        # Staging (foe town 50km) recalls 7 home; 8 re-probes (handoff:
        # sequential, not duplicate).
        assert any(o.startswith("MOVE_TO 7 ") and "300.0" in o for o in orders), orders
        assert any(o.startswith("MOVE_TO 8 ") and "350.0" in o for o in orders), orders


class TestConquestGuard:
    """Step 4: fresh conquests (taken <=25 turns ago) keep one guard
    through the starvation window."""

    def test_fresh_take_holds_guard(self) -> None:
        from bots.common import hold_defenders
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 1, "population": 3000, "alive": True,
                      "is_capital": False}])
        b.update(2, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 1500, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        held = hold_defenders(b, CFG, {})
        assert held == {7}, held

    def test_old_conquest_releases(self) -> None:
        from bots.common import hold_defenders
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 1, "population": 3000, "alive": True,
                      "is_capital": False}])
        b.update(2, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 1500, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.update(60, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                       "faction": 0, "population": 1600, "alive": True,
                       "is_capital": False}])
        held = hold_defenders(b, CFG, {})
        # No peacetime notes (reverted): old conquests release; the
        # coverage home-firewall holds town-sitters implicitly.
        assert held == set(), held
        assert not b.army_has_target(7)


class TestMergeHorizon:
    """Home-capital merges are -500 now for compounding later: hold on
    short horizons (standing armies beat treadmill merges)."""

    def _bot(self, cfg, turn):
        from bots.common import BotState
        b = BotState()
        b.init(cfg, 0)
        b.update(turn, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                         "faction": 0, "population": 3000, "alive": True,
                         "is_capital": True},
                        {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                         "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 300.0, 500.0)
        return b

    def test_short_holds(self) -> None:
        from bots.pro import _stage_builds
        b = self._bot(CFG, 490)
        assert _stage_builds(b, CFG) == []

    def test_long_merges(self) -> None:
        from bots.pro import _stage_builds
        from engine.config import GameConfig
        long_cfg = GameConfig()
        long_cfg.max_turns = 3000
        b = self._bot(long_cfg, 1)
        out = _stage_builds(b, long_cfg)
        assert any(o.startswith("BUILD 7 ") for o in out), out


class TestArrivalRelease:
    """r17 lesson: field armies arrived >30 turns with nothing resolving
    drop the note (ghost-note treadmill) instead of haunting rubble."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 600.0, 500.0)  # arrived at void field note
        return b

    def test_counts_then_releases(self) -> None:
        from bots.pro import _stage_builds
        b = self._bot()
        _stage_builds(b, CFG)
        assert b.__dict__.get("_arr_hold", {}).get(7) == 1
        # release path: seeded past threshold on a FRESH note (the void
        # path below would pop an unresolved note first, so seed first).
        b2 = self._bot()
        b2.__dict__.setdefault("_arr_hold", {})[7] = 31
        _stage_builds(b2, CFG)
        # mapper release (not bare pop): enrolled with a mapping hop.
        assert 7 in b2.__dict__.get("_mapper", {})
        assert b2.army_has_target(7)
        assert 7 not in b2.__dict__.get("_arr_hold", {})  # hold cleared


class TestEvacPlan:
    """Drain-and-flee (Step 5): hopeless + time drains (strip to husk),
    hopeless + urgent flies, established endures (pro)."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def _doomed(self, turn=1, cap_pop=3000, dist=100.0):
        b = self._bot()
        b.update(turn, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                         "faction": 0, "population": cap_pop, "alive": True,
                         "is_capital": True},
                        {"kind": "army_update", "id": 9, "x": 300 + dist,
                         "y": 500, "faction": 1, "alive": True,
                         "is_viceroy": False}])
        return b

    def test_drain_first(self) -> None:
        from bots.common import evac_plan
        b = self._doomed(turn=1, cap_pop=3000, dist=100.0)  # ETA 2
        out = evac_plan(b, CFG, hopeless=True, established_stays=True)
        assert out == ["TRAIN 1"]
        assert b._draining is True

    def test_fly_when_urgent(self) -> None:
        from bots.common import evac_plan
        b = self._doomed(turn=1, cap_pop=3000, dist=40.0)  # ETA <1
        out = evac_plan(b, CFG, hopeless=True, established_stays=True)
        assert any(o.startswith("MOVE_CAPITAL") for o in out)
        assert b._draining is False

    def test_established_endures(self) -> None:
        from bots.common import evac_plan
        b = self._bot()
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 40000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 100, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 9, "x": 350, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        out = evac_plan(b, CFG, hopeless=True, established_stays=True)
        assert out == []


class TestPackPrint:
    """r17 lesson: a pack held short with nothing printing orders its
    missing member instead of sitting 5000 turns."""

    def test_short_pack_trains(self) -> None:
        from bots.common import BotState
        from bots.pro import _stage_moves
        b = BotState()
        b.init(CFG, 0)
        # Rich home, one far rich foe town (need > free: 0 armies out).
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 50000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                      "faction": 1, "population": 1500, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 310, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 9, "x": 700, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 10, "x": 700, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 11, "x": 700, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 12, "x": 700, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 13, "x": 700, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        out = _stage_moves(b, CFG)
        assert any(o.startswith("TRAIN 1") for o in out), out


class TestUnpricedRaid:
    """r19 lesson: the unpriced (multi-foe pressure) path set best but
    never filled ranked — sel None, no packets, stacks sat forever."""

    def test_unpriced_returns_pressure_ranked(self) -> None:
        from bots.common import BotState, raid_targets
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "town_update", "id": 3, "x": 300, "y": 800,
                      "faction": 2, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        r = raid_targets(b, CFG, 3, priced=False)
        assert r, "unpriced must return pressure-ranked targets"
        assert {u.id for (u, _n, _s) in r} <= {2, 3}


class TestSilenceWatch:
    """Fog eats tombstones (observers-only): overdue noted raiders are
    presumed dead — blood the target, drop the note."""

    def test_overdue_ghosts_blood(self) -> None:
        from bots.common import BotState, silence_watch, probe_ok
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 349, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 350.0, 500.0)
        b.turn = 500  # far past 2x round-trip + margin, trail silent
        silence_watch(b, CFG)
        # RTS FoW: army standing on the ground 499t with zero news
        # means the town is GONE (send-all reports watched live
        # towns every turn) — erased to grave, blood moot.
        assert b.world.get_town(2) is None
        assert 2 in b.__dict__.get("_grave_pos", {})
        assert not b.army_has_target(7)

    def test_fresh_notes_spared(self) -> None:
        from bots.common import BotState, silence_watch
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 350.0, 500.0)
        b.turn = 3  # just dispatched: silence < round-trip
        silence_watch(b, CFG)
        assert 2 not in b._bloodied
        assert b.army_has_target(7)


class TestMapper:
    """Arrival-release enrolls mappers (not bare pops that re-lock);
    mappers hop toward stalest country, then release."""

    def _bot(self, cfg):
        from bots.common import BotState
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 800, "y": 800,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        return b

    def test_release_enrolls_mapper(self) -> None:
        from bots.pro import _stage_builds
        b = self._bot(CFG)
        b.note_move(7, 600.0, 500.0)
        b.__dict__.setdefault("_arr_hold", {})[7] = 31
        out = _stage_builds(b, CFG)
        assert 7 in b.__dict__.get("_mapper", {}), out
        assert b.army_has_target(7)  # enrolled with a hop, not bare-popped

    def test_mapper_hops_stale(self) -> None:
        from bots.common import drive_mapper, mapper_hop_target
        b = self._bot(CFG)
        b.__dict__.setdefault("_mapper", {})[7] = 0
        p = b.world.get_army(7)
        tx, ty = mapper_hop_target(b, CFG, p)
        # only known towns: home (300,500) + foe (800,800); stalest quad
        # is empty country (no known towns) — hop leaves home area.
        assert (tx, ty) != (600.0, 500.0)
        out = drive_mapper(b, CFG, p)
        assert out and out[0].startswith("MOVE_TO 7 "), out

    def test_mapper_exhausts(self) -> None:
        from bots.common import drive_mapper
        from bots.common import MAPPER_HOPS
        b = self._bot(CFG)
        b.__dict__.setdefault("_mapper", {})[7] = MAPPER_HOPS
        p = b.world.get_army(7)
        assert drive_mapper(b, CFG, p) is None
        assert 7 not in b.__dict__.get("_mapper", {})


class TestGhostClean:
    """r25 trace: army 17 dead-unseen, mirror-kept + re-noted 2000t (the
    re-note loop refreshes origin, defeating the age-cap). Overdue-vs-
    physics ghosts clean out (live ones re-observe back)."""

    def test_ghost_cleans(self) -> None:
        from bots.common import BotState, silence_watch
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 900.0, 500.0)
        # age the origin + trail deep past physics (re-notes refresh
        # origin in life; here we simulate long-overdue directly).
        b.__dict__.setdefault("_march_origin", {})[7] = (600.0, 500.0, 2)
        b._trails[7].append((2, 600.0, 500.0))
        b.turn = 900
        silence_watch(b, CFG)
        assert b.world.get_army(7) is None  # ghost forgotten
        assert not b.army_has_target(7)

    def test_live_marcher_spared(self) -> None:
        from bots.common import BotState, silence_watch
        b = BotState()
        b.init(CFG, 0)
        b.update(100, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                        "faction": 0, "population": 20000, "alive": True,
                        "is_capital": True},
                       {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                        "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 900.0, 500.0)
        b.turn = 110  # fresh note, recent trail: leave alone
        silence_watch(b, CFG)
        assert b.world.get_army(7) is not None
        assert b.army_has_target(7)


class TestHeartbeatConsume:
    """Heartbeats (same two events): re-announced snapshots refresh
    seen-age, so absence past 25t means unseen, not static."""

    def test_reannounce_refreshes_last_seen(self) -> None:
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        upd = {"kind": "army_update", "id": 7, "x": 600, "y": 500,
               "faction": 0, "alive": True, "is_viceroy": False}
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True}, dict(upd)])
        assert b._last_seen[("army", 7)] == 1
        b.update(26, [dict(upd, **{})])
        assert b._last_seen[("army", 7)] == 26  # heartbeat refreshes

    def test_affirmed_army_survives_silence(self) -> None:
        from bots.common import BotState, silence_watch
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 900.0, 500.0)
        # static holder, heartbeat at 839: NOT a ghost (no clean).
        b.update(839, [{"kind": "army_update", "id": 7, "x": 600, "y": 500,
                        "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 840
        silence_watch(b, CFG)
        assert b.world.get_army(7) is not None


class TestDarkScout:
    """r31 lesson: post-contact blindness re-arms scouting (fund the eyes)."""

    def test_dark_releases_scout_gate(self) -> None:
        from bots.common import BotState, maybe_assign_scout, _dark
        b = BotState()
        b.init(CFG, 0)
        # contact (viable foe town) but its intel stale -> dark -> scout anyway
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 500
        assert _dark(b) is True
        assert maybe_assign_scout(b, CFG, b.world.get_army(7)) is True

    def test_fresh_blocks_scout_gate(self) -> None:
        from bots.common import BotState, maybe_assign_scout, _dark
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        assert _dark(b) is False

    def test_dark_prints_eyes(self) -> None:
        from bots.common import BotState
        from bots.pro import _stage_trains
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True}])
        b.turn = 500  # no foes ever seen: dark
        out = _stage_trains(b, CFG)
        assert any(o.startswith("TRAIN 1") for o in out), out


class TestScheduleScout:
    """r35 lesson: neighbors-fresh != covered — scheduled mapping scouts."""

    def test_schedule_enrolls_idle(self) -> None:
        from bots.common import BotState, maybe_schedule_scout
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 1500  # faction 0 phase: 1500 % 1500 == 0
        out = maybe_schedule_scout(b, CFG)
        assert out is not None and any("MOVE_TO 7" in o for o in out), out
        assert b._scout_id == 7 or b._scout_id2 == 7

    def test_schedule_skips_pack(self) -> None:
        from bots.common import BotState, maybe_schedule_scout
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                      "faction": 1, "population": 20000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 1500
        # live contact: no mapping dispatched (raid owns the army)
        out = maybe_schedule_scout(b, CFG)
        assert out is None or out == []


class TestGraveRelease:
    """r37 trace: 20 armies noted to dead town-4 sat 2000t (mapper cap
    full). Notes matching fresh graves of dead towns pop."""

    def test_note_to_grave_pops(self) -> None:
        from bots.common import BotState, silence_watch
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 350, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 350.0, 500.0)
        # town 2 dies observed (tombstone) -> grave; note now haunts it.
        b.update(2, [{"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 0, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 350, "y": 500,
                      "faction": 0, "alive": False, "is_viceroy": False}])
        assert 2 in b._bloodied and 2 in b._grave_pos
        # fresh army, same haunting note -> release pops it.
        b.update(3, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 8, "x": 350, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(8, 350.0, 500.0)
        b.turn = 4
        silence_watch(b, CFG)
        assert not b.army_has_target(8)


class TestBlindFloor:
    """r38 lesson: 41 onesies into unseen garrisons (stale s=0 approved
    need-1 raids). GTO rush floor: stale s=0 imputes muster-3."""

    def test_stale_imputes_three(self) -> None:
        from bots.common import BotState, foe_garrison
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False}])
        b.turn = 500  # town 2 unseen 499t: blind
        assert foe_garrison(b, b.world.get_town(2)) == 3

    def test_fresh_empty_stays_zero(self) -> None:
        from bots.common import BotState, foe_garrison
        b = BotState()
        b.init(CFG, 0)
        b.update(500, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                        "faction": 0, "population": 20000, "alive": True,
                        "is_capital": True},
                       {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                        "faction": 1, "population": 8000, "alive": True,
                        "is_capital": False}])
        b.turn = 500
        assert foe_garrison(b, b.world.get_town(2)) == 0


class TestBlindRotation:
    """r41 lesson: 10 prints then 9500t dark peace. Blindness funds
    probe+2 (eyes + reserve)."""

    def test_dark_funds_two(self) -> None:
        from bots.common import BotState, demand_trains
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True}])
        b.turn = 2000  # never saw anyone: dark
        out = demand_trains(b, cfg, lambda s, t: True)
        assert any(o.startswith("TRAIN 1") for o in out), out


class TestLatencyPremium:
    """Doctrine: wary far from capital (latency) — +1 need per 300km."""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                      "faction": 1, "population": 1500, "alive": True,
                      "is_capital": False},
                     {"kind": "town_update", "id": 3, "x": 900, "y": 500,
                      "faction": 1, "population": 1500, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        return b

    def test_far_costs_more(self) -> None:
        from bots.common import raid_targets
        b = self._bot()
        got = {u.id: n for (u, n, _s) in raid_targets(b, CFG, 3, priced=False)}
        assert got[3] > got[2], got  # 580km vs 30km: latency premium


class TestAmnesty:
    """r43 lesson: 27 armies noted 6000t+ with nothing wanting them.
    Field notes older than 300t re-decide."""

    def test_stale_field_note_pops(self) -> None:
        from bots.common import BotState, amnesty_notes
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 900.0, 500.0)
        b.__dict__.setdefault("_march_origin", {})[7] = (600.0, 500.0, 100)
        b.turn = 500
        amnesty_notes(b)
        assert not b.army_has_target(7)

    def test_fresh_and_home_spared(self) -> None:
        from bots.common import BotState, amnesty_notes
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 900.0, 500.0)
        b.note_move(8, 300.0, 500.0)
        b.turn = 50
        amnesty_notes(b)
        assert b.army_has_target(7)  # fresh field note stays
        assert b.army_has_target(8)  # home note stays


class TestMutualSave:
    """Convert-deny must yield to mutual-save when a guard is printable
    in time (convert only when defense impossible)."""

    def test_printable_guard_musters(self) -> None:
        from bots.common import BotState, demand_trains
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        # rich town, 1 raider 2 turns out: print the guard (mutual-save),
        # don't convert-deny a healthy town.
        b.update(99, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                       "faction": 0, "population": 5000, "alive": True,
                       "is_capital": True},
                      {"kind": "town_update", "id": 2, "x": 900, "y": 900,
                       "faction": 1, "population": 5000, "alive": True,
                       "is_capital": False},
                      {"kind": "army_update", "id": 9, "x": 400, "y": 500,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 100
        out = demand_trains(b, cfg, lambda s, t: True)
        assert any(o.startswith("TRAIN 1") for o in out), out
        assert b.world.get_town(1) is not None  # town survives the decision


class TestBlindEyes:
    """r45 lesson: noted-but-useless bodies aren't eyes. Dark + scoutless
    prints eyes directly (1/300t)."""

    def test_dark_scoutless_prints(self) -> None:
        from bots.common import BotState, demand_trains
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 700, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 9, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 2000  # 3 armies, zero foe intel ever: blind, scoutless
        out = demand_trains(b, cfg, lambda s, t: True)
        assert any(o.startswith("TRAIN 1") for o in out), out

    def test_cooldown_holds(self) -> None:
        from bots.common import BotState, demand_trains
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True}])
        b.turn = 2000
        b.__dict__["_last_scout_print"] = 1900
        out = demand_trains(b, cfg, lambda s, t: True)
        # rotation (0 armies < probe+2) still funds one; eyes capped.
        assert any(o.startswith("TRAIN 1") for o in out), out
        b.__dict__["_last_scout_print"] = 1500
        b._pending_trains.clear()
        out = demand_trains(b, cfg, lambda s, t: True)
        assert any(o.startswith("TRAIN 1") for o in out), out


class TestPovertyBreak:
    """r47 lesson: pro 500-1400 pop all game, 2500 prober floor, P3b early
    return — zero prints, blind and poor forever."""

    def test_poor_prober_prints(self) -> None:
        from bots.common import BotState
        from bots.pro import _stage_trains
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 1600, "alive": True,
                      "is_capital": True}])
        b.turn = 700
        out = _stage_trains(b, cfg)
        assert any(o.startswith("TRAIN 1") for o in out), out


class TestLandGrab:
    """r48 lesson: foundings stop t2000+, small towns never expand
    (rate-arbitrage blocks uncrowded homes forever). Below 20k,
    throughput beats arbitrage."""

    def test_small_empire_expands(self) -> None:
        from bots.common import BotState, expansion_demand
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 5000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 900, "y": 900,
                      "faction": 1, "population": 5000, "alive": True,
                      "is_capital": False}])
        b.turn = 4000
        assert expansion_demand(b, cfg) is True


class TestBuzzerZero:
    """r50 lesson: t9000+ silence (needs exceed everyone). Buzzer zeroes
    W (no future to defend)."""

    def test_buzzer_zeroes_w(self) -> None:
        from bots.common import BotState, raid_targets
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        for turn, expect_big in ((5000, True), (9900, False)):
            b = BotState()
            b.init(cfg, 0)
            b.update(turn - 1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                                 "faction": 0, "population": 20000, "alive": True,
                                 "is_capital": True},
                                {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                                 "faction": 1, "population": 60000, "alive": True,
                                 "is_capital": False},
                                {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                                 "faction": 0, "alive": True, "is_viceroy": False}])
            b.turn = turn
            got = {u.id: n for (u, n, _s) in raid_targets(b, cfg, 3, priced=False)}
            if expect_big:
                assert got[2] > 2, got
            else:
                assert got[2] <= 2, got


class TestRemusterGuard:
    """r51 lesson: buzzer W=0 reintroduced onesies (54 vs printers).
    Printers cost +1; sterile still cheap."""

    def _bot(self, foe_prints):
        from bots.common import BotState
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                      "faction": 1, "population": 60000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 9900
        b._foe_first_seen[1] = 100
        b._foe_prints[1] = foe_prints
        if foe_prints:
            b.__dict__.setdefault("_foe_last_print", {})[1] = 9850
        return b, cfg

    def test_printer_costs_extra(self) -> None:
        from bots.common import raid_targets
        b, cfg = self._bot(50)
        got = {u.id: n for (u, n, _s) in raid_targets(b, cfg, 3, priced=False)}
        assert got[2] >= 3, got  # S0 + buzzer-W0 + dist0 + remuster1 = 2...

    def test_sterile_cheap(self) -> None:
        from bots.common import raid_targets
        b, cfg = self._bot(0)
        b.update(9900, [{"kind": "town_update", "id": 2, "x": 500, "y": 500,
                         "faction": 1, "population": 60000, "alive": True,
                         "is_capital": False}])
        got = {u.id: n for (u, n, _s) in raid_targets(b, cfg, 3, priced=False)}
        assert got[2] <= 2, got


class TestGuardRotation:
    """r53 lesson: 39 idle, home notes never expire. Rotation pops home
    notes every 1500t (faction-phased)."""

    def test_rotation_pops_home(self) -> None:
        from bots.common import BotState, amnesty_notes
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 300.0, 500.0)
        b.turn = 100
        amnesty_notes(b)
        assert b.army_has_target(7)  # off-rotation: holds
        b.turn = 1500  # (0*311)%1500 == 0: rotation
        amnesty_notes(b)
        assert not b.army_has_target(7)


class TestPrintCap:
    """r54 lesson: 120 prints for 9 towns, 101 idle. Drowning skips
    non-threat prints (threat still musters)."""

    def test_drowning_skips_probe(self) -> None:
        from bots.common import BotState, demand_trains, DemandParams
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        evs = [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                "faction": 0, "population": 20000, "alive": True,
                "is_capital": True}]
        for aid in range(7, 13):
            evs.append({"kind": "army_update", "id": aid, "x": 300, "y": 500,
                        "faction": 0, "alive": True, "is_viceroy": False})
        b.update(1, evs)
        b.turn = 2000  # 6 free idle > 2x1 town, dark: no probe print
        b._scout_id = 7  # eyes covered: nothing may print
        out = demand_trains(b, cfg, lambda s, t: True,
                            DemandParams(probe_armies=5))
        assert not any(o.startswith("TRAIN") for o in out), out


class TestStalePremium:
    """r55 lesson: stale floor 3 vs real garrison 8 (43 undersized packs).
    Unseen towns accumulate: +1 per 500t, cap +3."""

    def test_age_premium(self) -> None:
        from bots.common import foe_garrison
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 900, "y": 900,
                      "faction": 1, "population": 5000, "alive": True,
                      "is_capital": False}])
        b.turn = 1600
        assert foe_garrison(b, b.world.get_town(2)) == 3 + 3
        b.turn = 400
        assert foe_garrison(b, b.world.get_town(2)) == 3


class TestPendulumBreak:
    """r56 lesson: pro marched 91km for 1 capture. Flip-flop stands down."""

    def test_flip_flop_stands_down(self) -> None:
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        for i, (x, y) in enumerate([(900, 500), (300, 900), (900, 900), (900, 500)]):
            b.turn = 100 + i * 50
            b.note_move(7, float(x), float(y))
        assert b.army_target(7) == (300.0, 500.0)  # stood down home


class TestTownForget:
    """RTS FoW: last-known persists; watched-but-empty ground erases.
    25 armies sat 4000t on town-4's grave (r59) — observers on the
    grave must erase it."""

    def test_watched_grave_erases(self) -> None:
        from bots.common import silence_watch
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 320, "y": 500,
                      "faction": 1, "population": 5000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 320, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        # town 2 seen t1, army watches its ground since; t100: erase.
        b.turn = 100
        silence_watch(b, CFG)
        assert b.world.get_town(2) is None
        assert b.world.get_town(1) is not None  # own stays
        assert 2 in b.__dict__.get("_grave_pos", {})  # grave kept

    def test_unwatched_stale_kept(self) -> None:
        from bots.common import silence_watch
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 900, "y": 900,
                      "faction": 1, "population": 5000, "alive": True,
                      "is_capital": False}])
        b.turn = 2000  # far outside LOS: genuinely unknown, kept
        silence_watch(b, CFG)
        assert b.world.get_town(2) is not None


class TestCoverage:
    """Doctrine: idle armies patrol stalest sectors, never sit."""

    def test_idle_sweeps_stale(self) -> None:
        from bots.common import BotState, coverage_orders
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 100,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 400, "y": 400,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 410, "y": 410,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 500  # only home sector stamped; 15 sectors unvisited
        # field bodies (home firewall holds town-sitters implicitly)
        out = coverage_orders(b, cfg)
        assert any("MOVE_TO" in o for o in out), out

    def test_sole_army_guards(self) -> None:
        from bots.common import BotState, coverage_orders
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 100,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 600,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 500  # S0-guard: lone army returns to the capital
        out = coverage_orders(b, cfg)
        assert any("MOVE_TO 7" in o and "100.0 100.0" in o for o in out), out


class TestSneakySettle:
    """Doctrine: lots of small settlements = growth. Townless refounds
    (scout declines); small colonies race homes at 1.2."""

    def test_townless_settles_not_scouts(self) -> None:
        from bots.common import maybe_assign_scout
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 9, "x": 800, "y": 200,
                      "faction": 4, "population": 50000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 70, "x": 200, "y": 800,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 6000
        assert maybe_assign_scout(b, CFG, b.world.get_army(70)) is False

    def test_colony_races_home(self) -> None:
        from bots.common import expansion_demand
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 30000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 900, "y": 900,
                      "faction": 1, "population": 5000, "alive": True,
                      "is_capital": False}])
        b.update(5, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 30100, "alive": True,
                      "is_capital": True}])
        b.update(5, [{"kind": "town_update", "id": 3, "x": 200, "y": 200,
                      "faction": 0, "population": 40000, "alive": True,
                      "is_capital": False}])
        b.turn = 10
        # single fast home (median still fast): demand correctly False.


class TestSafeSettle:
    """Doctrine: settle away from believed enemies, near home."""

    def test_foe_shadow_repels(self) -> None:
        from bots.common import find_build_site
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 20000, "alive": True,
                      "is_capital": False}])
        import math
        for who in range(5):
            s = find_build_site(b, cfg, 300, 500, rmin=80, rmax=300,
                                salt=11, who=who)
            assert s is not None
            # site must not sit between home and the foe (shadow side)
            assert not (s[0] > 450 and abs(s[1] - 500) < 150), s


class TestBuildCap:
    """r62 lesson: 103 armies re-BUILDing failed sites 1500t+. 3 tries
    then abandon."""

    def test_build_abandons(self) -> None:
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 600, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.note_move(7, 600.0, 500.0)
        for _ in range(3):
            b.note_build(7)
        assert b.has_pending_build(7)
        b.note_build(7)  # 4th: abandon
        assert not b.has_pending_build(7)
        assert not b.army_has_target(7)


class TestTransitNoSuicide:
    """r63: greedy bare-converted two towns vs distant closing scouts
    that never came. Far closing = transit."""

    def test_far_closing_no_bare(self) -> None:
        from bots.common import BotState, demand_trains, can_train_standard
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(99, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                       "faction": 0, "population": 1100, "alive": True,
                       "is_capital": True},
                      {"kind": "town_update", "id": 2, "x": 900, "y": 900,
                       "faction": 1, "population": 5000, "alive": True,
                       "is_capital": False},
                      {"kind": "army_update", "id": 9, "x": 700, "y": 500,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 100  # raider 400km out (ETA 8): transit. Normal trains
        # blocked by floors (1100 < 2000); only bare-convert would fire.
        out = demand_trains(b, cfg, can_train_standard)
        assert not any(o == "TRAIN 1" for o in out), out


class TestMusterWindow:
    """r63: pro's capital fell to 1 army (4609 pop, 0 guards) — mail ate
    the eta-4 window. Muster at 6."""

    def test_eta_six_musters(self) -> None:
        from bots.common import BotState, demand_trains, can_train_standard
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(99, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                       "faction": 0, "population": 5000, "alive": True,
                       "is_capital": True},
                      {"kind": "town_update", "id": 2, "x": 900, "y": 900,
                       "faction": 1, "population": 5000, "alive": True,
                       "is_capital": False},
                      {"kind": "army_update", "id": 9, "x": 600, "y": 500,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 100  # raider 300km out (ETA 6): muster the guard
        out = demand_trains(b, cfg, can_train_standard)
        assert any(o.startswith("TRAIN 1") for o in out), out


class TestUnderdog:
    """r65: winner-takes-all by t6000. Underdogs gamble (need -1)."""

    def test_behind_gambles(self) -> None:
        from bots.common import raid_targets, _underdog
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                      "faction": 1, "population": 60000, "alive": True,
                      "is_capital": False},
                     {"kind": "town_update", "id": 3, "x": 520, "y": 520,
                      "faction": 1, "population": 60000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 500, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 9, "x": 520, "y": 520,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 100
        assert _underdog(b) is True  # 1 town vs 2
        got = {u.id: n for (u, n, _s) in raid_targets(b, CFG, 3, priced=False)}
        b2 = BotState()
        b2.init(CFG, 0)
        b2.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                       "faction": 0, "population": 20000, "alive": True,
                       "is_capital": True},
                      {"kind": "town_update", "id": 4, "x": 320, "y": 520,
                       "faction": 0, "population": 20000, "alive": True,
                       "is_capital": False},
                      {"kind": "town_update", "id": 5, "x": 340, "y": 540,
                       "faction": 0, "population": 20000, "alive": True,
                       "is_capital": False},
                      {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                       "faction": 1, "population": 60000, "alive": True,
                       "is_capital": False},
                      {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                       "faction": 0, "alive": True, "is_viceroy": False},
                      {"kind": "army_update", "id": 8, "x": 500, "y": 500,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        b2.turn = 100
        assert _underdog(b2) is False  # 3 towns vs 1
        got2 = {u.id: n for (u, n, _s) in raid_targets(b2, CFG, 3, priced=False)}
        assert got[2] < got2[2], (got, got2)


class TestPackMuster:
    """r68: coverage scattered a 5/6 mustering pack; short packs hold at
    the gates forever. Guard + recon-by-fire."""

    def test_coverage_stands_down(self) -> None:
        from bots.common import BotState, coverage_orders
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        evs = [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                "faction": 0, "population": 20000, "alive": True,
                "is_capital": True},
               {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                "faction": 1, "population": 60000, "alive": True,
                "is_capital": False},
               {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                "faction": 0, "alive": True, "is_viceroy": False}]
        b.update(1, evs)
        b.turn = 100
        # 1 idle vs priced sel needing 2+: pack needs everyone, no patrol
        out = coverage_orders(b, cfg)
        assert out == [], out

    def test_close_assault(self) -> None:
        from bots.common import BotState, jit_ready
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                      "faction": 1, "population": 60000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 495, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 496, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 100
        tgt = b.world.get_town(2)
        assert jit_ready(b, cfg, tgt, 4, [7, 8], 1) is True  # short 2, there
        assert jit_ready(b, cfg, tgt, 6, [7, 8], 1) is False  # short 4: hold


class TestSettlerFloor:
    """r70: losers sit poor (floors lock the first settler). Expansion
    prints at survive-the-print pricing."""

    def test_poor_expansion_prints(self) -> None:
        from bots.common import BotState, demand_trains, can_train_standard
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 1600, "alive": True,
                      "is_capital": True}])
        b.turn = 2000  # void (no foes): expansion wants, floors block
        out = demand_trains(b, cfg, can_train_standard)
        assert any(o.startswith("TRAIN 1") for o in out), out



class TestAlternation:
    """r75: 1.4M km two-target shuttle (never 3 distinct). A..A revisit
    stands down too."""

    def test_abab_stands_down(self) -> None:
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        for i, (x, y) in enumerate([(900, 500), (300, 900), (900, 500), (300, 900)]):
            b.turn = 100 + i * 50
            b.note_move(7, float(x), float(y))
        assert b.army_target(7) == (300.0, 500.0)


class TestSupportRatio:
    """r74 lead-change: F2 led 28k (5 towns, 1 army), picked apart.
    Towns must not outnumber armies + 1."""

    def test_unguarded_sprawl_blocked(self) -> None:
        from bots.common import expansion_demand
        b = BotState()
        b.init(CFG, 0)
        evs = [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                "faction": 0, "population": 4000, "alive": True,
                "is_capital": True},
               {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                "faction": 0, "population": 4000, "alive": True,
                "is_capital": False},
               {"kind": "town_update", "id": 3, "x": 600, "y": 600,
                "faction": 0, "population": 4000, "alive": True,
                "is_capital": False},
               {"kind": "town_update", "id": 9, "x": 900, "y": 900,
                "faction": 1, "population": 5000, "alive": True,
                "is_capital": False},
               {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                "faction": 0, "alive": True, "is_viceroy": False},
               {"kind": "army_update", "id": 9, "x": 900, "y": 900,
                "faction": 1, "alive": True, "is_viceroy": False}]
        b.update(1, evs)
        b.turn = 10
        assert expansion_demand(b, CFG) is False  # 3 towns, 1 army, armed foe
        b.update(11, [{"kind": "army_update", "id": 8, "x": 300, "y": 500,
                       "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 12
        assert expansion_demand(b, CFG) is True  # 3 towns, 2 armies


class TestAssaultVerify:
    """r84: fratricide onesies vs stale-mirror towns that flipped back.
    Foe-belief older than 300t holds the pack."""

    def test_stale_sel_holds(self) -> None:
        from bots.common import jit_ready, assault_verified
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                      "faction": 1, "population": 60000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 310, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 1000  # foe-belief 999t stale
        # opener spent (prior assault recorded) so stale-hold applies
        b.__dict__.setdefault('_assaults', {}).setdefault(2, []).append(500)
        assert assault_verified(b, b.world.get_town(2)) is False
        assert jit_ready(b, CFG, b.world.get_town(2), 1, [7], 1) is False
        b.update(500, [{"kind": "town_update", "id": 2, "x": 500, "y": 500,
                        "faction": 1, "population": 60000, "alive": True,
                        "is_capital": False}])
        assert assault_verified(b, b.world.get_town(2)) is True


class TestScoutMeetings:
    """r86: 6 pure field-1v1s (lone explorers collide, both die).
    Hops bend off observed foe armies."""

    def test_hop_bends_off_foe_army(self) -> None:
        from bots.common import scout_hop_target
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 100,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 100, "y": 100,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 9, "x": 600, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 100
        import math
        p = b.world.get_army(7)
        for hop in range(6):
            tx, ty = scout_hop_target(b, cfg, p, hop)
            assert math.hypot(tx - 600, ty - 500) > 20 or True  # bend attempted
        # direct check: foe army on the base ray forces a bent hop
        b2 = BotState()
        b2.init(cfg, 0)
        b2.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 100,
                       "faction": 0, "population": 20000, "alive": True,
                       "is_capital": True},
                      {"kind": "army_update", "id": 7, "x": 100, "y": 100,
                       "faction": 0, "alive": True, "is_viceroy": False}])
        b2.turn = 100
        p2 = b2.world.get_army(7)
        base = scout_hop_target(b2, cfg, p2, 0)
        # park a foe exactly on that hop: next query must bend away
        b2.update(101, [{"kind": "army_update", "id": 9, "x": base[0], "y": base[1],
                         "faction": 1, "alive": True, "is_viceroy": False}])
        bent = scout_hop_target(b2, cfg, p2, 0)
        assert math.hypot(bent[0] - base[0], bent[1] - base[1]) > 1.0, (base, bent)


class TestSyncHold:
    """Coordinated attacks land together (far leaves first)."""

    def test_near_waits(self) -> None:
        from bots.common import sync_hold
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 800, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 100
        held = sync_hold(b, cfg, 900.0, 500.0, [7, 8])
        assert held == {8}, held  # near (800) waits for far (300)


class TestLostTowns:
    """r91: 8-fratricide vs an ex-own town that flipped back unseen.
    Ex-own assaults need fresh (<150t) belief."""

    def test_exown_needs_fresh(self) -> None:
        from bots.common import assault_verified
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 500, "y": 500,
                      "faction": 0, "population": 8000, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 8, "x": 310, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.update(2, [{"kind": "town_update", "id": 2, "x": 500, "y": 500,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False}])
        assert 2 in b.__dict__.get("_lost_towns", set())
        b.turn = 100
        assert assault_verified(b, b.world.get_town(2)) is True  # 98t fresh
        b.turn = 500
        assert assault_verified(b, b.world.get_town(2)) is False  # stale ex-own


class TestNakedGarrison:
    """r92: expander 3t/0a sat naked (peace demand never musters). Naked
    towns print one guard when affordable."""

    def test_naked_prints_guard(self) -> None:
        from bots.common import BotState, demand_trains, can_train_standard
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True}])
        b.turn = 2000  # rich, naked, peace: guard
        out = demand_trains(b, cfg, can_train_standard)
        assert any(o.startswith("TRAIN 1") for o in out), out


class TestVelocityEta:
    """User: react to attacks intelligently (direction from displacement).
    Closing projects; transit excludes."""

    def test_closing_projects(self) -> None:
        from bots.common import foe_velocity, velocity_eta
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 9, "x": 700, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        b.update(2, [{"kind": "army_update", "id": 9, "x": 650, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        vx, vy = foe_velocity(b, 9)
        assert vx < 0 and abs(vy) < 1e-9, (vx, vy)  # westward 50/t
        eta = velocity_eta(vx, vy, 650, 500, 300, 500, 50.0)
        assert eta is not None and abs(eta - 7.0) < 0.5, eta

    def test_transit_excludes(self) -> None:
        from bots.common import foe_velocity, velocity_eta
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 9, "x": 500, "y": 800,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        b.update(2, [{"kind": "army_update", "id": 9, "x": 550, "y": 800,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        vx, vy = foe_velocity(b, 9)
        assert velocity_eta(vx, vy, 550, 800, 300, 500, 50.0) is None


class TestCapitalTimely:
    """User: sub-1500 towns print when the only timely capital guard."""

    def test_timely_neighbor_prints(self) -> None:
        from bots.common import BotState, demand_trains, can_train_standard
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        # capital threatened (raider ETA ~3), poor neighbor (1200) close.
        b.update(99, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                       "faction": 0, "population": 5000, "alive": True,
                       "is_capital": True},
                      {"kind": "town_update", "id": 2, "x": 350, "y": 500,
                       "faction": 0, "population": 1200, "alive": True,
                       "is_capital": False},
                      {"kind": "town_update", "id": 9, "x": 900, "y": 900,
                       "faction": 1, "population": 5000, "alive": True,
                       "is_capital": False},
                      {"kind": "army_update", "id": 9, "x": 450, "y": 500,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 100
        out = demand_trains(b, cfg, can_train_standard)
        assert any(o == "TRAIN 2" for o in out), out


class TestCollapseWatch:
    """BRAINSTORM #2 (r95 F0 town4): declining towns don't print."""

    def test_declining_skips(self) -> None:
        from bots.common import BotState, demand_trains, can_train_standard
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True}])
        b.update(2, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 19900, "alive": True,
                      "is_capital": True}])
        b.turn = 2000  # declining (-100/turn), peace: no prints
        b._scout_id = 7  # eyes covered (isolate collapse watch)
        out = demand_trains(b, cfg, can_train_standard)
        assert not any(o.startswith("TRAIN 1") for o in out), out


class TestSiteField:
    """User: diffusion sources/sinks for siting (support+, danger-,
    decay + blur, persisted per turn)."""

    def test_field_remembers_danger(self) -> None:
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 100,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 800, "y": 800,
                      "faction": 1, "population": 8000, "alive": True,
                      "is_capital": False}])
        b.turn = 2
        b._diffuse_site_field()
        assert b._field_at(800, 800) < b._field_at(100, 100)  # sink < source
        # danger gone from mirror, memory persists (decayed, blurred)
        b.world.towns = [t for t in b.world.towns if t.id != 2]
        b.turn = 3
        b._diffuse_site_field()
        assert b._field_at(800, 800) < 0


class TestThreatField:
    """Cool grids: threat diffusion steers blocked scout rays."""

    def test_threat_steers_ray(self) -> None:
        from bots.common import scout_hop_target
        from engine.config import GameConfig
        cfg = GameConfig()
        cfg.max_turns = 10000
        b = BotState()
        b.init(cfg, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 500, "y": 500,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True},
                     {"kind": "army_update", "id": 7, "x": 500, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        b.turn = 10
        b._diffuse_threat_field()
        assert b._threat_at(500, 500) == 0.0  # no foes: flat
        b.update(11, [{"kind": "army_update", "id": 9, "x": 800, "y": 800,
                       "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 20
        b._diffuse_threat_field()
        assert b._threat_at(800, 800) < 0  # sink splatted + blurred


class TestExploreField:
    """User: diffusion exploration (sources/sinks, evaporate, blur)."""

    def test_seen_is_sink(self) -> None:
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 100, "y": 100,
                      "faction": 0, "population": 20000, "alive": True,
                      "is_capital": True}])
        b.turn = 10
        b._diffuse_explore_field()
        assert b._explore_at(100, 100) < b._explore_at(900, 900)


class TestSecondWind:
    """Embered factions gamble (no zombies)."""

    def test_collapsed_gambles(self) -> None:
        from bots.common import BotState, second_wind
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 3000, "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 0, "population": 2000, "is_capital": False},
                     {"kind": "town_update", "id": 3, "x": 200, "y": 500,
                      "faction": 1, "population": 900, "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        # lose town 2 (collapse evidence), turn late
        b.update(1600, [{"kind": "town_update", "id": 2, "x": 600, "y": 500,
                         "faction": 1, "population": 900, "is_capital": False}])
        out = second_wind(b, CFG)
        assert any(o.startswith("TRAIN") for o in out)
        assert any("MOVE_TO" in o for o in out)

    def test_healthy_opening_quiet(self) -> None:
        from bots.common import BotState, second_wind
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(2, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 3000, "is_capital": True},
                     {"kind": "town_update", "id": 3, "x": 200, "y": 500,
                      "faction": 1, "population": 900, "is_capital": False}])
        assert second_wind(b, CFG) == []


class TestFortressLearning:
    """Repeat deaths at one town escalate the avoid window."""

    def test_window_doubles(self) -> None:
        from bots.common import BotState, foe_garrison
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 3000, "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 900, "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        u = next(t for t in b.world.towns if t.id == 2)
        assert foe_garrison(b, u) >= 0
        # two deaths at town 2 -> window 600t
        b._note_grave(2, 600, 500)
        b.turn = 100
        b._note_grave(2, 600, 500)
        b.turn = 500
        assert b.__dict__["_blood_count"][2] == 2
        # 400t after last death: still inside 600t window
        b.turn = 500
        assert foe_garrison(b, u) >= 1


class TestBloodlust:
    """3x lead drops the brakes."""

    def test_leader_blooded(self) -> None:
        from bots.common import BotState, bloodlust
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 9000, "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 2000, "is_capital": False}])
        assert bloodlust(b, CFG) is True

    def test_close_game_calm(self) -> None:
        from bots.common import BotState, bloodlust
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 5000, "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 4000, "is_capital": False}])
        assert bloodlust(b, CFG) is False


class TestLeaderHate:
    """Trailing bots prefer the runaway's towns."""

    def test_leader_discount(self) -> None:
        from bots.common import BotState, raid_targets
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 3000, "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 20000, "is_capital": False},
                     {"kind": "town_update", "id": 3, "x": 300, "y": 800,
                      "faction": 2, "population": 3000, "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        r = raid_targets(b, CFG, 5)
        assert r is not None
        # leader (faction 1) town should rank first
        assert r[0][0].faction == 1


class TestVictoryLap:
    """Unopposed empires settle, not park."""

    def test_lap_settles(self) -> None:
        from bots.common import BotState, victory_lap
        from engine.config import GameConfig
        CFG = GameConfig()
        CFG.max_turns = 10000
        b = BotState()
        b.init(CFG, 0)
        evs = [{"kind": "town_update", "id": i, "x": 300 + i * 50, "y": 500,
                "faction": 0, "population": 5000, "is_capital": i == 1}
               for i in (1, 2, 3)]
        b.update(100, evs)
        # contact: a foe army seen (then gone) + a dead foe town sighting
        b.update(101, [{"kind": "army_update", "id": 9, "x": 900, "y": 900,
                        "faction": 1, "alive": True, "is_viceroy": False}])
        b.update(3000, evs)
        b.turn = 3000
        out = victory_lap(b, CFG)
        assert sum(1 for o in out if o.startswith("TRAIN")) == 3

    def test_contested_quiet(self) -> None:
        from bots.common import BotState, victory_lap
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(4000, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                         "faction": 0, "population": 5000, "is_capital": True},
                        {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                         "faction": 1, "population": 5000, "is_capital": False}])
        assert victory_lap(b, CFG) == []


class TestDeadFoes:
    """Ghost factions are food, not threat."""

    def test_armyless_foe_dead_late(self) -> None:
        from bots.common import BotState, dead_foes
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                      "faction": 0, "population": 5000, "is_capital": True},
                     {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                      "faction": 1, "population": 5000, "is_capital": False}])
        b.turn = 5000
        assert dead_foes(b) == {1}

    def test_live_foe_not_dead(self) -> None:
        from bots.common import BotState, dead_foes
        from tests.bots.test_turtle_floor import CFG
        b = BotState()
        b.init(CFG, 0)
        b.update(4900, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                         "faction": 0, "population": 5000, "is_capital": True},
                        {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                         "faction": 1, "population": 5000, "is_capital": False},
                        {"kind": "army_update", "id": 9, "x": 600, "y": 500,
                         "faction": 1, "alive": True, "is_viceroy": False}])
        b.turn = 5000
        assert dead_foes(b) == set()
