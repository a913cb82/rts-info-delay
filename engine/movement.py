"""Movement — straight-line paths with path-blocking contacts."""

from __future__ import annotations

import numpy as np
from numba import njit

from engine.config import GameConfig
from engine.world import Army, World


def move_armies(world: World, config: GameConfig) -> list[dict]:
    """Advance all armies toward targets. Handle path-blocking contacts.

    Returns army_move events for each army that moved.
    Contacts resolve earliest-first. Stopped/dead party voids later contacts.
    Fresh spawns are immune.
    """
    ...


def _closest_approach(
    ax: float, ay: float, vx: float, vy: float,
    bx: float, by: float, wx: float, wy: float,
) -> tuple[float, float]:
    """Compute closest approach between two moving points.

    Returns (t*, min_distance) where t* ∈ [0, 1].
    P_i(t) = A + t·V_i, P_j(t) = B + t·V_j
    t* = clamp(-(D·E)/|E|², 0, 1) where D = B-A, E = V_j - V_i
    """
    ...


@njit
def _closest_approach_numba(
    ax: float, ay: float, vx: float, vy: float,
    bx: float, by: float, wx: float, wy: float,
) -> tuple[float, float]:
    """Numba-accelerated closest approach."""
    ...


def _path_blocks_army(
    army: Army, enemy: Army, radius: float
) -> tuple[bool, float]:
    """Check if army's path comes within radius of enemy.

    Returns (blocked, t_stop) where t_stop ∈ [0, 1].
    """
    ...


def _path_blocks_town(
    army: Army, town_x: float, town_y: float, radius: float
) -> tuple[bool, float]:
    """Check if army's path comes within radius of a town.

    Returns (blocked, t_stop) where t_stop ∈ [0, 1].
    """
    ...
