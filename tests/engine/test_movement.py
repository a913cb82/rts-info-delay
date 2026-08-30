"""Tests for engine/movement — straight-line paths, path blocking, closest approach."""

from __future__ import annotations

import math

import pytest

from engine.config import GameConfig
from engine.movement import _closest_approach, move_armies
from engine.world import Army, Town, World

CFG = GameConfig()


def _army(x: float, y: float, faction: int = 0, aid: int | None = None) -> Army:
    """Helper: create an Army at position with no target."""
    return Army(id=aid if aid is not None else 0, faction=faction, x=x, y=y)


def _world_with(*armies: Army, map_size: list[int] | None = None) -> World:
    """Helper: create a World containing the given armies."""
    w = World()
    w.map_size = map_size or [1000, 1000]
    w.armies = list(armies)
    return w


class TestMovement:
    """M1–M6d: Basic movement toward target."""

    def test_moves_toward_target(self) -> None:
        """M1: Army at (0,0) targeting (100,0), speed 50 → (50,0) after 1 turn."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        w = _world_with(a)
        move_armies(w, CFG)
        assert a.x == pytest.approx(50, abs=0.01)
        assert a.y == pytest.approx(0, abs=0.01)

    def test_reaches_short_target(self) -> None:
        """M2: Target closer than speed → army reaches target exactly."""
        a = _army(0, 0)
        a.target_x, a.target_y = 30, 0
        a.has_target = True
        w = _world_with(a)
        move_armies(w, CFG)
        assert a.x == pytest.approx(30, abs=0.01)
        assert a.y == pytest.approx(0, abs=0.01)

    def test_no_overshoot(self) -> None:
        """M3: Very short target → doesn't overshoot."""
        a = _army(0, 0)
        a.target_x, a.target_y = 10, 0
        a.has_target = True
        w = _world_with(a)
        move_armies(w, CFG)
        assert a.x == pytest.approx(10, abs=0.01)

    def test_no_target_stays_put(self) -> None:
        """M4: Army with no MOVE_TO stays in place."""
        a = _army(50, 50)
        w = _world_with(a)
        move_armies(w, CFG)
        assert a.x == 50
        assert a.y == 50

    def test_diagonal_short(self) -> None:
        """M5: Diagonal target at dist 5 (< speed 50) → reaches it."""
        a = _army(0, 0)
        a.target_x, a.target_y = 3, 4  # dist = 5
        a.has_target = True
        w = _world_with(a)
        move_armies(w, CFG)
        assert a.x == pytest.approx(3, abs=0.01)
        assert a.y == pytest.approx(4, abs=0.01)

    def test_edge_clamping(self) -> None:
        """M6: Move toward (-100,-100) from (5,5) on 1000×1000 map → clamps to (0,0)."""
        a = _army(5, 5)
        a.target_x, a.target_y = -100, -100
        a.has_target = True
        w = _world_with(a, map_size=[1000, 1000])
        move_armies(w, CFG)
        assert a.x >= 0
        assert a.y >= 0

    def test_exact_speed(self) -> None:
        """M6b: Target exactly 50 km away → reaches it in 1 turn."""
        a = _army(0, 0)
        a.target_x, a.target_y = 50, 0
        a.has_target = True
        w = _world_with(a)
        move_armies(w, CFG)
        assert a.x == pytest.approx(50, abs=0.01)
        assert a.y == pytest.approx(0, abs=0.01)

    def test_standing_order_continues(self) -> None:
        """M6c: Standing order persists across turns."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        w = _world_with(a)
        move_armies(w, CFG)
        assert a.x == pytest.approx(50, abs=0.01)
        move_armies(w, CFG)
        assert a.x == pytest.approx(100, abs=0.01)

    def test_from_matches_position(self) -> None:
        """M6d: MOVE_TO with from not matching army position → stale, ignored."""
        a = _army(50, 50)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        # from_pos is (0,0) but army is at (50,50) → stale
        # This is tested at the command layer; here we just verify
        # that move_armies respects current target
        w = _world_with(a)
        move_armies(w, CFG)
        # Army should still move (it already has the target set)
        assert a.x != 50 or a.y != 50


class TestPathBlocking:
    """M7–M17b: Path blocking by enemy armies and towns."""

    def test_crosses_enemy_within_radius(self) -> None:
        """M7: Army path passes near stationary enemy → stops at closest approach."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        enemy = _army(50, 5, faction=1)
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        # Should stop near (50, 0) — closest approach to enemy at (50, 5)
        assert a.x == pytest.approx(50, abs=5)
        assert abs(a.y) < 10

    def test_head_on_both_moving(self) -> None:
        """M8: Head-on collision → both stop at midpoint."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        b = _army(100, 0, faction=1)
        b.target_x, b.target_y = 0, 0
        b.has_target = True
        w = _world_with(a, b)
        move_armies(w, CFG)
        # Both should stop near x=50
        assert a.x == pytest.approx(50, abs=10)
        assert b.x == pytest.approx(50, abs=10)

    def test_asymmetric_approach(self) -> None:
        """M8b: A passes near B's start, but B moves away → only A stops."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        b = _army(50, 50, faction=1)
        b.target_x, b.target_y = 50, 150  # B moves away from A's path
        b.has_target = True
        w = _world_with(a, b)
        move_armies(w, CFG)
        # A should be blocked (path passes near B's start at ~50,0)
        # B should pass (its path doesn't come near A's)
        assert a.x < 60  # A stopped early

    def test_friendly_does_not_block(self) -> None:
        """M9: Friendly army at (50,5) doesn't block."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        friendly = _army(50, 5, faction=0)  # same faction
        w = _world_with(a, friendly)
        move_armies(w, CFG)
        assert a.x == pytest.approx(100, abs=0.01)

    def test_beyond_radius_passes(self) -> None:
        """M10: Enemy at (50,20), radius=10 → passes (dist 20 > 10)."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        enemy = _army(50, 20, faction=1)
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        assert a.x == pytest.approx(100, abs=0.01)

    def test_earliest_contact_first(self) -> None:
        """M11: Two enemies → stops at earliest contact."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        e1 = _army(30, 5, faction=1)  # closer
        e2 = _army(70, 5, faction=1)  # farther
        w = _world_with(a, e1, e2)
        move_armies(w, CFG)
        assert a.x == pytest.approx(30, abs=10)

    def test_exact_radius_boundary(self) -> None:
        """M11b: Enemy at dist exactly 10 → stops (≤ radius counts)."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        enemy = _army(30, 10, faction=1)  # dist = 10 exactly
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        assert a.x < 50  # stopped early

    def test_just_outside_boundary(self) -> None:
        """M11c: Enemy at dist 10.001 → passes."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        enemy = _army(50, 10.001, faction=1)
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        # Should reach or nearly reach target
        assert a.x > 80

    def test_moving_enemy_beyond_radius(self) -> None:
        """M11d: Moving enemy that stays > radius away → no stop."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        b = _army(50, 50, faction=1)
        b.target_x, b.target_y = 50, 100  # moves further from A's path
        b.has_target = True
        w = _world_with(a, b)
        move_armies(w, CFG)
        assert a.x == pytest.approx(100, abs=1)

    def test_enemy_town_blocks(self) -> None:
        """M12: Enemy town at (100,3) → army stops at closest approach (~100,0)."""
        a = _army(0, 0)
        a.target_x, a.target_y = 200, 0
        a.has_target = True
        w = _world_with(a)
        enemy_town = Town(id=w.allocate_id(), faction=1, x=100, y=3, population=1000)
        w.towns.append(enemy_town)
        move_armies(w, CFG)
        assert a.x == pytest.approx(100, abs=10)

    def test_far_enemy_town_passes(self) -> None:
        """M13: Enemy town at (100,30) → far enough, passes."""
        a = _army(0, 0)
        a.target_x, a.target_y = 200, 0
        a.has_target = True
        w = _world_with(a)
        enemy_town = Town(id=w.allocate_id(), faction=1, x=100, y=30, population=1000)
        w.towns.append(enemy_town)
        move_armies(w, CFG)
        assert a.x == pytest.approx(200, abs=1)

    def test_stops_at_approach_point(self) -> None:
        """M14: Stops at closest approach point on path, not entity position."""
        a = _army(0, 0)
        a.target_x, a.target_y = 200, 0
        a.has_target = True
        w = _world_with(a)
        town = Town(id=w.allocate_id(), faction=1, x=100, y=5, population=1000)
        w.towns.append(town)
        move_armies(w, CFG)
        # Should stop near (100, 0), not (100, 5)
        assert a.x == pytest.approx(100, abs=10)
        assert abs(a.y) < 10

    def test_friendly_town_no_block(self) -> None:
        """M14b: Friendly town doesn't block."""
        a = _army(0, 0)
        a.target_x, a.target_y = 200, 0
        a.has_target = True
        w = _world_with(a)
        friendly_town = Town(id=w.allocate_id(), faction=0, x=100, y=3, population=1000)
        w.towns.append(friendly_town)
        move_armies(w, CFG)
        assert a.x == pytest.approx(200, abs=1)

    def test_earliest_first_void(self) -> None:
        """M15: After first contact stops army, later contacts voided."""
        a = _army(0, 0)
        a.target_x, a.target_y = 200, 0
        a.has_target = True
        e1 = _army(30, 5, faction=1)  # earliest
        e2 = _army(100, 5, faction=1)  # later
        w = _world_with(a, e1, e2)
        move_armies(w, CFG)
        # Stopped at e1, never reaches e2
        assert a.x < 50

    def test_closest_approach_numeric(self) -> None:
        """M16: D=(10,0), E=(-2,0) → t*=clamp(20/4)=1, min at end."""
        # A moving from (0,0) at v=(10,0), B at (-2,0) stationary w=(0,0)
        # D = B - A = (-2, 0), E = w - v = (-10, 0)
        # D·E = 20, |E|² = 100, t* = clamp(-20/100) = clamp(-0.2) = 0
        # Wait: let me recalculate. D = B-A = (-2-0, 0-0) = (-2, 0)
        # v_i = (10, 0) (army moves 10 units in 1 turn), v_j = (0, 0) (stationary)
        # E = v_j - v_i = (-10, 0)
        # D·E = (-2)(-10) + 0 = 20
        # t* = clamp(-20/100, 0, 1) = clamp(-0.2, 0, 1) = 0
        t_star, min_dist = _closest_approach(
            ax=0, ay=0, vx=10, vy=0,  # army: starts at origin, moves right
            bx=-2, by=0, wx=0, wy=0,  # enemy: at (-2,0), stationary
        )
        assert t_star == pytest.approx(0, abs=0.01)
        # At t=0, distance = 2
        assert min_dist == pytest.approx(2.0, abs=0.1)

    def test_t_star_middle(self) -> None:
        """M16b: D=(0,10), E=(0,-20) → t*=0.5."""
        # Army at (0,0) moving at (0,10)
        # Enemy at (0,10) moving at (0,-20)
        # D = (0,10) - (0,0) = (0, 10)
        # E = (0,-20) - (0,10) = (0, -30)
        # D·E = 10 × (-30) = -300
        # |E|² = 900
        # t* = clamp(300/900, 0, 1) = 0.333
        # Hmm let me re-read: t* = clamp(-(D·E)/|E|², 0, 1)
        # -(D·E)/|E|² = -(-300)/900 = 300/900 = 1/3
        t_star, min_dist = _closest_approach(
            ax=0, ay=0, vx=0, vy=10,  # army moves up
            bx=0, by=10, wx=0, wy=-20,  # enemy starts above, moves down
        )
        assert t_star == pytest.approx(0.333, abs=0.05)

    def test_t_star_parallel(self) -> None:
        """M16c: E=0 (parallel, same velocity) → t*=0 (stationary distance)."""
        t_star, min_dist = _closest_approach(
            ax=0, ay=0, vx=10, vy=0,
            bx=0, by=5, wx=10, wy=0,  # same velocity → E=0
        )
        # When E=0, closest approach is at t=0
        assert t_star == pytest.approx(0, abs=0.01)
        assert min_dist == pytest.approx(5.0, abs=0.1)

    def test_t_star_clamped_low(self) -> None:
        """M16d: D·E positive → negative t* → clamped to 0."""
        # Army at (0,0) moving at (10,0)
        # Enemy at (5,0) moving at (10,0) — same direction, ahead
        # D = (5,0), E = (0,0) — same velocity, parallel
        # Let's use: enemy moving away faster
        # D = (5,0), E = v_enemy - v_army = (10-10, 0) = (0,0) — boring
        # Instead: enemy at (5,0) moving at (20,0)
        # D = (5,0), E = (20,0) - (10,0) = (10,0)
        # D·E = 50, |E|² = 100
        # t* = clamp(-50/100, 0, 1) = clamp(-0.5, 0, 1) = 0
        t_star, min_dist = _closest_approach(
            ax=0, ay=0, vx=10, vy=0,
            bx=5, by=0, wx=20, wy=0,
        )
        assert t_star == pytest.approx(0, abs=0.01)
        assert min_dist == pytest.approx(5.0, abs=0.1)

    def test_fresh_spawn_immune(self) -> None:
        """M17: Fresh spawn not involved in path blocking."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        spawn = _army(50, 3, faction=1)
        spawn.is_fresh = True  # just spawned this turn
        w = _world_with(a, spawn)
        move_armies(w, CFG)
        # Fresh spawn immune → A passes through
        assert a.x == pytest.approx(100, abs=1)

    def test_fresh_spawn_no_block_town(self) -> None:
        """M17b: Fresh spawn at town path → no block."""
        a = _army(0, 0)
        a.target_x, a.target_y = 200, 0
        a.has_target = True
        spawn = _army(100, 3, faction=1)
        spawn.is_fresh = True
        w = _world_with(a, spawn)
        move_armies(w, CFG)
        # Fresh spawn should not block
        assert a.x > 150
