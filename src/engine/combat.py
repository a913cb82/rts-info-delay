"""Combat — weakness-based simultaneous death resolution."""

from __future__ import annotations

import math

import numpy as np

from engine.config import GameConfig
from engine.world import Army, World


def _brute_weakness_adj(
    armies: list[Army], R2: float, adj: dict[int, set[int]] | None
) -> dict[int, int]:
    """O(n^2) weakness (+ optional adjacency). Fallback and small-n path."""
    result: dict[int, int] = {}
    for a in armies:
        cnt = 0
        ax, ay, af, aid = a.x, a.y, a.faction, a.id
        for b in armies:
            if b.id == aid or b.faction == af:
                continue
            dx = b.x - ax
            dy = b.y - ay
            if dx * dx + dy * dy <= R2:
                cnt += 1
                if adj is not None:
                    adj[aid].add(b.id)
                    adj[b.id].add(aid)
        result[aid] = cnt
    return result


def compute_weaknesses(
    armies: list[Army], config: GameConfig
) -> dict[int, int]:
    """Return {army_id: num_enemy_armies_within_interact_radius}."""
    weaknesses, _ = _compute_weaknesses_and_adj(armies, config)
    return weaknesses


def _compute_weaknesses_and_adj(
    armies: list[Army], config: GameConfig
) -> tuple[dict[int, int], dict[int, set[int]]]:
    """Single-pass weakness + adjacency. Returns (weaknesses, adj)."""
    n = len(armies)
    if n == 0:
        return {}, {}
    radius = config.interact_radius
    R2 = (radius + 1e-9) * (radius + 1e-9)
    adj: dict[int, set[int]] = {a.id: set() for a in armies}
    if n < 400:
        return _brute_weakness_adj(armies, R2, adj), adj
    # large n: spatial hash, brute fallback on any failure
    try:
        from engine.spatial import SpatialHash
        import math as m

        sh = SpatialHash.__new__(SpatialHash)
        sh.config = config
        sh.cell_size = float(radius if radius >= 1 else 10)
        try:
            mx, my = config.map_size[0], config.map_size[1]
        except Exception:
            mx, my = 1000, 1000
        sh.width = int(m.ceil(mx / sh.cell_size))
        sh.height = int(m.ceil(my / sh.cell_size))
        sh.cells = {}
        pos = np.array([[a.x, a.y] for a in armies], dtype=float)
        sh.positions = pos
        for idx, (x, y) in enumerate(pos):
            key = (int(m.floor(x / sh.cell_size)), int(m.floor(y / sh.cell_size)))
            sh.cells.setdefault(key, []).append(idx)
        result = {}
        for a in armies:
            neigh = sh.query_radius(float(a.x), float(a.y), float(radius + 1e-9))
            cnt = 0
            for idx in neigh:
                b = armies[idx]
                if b.id == a.id or b.faction == a.faction:
                    continue
                cnt += 1
                adj[a.id].add(b.id)
                adj[b.id].add(a.id)
            result[a.id] = cnt
        return result, adj
    except Exception:
        adj = {a.id: set() for a in armies}
        return _brute_weakness_adj(armies, R2, adj), adj


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

    combat_armies = list(world.armies)
    if not combat_armies:
        return events
    # Fast path (ants-inspired sound skip): single faction means no enemies
    # anywhere, so no deaths — skip weakness/hash entirely. Common early game.
    first_faction = combat_armies[0].faction
    if all(a.faction == first_faction for a in combat_armies):
        return events

    # id->army dict: event building below does O(1) lookups instead of
    # O(n) linear scans per member (was O(n^2) total for big battles).
    by_id = {a.id: a for a in combat_armies}

    weaknesses, adj = _compute_weaknesses_and_adj(combat_armies, config)

    # Determine deaths using pre-built adjacency (no second O(n²) pass)
    dead_ids: set[int] = set()
    for a in combat_armies:
        w_a = weaknesses.get(a.id, 0)
        for eid in adj.get(a.id, set()):
            w_e = weaknesses.get(eid, 0)
            if w_e <= w_a:
                dead_ids.add(a.id)
                break

    if not dead_ids:
        return events

    # adj already built by compute_weaknesses — skip O(n²) rebuild

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
            army = by_id.get(aid)
            if army:
                combatants.append({"id": army.id, "faction": army.faction})
        # Compute battle position as centroid of dead armies or average of component
        xs = []
        ys = []
        for aid in comp:
            army = by_id.get(aid)
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
            army = by_id.get(aid)
            if army:
                events.append({"kind": "army_death", "id": army.id, "x": army.x, "y": army.y, "is_viceroy": army.is_viceroy})

    # For dead armies that were not in any component (isolated? shouldn't happen), still generate death
    remaining_dead = dead_ids - set().union(*components) if components else dead_ids
    for aid in remaining_dead:
        army = by_id.get(aid)
        if army:
            events.append({"kind": "army_death", "id": army.id, "x": army.x, "y": army.y, "is_viceroy": army.is_viceroy})
            # Also create battle for isolated dead? Not needed

    # Remove dead armies from world (single batch pass)
    world.remove_armies(dead_ids)

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
    A captured capital is demoted; captures never create capitals
    (beheading is permanent, only MOVE_CAPITAL founds new ones).
    """
    events: list[dict] = []
    if not world.armies or not world.towns:
        return events

    radius = config.interact_radius
    R2 = (radius+1e-9)*(radius+1e-9)
    captured_town_ids: set[int] = set()
    # Hoisted bookkeeping: one O(T+A) snapshot instead of per-capture
    # O(T)/O(A) scans (faction_capital + any() checks). Updated per capture.
    # Armies are static during captures, so viceroy presence is precomputed.
    capitals: dict[int, object] = {}
    for t in world.towns:
        if t.is_capital and t.faction not in capitals:
            capitals[t.faction] = t
    book = capitals
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
                # capture below (bookkept, no per-capture scans)
                events.append(_apply_capture(world, town, af, config, book))
                captured_town_ids.add(town.id)
        if captured_town_ids:
            world.mark_dirty()
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
                events.append(_apply_capture(world, town, army.faction, config, book))
                captured_town_ids.add(town.id)
        if captured_town_ids:
            world.mark_dirty()
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

            # Capture via shared bookkept helper (no per-capture scans).
            events.append(_apply_capture(world, town, army.faction, config, book))
            captured_town_ids.add(town.id)

    if captured_town_ids:
        world.mark_dirty()
    return events


def _apply_capture(world: World, town, new_faction: int, config: GameConfig, book) -> dict:
    """Apply one town capture, maintaining the hoisted bookkeeping.

    book = {faction: capital town} for old-capital demotion. Captures never
    create capitals: a captured capital is demoted and beheading is
    permanent — only MOVE_CAPITAL founds new capitals.
    """
    capitals = book
    old_faction = town.faction
    was_capital = town.is_capital
    if was_capital:
        town.is_capital = False
        if capitals.get(old_faction) is town:
            del capitals[old_faction]
    town.faction = new_faction
    town.population *= (1.0 - config.build_efficiency)
    return {
        "kind": "town_capture",
        "id": town.id,
        "x": town.x,
        "y": town.y,
        "old_faction": old_faction,
        "new_faction": new_faction,
        "was_capital": was_capital,
        "population": town.population,
    }
