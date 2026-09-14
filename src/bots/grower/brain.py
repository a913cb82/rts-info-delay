"""grower brain — peaceful maximal growth (pioneer + boost + JIT muster).

Playbook (all numbers experimental, BOT_WORKLOG early-game series):
- hands in pockets (pop-watch free; train nothing unpriced)
- pioneer on 16km hex lattice (coarse market band; min 8km from towns)
- boost colonies <150 every ~750t (47->210 track; beats founding ~5x)
- JIT muster vs visible threats (defense is score-neutral; T6)
- no standing armies (all mouths farm or compound), no scouts (T8)
"""
from __future__ import annotations
import math
from engine.config import GameConfig
from .intel import GrowerState as BotState

LATTICE = 16.0        # pioneer hex spacing (market band 13-18km)
MIN_DIST = 8.0        # min founding distance from any own town (P1: 4km spirals)
MIN_ARMY = 10.0      # armies below this get no missions (starve/merge; don't spam 0.0)
MIN_TRAIN = 20.0      # never train below this (9-towns die; skip until want>=20)
SCAN_R = 400.0        # pioneer scan radius (cached; full-map fallback when empty)
DENSE_DIST = 4.0      # densify ring radius around small towns (P2/P2b)
DENSE_MAX_POP = 300.0 # densify only around towns <= this (mild gradient)
DENSE_HOLE_R = 30.0  # no densify near 800+ towns (feeds black holes -> crash)
DENSE_HOLE_POP = 800.0
TRAIN_SIZE = 30.0     # v3: small-fast trains beat big-slow (CAD 718)
TRAIN_FLOOR = 350.0   # normal floor (v9-trickle dynamics, honest cadence)
TRAIN_COOLDOWN = 50     # per-town trickle spacing (matches accidental-50 that scored)
COOLDOWN = 750        # growth-train cooldown per town (T2 cadence)
BOOST_BELOW = 210.0   # colonies below this get boosted (T2 track)
FOUND_SIZE = 450.0    # legacy founding target (superseded by tier spends)
MARKET_SPEND = 667.0   # 16km-site spend -> 600-town (E1 self-sufficient grower)
VILLAGE_SPEND = 333.0  # 4km-site spend -> 300-town (T3 grows +0.2%/yr)
CHUNK = 500.0         # max single BUILD spend (big armies chain-spend; E9: no overshoot)
TRIAGE_GROWTH = -0.01   # town shrinking faster than 1%/turn is dying: shed (no floor)
ARRIVED = 1.0         # km: close enough to count as landed (exact engine)
SIGHT = 150.0         # vision/muster-trigger range

_LAST_TRAIN: dict[int, int] = {}
_ANCHOR: list | None = None  # lattice anchor (capital pos, first turn)
_SITE_CACHE: dict = {}  # town-signature -> sorted free-site list
_LAST_SCAN: dict = {}  # cache-key-kind -> turn of last full rescan


def _anchor(state) -> tuple[float, float]:
    global _ANCHOR
    if _ANCHOR is None:
        cap = state.world.faction_capital(state.faction)
        own = state.own_towns()
        src = cap if cap is not None else (own[0] if own else None)
        _ANCHOR = (src.x, src.y) if src is not None else (500.0, 500.0)
    return _ANCHOR


def _site_key(state, config):
    ax, ay = _anchor(state)
    mw, mh = config.map_size if getattr(config, "map_size", None) else (1000, 1000)
    own = state.own_towns()
    return (ax, ay, mw, mh, tuple(sorted((t.id, round(t.x, 1), round(t.y, 1)) for t in own)))


def _all_sites(state, config) -> list[tuple[float, float]]:
    """Free-site list by distance, cached by town signature (16k scan)."""
    key = _site_key(state, config)
    hit = _SITE_CACHE.get(key)
    if hit is not None:
        return hit
    _LAST_SCAN["sites"] = state.turn
    ax, ay, mw, mh, _ = key
    own = state.own_towns()
    foes = [t for t in state.world.towns
            if t.faction != state.faction and t.faction is not None]
    _og = _grid([(t.x, t.y, 1) for t in own], 16.0)
    _fg = _grid([(t.x, t.y, 1) for t in foes], 32.0)
    for R in (int(SCAN_R / LATTICE) + 2, int(max(mw, mh) / LATTICE) + 2):
        pts = []
        for j in range(-R, R + 1):
            y = ay + j * LATTICE * math.sqrt(3) / 2
            if y < 5 or y > mh - 5:
                continue
            off = LATTICE / 2 if j % 2 else 0.0
            for i in range(-R, R + 1):
                x = ax + off + i * LATTICE
                if x < 5 or x > mw - 5:
                    continue
                if _near(_og, 16.0, x, y, MIN_DIST):
                    continue
                if _near(_fg, 32.0, x, y, 30.0):
                    continue
                pts.append((math.hypot(x - ax, y - ay), (x, y)))
        if pts:
            break
    pts.sort()
    out = [p for _, p in pts]
    _SITE_CACHE[key] = out
    if len(_SITE_CACHE) > 8:
        _SITE_CACHE.pop(next(iter(_SITE_CACHE)))
    return out


def _lattice_site(state, config, exclude=None) -> tuple[float, float] | None:
    """Nearest free pioneer site on the hex lattice (deterministic)."""
    excl = list(exclude) if exclude else []
    for (x, y) in _all_sites(state, config):
        if any(math.hypot(x - ex, y - ey) < MIN_DIST for ex, ey in excl):
            continue
        return (x, y)
    return None


def _train_size(t, config) -> float:
    frac = getattr(config, "max_train_frac", 0.1) or 0.1
    if t.population >= 700.0:
        return max(TRAIN_SIZE, t.population * frac)
    return min(TRAIN_SIZE, max(10.0, t.population * frac))


def _densify_list(state, config, exclude=None) -> list[tuple[float, float]]:
    """All 4km-ring points around <=300 towns, nearest-first (computed once)."""
    mw, mh = config.map_size if getattr(config, "map_size", None) else (1000, 1000)
    own = state.own_towns()
    excl = list(exclude) if exclude else []
    small = [t for t in own if t.population <= DENSE_MAX_POP]
    bigs = [(t.x, t.y) for t in own if t.population >= DENSE_HOLE_POP]
    out = []
    for t in small:
        if any(math.hypot(t.x - bx, t.y - by) < DENSE_HOLE_R for bx, by in bigs):
            continue  # hole brewing nearby: spread (pioneer) instead of feeding it
        for ring_r in (DENSE_DIST, DENSE_DIST * 2):
            for k in range(6):
                ang = k * math.pi / 3
                x, y = t.x + ring_r * math.cos(ang), t.y + ring_r * math.sin(ang)
                if x < 5 or x > mw - 5 or y < 5 or y > mh - 5:
                    continue
                if any(math.hypot(x - u.x, y - u.y) < DENSE_DIST for u in own):
                    continue
                if any(math.hypot(x - ex, y - ey) < DENSE_DIST for ex, ey in excl):
                    continue
                out.append((t.population, math.hypot(x - t.x, y - t.y), (x, y)))
    out.sort()
    return [p for _, _, p in out]


def _densify_site(state, config, exclude=None) -> tuple[float, float] | None:
    """Nearest 4km-ring point around a <=300 town (mild-gradient infill)."""
    lst = _densify_list(state, config, exclude)
    return lst[0] if lst else None


def _grid(pts, cell):
    """cell-size spatial index: dict cell -> list of (x, y, payload)."""
    g = {}
    for x, y, p in pts:
        g.setdefault((int(x // cell), int(y // cell)), []).append((x, y, p))
    return g


def _near(g, cell, x, y, r):
    """Any indexed point within r of (x, y) (checks 3x3 cells)."""
    cx, cy = int(x // cell), int(y // cell)
    r2 = r * r
    cr = int(r // cell) + 1
    for ix in range(cx - cr, cx + cr + 1):
        for iy in range(cy - cr, cy + cr + 1):
            for px, py, p in g.get((ix, iy), ()):
                dx, dy = px - x, py - y
                if dx * dx + dy * dy < r2:
                    return True
    return False


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    # big-state skip-turn (missions are multi-turn idempotent; halves average
    # cost so the bank pins at cap (spike-proof). Muster still runs every turn.
    _big = len(state.world.towns) + len(state.world.armies) > 30
    _quiet = not any(a.faction != state.faction and a.alive for a in state.world.armies)
    turn = state.turn
    own_t = state.own_towns()
    if not own_t:
        return out
    cap = state.world.faction_capital(state.faction)
    cap_id = cap.id if cap is not None else None

    def _triage(t) -> bool:
        try:
            g = state.get_growth(t.id)
        except Exception:
            return False
        return g is not None and g < TRIAGE_GROWTH * max(1.0, t.population)

    def cooled(t) -> bool:
        # pending (delivery) paces; floor-350 + trickle-50 govern (v9 dynamics)
        if t.id in state._pending_trains:
            return False
        return t.population >= TRAIN_FLOOR or _triage(t)

    # 1. JIT muster (T6: muster beats raids; defense is score-neutral).
    foe_armies = [a for a in state.world.armies
                  if a.faction != state.faction and a.alive]
    mustered: set[int] = set()
    if foe_armies:
        for t in own_t:
            if state.should_yield():
                break
            if t.id in state._pending_trains:
                continue
            if any(math.hypot(a.x - t.x, a.y - t.y) <= SIGHT for a in foe_armies):
                out.append(f"TRAIN {t.id} {_train_size(t, config):.1f}")
                state.note_train(t.id)
                mustered.add(t.id)

    # arrival release (belt-and-braces: update() already clears on sight).
    for a in state.own_armies():
        tgt = state.army_target(a.id)
        if tgt is not None and math.hypot(a.x - tgt[0], a.y - tgt[1]) <= ARRIVED:
            state._army_targets.pop(a.id, None)
    if _big and _quiet and turn % 2 == 1:
        return out  # skip-turn: missions/trains wait a turn (muster above already ran)
    # en-route coverage: armies already marching count toward missions.
    enroute: list[tuple[float, float]] = []
    for a in state.own_armies():
        if a.is_viceroy or not state.army_has_target(a.id) or state.has_pending_build(a.id):
            continue
        tgt = state.army_target(a.id)
        if tgt is not None:
            enroute.append(tgt)
    egrid = _grid([(ex, ey, 1) for ex, ey in enroute], 10.0)
    ogrid = _grid([(t.x, t.y, 1) for t in own_t], 16.0)
    needy = [t for t in sorted(
        (t for t in own_t if t.population < BOOST_BELOW),
        key=lambda t: t.population)
        if not _near(egrid, 10.0, t.x, t.y, 5.0)]
    pioneer_busy = any(not _near(ogrid, 16.0, ex, ey, MIN_DIST) for ex, ey in enroute)
    # densify openings (4km around <=300 towns), excluding en-route/used
    def _dense_open(excl):
        s = _densify_site(state, config, excl)
        return s
    sgrid = _grid([(t.x, t.y, 1) for t in own_t if t.population <= DENSE_MAX_POP], 16.0)
    dense_busy = any(_near(sgrid, 16.0, ex, ey, DENSE_DIST * 2) for ex, ey in enroute)
    idle = [a for a in state.own_armies()
            if not a.is_viceroy and not state.army_has_target(a.id)
            and not state.has_pending_build(a.id) and a.size >= MIN_ARMY]
    # site lists computed ONCE (per-army rescans killed the clock: 0.9s/turn).
    # site exclusion via grid (enroute churns; keyed caches never hit).
    _skey = _site_key(state, config)
    _sg = _SITE_CACHE.get((_skey, "grid"))
    if _sg is None:
        _full = _all_sites(state, config)
        _sg = (_full, _grid([(x, y, i) for i, (x, y) in enumerate(_full)], 16.0))
        _SITE_CACHE[(_skey, "grid")] = _sg
        if len(_SITE_CACHE) > 12:
            _SITE_CACHE.pop(next(iter(_SITE_CACHE)))
    _full, _sgrid = _sg
    _excl_idx: set[int] = set()
    for ex, ey in enroute:
        cx, cy = int(ex // 16.0), int(ey // 16.0)
        for ix in range(cx - 1, cx + 2):
            for iy in range(cy - 1, cy + 2):
                for px, py, pi in _sgrid.get((ix, iy), ()):
                    if (px - ex) ** 2 + (py - ey) ** 2 < MIN_DIST * MIN_DIST:
                        _excl_idx.add(pi)
    psites = [s for i, s in enumerate(_full) if i not in _excl_idx]
    _dkey = (_skey, "dense")
    _dcache = _SITE_CACHE.get(_dkey)
    if _dcache is None:
        _dcache = _densify_list(state, config, [])
        _SITE_CACHE[_dkey] = _dcache
    dsites = [s for s in _dcache
              if not any(math.hypot(s[0] - ex, s[1] - ey) < DENSE_DIST for ex, ey in enroute)]
    pidx = didx = 0
    used_sites: list[tuple[float, float]] = []
    for a in sorted(idle, key=lambda x: x.id):
        if state.should_yield():
            break
        if needy:
            tgt = needy.pop(0)
            spend = min(a.size, max(10.0, BOOST_BELOW - tgt.population), CHUNK)
            if math.hypot(a.x - tgt.x, a.y - tgt.y) <= ARRIVED:
                out.append(f"BUILD {a.id} {tgt.x:.1f} {tgt.y:.1f} {spend:.1f}")
            elif a.size >= 2 * spend:
                out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {tgt.x:.1f} {tgt.y:.1f} {spend:.1f}")
            else:
                out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {tgt.x:.1f} {tgt.y:.1f}")
            continue
        site = None
        spend_target = VILLAGE_SPEND
        if didx < len(dsites):
            site = dsites[didx]
            didx += 1
            spend_target = VILLAGE_SPEND
        elif pidx < len(psites):
            site = psites[pidx]
            pidx += 1
            spend_target = MARKET_SPEND
        if site is None:
            break
        if math.hypot(a.x - site[0], a.y - site[1]) <= ARRIVED:
            out.append(f"BUILD {a.id} {site[0]:.1f} {site[1]:.1f} {min(a.size, spend_target):.1f}")
        elif a.size >= 2 * spend_target:
            # split-to-mission: mover marches with spend, remainder stays for next mission
            out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {site[0]:.1f} {site[1]:.1f} {spend_target:.1f}")
        else:
            out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {site[0]:.1f} {site[1]:.1f}")
        used_sites.append(site)

    # 3. growth trains, mouth-accounted (general across scales: train what's
    # needed; big towns make exact-size armies, no flood, no starvation).
    want = sum(max(0.0, min(BOOST_BELOW - t.population, CHUNK)) for t in needy)
    if not pioneer_busy and pidx < len(psites):
        want += MARKET_SPEND
    if not dense_busy and didx < len(dsites):
        want += VILLAGE_SPEND
    short = want - sum(a.size for a in idle)
    if short >= MIN_TRAIN:
        cands = sorted((t for t in own_t if t.id not in mustered and cooled(t)),
                       key=lambda t: t.population, reverse=True)
        # ONE growth train per turn (CAD one-at-a-time; parallel floods pin the mother)
        t = cands[0] if cands else None
        if t is not None and not state.should_yield():
            size = min(_train_size(t, config), max(MIN_TRAIN, short))
            if not (t.population - size < TRAIN_FLOOR and t.population < 700.0 and cooled(t) and t.population >= TRAIN_FLOOR):
                out.append(f"TRAIN {t.id} {size:.1f}")
                state.note_train(t.id)
                _LAST_TRAIN[t.id] = turn
    return out
