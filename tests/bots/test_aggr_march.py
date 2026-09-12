"""March discipline: packs march on fresh-need targets only."""
from engine.config import GameConfig
from bots.aggressive.intel import BotState
from bots.aggressive.brain import _target_fresh

CFG = GameConfig()


class T:
    def __init__(s, i, x, y):
        s.id, s.x, s.y = i, x, y


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


def test_fresh_target_marches():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 800, 500, 1, 8000, False)])
    assert _target_fresh(b, T(2, 800, 500)) is True


def test_stale_target_holds():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 800, 500, 1, 8000, False)])
    for t in range(101, 146):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)])
    assert _target_fresh(b, T(2, 800, 500)) is False


def test_unknown_defaults_march():
    # missing key (shouldn't happen): preserve behavior, don't strand
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True)])
    assert _target_fresh(b, T(99, 800, 500)) is True
