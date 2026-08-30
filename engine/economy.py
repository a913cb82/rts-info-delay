"""Economy — logistic growth, crowding, TRAIN, BUILD, town death."""

from __future__ import annotations

import numpy as np

from engine.config import GameConfig
from engine.world import Town, World


def logistic(population: float, config: GameConfig) -> float:
    """Per-turn logistic growth: growth_rate × pop × (1 − pop / cap)."""
    ...


def crowding_net(town: Town, all_towns: list[Town], config: GameConfig) -> float:
    """Net population change for town including crowding from neighbours.

    net(A) = logistic(A) × [1 − Σ asym(A,B_i) × (d_eq_i / d_i)^crowding_decay]
    Sum over all towns within info_speed.
    """
    ...


def asymmetry(a_pop: float, b_pop: float, config: GameConfig) -> float:
    """Asymmetric crowding factor: 1 + crowding_asymmetry × log(B / A)."""
    ...


def equilibrium_distance(a_pop: float, b_pop: float, config: GameConfig) -> float:
    """Equilibrium distance: equilibrium_spacing × √min(A, B)."""
    ...


def apply_growth(world: World, config: GameConfig) -> list[dict]:
    """Apply population changes to all towns. Return events for dead towns."""
    ...


def apply_train(world: World, config: GameConfig) -> list[dict]:
    """Execute standing TRAIN orders: subtract army_cost, spawn army."""
    ...


def apply_build(
    world: World, config: GameConfig
) -> list[dict]:
    """Execute pending BUILD commands. Returns army_spawn / town_spawn events."""
    ...


def check_town_death(town: Town, config: GameConfig) -> bool:
    """Return True if town should die (pop < army_cost × build_efficiency)."""
    ...
