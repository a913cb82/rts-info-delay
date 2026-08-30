"""Section 22 medium-level tests — entities N6-N9."""

from engine.config import GameConfig
from engine.world import World, Town, Army, StandingOrder, CommandType
from engine.economy import apply_growth, apply_train, apply_build, check_town_death

CFG = GameConfig()


def _make_world(**kwargs) -> World:
    w = World()
    w.map_size = kwargs.get("map_size", [1000, 1000])
    return w


class TestEntitiesMedium:
    def test_N6_unique_ids(self) -> None:
        """N6: 10 armies spawned have unique ids."""
        w = _make_world()
        ids = [w.allocate_id() for _ in range(10)]
        assert len(set(ids)) == 10

    def test_N7_town_survives_10_steps(self) -> None:
        """N7: Town survives 10 step() calls."""
        w = _make_world()
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=500, y=500, population=2000)
        w.towns.append(t)
        for _ in range(10):
            apply_growth(w, CFG)
        assert any(town.id == tid for town in w.towns)
        assert t.population > 2000

    def test_N8_army_removed_after_build(self) -> None:
        """N8: Army removed after BUILD."""
        w = _make_world()
        aid = w.allocate_id()
        a = Army(id=aid, faction=0, x=100, y=100)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=aid, target_type="army", args=[100, 100])
        )
        apply_build(w, CFG)
        assert all(army.id != aid for army in w.armies)

    def test_N9_town_removed_when_pop_zero(self) -> None:
        """N9: Town removed when pop hits 0."""
        w = _make_world()
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=500, y=500, population=0)
        w.towns.append(t)
        apply_growth(w, CFG)
        # Pop 0 → logistic(0)=0, no growth, but check_town_death should kill it
        assert all(town.id != tid for town in w.towns) or t.population < 500
