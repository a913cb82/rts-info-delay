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

    def test_E36_equal_neighbours_share_access(self) -> None:
        """E36: two close equal towns each grow faster than isolated
        (mutual access at parity; migration cancels for equal sizes)."""
        a = Town(id=1, faction=0, x=0, y=0, population=1000)
        b = Town(id=2, faction=0, x=5, y=0, population=1000)
        w = _make_world(a, b)
        for _ in range(10):
            apply_growth(w, CFG)
        w2 = _make_world(Town(id=99, faction=0, x=0, y=0, population=1000))
        for _ in range(10):
            apply_growth(w2, CFG)
        # Compare against the stepped isolated town (not a fresh object).
        assert a.population > w2.towns[0].population

    def test_E37_town_dies_mid_game(self) -> None:
        """E37: Town at the floor (0) dies mid-game."""
        t = Town(id=1, faction=0, x=500, y=500, population=0)
        w = _make_world(t)
        apply_growth(w, CFG)
        assert all(town.id != 1 for town in w.towns)

    def test_E38_build_then_growth(self) -> None:
        """E38: BUILD then growth."""
        # Center, plus a neighbour village: lone 900s sit below the
        # Malthusian point on labour footprint alone; trade+boost feed them.
        w = _make_world(Town(id=99, faction=0, x=500, y=530, population=300))
        a = Army(id=w.allocate_id(), faction=0, x=500, y=500)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[500, 500])
        )
        apply_build(w, CFG)
        # Find the new town
        new_towns = [t for t in w.towns if t.x == 500 and t.y == 500]
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
        # Training cost is spent, town stabilizes near capacity instead
        # of spiralling. (Level pinning belongs to the tripwire.)
        assert t.population > 1500

    def test_E40_standing_train_one_shot(self) -> None:
        """E40: Standing TRAIN is one-shot (consumed after execution)."""
        t = Town(id=1, faction=0, x=500, y=500, population=5000)
        w = _make_world(t)
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=1, target_type="town")
        )
        for _ in range(3):
            apply_train(w, CFG)
        # TRAIN is one-shot: only 1 army spawned
        assert len(w.armies) == 1
        assert t.population == 4000
        assert len(w.standing_orders) == 0

    def test_E41_build_extends_life(self) -> None:
        """E41: BUILD on existing town extends life."""
        # Center (full ring): corner cells clip and starve boosted towns.
        t = Town(id=1, faction=0, x=500, y=500, population=600)
        w = _make_world(t)
        a = Army(id=w.allocate_id(), faction=0, x=500, y=500)
        w.armies.append(a)
        w.standing_orders.append(
            StandingOrder(command=CommandType.BUILD, target_id=a.id, target_type="army", args=[500, 500])
        )
        apply_build(w, CFG)
        assert t.population == 1500
        # Lone towns above ring capacity decline; BUILD buys life, and the
        # boosted town outlives an unboosted twin (relative, robust).
        twin = Town(id=2, faction=0, x=500, y=700, population=600)
        w.towns.append(twin)
        for _ in range(10):
            apply_growth(w, CFG)
        assert t.population > twin.population
        assert t.population > 1000

    def test_E42_close_hamlets_stay_together(self) -> None:
        """E42: three 8-km-apart hamlets coexist and stay similar."""
        towns = [
            Town(id=i, faction=0, x=100 + i * 8, y=500, population=500)
            for i in range(3)
        ]
        w = _make_world(*towns)
        for _ in range(100):
            apply_growth(w, CFG)
        assert len(w.towns) == 3
        pops = [t.population for t in w.towns]
        assert max(pops) - min(pops) < 200
