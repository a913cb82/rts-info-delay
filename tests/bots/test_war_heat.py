"""Fight-heat siege trigger: fights arm it, quiet loitering doesn't."""
from engine.config import GameConfig
from bots.pro.intel import BotState
from bots.pro.brain import _stage_moves

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
             "faction": a[3], "alive": a[4], "is_viceroy": False}
            for a in armies]
    b.update(turn, evs)


def test_quiet_loiter_never_heats():
    b = _bot()
    for t in range(100, 300):
        # foe loiters at 50km (visible, never in-bubble, never dies)
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)],
              armies=[(10, 500, 500, 0, True), (20, 550, 500, 1, True)])
        _stage_moves(b, CFG)
    assert b._war_heat == 0.0


def test_bubble_fights_heat_and_arm():
    b = _bot()
    for k in range(6):
        t = 100 + k * 10
        # foe enters bubble then dies (my guard kills it clean)
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)],
              armies=[(10, 500, 500, 0, True), (20 + k, 505, 505, 1, True)])
        _stage_moves(b, CFG)
        _feed(b, t + 1, towns=[(1, 500, 500, 0, 20000, True)],
              armies=[(10, 500, 500, 0, True), (20 + k, 505, 505, 1, False)])
        _stage_moves(b, CFG)
    assert b._war_heat >= 5.0


def test_heat_decays_when_quiet():
    b = _bot()
    b._war_heat = 10.0
    for t in range(100, 300):
        _feed(b, t, towns=[(1, 500, 500, 0, 20000, True)])
        _stage_moves(b, CFG)
    assert b._war_heat < 5.0
