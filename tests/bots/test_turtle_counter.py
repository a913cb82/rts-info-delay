"""Counter-takes: storm debt retaliates next calm (natural force)."""
from engine.config import GameConfig
from bots.turtle.intel import BotState
from bots.turtle.brain import decide_orders

CFG = GameConfig(max_turns=10000)


def _bot():
    b = BotState()
    b.init(CFG, 3)
    return b


def _feed(b, turn, towns=(), armies=()):
    evs = [{"kind": "town_update", "id": t[0], "x": t[1], "y": t[2],
            "faction": t[3], "population": t[4], "is_capital": t[5]}
           for t in towns]
    evs += [{"kind": "army_update", "id": a[0], "x": a[1], "y": a[2],
             "faction": a[3], "alive": True, "is_viceroy": False}
            for a in armies]
    b.update(turn, evs)


def test_storm_debt_retaliates_next_calm():
    b = _bot()
    own = [(1, 500, 500, 3, 30000, True)]
    foe = [(2, 100, 100, 1, 6000, False)]
    guards = [(10 + i, 500, 500, 3) for i in range(6)]
    # storm: foe army inbound (threatened, owes retaliation)
    _feed(b, 5000, towns=own + foe,
          armies=guards + [(90, 560, 500, 1)])
    decide_orders(b, CFG)
    assert getattr(b, "_retaliate_owed", False) is True
    # calm: foe gone (repelled), empty viable spaced foe town -> retaliate
    # (field army away retaliates; home guards stay via positional filter)
    _feed(b, 5010, towns=own + foe, armies=guards +
          [(11 + i, 300, 300, 3) for i in range(6)])
    out = decide_orders(b, CFG)
    takes = [o for o in out if "100.0 100.0" in o]
    assert takes, f"storm debt should retaliate: {out}"


def test_no_debt_no_take():
    b = _bot()
    _feed(b, 5000, towns=[(1, 500, 500, 3, 30000, True),
                          (2, 100, 100, 1, 6000, False)],
          armies=[(10 + i, 500, 500, 3) for i in range(6)])
    out = decide_orders(b, CFG)
    takes = [o for o in out if "100.0 100.0" in o]
    assert not takes, f"no storm, no retaliation: {takes}"
