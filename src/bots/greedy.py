"""Greedy bot — expands toward nearest neutral/enemy town, trains when able."""

from __future__ import annotations

import json
import math
import sys

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
        # Simple event handling: update world based on events? For greedy we maintain world via events
        # For now, we don't fully reconstruct; we rely on decide_orders using world snapshot
        # We'll update world from events payloads (minimal)
        for ev in events:
            # Try to apply event to world (town_spawn, army_spawn etc.)
            kind = ev.get("kind")
            if kind == "army_spawn":
                from engine.world import Army
                # Avoid duplicates
                if any(a.id == ev.get("id") for a in world.armies):
                    continue
                army = Army(id=ev.get("id"), faction=ev.get("faction", faction), x=ev.get("x", 0), y=ev.get("y", 0), is_fresh=True)
                army.is_viceroy = ev.get("is_viceroy", False)
                world.armies.append(army)
            elif kind == "town_spawn":
                from engine.world import Town
                if any(t.id == ev.get("id") for t in world.towns):
                    continue
                town = Town(id=ev.get("id"), faction=ev.get("faction", faction), x=ev.get("x", 0), y=ev.get("y", 0), population=ev.get("population", 500), is_capital=ev.get("is_capital", False))
                world.towns.append(town)
            elif kind == "army_move":
                army = world.get_army(ev.get("id"))
                if army:
                    army.x = ev.get("x", army.x)
                    army.y = ev.get("y", army.y)
            elif kind == "army_death":
                world.remove_army(ev.get("id"))
            elif kind == "battle":
                # Battle implies deaths already handled via army_death events
                pass

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
    """Generate greedy orders:
    - TRAIN if town pop ≥ army_cost
    - MOVE_TO nearest enemy/neutral town
    - BUILD if army near empty ground
    """
    orders: list[str] = []
    own_armies = world.armies_for_faction(faction)
    own_towns = world.towns_for_faction(faction)

    # TRAIN if affordable
    for town in own_towns:
        if town.population >= config.army_cost:
            orders.append(f"TRAIN {town.id}")

    # For each army, move toward nearest enemy or neutral town, or empty ground
    # Find enemy towns
    enemy_towns = [t for t in world.towns if t.faction != faction]

    for army in own_armies:
        # Skip viceroy (already has target)
        if army.is_viceroy and army.has_target:
            continue
        if enemy_towns:
            # Nearest enemy town
            nearest = min(enemy_towns, key=lambda t: math.hypot(t.x - army.x, t.y - army.y))
            # If already close to a town, consider BUILD instead
            dist_to_nearest = math.hypot(nearest.x - army.x, nearest.y - army.y)
            if dist_to_nearest <= config.interact_radius + 1e-9:
                # If army near own town? Actually near enemy town won't BUILD? But if near own town's location? We'll build if near empty
                pass
            # Move toward nearest enemy town
            # Only issue MOVE_TO if not already heading there?
            # Check if already has target near that town
            if not army.has_target or math.hypot(army.target_x - nearest.x, army.target_y - nearest.y) > 1e-6:
                orders.append(f"MOVE_TO {army.id} {army.x} {army.y} {nearest.x} {nearest.y}")
        else:
            # No enemy towns, explore random
            # Move to center or random edge
            # For expansion, build new town if army not near town
            # Check if army near any town
            near_town = any(math.hypot(t.x - army.x, t.y - army.y) <= config.interact_radius * 2 for t in world.towns)
            if not near_town:
                # Build at current location
                orders.append(f"BUILD {army.id} {army.x} {army.y}")
            else:
                # Move to random far location
                # Pick point away from own capital
                capital = world.faction_capital(faction)
                if capital:
                    # Move opposite direction?
                    tx = army.x + (army.x - capital.x) * 0.5 + 100
                    ty = army.y + (army.y - capital.y) * 0.5 + 100
                    tx, ty = world.clamp_position(tx, ty)
                    orders.append(f"MOVE_TO {army.id} {army.x} {army.y} {tx} {ty}")

    # Also handle BUILD for armies that are near empty ground and have moved
    # For any army not already given a BUILD order, if it's far from towns, build
    built_army_ids = set()
    for o in orders:
        if o.startswith("BUILD"):
            try:
                built_army_ids.add(int(o.split()[1]))
            except Exception:
                pass
    for army in own_armies:
        if army.id in built_army_ids:
            continue
        if army.is_viceroy:
            continue
        # If army has been stationary for a while and near no town, build
        near_any = any(math.hypot(t.x - army.x, t.y - army.y) < config.interact_radius + 5 for t in world.towns)
        if not near_any and army.has_target is False:
            # Idle army in empty area -> build
            orders.append(f"BUILD {army.id} {army.x} {army.y}")

    return orders


def write_orders(orders: list[str]) -> None:
    """Print orders to stdout followed by 'go'."""
    for o in orders:
        sys.stdout.write(o + "\n")
    sys.stdout.write("go\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
