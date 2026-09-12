"""Picket: capital-nearest idle stations (marches home if away)."""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.brain import decide_orders

CFG = GameConfig()


def _bot():
    b = BotState()
    b.init(CFG, 0)
    return b


def _feed(b, turn, towns=(), armies=()):
    evs = [{"kind": "town_update", "id": t[0], "x": t[1], "y": t[2],
            "faction": t[3], "population": t[4], "is_capital": t[5]}
           for t in towns]
    evs += [{"kind": "army_update", "id": a[0], "x": a[1], "y": a[2],
             "faction": a[3], "alive": True, "is_viceroy": False}
            for a in armies]
    b.update(turn, evs)


def test_picket_marches_home_when_away():
    b = _bot()
    _feed(b, 5000, towns=[(1, 500, 500, 0, 30000, True)],
          armies=[(10, 100, 100, 0), (11, 120, 100, 0)])
    out = decide_orders(b, CFG)
    homes = [o for o in out if o.startswith("MOVE_TO 10 100.0 100.0 500.0 500.0")]
    assert homes, f"away picket should march home: {out}"


def test_picket_holds_when_home():
    b = _bot()
    _feed(b, 5000, towns=[(1, 500, 500, 0, 30000, True)],
          armies=[(10, 500, 500, 0), (11, 510, 500, 0)])
    out = decide_orders(b, CFG)
    moves10 = [o for o in out if o.startswith("MOVE_TO 10 ")]
    assert not moves10, f"home picket should sit: {out}"
