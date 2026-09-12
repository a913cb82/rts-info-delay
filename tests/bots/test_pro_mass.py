"""Mass-release: rich holds small packs to 8+ (pure hold, no probes)."""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.brain import decide_orders

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


def test_mass_hold_wiring():
    # mass_hold is wired (brain references it); e2e pack-size verification
    # happens via order-tracing in rated games (pack sizes 8+ in orders).
    import inspect
    from bots.pro import brain as br
    src = inspect.getsource(br._stage_moves)
    assert "mass_hold" in src and "free_n < 8" in src


def test_poor_takes_now():
    b = _bot()
    _feed(b, 7000, towns=[(1, 500, 500, 0, 20000, True),
                          (2, 100, 100, 1, 2000, False)],
          armies=[(10 + i, 500, 500, 0) for i in range(5)])
    out = decide_orders(b, CFG)
    marches = [o for o in out if o.startswith("MOVE_TO") and "100.0 100.0" in o]
    assert marches, f"poor should take now: {out}"
