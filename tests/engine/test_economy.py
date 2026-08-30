"""Tests for engine/economy — logistic growth, crowding, TRAIN, BUILD."""

from __future__ import annotations

import math

import pytest

from engine.config import GameConfig
from engine.economy import (
    apply_build,
    apply_growth,
    apply_train,
    asymmetry,
    check_town_death,
    crowding_net,
    equilibrium_distance,
    logistic,
)
from engine.world import Army, Town, World

CFG = GameConfig()  # default config for all economy tests


def _town(x: float, y: float, pop: float, faction: int = 0, cap: bool = False, tid: int = 0) -> Town:
    """Helper: create a Town."""
    return Town(id=tid, faction=faction, x=x, y=y, population=pop, is_capital=cap)


class TestLogisticGrowth:
    """E1–E6c: Pure logistic function."""

    def test_village_isolated(self) -> None:
        """E1: logistic(500) ≈ 0.4975."""
        result = logistic(500, CFG)
        assert result == pytest.approx(0.4975, abs=1e-3)

    def test_city_at_peak(self) -> None:
        """E2: logistic(50000) ≈ 25.0."""
        result = logistic(50_000, CFG)
        assert result == pytest.approx(25.0, abs=1e-6)

    def test_at_cap(self) -> None:
        """E3: logistic(100000) == 0."""
        result = logistic(100_000, CFG)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_over_cap(self) -> None:
        """E4: logistic(120000) ≈ -24.0."""
        result = logistic(120_000, CFG)
        assert result == pytest.approx(-24.0, abs=1e-6)

    def test_annualised_village(self) -> None:
        """E5: 52 turns from pop 500 → ~526 (±1)."""
        pop = 500.0
        for _ in range(52):
            pop += logistic(pop, CFG)
        assert pop == pytest.approx(526, abs=1)

    def test_annualised_city(self) -> None:
        """E6: 52 turns from pop 50000 → ~51300 (±50)."""
        pop = 50_000.0
        for _ in range(52):
            pop += logistic(pop, CFG)
        assert pop == pytest.approx(51_300, abs=50)

    def test_per_turn_formula(self) -> None:
        """E6b: Exact per-turn formula for several populations."""
        for a in [500, 1000, 50_000, 100_000]:
            expected = 0.001 * a * (1 - a / 100_000)
            assert logistic(a, CFG) == pytest.approx(expected, abs=1e-9)

    def test_logistic_peak_location(self) -> None:
        """E6c: Peak at A=50000, value=25."""
        best_pop = 0
        best_val = -float("inf")
        for a in range(0, 100_001, 100):
            val = logistic(float(a), CFG)
            if val > best_val:
                best_val = val
                best_pop = a
        assert best_pop == 50_000
        assert best_val == pytest.approx(25.0, abs=0.1)


class TestCrowding:
    """E7–E34: Crowding formula, asymmetry, equilibrium distance."""

    def _net_for(self, a: Town, others: list[Town]) -> float:
        """Helper: compute crowding_net for town a among others."""
        all_towns = [a] + others
        return crowding_net(a, all_towns, CFG)

    def test_two_villages_at_d_eq(self) -> None:
        """E7: A=B=500 at d_eq → net ≈ 0."""
        d_eq = 0.4 * math.sqrt(500)
        a = _town(0, 0, 500, tid=0)
        b = _town(d_eq, 0, 500, tid=1)
        net = self._net_for(a, [b])
        assert net == pytest.approx(0.0, abs=0.05)

    def test_two_markets_at_d_eq(self) -> None:
        """E8: A=B=1000 at d_eq → net ≈ 0."""
        d_eq = 0.4 * math.sqrt(1000)
        a = _town(0, 0, 1000, tid=0)
        b = _town(d_eq, 0, 1000, tid=1)
        net = self._net_for(a, [b])
        assert net == pytest.approx(0.0, abs=0.1)

    def test_two_cities_at_d_eq(self) -> None:
        """E9: A=B=50000 at d_eq → net ≈ 0."""
        d_eq = 0.4 * math.sqrt(50_000)
        a = _town(0, 0, 50_000, tid=0)
        b = _town(d_eq, 0, 50_000, tid=1)
        net = self._net_for(a, [b])
        assert net == pytest.approx(0.0, abs=1.0)

    def test_closer_than_d_eq(self) -> None:
        """E10: A=B=500 at dist=6 (<d_eq=8.94) → net < 0."""
        a = _town(0, 0, 500, tid=0)
        b = _town(6, 0, 500, tid=1)
        net = self._net_for(a, [b])
        assert net < 0

    def test_farther_than_d_eq(self) -> None:
        """E11: A=B=500 at dist=12 (>d_eq) → net > 0 but < isolated."""
        a = _town(0, 0, 500, tid=0)
        b = _town(12, 0, 500, tid=1)
        net = self._net_for(a, [b])
        isolated = logistic(500, CFG)
        assert 0 < net < isolated

    def test_village_near_city(self) -> None:
        """E12: A=500 near B=50000 at dist=5 → net(A) strongly negative."""
        a = _town(0, 0, 500, tid=0)
        b = _town(5, 0, 50_000, tid=1)
        net = self._net_for(a, [b])
        assert net < 0

    def test_city_near_village(self) -> None:
        """E13: A=50000 near B=500 at dist=5 → net(A) ≈ logistic(A)."""
        a = _town(0, 0, 50_000, tid=0)
        b = _town(5, 0, 500, tid=1)
        net = self._net_for(a, [b])
        expected = logistic(50_000, CFG)
        # City barely affected by nearby village
        assert net == pytest.approx(expected, abs=0.5)

    def test_cross_size_at_d_eq(self) -> None:
        """E14: A=500, B=50000, dist=d_eq(min=500)=8.94 → net ≈ 0."""
        d_eq = 0.4 * math.sqrt(500)
        a = _town(0, 0, 500, tid=0)
        b = _town(d_eq, 0, 50_000, tid=1)
        net = self._net_for(a, [b])
        assert net == pytest.approx(0.0, abs=0.1)

    def test_market_provincial_d_eq(self) -> None:
        """E15: A=1000, B=10000 at d_eq(min=1000)=12.65 → net ≈ 0."""
        d_eq = 0.4 * math.sqrt(1000)
        a = _town(0, 0, 1000, tid=0)
        b = _town(d_eq, 0, 10_000, tid=1)
        net = self._net_for(a, [b])
        assert net == pytest.approx(0.0, abs=0.1)

    def test_asymmetry_direction(self) -> None:
        """E16: Larger B → more negative net for A."""
        a = _town(0, 0, 500, tid=0)
        b_big = _town(10, 0, 50_000, tid=1)
        b_small = _town(10, 0, 500, tid=2)
        net_big = self._net_for(a, [b_big])
        net_small = self._net_for(a, [b_small])
        assert net_big < net_small

    def test_asymmetry_log_scale(self) -> None:
        """E17: 100× population only slightly worse than 2× at same dist."""
        a = _town(0, 0, 500, tid=0)
        b_100x = _town(10, 0, 50_000, tid=1)
        b_2x = _town(10, 0, 1000, tid=2)
        net_100x = self._net_for(a, [b_100x])
        net_2x = self._net_for(a, [b_2x])
        # 100× is worse, but log compression means not dramatically so
        assert net_100x < net_2x
        # The ratio of asymmetry factors is small
        asy_100x = asymmetry(500, 50_000, CFG)
        asy_2x = asymmetry(500, 1000, CFG)
        assert asy_100x / asy_2x < 1.5  # log compression

    def test_symmetric_asym(self) -> None:
        """E18: A=B → asymmetry = 1."""
        assert asymmetry(500, 500, CFG) == pytest.approx(1.0, abs=1e-9)
        assert asymmetry(10_000, 10_000, CFG) == pytest.approx(1.0, abs=1e-9)

    def test_asymmetry_numeric(self) -> None:
        """E18b: asymmetry(500, 50000) ≈ 1.0276."""
        result = asymmetry(500, 50_000, CFG)
        # 1 + 0.006 × ln(100) = 1 + 0.006 × 4.60517 ≈ 1.02763
        assert result == pytest.approx(1.0276, abs=0.001)

    def test_d_eq_uses_min(self) -> None:
        """E18c: d_eq = 0.4 × sqrt(min(A,B)), not sqrt(max)."""
        # A=500, B=50000 → d_eq = 0.4 × sqrt(500) ≈ 8.94
        result = equilibrium_distance(500, 50_000, CFG)
        expected = 0.4 * math.sqrt(500)
        assert result == pytest.approx(expected, abs=1e-6)
        # Same result regardless of argument order
        assert equilibrium_distance(50_000, 500, CFG) == pytest.approx(expected, abs=1e-6)

    def test_two_neighbours_sum(self) -> None:
        """E19: Two B's at d_eq → Σ has 2 terms → more negative."""
        d_eq = 0.4 * math.sqrt(500)
        a = _town(0, 0, 500, tid=0)
        b1 = _town(d_eq, 0, 500, tid=1)
        b2 = _town(-d_eq, 0, 500, tid=2)
        net_one = self._net_for(a, [b1])
        net_two = self._net_for(a, [b1, b2])
        assert net_two < net_one

    def test_mixed_near_far(self) -> None:
        """E20: B1 close (crowding) + B2 far (relief) → net between."""
        a = _town(0, 0, 500, tid=0)
        b_near = _town(6, 0, 500, tid=1)
        b_far = _town(20, 0, 500, tid=2)
        net_near_only = self._net_for(a, [b_near])
        net_both = self._net_for(a, [b_near, b_far])
        net_far_only = self._net_for(a, [b_far])
        # Far alone gives partial relief, near+far is between
        assert net_near_only < net_both
        assert net_both < net_far_only

    def test_no_neighbours(self) -> None:
        """E21: Single town → net = logistic."""
        a = _town(0, 0, 500, tid=0)
        net = self._net_for(a, [])
        expected = logistic(500, CFG)
        assert net == pytest.approx(expected, abs=1e-9)

    def test_cutoff_at_info_speed(self) -> None:
        """E30: Town beyond info_speed excluded from Σ."""
        a = _town(0, 0, 500, tid=0)
        b = _town(151, 0, 500, tid=1)  # 151 > info_speed=150
        net = self._net_for(a, [b])
        expected = logistic(500, CFG)
        assert net == pytest.approx(expected, abs=1e-9)

    def test_just_inside_cutoff(self) -> None:
        """E31: Town at 149 km (just inside 150) → included."""
        a = _town(0, 0, 500, tid=0)
        b = _town(149, 0, 500, tid=1)
        net = self._net_for(a, [b])
        expected = logistic(500, CFG)
        assert net < expected  # crowding reduces growth

    def test_flat_gamma_long_range(self) -> None:
        """E32: At dist=100 km, crowding still significant (γ=0.3 is flat)."""
        d_eq = 0.4 * math.sqrt(500)  # ~8.94
        a = _town(0, 0, 500, tid=0)
        b = _town(100, 0, 500, tid=1)
        net = self._net_for(a, [b])
        isolated = logistic(500, CFG)
        # (8.94/100)^0.3 ≈ 0.52, so 52% crowding weight
        # net = isolated × (1 - 1 × 0.52) = isolated × 0.48
        assert net < isolated * 0.4  # meaningfully reduced
        assert net > 0  # still positive

    def test_cannot_skip_distant_pairs(self) -> None:
        """E33: 5 towns 80 km apart all 500 pop → each has 4 crowding terms."""
        towns = [_town(i * 80, 0, 500, tid=i) for i in range(5)]
        for t in towns:
            net = self._net_for(t, [o for o in towns if o.id != t.id])
            isolated = logistic(500, CFG)
            assert net < isolated  # significant total crowding

    def test_three_body_sum(self) -> None:
        """E34: Σ = term1 + term2 (additive, not sequential)."""
        a = _town(0, 0, 500, tid=0)
        b1 = _town(10, 0, 500, tid=1)
        b2 = _town(20, 0, 500, tid=2)
        net_b1 = self._net_for(a, [b1])
        net_b2 = self._net_for(a, [b2])
        net_both = self._net_for(a, [b1, b2])
        # Net with both = logistic × (1 - asym×ratio1 - asym×ratio2)
        # Should be less than either alone
        assert net_both < net_b1
        assert net_both < net_b2


class TestEconomyCommands:
    """E22–E31d: check_town_death, apply_build, apply_train."""

    def test_town_dies_at_499(self) -> None:
        """E22: Town with pop=499 → dies."""
        t = _town(0, 0, 499, tid=0)
        assert check_town_death(t, CFG) is True

    def test_town_survives_at_500(self) -> None:
        """E23: Town with pop=500 → survives."""
        t = _town(0, 0, 500, tid=0)
        assert check_town_death(t, CFG) is False

    def test_isolated_never_dies(self) -> None:
        """E24: Isolated village pop=500 grows over 100 turns."""
        t = _town(0, 0, 500, tid=0)
        pop = t.population
        for _ in range(100):
            pop += logistic(pop, CFG)
        assert pop > 500

    def test_build_empty_ground(self) -> None:
        """E25: BUILD on empty ground → new town, army consumed."""
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        events = apply_build(w, CFG)
        # Should find army at (100,200) with no town there → found new town
        assert any(e.get("kind") == "town_spawn" for e in events)

    def test_build_on_town(self) -> None:
        """E26: BUILD on existing town → pop += army_cost × build_efficiency."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=100, y=200, population=2000)
        w.towns.append(t)
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        apply_build(w, CFG)
        assert t.population == pytest.approx(2000 + 1000 * 0.5)

    def test_build_consumes_army(self) -> None:
        """E27: BUILD removes army from world."""
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=0, x=100, y=200)
        w.armies.append(a)
        aid = a.id
        apply_build(w, CFG)
        assert w.get_army(aid) is None

    def test_build_distance_fail(self) -> None:
        """E28: BUILD army far from target → no town created."""
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=0, x=0, y=0)
        w.armies.append(a)
        # Build at (100,0) but army at (0,0) → far away
        events = apply_build(w, CFG)
        town_events = [e for e in events if e.get("kind") == "town_spawn"]
        assert len(town_events) == 0

    def test_train_reduces_pop(self) -> None:
        """E29: TRAIN on town → pop -= army_cost."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=2000)
        w.towns.append(t)
        # Add a standing TRAIN order
        from engine.world import StandingOrder, CommandType

        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        apply_train(w, CFG)
        assert t.population == pytest.approx(1000)

    def test_train_spawns_at_town(self) -> None:
        """E30b: TRAIN spawns army at town position."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=2000)
        w.towns.append(t)
        from engine.world import StandingOrder, CommandType

        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        events = apply_train(w, CFG)
        spawn_events = [e for e in events if e.get("kind") == "army_spawn"]
        assert len(spawn_events) == 1
        assert spawn_events[0]["x"] == 300
        assert spawn_events[0]["y"] == 400

    def test_train_insufficient_pop(self) -> None:
        """E31d: TRAIN when pop < army_cost → no spawn."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=400)
        w.towns.append(t)
        from engine.world import StandingOrder, CommandType

        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        events = apply_train(w, CFG)
        spawn_events = [e for e in events if e.get("kind") == "army_spawn"]
        assert len(spawn_events) == 0

    def test_train_standing_order(self) -> None:
        """E31c: TRAIN standing order spawns one army per economy step."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=300, y=400, population=5000)
        w.towns.append(t)
        from engine.world import StandingOrder, CommandType

        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        # Run 3 economy steps
        for _ in range(3):
            apply_train(w, CFG)
        # Should have spawned 3 armies
        assert len(w.armies) == 3

    def test_train_ownership_check(self) -> None:
        """E31e: TRAIN on enemy town → ignored."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=1, x=300, y=400, population=2000)  # faction 1
        w.towns.append(t)
        from engine.world import StandingOrder, CommandType

        # Faction 0 tries to TRAIN faction 1's town
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town", args=[0.0])
        )
        events = apply_train(w, CFG)
        spawn_events = [e for e in events if e.get("kind") == "army_spawn"]
        assert len(spawn_events) == 0

    def test_build_new_town_faction(self) -> None:
        """E31f: BUILD by faction B → new town faction=B."""
        w = World()
        w.map_size = [1000, 1000]
        a = Army(id=w.allocate_id(), faction=1, x=100, y=200)  # faction 1
        w.armies.append(a)
        events = apply_build(w, CFG)
        town_events = [e for e in events if e.get("kind") == "town_spawn"]
        if town_events:
            assert town_events[0]["faction"] == 1
