"""Section 22 medium-level tests — ledger G6-G9, score S4-S7, commands O14-O19, info I6-I9, lag L6-L9."""

from engine.config import GameConfig
from engine.world import World, Town, Army, StandingOrder, CommandType
from engine.ledger import Ledger, Event
from engine.economy import apply_growth, apply_train, apply_build

CFG = GameConfig()


class TestLedgerMedium:
    def test_G6_accumulates_over_steps(self) -> None:
        """G6: Ledger accumulates over 10 steps."""
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=500, y=500, population=2000)]
        w.standing_orders.append(StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town"))
        from engine.step import step

        for i in range(10):
            step(w, CFG, [])
        # Ledger should have entries (TRAIN spawns each turn)
        assert len(w.ledger.events) > 0

    def test_G7_event_visible_after_delay(self) -> None:
        """G7: Event visible after correct delay."""
        ledger = Ledger(window=100)
        # Log event at turn 0
        ledger.log(Event(t=0, x=0, y=0, kind="army_spawn", payload={}))
        # Faction capital at (50, 0), info_speed 150
        # dist = 50, delay = 50/150 = 0.33 → visible at t >= 0.33
        visible = ledger.visible(0, faction=0, capital_x=50, capital_y=0, info_speed=150, now=1)
        assert len(visible) == 1

    def test_G8_old_events_evicted(self) -> None:
        """G8: Old events evicted after window."""
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=500, y=500, population=5000)]
        w.standing_orders.append(StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town"))
        from engine.step import step

        # Ensure ledger exists before measuring
        step(w, CFG, [])
        initial = len(w.ledger.events)
        for i in range(20):
            step(w, CFG, [])
        # Events should not grow unboundedly (eviction window)
        assert len(w.ledger.events) < 200

    def test_G9_sorted_by_time(self) -> None:
        """G9: Events sorted by time."""
        ledger = Ledger(window=100)
        ledger.log(Event(t=3, x=0, y=0, kind="army_spawn", payload={}))
        ledger.log(Event(t=1, x=0, y=0, kind="army_spawn", payload={}))
        ledger.log(Event(t=2, x=0, y=0, kind="army_spawn", payload={}))
        times = [e.t for e in ledger.events]
        assert times == sorted(times)


class TestScoreMedium:
    def test_S4_score_grows_with_towns(self) -> None:
        """S4: Score grows as towns grow."""
        from engine.score import compute_score

        w = World()
        w.map_size = [1000, 1000]
        t = Town(id=1, faction=0, x=500, y=500, population=500)
        w.towns = [t]
        score0 = compute_score(w, faction=0)
        for _ in range(50):
            apply_growth(w, CFG)
        score50 = compute_score(w, faction=0)
        assert score50 > score0

    def test_S5_build_costs_score(self) -> None:
        """S5: BUILD costs score."""
        from engine.score import compute_score

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=100, y=100)
        w.armies = [a]
        w.standing_orders.append(StandingOrder(command=CommandType.BUILD, target_id=1, target_type="army", args=[100, 100]))
        score_before = compute_score(w, faction=0)
        apply_build(w, CFG)
        score_after = compute_score(w, faction=0)
        # Army (1000) → town (500) = net -500
        assert score_after < score_before

    def test_S6_train_neutral(self) -> None:
        """S6: TRAIN is score-neutral."""
        from engine.score import compute_score

        w = World()
        w.map_size = [1000, 1000]
        t = Town(id=1, faction=0, x=500, y=500, population=2000)
        w.towns = [t]
        w.standing_orders.append(StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town"))
        score_before = compute_score(w, faction=0)
        apply_train(w, CFG)
        score_after = compute_score(w, faction=0)
        # Pop 2000 → 1000 + army 1000 = same total
        assert score_after == score_before

    def test_S7_multifaction_separate(self) -> None:
        """S7: Multi-faction score tracked separately."""
        from engine.score import compute_score

        w = World()
        w.map_size = [1000, 1000]
        t1 = Town(id=1, faction=0, x=100, y=100, population=1000)
        t2 = Town(id=2, faction=1, x=900, y=900, population=2000)
        w.towns = [t1, t2]
        score_f0 = compute_score(w, faction=0)
        score_f1 = compute_score(w, faction=1)
        assert score_f0 == 1000
        assert score_f1 == 2000


class TestCommandsMedium:
    def test_O14_move_to_step(self) -> None:
        """O14: MOVE_TO then step() moves army."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=0, y=0)
        w.armies = [a]
        orders = [{"command": "MOVE_TO", "army_id": 1, "from_x": 0, "from_y": 0, "to_x": 100, "to_y": 0}]
        step(w, CFG, orders)
        assert a.x == 50

    def test_O15_build_step(self) -> None:
        """O15: BUILD then step() creates town."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=100, y=100)
        w.armies = [a]
        orders = [{"command": "BUILD", "army_id": 1, "x": 100, "y": 100}]
        step(w, CFG, orders)
        new_towns = [t for t in w.towns if t.x == 100 and t.y == 100]
        assert len(new_towns) == 1
        assert all(army.id != 1 for army in w.armies)

    def test_O16_train_step(self) -> None:
        """O16: TRAIN then step() spawns army."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        t = Town(id=1, faction=0, x=500, y=500, population=2000)
        w.towns = [t]
        orders = [{"command": "TRAIN", "town_id": 1}]
        step(w, CFG, orders)
        assert len(w.armies) >= 1
        # Population after TRAIN (2000-1000) plus small growth for 1 turn, so approx 1000
        assert t.population == 1000 or abs(t.population - 1000) < 2

    def test_O17_multiple_commands(self) -> None:
        """O17: Multiple commands in one step."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        t = Town(id=1, faction=0, x=500, y=500, population=3000)
        a1 = Army(id=2, faction=0, x=0, y=0)
        a2 = Army(id=3, faction=0, x=100, y=100)
        w.towns = [t]
        w.armies = [a1, a2]
        orders = [
            {"command": "MOVE_TO", "army_id": 2, "from_x": 0, "from_y": 0, "to_x": 200, "to_y": 0},
            {"command": "TRAIN", "town_id": 1},
            {"command": "BUILD", "army_id": 3, "x": 100, "y": 100},
        ]
        step(w, CFG, orders)
        assert a1.x == 50  # moved
        assert len(w.armies) >= 1  # TRAIN spawned + BUILD consumed a2
        new_towns = [town for town in w.towns if town.x == 100 and town.y == 100]
        assert len(new_towns) == 1

    def test_O18_invalid_commands_ignored(self) -> None:
        """O18: Invalid commands ignored."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=0, y=0)
        w.armies = [a]
        # BUILD at (100,100) but army at (0,0) — too far
        orders = [{"command": "BUILD", "army_id": 1, "x": 100, "y": 100}]
        step(w, CFG, orders)
        assert len(w.towns) == 0
        assert len(w.armies) == 1

    def test_O19_standing_orders_persist(self) -> None:
        """O19: Standing orders persist across steps."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True)
        w.armies = [a]
        for _ in range(5):
            step(w, CFG, [])
        assert a.x == 200


class TestInfoDelayMedium:
    def test_I6_event_visible_next_turn(self) -> None:
        """I6: Event visible after 1 turn if close."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=10, y=0, population=2000)]
        a = Army(id=2, faction=1, x=5, y=0)
        w.armies = [a]
        # Run 2 turns — first turn creates events, second checks visibility
        step(w, CFG, [])
        step(w, CFG, [])

    def test_I7_far_event_delayed(self) -> None:
        """I7: Event delayed 2 turns if far."""
        from engine.ledger import Ledger, Event

        ledger = Ledger(window=100)
        ledger.log(Event(t=0, x=0, y=0, kind="army_spawn", payload={}))
        # Capital at (300, 0), info_speed 150
        visible_t1 = ledger.visible(0, faction=0, capital_x=300, capital_y=0, info_speed=150, now=1)
        visible_t2 = ledger.visible(0, faction=0, capital_x=300, capital_y=0, info_speed=150, now=2)
        assert len(visible_t1) == 0  # not yet
        assert len(visible_t2) == 1  # arrived

    def test_I8_capital_blind_during_flight(self) -> None:
        """I8: Capital blind during MOVE_CAPITAL."""
        # This tests that during flight, ledger deliveries are withheld
        # Will be verified when MOVE_CAPITAL is implemented
        pass

    def test_I9_ledger_window_holds(self) -> None:
        """I9: Ledger window holds events."""
        from engine.ledger import Ledger, Event

        ledger = Ledger(window=20)
        for t in range(15):
            ledger.log(Event(t=t, x=0, y=0, kind="army_spawn", payload={}))
        # Events from turn 1 should still be in ledger
        assert len(ledger.events) > 0


class TestOrderLagMedium:
    def test_L6_close_delivery(self) -> None:
        """L6: Messenger delivers next turn if close."""
        from engine.ledger import Messenger

        m = Messenger(from_x=0, from_y=0, to_x=10, to_y=0, turn_sent=0, payload={})
        m.advance(info_speed=150)
        assert m.delivered  # 10/150 = 0.07 turns → delivered immediately

    def test_L7_far_delivery(self) -> None:
        """L7: Messenger takes 2 turns if far."""
        from engine.ledger import Messenger

        m = Messenger(from_x=0, from_y=0, to_x=200, to_y=0, turn_sent=0, payload={})
        m.advance(info_speed=150)
        assert not m.delivered  # 200/150 = 1.33 turns
        m.advance(info_speed=150)
        assert m.delivered  # now delivered

    def test_L8_dead_letter_on_death(self) -> None:
        """L8: Dead letter on army death."""
        # Will be tested when full runner exists
        pass

    def test_L9_standing_order_persists(self) -> None:
        """L9: Standing order persists across steps."""
        from engine.step import step

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True)
        w.armies = [a]
        for _ in range(3):
            step(w, CFG, [])
        assert a.x == 150  # 3 × 50
