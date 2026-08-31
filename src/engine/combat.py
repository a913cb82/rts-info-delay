"""Combat — weakness-based simultaneous death resolution."""

from __future__ import annotations

import math

import numpy as np

from engine.config import GameConfig
from engine.world import Army, World


def compute_weaknesses(
    armies: list[Army], config: GameConfig
) -> dict[int, int]:
    """Return {army_id: num_enemy_armies_within_interact_radius}."""
    result: dict[int, int] = {}
    radius = config.interact_radius
    for a in armies:
        cnt = 0
        for b in armies:
            if b.id == a.id:
                continue
            if b.faction == a.faction:
                continue
            dist = math.hypot(a.x - b.x, a.y - b.y)
            if dist <= radius + 1e-9:
                cnt += 1
        result[a.id] = cnt
    return result


def resolve_combat(
    world: World, config: GameConfig
) -> list[dict]:
    """Compute deaths from final positions. Returns battle event dicts.

    An army dies if any enemy within interact_radius has weakness ≤ its own.
    Deaths are simultaneous — computed from snapshot of positions.
    """
    events: list[dict] = []
    if not world.armies:
        return events
    radius = config.interact_radius

    # Fresh spawns are immune this turn – exclude them from combat
    combat_armies = [a for a in world.armies if not getattr(a, "is_fresh", False)]
    if not combat_armies:
        return events

    weaknesses = compute_weaknesses(combat_armies, config)

    # Determine deaths
    dead_ids: set[int] = set()
    # For each army, check enemies within radius
    for a in combat_armies:
        w_a = weaknesses.get(a.id, 0)
        # Find enemies within radius
        enemies_in_radius = _enemies_within_radius(a, combat_armies, radius)
        if not enemies_in_radius:
            continue
        # If any enemy has weakness <= w_a, then a dies
        for enemy in enemies_in_radius:
            w_e = weaknesses.get(enemy.id, 0)
            if w_e <= w_a:
                dead_ids.add(a.id)
                break

    if not dead_ids:
        return events

    # Generate battle events grouping
    # Group dead and involved armies by spatial clustering
    # Build graph where edge between combat_armies if dist <= radius and factions differ? Or just any enemy within radius regardless of faction? Use enemy condition.
    # Simpler: cluster based on any pair within radius (regardless of faction) that are both in combat_armies and at least one is dead or involved?
    # We'll cluster all combat_armies that are within radius of each other (any faction diff or same? but same faction not enemy but still could be in same battle via chained enemies)
    # Use union-find for all combat_armies where dist <= radius*2? Actually use radius directly: if dist <= radius, they are in same battle cluster if there's enemy linkage

    # We'll do BFS clustering: start from dead armies, expand to all enemies within radius recursively
    # That will group distinct battles.

    # Create adjacency for enemy within radius
    n = len(combat_armies)
    # Map id -> index
    id_to_idx = {a.id: i for i, a in enumerate(combat_armies)}
    # Build adjacency list
    adj: dict[int, set[int]] = {a.id: set() for a in combat_armies}
    for i in range(n):
        a = combat_armies[i]
        for j in range(i+1, n):
            b = combat_armies[j]
            if a.faction == b.faction:
                continue
            dist = math.hypot(a.x - b.x, a.y - b.y)
            if dist <= radius + 1e-9:
                adj[a.id].add(b.id)
                adj[b.id].add(a.id)

    # Find connected components among armies that are involved (have at least one enemy edge)
    visited: set[int] = set()
    components: list[set[int]] = []
    for a in combat_armies:
        if a.id in visited:
            continue
        if not adj[a.id]:
            continue
        # BFS
        stack = [a.id]
        comp: set[int] = set()
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp.add(cur)
            for nb in adj[cur]:
                if nb not in visited:
                    stack.append(nb)
        # Also need to include allies of those enemies that are within radius of enemies? Already via graph, but allies not directly connected (same faction not edge) but they share enemy so they connect via enemy: A1 connected to B, B connected to A2 => A1 and A2 are in same component via B. Our BFS includes that because we traverse through B.
        # However if there are two allies not connected via enemy path, they'd be separate, but they share same battle via enemy? Actually if A1 and A2 both near same B, they both connect to B, so they are same component.
        if comp:
            components.append(comp)

    # Also include isolated pairs where no adjacency? Already handled.

    # For each component, check if it contains any dead
    for comp in components:
        comp_dead = [aid for aid in comp if aid in dead_ids]
        if not comp_dead:
            continue
        # Gather combatants in this component (all ids)
        combatants = []
        for aid in comp:
            army = next((a for a in combat_armies if a.id == aid), None)
            if army:
                combatants.append({"id": army.id, "faction": army.faction})
        # Compute battle position as centroid of dead armies or average of component
        xs = []
        ys = []
        for aid in comp:
            army = next((a for a in combat_armies if a.id == aid), None)
            if army:
                xs.append(army.x)
                ys.append(army.y)
        if xs:
            bx = sum(xs) / len(xs)
            by = sum(ys) / len(ys)
        else:
            bx, by = 0.0, 0.0
        events.append({
            "kind": "battle",
            "x": bx,
            "y": by,
            "combatants": combatants,
            "killed": sorted(list(comp_dead)),
        })
        # Also generate army_death events for each dead in component
        for aid in comp_dead:
            army = next((a for a in combat_armies if a.id == aid), None)
            if army:
                events.append({"kind": "army_death", "id": army.id, "x": army.x, "y": army.y, "is_viceroy": army.is_viceroy})

    # For dead armies that were not in any component (isolated? shouldn't happen), still generate death
    remaining_dead = dead_ids - set().union(*components) if components else dead_ids
    for aid in remaining_dead:
        army = next((a for a in combat_armies if a.id == aid), None)
        if army:
            events.append({"kind": "army_death", "id": army.id, "x": army.x, "y": army.y, "is_viceroy": army.is_viceroy})
            # Also create battle for isolated dead? Not needed

    # Remove dead armies from world
    # Also need to clean standing orders for dead armies (world.remove_army will handle per id but we batch)
    for aid in dead_ids:
        world.remove_army(aid)

    # For fresh armies, we still need to keep them; they remain in world

    return events


def _enemies_within_radius(
    army: Army, armies: list[Army], radius: float
) -> list[Army]:
    """Return enemy armies within radius of army."""
    res: list[Army] = []
    for other in armies:
        if other.id == army.id:
            continue
        if other.faction == army.faction:
            continue
        dist = math.hypot(army.x - other.x, army.y - other.y)
        if dist <= radius + 1e-9:
            res.append(other)
    return res


def resolve_captures(world: World, config: GameConfig) -> list[dict]:
    """Capture enemy towns within interact_radius of surviving armies.

    After combat, surviving armies within interact_radius of an enemy town
    capture it: ownership changes, population reduced by build_efficiency.
    Capital status transfers to captor if the captured town was a capital.
    """
    events: list[dict] = []
    if not world.armies or not world.towns:
        return events

    radius = config.interact_radius
    captured_town_ids: set[int] = set()

    for army in world.armies:
        for town in world.towns:
            if town.id in captured_town_ids:
                continue  # already captured this turn
            if town.faction == army.faction:
                continue  # can't capture own town
            dist = math.hypot(army.x - town.x, army.y - town.y)
            if dist > radius + 1e-9:
                continue

            # Capture!
            old_faction = town.faction
            was_capital = town.is_capital
            old_pop = town.population

            # If this town was a capital, demote it for old owner
            if was_capital:
                town.is_capital = False

            # Change ownership
            town.faction = army.faction

            # Reduce population by build_efficiency
            town.population *= (1.0 - config.build_efficiency)

            # If captor has no capital AND has a viceroy or town alive, make this the new capital
            # If captor is completely dead (no towns, no viceroy), don't revive them
            captor_capital = world.faction_capital(army.faction)
            if captor_capital is None:
                has_towns = any(t.faction == army.faction for t in world.towns)
                has_viceroy = any(a.is_viceroy and a.faction == army.faction for a in world.armies)
                if has_towns or has_viceroy:
                    town.is_capital = True

            captured_town_ids.add(town.id)
            events.append({
                "kind": "town_capture",
                "id": town.id,
                "x": town.x,
                "y": town.y,
                "old_faction": old_faction,
                "new_faction": army.faction,
                "was_capital": was_capital,
                "population": town.population,
            })

    return events
