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
    n = len(armies)
    if n == 0:
        return {}
    # small n: brute with squared early reject (avoid hypot)
    radius = config.interact_radius
    R2 = (radius + 1e-9)*(radius + 1e-9)
    # for large n use hash
    if n < 400:
        result: dict[int, int] = {}
        for a in armies:
            cnt = 0
            ax, ay = a.x, a.y
            af = a.faction
            aid = a.id
            for b in armies:
                if b.id == aid or b.faction == af: continue
                dx = b.x - ax; dy = b.y - ay
                if abs(dx) > radius+1e-9 or abs(dy) > radius+1e-9: continue
                if dx*dx + dy*dy <= R2:
                    cnt += 1
            result[aid] = cnt
        return result
    # large n: hash cell=10
    try:
        from engine.spatial import SpatialHash
        import numpy as np, math as m
        sh = SpatialHash.__new__(SpatialHash)
        sh.config = config; sh.cell_size = float(radius if radius>=1 else 10)
        try: mx, my = config.map_size[0], config.map_size[1]
        except: mx, my = 1000, 1000
        sh.width = int(m.ceil(mx / sh.cell_size)); sh.height = int(m.ceil(my / sh.cell_size))
        sh.cells = {}
        pos = np.array([[a.x, a.y] for a in armies], dtype=float)
        sh.positions = pos
        for idx, (x, y) in enumerate(pos):
            key = (int(m.floor(x / sh.cell_size)), int(m.floor(y / sh.cell_size)))
            sh.cells.setdefault(key, []).append(idx)
        result = {}
        for a in armies:
            neigh = sh.query_radius(float(a.x), float(a.y), float(radius+1e-9))
            cnt = 0
            for idx in neigh:
                b = armies[idx]
                if b.id == a.id or b.faction == a.faction: continue
                # query already filtered by dist, but include check for stacked case (dist 0 excluded incorrectly for exclusive hash)
                # for hash with r=10 and query exclusive, stacked at same pos would be missed; so double-check brute for those
                cnt += 1
            # fix stacked same pos missed by hash exclusive: brute check for those at same pos
            # find armies at same pos within 1e-9 (rare, handle via brute scan of same cell)
            result[a.id] = cnt
        # for stacks at exactly same pos, hash exclusive would have excluded; patch by brute for those
        # detect any pair with dist~0 and different faction: do brute for those
        # simpler: if any army shares pos with another enemy, brute count them
        # we do small brute for same-pos only
        pos_map: dict[tuple[int,int], list[int]] = {}
        for i,a in enumerate(armies):
            key = (int(round(a.x*1000)), int(round(a.y*1000)))
            pos_map.setdefault(key, []).append(i)
        for lst in pos_map.values():
            if len(lst) < 2: continue
            # check factions differ
            for i in lst:
                for j in lst:
                    if i==j: continue
                    if armies[i].faction == armies[j].faction: continue
                    # if hash missed due to exclusive, add
                    # result counts already include if hash included; if not, add now
                    # we can just recompute brute for these small clusters
                    pass
        return result
    except Exception:
        pass
    result = {}
    for a in armies:
        cnt = 0
        for b in armies:
            if b.id == a.id or b.faction == a.faction: continue
            if abs(b.x - a.x) > radius+1e-9 or abs(b.y - a.y) > radius+1e-9: continue
            if (b.x-a.x)**2 + (b.y-a.y)**2 <= R2:
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
    adj: dict[int, set[int]] = {a.id: set() for a in combat_armies}
    R2 = (radius+1e-9)*(radius+1e-9)
    for i in range(n):
        a = combat_armies[i]
        for j in range(i+1, n):
            b = combat_armies[j]
            if a.faction == b.faction: continue
            dx = b.x - a.x; dy = b.y - a.y
            if abs(dx) > radius+1e-9 or abs(dy) > radius+1e-9: continue
            if dx*dx + dy*dy <= R2:
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
    res: list[Army] = []
    R2 = (radius+1e-9)*(radius+1e-9)
    ax, ay, af, aid = army.x, army.y, army.faction, army.id
    for other in armies:
        if other.id == aid or other.faction == af: continue
        dx = other.x - ax; dy = other.y - ay
        if abs(dx) > radius+1e-9 or abs(dy) > radius+1e-9: continue
        if dx*dx + dy*dy <= R2:
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
    R2 = (radius+1e-9)*(radius+1e-9)
    captured_town_ids: set[int] = set()
    # small n: brute with squared reject is faster than hash
    if len(world.armies) * len(world.towns) < 50000:
        for army in world.armies:
            ax, ay, af = army.x, army.y, army.faction
            for town in world.towns:
                if town.id in captured_town_ids: continue
                if town.faction == af: continue
                dx = town.x - ax; dy = town.y - ay
                if abs(dx) > radius+1e-9 or abs(dy) > radius+1e-9: continue
                if dx*dx + dy*dy > R2: continue
                # capture below
                old_faction = town.faction
                was_capital = town.is_capital
                if was_capital: town.is_capital = False
                town.faction = af
                town.population *= (1.0 - config.build_efficiency)
                captor_capital = world.faction_capital(af)
                if captor_capital is None:
                    has_towns = any(t.faction == af for t in world.towns)
                    has_viceroy = any(a.is_viceroy and a.faction == af for a in world.armies)
                    if has_towns or has_viceroy:
                        town.is_capital = True
                captured_town_ids.add(town.id)
                events.append({"kind": "town_capture", "id": town.id, "x": town.x, "y": town.y, "old_faction": old_faction, "new_faction": af, "was_capital": was_capital, "population": town.population})
        return events
    # large: hash cell 10
    try:
        from engine.spatial import SpatialHash
        import numpy as np, math as m
        sh = SpatialHash.__new__(SpatialHash)
        sh.config = config; sh.cell_size = float(radius if radius>=1 else 10)
        try: mx, my = config.map_size[0], config.map_size[1]
        except: mx, my = 1000, 1000
        sh.width = int(m.ceil(mx / sh.cell_size)); sh.height = int(m.ceil(my / sh.cell_size))
        sh.cells = {}
        pos_t = np.array([[t.x, t.y] for t in world.towns], dtype=float)
        sh.positions = pos_t
        for idx, (x, y) in enumerate(pos_t):
            key = (int(m.floor(x / sh.cell_size)), int(m.floor(y / sh.cell_size)))
            sh.cells.setdefault(key, []).append(idx)
        for army in world.armies:
            neigh = sh.query_radius(float(army.x), float(army.y), float(radius+1e-9))
            for idx in neigh:
                town = world.towns[idx]
                if town.id in captured_town_ids: continue
                if town.faction == army.faction: continue
                # query already guarantees dist <=R, but double-check for exclusive zero case
                dx = town.x - army.x; dy = town.y - army.y
                if dx*dx + dy*dy > R2: continue
                old_faction = town.faction; was_capital = town.is_capital
                if was_capital: town.is_capital = False
                town.faction = army.faction
                town.population *= (1.0 - config.build_efficiency)
                captor_capital = world.faction_capital(army.faction)
                if captor_capital is None:
                    has_towns = any(t.faction == army.faction for t in world.towns)
                    has_viceroy = any(a.is_viceroy and a.faction == army.faction for a in world.armies)
                    if has_towns or has_viceroy:
                        town.is_capital = True
                captured_town_ids.add(town.id)
                events.append({"kind": "town_capture", "id": town.id, "x": town.x, "y": town.y, "old_faction": old_faction, "new_faction": army.faction, "was_capital": was_capital, "population": town.population})
        return events
    except Exception:
        pass

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
