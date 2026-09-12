"""Closing+muster siege trigger: hears bloodbaths intel can't count."""
from engine.config import GameConfig
from bots.pro.threat import closing_contacts, mustering_staging, siege_active

CFG = GameConfig()


class T:
    def __init__(s, i, x, y, f, p=5000):
        s.id, s.x, s.y, s.faction, s.population = i, x, y, f, p


class A:
    def __init__(s, i, x, y, f):
        s.id, s.x, s.y, s.faction = i, x, y, f


class W:
    def __init__(s, towns, armies):
        s.towns, s.armies = towns, armies


class S:
    faction = 0
    turn = 3000

    def __init__(s, towns, armies, trails=None, turn=3000):
        s.world = W(towns, armies)
        s._trails = trails or {}
        s.turn = turn

    def own_towns(s):
        return [t for t in s.world.towns if t.faction == 0]


def test_closing_rusher_counts():
    s = S([T(1, 500, 500, 0)], [A(9, 300, 500, 1)],
          trails={9: ((2995, 300.0, 500.0), (3000, 400.0, 500.0))})
    assert closing_contacts(s, CFG) == 1


def test_parked_loiterer_silent():
    s = S([T(1, 500, 500, 0)], [A(9, 300, 500, 1)],
          trails={9: ((2900, 300.0, 500.0), (3000, 300.0, 500.0))})
    assert closing_contacts(s, CFG) == 0


def test_single_point_counts():
    s = S([T(1, 500, 500, 0)], [A(9, 300, 500, 1)], trails={})
    assert closing_contacts(s, CFG) == 1


def test_stale_trail_silent():
    s = S([T(1, 500, 500, 0)], [A(9, 300, 500, 1)],
          trails={9: ((2900, 400.0, 500.0), (2950, 300.0, 500.0))}, turn=3000)
    assert closing_contacts(s, CFG) == 0


def test_mustering_counts():
    s = S([T(1, 500, 500, 0), T(2, 600, 500, 1)],
          [A(9, 650, 500, 1)])
    assert mustering_staging(s, CFG) == 1


def test_quiet_colony_silent():
    s = S([T(1, 500, 500, 0), T(2, 600, 500, 1)], [])
    assert mustering_staging(s, CFG) == 0


def test_garrison_only_silent():
    s = S([T(1, 500, 500, 0), T(2, 600, 500, 1)],
          [A(9, 605, 500, 1)])
    assert mustering_staging(s, CFG) == 0


def test_siege_arms_and_quiets():
    rusher = S([T(1, 500, 500, 0)], [A(9, 300, 500, 1)],
               trails={9: ((2995, 300.0, 500.0), (3000, 400.0, 500.0))})
    assert siege_active(rusher, CFG) is True
    quiet = S([T(1, 500, 500, 0), T(2, 600, 500, 1)], [])
    assert siege_active(quiet, CFG) is False
