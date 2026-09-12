"""Destination-knowledge gate (intel-quality rule): march into known space.

Home turf (own LOS) and void always pass; near known foe towns passes iff
freshly seen; stale-only turf holds (no blind donations). Recalls (home
turf) and void settlers always pass.
"""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.scout import _dest_known

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


def test_home_turf_passes():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True)])
    assert _dest_known(b, 500, 500) is True
    assert _dest_known(b, 600, 550) is True  # within 150 LOS


def test_void_passes():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True)])
    assert _dest_known(b, 100, 100) is True  # nothing known nearby


def test_fresh_foe_turf_passes():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 700, 700, 1, 5000, False)])
    assert _dest_known(b, 700, 700) is True


def test_stale_foe_turf_holds():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 700, 700, 1, 5000, False)])
    # age the intel: re-feed only own town for 60 turns (foe goes stale)
    for t in range(101, 161):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)])
    assert _dest_known(b, 700, 700) is False
    # home still fine
    assert _dest_known(b, 500, 500) is True
