"""Tests for engine/economy — agrarian model, TRAIN, BUILD.

Model (all parameters real-world; see GameConfig):
    Y_i     = (1+boost_i) * min(rural_density*area_i, farm_workers_yield*P_i)
    boost_i = market_premium * mkt/(mkt + P_i)
    mkt_i   = sum_j serv_j * c(d_ij),  serv_j = max(0, P_j - Y_j/sf)
    S_i     = Y_i + imports_i
    B_i     = birth_rate*P_i*S_i/(S_i + h*P_i),  h = birth/death - 1
    D_i     = death_rate*P_i
    out_i   = migration_share*max(0,B-D) + surplus_mobility*max(0,P - Y/sf)
    trade   = greedy nearest-first with caps (conservative)
    migration = origin-budgeted flows, net antisymmetric (conservative)
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from engine.config import GameConfig
from engine.economy import (
    _geo,
    _market_boost,
    _migration,
    _step_core,
    _trade,
    apply_build,
    apply_growth,
    apply_train,
    base_growth,
    check_town_death,
    crowding_net,
    crowding_nets_batch,
    derived,
    interaction_window,
    land_areas,
    nets_for,
)
from engine.world import Army, CommandType, StandingOrder, Town, World

CFG = GameConfig()
NO_MIG = replace(CFG, migration_share=0.0, surplus_mobility=0.0)


def _town(x: float, y: float, pop: float, faction: int = 0, cap: bool = False, tid: int = 0) -> Town:
    return Town(id=tid, faction=faction, x=x, y=y, population=pop, is_capital=cap)


def _world(*towns: Town) -> World:
    w = World()
    w.map_size = [1000, 1000]
    w.towns = list(towns)
    return w


def _geo_xs(*xs: float):
    """Neighbor structure for towns on a line (replaces hand-made D)."""
    towns = [_town(float(x), 0.0, 300.0, tid=k) for k, x in enumerate(xs)]
    return _geo(towns, CFG)


class TestLand:

    def test_lone_area_is_the_ring(self) -> None:
        w = _world(_town(500, 500, 300, tid=1))
        a = land_areas(w.towns, w.map_size, CFG)
        ring = math.pi * CFG.farm_radius_km ** 2
        assert float(a[0]) == pytest.approx(ring, rel=0.03)

    def test_neighbours_share_land(self) -> None:
        w = _world(_town(500, 500, 300, tid=1), _town(503.5, 500, 300, tid=2))
        a = land_areas(w.towns, w.map_size, CFG)
        ring = math.pi * CFG.farm_radius_km ** 2
        assert 0.6 * ring < float(a[0]) < 0.85 * ring
        assert float(a[0]) == pytest.approx(float(a[1]), rel=0.05)

    def test_cached_while_towns_unchanged(self) -> None:
        w = _world(_town(500, 500, 300, tid=1))
        a1 = land_areas(w.towns, w.map_size, CFG)
        a2 = land_areas(w.towns, w.map_size, CFG)
        assert a1 is a2  # same cached array while the town set is unchanged


class TestBirthsDeaths:

    def test_lone_village_grows_slowly(self) -> None:
        g = base_growth(300.0, CFG)
        assert 0 < g < 0.2

    def test_equilibrium_below_flat_capacity(self) -> None:
        """Malthusian equilibrium exists; Von Thunen travel costs put it
        below the flat-ring yield (a lone town cannot work the far ring
        hard enough to feed flat capacity)."""
        y_ring, _pm, _h, _b, _m, _th, _nu = derived(CFG)
        assert base_growth(300.0, CFG) > 0 > base_growth(y_ring, CFG)

    def test_lone_city_declines(self) -> None:
        w = _world(_town(500, 500, 20000.0, tid=1))
        for _ in range(1000):
            apply_growth(w, CFG)
        assert w.towns[0].population < 19000

    def test_floor_removes_tiny_towns(self) -> None:
        w = _world(_town(500, 500, 5.0, tid=1))
        events = apply_growth(w, CFG)
        assert not w.towns
        assert any(e["kind"] == "town_death" for e in events)


class TestTrade:

    def test_conserves_and_caps(self) -> None:
        surplus = np.array([0.0, 100.0])
        deficit = np.array([40.0, 0.0])
        imports, exports = _trade(surplus, deficit, _geo_xs(0.0, 30.0), CFG)
        assert imports[0] == pytest.approx(40.0)
        assert exports[1] == pytest.approx(40.0)
        assert imports.sum() == pytest.approx(exports.sum())

    def test_caps_at_surplus(self) -> None:
        surplus = np.array([0.0, 100.0])
        deficit = np.array([500.0, 0.0])
        imports, exports = _trade(surplus, deficit, _geo_xs(0.0, 30.0), CFG)
        assert imports[0] == pytest.approx(100.0)
        assert exports[1] == pytest.approx(100.0)

    def test_beyond_carting_reach_no_trade(self) -> None:
        surplus = np.array([0.0, 100.0])
        deficit = np.array([40.0, 0.0])
        imports, exports = _trade(surplus, deficit, _geo_xs(0.0, 100.0), CFG)
        assert imports[0] == 0.0 and exports[1] == 0.0

    def test_nearest_served_first(self) -> None:
        surplus = np.array([0.0, 100.0, 100.0])
        deficit = np.array([60.0, 0.0, 0.0])
        imports, exports = _trade(surplus, deficit, _geo_xs(0.0, 10.0, 40.0), CFG)
        assert exports[1] == pytest.approx(60.0)  # nearest seller pays
        assert exports[2] == 0.0


class TestMigration:

    def test_flows_are_conserving(self) -> None:
        pops = np.array([300.0, 2400.0])
        S = np.array([390.0, 2356.0])
        out = np.array([0.1, 0.0])
        net = _migration(pops, S, out,
                         np.array([0.0, 30.0]), np.array([0.0, 0.0]), CFG)
        assert net.sum() == pytest.approx(0.0, abs=1e-12)

    def test_people_move_upward(self) -> None:
        pops = np.array([300.0, 2400.0])
        S = np.array([390.0, 2356.0])
        out = np.array([0.5, 0.0])
        net = _migration(pops, S, out,
                         np.array([0.0, 30.0]), np.array([0.0, 0.0]), CFG)
        assert net[0] < 0 < net[1]

    def test_no_flow_between_equal_towns(self) -> None:
        pops = np.array([300.0, 300.0])
        S = np.array([390.0, 390.0])
        out = np.array([0.5, 0.5])
        assert np.allclose(_migration(pops, S, out,
                                      np.array([0.0, 30.0]),
                                      np.array([0.0, 0.0]), CFG), 0.0)


class TestMarketAccess:

    def test_non_farm_population_provides_services(self) -> None:
        serv = np.array([588.0, 0.0])
        pops = np.array([2400.0, 300.0])
        boost = _market_boost(serv, pops, _geo_xs(0.0, 30.0),
                              CFG, derived(CFG)[1])
        assert boost[1] > 0.02

    def test_no_market_no_boost(self) -> None:
        serv = np.array([0.0, 0.0])
        pops = np.array([300.0, 300.0])
        boost = _market_boost(serv, pops, _geo_xs(0.0, 30.0),
                              CFG, derived(CFG)[1])
        assert np.allclose(boost, 0.0)

    def test_market_yield_reaches_the_village(self) -> None:
        village = _town(500, 500, 300.0, tid=1)
        town = _town(530, 500, 2400.0, tid=2)
        alone, _ = _step_core([village], [1000, 1000], NO_MIG)
        together, _ = _step_core([village, town], [1000, 1000], NO_MIG)
        assert together[0] > alone[0]

    def test_one_turn_is_stateless(self) -> None:
        """Same inputs give same outputs; no priming turn needed."""
        towns = [_town(500, 500, 300.0, tid=1),
                 _town(530, 500, 2400.0, tid=2)]
        first, _ = _step_core(towns, [1000, 1000], CFG)
        second, _ = _step_core(towns, [1000, 1000], CFG)
        assert list(first) == list(second)


class TestWindow:

    def test_full_at_zero(self) -> None:
        assert interaction_window(0.0, CFG) == 1.0

    def test_hard_bound(self) -> None:
        d = CFG.info_speed
        assert interaction_window(d * d, CFG) == 0.0
        assert interaction_window((d + 1) ** 2, CFG) == 0.0

    def test_monotone(self) -> None:
        vals = [interaction_window(d * d, CFG) for d in range(0, 150, 10)]
        assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))


class TestBatch:

    def test_batch_matches_per_town(self) -> None:
        towns = [_town(0, 0, 300, tid=0), _town(30, 0, 2400, tid=1),
                 _town(60, 0, 300, tid=2)]
        batch = nets_for(towns, CFG)
        per = [crowding_net(t, towns, CFG) for t in towns]
        for b, p in zip(batch, per):
            assert b == pytest.approx(p, abs=1e-9)

    def test_equal_towns_do_not_interact(self) -> None:
        # Beyond service reach (60 km) equal towns are fully independent:
        # no shared boost, no trade, no migration between equals.
        # (Within reach they share services through the market boost —
        # that is the agglomeration mechanism, not extraction.)
        towns = [_town(500, 500, 300, tid=0), _town(600, 500, 300, tid=1)]
        total = sum(nets_for(towns, CFG))
        lone, _ = _step_core([_town(500, 500, 300, tid=0)], [1000, 1000], CFG)
        assert total == pytest.approx(2.0 * (lone[0] - 300.0), rel=1e-9)


class TestEconomyCommands:
    """E35+: check_town_death, apply_build, apply_train."""

    def test_town_dies_at_floor(self) -> None:
        assert check_town_death(_town(0, 0, 0.0, tid=0), CFG) is True

    def test_town_survives_above_floor(self) -> None:
        assert check_town_death(_town(0, 0, 20.0, tid=0), CFG) is False

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
        assert t.population == pytest.approx(2000 + 1000 * 0.9)

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
        assert t.population == pytest.approx(2900)
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
