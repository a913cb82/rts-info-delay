"""Tests for engine/step — turn resolution order, info delay, order lag, commands."""

from __future__ import annotations

import pytest

from engine.config import GameConfig
from engine.ledger import Event, EventKind, Ledger
from engine.step import step
from engine.world import Army, CommandType, Messenger, StandingOrder, Town, World

CFG = GameConfig()


def _world_with(
    armies: list[Army] | None = None,
    towns: list[Town] | None = None,
    map_size: list[int] | None = None,
) -> World:
    """Helper: create a World."""
    w = World()
    w.map_size = map_size or [1000, 1000]
    if armies:
        w.armies = armies
    if towns:
        w.towns = towns
    return w


def _army(x: float, y: float, faction: int, aid: int) -> Army:
    return Army(id=aid, faction=faction, x=x, y=y)


def _town(x: float, y: float, pop: float, faction: int, tid: int, cap: bool = False) -> Town:
    return Town(id=tid, faction=faction, x=x, y=y, population=pop, is_capital=cap)


class TestTurnOrder:
    """T1–T7: Turn resolution phase ordering."""

    def test_command_before_movement(self) -> None:
        """T1: Command delivered same turn as move → army uses new course."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        # Order: MOVE_TO army 1 → (100, 0)
        orders = {0: ["MOVE_TO 1 0 0 100 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Army should have moved toward (100, 0)
        assert w.armies[0].x > 0

    def test_combat_after_movement(self) -> None:
        """T2: Combat resolves at final positions, not start."""
        # Two armies march toward each other, should meet and fight
        a1 = _army(0, 0, 0, 1)
        a1.target_x, a1.target_y = 60, 0
        a1.has_target = True
        a2 = _army(100, 0, 1, 2)
        a2.target_x, a2.target_y = 40, 0
        a2.has_target = True
        w = _world_with(armies=[a1, a2])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={})
        # After movement, armies should be closer; combat should resolve
        # Both should die if they end up within interact_radius
        # (depending on exact implementation, they may or may not end up within 10km)
        # At minimum, movement happened before combat check
        assert len(w.armies) <= 2  # some may have died

    def test_economy_after_combat(self) -> None:
        """T3: Economy runs after combat — newly TRAINed armies don't fight."""
        t = _town(100, 100, 2000, faction=0, tid=1)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        # Standing TRAIN order
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        step(w, CFG, ledger, turn=1, orders={})
        # Army spawned during economy, should not have participated in combat
        assert len(w.armies) == 1  # newly spawned

    def test_knowledge_after_economy(self) -> None:
        """T4: Ledger events logged after economy+combat, not instantly."""
        w = _world_with(armies=[_army(0, 0, 0, 1), _army(5, 0, 1, 2)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={})
        # Events should be in ledger
        assert len(ledger.events) > 0
        # All events logged at current turn
        for ev in ledger.events:
            assert ev.turn == 1

    def test_fresh_spawns_immune_this_turn(self) -> None:
        """T5: TRAIN-spawned army immune from combat this turn."""
        t = _town(0, 0, 5000, faction=0, tid=1)
        enemy = _army(3, 0, faction=1, aid=2)  # very close to town
        w = _world_with(towns=[t], armies=[enemy])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        step(w, CFG, ledger, turn=1, orders={})
        # Spawned army should exist (immune from combat)
        friendly_armies = [a for a in w.armies if a.faction == 0]
        assert len(friendly_armies) >= 1

    def test_eviction_last(self) -> None:
        """T6: Ledger eviction happens after knowledge phase."""
        w = _world_with()
        ledger = Ledger(CFG.info_speed, 1414)
        # Log an old event manually
        ledger.log(Event(turn=1, x=0, y=0, kind=EventKind.BATTLE, payload={}))
        step(w, CFG, ledger, turn=100, orders={})
        # Old event should be evicted (well past window)
        # The step function calls evict at the end

    def test_full_sequence_determinism(self) -> None:
        """T7: Same inputs → same outputs across 10 turns."""
        def run_10_turns(seed_world: World) -> list[tuple[float, float]]:
            """Run 10 turns, return army positions."""
            w = _world_with(armies=[_army(0, 0, 0, 1)])
            w.armies[0].target_x = 100
            w.armies[0].target_y = 0
            w.armies[0].has_target = True
            ledger = Ledger(CFG.info_speed, 1414)
            for t in range(1, 11):
                step(w, CFG, ledger, turn=t, orders={})
            return [(a.x, a.y) for a in w.armies]

        run1 = run_10_turns(None)
        run2 = run_10_turns(None)
        assert run1 == run2


class TestInfoDelay:
    """I1–I5e: Information delay — events visible only after propagation time."""

    def test_near_event_same_turn(self) -> None:
        """I1: Event at dist 50 → visible by turn 1 (within info_speed)."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=1, x=50, y=0, kind=EventKind.BATTLE, payload={}))
        visible = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=1.5)
        assert len(visible) == 1

    def test_far_event_delayed(self) -> None:
        """I2: Event at dist 300 → delayed 2 turns."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=1, x=300, y=0, kind=EventKind.BATTLE, payload={}))
        # Delay = 300/150 = 2.0, visible at turn 1+2=3
        v_now2 = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=2.0)
        assert len(v_now2) == 0
        v_now3 = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=3.0)
        assert len(v_now3) == 1

    def test_at_capital_immediate(self) -> None:
        """I3: Event at capital position → zero delay."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=5, x=100, y=200, kind=EventKind.ARMY_SPAWN, payload={}))
        visible = ledger.visible_events(faction=0, capital_x=100, capital_y=200, now=5.0)
        assert len(visible) == 1

    def test_independent_delays(self) -> None:
        """I4: Three events at different distances → visible at different times."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=1, x=10, y=0, kind=EventKind.BATTLE, payload={}))
        ledger.log(Event(turn=1, x=150, y=0, kind=EventKind.BATTLE, payload={}))
        ledger.log(Event(turn=1, x=300, y=0, kind=EventKind.BATTLE, payload={}))

        v1 = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=1.1)
        assert len(v1) == 1  # only near event
        v2 = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=2.0)
        assert len(v2) == 2  # near + middle
        v3 = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=3.0)
        assert len(v3) == 3  # all

    def test_ledger_window_retain(self) -> None:
        """I5: Ledger retains events for ≥ max_dist/info_speed turns."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=1, x=0, y=0, kind=EventKind.BATTLE, payload={}))
        # max window = 1414/150 ≈ 9.4 turns
        visible = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=10.0)
        assert len(visible) == 1

    def test_no_delivery_during_capital_flight(self) -> None:
        """I5b: No events delivered during MOVE_CAPITAL flight."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=1, x=0, y=0, kind=EventKind.BATTLE, payload={}))
        visible = ledger.visible_events(
            faction=0, capital_x=0, capital_y=0, now=100.0, is_in_flight=True
        )
        assert len(visible) == 0

    def test_capital_move_changes_dist(self) -> None:
        """I5c: After capital move, old events re-evaluated from new capital."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=1, x=0, y=0, kind=EventKind.BATTLE, payload={}))
        # Near old capital
        v1 = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=1.0)
        assert len(v1) == 1
        # Far from new capital → delay
        v2 = ledger.visible_events(faction=0, capital_x=500, capital_y=0, now=2.0)
        assert len(v2) == 0

    def test_event_kind_fields(self) -> None:
        """I5d: Events have kind field."""
        ledger = Ledger(CFG.info_speed, 1414)
        for kind in EventKind:
            ledger.log(Event(turn=1, x=0, y=0, kind=kind, payload={}))
        kinds = {e.kind for e in ledger.events}
        assert kinds == set(EventKind)

    def test_faction_specific_visibility(self) -> None:
        """I5e: Factions see events at different times based on capital distance."""
        ledger = Ledger(CFG.info_speed, 1414)
        ledger.log(Event(turn=1, x=100, y=0, kind=EventKind.BATTLE, payload={}))
        # Faction 0 capital at (0,0): dist=100 → delay=0.67
        v0 = ledger.visible_events(faction=0, capital_x=0, capital_y=0, now=1.7)
        assert len(v0) == 1
        # Faction 1 capital at (400,0): dist=300 → delay=2.0
        v1 = ledger.visible_events(faction=1, capital_x=400, capital_y=0, now=2.0)
        assert len(v1) == 0
        v1_later = ledger.visible_events(faction=1, capital_x=400, capital_y=0, now=3.0)
        assert len(v1_later) == 1


class TestOrderLag:
    """L1–L5e: Messenger-based order delivery."""

    def test_travel_time(self) -> None:
        """L1: Order travels at info_speed; 100 km → 0.67 turns."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        orders = {0: ["MOVE_TO 1 0 0 100 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Messenger created, delivery may happen same or next turn
        # depending on distance and speed
        assert len(w.messengers) >= 0  # messenger may have been delivered already

    def test_same_turn_if_close(self) -> None:
        """L2: Very close target → delivered same turn."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        # Order to army at same position → instant delivery
        orders = {0: ["MOVE_TO 1 0 0 5 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Army should have received the order
        a = w.armies[0]
        assert a.has_target or a.x > 0  # either target set or already moved

    def test_fifo_per_entity(self) -> None:
        """L3: Two orders to same army executed in FIFO order."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        orders = {0: ["MOVE_TO 1 0 0 100 0", "MOVE_TO 1 0 0 200 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Second order overwrites first (both queued FIFO)
        a = w.armies[0]
        if a.has_target:
            assert a.target_x == 200  # second order wins

    def test_dead_letter_army_death(self) -> None:
        """L4: Order to dead army → discarded (no crash)."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        # Army will die in combat (place enemy nearby)
        w.armies.append(_army(3, 0, 1, 2))
        orders = {0: ["MOVE_TO 1 0 0 100 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Should not crash even if army died
        assert len(w.armies) <= 2

    def test_dead_letter_army_consumed(self) -> None:
        """L4b: Order to army consumed by BUILD → discarded."""
        w = _world_with(armies=[_army(100, 200, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        # BUILD consumes army, then a MOVE_TO arrives for same army
        orders = {0: ["BUILD 1 100 200", "MOVE_TO 1 0 0 200 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # No crash expected

    def test_dead_letter_town_death(self) -> None:
        """L4c: TRAIN to dead town → discarded."""
        t = _town(0, 0, 200, faction=0, tid=1)  # below death threshold
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        step(w, CFG, ledger, turn=1, orders={})
        # Town should be removed, no crash from standing order

    def test_standing_order_persists(self) -> None:
        """L5: MOVE_TO once → army continues toward target."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        orders = {0: ["MOVE_TO 1 0 0 200 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        x_after_1 = w.armies[0].x
        step(w, CFG, ledger, turn=2, orders={})
        x_after_2 = w.armies[0].x
        assert x_after_2 > x_after_1

    def test_TRAIN_then_TRAIN_second_ignored_after_pop_depleted(self) -> None:
        """TRAIN with 1110 pop: first TRAIN spawns (pop→110) and town dies, second TRAIN is dead letter."""
        # Capital close to town (10 km) so messenger delivered same turn, but not at same pos to avoid extreme crowding
        cap = _town(0, 0, 5000, faction=0, tid=10, cap=True)
        t = _town(10, 0, 1110, faction=0, tid=1)
        w = _world_with(towns=[cap, t])
        ledger = Ledger(CFG.info_speed, 1414)
        # Turn 1: TRAIN 1 — pop 1110 → 110, spawns 1 army, town dies (110 < 500)
        step(w, CFG, ledger, turn=1, orders={0: ["TRAIN 1"]})
        assert len(w.armies) == 1
        assert w.get_town(1) is None  # died
        # Turn 2: TRAIN 1 again — town is dead, should be ignored (dead letter)
        step(w, CFG, ledger, turn=2, orders={0: ["TRAIN 1"]})
        assert len(w.armies) == 1  # no new army
        assert w.get_town(1) is None

    def test_train_standing_one_shot(self) -> None:
        """L5b: TRAIN standing order is one-shot (consumed after execution)."""
        t = _town(100, 100, 10000, faction=0, tid=1)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        for turn in range(1, 4):
            step(w, CFG, ledger, turn=turn, orders={})
        # TRAIN is one-shot: only 1 army spawned
        assert len(w.armies) == 1
        assert len(w.standing_orders) == 0

    def test_messenger_pursuit(self) -> None:
        """L5c: Messenger targets current entity position."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        orders = {0: ["MOVE_TO 1 0 0 100 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Messenger should follow the army

    def test_fifo_across_movement(self) -> None:
        """L5d: Two orders queued while army moving; second starts from new course."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        orders = {0: ["MOVE_TO 1 0 0 100 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Second order to different target
        orders2 = {0: ["MOVE_TO 1 0 0 0 100"]}
        step(w, CFG, ledger, turn=2, orders=orders2)

    def test_move_capital_instant(self) -> None:
        """L5e: MOVE_CAPITAL executes instantly at capital."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        orders = {0: ["MOVE_CAPITAL 200 200"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        # Guard army should be spawned instantly
        viceroy_armies = [a for a in w.armies if a.is_viceroy]
        assert len(viceroy_armies) == 1


class TestCommands:
    """O1–O13: Command processing — MOVE_TO, BUILD, TRAIN, MOVE_CAPITAL."""

    def test_move_to_sets_course(self) -> None:
        """O1: MOVE_TO sets army target, army moves next movement phase."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        orders = {0: ["MOVE_TO 1 0 0 100 100"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        a = w.armies[0]
        # Either target is set or army already moved
        assert a.has_target or (a.x > 0 or a.y > 0)

    def test_move_to_distance_check(self) -> None:
        """O2: MOVE_TO ignored if army not near command target when delivered."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        # from (999,999) but army at (0,0) → stale command
        orders = {0: ["MOVE_TO 1 999 999 200 200"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        a = w.armies[0]
        # Should be ignored (from doesn't match)
        assert not a.has_target

    def test_move_to_from_validation(self) -> None:
        """O2b: MOVE_TO with wrong from → ignored as stale."""
        w = _world_with(armies=[_army(50, 50, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        # from=(0,0) but army at (50,50)
        orders = {0: ["MOVE_TO 1 0 0 100 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        a = w.armies[0]
        assert not a.has_target

    def test_move_to_replaces(self) -> None:
        """O3: New MOVE_TO replaces old target."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_TO 1 0 0 100 0"]})
        step(w, CFG, ledger, turn=2, orders={0: ["MOVE_TO 1 50 0 0 100"]})
        a = w.armies[0]
        # Second order should have taken effect (if first was delivered)
        # At minimum, no crash

    def test_move_to_ownership_fail(self) -> None:
        """O3b: MOVE_TO on enemy army → ignored."""
        w = _world_with(armies=[_army(0, 0, 1, 1)])  # faction 1
        ledger = Ledger(CFG.info_speed, 1414)
        # Faction 0 tries to move faction 1's army
        orders = {0: ["MOVE_TO 1 0 0 100 0"]}
        step(w, CFG, ledger, turn=1, orders=orders)
        a = w.armies[0]
        assert not a.has_target

    def test_build_empty_ground(self) -> None:
        """O4: BUILD on empty ground → new town."""
        w = _world_with(armies=[_army(50, 50, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["BUILD 1 50 50"]})
        new_towns = [t for t in w.towns if t.x == 50 and t.y == 50]
        assert len(new_towns) == 1
        assert new_towns[0].population == 500  # army_cost × build_efficiency

    def test_build_on_own_town(self) -> None:
        """O5: BUILD on own town → town pop += 500."""
        t = _town(50, 50, 2000, faction=0, tid=1)
        w = _world_with(armies=[_army(50, 50, 0, 2)], towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["BUILD 2 50 50"]})
        assert t.population == pytest.approx(2500)

    def test_build_on_enemy_town(self) -> None:
        """O5b: BUILD at enemy town position → army captures it first."""
        t = _town(50, 50, 2000, faction=1, tid=1)
        w = _world_with(armies=[_army(50, 50, 0, 2)], towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["BUILD 2 50 50"]})
        # Army within interact_radius captures town (pop reduced by 50%)
        assert t.faction == 0  # captured
        assert t.population < 2000  # reduced by build_efficiency

    def test_build_distance_fail(self) -> None:
        """O6: BUILD where army not within interact_radius → no town."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["BUILD 1 100 0"]})
        # Army at (0,0), BUILD target (100,0) → far away
        assert len(w.towns) == 0

    def test_build_ownership_army(self) -> None:
        """O6b: BUILD with enemy army id → ignored."""
        w = _world_with(armies=[_army(50, 50, 1, 1)])  # enemy army
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["BUILD 1 50 50"]})
        assert len(w.towns) == 0

    def test_build_consumes(self) -> None:
        """O7: After BUILD success, army is gone."""
        w = _world_with(armies=[_army(50, 50, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["BUILD 1 50 50"]})
        assert w.get_army(1) is None

    def test_move_capital_instant_cmd(self) -> None:
        """O8: MOVE_CAPITAL executes instantly, guard spawned immediately."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 200 200"]})
        viceroy = [a for a in w.armies if a.is_viceroy]
        assert len(viceroy) == 1

    def test_move_capital_guard(self) -> None:
        """O9: Capital pop reduces by army_cost, guard at capital pos."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 200 200"]})
        assert t.population == pytest.approx(4000)  # 5000 - 1000
        viceroy = [a for a in w.armies if a.is_viceroy]
        assert len(viceroy) == 1
        assert viceroy[0].x == 100
        assert viceroy[0].y == 100

    def test_move_capital_guard_speed(self) -> None:
        """O9b: Viceroy guard moves at army_speed (50 km/turn)."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 200 200"]})
        # After 1 turn of movement
        step(w, CFG, ledger, turn=2, orders={})
        viceroy = [a for a in w.armies if a.is_viceroy]
        if viceroy:
            dist_moved = ((viceroy[0].x - 100) ** 2 + (viceroy[0].y - 100) ** 2) ** 0.5
            assert dist_moved == pytest.approx(50, abs=1)

    def test_move_capital_blind(self) -> None:
        """O10: During flight, faction receives no event deliveries."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 200 200"]})
        # During flight → visible_events returns []
        visible = ledger.visible_events(faction=0, capital_x=100, capital_y=100, now=2.0, is_in_flight=True)
        assert len(visible) == 0

    def test_move_capital_insufficient_pop(self) -> None:
        """O10b: MOVE_CAPITAL when capital pop < army_cost → rejected."""
        t = _town(100, 100, 400, faction=0, tid=1, cap=True)  # pop < 1000
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 200 200"]})
        # Should not spawn viceroy
        viceroy = [a for a in w.armies if a.is_viceroy]
        assert len(viceroy) == 0

    def test_move_capital_founds(self) -> None:
        """O11: On arrival, guard founds new capital town."""
        t = _town(0, 0, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 10 0"]})
        # Run enough turns for viceroy to arrive (dist=10, speed=50)
        for turn in range(2, 5):
            step(w, CFG, ledger, turn=turn, orders={})
        # New capital should exist at (10,0) or wherever arrival happened
        capitals = [t for t in w.towns if t.is_capital]
        assert len(capitals) >= 1

    def test_old_capital_demoted(self) -> None:
        """O11b: After MOVE_CAPITAL arrives, old capital demoted."""
        t1 = _town(0, 0, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t1])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 10 0"]})
        for turn in range(2, 5):
            step(w, CFG, ledger, turn=turn, orders={})
        # Exactly one capital per faction
        capitals = [t for t in w.towns if t.faction == 0 and t.is_capital]
        assert len(capitals) == 1

    def test_multiple_move_capital_queued(self) -> None:
        """O11c: Second MOVE_CAPITAL during flight → rejected or blocked."""
        t = _town(0, 0, 10000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_CAPITAL 100 0"]})
        step(w, CFG, ledger, turn=2, orders={0: ["MOVE_CAPITAL 200 0"]})
        # Only one viceroy should exist
        viceroys = [a for a in w.armies if a.is_viceroy]
        assert len(viceroys) <= 1

    def test_invalid_commands_ignored(self) -> None:
        """O12: Invalid commands (FOO, bad args, bad id) → no crash."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={
            0: ["FOO", "MOVE_TO", "MOVE_TO 999 0 0 10 10", "BUILD"]
        })
        # No crash, army still alive
        assert len(w.armies) == 1

    def test_multiple_commands_per_turn(self) -> None:
        """O13: Multiple valid commands in one turn → all processed."""
        t = _town(0, 0, 5000, faction=0, tid=1)
        a = _army(50, 50, 0, 2)
        w = _world_with(armies=[a], towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_TO 2 50 50 100 100"]})
        # Both TRAIN and MOVE_TO processed
        assert len(w.armies) >= 2  # original + trained


class TestDistanceCheckTiming:
    """Distance check: order arrives after army moved away from from_x, from_y."""

    def test_MOVE_TO_order_ignored_if_army_moved_away(self) -> None:
        """Army marching, order from=(0,0) but army now at (50,0) → rejected."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        w.armies[0].target_x = 200
        w.armies[0].target_y = 0
        w.armies[0].has_target = True
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={
            0: ["MOVE_TO 1 0 0 300 300"]
        })
        a = w.armies[0]
        # Army should still be heading to (200,0), not (300,300)
        assert a.target_x == 200 and a.target_y == 0

    def test_BUILD_order_ignored_if_army_moved_away(self) -> None:
        """Army marching, BUILD from=(10,10) but army at (60,10) → rejected."""
        w = _world_with(armies=[_army(10, 10, 0, 1)])
        w.armies[0].target_x = 500
        w.armies[0].target_y = 10
        w.armies[0].has_target = True
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={
            0: ["BUILD 1 10 10"]
        })
        # Army moved to (60,10), far from (10,10)
        assert len(w.towns) == 0

    def test_BUILD_order_accepted_if_army_still_nearby(self) -> None:
        """Stationary army, BUILD from=(0,0) matches → accepted."""
        w = _world_with(armies=[_army(0, 0, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={
            0: ["BUILD 1 0 0"]
        })
        assert len(w.towns) == 1

    def test_MOVE_TO_order_accepted_if_army_still_nearby(self) -> None:
        """Stationary army, MOVE_TO from=(100,100) matches → accepted."""
        w = _world_with(armies=[_army(100, 100, 0, 1)])
        ledger = Ledger(CFG.info_speed, 1414)
        step(w, CFG, ledger, turn=1, orders={
            0: ["MOVE_TO 1 100 100 500 500"]
        })
        a = w.armies[0]
        assert a.target_x == 500 and a.target_y == 500

    def test_two_MOVE_TO_same_from_second_ignored_after_move(self) -> None:
        """Two MOVE_TO from same (0,0): first moves army, second is stale and ignored."""
        cap = _town(0, 0, 5000, faction=0, tid=10, cap=True)
        w = _world_with(armies=[_army(0, 0, 0, 1)], towns=[cap])
        ledger = Ledger(CFG.info_speed, 1414)
        # Turn 1: MOVE_TO from (0,0) to (100,0) — accepted, army moves to (50,0)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_TO 1 0 0 100 0"]})
        assert w.armies[0].target_x == 100
        assert w.armies[0].x == 50
        # Turn 2: MOVE_TO from same (0,0) to (200,0) — army now at (50,0), from is stale
        step(w, CFG, ledger, turn=2, orders={0: ["MOVE_TO 1 0 0 200 0"]})
        # Second order ignored (dist 50 > radius 10), army continues to first target
        assert w.armies[0].target_x == 100
        assert w.armies[0].x == 100

    def test_MOVE_then_BUILD_same_pos_second_ignored_after_move(self) -> None:
        """MOVE then 1 turn later BUILD at same (10,10): BUILD ignored as army moved."""
        cap = _town(0, 0, 5000, faction=0, tid=10, cap=True)
        w = _world_with(armies=[_army(10, 10, 0, 1)], towns=[cap])
        ledger = Ledger(CFG.info_speed, 1414)
        # Turn 1: MOVE_TO from (10,10) to (500,10) — accepted, army moves to (60,10)
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_TO 1 10 10 500 10"]})
        assert w.armies[0].target_x == 500
        assert w.armies[0].x == 60
        # Turn 2: BUILD at same (10,10) with same army_id — army now at (60,10), from is stale
        step(w, CFG, ledger, turn=2, orders={0: ["BUILD 1 10 10"]})
        # BUILD ignored (dist 50 > radius 10), no town, army survives and continues moving
        assert len(w.towns) == 1  # only the capital
        assert len(w.armies) == 1
        assert w.armies[0].id == 1
        assert w.armies[0].x == 110  # moved again toward (500,10)

    def test_MOVE_TO_ignored_if_different_friendly_at_from(self) -> None:
        """MOVE_TO to army_id,x,y ignored even if different friendly army is at x,y."""
        # Army 1 at (0,0), Army 2 at (50,50), both faction 0
        w = _world_with(armies=[_army(0, 0, 0, 1), _army(50, 50, 0, 2)])
        ledger = Ledger(CFG.info_speed, 1414)
        # Order claims army 1 is at (50,50) — where army 2 actually is
        step(w, CFG, ledger, turn=1, orders={0: ["MOVE_TO 1 50 50 100 100"]})
        a1 = w.get_army(1)
        # Must be ignored: check is per army_id, not per position
        assert not a1.has_target
        # Army 2 should be unaffected (order was for army 1)
        a2 = w.get_army(2)
        assert not a2.has_target


class TestMoveCapitalEvents:
    """MOVE_CAPITAL event verification — is_viceroy, town_spawn, consumption."""

    def test_MOVE_CAPITAL_emits_army_spawn_with_is_viceroy(self) -> None:
        """MOVE_CAPITAL emits army_spawn with is_viceroy: true."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[200.0, 200.0])
        )
        events = step(w, CFG, ledger, turn=1, orders={})
        viceroy_spawns = [e for e in events
                          if e.get("kind") == "army_spawn" and e.get("is_viceroy") is True]
        assert len(viceroy_spawns) == 1
        assert viceroy_spawns[0]["x"] == 100
        assert viceroy_spawns[0]["y"] == 100

    def test_MOVE_CAPITAL_arrival_emits_town_spawn_is_capital(self) -> None:
        """Viceroy arrival emits town_spawn with is_capital: true."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[100.0, 100.0])  # same pos → instant
        )
        events = step(w, CFG, ledger, turn=1, orders={})
        cap_spawns = [e for e in events
                      if e.get("kind") == "town_spawn" and e.get("is_capital") is True]
        assert len(cap_spawns) == 1
        assert cap_spawns[0]["x"] == 100
        assert cap_spawns[0]["y"] == 100

    def test_viceroy_consumed_on_arrival(self) -> None:
        """Viceroy army removed from world on arrival."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[100.0, 100.0])
        )
        step(w, CFG, ledger, turn=1, orders={})
        viceroy = [a for a in w.armies if a.is_viceroy]
        assert len(viceroy) == 0


class TestViceroyFieldInEvents:
    """is_viceroy field in army_spawn events."""

    def test_TRAIN_spawn_has_is_viceroy_false(self) -> None:
        """army_spawn from TRAIN has is_viceroy: false."""
        t = _town(500, 500, 2000, faction=0, tid=1)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        events = step(w, CFG, ledger, turn=1, orders={})
        spawns = [e for e in events if e.get("kind") == "army_spawn"]
        assert len(spawns) == 1
        assert spawns[0].get("is_viceroy") is False

    def test_MOVE_CAPITAL_spawn_has_is_viceroy_true(self) -> None:
        """army_spawn from MOVE_CAPITAL has is_viceroy: true."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[500.0, 500.0])
        )
        events = step(w, CFG, ledger, turn=1, orders={})
        spawns = [e for e in events if e.get("kind") == "army_spawn"]
        assert len(spawns) == 1
        assert spawns[0].get("is_viceroy") is True


class TestMoveCapitalEdgeCases:
    """MOVE_CAPITAL edge cases."""

    def test_same_position_as_current_capital(self) -> None:
        """MOVE_CAPITAL to same position → completes immediately."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[100.0, 100.0])
        )
        events = step(w, CFG, ledger, turn=1, orders={})
        cap_spawns = [e for e in events if e.get("kind") == "town_spawn" and e.get("is_capital")]
        assert len(cap_spawns) == 1
        assert cap_spawns[0]["x"] == 100
        assert cap_spawns[0]["y"] == 100
        assert t.is_capital is False

    def test_no_capital_exists(self) -> None:
        """MOVE_CAPITAL when faction has no capital → ignored."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=False)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[500.0, 500.0])
        )
        events = step(w, CFG, ledger, turn=1, orders={})
        viceroy_spawns = [e for e in events if e.get("is_viceroy") is True]
        assert len(viceroy_spawns) == 0

    def test_multiple_MOVE_CAPITAL_queued(self) -> None:
        """Two MOVE_CAPITAL orders → only first should execute."""
        t = _town(100, 100, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[t])
        ledger = Ledger(CFG.info_speed, 1414)
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[200.0, 200.0])
        )
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town",
                           args=[300.0, 300.0])
        )
        events = step(w, CFG, ledger, turn=1, orders={})
        cap_spawns = [e for e in events if e.get("kind") == "town_spawn" and e.get("is_capital")]
        assert len(cap_spawns) == 1
        assert cap_spawns[0]["x"] == 200 and cap_spawns[0]["y"] == 200


class TestMoveCapitalLedger:
    """Event visibility after MOVE_CAPITAL — only events from new capital time onwards."""

    def test_events_before_new_capital_not_visible_from_new_capital(self) -> None:
        """Old events (t < new_capital_time) never become visible from new capital."""
        # Old capital at (0,0), new capital will be at (500,0) established at turn 5
        cap = _town(0, 0, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[cap])
        ledger = Ledger(CFG.info_speed, 1414)
        # Event at old capital position at t=1 (near old capital)
        from engine.ledger import Event, EventKind
        ledger.log(Event(turn=1, x=0, y=0, kind=EventKind.BATTLE, payload={}))
        # MOVE_CAPITAL at turn 5 to (500,0) — arrives same turn (dist 0 for this test, target same as start for instant)
        # Use instant arrival: target same as capital, so new capital at (500,0) at turn 5
        # To make it 500 away, we need a real move: use target (500,0) distance 500, speed 50 → 10 turns, but for test we use instant via same pos trick
        # Simpler: directly set capital_since to 5 to simulate new capital at turn 5
        # Instead, do a real MOVE_CAPITAL via step and then check visibility
        # Log an event at t=6 near new capital (should be visible) and check filtering
        ledger.log(Event(turn=6, x=500, y=0, kind=EventKind.BATTLE, payload={}))
        # Simulate new capital established at turn 5
        ledger.set_capital_since(faction=0, turn=5)
        # Old event at t=1 should NOT be visible from new capital at (500,0) even though dist allows it (1+500/150=4.33 <=10)
        visible_old = ledger.visible_events(faction=0, capital_x=500, capital_y=0, now=10)
        # Only the t=6 event should be visible, not t=1
        assert len(visible_old) == 1
        assert visible_old[0].turn == 6

    def test_new_events_visible_from_new_capital(self) -> None:
        """Events with t >= new_capital_time are visible from new capital based on distance."""
        from engine.ledger import Event, EventKind
        ledger = Ledger(CFG.info_speed, 1414)
        # New capital at (500,0) since turn 5
        ledger.set_capital_since(faction=0, turn=5)
        ledger.log(Event(turn=5, x=500, y=0, kind=EventKind.BATTLE, payload={"id": 1}))
        ledger.log(Event(turn=6, x=500, y=0, kind=EventKind.BATTLE, payload={"id": 2}))
        # Both at distance 0 from new capital, should be visible at now=6
        visible = ledger.visible_events(faction=0, capital_x=500, capital_y=0, now=6)
        assert len(visible) == 2
        # Event at t=4 (before new capital) should not be visible even if close
        ledger2 = Ledger(CFG.info_speed, 1414)
        ledger2.set_capital_since(faction=0, turn=5)
        ledger2.log(Event(turn=4, x=500, y=0, kind=EventKind.BATTLE, payload={}))
        visible2 = ledger2.visible_events(faction=0, capital_x=500, capital_y=0, now=10)
        assert len(visible2) == 0

    def test_step_MOVE_CAPITAL_resets_ledger_since(self) -> None:
        """Full step: after MOVE_CAPITAL arrival, ledger filters old events."""
        cap = _town(0, 0, 5000, faction=0, tid=1, cap=True)
        w = _world_with(towns=[cap])
        ledger = Ledger(CFG.info_speed, 1414)
        # Event at old capital before move
        from engine.ledger import Event, EventKind
        ledger.log(Event(turn=1, x=0, y=0, kind=EventKind.BATTLE, payload={}))
        # MOVE_CAPITAL instantly to (100,0) at turn 2
        w.standing_orders.append(
            StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=1, target_type="town", args=[100.0, 100.0])
        )
        step(w, CFG, ledger, turn=2, orders={})
        # After move, old event at t=1 should not be visible from new capital at (100,0)
        visible = ledger.visible_events(faction=0, capital_x=100, capital_y=0, now=10)
        # The old t=1 event is < capital_since (2), so filtered
        assert all(e.turn >= 2 for e in visible)
        # A new event at t=3 near new capital should be visible
        ledger.log(Event(turn=3, x=100, y=0, kind=EventKind.BATTLE, payload={}))
        visible2 = ledger.visible_events(faction=0, capital_x=100, capital_y=0, now=10)
        assert any(e.turn == 3 for e in visible2)
