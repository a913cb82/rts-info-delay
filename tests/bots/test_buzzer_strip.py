"""Buzzer strip-mine: towns >=60k muster free force late."""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.economy import demand_trains, can_train_standard

CFG = GameConfig(max_turns=10000)


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


def test_strip_mine_fires_in_buzzer():
    b = _bot()
    _feed(b, 9500, towns=[(1, 500, 500, 0, 70000, True),
                         (2, 900, 900, 1, 500, False)])
    out = demand_trains(b, CFG, can_train_standard)
    assert any(o == "TRAIN 1" for o in out), out


def test_no_strip_before_buzzer():
    b = _bot()
    _feed(b, 5000, towns=[(1, 500, 500, 0, 70000, True),
                         (2, 900, 900, 1, 500, False)])
    out = demand_trains(b, CFG, can_train_standard)
    assert not any(o == "TRAIN 1" for o in out), out


def test_growers_keep_compounding_in_buzzer():
    b = _bot()
    _feed(b, 9500, towns=[(1, 500, 500, 0, 30000, True),
                         (2, 900, 900, 1, 500, False)])
    out = demand_trains(b, CFG, can_train_standard)
    assert not any(o == "TRAIN 1" for o in out), out
