"""Economy — fitted realism growth (base curve + directed interactions),
TRAIN, BUILD, town death.

Growth model (fitted to bench/growth_realism, 2026-09-12; params are
config defaults, all 2 significant figures):

    g(P)   = a*P - (a/K)*P^2 - c*P^3                (a lone town)
    W(i,j) = alpha*P_i*sig((P_j-P_i)/gate) * e^(-(d/rho)^2) * win(d)
           + mu*P_i*P_j/(P_i+P_j)*(P_i-P_j) * e^(-d/rho) * win(d)
    net_i  = g(P_i) + sum_j W(i,j)

    win(d) = sig(D^2/d^2 - D^2/(D^2-d^2)),  D = info_speed (150 km)

``win`` is a single C-infinity curve with one constant: exactly 1 at
d=0, exactly 0 at d=D, and pairs at d >= D contribute exactly zero
(hard interaction bound, also the engine's neighbour cutoff).
The first term is market access (directed: bigger places serve smaller
ones); the second is gravity migration toward larger towns (population
conserving). There is no separate crowding tax: fewer than ~60 km the
access halo dominates, and a big city's pull drains its neighbours
(the urban graveyard circuit).
"""

from __future__ import annotations

import math

import numpy as np

from engine.config import GameConfig
from engine.world import Army, CommandType, Town, World


def base_growth(population: float, config: GameConfig) -> float:
    """Net growth per turn of a lone town: aP - (a/K)P^2 - cP^3."""
    a = config.population_growth
    b = a / config.land_capacity
    return population * (a - b * population - config.urban_sink * population * population)


def interaction_window(d2: float, config: GameConfig) -> float:
    """Hard-bound C-infinity window: 1 at d=0, 0 at d >= info_speed."""
    dcut2 = config.info_speed * config.info_speed
    if d2 >= dcut2:
        return 0.0
    if d2 <= 0.0:
        return 1.0
    x = dcut2 / d2 - dcut2 / (dcut2 - d2)
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _sigmoid(x: float) -> float:
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def pair_gain(pi: float, pj: float, d2: float, config: GameConfig) -> float:
    """Influence of town j on town i: access (directed) + migration.

    Exact stacks (d2 == 0) are the one non-smooth rule kept for engine
    invariants: the smaller town dies, the larger ignores the neighbour
    (maps never stack; a viceroy founding onto a friendly town merges).
    """
    if d2 <= 1e-18:
        return 0.0 if pj <= pi else -1e6
    win = interaction_window(d2, config)
    if win <= 0.0:
        return 0.0
    rho = config.kernel_scale
    access = (config.access_alpha * pi
              * _sigmoid((pj - pi) / config.service_gate)
              * math.exp(-d2 / (rho * rho)) * win)
    total = pi + pj
    mig = (config.migration_mu * (pi * pj / total if total > 0.0 else 0.0)
           * (pi - pj) * math.exp(-math.sqrt(d2) / rho) * win)
    return access + mig


# ---------------------------------------------------------------------------
# Pairwise kernels (numba when available; numpy/python fallbacks otherwise).
# The distance matrix and the identity-validated caches are shared by both
# crowding_net (single row) and crowding_nets_batch (full matrix).

_dist_cache: dict = {}  # id(all_towns) -> [towns_ref, D, ids]


def _same_towns(ref: list[Town] | None, all_towns: list[Town]) -> bool:
    if ref is None or len(ref) != len(all_towns):
        return False
    for a, b in zip(ref, all_towns):
        if a is not b:
            return False
    return True


def _get_dist_matrix(all_towns: list[Town]):
    """Cached NxN distance matrix keyed by list identity + full element check."""
    e = _dist_cache.get(id(all_towns))
    if e is not None and _same_towns(e[0], all_towns):
        return e[1], e[2]
    xs = np.array([t.x for t in all_towns], dtype=np.float64)
    ys = np.array([t.y for t in all_towns], dtype=np.float64)
    ids = np.array([t.id for t in all_towns], dtype=np.int64)
    dx = xs[:, None] - xs[None, :]
    dy = ys[:, None] - ys[None, :]
    D = np.sqrt(dx * dx + dy * dy)
    _dist_cache[id(all_towns)] = [list(all_towns), D, ids]
    if len(_dist_cache) > 20:
        del _dist_cache[next(iter(_dist_cache))]
    return D, ids


def _win_np(d2: np.ndarray, dcut2: float) -> np.ndarray:
    with np.errstate(divide="ignore", over="ignore"):
        pos = np.maximum(d2, 1e-300)
        rest = np.maximum(dcut2 - d2, 1e-300)
        x = dcut2 / pos - dcut2 / rest
        w = np.where(x >= 0.0,
                     1.0 / (1.0 + np.exp(-np.minimum(x, 700.0))),
                     np.exp(np.maximum(x, -700.0)) / (1.0 + np.exp(np.maximum(x, -700.0))))
    return np.where(d2 >= dcut2, 0.0, w)


def _nets_np(all_towns: list[Town], config: GameConfig) -> list[float]:
    """Vectorised numpy fallback for the batch path (no numba)."""
    n = len(all_towns)
    pops = np.array([t.population for t in all_towns], dtype=np.float64)
    a = config.population_growth
    b = a / config.land_capacity
    c = config.urban_sink
    g = pops * (a - b * pops - c * pops * pops)
    if n == 1:
        return [float(g[0])]
    D, _ = _get_dist_matrix(all_towns)
    dcut2 = config.info_speed * config.info_speed
    rho = config.kernel_scale
    win = _win_np(D * D, dcut2)
    gate = 1.0 / (1.0 + np.exp(-np.clip((pops[None, :] - pops[:, None]) / config.service_gate, -700, 700)))
    access = config.access_alpha * pops[:, None] * gate * np.exp(-(D * D) / (rho * rho)) * win
    total = pops[:, None] + pops[None, :]
    mig = (config.migration_mu
           * np.where(total > 0, pops[:, None] * pops[None, :] / total, 0.0)
           * (pops[:, None] - pops[None, :]) * np.exp(-D / rho) * win)
    stack = D * D <= 1e-18
    # exact stacks: smaller dies, larger ignores the neighbour
    W = np.where(stack & (pops[None, :] > pops[:, None]), -1e6,
                 np.where(stack, 0.0, access + mig))
    np.fill_diagonal(W, 0.0)
    return (g + W.sum(axis=1)).tolist()


try:
    import numba

    @numba.njit(cache=True)
    def _sig_nb(x):
        if x >= 0.0:
            return 1.0 / (1.0 + math.exp(-x))
        e = math.exp(x)
        return e / (1.0 + e)

    @numba.njit(cache=True)
    def _win_nb(d2, dcut2):
        if d2 >= dcut2:
            return 0.0
        if d2 <= 0.0:
            return 1.0
        x = dcut2 / d2 - dcut2 / (dcut2 - d2)
        if x >= 0.0:
            return 1.0 / (1.0 + math.exp(-x))
        e = math.exp(x)
        return e / (1.0 + e)

    @numba.njit(cache=True)
    def _batch_kernel(D, pops, a, b, c, alpha, gate, rho, mu, dcut2, out):
        n = pops.shape[0]
        rho2 = rho * rho
        for i in range(n):
            pi = pops[i]
            s = pi * (a - b * pi - c * pi * pi)
            for j in range(n):
                if j == i:
                    continue
                d2 = D[i, j] * D[i, j]
                if d2 <= 1e-18:
                    if pops[j] > pi:
                        s -= 1e6
                    continue
                if d2 >= dcut2:
                    continue
                w = _win_nb(d2, dcut2)
                tot = pi + pops[j]
                s += (alpha * pi * _sig_nb((pops[j] - pi) / gate)
                      * math.exp(-d2 / rho2) * w)
                if tot > 0.0:
                    s += (mu * pi * pops[j] / tot * (pi - pops[j])
                          * math.exp(-D[i, j] / rho) * w)
            out[i] = s

    @numba.njit(cache=True)
    def _row_kernel(D_row, pops, idx, a, b, c, alpha, gate, rho, mu, dcut2):
        n = pops.shape[0]
        rho2 = rho * rho
        pi = pops[idx]
        s = pi * (a - b * pi - c * pi * pi)
        for j in range(n):
            if j == idx:
                continue
            d2 = D_row[j] * D_row[j]
            if d2 <= 1e-18:
                if pops[j] > pi:
                    s -= 1e6
                continue
            if d2 >= dcut2:
                continue
            w = _win_nb(d2, dcut2)
            tot = pi + pops[j]
            s += alpha * pi * _sig_nb((pops[j] - pi) / gate) * math.exp(-d2 / rho2) * w
            if tot > 0.0:
                s += mu * pi * pops[j] / tot * (pi - pops[j]) * math.exp(-D_row[j] / rho) * w
        return s

    # Pre-compile so the first real call never pays JIT latency.
    try:
        _wD = np.zeros((2, 2), dtype=np.float64)
        _wp = np.array([500.0, 500.0], dtype=np.float64)
        _wo = np.zeros(2, dtype=np.float64)
        _batch_kernel(_wD, _wp, 8.2e-5, 8.2e-5 / 3e5, 1e-14, 1.8e-5, 30.0, 270.0, 2.7e-9, 22500.0, _wo)
        _row_kernel(_wD[0], _wp, 0, 8.2e-5, 8.2e-5 / 3e5, 1e-14, 1.8e-5, 30.0, 270.0, 2.7e-9, 22500.0)
        del _wD, _wp, _wo
    except Exception:
        pass
except Exception:  # pragma: no cover
    _batch_kernel = None  # type: ignore
    _row_kernel = None  # type: ignore


def crowding_net(town: Town, all_towns: list[Town], config: GameConfig) -> float:
    """Net growth per turn for one town among all_towns (its neighbours only)."""
    if not all_towns or len(all_towns) <= 1:
        return base_growth(town.population, config)
    pops = [t.population for t in all_towns]
    try:
        if _row_kernel is not None:
            D, ids = _get_dist_matrix(all_towns)
            matches = np.where(ids == town.id)[0]
            if matches.size > 0:
                idx = int(matches[0])
                pn = np.array(pops, dtype=np.float64)
                a = config.population_growth
                return float(_row_kernel(
                    D[idx], pn, idx, a, a / config.land_capacity,
                    config.urban_sink, config.access_alpha, config.service_gate,
                    config.kernel_scale, config.migration_mu,
                    config.info_speed * config.info_speed))
            raise RuntimeError("town not in matrix")
        else:
            raise RuntimeError("no numba")
    except Exception:
        pass
    # pure-python fallback: correct for any size, slow but O(n)
    s = base_growth(town.population, config)
    pi = town.population
    for other in all_towns:
        if other is town or other.id == town.id:
            continue
        dx = town.x - other.x
        dy = town.y - other.y
        s += pair_gain(pi, other.population, dx * dx + dy * dy, config)
    return s


def crowding_nets_batch(all_towns: list[Town], config: GameConfig) -> list[float]:
    """Per-town net growth for the whole town list (fast path per step)."""
    n = len(all_towns)
    if n == 0:
        return []
    if n == 1:
        return [base_growth(all_towns[0].population, config)]
    pops = np.array([t.population for t in all_towns], dtype=np.float64)
    a = config.population_growth
    b = a / config.land_capacity
    c = config.urban_sink
    if _batch_kernel is not None:
        try:
            D, _ = _get_dist_matrix(all_towns)
            out = np.empty(n, dtype=np.float64)
            _batch_kernel(D, pops, a, b, c, config.access_alpha,
                          config.service_gate, config.kernel_scale,
                          config.migration_mu,
                          config.info_speed * config.info_speed, out)
            return out.tolist()
        except Exception:
            pass
    return _nets_np(all_towns, config)


def apply_growth(world: World, config: GameConfig) -> list[dict]:
    events: list[dict] = []
    if not world.towns:
        return events
    snapshot = list(world.towns)
    try:
        nets = crowding_nets_batch(snapshot, config)
    except Exception:
        nets = [crowding_net(t, snapshot, config) for t in snapshot]
    for t, net in zip(snapshot, nets):
        t.population += net
        if abs(net) > 1e-9:
            events.append({"kind": "pop_change", "id": t.id, "population": t.population})
    dead = [t for t in list(world.towns) if t.population <= config.town_min_population]
    for t in dead:
        was_capital = t.is_capital
        world.remove_town(t.id)
        events.append({"kind": "town_death", "id": t.id, "x": t.x, "y": t.y,
                       "faction": t.faction, "is_capital": was_capital})
    return events


def apply_train(world: World, config: GameConfig, pre_capture_factions: dict[int, int] | None = None) -> list[dict]:
    events: list[dict] = []
    train_orders = [so for so in world.standing_orders if so.command == CommandType.TRAIN and so.target_type == "town"]
    if not train_orders:
        return events
    trained_this_turn: set[int] = set()  # 1 army / town / turn cap
    for so in list(train_orders):
        if so not in world.standing_orders:
            continue
        if so.target_id in trained_this_turn:
            # Extra TRAINs at the same town in the same turn are
            # discarded: removed, no deduction, no spawn.
            world.standing_orders.remove(so)
            continue
        town = world.get_town(so.target_id)
        if town is None:
            if so in world.standing_orders:
                world.standing_orders.remove(so)
            continue
        # Use pre-capture faction if available (capture runs before economy)
        original_faction = town.faction
        if pre_capture_factions and so.target_id in pre_capture_factions:
            original_faction = pre_capture_factions[so.target_id]
        if so.args and len(so.args) >= 1:
            try:
                requested_faction = int(float(so.args[0]))
                if requested_faction != original_faction:
                    continue
            except (ValueError, TypeError):
                pass
        trained_this_turn.add(so.target_id)
        original_pop = town.population
        town.population -= config.army_cost
        should_spawn = original_pop >= config.army_cost - 1e-9
        if should_spawn:
            new_id = world.allocate_id()
            army = Army(id=new_id, faction=original_faction, x=town.x, y=town.y, is_viceroy=False)
            world.armies.append(army)
            events.append({"kind": "army_spawn", "id": army.id, "faction": army.faction, "x": army.x, "y": army.y, "is_viceroy": False})
        if town.population <= config.town_min_population:
            tid = town.id
            tx, ty = town.x, town.y
            tf = town.faction
            was_capital = town.is_capital
            world.remove_town(tid)
            events.append({"kind": "town_death", "id": tid, "x": tx, "y": ty, "faction": tf, "is_capital": was_capital})
        # TRAIN is one-shot: remove standing order after execution
        if so in world.standing_orders:
            world.standing_orders.remove(so)
    return events


def apply_build(world: World, config: GameConfig) -> list[dict]:
    events: list[dict] = []
    build_orders = [so for so in world.standing_orders if so.command == CommandType.BUILD]
    if not build_orders:
        return events
    for so in list(build_orders):
        if so not in world.standing_orders:
            continue
        army = world.get_army(so.target_id)
        if army is None:
            if so in world.standing_orders:
                world.standing_orders.remove(so)
            continue
        if len(so.args) >= 2:
            if len(so.args) >= 3:
                try:
                    maybe_faction = int(so.args[0])
                    if maybe_faction == army.faction and len(so.args) == 3:
                        tx, ty = float(so.args[1]), float(so.args[2])
                    else:
                        tx, ty = float(so.args[0]), float(so.args[1])
                except Exception:
                    tx, ty = float(so.args[0]), float(so.args[1])
            else:
                tx, ty = float(so.args[0]), float(so.args[1])
        else:
            tx, ty = army.x, army.y
        tx, ty = world.clamp_position(tx, ty)
        dist = math.hypot(army.x - tx, army.y - ty)
        if dist > config.interact_radius + 1e-9:
            if so in world.standing_orders:
                world.standing_orders.remove(so)
            continue
        found_town = None
        for t in world.towns:
            if math.hypot(t.x - tx, t.y - ty) <= config.interact_radius + 1e-9:
                found_town = t
                break
        if found_town is not None and found_town.faction != army.faction:
            # Blocked by an enemy town: hold (keep the standing order)
            # until it is captured or gone. Nothing consumed, no event.
            continue
        aid = army.id
        ax, ay = army.x, army.y
        world.remove_army(aid)
        events.append({"kind": "army_death", "id": aid, "x": ax, "y": ay})
        if so in world.standing_orders:
            try:
                world.standing_orders.remove(so)
            except ValueError:
                pass
        if found_town is not None:
            found_town.population += config.army_cost * config.build_efficiency
        else:
            new_id = world.allocate_id()
            new_town = Town(id=new_id, faction=army.faction, x=tx, y=ty, population=config.army_cost * config.build_efficiency, is_capital=False)
            world.towns.append(new_town)
            events.append({"kind": "town_spawn", "id": new_town.id, "faction": new_town.faction, "x": new_town.x, "y": new_town.y, "population": new_town.population, "is_capital": False})
    return events


def check_town_death(*args, **kwargs) -> bool | list[dict]:
    if args and isinstance(args[0], World):
        world: World = args[0]
        config: GameConfig = args[1] if len(args) > 1 else kwargs.get("config")  # type: ignore
        if config is None:
            raise TypeError("config required")
        dead_ids: list[int] = []
        for t in list(world.towns):
            if t.population <= config.town_min_population:
                dead_ids.append(t.id)
        for tid in dead_ids:
            world.remove_town(tid)
        return len(dead_ids) > 0  # type: ignore
    else:
        town: Town = args[0]  # type: ignore
        config: GameConfig = args[1] if len(args) > 1 else kwargs.get("config")  # type: ignore
        if config is None:
            raise TypeError("config required")
        return town.population <= config.town_min_population
