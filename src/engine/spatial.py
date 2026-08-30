"""Spatial hash grid for O(n) proximity queries."""

from __future__ import annotations

import numpy as np

from engine.config import GameConfig


class SpatialHash:
    """Uniform grid with cell size ≥ interact_radius.

    Rebuilt each turn. Queries return entity indices within a radius.
    """

    cell_size: float
    width: int
    height: int
    cells: dict[tuple[int, int], list[int]]

    def __init__(self, config: GameConfig) -> None:
        ...

    def rebuild(self, positions: np.ndarray) -> None:
        """Rebuild grid from Nx2 position array."""
        ...

    def query_radius(self, x: float, y: float, radius: float) -> list[int]:
        """Return indices of entities within radius of (x, y)."""
        ...

    def query_radius_pairs(
        self, positions: np.ndarray, radius: float
    ) -> list[tuple[int, int]]:
        """Return all index pairs within radius. No self-pairs, no duplicates."""
        ...

    def _cell_key(self, x: float, y: float) -> tuple[int, int]:
        """Convert world position to cell key."""
        ...

    def _cells_in_radius(self, x: float, y: float, radius: float) -> list[tuple[int, int]]:
        """Return all cell keys within radius of (x, y)."""
        ...
