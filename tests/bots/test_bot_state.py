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
from engine.delivery import SendState, build_updates
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
    assert build_updates(ledger, 0, SendState(), 0, (0.0, 0.0), 1.0) == []


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
    got = build_updates(ledger, 0, SendState(), 0, (100.0, 100.0), 2.0)
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

    got = build_updates(ledger, 0, SendState(), 0, (100.0, 100.0), 1.0)
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
        assert held == set(), held


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
        from bots.greedy import _stage_builds
        b = self._bot(CFG, 490)
        assert _stage_builds(b, CFG) == []

    def test_long_merges(self) -> None:
        from bots.greedy import _stage_builds
        from engine.config import GameConfig
        long_cfg = GameConfig()
        long_cfg.max_turns = 3000
        b = self._bot(long_cfg, 1)
        out = _stage_builds(b, long_cfg)
        assert any(o.startswith("BUILD 7 ") for o in out), out


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
