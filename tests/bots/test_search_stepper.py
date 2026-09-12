"""Search stepper tests (M1): engine-exactness + prune invariance + speed."""
import math

from bots.pro.search import make_state, prune, step, score, rollout

CFG = {"army_speed": 50.0, "interact_radius": 10.0, "population_growth": 0.001,
       "population_cap": 100000.0, "death_threshold": 500.0, "army_cost": 1000,
       "build_efficiency": 0.5}


def T(i, x, y, f, pop, cap=False):
    return {"id": i, "x": x, "y": y, "faction": f, "population": pop,
            "is_capital": cap}


def A(i, x, y, f):
    return {"id": i, "x": x, "y": y, "faction": f}


def test_3v1_clean():
    st = make_state([T(1, 0, 0, 0, 5000, True)],
                    [A(10, 0, 0, 0), A(11, 1, 0, 0), A(12, 0, 1, 0), A(20, 2, 0, 1)])
    step(st, CFG)
    assert sorted(st["A"].keys()) == [10, 11, 12]
    assert st["T"][1][2] == 0


def test_1v1_mutual():
    st = make_state([T(1, 500, 500, 0, 5000, True)], [A(10, 0, 0, 0), A(20, 2, 0, 1)])
    step(st, CFG)
    assert st["A"] == {}


def test_guarded_hold():
    st = make_state([T(1, 0, 0, 0, 5000, True)],
                    [A(10, 0, 0, 0), A(11, 1, 1, 0), A(20, 2, 0, 1)])
    step(st, CFG)
    assert 20 not in st["A"]  # raider dies clean
    assert st["T"][1][2] == 0  # town held


def test_standoff_no_take():
    st = make_state([T(1, 0, 0, 0, 5000, True)], [A(20, 2, 0, 1), A(30, -2, 0, 2)])
    step(st, CFG)
    assert st["T"][1][2] == 0


def test_lone_take_halves_and_demotes():
    st = make_state([T(1, 0, 0, 0, 5000, True)], [A(20, 2, 0, 1)])
    step(st, CFG)
    assert 20 in st["A"]  # unopposed taker lives
    assert st["T"][1][2] == 1
    assert st["T"][1][4] is False
    assert abs(st["T"][1][3] - 2500) < 300  # halved + one turn growth


def test_logistic_exact_solo():
    st = make_state([T(1, 0, 0, 0, 10000)], [])
    step(st, CFG)
    assert abs(st["T"][1][3] - (10000 + 0.001 * 10000 * 0.9)) < 1e-6


def test_crowding_taxes():
    st = make_state([T(1, 0, 0, 0, 10000), T(2, 100, 0, 1, 10000)], [])
    step(st, CFG)
    assert st["T"][1][3] < 10000 + 0.001 * 10000 * 0.9  # taxed vs solo


def test_prune_keeps_mine_and_near():
    st = make_state([T(1, 0, 0, 0, 5000, True), T(2, 100, 0, 1, 5000),
                     T(3, 900, 900, 2, 5000)],
                    [A(10, 0, 0, 0), A(20, 100, 0, 1), A(30, 900, 900, 2)])
    p = prune(st, 0)
    assert set(p["T"]) == {1, 2}
    assert set(p["A"]) == {10, 20}


def test_prune_empty_safe():
    st = make_state([T(1, 900, 900, 2, 5000)], [A(30, 900, 900, 2)])
    p = prune(st, 0)
    assert score(p, 0) == -50000.0


def test_score_counts():
    st = make_state([T(1, 0, 0, 0, 5000, True)], [A(10, 0, 0, 0)])
    assert score(st, 0) == 6000.0
