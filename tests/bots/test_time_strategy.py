"""Ideas 4+5+6: quiet-turn skip, plan queue, clock-aware effort."""
import time
from bots.common import BotState
from bots import greedy
from engine.config import GameConfig
from engine.world import Town, Army

CFG = GameConfig()
MILITARY = {"army_spawn", "army_death", "town_spawn", "town_death", "town_capture", "battle"}


def _state():
    st = BotState()
    st.init(CFG, 0)
    st.deadline = time.time() + 60
    st.world.towns.append(Town(id=0, faction=0, x=100.0, y=100.0, population=30000.0, is_capital=True))
    st.world.towns.append(Town(id=1, faction=1, x=800.0, y=800.0, population=12000.0, is_capital=True))
    st.world.armies.append(Army(id=10, faction=0, x=150.0, y=120.0, target_x=150.0, target_y=120.0, has_target=False))
    st.update(1, [])
    return st


def test_idea4_quiet_detection():
    """Idea 4: only military kinds break quiet."""
    st = _state()
    assert st.is_quiet([{"kind": "pop_change", "id": 0, "population": 1.0}]) is True
    assert st.is_quiet([]) is True
    for kind in MILITARY:
        assert st.is_quiet([{"kind": kind, "id": 9, "x": 0.0, "y": 0.0}]) is False


def test_idea4_quiet_turn_replays_standing_orders():
    """Idea 4: quiet turns replay cached orders without running decide."""
    st = _state()
    evts: list = []
    orders1 = st.cached_or_decide(greedy.decide_orders, CFG, evts)
    orders2 = st.cached_or_decide(greedy.decide_orders, CFG, evts)
    assert orders1 == orders2
    assert orders1 == greedy.decide_orders(_state(), CFG)


def test_idea4_military_busts_cache():
    """Idea 4: any military event forces a fresh decide."""
    st = _state()
    st.cached_or_decide(greedy.decide_orders, CFG, [])
    calls = []
    def spy(state, cfg):
        calls.append(1)
        return ["TRAIN 0"]
    out = st.cached_or_decide(spy, CFG, [{"kind": "battle", "x": 1.0, "y": 1.0}])
    assert out == ["TRAIN 0"]
    assert len(calls) == 1


def test_idea5_plan_queue_pops_without_decide():
    """Idea 5: pushed plan issues orders for its lifetime without decide."""
    st = _state()
    st.push_plan(["TRAIN 0", "TRAIN 0"], valid_until_turn=5)
    calls = []
    def spy(state, cfg):
        calls.append(1)
        return ["TRAIN 99"]
    st.turn = 3
    assert st.cached_or_decide(spy, CFG, []) == ["TRAIN 0", "TRAIN 0"]
    assert calls == []


def test_idea5_plan_invalidates_on_new_intel_or_expiry():
    """Idea 5: military intel or expired turn kills the plan."""
    st = _state()
    st.push_plan(["TRAIN 0"], valid_until_turn=5)
    st.turn = 3
    calls = []
    def spy(state, cfg):
        calls.append(1)
        return ["TRAIN 99"]
    assert st.cached_or_decide(spy, CFG, [{"kind": "army_spawn", "id": 5, "faction": 1, "x": 1.0, "y": 1.0}]) == ["TRAIN 99"]
    st.push_plan(["TRAIN 0"], valid_until_turn=5)
    st.turn = 6
    assert st.cached_or_decide(spy, CFG, []) == ["TRAIN 99"]
    assert len(calls) == 2


def test_idea6_effort_thresholds():
    """Idea 6: None -> full, <25 -> low, else full."""
    st = _state()
    assert st.effort(None) == "full"
    assert st.effort(100.0) == "full"
    assert st.effort(25.0) == "full"
    assert st.effort(24.9) == "low"
    assert st.effort(5.0) == "low"


def test_idea6_low_clock_trains_only():
    """Idea 6: low clock issues a safe-only subset (trains) of full orders."""
    st = _state()
    st.clock_budget_ms = 100.0
    full = greedy.decide_orders(st, CFG)
    st2 = _state()
    st2.clock_budget_ms = 5.0
    low = greedy.decide_orders(st2, CFG)
    assert low, "expected at least trains on this rich state"
    assert all(o.startswith("TRAIN") for o in low)
    assert set(low) <= set(full)
