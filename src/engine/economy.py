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
    mi   max_improvement     max farm-output improvement from market access
    th   migration_share     share of total population emigrating/year
    nu   surplus_mobility    share of surplus labour leaving per year
    Lm   migration_scale_km  migration distance scale

Per turn (TURNS_PER_YEAR = config.turns_per_year):

    Y0_i    = min(rho*area_i, sf*P_i)                     own-land production
    serv_j  = max(0, P_j - Y0_j/sf)                       non-farm workforce
    offer_j = P_market*(serv_j/P_market)^g * (1 + last_j)  resell: pass on
                                                            what was received
    mkt_i   = sum_j offer_j * c(d_ij)                     one pass/turn;
                                                            hops accrue over turns
    improvement_i = mi * mkt_i/(mkt_i + P_i)              soft-capped at mi
    Y_i     = (1+improvement_i) * Y0_i                    production
    S_i     = Y_i + imports_i                             food commanded
    B_i     = b*P_i * S_i/(S_i + h*P_i),  h = b/m - 1
    D_i     = m*P_i
    out_i   = th*P_i + nu*max(0,P_i - Y0_i/sf)
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

    Flat (c = 0): min(rural_density*area, sigma*P).
    Decay (current): farmers work the best land first; a worker farms
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
    """Return (Y_ring, P_market, h, b_turn, m_turn, th_turn, nu_turn)."""
    y_ring = config.rural_density * math.pi * config.farm_radius_km ** 2
    p_market = y_ring
    h = max(config.birth_rate / max(config.death_rate, 1e-12) - 1.0, 1e-9)
    tpy = max(config.turns_per_year, 1.0)
    return (y_ring, p_market, h,
            config.birth_rate / tpy, config.death_rate / tpy,
            config.migration_share / tpy, config.surplus_mobility / tpy)


# ---------------------------------------------------------------------------
# Spatial index: cached 60 km neighbor lists (ascending indices + exact
# distances) replace the dense N x N distance matrix, which only ever
# served neighbor discovery. Built on a CSR cell grid (combat.py pattern)
# so no N x N array is ever materialized; pair sets match the old matrix
# thresholding bit-for-bit (same sqrt expression, same comparison), and
# every consumer below visits pairs in ascending index order — so the
# whole economy is bit-identical to the matrix version (tripwire-stable).

_GRID_CELL_KM = 20.0
_geo_cache = {"key": None, "geo": None, "grid": None, "prev_key": None,
              "event": None}


def _geo(towns: list[Town], config: GameConfig):
    """(nidx, ndist, ndeg, nweight, xs, ys): neighbors within trade reach.

    nidx[i] lists town indices within max_km (self included) ascending,
    ndist their exact distances, ndeg the counts, nweight the migration
    weights w = exp(-d/scale)*win(d) (same code path as the dense form,
    so bit-identical). Padding slots point at self with weight 1.0 =
    the true self weight, so scatter writes there are order-free. One
    entry cached per town set (positions only move when the set changes,
    like land); reach and migration scale are part of the key so mid-run
    sweeps rebuild."""
    max_km = _TRADE_REACH_FACTOR * config.cart_distance_km
    scale = max(config.migration_scale_km, 1e-9)
    key = (tuple((t.id, t.x, t.y) for t in towns),
           float(max_km), float(scale))
    if _geo_cache["key"] == key:
        # No event clearing here: land_areas calls _geo mid-turn after the
        # main call, and a hit must not wipe the event the miss just set.
        # Staleness is impossible (a hit means the trade content key hits
        # too, so the event is never read).
        return _geo_cache["geo"]
    inc = _geo_try_incremental(towns, config, max_km, scale, key)
    if inc is not None:
        _geo_cache["prev_key"] = _geo_cache["key"]
        _geo_cache["key"] = key
        _geo_cache["geo"] = inc[0]
        _geo_cache["grid"] = inc[1]
        return inc[0]
    n = len(towns)
    xs = np.array([t.x for t in towns], dtype=np.float64)
    ys = np.array([t.y for t in towns], dtype=np.float64)
    cells = None
    if n == 0:
        geo = (np.zeros((0, 0), np.int64), np.zeros((0, 0)),
               np.zeros(0, np.int64), np.zeros((0, 0)), xs, ys)
    else:
        cell = _GRID_CELL_KM
        cells: dict = {}
        for j in range(n):
            ck = (math.floor(xs[j] / cell), math.floor(ys[j] / cell))
            cells.setdefault(ck, []).append(j)
        rows_i, rows_d = [], []
        for i in range(n):
            # Cells overlapped by the reach disc (1e-7 slop dwarfs fp
            # noise; the exact-distance filter below is the arbiter).
            ix0 = math.floor((xs[i] - max_km - 1e-7) / cell)
            ix1 = math.floor((xs[i] + max_km + 1e-7) / cell)
            iy0 = math.floor((ys[i] - max_km - 1e-7) / cell)
            iy1 = math.floor((ys[i] + max_km + 1e-7) / cell)
            cand = []
            for ax in range(ix0, ix1 + 1):
                for ay in range(iy0, iy1 + 1):
                    cand.extend(cells.get((ax, ay), ()))
            cand = np.unique(np.array(cand, dtype=np.int64))
            dx = xs[i] - xs[cand]
            dy = ys[i] - ys[cand]
            d = np.sqrt(dx * dx + dy * dy)
            keep = d <= max_km
            rows_i.append(cand[keep])
            rows_d.append(d[keep])
        md = max((len(r) for r in rows_i), default=0)
        nidx = np.zeros((n, md), dtype=np.int64)
        ndist = np.zeros((n, md), dtype=np.float64)
        ndeg = np.zeros(n, dtype=np.int64)
        for i in range(n):
            m = len(rows_i[i])
            ndeg[i] = m
            nidx[i, :m] = rows_i[i]
            ndist[i, :m] = rows_d[i]
            nidx[i, m:] = i  # padding: self, whose true weight is 1.0
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            nweight = np.exp(-ndist / scale) * _win_np(ndist, max_km)
        geo = (nidx, ndist, ndeg, nweight, xs, ys)
    _geo_cache["prev_key"] = _geo_cache["key"]
    _geo_cache["key"] = key
    _geo_cache["geo"] = geo
    _geo_cache["grid"] = cells
    _geo_cache["event"] = None
    return geo


def _classify(old_ids, new_ids):
    """Single founding/death vs rebuild, from key id-tuples.

    Returns ("found", added) | ("death", removed) | ("rebuild",) with
    added/removed as (id, x, y) tuples. Any moved town (same id, changed
    position) forces rebuild. O(N) on the rare miss path only."""
    old = {t[0]: (t[1], t[2]) for t in old_ids}
    new = {t[0]: (t[1], t[2]) for t in new_ids}
    for i, xy in new.items():
        if i in old and old[i] != xy:
            return ("rebuild",)
    added = [t for t in new_ids if t[0] not in old]
    removed = [t for t in old_ids if t[0] not in new]
    if len(added) == 1 and not removed:
        return ("found", added[0])
    if len(removed) == 1 and not added:
        return ("death", removed[0])
    return ("rebuild",)


def _query_around(cells, cell, x, y, radius):
    """Candidate indices from cells overlapped by the reach disc.

    Same discovery as the full build (duplicated so the verified build
    path stays untouched); the exact-distance filter below is the arbiter."""
    ix0 = math.floor((x - radius - 1e-7) / cell)
    ix1 = math.floor((x + radius + 1e-7) / cell)
    iy0 = math.floor((y - radius - 1e-7) / cell)
    iy1 = math.floor((y + radius + 1e-7) / cell)
    cand = []
    for ax in range(ix0, ix1 + 1):
        for ay in range(iy0, iy1 + 1):
            cand.extend(cells.get((ax, ay), ()))
    return np.unique(np.array(cand, dtype=np.int64))


def _geo_try_incremental(towns, config, max_km, scale, key):
    """Fast path for single founding (appended) / single death.

    Returns (geo, grid) or None (caller falls through to full build).
    Append-at-end founding needs no index remap; death remaps once."""
    old_key = _geo_cache.get("key")
    old_geo = _geo_cache.get("geo")
    old_cells = _geo_cache.get("grid")
    if old_key is None or old_geo is None or old_cells is None:
        return None
    if old_key[1:] != key[1:]:
        return None  # reach/scale changed: every list changes
    old_ids, new_ids = old_key[0], key[0]
    cls = _classify(old_ids, new_ids)
    if cls[0] == "found" and len(new_ids) == len(old_ids) + 1 \
            and new_ids[:len(old_ids)] == old_ids:
        _geo_cache["event"] = ("append", len(new_ids) - 1)
        return _geo_found(towns, config, max_km, scale, old_geo, old_cells)
    if cls[0] == "death":
        removed = cls[1]
        d = next(k for k, t in enumerate(old_ids) if t[0] == removed[0])
        _geo_cache["event"] = ("remove", d)
        return _geo_forget(old_geo, old_cells, old_ids, new_ids, removed)
    _geo_cache["event"] = None
    return None


def _geo_found(towns, config, max_km, scale, old_geo, old_cells):
    """Append-at-end founding: newcomer index is max, so mirror entries
    append at row ends (no memmove) and no remap is needed."""
    nidx, ndist, ndeg, nweight, xs, ys = old_geo
    n = len(towns)
    j = n - 1
    xj, yj = towns[j].x, towns[j].y
    xs2 = np.append(xs, xj)
    ys2 = np.append(ys, yj)
    cand = _query_around(old_cells, _GRID_CELL_KM, xj, yj, max_km)
    dx = xj - xs[cand]
    dy = yj - ys[cand]
    d = np.sqrt(dx * dx + dy * dy)
    keep = d <= max_km
    lst = np.append(cand[keep], j)  # ascending (self idx is max)
    dst = np.append(d[keep], 0.0)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        wlst = np.exp(-dst / scale) * _win_np(dst, max_km)
    md = int(nidx.shape[1])
    full = [int(c) for c in lst if c != j and ndeg[c] >= md]
    new_md = max(md, len(lst))
    if full:
        new_md = max(new_md, int(ndeg[full].max()) + 1)
    ndeg2 = np.append(ndeg.copy(), len(lst))
    if new_md > md:
        nidx2 = np.zeros((n, new_md), dtype=np.int64)
        ndist2 = np.zeros((n, new_md), dtype=np.float64)
        nweight2 = np.zeros((n, new_md), dtype=np.float64)
        nidx2[:n - 1, :md] = nidx
        ndist2[:n - 1, :md] = ndist
        nweight2[:n - 1, :md] = nweight
        for i in range(n - 1):
            nidx2[i, int(ndeg[i]):] = i
            nweight2[i, int(ndeg[i]):] = 1.0
        nidx, ndist, nweight = nidx2, ndist2, nweight2
        md = new_md
    else:
        nidx = np.vstack([nidx, np.zeros((1, md), dtype=np.int64)])
        ndist = np.vstack([ndist, np.zeros((1, md), dtype=np.float64)])
        nweight = np.vstack([nweight, np.zeros((1, md), dtype=np.float64)])
    nidx[j, :len(lst)] = lst
    ndist[j, :len(lst)] = dst
    nweight[j, :len(lst)] = wlst
    nidx[j, len(lst):] = j
    nweight[j, len(lst):] = 1.0
    for pos, c in enumerate(lst):
        c = int(c)
        if c == j:
            continue
        m = int(ndeg2[c])
        nidx[c, m] = j
        ndist[c, m] = float(dst[pos])
        nweight[c, m] = float(wlst[pos])
        ndeg2[c] = m + 1
    ck = (math.floor(xj / _GRID_CELL_KM), math.floor(yj / _GRID_CELL_KM))
    cells2 = dict(old_cells)
    cells2[ck] = old_cells.get(ck, []) + [j]
    return ((nidx, ndist, ndeg2, nweight, xs2, ys2), cells2)


def _geo_forget(old_geo, old_cells, old_ids, new_ids, removed):
    """Single death: drop the row, remap higher indices down once."""
    nidx, ndist, ndeg, nweight, xs, ys = old_geo
    d = next(k for k, t in enumerate(old_ids) if t[0] == removed[0])
    n = len(new_ids)
    if n == 0:
        z = (np.zeros((0, nidx.shape[1]), np.int64), np.zeros((0, nidx.shape[1])),
             np.zeros(0, np.int64), np.zeros((0, nidx.shape[1])),
             np.zeros(0), np.zeros(0))
        return (z, {})
    keep_rows = [r for r in range(n + 1) if r != d]
    idx2 = nidx[keep_rows]
    dis2 = ndist[keep_rows]
    wgt2 = nweight[keep_rows]
    deg2 = ndeg[keep_rows].copy()
    md = int(idx2.shape[1])
    for r in range(n):
        row = idx2[r, :int(deg2[r])]
        pos = int(np.searchsorted(row, d))
        if pos < int(deg2[r]) and row[pos] == d:
            tail_i = row[pos + 1:].copy()
            tail_d = dis2[r, pos + 1:int(deg2[r])].copy()
            tail_w = wgt2[r, pos + 1:int(deg2[r])].copy()
            idx2[r, pos:int(deg2[r]) - 1] = tail_i
            dis2[r, pos:int(deg2[r]) - 1] = tail_d
            wgt2[r, pos:int(deg2[r]) - 1] = tail_w
            deg2[r] -= 1
    valid = np.arange(md)[None, :] < deg2[:, None]
    sub = idx2 > d
    idx2[valid & sub] -= 1
    rows = np.arange(n)[:, None]
    pad = np.arange(md)[None, :] >= deg2[:, None]
    idx2[pad] = np.broadcast_to(rows, (n, md))[pad]
    dis2[pad] = 0.0
    wgt2[pad] = 1.0
    xs2 = np.delete(xs, d)
    ys2 = np.delete(ys, d)
    cells2 = {}
    for k, members in old_cells.items():
        m2 = [m - 1 if m > d else m for m in members if m != d]
        if m2:
            cells2[k] = m2
    return ((idx2, dis2, deg2, wgt2, xs2, ys2), cells2)


# ---------------------------------------------------------------------------
# Land areas: nearest-farmer cell within R, sample-quadrature, cached

_land_cache = {"key": None, "areas": None}

# Quadrature points per town. Isolated towns are exact at any K;
# shared boundaries need K large enough that one point (pi*R^2/K km2)
# stays small next to the smallest farmed area (~7 km2 for a 300-pop
# village). Measured: K=8 errs up to 40% on small cells, K=16/32 a few
# %, K=64/128 ~1-2%. Growth rankings are unchanged down to K=16, so
# the default is 32 (4x kernel speedup over 128 at no ranking cost).
_SAMPLE_K = 32


def _sample_offsets(k: int | None = None):
    """Equal-area (Vogel spiral) sample points in the unit disc."""
    if k is None:
        k = _SAMPLE_K
    idx = np.arange(k, dtype=np.float64) + 0.5
    r = np.sqrt(idx / k)
    theta = idx * math.pi * (3.0 - math.sqrt(5.0))
    return r * np.cos(theta), r * np.sin(theta)


try:
    import numba

    @numba.njit(cache=True)
    def _land_kernel(xs, ys, sx, sy, radius, nbrs, degs, out):
        """Voronoi area within R per town, by equal-area sampling.

        A sample in town i's ring counts for i iff i is the nearest
        settlement to it (the map is a window; countryside continues).
        `nbrs[i]` lists candidate towns within 2R of i in ascending
        index order: by the triangle inequality the true nearest to any
        of i's samples is always among them, and strict-less-than over an
        ascending list reproduces brute-force tie-breaking exactly."""
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
                for m in range(degs[i]):
                    j = nbrs[i, m]
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


def _land_fallback(xs, ys, sx, sy, radius, nbrs, degs, out, only=None):
    """Pure-python land kernel, op-for-op identical to _land_kernel.

    Same per-sample winner (first-minimum over ascending candidates),
    same sequential wt accumulation in q order — bit-identical outputs.
    `only` restricts to a subset of town indices (incremental updates).
    Pinned by test_fallback_matches_kernel; do not 'simplify'."""
    n = xs.shape[0]
    k = sx.shape[0]
    wt = math.pi * radius * radius / k
    idx = range(n) if only is None else only
    for i in idx:
        tot = 0.0
        for q in range(k):
            px = xs[i] + sx[q] * radius
            py = ys[i] + sy[q] * radius
            bd = 1e18
            bj = -1
            for m in range(degs[i]):
                j = nbrs[i, m]
                dx = xs[j] - px
                dy = ys[j] - py
                d2 = dx * dx + dy * dy
                if d2 < bd:
                    bd = d2
                    bj = j
            if bj == i:
                tot += wt
        out[i] = tot


def land_areas(towns: list[Town], map_size, config: GameConfig) -> np.ndarray:
    map_w = float(map_size[0]) if map_size else 1000.0
    map_h = float(map_size[1]) if map_size and len(map_size) > 1 else map_w
    key = (tuple((t.id, t.x, t.y) for t in towns), map_w, map_h)
    if _land_cache["key"] == key:
        return _land_cache["areas"]
    inc = _land_try_incremental(towns, config, map_w, map_h, key)
    if inc is not None:
        _land_cache["key"] = key
        _land_cache["areas"] = inc
        return inc
    n = len(towns)
    areas = np.zeros(n, dtype=np.float64)
    if n:
        _g = _geo(towns, config)
        xs, ys = _g[4], _g[5]
        nidx, ndist, ndeg = _g[0], _g[1], _g[2]
        sx, sy = _sample_offsets(_SAMPLE_K)
        # Candidate towns within 2R of each town (ascending index).
        # Triangle inequality: the nearest town to any sample in i's
        # ring is at most 2R from i, so restricting to candidates is
        # exact; the 1e-9 slack dwarfs float noise at the boundary.
        # The 60 km lists below already hold exact distances — filtering
        # preserves their ascending order, so these match the old
        # matrix-thresholded candidates bit-for-bit.
        reach = 2.0 * config.farm_radius_km * (1.0 + 1e-9)
        degs = np.zeros(n, dtype=np.int64)
        for i in range(n):
            degs[i] = int(np.count_nonzero(ndist[i, :ndeg[i]] <= reach))
        nbrs = np.zeros((n, int(degs.max())), dtype=np.int64)
        for i in range(n):
            m = ndist[i, :ndeg[i]] <= reach
            nbrs[i, :degs[i]] = nidx[i, :ndeg[i]][m]
        if _has_numba:
            _land_kernel(xs, ys, sx, sy, config.farm_radius_km, nbrs, degs, areas)
        else:
            _land_fallback(xs, ys, sx, sy, config.farm_radius_km, nbrs, degs, areas)
    _land_cache["key"] = key
    _land_cache["areas"] = areas
    return areas


def _land_try_incremental(towns, config, map_w, map_h, key):
    """Fast path for single founding/death: recompute only towns within
    2R of the event (triangle inequality: only their samples can change
    hands). Unaffected towns keep cached areas by id. Else None."""
    old_key = _land_cache.get("key")
    old_areas = _land_cache.get("areas")
    if old_key is None or old_areas is None:
        return None
    if old_key[1:] != (map_w, map_h):
        return None
    cls = _classify(old_key[0], key[0])
    if cls[0] == "found":
        ex, ey = cls[1][1], cls[1][2]
    elif cls[0] == "death":
        ex, ey = cls[1][1], cls[1][2]
    else:
        return None
    _g = _geo(towns, config)
    nidx, ndist, ndeg, xs, ys = _g[0], _g[1], _g[2], _g[4], _g[5]
    n = len(towns)
    new_by_id = {t[0]: k for k, t in enumerate(key[0])}
    areas = np.zeros(n, dtype=np.float64)
    for k, t in enumerate(old_key[0]):
        if t[0] in new_by_id:
            areas[new_by_id[t[0]]] = float(old_areas[k])
    reach = 2.0 * config.farm_radius_km * (1.0 + 1e-9)
    d = np.sqrt((xs - ex) ** 2 + (ys - ey) ** 2)
    affected = sorted(int(i) for i in range(n) if d[i] <= reach)
    degs = np.zeros(n, dtype=np.int64)
    rows = {}
    for i in affected:
        m = ndist[i, :ndeg[i]] <= reach
        rows[i] = nidx[i, :ndeg[i]][m]
        degs[i] = len(rows[i])
    md = max([len(r) for r in rows.values()], default=0)
    nbrs = np.zeros((n, max(1, md)), dtype=np.int64)
    for i in affected:
        nbrs[i, :degs[i]] = rows[i]
    sx, sy = _sample_offsets(_SAMPLE_K)
    _land_fallback(xs, ys, sx, sy, config.farm_radius_km, nbrs, degs,
                    areas, only=affected)
    return areas


# ---------------------------------------------------------------------------
# Trade: greedy nearest-first transportation with caps

try:
    import numba as _numba

    @_numba.njit(cache=True)
    def _trade_kernel(ii, jj, dd, S, pops, tau, imports, exports):
        # Equalize S/P over a cached canonical pair order (see
        # _trade_order), discounted by melt (see _trade): while the donor
        # is better fed, move food toward lossy pairwise equality.
        # pops<=0 pairs are geometry-listed but skipped. Returns melted.
        # melt = 0 is bit-exact with the melt-free kernel (delta = 1.0
        # multiplies exactly; denominator ordered to match).
        melted = 0.0
        for oi in range(ii.shape[0]):
            i = ii[oi]
            j = jj[oi]
            if pops[i] <= 0.0 or pops[j] <= 0.0:
                continue
            spi = S[i] / pops[i]
            spj = S[j] / pops[j]
            if spj > spi:
                delta = math.exp(-tau[i] * dd[oi])
                f = ((spj - spi) * pops[i] * pops[j] /
                     (pops[i] + delta * pops[j]))
                if f > S[j]:
                    f = S[j]
                if f > 0.0:
                    got = f * delta
                    S[i] += got
                    S[j] -= f
                    imports[i] += got
                    exports[j] += f
                    melted += f - got
        return melted

    @_numba.njit(cache=True)
    def _trade_enum(nidx, ndist, ndeg, pops, ds, ii, jj):
        # Enumerate all in-reach (i, j), i != j, pops > 0 (unsorted).
        k = 0
        for i in range(nidx.shape[0]):
            if pops[i] <= 0.0:
                continue
            for mm in range(ndeg[i]):
                j = nidx[i, mm]
                if j != i and pops[j] > 0.0:
                    ds[k] = ndist[i, mm]
                    ii[k] = i
                    jj[k] = j
                    k += 1
        return k

    @_numba.njit(cache=True)
    def _order_merge(o_dd, o_ii, o_jj, n_dd, n_ii, n_jj, t_dd, t_ii,
                     t_jj):
        # Merge two lex-sorted (d, i, j) runs. Exact: same multiset +
        # total lex order in, same array out as a fresh lexsort.
        a = 0
        b = 0
        c = 0
        na = o_ii.shape[0]
        nb = n_ii.shape[0]
        while a < na and b < nb:
            if (n_dd[b] < o_dd[a] or (n_dd[b] == o_dd[a] and
                    (n_ii[b] < o_ii[a] or (n_ii[b] == o_ii[a] and
                     n_jj[b] < o_jj[a])))):
                t_dd[c] = n_dd[b]
                t_ii[c] = n_ii[b]
                t_jj[c] = n_jj[b]
                b += 1
            else:
                t_dd[c] = o_dd[a]
                t_ii[c] = o_ii[a]
                t_jj[c] = o_jj[a]
                a += 1
            c += 1
        while a < na:
            t_dd[c] = o_dd[a]
            t_ii[c] = o_ii[a]
            t_jj[c] = o_jj[a]
            a += 1
            c += 1
        while b < nb:
            t_dd[c] = n_dd[b]
            t_ii[c] = n_ii[b]
            t_jj[c] = n_jj[b]
            b += 1
            c += 1
        return c

    @_numba.njit(cache=True)
    def _order_compact(o_dd, o_ii, o_jj, d, t_dd, t_ii, t_jj):
        # Drop pairs touching d, remap higher indices down once. Drops
        # preserve relative order and monotone remap preserves lex order,
        # so the result equals a fresh lexsort of the post-removal pairs.
        c = 0
        for k in range(o_ii.shape[0]):
            i = o_ii[k]
            j = o_jj[k]
            if i == d or j == d:
                continue
            t_dd[c] = o_dd[k]
            t_ii[c] = i - 1 if i > d else i
            t_jj[c] = j - 1 if j > d else j
            c += 1
        return c

    _has_trade_numba = True
except Exception:  # pragma: no cover
    _has_trade_numba = False
    _trade_kernel = None  # type: ignore
    _trade_enum = None  # type: ignore
    _order_merge = None  # type: ignore
    _order_compact = None  # type: ignore


# Cached canonical trade order: all in-reach (i, j) sorted by
# (distance, i, j), with distances kept for merging. Geometry-only (no
# pops/S): steady turns reuse it untouched. Lexicographic = canonical:
# every correct builder reproduces it, and tie order is provably
# irrelevant (reversed ties give bit-identical S). Incremental events
# (append/compact) maintain canonicity exactly — same multiset, same
# total order as a fresh lexsort — or it falls back to full rebuild.
_trade_cache = {"key": None, "ii": None, "jj": None, "dd": None,
                "geokey": None}


def _trade_build(geo, config):
    nidx, ndist, ndeg = geo[0], geo[1], geo[2]
    n = nidx.shape[0]
    m = int(np.sum(ndeg))
    ds = np.empty(m, dtype=np.float64)
    ii = np.empty(m, dtype=np.int64)
    jj = np.empty(m, dtype=np.int64)
    if _has_trade_numba:
        pops_ones = np.ones(n, dtype=np.float64)
        k = _trade_enum(nidx, ndist, ndeg, pops_ones, ds, ii, jj)
    else:
        k = 0
        for i in range(n):
            for mm in range(ndeg[i]):
                j = int(nidx[i, mm])
                if j != i:
                    ds[k] = ndist[i, mm]
                    ii[k] = i
                    jj[k] = j
                    k += 1
    ds, ii, jj = ds[:k], ii[:k], jj[:k]
    perm = np.lexsort((jj, ii, ds))  # canonical: distance, then i, then j
    return ii[perm], jj[perm], ds[perm]


def _trade_order(geo, config):
    nidx, ndist, ndeg = geo[0], geo[1], geo[2]
    n = nidx.shape[0]
    # Content key: coords determine pair membership (fixed reach).
    # Never ambient cache state (tests pass foreign geos with stale keys).
    xs, ys = geo[4], geo[5]
    key = (n, int(np.sum(ndeg)), hash((xs.tobytes(), ys.tobytes())),
           float(config.cart_distance_km))
    if _trade_cache["key"] == key and _trade_cache["ii"] is not None:
        return (_trade_cache["ii"], _trade_cache["jj"],
                _trade_cache["dd"])
    ev = _geo_cache.get("event")
    src = _trade_cache.get("geokey")
    prev = _geo_cache.get("prev_key")
    if (ev is not None and src is not None and src == prev
            and _trade_cache["ii"] is not None and _has_trade_numba):
        o_ii, o_jj, o_dd = (_trade_cache["ii"], _trade_cache["jj"],
                            _trade_cache["dd"])
        if ev[0] == "append":
            # Newcomer is index n-1 (append-at-end, verified by geo).
            # Pairs: its row plus mirrors (membership is symmetric).
            row = nidx[n - 1, :ndeg[n - 1]]
            dst = ndist[n - 1, :ndeg[n - 1]]
            m = [(float(dst[t]), n - 1, int(row[t])) for t in range(len(row))
                 if int(row[t]) != n - 1]
            m += [(d, i, n - 1) for (d, _, i) in m]
            if m:
                m_arr = np.array(m, dtype=[("d", float), ("i", int),
                                            ("j", int)])
                m_arr.sort(order=("d", "i", "j"))
                n_dd = m_arr["d"].astype(np.float64)
                n_ii = m_arr["i"].astype(np.int64)
                n_jj = m_arr["j"].astype(np.int64)
                t_dd = np.empty(len(o_dd) + len(n_dd), dtype=np.float64)
                t_ii = np.empty(len(o_ii) + len(n_ii), dtype=np.int64)
                t_jj = np.empty(len(o_jj) + len(n_jj), dtype=np.int64)
                c = _order_merge(o_dd, o_ii, o_jj, n_dd, n_ii, n_jj,
                                 t_dd, t_ii, t_jj)
                ii, jj, dd = t_ii[:c], t_jj[:c], t_dd[:c]
                _trade_cache.update(key=key, ii=ii, jj=jj, dd=dd,
                                    geokey=_geo_cache.get("key"))
                return ii, jj, dd
            ii, jj, dd = o_ii, o_jj, o_dd
            _trade_cache.update(key=key, ii=ii, jj=jj, dd=dd, geokey=_geo_cache.get("key"))
            return ii, jj, dd
        if ev[0] == "remove":
            d = ev[1]
            t_dd = np.empty_like(o_dd)
            t_ii = np.empty_like(o_ii)
            t_jj = np.empty_like(o_jj)
            c = _order_compact(o_dd, o_ii, o_jj, d, t_dd, t_ii, t_jj)
            ii, jj, dd = t_ii[:c], t_jj[:c], t_dd[:c]
            _trade_cache.update(key=key, ii=ii, jj=jj, dd=dd, geokey=_geo_cache.get("key"))
            return ii, jj, dd
    ii, jj, dd = _trade_build(geo, config)
    _trade_cache.update(key=key, ii=ii, jj=jj, dd=dd, geokey=_geo_cache.get("key"))
    return ii, jj, dd


def _trade(S: np.ndarray, pops: np.ndarray, geo,
           config: GameConfig):
    """Equalize food per head within reach (S mutated in place),
    discounted by melt (see below).

    Nearest pair first; while the donor is better fed, move food toward
    lossy pairwise equality. Hungry mouths eat first; donors never fall
    below recipients (no inversion, no starvation by trade). Returns
    (imports, exports, melted). Melt: a unit sent over distance d to a
    recipient of pop P arrives as exp(-tau*d) with tau = melt*Pm/(Pm+P)
    (big importers have roads; melt = 0 disables loss bit-exactly).
    geo is the (nidx, ndist, ndeg, xs, ys) tuple from _geo."""
    n = len(S)
    imports = np.zeros(n, dtype=np.float64)
    exports = np.zeros(n, dtype=np.float64)
    if n < 2:
        return imports, exports, 0.0
    ii, jj, dd = _trade_order(geo, config)
    p_market = derived(config)[1]
    melt = max(config.melt_per_km, 0.0)
    tau = melt * p_market / (p_market + np.maximum(pops, 0.0))
    if _has_trade_numba:
        melted = _trade_kernel(ii, jj, dd, S, pops, tau, imports, exports)
        return imports, exports, float(melted)
    melted = 0.0
    for oi in range(ii.shape[0]):
        i = int(ii[oi])
        j = int(jj[oi])
        if pops[i] <= 0.0 or pops[j] <= 0.0:
            continue
        spi = S[i] / pops[i]
        spj = S[j] / pops[j]
        if spj > spi:
            delta = math.exp(-tau[i] * dd[oi])
            f = ((spj - spi) * pops[i] * pops[j] /
                 (pops[i] + delta * pops[j]))
            f = min(f, S[j])
            if f > 0.0:
                got = f * delta
                S[i] += got
                S[j] -= f
                imports[i] += got
                exports[j] += f
                melted += f - got
    return imports, exports, melted


try:
    import numba as _numba2

    @_numba2.njit(cache=True)
    def _market_kernel(xs, ys, offer, cart_km, ln2, rcut, out):
        """Market accumulation over coordinates (ascending j per town).

        Same pairs in the same order with the same distances as the stored
        lists below the old reach edge — bit-identical sums there — plus
        the thin tail out to rcut (one rule: nothing economic travels
        beyond sight/mail range)."""
        n = xs.shape[0]
        r2cut = rcut * rcut
        for i in range(n):
            s = 0.0
            xi = xs[i]
            yi = ys[i]
            for j in range(n):
                c = offer[j]
                if c != 0.0:
                    dx = xi - xs[j]
                    dy = yi - ys[j]
                    d2 = dx * dx + dy * dy
                    if d2 <= r2cut:
                        s += math.exp(-math.sqrt(d2) * ln2 / cart_km) * c
            out[i] = s

    @_numba2.njit(cache=True)
    def _frontier_kernel(xs, ys, offer, frange, mx):
        # Best offer within teaching range per town: j teaches i iff
        # d(i,j) <= range(pop_j) (continuous fame; self always qualifies).
        # Pure max: order-independent, bit-exact under any walk.
        n = xs.shape[0]
        for i in range(n):
            best = 0.0
            xi = xs[i]
            yi = ys[i]
            for j in range(n):
                oj = offer[j]
                if oj > best:
                    dx = xs[j] - xi
                    dy = ys[j] - yi
                    r = frange[j]
                    if dx * dx + dy * dy <= r * r:
                        best = oj
            mx[i] = best

    _has_market_numba = True
except Exception:  # pragma: no cover
    _has_market_numba = False
    _market_kernel = None  # type: ignore
    _frontier_kernel = None  # type: ignore


# Fame range: how far a town's methods travel, continuous in population.
# Anchors (1k -> daily-walk 10km, 5k -> commercial 60km, 50k -> 150km max):
# log curve through the lower pair, steeper log past 5k (word spreads faster
# once truly famous), capped at sight/mail range. Floor is the daily walk
# (2R), so small towns teach exactly as before; zero new parameters.
_FAME_K1 = 50.0 / math.log(5.0)    # 10 + K1*ln(P/1000): 5k -> 60
_FAME_K2 = 90.0 / math.log(10.0)   # 60 + K2*ln(P/5000): 50k -> 150


def fame_range_km(pop: float, config: GameConfig) -> float:
    """Teaching range of one town: 10km at/below 1k, ~60km at 5k,
    150km (info_speed) at/above 50k, log-smooth between."""
    learn = 2.0 * config.farm_radius_km
    if pop <= 1000.0:
        return learn
    if pop <= 5000.0:
        return learn + _FAME_K1 * math.log(pop / 1000.0)
    return min(float(config.info_speed),
               learn + 50.0 + _FAME_K2 * math.log(pop / 5000.0))


def _market_improvement(serv: np.ndarray, pops: np.ndarray, geo,
                        config: GameConfig, p_market: float,
                        last: np.ndarray) -> np.ndarray:
    """Farm-output improvement = services per head served, resold.

    mkt is the reachable non-farm population; the denominator is the
    population it serves, so the improvement is a service ratio (0
    remote, -> max_improvement where services are abundant). Each town
    offers its services scaled by what it received last turn, so market
    richness propagates one hop per turn (cold start = plain pairwise).
    geo is the (nidx, ndist, ndeg, xs, ys) tuple from _geo (frontier and
    market read coordinates directly; trade/migration keep the lists)."""
    n = len(serv)
    if n == 0:
        return np.zeros(0)
    ln2 = math.log(2.0)
    contrib = np.where(
        serv > 0.0,
        p_market * np.power(np.maximum(serv, 0.0) / p_market,
                            config.market_scaling),
        0.0,
    )
    offer = contrib * (1.0 + last)
    # Technique frontier: the best methods in teaching range set what is
    # available. Range is continuous in the teacher's population
    # (fame_range_km: daily-walk 10km at/below 1k, ~60km at 5k, 150km max),
    # so each tier owns its own shed; the value curve is unchanged
    # (gamma-1): one agglomeration exponent. At gamma=1 the frontier is
    # off (x**0==1). Uses town coordinates directly (not the 60km trade
    # lists), so far-famous pairs need no extra neighbor storage.
    xs, ys = geo[4], geo[5]
    learn = 2.0 * config.farm_radius_km
    frange = np.where(
        pops <= 1000.0, learn,
        np.minimum(float(config.info_speed),
                   np.where(pops <= 5000.0,
                            learn + _FAME_K1 * np.log(np.maximum(pops, 1000.0) / 1000.0),
                            learn + 50.0 + _FAME_K2 * np.log(np.maximum(pops, 5000.0) / 5000.0))))
    mx = np.zeros(n, dtype=np.float64)
    if _has_market_numba:
        _frontier_kernel(xs, ys, offer, frange, mx)
    else:
        for j in range(n):
            oj = float(offer[j])
            if oj <= 0.0:
                continue
            r = float(frange[j])
            d2 = (xs - xs[j]) ** 2 + (ys - ys[j]) ** 2
            m = d2 <= r * r
            mx[m] = np.maximum(mx[m], oj)
    gm1 = config.market_scaling - 1.0
    frontier = np.minimum(1.0, np.power(mx / p_market, gm1))
    mkt = np.zeros(n, dtype=np.float64)
    rcut = float(config.info_speed)
    if _has_market_numba:
        _market_kernel(xs, ys, offer,
                       config.cart_distance_km, ln2, rcut, mkt)
    else:
        for i in range(n):
            d2 = (xs - xs[i]) ** 2 + (ys - ys[i]) ** 2
            m = (d2 <= rcut * rcut) & (offer != 0.0)
            if np.any(m):
                dd = np.sqrt(d2[m])
                mkt[i] = np.sum(np.exp(-dd * ln2 / config.cart_distance_km)
                                * offer[m])
    return (config.max_improvement * frontier * mkt /
            (mkt + np.maximum(pops, 1e-12)))


# Row-block size for migration: bounds the N x N temporaries (each block
# holds ~4 x R x N floats). N <= block runs as a single block, which is
# bit-identical to the unblocked computation.
_MIG_BLOCK = 256
# Reused block buffers (kills per-block mmap/page-fault overhead).
# Same values, same op order, same reductions as fresh arrays — exact.
_mig_bufs = {"key": None, "bufs": None}
_RR = np.arange(_MIG_BLOCK)[:, None]

try:
    import numba as _numba3

    @_numba3.njit(cache=True)
    def _mig_build(Ab, popsB, pops, feed, Wb):
        # A = max(0, Pj-Pi)*feed_j*W fused. Same scalar ops in the same
        # order per element as the numpy chain — identical values.
        R = Ab.shape[0]
        n = Ab.shape[1]
        for r in range(R):
            pr = popsB[r]
            for j in range(n):
                g = pops[j] - pr
                if g < 0.0:
                    g = 0.0
                Ab[r, j] = g * feed[j] * Wb[r, j]

    @_numba3.njit(cache=True)
    def _mig_scale(Ab, outB, rs_safe):
        # A = (A*out)/rs fused. Mult-then-divide matches the numpy chain
        # bit-for-bit (mult commutes exactly); zero rows stay 0 via safe.
        R = Ab.shape[0]
        n = Ab.shape[1]
        for r in range(R):
            o = outB[r]
            s = rs_safe[r]
            for j in range(n):
                Ab[r, j] = Ab[r, j] * o / s

    _has_mig_numba = True
except Exception:  # pragma: no cover
    _has_mig_numba = False
    _mig_build = None  # type: ignore
    _mig_scale = None  # type: ignore


def _migration(pops: np.ndarray, S: np.ndarray, out_people: np.ndarray,
               geo, config: GameConfig) -> np.ndarray:
    """geo is the (nidx, ndist, ndeg, nweight, xs, ys) tuple from _geo."""
    n = len(pops)
    if n < 2:
        return np.zeros(n)
    with np.errstate(divide="ignore", invalid="ignore"):
        feed = np.where(pops > 0.0,
                        np.minimum(1.0, S / np.maximum(pops, 1e-12)), 0.0)
    nidx, nweight, ndeg = geo[0], geo[3], geo[2]
    key = (_MIG_BLOCK, n)
    if _mig_bufs["key"] != key:
        _mig_bufs["key"] = key
        _mig_bufs["bufs"] = [np.zeros((_MIG_BLOCK, n), dtype=np.float64),
                              np.zeros((_MIG_BLOCK, n), dtype=np.float64)]
    Wb0, Ab0 = _mig_bufs["bufs"]
    inflow = np.zeros(n, dtype=np.float64)
    outflow = np.zeros(n, dtype=np.float64)
    for r0 in range(0, n, _MIG_BLOCK):
        B = slice(r0, min(r0 + _MIG_BLOCK, n))
        R = min(r0 + _MIG_BLOCK, n) - r0
        Wb, Ab = Wb0[:R], Ab0[:R]
        # Scatter cached weights (padding writes 1.0 onto the self column
        # = its true weight, so order is irrelevant). Values match the old
        # exp*win computation bit-for-bit.
        Wb.fill(0.0)
        Wb[_RR[:R], nidx[B]] = nweight[B]
        # gap -> A (fused numba, or numpy chain: same scalar ops/order).
        if _has_mig_numba:
            _mig_build(Ab, pops[B], pops, feed, Wb)
        else:
            np.subtract(pops[None, :], pops[B, None], out=Ab)
            np.maximum(0.0, Ab, out=Ab)
            Ab *= feed[None, :]
            Ab *= Wb
        rs_b = Ab.sum(axis=1)
        # Flow in place: (A*out)/rs matches (out*A)/rs bit-for-bit
        # (mult commutes exactly); zero rows stay 0 via rs_safe.
        rs_safe = np.where(rs_b > 0.0, rs_b, 1.0)
        if _has_mig_numba:
            _mig_scale(Ab, out_people[B], rs_safe)
        else:
            Ab *= out_people[B, None]
            Ab /= rs_safe[:, None]
        outflow[B] = Ab.sum(axis=1)
        inflow += Ab.sum(axis=0)
    return inflow - outflow


# ---------------------------------------------------------------------------
# Core step

def _step_core(towns: list[Town], map_size, config: GameConfig):
    """One turn of the economy. One cross-turn state lives on the towns:
    last_improvement (what each town received last turn), which scales
    what it offers this turn — market richness propagates one hop per
    turn. Everything else resolves in a single pass: land -> own-land
    production -> services -> improvement -> trade -> births/deaths ->
    migration. Cold start (all zero) is exactly pairwise.
    """
    n = len(towns)
    if n == 0:
        return np.zeros(0), np.zeros(0)
    pops = np.array([t.population for t in towns], dtype=np.float64)
    y_ring, p_market, h, b_t, m_t, th_t, nu_t = derived(config)
    sf = max(config.farm_workers_yield, 1e-12)
    areas = land_areas(towns, map_size, config)
    # No n>=2 shortcuts: a lone town earns its own-services improvement
    # too. (Skipping it would make founding a faraway town improve
    # everyone — action at a distance. _trade/_migration no-op below.)
    geo = _geo(towns, config)
    base_prod = production(config, areas, pops)
    last = np.array([t.last_improvement for t in towns], dtype=np.float64)
    # Farmers staffed at expected (boosted) yields: improved towns need
    # fewer hands, freeing services. Cold start (last=0) is identical.
    serv = np.maximum(0.0, pops - base_prod / (sf * (1.0 + last)))
    improvement = _market_improvement(serv, pops, geo, config, p_market, last)
    for t, v in zip(towns, improvement):
        t.last_improvement = float(v)
    prod = (1.0 + improvement) * base_prod
    S = prod.copy()
    imports, exports, melted = _trade(S, pops, geo, config)
    assert abs(S.sum() - (prod.sum() - melted)) < 1e-6 * max(prod.sum(), 1.0)
    births = b_t * pops  # fixed: food acts through deaths, not births
    sp = S / np.maximum(pops, 1e-12)
    deaths = m_t * pops * np.power(np.maximum(sp, 1e-9),
                                   -config.starvation_elasticity)
    p_surp = serv  # same non-farm people
    out_people = th_t * pops + nu_t * p_surp
    net_mig = _migration(pops, S, out_people, geo, config)
    new_pops = np.maximum(0.0, pops + births - deaths + net_mig)
    return new_pops, serv


def base_growth(population: float, config: GameConfig) -> float:
    """Net growth per turn of a lone settlement (full ring, no neighbours,
    no market improvement) — the no-services analytic baseline. A real
    lone town still earns its own-services improvement via _step_core."""
    _y_ring, _p_market, _h, b_t, m_t, _th, _nu = derived(config)
    area = np.array([math.pi * config.farm_radius_km ** 2])
    pops = np.array([float(population)])
    prod = float(production(config, area, pops)[0])
    s = prod / max(population, 1e-12)
    return (b_t * population
            - m_t * population * max(s, 1e-9) ** -config.starvation_elasticity)


def nets_for(all_towns: list[Town], config: GameConfig, map_size=None) -> list[float]:
    """Net population change per town for one turn (no mutation).

    Pure query: snapshots and restores last_improvement, so measuring
    rates never advances the resell state. Only _step_core (a turn)
    advances it."""
    towns = list(all_towns)
    if not towns:
        return []
    saved = [t.last_improvement for t in towns]
    try:
        pops = np.array([t.population for t in towns], dtype=np.float64)
        new_pops, _ = _step_core(towns, map_size or [1000, 1000], config)
        return (new_pops - pops).tolist()
    finally:
        for t, v in zip(towns, saved):
            t.last_improvement = v



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
        return events
    towns = world.towns
    old = [t.population for t in towns]
    new_pops, _serv = _step_core(towns, world.map_size, config)
    for t, p in zip(towns, new_pops):
        t.population = float(p)
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
        try:
            requested = float(so.args[1]) if len(so.args) >= 2 else config.army_cost
        except (ValueError, TypeError):
            requested = config.army_cost
        if requested <= 0.0:
            if so in world.standing_orders:
                world.standing_orders.remove(so)
            continue
        # TRAIN draws at most max_train_frac of the town's people.
        size = min(requested, config.max_train_frac * town.population)
        original_pop = town.population
        town.population -= size
        should_spawn = original_pop >= size - 1e-9
        if should_spawn:
            new_id = world.allocate_id()
            army = Army(id=new_id, faction=original_faction, x=town.x, y=town.y, is_viceroy=False, size=size)
            world.armies.append(army)
            events.append({"kind": "army_spawn", "id": army.id, "faction": army.faction, "x": army.x, "y": army.y, "is_viceroy": False, "size": army.size})
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
            try:
                tx, ty = float(so.args[0]), float(so.args[1])
                size = float(so.args[2]) if len(so.args) >= 3 else config.army_cost
            except Exception:
                tx, ty = float(so.args[0]), float(so.args[1])
                size = config.army_cost
        else:
            tx, ty = army.x, army.y
            size = config.army_cost
        tx, ty = world.clamp_position(tx, ty)
        # Exact site: the army must stand on the build spot.
        dist = math.hypot(army.x - tx, army.y - ty)
        if dist > 1e-9:
            if so in world.standing_orders:
                world.standing_orders.remove(so)
            continue
        found_town = None
        for t in world.towns:
            if math.hypot(t.x - tx, t.y - ty) <= 1e-9:
                found_town = t
                break
        if found_town is not None and found_town.faction != army.faction:
            # Blocked by an enemy town: BUILD is single-turn, so the order
            # lapses (the army can take the town and rebuild next turn).
            if so in world.standing_orders:
                world.standing_orders.remove(so)
            continue
        if size <= 0.0:
            if so in world.standing_orders:
                world.standing_orders.remove(so)
            continue
        # Spend at most the army's whole size; the rest marches on.
        used = min(size, army.size)
        gain = used * config.build_efficiency
        aid = army.id
        ax, ay = army.x, army.y
        army.size -= used
        if so in world.standing_orders:
            try:
                world.standing_orders.remove(so)
            except ValueError:
                pass
        if army.size <= 1e-9:
            world.remove_army(aid)
            events.append({"kind": "army_death", "id": aid, "x": ax, "y": ay})
        if found_town is not None:
            found_town.population += gain
        else:
            new_id = world.allocate_id()
            new_town = Town(id=new_id, faction=army.faction, x=tx, y=ty, population=gain, is_capital=False)
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
