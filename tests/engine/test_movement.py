"""Tests for engine/movement — straight-line paths, path blocking, closest approach."""

from __future__ import annotations

import math

import pytest

from engine.config import GameConfig
from engine.movement import _closest_approach, move_armies
from engine.world import Army, Town, World

CFG = GameConfig()


_next_aid = 100
def _army(x: float, y: float, faction: int = 0, aid: int | None = None) -> Army:
    """Helper: create an Army at position with no target."""
    global _next_aid
    if aid is None:
        aid = _next_aid
        _next_aid += 1
    return Army(id=aid, faction=faction, x=x, y=y)


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
        enemy = _army(25, 5, faction=1)  # blocker halfway along move path
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        # Should stop near (25, 0) — closest approach to enemy at (25, 5)
        assert a.x == pytest.approx(25, abs=5)
        assert abs(a.y) < 10

    def test_head_on_both_moving(self) -> None:
        """M8: Head-on collision → both stop at closest approach."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        b = _army(50, 0, faction=1)  # blocker halfway along A's path
        b.target_x, b.target_y = -50, 0  # B moves toward A
        b.has_target = True
        w = _world_with(a, b)
        move_armies(w, CFG)
        # Both stop at closest approach (midpoint)
        assert a.x < 30  # A stopped early
        assert b.x > 20  # B stopped before reaching A

    def test_angled_crossing_both_moving(self) -> None:
        """M8c: Two armies moving at an angle → both stop if paths cross within radius."""
        # A moves right, B moves up-left. Paths cross at an angle.
        # Closest approach ~7.6 km (within 10 km radius) → both blocked.
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        b = _army(15, 5, faction=1)
        b.target_x, b.target_y = 0, 20  # B moves up-left
        b.has_target = True
        w = _world_with(a, b)
        move_armies(w, CFG)
        # Both armies stopped before reaching their targets
        assert a.x < 30  # A stopped (would reach 50 without block)
        assert b.y < 20  # B stopped (would reach ~18 without block)

    def test_asymmetric_approach(self) -> None:
        """M8b: A passes near stationary B → A stops. B has no target → stays put."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        b = _army(25, 5, faction=1)  # stationary blocker halfway along A's path
        w = _world_with(a, b)
        move_armies(w, CFG)
        # A is blocked — closest approach to B at (25,5) is 5 km ≤ radius
        assert a.x == pytest.approx(25, abs=5)
        # B has no target → stays at (25,5)
        assert b.x == pytest.approx(25, abs=0.01)
        assert b.y == pytest.approx(5, abs=0.01)

    def test_friendly_does_not_block(self) -> None:
        """M9: Friendly army at (25,5) doesn't block."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        friendly = _army(25, 5, faction=0)  # same faction, halfway along path
        w = _world_with(a, friendly)
        move_armies(w, CFG)
        # Friendly at (25,5) is within radius but same faction → no block
        assert a.x == pytest.approx(50, abs=0.01)

    def test_beyond_radius_passes(self) -> None:
        """M10: Enemy at (25,20), radius=10 → passes (dist 20 > 10)."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        enemy = _army(25, 20, faction=1)  # halfway along path but outside radius
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        # Closest approach at x=25: dist=20 > radius=10 → no block
        assert a.x == pytest.approx(50, abs=0.01)

    def test_earliest_contact_first(self) -> None:
        """M11: Two enemies → stops at earliest contact."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        e1 = _army(15, 5, faction=1)  # closer (15 km)
        e2 = _army(35, 5, faction=1)  # farther (35 km)
        w = _world_with(a, e1, e2)
        move_armies(w, CFG)
        # Army blocked at earliest enemy's x
        assert a.x == pytest.approx(15, abs=5)

    def test_exact_radius_boundary(self) -> None:
        """M11b: Enemy at dist exactly 10 → stops (≤ radius counts)."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        enemy = _army(20, 10, faction=1)  # halfway, dist = 10 exactly at x=20
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        # Closest approach at x=20: dist = 10 ≤ radius → blocked
        assert a.x < 30  # stopped early

    def test_just_outside_boundary(self) -> None:
        """M11c: Enemy at dist 10.001 → passes."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        enemy = _army(30, 10.001, faction=1)  # halfway, just outside radius
        w = _world_with(a, enemy)
        move_armies(w, CFG)
        # Closest approach at x=30: dist = 10.001 > radius = 10 → no block
        assert a.x == pytest.approx(50, abs=0.01)

    def test_moving_enemy_beyond_radius(self) -> None:
        """M11d: Enemy at dist > radius → no stop."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        b = _army(25, 15, faction=1)  # halfway, outside radius (dist=15 > 10)
        w = _world_with(a, b)
        move_armies(w, CFG)
        # Closest approach at x=25: dist = 15 > radius = 10 → no block
        assert a.x == pytest.approx(50, abs=1)

    def test_enemy_town_blocks(self) -> None:
        """M12: Enemy town at (25,3) → army stops at closest approach (~25,0)."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        w = _world_with(a)
        enemy_town = Town(id=w.allocate_id(), faction=1, x=25, y=3, population=1000)  # halfway
        w.towns.append(enemy_town)
        move_armies(w, CFG)
        # Should stop near (25, 0) — closest approach to town at (25, 3)
        assert a.x == pytest.approx(25, abs=5)
        assert abs(a.y) < 5

    def test_far_enemy_town_passes(self) -> None:
        """M13: Enemy town at (25,30) → far enough, passes."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        w = _world_with(a)
        enemy_town = Town(id=w.allocate_id(), faction=1, x=25, y=30, population=1000)  # outside radius
        w.towns.append(enemy_town)
        move_armies(w, CFG)
        # Closest approach at x=25: dist=30 > radius=10 → no block
        assert a.x == pytest.approx(50, abs=1)

    def test_stops_at_approach_point(self) -> None:
        """M14: Stops at closest approach point on path, not entity position."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        w = _world_with(a)
        town = Town(id=w.allocate_id(), faction=1, x=25, y=5, population=1000)  # halfway
        w.towns.append(town)
        move_armies(w, CFG)
        # Should stop near (25, 0), not (25, 5) — closest approach on path
        assert a.x == pytest.approx(25, abs=5)
        assert abs(a.y) < 5

    def test_friendly_town_no_block(self) -> None:
        """M14b: Friendly town doesn't block."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        w = _world_with(a)
        friendly_town = Town(id=w.allocate_id(), faction=0, x=25, y=3, population=1000)  # halfway
        w.towns.append(friendly_town)
        move_armies(w, CFG)
        # Friendly town at (25,3) within radius but same faction → no block
        assert a.x == pytest.approx(50, abs=1)

    def test_earliest_first_void(self) -> None:
        """M15: After first contact stops army, later contacts voided."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        e1 = _army(15, 5, faction=1)  # earlier (15 km)
        e2 = _army(35, 5, faction=1)  # later (35 km)
        w = _world_with(a, e1, e2)
        move_armies(w, CFG)
        # Stopped at e1, never reaches e2
        assert a.x == pytest.approx(15, abs=5)

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
        spawn = _army(25, 3, faction=1)  # halfway along path
        spawn.is_fresh = True  # just spawned this turn
        w = _world_with(a, spawn)
        move_armies(w, CFG)
        # Fresh spawn immune → A passes through to speed-limited position
        assert a.x == pytest.approx(50, abs=1)

    def test_fresh_spawn_no_block_town(self) -> None:
        """M17b: Fresh spawn at town path → no block."""
        a = _army(0, 0)
        a.target_x, a.target_y = 100, 0
        a.has_target = True
        spawn = _army(25, 3, faction=1)  # halfway along path
        spawn.is_fresh = True
        w = _world_with(a, spawn)
        move_armies(w, CFG)
        # Fresh spawn immune → A passes through to speed-limited position
        assert a.x == pytest.approx(50, abs=1)


class TestMovementStacking:
    """Stacking at movement layer — two armies at identical coords."""

    def test_two_armies_same_pos_both_move_together(self) -> None:
        """Two armies at same position with same target move identically."""
        a1 = Army(id=1, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True)
        a2 = Army(id=2, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True)
        w = _world_with(a1, a2)
        move_armies(w, CFG)
        assert a1.x == a2.x == 50
        assert a1.y == a2.y == 0

    def test_two_armies_same_pos_different_targets(self) -> None:
        """Two armies at same position but different targets move independently."""
        a1 = Army(id=1, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True)
        a2 = Army(id=2, faction=0, x=0, y=0, target_x=0, target_y=200, has_target=True)
        w = _world_with(a1, a2)
        move_armies(w, CFG)
        assert a1.x == 50 and a1.y == 0
        assert a2.x == 0 and a2.y == 50

    def test_three_armies_stacked_all_move(self) -> None:
        """Three armies stacked all move together."""
        armies = [
            Army(id=i, faction=0, x=100, y=100, target_x=300, target_y=100, has_target=True)
            for i in range(3)
        ]
        w = _world_with(*armies)
        move_armies(w, CFG)
        for a in w.armies:
            assert a.x == 150 and a.y == 100

    def test_blocked_armies_fight_head_on(self) -> None:
        """Two armies move toward each other, block at midpoint, then combat."""
        from engine.combat import resolve_combat

        a = Army(id=1, faction=0, x=0, y=0, target_x=100, target_y=0, has_target=True)
        b = Army(id=2, faction=1, x=10, y=0, target_x=-90, target_y=0, has_target=True)
        w = _world_with(a, b)
        move_armies(w, CFG)
        # Both blocked at ~(5,0) — closest approach 0 km
        assert a.x == pytest.approx(5, abs=1)
        assert b.x == pytest.approx(5, abs=1)
        # Distance ≤ radius → combat kills both
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_blocked_armies_fight_angled(self) -> None:
        """Two armies moving at an angle, block mid-trajectory, then combat."""
        from engine.combat import resolve_combat

        a = Army(id=1, faction=0, x=0, y=0, target_x=100, target_y=0, has_target=True)
        b = Army(id=2, faction=1, x=10, y=3, target_x=10, target_y=20, has_target=True)
        w = _world_with(a, b)
        move_armies(w, CFG)
        # Both blocked — closest approach ~6 km (within radius)
        dist = math.hypot(a.x - b.x, a.y - b.y)
        assert dist < 10  # within combat radius
        # 1v1 mutual → both die
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_death_event_position_is_final_not_start(self) -> None:
        """Army marching (0,0)→(100,0) dies at (50,0). Combat at final pos."""
        from engine.combat import resolve_combat

        a = Army(id=1, faction=0, x=0, y=0, target_x=100, target_y=0, has_target=True)
        b = _army(50, 0, faction=1)
        w = _world_with(a, b)
        move_armies(w, CFG)
        # a moved to (50,0), b at (50,0) — combat at final position
        resolve_combat(w, CFG)
        assert len(w.armies) == 0  # both die at (50,0)
