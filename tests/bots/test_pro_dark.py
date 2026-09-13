"""Dark-pack port: stale unseen mass vetoes expansion + recalls 2 home."""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.threat import dark_pack
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


def test_dark_pack_counts_stale_only():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 30000, True)],
          armies=[(10, 500, 500, 0), (20, 900, 900, 1)])
    assert dark_pack(b, CFG) == 0  # fresh-visible: inbound owns it
    _feed(b, 110, towns=[(1, 500, 500, 0, 30000, True)],
          armies=[(10, 500, 500, 0)])
    assert dark_pack(b, CFG) == 1  # stale 10t (mass unseen)
    _feed(b, 200, towns=[(1, 500, 500, 0, 30000, True)],
          armies=[(10, 500, 500, 0)])
    assert dark_pack(b, CFG) == 0  # ghost (>30t)


def test_dark_recall_brings_field_armies_home():
    b = _bot()
    _feed(b, 100, towns=[(1, 500, 500, 0, 60000, True),
                         (2, 900, 900, 1, 8000, False)],
          armies=[(10, 500, 500, 0), (11, 200, 200, 0),
                  (20, 900, 900, 1), (21, 910, 900, 1)])
    _feed(b, 110, towns=[(1, 500, 500, 0, 60000, True),
                         (2, 900, 900, 1, 8000, False)],
          armies=[(10, 500, 500, 0), (11, 200, 200, 0)])
    assert dark_pack(b, CFG) == 2
    out = decide_orders(b, CFG)
    homes = [o for o in out if o.startswith("MOVE_TO 11")]
    assert homes, f"field army 11 should recall home: {out}"
