"""Surplus-takes: calm leftovers march fresh-empty viable spaced towns."""
from engine.config import GameConfig
from bots.turtle.intel import BotState
from bots.turtle.brain import decide_orders

CFG = GameConfig(max_turns=10000)


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


def test_calm_surplus_takes():
    b = _bot()
    _feed(b, 7000, towns=[(1, 500, 500, 3, 30000, True),
                          (2, 100, 100, 1, 8000, False)],
          armies=[(10 + i, 500, 500, 3) for i in range(8)])
    out = decide_orders(b, CFG)
    takes = [o for o in out if "100.0 100.0" in o]
    assert takes, f"calm surplus should take: {out}"
