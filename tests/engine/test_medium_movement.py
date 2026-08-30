"""Section 22 medium-level tests — movement M18-M24."""

from engine.config import GameConfig
from engine.world import World, Town, Army
from engine.movement import move_armies
from engine.combat import resolve_combat

CFG = GameConfig()


def _make_world(*armies: Army, **kwargs) -> World:
    w = World()
    w.map_size = kwargs.get("map_size", [1000, 1000])
    w.armies = list(armies)
    return w


class TestMovementMedium:
    def test_M18_marches_200km(self) -> None:
        """M18: Army marches 200 km over 4 turns."""
        a = Army(id=1, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True)
        w = _make_world(a)
        for _ in range(4):
            move_armies(w, CFG)
        assert a.x == 200 and a.y == 0

    def test_M19_blocked_then_resumes(self) -> None:
        """M19: Army blocked then resumes."""
        a = Army(id=1, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True)
        b = Army(id=2, faction=1, x=100, y=5)
        w = _make_world(a, b)
        move_armies(w, CFG)
        # A should stop near (100, 0)
        assert abs(a.x - 100) < 15
        # Remove enemy
        w.armies = [army for army in w.armies if army.id != 2]
        move_armies(w, CFG)
        # A should move further
        assert a.x > 100

    def test_M20_movement_before_combat(self) -> None:
        """M20: Movement before combat in step."""
        a = Army(id=1, faction=0, x=0, y=0, target_x=50, target_y=0, has_target=True)
        b = Army(id=2, faction=1, x=60, y=0)
        w = _make_world(a, b)
        move_armies(w, CFG)
        # A moves to 50
        assert a.x == 50
        # Now combat checks final positions
        resolve_combat(w, CFG)
        # Both at 50 vs 60 (dist 10 ≤ radius) → both die
        assert len(w.armies) == 0

    def test_M21_army_clamps_at_edge(self) -> None:
        """M21: Army clamps at map edge."""
        a = Army(id=1, faction=0, x=50, y=50, target_x=-100, target_y=-100, has_target=True)
        w = _make_world(a, map_size=[1000, 1000])
        move_armies(w, CFG)
        assert a.x >= 0 and a.y >= 0

    def test_M22_fresh_spawn_doesnt_block(self) -> None:
        """M22: Fresh spawn doesn't block movement."""
        a = Army(id=1, faction=0, x=0, y=0, target_x=200, target_y=0, has_target=True, is_fresh=False)
        b = Army(id=2, faction=1, x=100, y=5, is_fresh=True)
        w = _make_world(a, b)
        move_armies(w, CFG)
        # A should reach target (B is immune)
        assert a.x == 200

    def test_M23_head_on_both_stop(self) -> None:
        """M23: Two armies head-on both stop."""
        a = Army(id=1, faction=0, x=0, y=0, target_x=100, target_y=0, has_target=True)
        b = Army(id=2, faction=1, x=100, y=0, target_x=0, target_y=0, has_target=True)
        w = _make_world(a, b)
        move_armies(w, CFG)
        assert abs(a.x - 50) < 10
        assert abs(b.x - 50) < 10

    def test_M24_moves_then_fights(self) -> None:
        """M24: Army moves then fights same turn."""
        a = Army(id=1, faction=0, x=0, y=0, target_x=10, target_y=0, has_target=True)
        b = Army(id=2, faction=1, x=15, y=0)
        w = _make_world(a, b)
        move_armies(w, CFG)
        assert a.x == 10
        resolve_combat(w, CFG)
        # 10 vs 15 (dist 5 ≤ radius) → both die
        assert len(w.armies) == 0
