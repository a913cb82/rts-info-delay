"""Beheading-futility evac gate: fires iff capital will fall + flight works."""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.brain import _capital_doomed

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


def test_doomed_fires():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 3000, True)],
          armies=[(20 + i, 650, 500, 1) for i in range(5)])
    assert _capital_doomed(b, CFG) is True


def test_viable_holds():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 3000, True)],
          armies=[(10 + i, 500, 500, 0) for i in range(3)]
          + [(20, 650, 500, 1)])
    assert _capital_doomed(b, CFG) is False


def test_too_late_fights():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 3000, True)],
          armies=[(20 + i, 550, 500, 1) for i in range(5)])
    assert _capital_doomed(b, CFG) is False


def test_poor_cannot_fly():
    # 1400 - 1000 viceroy = 400 < 500 floor: flight kills the town (pointless)
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 1400, True)],
          armies=[(20 + i, 650, 500, 1) for i in range(5)])
    assert _capital_doomed(b, CFG) is False


def test_thin_but_viable_flies():
    # 1500 - 1000 = 500: survives exactly; overmatch must still hold
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 1500, True)],
          armies=[(20 + i, 650, 500, 1) for i in range(5)])
    assert _capital_doomed(b, CFG) is True


def test_quiet_never_evacs():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 3000, True)])
    assert _capital_doomed(b, CFG) is False
