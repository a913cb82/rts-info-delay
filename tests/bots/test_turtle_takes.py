"""Hybrid takes: calm leftovers march fresh-empty viable spaced towns en masse."""
from engine.config import GameConfig
from bots.turtle.intel import BotState
from bots.turtle.brain import decide_orders

CFG = GameConfig()


def _bot():
    b = BotState()
    b.init(CFG, 3)
    return b


def _feed(b, turn, towns=(), armies=()):
    evs = [{"kind": "town_update", "id": t[0], "x": t[1], "y": t[2],
            "faction": t[3], "population": t[4], "is_capital": t[5]}
           for t in towns]
    evs += [{"kind": "army_update", "id": a[0], "x": a[1], "y": a[2],
             "faction": a[3], "alive": True, "is_viceroy": False}
            for a in armies]
    b.update(turn, evs)


def test_calm_takes_empty_viable_spaced():
    b = _bot()
    _feed(b, 7000, towns=[(1, 500, 500, 3, 30000, True),
                          (2, 100, 100, 1, 8000, False)],
          armies=[(10 + i, 500, 500, 3) for i in range(12)])
    out = decide_orders(b, CFG)
    moves = [o for o in out if o.startswith("MOVE_TO")]
    assert any("100.0 100.0" in m for m in moves), f"takes should march 100,100: {moves}"


def test_threatened_holds_no_takes():
    b = _bot()
    _feed(b, 7000, towns=[(1, 500, 500, 3, 30000, True),
                          (2, 100, 100, 1, 8000, False)],
          armies=[(10 + i, 500, 500, 3) for i in range(12)]
          + [(90, 560, 500, 1)])
    out = decide_orders(b, CFG)
    moves = [o for o in out if o.startswith("MOVE_TO")]
    assert not any("100.0 100.0" in m for m in moves), f"threatened holds: {moves}"
