"""Tests for score computation — cross-cutting (uses engine/world + engine/config)."""

from __future__ import annotations

import pytest

from engine.config import GameConfig
from runner.main import score
from engine.world import Army, Town, World

CFG = GameConfig()


def _world_with(
    towns: list[Town] | None = None,
    armies: list[Army] | None = None,
) -> World:
    """Helper: create a World."""
    w = World()
    w.map_size = [1000, 1000]
    if towns:
        w.towns = towns
    if armies:
        w.armies = armies
    return w


class TestScore:
    """S1–S3d: Score formula and edge cases."""

    def test_formula(self) -> None:
        """S1: 3 towns (1000+2000+500=3500), 2 armies ×1000 = 2000 → 5500."""
        w = _world_with(
            towns=[
                Town(id=0, faction=0, x=0, y=0, population=1000),
                Town(id=1, faction=0, x=10, y=0, population=2000),
                Town(id=2, faction=0, x=20, y=0, population=500),
            ],
            armies=[
                Army(id=10, faction=0, x=0, y=0),
                Army(id=11, faction=0, x=0, y=0),
            ],
        )
        result = score(w, CFG)
        assert result[0] == 5500

    def test_only_alive_counted(self) -> None:
        """S2: Kill 1 town (pop 1000) → score drops by 1000."""
        w = _world_with(
            towns=[
                Town(id=0, faction=0, x=0, y=0, population=1000),
                Town(id=1, faction=0, x=10, y=0, population=2000),
            ],
            armies=[Army(id=10, faction=0, x=0, y=0)],
        )
        score_before = score(w, CFG)[0]
        # Remove one town
        w.towns = [t for t in w.towns if t.id != 0]
        score_after = score(w, CFG)[0]
        assert score_before - score_after == 1000

    def test_at_start(self) -> None:
        """S3: 1 town (500) + 1 army (1000) → 1500."""
        w = _world_with(
            towns=[Town(id=0, faction=0, x=0, y=0, population=500)],
            armies=[Army(id=10, faction=0, x=0, y=0)],
        )
        result = score(w, CFG)
        assert result[0] == 1500

    def test_empty_faction(self) -> None:
        """S3b: Faction with 0 towns, 0 armies → 0."""
        w = _world_with()
        result = score(w, CFG)
        assert result.get(0, 0) == 0

    def test_build_vs_score(self) -> None:
        """S3c: BUILD army (1000) → town (500): net −500."""
        w = _world_with(
            armies=[Army(id=10, faction=0, x=50, y=50)],
        )
        score_before = score(w, CFG)[0]  # 0 + 1000×1 = 1000
        assert score_before == 1000
        # Convert army to town
        w.armies = []
        w.towns = [Town(id=20, faction=0, x=50, y=50, population=500)]
        score_after = score(w, CFG)[0]  # 500 + 0 = 500
        assert score_after == 500

    def test_train_vs_score(self) -> None:
        """S3d: TRAIN town (2000) → town (1000) + army (1000): net 0."""
        w = _world_with(
            towns=[Town(id=0, faction=0, x=0, y=0, population=2000)],
        )
        score_before = score(w, CFG)[0]  # 2000
        # Simulate TRAIN: pop reduces, army spawns
        w.towns[0].population = 1000
        w.armies = [Army(id=10, faction=0, x=0, y=0)]
        score_after = score(w, CFG)[0]  # 1000 + 1000 = 2000
        assert score_after == 2000

    def test_multi_faction(self) -> None:
        """Score computed per faction."""
        w = _world_with(
            towns=[
                Town(id=0, faction=0, x=0, y=0, population=1000),
                Town(id=1, faction=1, x=50, y=0, population=2000),
            ],
            armies=[
                Army(id=10, faction=0, x=0, y=0),
                Army(id=11, faction=1, x=50, y=0),
            ],
        )
        result = score(w, CFG)
        assert result[0] == 2000  # 1000 + 1000
        assert result[1] == 3000  # 2000 + 1000

    def test_score_covers_all_factions(self) -> None:
        """Score works for each faction independently, including absent factions."""
        w = _world_with(
            towns=[
                Town(id=1, faction=0, x=100, y=100, population=1000),
                Town(id=2, faction=1, x=900, y=900, population=2000),
            ],
            armies=[Army(id=3, faction=2, x=500, y=500)],
        )
        s0 = score(w, CFG)
        assert s0[0] == 1000
        assert s0[1] == 2000
        assert s0.get(2, 0) == 1000  # army only

    def test_score_empty_world(self) -> None:
        """Score of empty world is 0 for all factions."""
        w = _world_with()
        result = score(w, CFG)
        assert result.get(0, 0) == 0
