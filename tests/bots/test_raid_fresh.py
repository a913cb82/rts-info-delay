"""M3 v1 freshness demotion: stale raid targets rank below fresh equals."""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.raid import raid_target

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


def _world(b, turn):
    # own capital + guard, two equal foe towns (A fresh, B to age)
    _feed(b, turn, towns=[(1, 500, 500, 0, 20000, True),
                          (2, 800, 500, 1, 8000, False),
                          (3, 200, 500, 2, 8000, False)],
          armies=[(10, 500, 500, 0)])


def test_fresh_target_beats_stale_equal():
    b = _bot()
    _world(b, 100)
    # age only B (town 3): re-feed everything except town 3 for 60 turns
    for t in range(101, 161):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True),
                           (2, 800, 500, 1, 8000, False)],
              armies=[(10, 500, 500, 0)])
    sel = raid_target(b, CFG, priced=True)
    assert sel is not None
    assert sel[0].id == 2, f"expected fresh town 2, got {sel[0].id}"


def test_both_fresh_picks_either_without_crash():
    b = _bot()
    _world(b, 100)
    sel = raid_target(b, CFG, priced=True)
    assert sel is not None
    assert sel[0].id in (2, 3)
    assert sel[1] >= 1  # need positive


def test_unpriced_branch_runs():
    b = _bot()
    _world(b, 100)
    sel = raid_target(b, CFG, priced=False)
    assert sel is not None
