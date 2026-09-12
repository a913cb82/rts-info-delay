"""Savings override: sterile-rich towns assume full muster on raid."""
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


def _own(b, turn):
    _feed(b, turn, towns=[(1, 500, 500, 0, 20000, True)],
          armies=[(10 + i, 500, 500, 0) for i in range(5)])


def test_sterile_rich_assumes_muster():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 800, 500, 1, 8000, False)],
          armies=[(10, 500, 500, 0)])
    # age past grace with zero prints (sterile); town stays 8000
    for t in range(101, 201):
        _own(b, t)
        _feed(b, t, towns=[(2, 800, 500, 1, 8000, False)])
    r = raid_targets(b, CFG, 1)
    assert r is not None
    # printable=(8000-1500)/1000=6.5, arrival=300/50=6 -> W=6, need=0+6+1+1(latency)=8
    assert r[0][1] == 8, f"need {r[0][1]}, expected 8 (full muster, not 0)"


def test_sterile_thin_stays_cheap():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 800, 500, 1, 3000, False)],
          armies=[(10, 500, 500, 0)])
    for t in range(101, 201):
        _own(b, t)
        _feed(b, t, towns=[(2, 800, 500, 1, 3000, False)])
    r = raid_targets(b, CFG, 1)
    assert r is not None
    # printable=1.5 <5: no override; sterile W=0 -> need=0+0+1+1=2
    assert r[0][1] == 2, f"need {r[0][1]}, expected 2"
