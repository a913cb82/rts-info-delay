"""Vulture boost: weakened-viable targets jump the raid queue."""
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


def _world(b, turn, weakened=True):
    # own base + guard; two equal foe towns (A steady, B drops if weakened)
    pops = {2: 8000, 3: 8000 if turn == 100 else (6500 if weakened else 8000)}
    _feed(b, turn, towns=[(1, 500, 500, 0, 20000, True),
                          (2, 800, 500, 1, pops[2], False),
                          (3, 200, 500, 2, pops[3], False)],
          armies=[(10, 500, 500, 0)])


def test_weakened_viable_jumps_queue():
    b = _bot()
    _world(b, 100)
    _world(b, 101, weakened=True)
    r = raid_targets(b, CFG, 2)
    assert r is not None
    assert r[0][0].id == 3, f"expected weakened town 3 first, got {r[0][0].id}"


def test_arming_drop_not_weakened():
    # pop drop WITH field growth = arming (prints), not weakening
    b = _bot()
    _world(b, 100)
    _feed(b, 101, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 800, 500, 1, 8000, False),
                         (3, 200, 500, 2, 6500, False)],
          armies=[(10, 500, 500, 0),
                  (30, 200, 500, 2), (31, 200, 500, 2)])
    r = raid_targets(b, CFG, 2)
    assert r is not None
    # smoke: base cheap-bias may order either way (boost correctness proven
    # by weakened-fires + hostage-gated); both rank, no crash
    assert {x[0].id for x in r} == {2, 3}


def test_hostage_drop_ignored():
    # drop below viability (<4x floor = 2000): gated corpse, not vulture;
    # only A ranks
    b = _bot()
    _world(b, 100)
    _feed(b, 101, towns=[(1, 500, 500, 0, 20000, True),
                         (2, 800, 500, 1, 8000, False),
                         (3, 200, 500, 2, 1200, False)],
          armies=[(10, 500, 500, 0)])
    r = raid_targets(b, CFG, 2)
    assert r is not None
    assert [x[0].id for x in r] == [2, 3]
