"""Search rank tests (M2): picks clear winners, keeps default on ties/low clock."""
import math

from engine.config import GameConfig
from bots.pro.search import choose_site, rank, site_plans

CFG = GameConfig()


class T:
    def __init__(self, i, x, y, f, pop, cap=False):
        self.id, self.x, self.y, self.faction = i, x, y, f
        self.population, self.is_capital = pop, cap


class P:
    faction = 0

    def __init__(self, i, x, y):
        self.id, self.x, self.y = i, x, y


class W:
    def __init__(self, towns, armies):
        self.towns, self.armies = towns, armies


class S:
    faction = 0
    turn = 100

    def __init__(self, towns, own, foes, clock=100.0):
        self.world = W(towns, own + foes)
        self._own = own
        self.clock_budget_ms = clock

    def own_armies(self):
        return self._own

    def army_target(self, aid):
        return None

    def effort(self, ms):
        if ms is None:
            return "full"
        return "low" if float(ms) < 25 else "full"


def test_rank_picks_clear_site():
    # home + one settler; site A clear, site B crowded by big foe town
    towns = [T(1, 500, 500, 0, 20000, True), T(2, 300, 300, 1, 60000)]
    st = S(towns, [P(10, 500, 500)], [], clock=100.0)
    plans = [((800, 800), {0: {"moves": {10: (800, 800)}}, 10: {"builds": {10: (800, 800)}}}),
             ((350, 350), {0: {"moves": {10: (350, 350)}}, 6: {"builds": {10: (350, 350)}}})]
    assert rank(st, CFG, plans) == 0  # clear beats crowded


def test_rank_margin_keeps_default_on_tie():
    towns = [T(1, 500, 500, 0, 20000, True)]
    st = S(towns, [P(10, 500, 500)], [], clock=100.0)
    plans = [((800, 800), {0: {"moves": {10: (800, 800)}}, 10: {"builds": {10: (800, 800)}}}),
             ((801, 800), {0: {"moves": {10: (801, 800)}}, 10: {"builds": {10: (801, 800)}}})]
    assert rank(st, CFG, plans) == 0  # 1km apart: within margin -> default


def test_choose_site_low_clock_returns_heuristic():
    towns = [T(1, 500, 500, 0, 20000, True)]
    st = S(towns, [P(10, 500, 500)], [], clock=5.0)
    from bots.pro.settle import find_build_sites
    expect = find_build_sites(st, CFG, 500, 500, 160, 300, 11, 10, 3)
    got = choose_site(st, CFG, P(10, 500, 500))
    assert got == (expect[0] if expect else None)


def test_choose_site_unknown_clock_returns_heuristic():
    towns = [T(1, 500, 500, 0, 20000, True)]
    st = S(towns, [P(10, 500, 500)], [], clock=None)
    from bots.pro.settle import find_build_sites
    expect = find_build_sites(st, CFG, 500, 500, 160, 300, 11, 10, 3)
    got = choose_site(st, CFG, P(10, 500, 500))
    assert got == (expect[0] if expect else None)


def test_choose_site_full_clock_returns_member():
    towns = [T(1, 500, 500, 0, 20000, True)]
    st = S(towns, [P(10, 500, 500)], [], clock=100.0)
    from bots.pro.settle import find_build_sites
    expect = find_build_sites(st, CFG, 500, 500, 160, 300, 11, 10, 3)
    got = choose_site(st, CFG, P(10, 500, 500))
    assert got in (expect or [None])
