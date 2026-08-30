"""Random bot — issues random valid orders each turn."""

from __future__ import annotations

import json
import random
import sys
import math

from engine.config import GameConfig
from engine.world import World


def main() -> None:
    """Bot entry point. Reads startup, then loops turns."""
    config, faction = read_startup()
    world = World()
    world.map_size = config.map_size
    if config.map:
        world.parse_map(config.map)

    while True:
        turn_info = read_turn()
        if turn_info is None:
            break
        turn, events = turn_info
        if turn == -1:
            break
        # Apply events to world? For random bot, we just track minimally
        # Update world based on events (simplified)
        # For decide_orders, we need world state; we will maintain simple world parsing from events?
        # We'll just use current world snapshot plus events
        # For simplicity, we don't fully reconstruct world from events; we use decide_orders with current world
        orders = decide_orders(world, faction, config)
        write_orders(orders)


def read_startup() -> tuple[GameConfig, int]:
    """Read config, faction, go lines from stdin."""
    config = GameConfig()
    faction = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("config "):
            json_str = line[len("config "):]
            try:
                d = json.loads(json_str)
                config = GameConfig.from_dict(d)
            except Exception:
                pass
        elif line.startswith("faction "):
            try:
                faction = int(line.split()[1])
            except Exception:
                faction = 0
        elif line == "go":
            break
        elif line.startswith("end "):
            sys.exit(0)
    return config, faction


def read_turn() -> tuple[int, list[dict]] | None:
    """Read turn number, events, go from stdin."""
    turn = None
    events: list[dict] = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("turn "):
            try:
                turn = int(line.split()[1])
            except Exception:
                turn = 0
        elif line == "go":
            if turn is not None:
                return (turn, events)
            continue
        elif line.startswith("end "):
            return (-1, [])
        elif line.startswith("{"):
            try:
                ev = json.loads(line)
                events.append(ev)
            except Exception:
                pass
        else:
            try:
                ev = json.loads(line)
                events.append(ev)
            except Exception:
                pass
    return None


def decide_orders(world: World, faction: int, config: GameConfig) -> list[str]:
    """Generate random valid orders for this turn."""
    orders: list[str] = []
    # Gather own entities
    own_armies = world.armies_for_faction(faction)
    own_towns = world.towns_for_faction(faction)

    # Randomly TRAIN if possible
    for town in own_towns:
        if town.population >= config.army_cost and random.random() < 0.3:
            orders.append(f"TRAIN {town.id}")

    # Randomly MOVE_TO
    for army in own_armies:
        if random.random() < 0.3:
            # Random target within map
            tx = random.uniform(0, config.map_size[0])
            ty = random.uniform(0, config.map_size[1])
            orders.append(f"MOVE_TO {army.id} {army.x} {army.y} {tx} {ty}")

    # Randomly BUILD
    for army in own_armies:
        if random.random() < 0.1:
            # Build at army's current location
            orders.append(f"BUILD {army.id} {army.x} {army.y}")

    # Occasionally MOVE_CAPITAL (rare)
    if own_towns and random.random() < 0.02:
        # Pick random location
        tx = random.uniform(0, config.map_size[0])
        ty = random.uniform(0, config.map_size[1])
        orders.append(f"MOVE_CAPITAL {tx} {ty}")

    return orders


def write_orders(orders: list[str]) -> None:
    """Print orders to stdout followed by 'go'."""
    for o in orders:
        sys.stdout.write(o + "\n")
    sys.stdout.write("go\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
