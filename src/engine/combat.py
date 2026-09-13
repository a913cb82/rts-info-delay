"""Combat — weakness-based simultaneous death resolution."""

from __future__ import annotations

import math

import numpy as np

from engine.config import GameConfig
from engine.world import Army, CommandType, World


def _build_need(world: World, army: Army, config: GameConfig) -> float:
    """Size this army's BUILD order needs (0 if it holds none)."""
    for so in world.standing_orders:
        if so.command == CommandType.BUILD and so.target_id == army.id:
            try:
                return float(so.args[2]) if len(so.args) >= 3 else config.army_cost
            except (ValueError, TypeError):
                return config.army_cost
    return 0.0


def _en_route(army: Army) -> bool:
    """True when the army is still travelling to its MOVE_TO target."""
    if not army.has_target:
        return False
    return math.hypot(army.target_x - army.x, army.target_y - army.y) > 1e-9


def resolve_merges(world: World, config: GameConfig) -> None:
    """Merge co-located same-faction idle armies (lower id survives).

    Runs after movement, before combat. Viceroys never merge; armies still
    travelling never merge. BUILD needs pool onto the survivor's single
    order at the shared spot; any surplus forms a second idle army (which
    vanishes when there is none).
    """
    groups: dict[tuple[int, float, float], list[Army]] = {}
    for a in world.armies:
        if a.is_viceroy:
            continue
        groups.setdefault((a.faction, a.x, a.y), []).append(a)
    for members in groups.values():
        eligible = [a for a in members if not _en_route(a)]
        if len(eligible) < 2:
            continue
        eligible.sort(key=lambda a: a.id)
        needs = {a.id: _build_need(world, a, config) for a in eligible}
        builders = [a for a in eligible if needs[a.id] > 0.0]
        idles = [a for a in eligible if needs[a.id] <= 0.0]
        total_need = sum(needs.values())
        total_size = sum(a.size for a in eligible)
        if builders:
            # The lowest-id builder carries the pooled BUILD order;
            # the next army in line holds the surplus idle.
            survivor = builders[0]
            rest = [a for a in eligible if a.id != survivor.id]
            survivor.size = min(total_size, total_need)
            # One BUILD order for the pooled need at the shared spot.
            for so in [s for s in world.standing_orders
                       if s.command == CommandType.BUILD
                       and s.target_id in {a.id for a in eligible}]:
                world.standing_orders.remove(so)
            from engine.world import StandingOrder
            world.standing_orders.append(StandingOrder(
                command=CommandType.BUILD, target_id=survivor.id,
                target_type="army",
                args=[survivor.x, survivor.y, total_need]))
            if rest and total_need < total_size - 1e-9:
                second = rest[0]
                second.size = total_size - survivor.size
                second.has_target = False
                gone = rest[1:]
            else:
                gone = rest
        else:
            survivor = eligible[0]
            survivor.size = total_size
            survivor.has_target = False
            gone = list(eligible[1:])
        for a in gone:
            for so in [s for s in world.standing_orders if s.target_id == a.id]:
                world.standing_orders.remove(so)
            world.remove_army(a.id)
        world.mark_dirty()


def _brute_weakness_adj(
    armies: list[Army], R2: float, adj: dict[int, set[int]] | None
) -> dict[int, float]:
    """O(n^2) weakness (+ optional adjacency). Fallback and small-n path."""
    result: dict[int, float] = {}
    for a in armies:
        cnt = 0.0
        ax, ay, af, aid = a.x, a.y, a.faction, a.id
        for b in armies:
            if b.id == aid or b.faction == af:
                continue
            dx = b.x - ax
            dy = b.y - ay
            if dx * dx + dy * dy <= R2:
                cnt += b.size
                if adj is not None:
                    adj[aid].add(b.id)
                    adj[b.id].add(aid)
        result[aid] = cnt
    return result


def compute_weaknesses(
    armies: list[Army], config: GameConfig
) -> dict[int, float]:
    """Return {army_id: total enemy size within interact_radius}."""
    weaknesses, _ = _compute_weaknesses_and_adj(armies, config)
    return weaknesses


def _compute_weaknesses_and_adj(
    armies: list[Army], config: GameConfig
) -> tuple[dict[int, float], dict[int, set[int]]]:
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
            cnt = 0.0
            for idx in neigh:
                b = armies[idx]
                if b.id == a.id or b.faction == a.faction:
                    continue
                cnt += b.size
                adj[a.id].add(b.id)
                adj[b.id].add(a.id)
            result[a.id] = cnt
        return result, adj
    except Exception:
        adj = {a.id: set() for a in armies}
        return _brute_weakness_adj(armies, R2, adj), adj


def resolve_combat(
    world: World, config: GameConfig
) -> tuple[list[dict], dict[int, float]]:
    """Compute deaths from final positions.

    Returns (battle event dicts, weakness table). The table is shared
    with captures: towns read combat directly (they never contributed —
    weakness sums enemy size only). Fast paths return {} (exact:
    with no enemies anywhere, captures never consult values).
    An army dies if any enemy within interact_radius has weakness ≤ its own.
    Deaths are simultaneous — computed from snapshot of positions.
    """
    events: list[dict] = []
    if not world.armies:
        return events, {}
    radius = config.interact_radius

    combat_armies = list(world.armies)
    if not combat_armies:
        return events, {}
    # Fast path (ants-inspired sound skip): single faction means no enemies
    # anywhere, so no deaths — skip weakness/hash entirely. Common early game.
    first_faction = combat_armies[0].faction
    if all(a.faction == first_faction for a in combat_armies):
        return events, {}

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
        return events, weaknesses

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

    return events, weaknesses


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


def resolve_captures(world: World, config: GameConfig, weaknesses=None) -> list[dict]:
    """Contested captures: the weakest enemy army in range takes the town.

    After combat, each town with enemy armies within interact_radius is
    decided once: weakest-in-range enemy faction captures (ownership
    changes, population reduced by capture_loss) — unless an allied
    army in range matches its weakness (held), or enemies tie for weakest
    across factions (standoff, no capture). Same-faction ties capture.
    A captured capital is demoted; captures never create capitals
    (beheading is permanent, only MOVE_CAPITAL founds new ones).
    """
    events: list[dict] = []
    if not world.armies or not world.towns:
        return events

    radius = config.interact_radius
    R2 = (radius+1e-9)*(radius+1e-9)
    if weaknesses is None:
        # Direct calls (tests) that skip combat: same values combat would
        # have computed on these armies.
        weaknesses = compute_weaknesses(world.armies, config)
    # Hoisted bookkeeping: one O(T+A) snapshot instead of per-capture
    # O(T)/O(A) scans (faction_capital + any() checks). Updated per capture.
    # Armies are static during captures, so viceroy presence is precomputed.
    capitals: dict[int, object] = {}
    for t in world.towns:
        if t.is_capital and t.faction not in capitals:
            capitals[t.faction] = t
    book = capitals
    # Gather in-range armies per town (all factions; allies vote to hold).
    near: dict[int, list] = {t.id: [] for t in world.towns}
    # small n: brute with squared reject is faster than hash
    if len(world.armies) * len(world.towns) < 50000:
        for army in world.armies:
            ax, ay = army.x, army.y
            for town in world.towns:
                dx = town.x - ax; dy = town.y - ay
                if abs(dx) > radius+1e-9 or abs(dy) > radius+1e-9: continue
                if dx*dx + dy*dy > R2: continue
                near[town.id].append(army)
        _decide_captures(world, config, near, weaknesses, book, events)
        if events:
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
                # query already guarantees dist <=R, but double-check for exclusive zero case
                dx = town.x - army.x; dy = town.y - army.y
                if dx*dx + dy*dy > R2: continue
                near[town.id].append(army)
        _decide_captures(world, config, near, weaknesses, book, events)
        if events:
            world.mark_dirty()
        return events
    except Exception:
        pass

    for army in world.armies:
        for town in world.towns:
            dist = math.hypot(army.x - town.x, army.y - town.y)
            if dist > radius + 1e-9:
                continue
            near[town.id].append(army)

    _decide_captures(world, config, near, weaknesses, book, events)
    if events:
        world.mark_dirty()
    return events


def _decide_captures(world, config, near, weaknesses, book, events) -> None:
    """One decision per town, in world order: weakest-in-range enemy
    faction captures, unless an allied army in range matches its weakness
    (held) or enemies tie for weakest across factions (standoff)."""
    for town in world.towns:
        armies = near.get(town.id, [])
        foes = [a for a in armies if a.faction != town.faction]
        if not foes:
            continue
        min_foe = min(weaknesses.get(a.id, 0) for a in foes)
        if any(weaknesses.get(a.id, 0) <= min_foe
               for a in armies if a.faction == town.faction):
            continue  # guarded: an ally matches the best enemy
        takers = {a.faction for a in foes if weaknesses.get(a.id, 0) == min_foe}
        if len(takers) != 1:
            continue  # standoff between enemies
        events.append(_apply_capture(world, town, next(iter(takers)), config, book))


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
    town.population *= (1.0 - config.capture_loss)
    town.last_improvement *= (1.0 - config.capture_loss)  # sack loots workshops too
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
