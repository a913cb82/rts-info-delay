"""Overmatch margin: needs include +2 mass beyond S+W+1."""
from engine.config import GameConfig
from bots.aggressive.intel import BotState
from bots.aggressive.raid import raid_targets

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


def test_need_has_overmatch_margin():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 800, 500, 1, 8000, False)],
          armies=[(10, 500, 500, 0)])
    r = raid_targets(b, CFG, 1)
    assert r is not None
    # S=0, W=min(6.5,6)=6 (printer grace), base 0+6+1=7, margin +2,
    # latency 300//300=1, remuster printer +1 => 11
    assert r[0][1] == 11, f"need {r[0][1]}, expected 11"
