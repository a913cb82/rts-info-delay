"""Game record — JSONL serialisation of full world state per turn."""

from __future__ import annotations

import json
from pathlib import Path

from engine.config import GameConfig
from engine.world import World


def write_config_line(config: GameConfig, f: Path) -> None:
    """Write the config JSON line as first line of record."""
    data = config.to_dict()
    data["type"] = "config"
    # ensure map field etc
    line = json.dumps(data, sort_keys=True)
    # f is Path, we append
    path = Path(f)
    # If file exists, append; else create
    # For first line, we should ensure file is written (truncate if needed? Tests create fresh temp file)
    # We'll append with newline
    with open(path, "a") as out:
        out.write(line + "\n")


def write_turn_line(turn: int, world: World, events: list[dict], f: Path,
                    orders: dict | None = None) -> None:
    """Write one turn's full state + events as a JSON line.

    orders (optional, additive): {faction: [order strs]} for order tracing
    (precise autopsies: why takes were/weren't issued)."""
    path = Path(f)
    data = {
        "type": "turn",
        "turn": turn,
        "world": world_to_dict(world),
        "events": events,
    }
    if orders is not None:
        data["orders"] = {str(k): list(v) for k, v in orders.items()}
    line = json.dumps(data, sort_keys=True)
    with open(path, "a") as out:
        out.write(line + "\n")


def world_to_dict(world: World) -> dict:
    """Serialise world to {"armies": [...], "towns": [...]}."""
    return {
        "armies": [army_to_dict(a) for a in world.armies],
        "towns": [town_to_dict(t) for t in world.towns],
    }


def army_to_dict(army) -> dict:
    """Serialise army: {id, faction, x, y, size}."""
    # Include is_viceroy? But spec says army has id,faction,x,y; viewer needs is_viceroy in events not world. World serialisation is minimal.
    return {"id": army.id, "faction": army.faction, "x": army.x, "y": army.y, "size": army.size}


def town_to_dict(town) -> dict:
    """Serialise town: {id, faction, x, y, population, is_capital}."""
    return {
        "id": town.id,
        "faction": town.faction,
        "x": town.x,
        "y": town.y,
        "population": town.population,
        "is_capital": town.is_capital,
    }
