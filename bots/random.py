"""Random bot — issues random valid orders each turn."""

from __future__ import annotations

import random
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
    """Generate random valid orders for this turn."""
    ...


def write_orders(orders: list[str]) -> None:
    """Print orders to stdout followed by 'go'."""
    ...


if __name__ == "__main__":
    main()
