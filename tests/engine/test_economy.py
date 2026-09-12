"""Tests for engine/economy — fitted realism growth model, TRAIN, BUILD.

Growth (config defaults, all 2 s.f.):
    g(P)   = a*P - (a/K)*P^2 - c*P^3
    W(i,j) = alpha*Pi*sig((Pj-Pi)/gate)*e^-(d/rho)^2 * win(d)
           + mu*Pi*Pj/(Pi+Pj)*(Pi-Pj)*e^-(d/rho) * win(d)
    win(d) = sig(D^2/d^2 - D^2/(D^2-d^2)),  D = info_speed = 150 km
"""

from __future__ import annotations

import math

import pytest

from engine.config import GameConfig
from engine.economy import (
    apply_build,
    apply_growth,
    apply_train,
    base_growth,
    check_town_death,
    crowding_net,
    crowding_nets_batch,
    interaction_window,
    pair_gain,
)
from engine.world import Army, CommandType, StandingOrder, Town, World

CFG = GameConfig()  # default config for all economy tests
A = CFG.population_growth
K = CFG.land_capacity
C = CFG.urban_sink
D2 = CFG.info_speed * CFG.info_speed


def _town(x: float, y: float, pop: float, faction: int = 0, cap: bool = False, tid: int = 0) -> Town:
    """Helper: create a Town."""
    return Town(id=tid, faction=faction, x=x, y=y, population=pop, is_capital=cap)


class TestBaseGrowth:
    """E1–E6: Lone-town curve (fertility, saturation, urban sink)."""

    def test_zero_pop(self) -> None:
        assert base_growth(0.0, CFG) == 0.0

    def test_village_slow_and_positive(self) -> None:
        """E1: a 500 village grows ~0.041/turn (~0.43%/yr, historical band)."""
        g = base_growth(500.0, CFG)
        assert g == pytest.approx(0.041, abs=1e-3)
        annual = g / 500 * 52 * 100
        assert 0.1 <= annual <= 0.5

    def test_grows_until_late(self) -> None:
        """E2: 500 / 5k / 20k all still grow."""
        for p in (500.0, 5_000.0, 20_000.0):
            assert base_growth(p, CFG) > 0

    def test_urban_sink(self) -> None:
        """E3: beyond ~78k a lone town shrinks (urban graveyard)."""
        assert base_growth(80_000.0, CFG) < 0
        assert base_growth(120_000.0, CFG) < 0

    def test_peak_location(self) -> None:
        """E4: net growth peaks in the tens of thousands."""
        vals = {p: base_growth(float(p), CFG) for p in range(10_000, 100_001, 5_000)}
        peak = max(vals, key=vals.get)
        assert 20_000 <= peak <= 70_000
        assert vals[peak] > base_growth(10_000.0, CFG)
        assert vals[peak] > base_growth(100_000.0, CFG)

    def test_annualised_village(self) -> None:
        """E5: 52 turns from 500 → ~502 (a year of village growth)."""
        pop = 500.0
        for _ in range(52):
            pop += base_growth(pop, CFG)
        assert pop == pytest.approx(502.1, abs=1.0)

    def test_city_grows_slowly(self) -> None:
        """E6: a 60k town is nearly flat (<0.3%/yr)."""
        annual = base_growth(60_000.0, CFG) / 60_000 * 52 * 100
        assert 0.0 < annual < 0.3


class TestInteractionWindow:
    """E7–E10: the hard-bounded window win(d)."""

    def test_full_at_zero(self) -> None:
        assert interaction_window(0.0, CFG) == 1.0

    def test_hard_bound(self) -> None:
        """E7: d >= 150 km contributes exactly zero."""
        assert interaction_window(D2, CFG) == 0.0
        assert interaction_window(D2 + 1.0, CFG) == 0.0
        assert interaction_window(200 * 200, CFG) == 0.0

    def test_monotone(self) -> None:
        """E8: the window never increases with distance."""
        prev = 1.0
        for d in range(0, 150):
            w = interaction_window(d * d, CFG)
            assert w <= prev + 1e-12
            prev = w

    def test_midrange_shape(self) -> None:
        """E9: meaningful weight at market range, tiny near the bound."""
        assert 0.85 <= interaction_window(75 * 75, CFG) <= 1.0
        assert interaction_window(100 * 100, CFG) < 0.8
        assert interaction_window(148 * 148, CFG) < 1e-2


class TestPairGain:
    """E11–E20: directed pairwise influence (access + migration)."""

    def test_bound_zero(self) -> None:
        """E11: a pair beyond 150 km is inert."""
        assert pair_gain(500.0, 500.0, 160.0 ** 2, CFG) == 0.0

    def test_equal_villages_help(self) -> None:
        """E12: equal neighbours serve each other (access at parity)."""
        assert pair_gain(500.0, 500.0, 25.0, CFG) > 0

    def test_village_gains_from_market(self) -> None:
        """E13: a small village near a market town gains."""
        assert pair_gain(300.0, 2_500.0, 10.0 ** 2, CFG) > 0

    def test_direction_asymmetry(self) -> None:
        """E14: the market lifts the village more than the village lifts the market."""
        up = pair_gain(300.0, 2_500.0, 10.0 ** 2, CFG)
        down = pair_gain(2_500.0, 300.0, 10.0 ** 2, CFG)
        assert up > down

    def test_migration_is_conserving(self) -> None:
        """E15: migration part of a pair sums to zero (access adds growth)."""
        pi, pj, d2 = 300.0, 60_000.0, 30.0 ** 2
        rho = CFG.kernel_scale
        win = interaction_window(d2, CFG)
        mig_ij = (CFG.migration_mu * pi * pj / (pi + pj) * (pi - pj)
                  * math.exp(-math.sqrt(d2) / rho) * win)
        mig_ji = (CFG.migration_mu * pj * pi / (pi + pj) * (pj - pi)
                  * math.exp(-math.sqrt(d2) / rho) * win)
        assert mig_ij + mig_ji == pytest.approx(0.0, abs=1e-12)

    def test_city_shadow(self) -> None:
        """E16: right next to a 60k city a village is drained (pull > access)."""
        village = _town(0, 0, 300, tid=0)
        city = _town(20, 0, 60_000, tid=1)
        net = crowding_net(village, [village, city], CFG)
        assert net < base_growth(300.0, CFG)

    def test_market_halo(self) -> None:
        """E17: near a market the village grows faster than alone."""
        village = _town(0, 0, 300, tid=0)
        market = _town(10, 0, 2_500, tid=1)
        net = crowding_net(village, [village, market], CFG)
        assert net > base_growth(300.0, CFG)


class TestCrowdingNet:
    """E21–E27: per-town and batch net growth."""

    def _net_for(self, a: Town, others: list[Town]) -> float:
        return crowding_net(a, [a] + others, CFG)

    def test_no_neighbours(self) -> None:
        """E21: single town → base growth."""
        a = _town(0, 0, 500, tid=0)
        assert self._net_for(a, []) == pytest.approx(base_growth(500.0, CFG), abs=1e-12)

    def test_far_neighbour_inert(self) -> None:
        """E22: neighbour at 151 km contributes nothing."""
        a = _town(0, 0, 500, tid=0)
        b = _town(151, 0, 500, tid=1)
        assert self._net_for(a, [b]) == pytest.approx(base_growth(500.0, CFG), abs=1e-12)

    def test_near_neighbours_add(self) -> None:
        """E23: two nearby equal villages grow faster than one alone."""
        a = _town(0, 0, 500, tid=0)
        b = _town(12, 0, 500, tid=1)
        c = _town(-12, 0, 500, tid=2)
        assert self._net_for(a, [b, c]) > base_growth(500.0, CFG)

    def test_batch_matches_per_town(self) -> None:
        """E24: batch == per-town path (1e-9)."""
        towns = [
            _town(0, 0, 500, tid=0),
            _town(30, 0, 2_000, tid=1),
            _town(120, 0, 10_000, tid=2),
            _town(300, 0, 500, tid=3),  # out of range
        ]
        batch = crowding_nets_batch(towns, CFG)
        for i, t in enumerate(towns):
            assert batch[i] == pytest.approx(crowding_net(t, towns, CFG), abs=1e-9)

    def test_batch_single(self) -> None:
        towns = [_town(0, 0, 500, tid=0)]
        assert crowding_nets_batch(towns, CFG)[0] == pytest.approx(base_growth(500.0, CFG))

    def test_batch_empty(self) -> None:
        assert crowding_nets_batch([], CFG) == []

    def test_deterministic(self) -> None:
        """E25: repeated evaluation is bit-identical."""
        towns = [_town(0, 0, 500, tid=0), _town(10, 0, 500, tid=1)]
        vals = {tuple(crowding_nets_batch(towns, CFG)) for _ in range(50)}
        assert len(vals) == 1


class TestGrowthApplication:
    """E28–E34: apply_growth semantics."""

    def test_isolated_village_grows(self) -> None:
        t = _town(500, 500, 500, tid=1)
        w = World()
        w.towns.append(t)
        for _ in range(52):
            apply_growth(w, CFG)
        assert 500.5 < t.population < 504

    def test_town_dies_at_zero(self) -> None:
        """E28: a town at exactly the floor (0) dies."""
        t = _town(500, 500, 0.0, tid=1)
        w = World()
        w.towns.append(t)
        apply_growth(w, CFG)
        assert not w.towns

    def test_small_town_survives(self) -> None:
        """E29: a 200 hamlet persists (no 500 floor any more)."""
        t = _town(500, 500, 200, tid=1)
        w = World()
        w.towns.append(t)
        for _ in range(52):
            apply_growth(w, CFG)
        assert w.get_town(1) is not None
        assert t.population > 200

    def test_lone_city_shrinks(self) -> None:
        """E30: a lone 90k city loses population (sink)."""
        t = _town(500, 500, 90_000, tid=1)
        w = World()
        w.towns.append(t)
        for _ in range(52):
            apply_growth(w, CFG)
        assert t.population < 90_000

    def test_villages_feed_the_city(self) -> None:
        """E31: a village ring feeds the city (migration circuit)."""
        for base in (60_000.0, 90_000.0):
            lone = _town(500, 500, base, tid=1)
            wl = World()
            wl.towns.append(lone)
            ringed = _town(500, 500, base, tid=1)
            wr = World()
            wr.towns.append(ringed)
            for i in range(6):
                ang = i * math.pi / 3
                wr.towns.append(_town(500 + 30 * math.cos(ang),
                                      500 + 30 * math.sin(ang), 500, tid=2 + i))
            for _ in range(52):
                apply_growth(wl, CFG)
                apply_growth(wr, CFG)
            assert ringed.population > lone.population

    def test_hamlet_cluster_coexists(self) -> None:
        """E32: five close hamlets coexist (no crowding death spiral)."""
        w = World()
        for i in range(5):
            w.towns.append(_town(100 + i * 5, 100, 500, tid=i))
        for _ in range(100):
            apply_growth(w, CFG)
        assert len(w.towns) == 5


class TestEconomyCommands:
    """E35+: check_town_death, apply_build, apply_train."""

    def test_town_dies_at_floor(self) -> None:
        assert check_town_death(_town(0, 0, 0.0, tid=0), CFG) is True

    def test_town_survives_above_floor(self) -> None:
        assert check_town_death(_town(0, 0, 1.0, tid=0), CFG) is False

    def test_build_empty_ground(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 200])
        )
        events = apply_build(w, CFG)
        assert any(e.get("kind") == "town_spawn" for e in events)

    def test_build_on_town(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=100, y=200, population=2000)
        w.towns.append(t)
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 200])
        )
        apply_build(w, CFG)
        assert t.population == pytest.approx(2000 + 1000 * 0.5)

    def test_build_consumes_army(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 200])
        )
        aid = a.id
        apply_build(w, CFG)
        assert w.get_army(aid) is None

    def test_build_distance_fail(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=0, x=0, y=0)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 0])
        )
        events = apply_build(w, CFG)
        assert not [e for e in events if e.get("kind") == "town_spawn"]
        assert w.get_army(a.id) is not None

    def test_train_reduces_pop(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=2000)
        w.towns.append(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        apply_train(w, CFG)
        assert t.population == pytest.approx(1000)

    def test_train_spawns_at_town(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=2000)
        w.towns.append(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        events = apply_train(w, CFG)
        spawn_events = [e for e in events if e.get("kind") == "army_spawn"]
        assert len(spawn_events) == 1
        assert spawn_events[0]["x"] == 300
        assert spawn_events[0]["y"] == 400

    def test_train_insufficient_pop(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=400)
        w.towns.append(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        events = apply_train(w, CFG)
        assert not [e for e in events if e.get("kind") == "army_spawn"]

    def test_train_standing_order(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=5000)
        w.towns.append(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        for _ in range(3):
            apply_train(w, CFG)
        assert len(w.armies) == 1
        assert len(w.standing_orders) == 0

    def test_train_ownership_check(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=1, x=300, y=400, population=2000)
        w.towns.append(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town", args=[0.0])
        )
        events = apply_train(w, CFG)
        assert not [e for e in events if e.get("kind") == "army_spawn"]

    def test_build_new_town_faction(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=1, x=100, y=200)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 200])
        )
        events = apply_build(w, CFG)
        town_events = [e for e in events if e.get("kind") == "town_spawn"]
        if town_events:
            assert town_events[0]["faction"] == 1

    def test_train_pop_800_dies(self) -> None:
        """TRAIN when pop=800 → pop goes to -200, town dies."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=800)
        w.towns.append(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        apply_train(w, CFG)
        assert all(town.id != tid for town in w.towns)

    def test_build_on_enemy_town(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        enemy_town = Town(id=tid, faction=1, x=100, y=200, population=2000)
        w.towns.append(enemy_town)
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 200])
        )
        events = apply_build(w, CFG)
        assert not [e for e in events if e.get("kind") == "town_spawn"]
        assert enemy_town.population == 2000
        assert w.get_army(a.id) is not None


class TestStandingOrderCleanup:
    """Standing order cleanup on entity death."""

    def test_TRAIN_order_removed_when_town_dies(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        t = Town(id=1, faction=0, x=500, y=500, population=0)
        w.towns.append(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        assert len(w.standing_orders) == 1
        check_town_death(w, CFG)
        assert len(w.standing_orders) == 0

    def test_BUILD_order_removed_when_army_dies(self) -> None:
        from engine.combat import resolve_combat

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=0, y=0)
        enemy = Army(id=2, faction=1, x=3, y=0)
        w.armies = [a, enemy]
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=1, target_type="army",
                           args=[0.0, 0.0])
        )
        resolve_combat(w, CFG)
        assert len(w.armies) == 0
        assert all(so.target_id != 1 for so in w.standing_orders)

    def test_move_orders_removed_when_army_dies(self) -> None:
        from engine.combat import resolve_combat

        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=1, faction=0, x=0, y=0, target_x=500, target_y=0, has_target=True)
        enemy = Army(id=2, faction=1, x=3, y=0)
        w.armies = [a, enemy]
        resolve_combat(w, CFG)
        assert len(w.armies) == 0


class TestBuildBlocked:
    """BUILD onto an enemy town blocks (army waits, order retained)."""

    def _world(self):
        w = World()
        w.map_size = [1000, 1000]
        return w

    def _order(self, w, aid, x, y):
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=aid, target_type="army", args=[x, y]))

    def test_build_on_enemy_town_blocked(self) -> None:
        w = self._world()
        w.towns.append(Town(id=w.allocate_id(), faction=1, x=100, y=200, population=2000))
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        self._order(w, a.id, 100, 200)
        events = apply_build(w, CFG)
        assert not [e for e in events if e.get("kind") == "town_spawn"]
        assert w.get_army(a.id) is not None
        assert w.get_town(0).population == 2000
        assert any(so.command == CommandType.BUILD for so in w.standing_orders)

    def test_blocked_build_fires_after_capture(self) -> None:
        w = self._world()
        t = Town(id=w.allocate_id(), faction=1, x=100, y=200, population=2000)
        w.towns.append(t)
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        self._order(w, a.id, 100, 200)
        apply_build(w, CFG)
        t.faction = 0  # captured by us
        apply_build(w, CFG)
        assert t.population == pytest.approx(2500)
        assert w.get_army(a.id) is None

    def test_blocked_build_founds_after_town_gone(self) -> None:
        w = self._world()
        t = Town(id=w.allocate_id(), faction=1, x=100, y=200, population=2000)
        w.towns.append(t)
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        self._order(w, a.id, 100, 200)
        apply_build(w, CFG)
        assert w.get_town(t.id) is not None
        w.remove_town(t.id)  # starved/destroyed
        events = apply_build(w, CFG)
        assert any(e.get("kind") == "town_spawn" for e in events)
        assert w.get_army(a.id) is None


class TestTrainCap:
    """TRAIN capped at 1 army / town / turn; extras discarded cleanly."""

    def _world(self, pop=5000):
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        w.towns.append(Town(id=tid, faction=0, x=300, y=400, population=pop))
        return w, tid

    def test_second_train_same_turn_discarded(self) -> None:
        w, tid = self._world()
        for _ in range(2):
            w.standing_orders.append(
                StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town"))
        events = apply_train(w, CFG)
        assert len([e for e in events if e.get("kind") == "army_spawn"]) == 1
        assert w.get_town(tid).population == pytest.approx(4000)
        assert not [so for so in w.standing_orders if so.command == CommandType.TRAIN]

    def test_cap_is_per_town(self) -> None:
        w, tid = self._world()
        tid2 = w.allocate_id()
        w.towns.append(Town(id=tid2, faction=0, x=600, y=700, population=5000))
        for t in (tid, tid, tid2):
            w.standing_orders.append(
                StandingOrder(command=CommandType.TRAIN, target_id=t, target_type="town"))
        apply_train(w, CFG)
        assert len(w.armies) == 2
        assert w.get_town(tid).population == pytest.approx(4000)
        assert w.get_town(tid2).population == pytest.approx(4000)

    def test_cap_resets_next_turn(self) -> None:
        w, tid = self._world()
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town"))
        apply_train(w, CFG)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town"))
        apply_train(w, CFG)
        assert len(w.armies) == 2
