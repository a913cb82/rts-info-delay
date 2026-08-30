"""Greedy bot — expands toward nearest neutral/enemy town, trains when able."""

from __future__ import annotations

import sys

from engine.config import GameConfig
from engine.world import World


def main() -> None:
    """Bot entry point. Reads startup, then loops turns."""
    ...


def read_startup() -> GameConfig:
    """Read config, faction, go lines from stdin."""
    ...


def read_turn() -> tuple[int, list[dict]]:
    """Read turn number, events, go from stdin."""
    ...


def decide_orders(world: World, faction: int, config: GameConfig) -> list[str]:
    """Generate greedy orders:
    - TRAIN if town pop ≥ army_cost
    - MOVE_TO nearest enemy/neutral town
    - BUILD if army near empty ground
    """
    ...


def write_orders(orders: list[str]) -> None:
    """Print orders to stdout followed by 'go'."""
    ...


if __name__ == "__main__":
    main()
