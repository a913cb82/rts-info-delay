"""Section 22 medium-level tests — economy E35-E42."""

from engine.config import GameConfig
from engine.world import World, Town, Army, StandingOrder, CommandType
from engine.economy import apply_growth, apply_train, apply_build, check_town_death

CFG = GameConfig()


def _make_world(*towns: Town) -> World:
    w = World()
    w.map_size = [1000, 1000]
    w.towns = list(towns)
    return w


class TestEconomyMedium:
    def test_E35_isolated_grows(self) -> None:
        """E35: Isolated town grows over 10 steps."""
        t = Town(id=1, faction=0, x=500, y=500, population=500)
        w = _make_world(t)
        for _ in range(10):
            apply_growth(w, CFG)
        assert t.population > 500

    def test_E36_crowding_reduces_growth(self) -> None:
        """E36: Two close towns crowd each other."""
        a = Town(id=1, faction=0, x=0, y=0, population=1000)
        b = Town(id=2, faction=0, x=5, y=0, population=1000)
        w = _make_world(a, b)
        for _ in range(10):
            apply_growth(w, CFG)
        # Both should have grown, but less than isolated
        # Isolated 1000 would grow more
        w2 = _make_world(Town(id=99, faction=0, x=0, y=0, population=1000))
        isolated = Town(id=99, faction=0, x=0, y=0, population=1000)
        w2.towns = [isolated]
        for _ in range(10):
            apply_growth(w2, CFG)
        assert a.population < isolated.population

    def test_E37_town_dies_mid_game(self) -> None:
        """E37: Town dies mid-game."""
        t = Town(id=1, faction=0, x=500, y=500, population=499)
        w = _make_world(t)
        apply_growth(w, CFG)
        assert all(town.id != 1 for town in w.towns)

    def test_E38_build_then_growth(self) -> None:
        """E38: BUILD then growth."""
        w = _make_world()
        a = Army(id=w.allocate_id(), faction=0, x=100, y=100)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 100])
        )
        apply_build(w, CFG)
        # Find the new town
        new_towns = [t for t in w.towns if t.x == 100 and t.y == 100]
        assert len(new_towns) == 1
        new_town = new_towns[0]
        initial_pop = new_town.population
        for _ in range(10):
            apply_growth(w, CFG)
        assert new_town.population > initial_pop

    def test_E39_train_then_recovery(self) -> None:
        """E39: TRAIN then recovery."""
        t = Town(id=1, faction=0, x=500, y=500, population=3000)
        w = _make_world(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        apply_train(w, CFG)
        assert t.population == 2000
        for _ in range(10):
            apply_growth(w, CFG)
        assert t.population > 2000

    def test_E40_standing_train_repeats(self) -> None:
        """E40: Standing TRAIN repeats."""
        t = Town(id=1, faction=0, x=500, y=500, population=5000)
        w = _make_world(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        for _ in range(3):
            apply_train(w, CFG)
        assert len(w.armies) == 3
        assert t.population == 2000

    def test_E41_build_extends_life(self) -> None:
        """E41: BUILD on existing town extends life."""
        t = Town(id=1, faction=0, x=100, y=100, population=600)
        w = _make_world(t)
        a = Army(id=w.allocate_id(), faction=0, x=100, y=100)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[100, 100])
        )
        apply_build(w, CFG)
        assert t.population == 1100
        for _ in range(10):
            apply_growth(w, CFG)
        assert t.population > 1100

    def test_E42_crowding_equilibrium(self) -> None:
        """E42: Crowding + growth equilibrium."""
        towns = [
            Town(id=i, faction=0, x=100 + i * 8, y=500, population=500)
            for i in range(3)
        ]
        w = _make_world(*towns)
        for _ in range(100):
            apply_growth(w, CFG)
        pops = [t.population for t in w.towns]
        # Pops should converge toward similar values
        assert max(pops) - min(pops) < 200
