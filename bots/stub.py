"""Stub bot — does nothing. Useful for testing runner infrastructure."""

from __future__ import annotations

import sys

from engine.config import GameConfig


def main() -> None:
    """Read startup, loop turns, always respond with just 'go'."""
    ...


def read_startup() -> GameConfig:
    """Read config, faction, go lines from stdin."""
    ...


def read_turn() -> tuple[int, list[dict]]:
    """Read turn number, events, go from stdin."""
    ...


def write_orders(orders: list[str]) -> None:
    """Print orders to stdout followed by 'go'."""
    ...


if __name__ == "__main__":
    main()
