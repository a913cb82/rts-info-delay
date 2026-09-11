"""Phase 4 — bot update-language: upsert parser, order-flag amnesia, last_seen."""
import pytest

from engine.config import GameConfig
from bots.common import BotForecast, BotState

CFG = GameConfig()


def _town_update(tid, x, y, faction=0, pop=2000, cap=False):
    return {"kind": "town_update", "id": tid, "x": x, "y": y,
            "faction": faction, "population": pop, "is_capital": cap}


def _army_update(aid, x, y, faction=0, alive=True, viceroy=False):
    return {"kind": "army_update", "id": aid, "x": x, "y": y,
            "faction": faction, "alive": alive, "is_viceroy": viceroy}


def _bot():
    b = BotState()
    b.init(CFG, 0)
    return b


class TestInit:
    def test_init_starts_empty_without_map(self) -> None:
        cfg = GameConfig()
        cfg.map = "100,100,A,5000\n"
        cfg.map_size = [1000, 1000]
        b = BotState()
        b.init(cfg, 0)
        assert b.world.towns == [] and b.world.armies == []

    def test_first_payload_creates_own_capital(self) -> None:
        b = _bot()
        b.update(1, [_town_update(1, 0, 0, faction=0, pop=5000, cap=True)])
        cap = b.world.faction_capital(0)
        assert cap is not None and cap.id == 1


class TestApplyMatrix:
    def test_town_create_and_absolute_update(self) -> None:
        b = _bot()
        b.update(1, [_town_update(2, 100, 0, faction=1, pop=2000, cap=False)])
        t = b.world.get_town(2)
        assert (t.faction, t.population, t.is_capital) == (1, 2000, False)
        b.update(2, [_town_update(2, 100, 0, faction=0, pop=1000, cap=False)])
        t = b.world.get_town(2)
        assert (t.faction, t.population) == (0, 1000)  # takeover applied absolutely

    def test_army_create_and_move(self) -> None:
        b = _bot()
        b.update(1, [_army_update(7, 10, 0)])
        a = b.world.get_army(7)
        assert (a.x, a.y) == (10.0, 0.0)
        b.update(2, [_army_update(7, 60, 0)])
        assert (b.world.get_army(7).x, b.world.get_army(7).y) == (60.0, 0.0)

    def test_town_pop_zero_removes(self) -> None:
        b = _bot()
        b.update(1, [_town_update(2, 100, 0, pop=2000)])
        b.update(2, [_town_update(2, 100, 0, pop=0)])
        assert b.world.get_town(2) is None

    def test_army_not_alive_removes(self) -> None:
        b = _bot()
        b.update(1, [_army_update(7, 10, 0)])
        b.note_move(7, 500, 0)
        b.update(2, [_army_update(7, 10, 0, alive=False)])
        assert b.world.get_army(7) is None
        assert 7 not in b._army_targets  # death clears trackers

    def test_unknown_kind_ignored(self) -> None:
        b = _bot()
        b.update(1, [{"kind": "battle", "x": 0, "y": 0}])
        assert b.world.towns == [] and b.world.armies == []

    def test_unknown_faction_applied(self) -> None:
        b = _bot()
        b.update(1, [_town_update(9, 10, 10, faction=4, pop=100)])
        assert b.world.get_town(9).faction == 4

    def test_old_kinds_ignored(self) -> None:
        # Legacy event shapes (if any ever arrive) are harmless no-ops.
        b = _bot()
        b.update(1, [{"kind": "pop_change", "id": 1, "population": 5},
                     {"kind": "army_spawn", "id": 7, "x": 0, "y": 0},
                     {"kind": "town_capture", "id": 1}])
        assert b.world.towns == [] and b.world.armies == []


class TestLastSeen:
    def test_records_delivery_turn(self) -> None:
        b = _bot()
        b.update(3, [_town_update(2, 100, 0), _army_update(7, 10, 0)])
        assert b._last_seen[("town", 2)] == 3
        assert b._last_seen[("army", 7)] == 3

    def test_never_observed_absent(self) -> None:
        b = _bot()
        b.update(3, [_town_update(2, 100, 0)])
        assert ("town", 99) not in b._last_seen
        assert ("army", 7) not in b._last_seen


class TestAmnesia:
    def _settled(self):
        b = _bot()
        b.update(1, [_town_update(1, 0, 0, faction=0, pop=5000, cap=True),
                     _army_update(7, 10, 0)])
        b.note_move(7, 500, 0)
        b.note_train(1)
        b._plan = (["TRAIN 1"], 10)
        b._standing_orders = (["TRAIN 1"], b._fingerprint())
        return b

    def test_order_then_jump_wipes_everything(self) -> None:
        b = self._settled()
        b.note_orders(["MOVE_CAPITAL 150 100"])
        assert b.evac_ordered is True
        b.update(5, [_town_update(9, 150, 100, faction=0, pop=1000, cap=True)])
        assert b.evac_ordered is False  # consumed by the wipe
        assert {t.id for t in b.world.towns} == {9}
        assert b.world.armies == []
        assert b._army_targets == {}
        assert b._pending_trains == {} and b._pending_builds == {}
        assert b._prev_pop == {} and b.get_growth(9) == 0.0  # fresh batch seeds bookkeeping
        assert b._last_seen == {("town", 9): 5}
        assert b._trails == {}
        assert b._wave_ids == set() and b._wave_hold_until == -1
        assert b._plan is None and b._standing_orders is None
        assert b._cluster_cache is None
        # Config, faction, and turn bookkeeping survive.
        assert b.faction == 0 and b.config is CFG and b.turn == 5

    def test_order_then_sequential_no_wipe(self) -> None:
        b = self._settled()
        b.note_orders(["MOVE_CAPITAL 150 100"])
        b.update(2, [_town_update(1, 0, 0, faction=0, pop=4990, cap=True)])
        assert b.evac_ordered is False  # failure path clears the flag
        assert b.world.get_town(1) is not None  # nothing wiped
        assert 7 in b._army_targets  # trackers survive

    def test_no_order_jump_applies_normally(self) -> None:
        # Fresh process (e.g. first payload): a jump with no flag is not a wipe.
        b = _bot()
        b.update(5, [_town_update(1, 0, 0, faction=0, pop=5000, cap=True)])
        assert b.world.get_town(1) is not None

    def test_note_orders_flags_evac(self) -> None:
        b = _bot()
        b.note_orders(["TRAIN 1", "MOVE_TO 7 10 0 500 0"])
        assert b.evac_ordered is False
        b.note_orders(["MOVE_CAPITAL 150 100"])
        assert b.evac_ordered is True


class TestQuietAndFingerprint:
    def test_empty_is_quiet(self) -> None:
        assert _bot().is_quiet([]) is True

    def test_any_update_breaks_quiet(self) -> None:
        b = _bot()
        assert b.is_quiet([_town_update(1, 0, 0)]) is False
        assert b.is_quiet([_army_update(7, 0, 0)]) is False

    def test_position_change_alone_invalidates(self) -> None:
        b = _bot()
        b.update(1, [_town_update(1, 0, 0, faction=0, pop=5000, cap=True),
                     _army_update(7, 10, 0)])
        fp = b._fingerprint()
        b.update(2, [_army_update(7, 60, 0)])
        assert b._fingerprint() != fp

    def test_same_quantum_pop_keeps_cache(self) -> None:
        b = _bot()
        b.update(1, [_town_update(1, 0, 0, faction=0, pop=5050, cap=True)])
        fp = b._fingerprint()
        b.update(2, [_town_update(1, 0, 0, faction=0, pop=5055, cap=True)])
        assert b._fingerprint() == fp


class TestMigratedMachinery:
    def test_pending_train_confirms_on_pop_drop(self) -> None:
        b = _bot()
        b.update(1, [_town_update(1, 0, 0, faction=0, pop=5000, cap=True)])
        b.note_train(1)
        assert 1 in b._pending_trains
        b.update(2, [_town_update(1, 0, 0, faction=0, pop=1000, cap=True)])
        assert 1 not in b._pending_trains  # own update confirms the train

    def test_wave_watch_fires_on_own_death(self) -> None:
        from bots.common import note_wave_watch
        b = _bot()
        b.update(1, [_town_update(1, 0, 0, faction=0, pop=5000, cap=True),
                     _army_update(7, 10, 0)])
        assert note_wave_watch(b) is False
        b.update(2, [_army_update(7, 10, 0, alive=False)])
        assert note_wave_watch(b) is True  # known own army vanished -> hold

    def test_forecast_projects_velocity(self) -> None:
        b = _bot()
        b.update(1, [_town_update(1, 0, 0, faction=0, pop=5000, cap=True),
                     _army_update(7, 100, 0, faction=1)])
        b.update(2, [_army_update(7, 150, 0, faction=1)])
        fc = BotForecast(b, CFG)
        fx, fy = fc.forecast_army_pos(b.world.get_army(7), turns_ahead=2.0)
        assert (fx, fy) == pytest.approx((250.0, 0.0))

    def test_forecast_stationary_stays(self) -> None:
        b = _bot()
        b.update(1, [_army_update(7, 100, 0, faction=1)])
        b.update(2, [_army_update(7, 100, 0, faction=1)])
        fc = BotForecast(b, CFG)
        assert fc.forecast_army_pos(b.world.get_army(7)) == (100.0, 0.0)


class TestDecideRobustness:
    @pytest.mark.parametrize("mod", ["pro", "greedy", "aggressive", "expander", "turtle"])
    def test_empty_world_decide_returns_list(self, mod) -> None:
        import importlib
        decide = importlib.import_module(f"bots.{mod}").decide_orders
        b = _bot()
        b.update(1, [])
        orders = decide(b, CFG)
        assert isinstance(orders, list)
