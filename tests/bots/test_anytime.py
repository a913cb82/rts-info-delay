"""Idea 2: anytime decide with staged prefixes (greedy pilot)."""
import time
from bots.common import BotState
from bots import greedy
from engine.config import GameConfig
from engine.world import Town, Army

CFG = GameConfig()


def _rich_state():
    st = BotState()
    st.init(CFG, 0)
    st.deadline = time.time() + 60
    st.world.towns.append(Town(id=0, faction=0, x=100.0, y=100.0, population=30000.0, is_capital=True))
    st.world.towns.append(Town(id=1, faction=0, x=200.0, y=150.0, population=25000.0))
    st.world.towns.append(Town(id=2, faction=1, x=800.0, y=800.0, population=12000.0, is_capital=True))
    st.world.armies.append(Army(id=10, faction=0, x=150.0, y=120.0, target_x=150.0, target_y=120.0, has_target=False))
    st.world.armies.append(Army(id=11, faction=1, x=790.0, y=790.0, target_x=790.0, target_y=790.0, has_target=False))
    st.update(1, [])
    return st


def test_idea2_stages_concatenate_to_full_orders():
    """Idea 2: concatenated stage outputs equal decide_orders output."""
    st = _rich_state()
    stages = greedy.decide_stages(st, CFG)
    assert [name for name, _ in stages] == ["trains", "moves", "builds"]
    flat = [o for _, orders in stages for o in orders]
    st2 = _rich_state()
    assert flat == greedy.decide_orders(st2, CFG)


def test_idea2_prefix_property_under_abort():
    """Idea 2: aborting after stage k keeps exactly the first-k prefix."""
    st = _rich_state()
    stages = greedy.decide_stages(st, CFG)
    trains = stages[0][1]
    # simulate abort right after the trains stage
    st2 = _rich_state()
    st2.deadline = time.time() - 1  # already expired
    partial = greedy.decide_orders(st2, CFG)
    assert partial == trains


def test_idea2_trains_never_dropped_for_raids():
    """Idea 2: stage 0 (trains) is never sacrificed for later stages."""
    st = _rich_state()
    stages = greedy.decide_stages(st, CFG)
    trains = [o for o in stages[0][1] if o.startswith("TRAIN")]
    assert len(trains) >= 1
    assert all(o.startswith("TRAIN") for o in stages[0][1])
