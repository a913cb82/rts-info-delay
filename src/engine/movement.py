"""Movement — straight-line paths with path-blocking contacts."""

from __future__ import annotations

import math

import numpy as np
from numba import njit

from engine.config import GameConfig
from engine.world import Army, World


def _closest_approach(
    ax: float, ay: float, vx: float, vy: float,
    bx: float, by: float, wx: float, wy: float,
) -> tuple[float, float]:
    """Compute closest approach between two moving points.

    Returns (t*, min_distance) where t* ∈ [0, 1].
    P_i(t) = A + t·V_i, P_j(t) = B + t·V_j
    t* = clamp(-(D·E)/|E|², 0, 1) where D = B-A, E = V_j - V_i
    """
    dx = bx - ax
    dy = by - ay
    ex = wx - vx
    ey = wy - vy
    denom = ex * ex + ey * ey
    if denom < 1e-12:
        t_star = 0.0
        min_dist = math.hypot(dx, dy)
        return t_star, min_dist
    dot = dx * ex + dy * ey
    t_star = -dot / denom
    if t_star < 0.0:
        t_star = 0.0
    elif t_star > 1.0:
        t_star = 1.0
    rx = dx + t_star * ex
    ry = dy + t_star * ey
    min_dist = math.hypot(rx, ry)
    return t_star, min_dist


@njit
def _closest_approach_numba(
    ax: float, ay: float, vx: float, vy: float,
    bx: float, by: float, wx: float, wy: float,
) -> tuple[float, float]:
    """Numba-accelerated closest approach."""
    dx = bx - ax
    dy = by - ay
    ex = wx - vx
    ey = wy - vy
    denom = ex * ex + ey * ey
    if denom < 1e-12:
        t_star = 0.0
        min_dist = math.hypot(dx, dy)
        return t_star, min_dist
    dot = dx * ex + dy * ey
    t_star = -dot / denom
    if t_star < 0.0:
        t_star = 0.0
    elif t_star > 1.0:
        t_star = 1.0
    rx = dx + t_star * ex
    ry = dy + t_star * ey
    min_dist = math.hypot(rx, ry)
    return t_star, min_dist


def _path_blocks_army(
    army: Army, enemy: Army, radius: float
) -> tuple[bool, float]:
    """Check if army's path comes within radius of enemy."""
    if not army.has_target:
        return False, 1.0
    vx = army.target_x - army.x
    vy = army.target_y - army.y
    if enemy.has_target:
        wx = enemy.target_x - enemy.x
        wy = enemy.target_y - enemy.y
    else:
        wx, wy = 0.0, 0.0
    t_star, min_dist = _closest_approach(army.x, army.y, vx, vy, enemy.x, enemy.y, wx, wy)
    if min_dist <= radius + 1e-9:
        return True, t_star
    return False, 1.0


def _path_blocks_town(
    army: Army, town_x: float, town_y: float, radius: float
) -> tuple[bool, float]:
    """Check if army's path comes within radius of a town."""
    if not army.has_target:
        return False, 1.0
    vx = army.target_x - army.x
    vy = army.target_y - army.y
    t_star, min_dist = _closest_approach(army.x, army.y, vx, vy, town_x, town_y, 0.0, 0.0)
    if min_dist <= radius + 1e-9:
        return True, t_star
    return False, 1.0


def move_armies(world: World, config: GameConfig) -> list[dict]:
    """Advance all armies toward targets. Handle path-blocking contacts.

    Returns army_move events for each army that moved.
    Contacts resolve earliest-first. Stopped/dead party voids later contacts.
    Fresh spawns are immune.
    """
    radius = config.interact_radius
    speed = config.army_speed

    n = len(world.armies)
    if n == 0:
        return []

    # Store start positions and velocities by index
    start_x = [a.x for a in world.armies]
    start_y = [a.y for a in world.armies]
    vel_x = [0.0] * n
    vel_y = [0.0] * n
    has_target = [a.has_target for a in world.armies]
    factions = [a.faction for a in world.armies]

    moving_indices: list[int] = []
    for i, army in enumerate(world.armies):
        if not army.has_target:
            continue
        dx = army.target_x - army.x
        dy = army.target_y - army.y
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            continue
        if dist <= speed:
            vel_x[i] = dx
            vel_y[i] = dy
        else:
            scale = speed / dist
            vel_x[i] = dx * scale
            vel_y[i] = dy * scale
        moving_indices.append(i)

    if not moving_indices:
        return []

    contacts: list[tuple[float, int, int, str, float]] = []
    town_list = list(world.towns)
    # --- spatial cull: army hash for start positions (cell 60) ---
    # Town contacts reuse the army hash cells (town batch walks them), so
    # no separate town hash is built.
    use_hash = False
    sh_army = None
    try:
        from engine.spatial import SpatialHash
        # army hash — all armies (stationary can block moving)
        sh_army = SpatialHash.__new__(SpatialHash)
        sh_army.config = config
        sh_army.cell_size = 60.0
        try: mx, my = config.map_size[0], config.map_size[1]
        except: mx, my = 1000, 1000
        sh_army.width = int(math.ceil(mx / sh_army.cell_size)) if sh_army.cell_size else 1
        sh_army.height = int(math.ceil(my / sh_army.cell_size)) if sh_army.cell_size else 1
        sh_army.cells = {}
        pos_a = np.array([[start_x[i], start_y[i]] for i in range(n)], dtype=np.float64) if n else np.zeros((0,2))
        sh_army.positions = pos_a
        for idx, (x, y) in enumerate(pos_a):
            key = (int(math.floor(x / sh_army.cell_size)), int(math.floor(y / sh_army.cell_size)))
            sh_army.cells.setdefault(key, []).append(idx)
        use_hash = True
    except Exception:
        use_hash = False

    moving_set = set(moving_indices)
    # == query_radius disc cutoffs (radius*radius + 1e-9, plus 1e-9 tolerance)
    RQ2_ARMY = 110.0 * 110.0 + 2e-9
    RQ2_TOWN = 60.0 * 60.0 + 2e-9
    if use_hash:
        # Batch cell-pair evaluation: each unordered army pair whose cells
        # are within Chebyshev 2 (covers the 110 query disc at cell 60) is
        # visited once; both move directions are evaluated inline. Same
        # candidate multiset as per-army query_radius; the downstream sort
        # makes insertion order irrelevant. Saves ~2400 query calls + lists.
        cells = sh_army.cells
        for cx_cy, members in cells.items():
            cx, cy = cx_cy
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if dx < 0 or (dx == 0 and dy < 0):
                        continue
                    other = cells.get((cx + dx, cy + dy))
                    if not other:
                        continue
                    same_cell = (dx == 0 and dy == 0)
                    for ii in range(len(members)):
                        a = members[ii]
                        js = range(ii + 1, len(members)) if same_cell else range(len(other))
                        for jj in js:
                            b = other[jj]
                            a_moves = a in moving_set
                            b_moves = b in moving_set
                            if not (a_moves or b_moves):
                                continue
                            qx = start_x[b] - start_x[a]; qy = start_y[b] - start_y[a]
                            if qx * qx + qy * qy > RQ2_ARMY:
                                continue
                            if a_moves and factions[a] != factions[b]:
                                ax = start_x[a]; ay = start_y[a]; vx = vel_x[a]; vy = vel_y[a]
                                bx = start_x[b]; by = start_y[b]; wx = vel_x[b]; wy = vel_y[b]
                                ddx = bx - ax; ddy = by - ay
                                eex = wx - vx; eey = wy - vy
                                denom = eex * eex + eey * eey
                                if denom < 1e-12:
                                    min_dist = math.hypot(ddx, ddy)
                                    t_s = 0.0
                                else:
                                    dot = ddx * eex + ddy * eey
                                    t_s = -dot / denom
                                    if t_s < 0.0: t_s = 0.0
                                    elif t_s > 1.0: t_s = 1.0
                                    rx = ddx + t_s * eex
                                    ry = ddy + t_s * eey
                                    min_dist = math.hypot(rx, ry)
                                if min_dist <= radius + 1e-9:
                                    contacts.append((t_s, a, b, "army", min_dist))
                            if b_moves and factions[a] != factions[b]:
                                ax = start_x[b]; ay = start_y[b]; vx = vel_x[b]; vy = vel_y[b]
                                bx = start_x[a]; by = start_y[a]; wx = vel_x[a]; wy = vel_y[a]
                                ddx = bx - ax; ddy = by - ay
                                eex = wx - vx; eey = wy - vy
                                denom = eex * eex + eey * eey
                                if denom < 1e-12:
                                    min_dist = math.hypot(ddx, ddy)
                                    t_s = 0.0
                                else:
                                    dot = ddx * eex + ddy * eey
                                    t_s = -dot / denom
                                    if t_s < 0.0: t_s = 0.0
                                    elif t_s > 1.0: t_s = 1.0
                                    rx = ddx + t_s * eex
                                    ry = ddy + t_s * eey
                                    min_dist = math.hypot(rx, ry)
                                if min_dist <= radius + 1e-9:
                                    contacts.append((t_s, b, a, "army", min_dist))
    else:
        for mi in moving_indices:
            ax = start_x[mi]; ay = start_y[mi]; vx = vel_x[mi]; vy = vel_y[mi]; m_faction = factions[mi]
            for bi in range(n):
                if bi == mi: continue
                if factions[bi] == m_faction: continue
                t_s, min_dist = _closest_approach(ax, ay, vx, vy, start_x[bi], start_y[bi], vel_x[bi], vel_y[bi])
                if min_dist <= radius + 1e-9:
                    contacts.append((t_s, mi, bi, "army", min_dist))
    if use_hash and town_list:
        # Batch town evaluation: per town, walk army-hash cells in the 3x3
        # stencil (covers the 60 query disc at cell 60) and evaluate moving
        # enemy armies. Same pair multiset as per-army town queries.
        for ti, town in enumerate(town_list):
            tcx = int(math.floor(town.x / 60.0)); tcy = int(math.floor(town.y / 60.0))
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    members = cells.get((tcx + dx, tcy + dy))
                    if not members:
                        continue
                    for bi in members:
                        if bi not in moving_set: continue
                        if factions[bi] == town.faction: continue
                        qx = start_x[bi] - town.x; qy = start_y[bi] - town.y
                        if qx * qx + qy * qy > RQ2_TOWN:
                            continue
                        ax = start_x[bi]; ay = start_y[bi]; vx = vel_x[bi]; vy = vel_y[bi]
                        # closest approach vs stationary town
                        ddx = town.x - ax; ddy = town.y - ay
                        eex = -vx; eey = -vy
                        denom = eex * eex + eey * eey
                        if denom < 1e-12:
                            min_dist = math.hypot(ddx, ddy)
                            t_s = 0.0
                        else:
                            dot = ddx * eex + ddy * eey
                            t_s = -dot / denom
                            if t_s < 0.0: t_s = 0.0
                            elif t_s > 1.0: t_s = 1.0
                            rx = ddx + t_s * eex
                            ry = ddy + t_s * eey
                            min_dist = math.hypot(rx, ry)
                        if min_dist <= radius + 1e-9:
                            contacts.append((t_s, bi, ti, "town", min_dist))
    for mi in moving_indices:
        ax = start_x[mi]; ay = start_y[mi]; vx = vel_x[mi]; vy = vel_y[mi]; m_faction = factions[mi]
        # candidates via hash (60 for towns)
        cand_towns = range(len(town_list)) if not use_hash else []
        for ti in cand_towns:
            town = town_list[ti]
            if town.faction == m_faction: continue
            tx, ty = town.x, town.y
            # inline closest approach vs stationary (wx=wy=0)
            ddx = tx - ax; ddy = ty - ay
            eex = -vx; eey = -vy
            denom = eex * eex + eey * eey
            if denom < 1e-12:
                min_dist = math.hypot(ddx, ddy)
                t_s = 0.0
            else:
                dot = ddx * eex + ddy * eey
                t_s = -dot / denom
                if t_s < 0.0: t_s = 0.0
                elif t_s > 1.0: t_s = 1.0
                rx = ddx + t_s * eex
                ry = ddy + t_s * eey
                min_dist = math.hypot(rx, ry)
            if min_dist <= radius + 1e-9:
                contacts.append((t_s, mi, ti, "town", min_dist))

    # If no contacts, just move all moving armies full speed
    # Sort contacts by t_star then moving_idx for determinism
    contacts.sort(key=lambda c: (c[0], c[1], c[2]))

    # Resolve earliest-first with grouping for simultaneous
    stop_t: dict[int, float] = {}
    stopped: set[int] = set()
    blocker_stop: dict[int, float] = {}  # for army blockers that are moving and got stopped

    idx = 0
    eps = 1e-9
    while idx < len(contacts):
        t_cur = contacts[idx][0]
        # Gather group with same t_cur (within eps)
        group = []
        j = idx
        while j < len(contacts) and abs(contacts[j][0] - t_cur) < 1e-7:
            group.append(contacts[j])
            j += 1
        # Determine which in group should actually stop
        to_stop: list[tuple[int, float]] = []
        for t_star, mi, bi, btype, md in group:
            if mi in stopped:
                continue
            if btype == "army":
                # If blocker is an army that was already stopped at earlier time, void
                if bi in stopped:
                    bt = blocker_stop.get(bi, float('inf'))
                    if bt < t_cur - eps:
                        continue
                # otherwise, if blocker is moving and not yet stopped, it's okay (both will stop together if same t)
            # town blockers never stopped
            to_stop.append((mi, t_star))
        for mi, t_star in to_stop:
            if mi not in stopped:
                stop_t[mi] = t_star
                stopped.add(mi)
                blocker_stop[mi] = t_star
        idx = j

    events: list[dict] = []
    for mi in moving_indices:
        army = world.armies[mi]
        ax = start_x[mi]
        ay = start_y[mi]
        vx = vel_x[mi]
        vy = vel_y[mi]
        if mi in stop_t:
            t = stop_t[mi]
            nx = ax + t * vx
            ny = ay + t * vy
        else:
            nx = ax + vx
            ny = ay + vy
        # Clamp
        nx, ny = world.clamp_position(nx, ny)
        if abs(nx - ax) > 1e-9 or abs(ny - ay) > 1e-9:
            events.append({"kind": "army_move", "id": army.id, "x": nx, "y": ny, "has_target": army.has_target, "target_x": army.target_x, "target_y": army.target_y})
        army.x = nx
        army.y = ny

    return events
