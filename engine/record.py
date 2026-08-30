"""Game record — JSONL serialisation of full world state per turn."""

from __future__ import annotations

import json
from pathlib import Path

from engine.config import GameConfig
from engine.world import World


def write_config_line(config: GameConfig, f: Path) -> None:
    """Write the config JSON line as first line of record."""
    ...


def write_turn_line(turn: int, world: World, events: list[dict], f: Path) -> None:
    """Write one turn's full state + events as a JSON line."""
    ...


def world_to_dict(world: World) -> dict:
    """Serialise world to {"armies": [...], "towns": [...]}."""
    ...


def army_to_dict(army) -> dict:
    """Serialise army: {id, faction, x, y}."""
    ...


def town_to_dict(town) -> dict:
    """Serialise town: {id, faction, x, y, population, is_capital}."""
    ...
