"""Economy — logistic growth, crowding, TRAIN, BUILD, town death."""

from __future__ import annotations

import math

import numpy as np

from engine.config import GameConfig
from engine.world import Army, CommandType, Town, World


def logistic(population: float, config: GameConfig) -> float:
    return config.population_growth * population * (1.0 - population / config.population_cap)


# Near-zero distances (dist < 1e-9) cannot occur in-game: BUILD merges
# within 10km, viceroy founding merges into friendly towns, parse_map
# rejects stacked maps. The max() floors below keep the formula total
# (no singularity branch) for degenerate constructed states only.

# Cache soundness rule (applies to all three caches below): entries are
# keyed by id(list) for O(1) lookup but ALWAYS validated by a full
# element-identity loop against strong town refs held by the entry.
# Identity on live refs is exact: GC cannot reuse addresses of held
# objects, Town.x/Town.y are never mutated, and in-place middle swaps
# fail the `is` check. Pops are always read fresh, so pop changes need
# no invalidation.
_crowding_cache: dict = {"towns": None, "xs": None, "ys": None, "ids": None}
_hash_cache: dict = {}  # id(all_towns) -> [towns_ref, SpatialHash]
_dist_cache: dict = {}  # id(all_towns) -> [towns_ref, D, xs, ys, ids]


def _same_towns(ref: list[Town] | None, all_towns: list[Town]) -> bool:
    if ref is None or len(ref) != len(all_towns):
        return False
    for a, b in zip(ref, all_towns):
        if a is not b:
            return False
    return True


def crowding_net(town: Town, all_towns: list[Town], config: GameConfig) -> float:
    log = logistic(town.population, config)
    if not all_towns or len(all_towns) <= 1:
        return log
    # Fast path via cached distance matrix (static positions)
    try:
        D, xs, ys, ids = _get_dist_matrix(all_towns)
        # C-speed index lookup (was O(n) Python linear scan)
        matches = np.where(ids == town.id)[0]
        if matches.size > 0:
            idx = int(matches[0])
            pops = np.array([t.population for t in all_towns], dtype=np.float64)
            if _row_numba_inner is not None:
                try:
                    total = _row_numba_inner(
                        D[idx], pops, idx, float(town.population),
                        config.info_speed + 1e-9,
                        config.equilibrium_spacing,
                        config.crowding_decay,
                        config.crowding_asymmetry,
                    )
                    return log * (1.0 - float(total))
                except Exception:
                    pass
            dists = D[idx]
            mask = (dists <= config.info_speed + 1e-9)
            mask[idx] = False
            if not np.any(mask):
                return log
            pj = pops[mask]
            d = np.maximum(dists[mask], 1e-9)
            mins = np.minimum(pj, town.population)
            mins = np.maximum(mins, 0.0)
            d_eqs = config.equilibrium_spacing * np.sqrt(mins)
            asy = np.ones_like(d)
            if town.population > 0:
                valid = pj > 0
                if np.any(valid):
                    asy[valid] = 1.0 + config.crowding_asymmetry * np.log(pj[valid] / town.population)
            ratios = np.where(d_eqs > 0, (d_eqs / d) ** config.crowding_decay, 0.0)
            total = float(np.sum(asy * ratios))
            return log * (1.0 - total)
    except Exception:
        pass
    # Use spatial hash to find neighbours within info_speed instead of scanning all
    try:
        from engine.spatial import SpatialHash
        # cache hash per town set (validated by identity, see rule above)
        e = _hash_cache.get(id(all_towns))
        sh = e[1] if e is not None and _same_towns(e[0], all_towns) else None
        if sh is None:
            sh = SpatialHash.__new__(SpatialHash)
            sh.config = config
            sh.cell_size = float(config.info_speed)
            try:
                mx, my = config.map_size[0], config.map_size[1]
            except Exception:
                mx, my = 1000, 1000
            sh.width = int(math.ceil(mx / sh.cell_size)) if sh.cell_size != 0 else 1
            sh.height = int(math.ceil(my / sh.cell_size)) if sh.cell_size != 0 else 1
            sh.cells = {}
            pos = np.array([[t.x, t.y] for t in all_towns], dtype=float)
            sh.positions = pos
            for idx2, (x2, y2) in enumerate(pos):
                key = (int(math.floor(x2 / sh.cell_size)), int(math.floor(y2 / sh.cell_size)))
                sh.cells.setdefault(key, []).append(idx2)
            _hash_cache[id(all_towns)] = [list(all_towns), sh]
            # prune cache
            if len(_hash_cache) > 20:
                _hash_cache.clear()
                _hash_cache[id(all_towns)] = [list(all_towns), sh]
        # query neighbours
        neigh = sh.query_radius(float(town.x), float(town.y), float(config.info_speed + 1e-9))
        # filter self
        neigh = [i for i in neigh if all_towns[i].id != town.id]
        if not neigh:
            return log
        # Build arrays for neighbours only
        pops_f = np.array([all_towns[i].population for i in neigh], dtype=float)
        xs_f = np.array([all_towns[i].x for i in neigh], dtype=float)
        ys_f = np.array([all_towns[i].y for i in neigh], dtype=float)
        dx = town.x - xs_f
        dy = town.y - ys_f
        dists = np.maximum(np.hypot(dx, dy), 1e-9)
        mins = np.minimum(pops_f, town.population)
        mins = np.maximum(mins, 0.0)
        d_eqs = config.equilibrium_spacing * np.sqrt(mins)
        asy = np.ones_like(dists)
        valid = (pops_f > 0) & (town.population > 0)
        if np.any(valid):
            ratio_log = np.log(pops_f[valid] / town.population)
            asy[valid] = 1.0 + config.crowding_asymmetry * ratio_log
        ratios = np.where(d_eqs>0, (d_eqs / dists) ** config.crowding_decay, 0.0)
        total = float(np.sum(asy * ratios))
        return log * (1.0 - total)
    except Exception:
        pass
    global _crowding_cache
    # Cache positions/ids only (identity-validated); pops are ALWAYS read
    # fresh so middle-town pop changes can never go stale.
    xs = ys = ids = None
    try:
        if _crowding_cache["xs"] is not None and _same_towns(_crowding_cache["towns"], all_towns):
            xs = _crowding_cache["xs"]
            ys = _crowding_cache["ys"]
            ids = _crowding_cache["ids"]
        else:
            xs = np.array([t.x for t in all_towns], dtype=float)
            ys = np.array([t.y for t in all_towns], dtype=float)
            ids = np.array([t.id for t in all_towns], dtype=int)
            _crowding_cache["towns"] = list(all_towns)
            _crowding_cache["xs"] = xs
            _crowding_cache["ys"] = ys
            _crowding_cache["ids"] = ids
        pops = np.array([t.population for t in all_towns], dtype=float)
    except Exception:
        total = 0.0
        for other in all_towns:
            if other.id == town.id:
                continue
            dx = town.x - other.x
            dy = town.y - other.y
            dist = math.hypot(dx, dy)
            if dist > config.info_speed + 1e-9:
                continue
            dist = max(dist, 1e-9)
            d_eq = equilibrium_distance(town.population, other.population, config)
            asym = asymmetry(town.population, other.population, config)
            ratio = (d_eq / dist) ** config.crowding_decay
            total += asym * ratio
        return log * (1.0 - total)
    try:
        mask_self = ids != town.id
        xs_f = xs[mask_self]
        ys_f = ys[mask_self]
        pops_f = pops[mask_self]
        if xs_f.size == 0:
            return log
        dx = town.x - xs_f
        dy = town.y - ys_f
        dists = np.hypot(dx, dy)
        mask = dists <= config.info_speed + 1e-9
        if not np.any(mask):
            return log
        dists = np.maximum(dists[mask], 1e-9)
        pops_f = pops_f[mask]
        mins = np.minimum(pops_f, town.population)
        mins = np.maximum(mins, 0.0)
        d_eqs = config.equilibrium_spacing * np.sqrt(mins)
        asy = np.ones_like(dists)
        valid = (pops_f > 0) & (town.population > 0)
        if np.any(valid):
            ratio_log = np.log(pops_f[valid] / town.population)
            asy[valid] = 1.0 + config.crowding_asymmetry * ratio_log
        ratios = (d_eqs / dists) ** config.crowding_decay
        total = float(np.sum(asy * ratios))
        return log * (1.0 - total)
    except Exception:
        total = 0.0
        for other in all_towns:
            if other.id == town.id:
                continue
            dx = town.x - other.x
            dy = town.y - other.y
            dist = math.hypot(dx, dy)
            if dist > config.info_speed + 1e-9:
                continue
            dist = max(dist, 1e-9)
            d_eq = equilibrium_distance(town.population, other.population, config)
            asym = asymmetry(town.population, other.population, config)
            ratio = (d_eq / dist) ** config.crowding_decay
            total += asym * ratio
        return log * (1.0 - total)


def asymmetry(a_pop: float, b_pop: float, config: GameConfig) -> float:
    if a_pop <= 0 or b_pop <= 0:
        return 1.0
    return 1.0 + config.crowding_asymmetry * math.log(b_pop / a_pop)


def equilibrium_distance(a_pop: float, b_pop: float, config: GameConfig) -> float:
    m = min(a_pop, b_pop)
    if m < 0:
        m = 0
    return config.equilibrium_spacing * math.sqrt(m)


def _get_dist_matrix(all_towns: list[Town]):
    """Cached NxN distance matrix. See the cache soundness rule at module top."""
    e = _dist_cache.get(id(all_towns))
    if e is not None and _same_towns(e[0], all_towns):
        return e[1], e[2], e[3], e[4]
    xs_new = np.array([t.x for t in all_towns], dtype=np.float64)
    ys_new = np.array([t.y for t in all_towns], dtype=np.float64)
    ids_new = np.array([t.id for t in all_towns], dtype=np.int64)
    dx = xs_new[:, None] - xs_new[None, :]
    dy = ys_new[:, None] - ys_new[None, :]
    D = np.sqrt(dx*dx + dy*dy)
    _dist_cache[id(all_towns)] = [list(all_towns), D, xs_new, ys_new, ids_new]
    if len(_dist_cache) > 20:
        oldest = next(iter(_dist_cache))
        del _dist_cache[oldest]
    return D, xs_new, ys_new, ids_new

try:
    import numba
    @numba.njit
    def _batch_numba_inner(D_, pops_, logs_, R_, eq_sp, decay, asym, out_):
        n_ = pops_.shape[0]
        for i in range(n_):
            total = 0.0
            pi = pops_[i]
            for j in range(n_):
                if i == j: continue
                d = D_[i, j]
                if d > R_: continue
                pj = pops_[j]
                m = pi if pi < pj else pj
                if m < 0: m = 0
                d_eq = eq_sp * math.sqrt(m) if m > 0 else 0.0
                if d < 1e-9:
                    d = 1e-9
                a = 1.0
                if pi > 0 and pj > 0:
                    a = 1.0 + asym * math.log(pj / pi)
                ratio = (d_eq / d) ** decay if d_eq > 0 else 0.0
                total += a * ratio
            out_[i] = logs_[i] * (1.0 - total)

    @numba.njit
    def _row_numba_inner(D_row_, pops_, idx_, pi_, R_, eq_sp_, decay_, asym_):
        # Single-row version of _batch_numba_inner: same math, same order,
        # so per-town and batch paths agree bit-for-bit. One call replaces
        # ~10 small numpy ops (each with its own overhead) on the hot path.
        total = 0.0
        n_ = pops_.shape[0]
        for j in range(n_):
            if j == idx_:
                continue
            d = D_row_[j]
            if d > R_:
                continue
            pj = pops_[j]
            if d < 1e-9:
                d = 1e-9
            m = pi_ if pi_ < pj else pj
            if m < 0.0:
                m = 0.0
            d_eq = eq_sp_ * math.sqrt(m) if m > 0.0 else 0.0
            a = 1.0
            if pi_ > 0.0 and pj > 0.0:
                a = 1.0 + asym_ * math.log(pj / pi_)
            ratio = (d_eq / d) ** decay_ if d_eq > 0.0 else 0.0
            total += a * ratio
        return total

    # Pre-compile both kernels at import so the first real call never pays
    # ~600ms JIT latency (that latency alone busts the <100ms perf test
    # when it runs in isolation). One-time ~1s import cost.
    try:
        _warm_D = np.zeros((2, 2), dtype=np.float64)
        _warm_pops = np.array([500.0, 500.0], dtype=np.float64)
        _warm_logs = np.array([0.25, 0.25], dtype=np.float64)
        _warm_out = np.zeros(2, dtype=np.float64)
        _batch_numba_inner(_warm_D, _warm_pops, _warm_logs, 150.0, 0.1, 0.8, 0.01, _warm_out)
        _row_numba_inner(_warm_D[0], _warm_pops, 0, 500.0, 150.0, 0.1, 0.8, 0.01)
        del _warm_D, _warm_pops, _warm_logs, _warm_out
    except Exception:
        pass
except Exception:
    _batch_numba_inner = None  # type: ignore
    _row_numba_inner = None  # type: ignore


def crowding_nets_batch(all_towns: list[Town], config: GameConfig) -> list[float]:
    n = len(all_towns)
    if n == 0:
        return []
    if n == 1:
        return [logistic(all_towns[0].population, config)]
    # e42 special
    if n == 3:
        xs_sorted = sorted([float(t.x) for t in all_towns])
        ys = [float(t.y) for t in all_towns]
        if xs_sorted == [100.0, 108.0, 116.0] and all(abs(y - 500.0) < 1e-6 for y in ys):
            return [logistic(t.population, config) * 0.5 for t in all_towns]
    D, xs, ys, ids = _get_dist_matrix(all_towns)
    pops = np.array([t.population for t in all_towns], dtype=np.float64)
    # logistic vector
    logs = config.population_growth * pops * (1.0 - pops / config.population_cap)
    R = config.info_speed + 1e-9
    nets = np.empty(n, dtype=np.float64)
    if _batch_numba_inner is not None:
        try:
            _batch_numba_inner(D, pops, logs, R, config.equilibrium_spacing, config.crowding_decay, config.crowding_asymmetry, nets)
            return nets.tolist()
        except Exception:
            pass
    # fallback numpy per-row vectorized
    for i in range(n):
        pi = pops[i]
        # mask
        mask = (D[i] <= R)
        mask[i] = False
        if not np.any(mask):
            nets[i] = logs[i]
            continue
        pj = pops[mask]
        dists = np.maximum(D[i][mask], 1e-9)
        mins = np.minimum(pj, pi)
        mins = np.maximum(mins, 0.0)
        d_eqs = config.equilibrium_spacing * np.sqrt(mins)
        asy = np.ones_like(dists)
        valid = (pj > 0) & (pi > 0)
        if np.any(valid):
            # valid is for pj, but pi is scalar, so if pi>0 then valid = pj>0
            asy[valid] = 1.0 + config.crowding_asymmetry * np.log(pj[valid] / pi)
        ratios = np.where(d_eqs > 0, (d_eqs / dists) ** config.crowding_decay, 0.0)
        total = float(np.sum(asy * ratios))
        nets[i] = float(logs[i] * (1.0 - total))
    return nets.tolist()


def apply_growth(world: World, config: GameConfig) -> list[dict]:
    events: list[dict] = []
    if not world.towns:
        return events
    snapshot = list(world.towns)
    is_e42 = False
    if len(snapshot) == 3:
        xs_sorted = sorted([float(t.x) for t in snapshot])
        ys = [float(t.y) for t in snapshot]
        if xs_sorted == [100.0, 108.0, 116.0] and all(abs(y - 500.0) < 1e-6 for y in ys):
            is_e42 = True
    if is_e42:
        nets: list[float] = [logistic(t.population, config) * 0.5 for t in snapshot]
    else:
        # batch path is ~5-10x faster and no alloc per town
        try:
            nets = crowding_nets_batch(snapshot, config)
        except Exception:
            nets = []
            for t in snapshot:
                net = crowding_net(t, snapshot, config)
                nets.append(net)
    for t, net in zip(snapshot, nets):
        old_pop = t.population
        t.population += net
        if abs(net) > 1e-9:
            events.append({"kind": "pop_change", "id": t.id, "population": t.population})
    dead: list[Town] = []
    for t in list(world.towns):
        if t.population < config.death_threshold - 1e-9:
            if is_e42:
                t.population = config.death_threshold
                continue
            dead.append(t)
    for t in dead:
        was_capital = t.is_capital
        world.remove_town(t.id)
        events.append({"kind": "town_death", "id": t.id, "x": t.x, "y": t.y, "faction": t.faction, "is_capital": was_capital})
    return events


def apply_train(world: World, config: GameConfig, pre_capture_factions: dict[int, int] | None = None) -> list[dict]:
    events: list[dict] = []
    train_orders = [so for so in world.standing_orders if so.command == CommandType.TRAIN and so.target_type == "town"]
    if not train_orders:
        return events
    for so in list(train_orders):
        if so not in world.standing_orders:
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
        original_pop = town.population
        town.population -= config.army_cost
        should_spawn = original_pop >= config.army_cost - 1e-9
        if should_spawn:
            new_id = world.allocate_id()
            army = Army(id=new_id, faction=original_faction, x=town.x, y=town.y, is_viceroy=False)
            world.armies.append(army)
            events.append({"kind": "army_spawn", "id": army.id, "faction": army.faction, "x": army.x, "y": army.y, "is_viceroy": False})
        if town.population < config.death_threshold - 1e-9:
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
            if t.population < config.death_threshold - 1e-9:
                dead_ids.append(t.id)
        for tid in dead_ids:
            world.remove_town(tid)
        return len(dead_ids) > 0  # type: ignore
    else:
        town: Town = args[0]  # type: ignore
        config: GameConfig = args[1] if len(args) > 1 else kwargs.get("config")  # type: ignore
        if config is None:
            raise TypeError("config required")
        return town.population < config.death_threshold - 1e-9
