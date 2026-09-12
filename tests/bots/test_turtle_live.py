"""Live-threat gate: stale ghosts + parked loiterers don't open the chest."""
from engine.config import GameConfig
from bots.turtle.intel import BotState
from bots.turtle.brain import _live_threat

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


def test_fresh_sighting_counts():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True)],
          armies=[(20, 300, 500, 1)])
    assert _live_threat(b, 20, 300, 500, 1) is True


def test_parked_loiterer_silent():
    b = _bot()
    for t in range(100, 110):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)],
              armies=[(20, 300, 500, 1)])
    assert _live_threat(b, 20, 300, 500, 1) is False


def test_mover_counts():
    b = _bot()
    for t in range(100, 106):
        x = 300 + (t - 100) * 50.0
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)],
              armies=[(20, x, 500, 1)])
    assert _live_threat(b, 20, 550, 500, 1) is True


def test_stale_ghost_silent():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True)],
          armies=[(20, 300, 500, 1)])
    for t in range(101, 131):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)])
    assert _live_threat(b, 20, 300, 500, 1) is False


def test_parked_with_mates_counts():
    # parked army WITH a same-faction mate nearby: staging pack, defend
    b = _bot()
    for t in range(100, 110):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)],
              armies=[(20, 300, 500, 1), (21, 320, 500, 1)])
    assert _live_threat(b, 20, 300, 500, 1) is True


def test_factory_counts_parked():
    # foe town printed (>=900 drop): pack factory soon, blanket early
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 900, 900, 1, 8000, False)],
          armies=[(20, 300, 500, 1)])
    for t in range(101, 105):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True),
                           (2, 900, 900, 1, 8000, False)],
              armies=[(20, 300, 500, 1)])
    # town 2 prints at t=105: 8000 -> 6900 (single-update drop 1100 >= 900)
    _feed(b, 105, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 900, 900, 1, 6900, False)],
              armies=[(20, 300, 500, 1)])
    assert _live_threat(b, 20, 300, 500, 1) is True


def test_thin_quiet_keeps_precision():
    # thin foe, steady pop, parked solo: silent
    b = _bot()
    for t in range(100, 110):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True),
                           (2, 900, 900, 1, 8000, False)],
              armies=[(20, 300, 500, 1)])
    assert _live_threat(b, 20, 300, 500, 1) is False
