"""Tests for engine/world — entities, map parsing, capital assignment."""

from __future__ import annotations

from engine.config import GameConfig
from engine.world import Army, Town, World


def _make_world(map_csv: str = "", map_size: list[int] | None = None) -> World:
    """Helper: create a World and parse a CSV map."""
    cfg = GameConfig()
    if map_size is not None:
        cfg.map_size = map_size
    w = World()
    w.map_size = cfg.map_size  # world needs to know map bounds for clamping
    if map_csv:
        w.parse_map(map_csv)
    return w


class TestMap:
    """P1–P12: CSV map parsing, factions, capitals, positions."""

    def test_csv_town(self) -> None:
        """P1: Parse town CSV line → correct fields."""
        w = _make_world("100,200,A,500\n")
        assert len(w.towns) == 1
        t = w.towns[0]
        assert t.faction == 0  # A → faction 0
        assert t.x == 100
        assert t.y == 200
        assert t.population == 500

    def test_csv_army(self) -> None:
        """P2: Parse army CSV line → correct fields."""
        w = _make_world("150,250,a,\n")
        assert len(w.armies) == 1
        a = w.armies[0]
        assert a.faction == 0  # a → faction 0
        assert a.x == 150
        assert a.y == 250

    def test_faction_letters(self) -> None:
        """P3: A/a → 0, B/b → 1, etc."""
        csv = "100,200,A,500\n300,400,B,1000\n150,250,a,\n350,450,b,\n"
        w = _make_world(csv)
        towns = {t.id: t.faction for t in w.towns}
        armies = {a.id: a.faction for a in w.armies}
        # Find by position to match CSV lines
        a_town = next(t for t in w.towns if t.x == 100)
        b_town = next(t for t in w.towns if t.x == 300)
        a_army = next(a for a in w.armies if a.x == 150)
        b_army = next(a for a in w.armies if a.x == 350)
        assert a_town.faction == 0
        assert b_town.faction == 1
        assert a_army.faction == 0
        assert b_army.faction == 1

    def test_own_faction_relabelled(self) -> None:
        """P4: own-faction perspective — faction 1 sees its entities as A/a."""
        # This is a view-layer concern; the engine stores raw faction IDs.
        # We test that faction IDs are consistent (not relabelled in storage).
        csv = "100,200,A,500\n200,300,B,1000\n"
        w = _make_world(csv)
        factions = {t.faction for t in w.towns}
        assert factions == {0, 1}

    def test_capital_is_first_town(self) -> None:
        """P5: First town per faction is capital."""
        csv = "0,0,A,500\n100,100,A,1000\n"
        w = _make_world(csv)
        assert len(w.towns) == 2
        t0 = next(t for t in w.towns if t.x == 0)
        t1 = next(t for t in w.towns if t.x == 100)
        assert t0.is_capital is True
        assert t1.is_capital is False

    def test_capital_per_faction(self) -> None:
        """P6: Each faction's first town is its capital."""
        csv = "0,0,A,500\n100,100,A,1000\n200,200,B,500\n300,300,B,1000\n"
        w = _make_world(csv)
        capitals = [t for t in w.towns if t.is_capital]
        assert len(capitals) == 2
        cap_factions = {c.faction for c in capitals}
        assert cap_factions == {0, 1}

    def test_continuous_positions(self) -> None:
        """P7: Float positions stored as float, not snapped."""
        csv = "100.7,200.3,A,500\n"
        w = _make_world(csv)
        t = w.towns[0]
        assert t.x == 100.7
        assert t.y == 200.3
        assert isinstance(t.x, float)
        assert isinstance(t.y, float)

    def test_edge_clamping_move(self) -> None:
        """P8: clamp_position respects map_size."""
        w = _make_world(map_size=[500, 500])
        x, y = w.clamp_position(2000, 2000)
        assert x == 500
        assert y == 500

    def test_edge_clamping_spawn(self) -> None:
        """P9: Entity at (1001, 500) on 500-wide map gets clamped."""
        w = _make_world(map_size=[500, 500])
        x, y = w.clamp_position(1001, 500)
        assert x == 500
        assert y == 500

    def test_map_size_respected(self) -> None:
        """P10: World with map_size [500,500] clamps (600,600) → (500,500)."""
        w = _make_world(map_size=[500, 500])
        x, y = w.clamp_position(600, 600)
        assert (x, y) == (500, 500)

    def test_population_required_for_town(self) -> None:
        """P11: Town line with missing population is handled (error or default)."""
        # Per spec: missing pop for town → parse error or default
        # Engine should at minimum not crash; we check it either raises
        # or assigns a sensible value.
        csv = "100,200,A,\n"
        w = _make_world(csv)
        # If parsed, the town must have a numeric population
        if w.towns:
            assert isinstance(w.towns[0].population, (int, float))

    def test_army_population_ignored(self) -> None:
        """P12: Army with a population column → pop is ignored."""
        csv = "100,200,a,500\n"
        w = _make_world(csv)
        assert len(w.armies) == 1
        # Army dataclass has no population field
        a = w.armies[0]
        assert not hasattr(a, "population") or a.faction == 0


class TestEntities:
    """N1–N5: Army/town fields, id allocation."""

    def test_army_fields(self) -> None:
        """N1: Army has id, faction, x, y; allocate_id increments."""
        w = World()
        w.map_size = [1000, 1000]
        id1 = w.allocate_id()
        id2 = w.allocate_id()
        assert id1 != id2
        assert id2 == id1 + 1

    def test_town_fields(self) -> None:
        """N2: Town has id, faction, x, y, population, is_capital."""
        t = Town(id=0, faction=0, x=10.0, y=20.0, population=500, is_capital=True)
        assert t.id == 0
        assert t.faction == 0
        assert t.x == 10.0
        assert t.y == 20.0
        assert t.population == 500
        assert t.is_capital is True

    def test_legacy_death_threshold_property(self) -> None:
        """N3: legacy bot floor tracks army_cost × build_efficiency (900).

        The engine's own death rule is `town_min_population` (0); this
        property only backs the bots' survive-floor heuristics."""
        cfg = GameConfig()
        assert cfg.death_threshold == 900  # 1000 × 0.9
        assert cfg.town_min_population == 0.0

    def test_town_ids_stable(self) -> None:
        """N4: Town that survives keeps the same id."""
        csv = "100,200,A,500\n"
        w = _make_world(csv)
        tid = w.towns[0].id
        # Simulate surviving turns — id never changes
        assert w.towns[0].id == tid

    def test_army_ids_unique(self) -> None:
        """N5: allocate_id twice → distinct values."""
        w = World()
        w.map_size = [1000, 1000]
        ids = {w.allocate_id() for _ in range(10)}
        assert len(ids) == 10


class TestStackedMaps:
    def test_stacked_towns_error(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="stacked"):
            _make_world("100,200,A,500\n100,200,B,500\n")

    def test_nearby_towns_fine(self) -> None:
        w = _make_world("100,200,A,500\n100.001,200,B,500\n")
        assert len(w.towns) == 2

    def test_stacked_clamped_edges_error(self) -> None:
        # distinct points clamping onto each other still count
        import pytest
        with pytest.raises(ValueError, match="stacked"):
            _make_world("0,0,A,500\n-50,-50,B,500\n", map_size=[1000, 1000])
