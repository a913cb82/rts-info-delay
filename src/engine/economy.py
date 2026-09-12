"""Economy — agrarian model (2026-09-13): land- and labour-limited
production, conservative food trade, food-limited births, surplus-labour
migration, market-access productivity.

Every parameter is a real-world quantity (see GameConfig):

    R    farm_radius_km      farm walking radius (5 km)
    c,p  farm_decay_*         yield decay within R (0 = flat ring)
    rho  rural_density       subsistence density (30 people/km2 c.1600)
    Lc   cart_distance_km    distance carting doubles grain price (20 km)
    sf   farm_workers_yield  people fed per farm worker (1.3)
    b    birth_rate          crude births / person / year (35/1000)
    m    death_rate          crude deaths / person / year (31/1000)
    sm   market_premium      max farm-output premium from market access
    th   migration_share     share of natural increase that emigrates
    nu   surplus_mobility    share of surplus labour leaving per year
    Lm   migration_scale_km  migration distance scale

Per turn (TURNS_PER_YEAR = config.turns_per_year):

    Y_i     = (1+boost_i) * min(rho*area_i, sf*P_i)      production
    boost_i = sm * mkt_i/(mkt_i + P_i)
    mkt_i   = sum_j P_market*(serv_j/P_market)^g * c(d_ij)
    serv_j  = max(0, P_j - Y_j/sf)                        non-farm population
    S_i     = Y_i + imports_i                             food commanded
    B_i     = b*P_i * S_i/(S_i + h*P_i),  h = b/m - 1
    D_i     = m*P_i
    out_i   = th*max(0,B_i-D_i) + nu*max(0,P_i - Y_i/sf)
    mig_ij  = out_i * attr_ij / sum_k attr_ik
    attr_ij = max(0,P_j-P_i) * min(1,S_j/P_j) * e^(-d/Lm) * win(d)

Land areas are the nearest-farmer cell within R, equal-area sampled
(128 points) and cached while the town set is unchanged. Trade is a greedy
nearest-first transportation with hard caps: every surplus unit is
shipped once, deficits are filled, nothing is created or destroyed.
Migration is origin-budgeted, so people only move (never appear).
"""

from __future__ import annotations

import math

import numpy as np

from engine.config import GameConfig
from engine.world import Army, CommandType, Town, World

# Trade and market access stop where carting makes grain uncompetitive:
# 3 price doublings (~60 km with Lc = 20 km).
_TRADE_REACH_FACTOR = 3.0


# ---------------------------------------------------------------------------
# Windows and derived constants

def _win_scalar(d2: float, cutoff: float) -> float:
    """Hard-bound C-infinity window: 1 at d=0, 0 at d >= cutoff."""
    c2 = cutoff * cutoff
    if d2 >= c2:
        return 0.0
    if d2 <= 1e-18:
        return 1.0
    x = c2 / d2 - c2 / (c2 - d2)
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _win_np(D: np.ndarray, cutoff: float) -> np.ndarray:
    c2 = cutoff * cutoff
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        d2 = D * D
        pos = np.maximum(d2, 1e-300)
        rest = np.maximum(c2 - d2, 1e-300)
        x = c2 / pos - c2 / rest
        w = np.where(
            x >= 0.0,
            1.0 / (1.0 + np.exp(-np.minimum(x, 700.0))),
            np.exp(np.maximum(x, -700.0)) / (1.0 + np.exp(np.maximum(x, -700.0))),
        )
    return np.where(d2 >= c2, 0.0, w)


def interaction_window(d2: float, config: GameConfig) -> float:
    """Compatibility wrapper (old signature): bound = info_speed."""
    return _win_scalar(d2, config.info_speed)


def rho0_of(config: GameConfig) -> float:
    """Near-field yield: rescaled so the full ring's mean yield is rural_density.

    yield(d) = rho0*(1 - c*(d/R)^p); mean over the ring = 1 - 2c/(p+2).
    """
    c = config.farm_decay_at_radius
    if c <= 0.0:
        return config.rural_density
    p = max(config.farm_decay_shape, 1e-9)
    return config.rural_density / max(1.0 - 2.0 * c / (p + 2.0), 1e-6)


def production(config: GameConfig, area: np.ndarray, pops: np.ndarray) -> np.ndarray:
    """Food from a settlement's cell, flat ring or Von Thuenen decay.

    Flat (current): min(rural_density*area, sigma*P).
    Decay: farmers work the best land first; a worker farms
    aw = sigma/rho0 km2, yield falls with distance, so output is the
    integral out to r = min(r_labor, r_cell).
    """
    c = config.farm_decay_at_radius
    sigma = config.farm_workers_yield
    if c <= 0.0:
        return np.minimum(config.rural_density * area, sigma * pops)
    rho0 = rho0_of(config)
    aw = sigma / rho0
    R = config.farm_radius_km
    p = config.farm_decay_shape
    r2 = np.minimum(area / math.pi, pops * aw / math.pi)
    r = np.sqrt(np.maximum(r2, 0.0))
    integral = 0.5 * r2 - c * np.power(r, p + 2.0) / ((p + 2.0) * R ** p)
    return 2.0 * math.pi * rho0 * np.maximum(integral, 0.0)


def derived(config: GameConfig):
    """Return (Y_ring, P_market, h, b_turn, m_turn, nu_turn)."""
    y_ring = config.rural_density * math.pi * config.farm_radius_km ** 2
    p_market = y_ring
    h = max(config.birth_rate / max(config.death_rate, 1e-12) - 1.0, 1e-9)
    tpy = max(config.turns_per_year, 1.0)
    return (y_ring, p_market, h,
            config.birth_rate / tpy, config.death_rate / tpy,
            config.surplus_mobility / tpy)


# ---------------------------------------------------------------------------
# Distance matrix cache (shared across turns; validated by element identity)

_dist_cache: dict = {}


def _same_towns(ref: list[Town] | None, all_towns: list[Town]) -> bool:
    if ref is None or len(ref) != len(all_towns):
        return False
    for a, b in zip(ref, all_towns):
        if a is not b:
            return False
    return True


def _get_dist_matrix(all_towns: list[Town]) -> np.ndarray:
    e = _dist_cache.get(id(all_towns))
    if e is not None and _same_towns(e[0], all_towns):
        return e[1]
    xs = np.array([t.x for t in all_towns], dtype=np.float64)
    ys = np.array([t.y for t in all_towns], dtype=np.float64)
    dx = xs[:, None] - xs[None, :]
    dy = ys[:, None] - ys[None, :]
    D = np.sqrt(dx * dx + dy * dy)
    _dist_cache[id(all_towns)] = [list(all_towns), D]
    if len(_dist_cache) > 20:
        del _dist_cache[next(iter(_dist_cache))]
    return D


# ---------------------------------------------------------------------------
# Land areas: nearest-farmer cell within R, sample-quadrature, cached

_land_cache = {"key": None, "areas": None}

_SAMPLE_K = 128


def _sample_offsets(k: int = _SAMPLE_K):
    """Equal-area (Vogel spiral) sample points in the unit disc."""
    idx = np.arange(k, dtype=np.float64) + 0.5
    r = np.sqrt(idx / k)
    theta = idx * math.pi * (3.0 - math.sqrt(5.0))
    return r * np.cos(theta), r * np.sin(theta)


try:
    import numba

    @numba.njit(cache=True)
    def _land_kernel(xs, ys, sx, sy, radius, map_w, map_h, out):
        """Voronoi area within R per town, by equal-area sampling.

        A sample in town i's ring counts for i iff i is the nearest
        settlement to it (the map is a window; countryside continues)."""
        n = xs.shape[0]
        k = sx.shape[0]
        wt = math.pi * radius * radius / k
        for i in range(n):
            tot = 0.0
            for q in range(k):
                px = xs[i] + sx[q] * radius
                py = ys[i] + sy[q] * radius
                bd = 1e18
                bj = -1
                for j in range(n):
                    dx = xs[j] - px
                    dy = ys[j] - py
                    d2 = dx * dx + dy * dy
                    if d2 < bd:
                        bd = d2
                        bj = j
                if bj == i:
                    tot += wt
            out[i] = tot

    _has_numba = True
except Exception:  # pragma: no cover
    _has_numba = False
    _land_kernel = None  # type: ignore


def land_areas(towns: list[Town], map_size, config: GameConfig) -> np.ndarray:
    map_w = float(map_size[0]) if map_size else 1000.0
    map_h = float(map_size[1]) if map_size and len(map_size) > 1 else map_w
    key = (tuple((t.id, t.x, t.y) for t in towns), map_w, map_h)
    if _land_cache["key"] == key:
        return _land_cache["areas"]
    n = len(towns)
    areas = np.zeros(n, dtype=np.float64)
    if n:
        xs = np.array([t.x for t in towns], dtype=np.float64)
        ys = np.array([t.y for t in towns], dtype=np.float64)
        sx, sy = _sample_offsets()
        if _has_numba:
            _land_kernel(xs, ys, sx, sy, config.farm_radius_km, map_w, map_h, areas)
        else:
            wt = math.pi * config.farm_radius_km ** 2 / len(sx)
            for i in range(n):
                for q in range(len(sx)):
                    px = xs[i] + sx[q] * config.farm_radius_km
                    py = ys[i] + sy[q] * config.farm_radius_km
                    d2 = (xs - px) ** 2 + (ys - py) ** 2
                    if int(np.argmin(d2)) == i:
                        areas[i] += wt
    _land_cache["key"] = key
    _land_cache["areas"] = areas
    return areas


# ---------------------------------------------------------------------------
# Trade: greedy nearest-first transportation with caps

try:
    import numba as _numba

    @_numba.njit(cache=True)
    def _trade_kernel(D, surplus, deficit, max_km, imports, exports):
        n = D.shape[0]
        m = 0
        for i in range(n):
            if deficit[i] <= 0.0:
                continue
            for j in range(n):
                if j != i and surplus[j] > 0.0 and D[i, j] <= max_km:
                    m += 1
        ds = np.empty(m, dtype=np.float64)
        ii = np.empty(m, dtype=np.int64)
        jj = np.empty(m, dtype=np.int64)
        k = 0
        for i in range(n):
            if deficit[i] <= 0.0:
                continue
            for j in range(n):
                if j != i and surplus[j] > 0.0 and D[i, j] <= max_km:
                    ds[k] = D[i, j]
                    ii[k] = i
                    jj[k] = j
                    k += 1
        order = np.argsort(ds)
        rem_s = surplus.copy()
        rem_d = deficit.copy()
        for oi in range(m):
            idx = order[oi]
            i = ii[idx]
            j = jj[idx]
            f = rem_d[i]
            if rem_s[j] < f:
                f = rem_s[j]
            if f > 0.0:
                imports[i] += f
                exports[j] += f
                rem_d[i] -= f
                rem_s[j] -= f

    _has_trade_numba = True
except Exception:  # pragma: no cover
    _has_trade_numba = False
    _trade_kernel = None  # type: ignore


def _trade(surplus: np.ndarray, deficit: np.ndarray, D: np.ndarray,
           config: GameConfig):
    n = len(surplus)
    imports = np.zeros(n, dtype=np.float64)
    exports = np.zeros(n, dtype=np.float64)
    if n < 2:
        return imports, exports
    max_km = _TRADE_REACH_FACTOR * config.cart_distance_km
    if _has_trade_numba:
        _trade_kernel(D, surplus, deficit, max_km, imports, exports)
        return imports, exports
    pairs = []
    for i in range(n):
        if deficit[i] <= 0.0:
            continue
        for j in range(n):
            if i != j and surplus[j] > 0.0 and D[i, j] <= max_km:
                pairs.append((D[i, j], i, j))
    pairs.sort()
    rem_s = surplus.copy()
    rem_d = deficit.copy()
    for _, i, j in pairs:
        f = min(rem_d[i], rem_s[j])
        if f > 0.0:
            imports[i] += f
            exports[j] += f
            rem_d[i] -= f
            rem_s[j] -= f
    return imports, exports


def _market_boost(serv: np.ndarray, pops: np.ndarray, D: np.ndarray,
                  config: GameConfig, p_market: float) -> np.ndarray:
    """Farm-output premium = services per head served.

    mkt is the reachable non-farm population; the denominator is the
    population it serves, so the premium is a service ratio (0 remote,
    -> market_premium where services are abundant)."""
    n = len(serv)
    if n == 0:
        return np.zeros(0)
    max_km = _TRADE_REACH_FACTOR * config.cart_distance_km
    ln2 = math.log(2.0)
    cm = np.where(D <= max_km,
                  np.exp(-D * ln2 / config.cart_distance_km), 0.0)
    contrib = np.where(
        serv > 0.0,
        p_market * np.power(np.maximum(serv, 0.0) / p_market,
                            config.market_scaling),
        0.0,
    )
    mkt = cm @ contrib
    return config.market_premium * mkt / (mkt + np.maximum(pops, 1e-12))


def _migration(pops: np.ndarray, S: np.ndarray, out_people: np.ndarray,
               D: np.ndarray, config: GameConfig) -> np.ndarray:
    n = len(pops)
    if n < 2:
        return np.zeros(n)
    with np.errstate(divide="ignore", invalid="ignore"):
        feed = np.where(pops > 0.0,
                        np.minimum(1.0, S / np.maximum(pops, 1e-12)), 0.0)
    gap = np.maximum(0.0, pops[None, :] - pops[:, None])
    mig = np.exp(-D / max(config.migration_scale_km, 1e-9)) * _win_np(D, config.info_speed)
    A = gap * feed[None, :] * mig
    rs = A.sum(axis=1)
    flow = np.zeros_like(A)
    nz = rs > 0.0
    flow[nz] = out_people[nz, None] * A[nz] / rs[nz, None]
    return flow.sum(axis=0) - flow.sum(axis=1)


# ---------------------------------------------------------------------------
# Core step

def _step_core(towns: list[Town], map_size, config: GameConfig,
               last_serv: dict[int, float] | None = None):
    n = len(towns)
    if n == 0:
        return np.zeros(0), np.zeros(0)
    pops = np.array([t.population for t in towns], dtype=np.float64)
    y_ring, p_market, h, b_t, m_t, nu_t = derived(config)
    areas = land_areas(towns, map_size, config)
    D = _get_dist_matrix(towns) if n >= 2 else None
    if n >= 2 and last_serv:
        serv = np.array([float(last_serv.get(t.id, 0.0)) for t in towns])
        boost = _market_boost(serv, pops, D, config, p_market)
    else:
        boost = np.zeros(n)
    prod = (1.0 + boost) * production(config, areas, pops)
    surplus = np.maximum(0.0, prod - pops)
    deficit = np.maximum(0.0, pops - prod)
    if n >= 2:
        imports, _exports = _trade(surplus, deficit, D, config)
    else:
        imports = np.zeros(n)
    S = prod + imports
    births = b_t * pops * S / np.maximum(S + h * pops, 1e-12)
    deaths = m_t * pops
    if n >= 2:
        p_need = prod / max(config.farm_workers_yield, 1e-12)
        p_surp = np.maximum(0.0, pops - p_need)
        out_people = (config.migration_share * np.maximum(0.0, births - deaths)
                      + nu_t * p_surp)
        net_mig = _migration(pops, S, out_people, D, config)
    else:
        net_mig = np.zeros(n)
    new_pops = np.maximum(0.0, pops + births - deaths + net_mig)
    # Non-farm population: people beyond what current production needs.
    serv_now = np.maximum(0.0, pops - prod / max(config.farm_workers_yield, 1e-12))
    return new_pops, serv_now


def base_growth(population: float, config: GameConfig) -> float:
    """Net growth per turn of a lone settlement (full ring, no neighbours)."""
    _y_ring, _p_market, h, b_t, m_t, _nu = derived(config)
    area = np.array([math.pi * config.farm_radius_km ** 2])
    pops = np.array([float(population)])
    prod = float(production(config, area, pops)[0])
    births = b_t * population * prod / max(prod + h * population, 1e-12)
    return births - m_t * population


def nets_for(all_towns: list[Town], config: GameConfig, map_size=None) -> list[float]:
    """Net population change per town for one turn (no mutation)."""
    towns = list(all_towns)
    if not towns:
        return []
    pops = np.array([t.population for t in towns], dtype=np.float64)
    new_pops, _ = _step_core(towns, map_size or [1000, 1000], config, None)
    return (new_pops - pops).tolist()



def crowding_net(town: Town, all_towns: list[Town], config: GameConfig) -> float:
    """Net change for one town in a one-turn step (test/bench helper)."""
    towns = list(all_towns)
    nets = nets_for(towns, config)
    for k, t in enumerate(towns):
        if t is town or t.id == town.id:
            return nets[k]
    return 0.0

def crowding_nets_batch(all_towns: list[Town], config: GameConfig) -> list[float]:
    """Compatibility alias for one-turn net changes."""
    return nets_for(all_towns, config)


def apply_growth(world: World, config: GameConfig) -> list[dict]:
    events: list[dict] = []
    if not world.towns:
        world._last_serv = {}
        return events
    towns = world.towns
    old = [t.population for t in towns]
    new_pops, serv = _step_core(towns, world.map_size, config,
                                getattr(world, "_last_serv", None))
    for t, p in zip(towns, new_pops):
        t.population = float(p)
    world._last_serv = {t.id: float(v) for t, v in zip(towns, serv)}
    for t, o, p in zip(towns, old, new_pops):
        if abs(p - o) > 1e-9:
            events.append({"kind": "pop_change", "id": t.id,
                           "population": float(p)})
    dead = [t for t in list(world.towns)
            if t.population <= config.town_min_population]
    for t in dead:
        was_capital = t.is_capital
        world.remove_town(t.id)
        events.append({"kind": "town_death", "id": t.id, "x": t.x, "y": t.y,
                       "faction": t.faction, "is_capital": was_capital})
    return events


# ---------------------------------------------------------------------------
# Commands (unchanged from the previous economy)

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
