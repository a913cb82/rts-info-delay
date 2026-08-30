"""Combat — weakness-based simultaneous death resolution."""

from __future__ import annotations

import numpy as np

from engine.config import GameConfig
from engine.world import Army, World


def compute_weaknesses(
    armies: list[Army], config: GameConfig
) -> dict[int, int]:
    """Return {army_id: num_enemy_armies_within_interact_radius}."""
    ...


def resolve_combat(
    world: World, config: GameConfig
) -> list[dict]:
    """Compute deaths from final positions. Returns battle event dicts.

    An army dies if any enemy within interact_radius has weakness ≤ its own.
    Deaths are simultaneous — computed from snapshot of positions.
    """
    ...


def _enemies_within_radius(
    army: Army, armies: list[Army], radius: float
) -> list[Army]:
    """Return enemy armies within radius of army."""
    ...
