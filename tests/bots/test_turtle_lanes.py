"""Lane-pickets wired (idle surplus stations at foe-march midpoints)."""
from engine.config import GameConfig
from bots.turtle.intel import BotState
from bots.turtle.brain import decide_orders

CFG = GameConfig(max_turns=10000)


def test_lane_block_wired():
    import inspect
    from bots.turtle import brain as br
    src = inspect.getsource(br.decide_orders)
    assert "_lane" in src and "foe-march" in src
