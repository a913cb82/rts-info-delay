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
TRAIN_SIZE = 30.0     # v3: small-fast trains beat big-slow (CAD 718)
TRAIN_FLOOR = 350.0   # train iff pop >= this (CAD winner)
COOLDOWN = 750        # growth-train cooldown per town (T2 cadence)
BOOST_BELOW = 210.0   # colonies below this get boosted (T2 track)
FOUND_SIZE = 450.0    # founding spend target (equilibrium scale; leftovers continue)
CHUNK = 500.0         # max single BUILD spend (big armies chain-spend; E9: no overshoot)
TRIAGE_GROWTH = -0.01   # town shrinking faster than 1%/turn is dying: shed (no floor)
ARRIVED = 1.0         # km: close enough to count as landed (exact engine)
SIGHT = 150.0         # vision/muster-trigger range

_LAST_TRAIN: dict[int, int] = {}
_ANCHOR: list | None = None  # lattice anchor (capital pos, first turn)
_SITE_CACHE: dict = {}  # town-signature -> sorted free-site list


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
    ax, ay, mw, mh, _ = key
    own = state.own_towns()
    foes = [t for t in state.world.towns
            if t.faction != state.faction and t.faction is not None]
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
                if any(math.hypot(x - t.x, y - t.y) < MIN_DIST for t in own):
                    continue
                if any(math.hypot(x - t.x, y - t.y) < 30.0 for t in foes):
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
    out = []
    for t in small:
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


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    turn = state.turn
    own_t = state.own_towns()
    if not own_t:
        return out
    cap = state.world.faction_capital(state.faction)
    cap_id = cap.id if cap is not None else None

    def cooled(t) -> bool:
        # floor governs; triage: dying towns shed regardless (mouths die otherwise)
        if t.id in state._pending_trains:
            return False
        if t.population >= TRAIN_FLOOR:
            return True
        try:
            g = state.get_growth(t.id)
        except Exception:
            g = None
        return g is not None and g < TRIAGE_GROWTH * max(1.0, t.population)

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
    # en-route coverage: armies already marching count toward missions.
    enroute: list[tuple[float, float]] = []
    for a in state.own_armies():
        if a.is_viceroy or not state.army_has_target(a.id) or state.has_pending_build(a.id):
            continue
        tgt = state.army_target(a.id)
        if tgt is not None:
            enroute.append(tgt)
    needy = [t for t in sorted(
        (t for t in own_t if t.population < BOOST_BELOW),
        key=lambda t: t.population)
        if not any(math.hypot(t.x - ex, t.y - ey) < 5.0 for ex, ey in enroute)]
    pioneer_busy = any(not any(math.hypot(ex - t.x, ey - t.y) < MIN_DIST for t in own_t)
                        for ex, ey in enroute)
    # densify openings (4km around <=300 towns), excluding en-route/used
    def _dense_open(excl):
        s = _densify_site(state, config, excl)
        return s
    dense_busy = any(any(math.hypot(ex - t.x, ey - t.y) < DENSE_DIST * 2 for t in own_t
                          if t.population <= DENSE_MAX_POP)
                     for ex, ey in enroute)
    idle = [a for a in state.own_armies()
            if not a.is_viceroy and not state.army_has_target(a.id)
            and not state.has_pending_build(a.id) and a.size >= MIN_ARMY]
    # site lists computed ONCE (per-army rescans killed the clock: 0.9s/turn).
    _esig = tuple(sorted((round(ex, 1), round(ey, 1)) for ex, ey in enroute))
    _skey = _site_key(state, config)
    _pkey = (_skey, _esig)
    _pcache = _SITE_CACHE.get(_pkey)
    if _pcache is None:
        _pcache = [s for s in _all_sites(state, config)
                   if not any(math.hypot(s[0] - ex, s[1] - ey) < MIN_DIST for ex, ey in enroute)]
        _SITE_CACHE[_pkey] = _pcache
        if len(_SITE_CACHE) > 12:
            _SITE_CACHE.pop(next(iter(_SITE_CACHE)))
    psites = _pcache
    _dkey = (_skey, _esig, "d")
    _dcache = _SITE_CACHE.get(_dkey)
    if _dcache is None:
        _dcache = _densify_list(state, config, enroute)
        _SITE_CACHE[_dkey] = _dcache
    dsites = _dcache
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
            else:
                out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {tgt.x:.1f} {tgt.y:.1f}")
            continue
        site = None
        if didx < len(dsites):
            site = dsites[didx]
            didx += 1
        elif pidx < len(psites):
            site = psites[pidx]
            pidx += 1
        if site is None:
            break
        if math.hypot(a.x - site[0], a.y - site[1]) <= ARRIVED:
            out.append(f"BUILD {a.id} {site[0]:.1f} {site[1]:.1f} {min(a.size, FOUND_SIZE):.1f}")
        else:
            out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {site[0]:.1f} {site[1]:.1f}")
        used_sites.append(site)

    # 3. growth trains, mouth-accounted (general across scales: train what's
    # needed; big towns make exact-size armies, no flood, no starvation).
    want = sum(max(0.0, min(BOOST_BELOW - t.population, CHUNK))
               for t in own_t if t.population < BOOST_BELOW
               and not any(math.hypot(t.x - ex, t.y - ey) < 5.0 for ex, ey in enroute))
    if not pioneer_busy and pidx < len(psites):
        want += FOUND_SIZE
    if not dense_busy and didx < len(dsites):
        want += FOUND_SIZE
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
