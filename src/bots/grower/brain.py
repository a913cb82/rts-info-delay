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
from bots.expander.intel import BotState, silence_watch

LATTICE = 16.0        # pioneer hex spacing (market band 13-18km)
MIN_DIST = 8.0        # min founding distance from any own town (P1: 4km spirals)
DENSE_DIST = 4.0      # densify ring radius around small towns (P2/P2b)
DENSE_MAX_POP = 300.0 # densify only around towns <= this (mild gradient)
TRAIN_SIZE = 30.0     # v3: small-fast trains beat big-slow (CAD 718)
TRAIN_FLOOR = 350.0   # train iff pop >= this (CAD winner)
COOLDOWN = 750        # growth-train cooldown per town (T2 cadence)
BOOST_BELOW = 150.0   # colonies below this get boosted
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


def _all_sites(state, config) -> list[tuple[float, float]]:
    """Free-site list by distance, cached by town signature (16k scan)."""
    ax, ay = _anchor(state)
    mw, mh = config.map_size if getattr(config, "map_size", None) else (1000, 1000)
    own = state.own_towns()
    key = (ax, ay, mw, mh, tuple(sorted((t.id, round(t.x, 1), round(t.y, 1)) for t in own)))
    hit = _SITE_CACHE.get(key)
    if hit is not None:
        return hit
    foes = [t for t in state.world.towns
            if t.faction != state.faction and t.faction is not None]
    pts = []
    R = int(max(mw, mh) / LATTICE) + 2
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


def _densify_site(state, config, exclude=None) -> tuple[float, float] | None:
    """Nearest 4km-ring point around a <=300 town (mild-gradient infill)."""
    mw, mh = config.map_size if getattr(config, "map_size", None) else (1000, 1000)
    own = state.own_towns()
    excl = list(exclude) if exclude else []
    small = [t for t in own if t.population <= DENSE_MAX_POP]
    best = None
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
                d = math.hypot(x - t.x, y - t.y)
                if best is None or (t.population, d) < (best[0], best[1]):
                    best = (t.population, d, (x, y))
    return best[2] if best else None


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    silence_watch(state, config)  # release stale march notes (else armies look busy forever)
    turn = state.turn
    own_t = state.own_towns()
    if not own_t:
        return out
    cap = state.world.faction_capital(state.faction)
    cap_id = cap.id if cap is not None else None

    def cooled(t) -> bool:
        # v3: floor governs (CAD: no cooldown, recovery time is the governor)
        return (t.id not in state._pending_trains
                and t.population >= TRAIN_FLOOR)

    # 1. JIT muster (T6: muster beats raids; defense is score-neutral).
    foe_armies = [a for a in state.world.armies
                  if a.faction != state.faction]
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

    # arrival release: noted armies sitting on their target are functionally
    # idle (engine keeps has_target after landing; notes persist while observed).
    for a in state.own_armies():
        tgt = state.army_target(a.id)
        if tgt is not None and math.hypot(a.x - tgt[0], a.y - tgt[1]) <= ARRIVED:
            state._army_targets.pop(a.id, None)
            state.__dict__.get("_march_origin", {}).pop(a.id, None)
    # en-route coverage: armies already marching count toward missions.
    enroute: list[tuple[float, float]] = []
    for a in state.own_armies():
        if a.is_viceroy or not state.army_has_target(a.id) or state.has_pending_build(a.id):
            continue
        tgt = state.army_target(a.id)
        if tgt is not None:
            enroute.append(tgt)
    needy = [t for t in sorted(
        (t for t in own_t if t.id != cap_id and t.population < BOOST_BELOW),
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
            and not state.has_pending_build(a.id)]
    used_sites: list[tuple[float, float]] = []
    for a in sorted(idle, key=lambda x: x.id):
        if state.should_yield():
            break
        if needy:
            tgt = needy.pop(0)
            if math.hypot(a.x - tgt.x, a.y - tgt.y) <= ARRIVED:
                out.append(f"BUILD {a.id} {tgt.x:.1f} {tgt.y:.1f} {a.size:.1f}")
            else:
                out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {tgt.x:.1f} {tgt.y:.1f}")
            continue
        site = _densify_site(state, config, used_sites + enroute)
        if site is None:
            site = _lattice_site(state, config, used_sites + enroute)
        if site is None:
            break
        if math.hypot(a.x - site[0], a.y - site[1]) <= ARRIVED:
            out.append(f"BUILD {a.id} {site[0]:.1f} {site[1]:.1f} {a.size:.1f}")
        else:
            out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {site[0]:.1f} {site[1]:.1f}")
        used_sites.append(site)

    # 3. growth trains (JIT: only when missions outnumber idle armies).
    want = len([t for t in own_t if t.id != cap_id and t.population < BOOST_BELOW
                 and not any(math.hypot(t.x - ex, t.y - ey) < 5.0 for ex, ey in enroute)])
    if not pioneer_busy and _lattice_site(state, config, used_sites + enroute) is not None:
        want += 1
    if not dense_busy and _densify_site(state, config, used_sites + enroute) is not None:
        want += 1
    short = want - len(idle)
    if short > 0:
        cands = sorted((t for t in own_t if t.id not in mustered and cooled(t)),
                       key=lambda t: t.population, reverse=True)
        for t in cands:
            if short <= 0 or state.should_yield():
                break
            # pioneers/boosts march from the biggest cooled town (bigger army)
            out.append(f"TRAIN {t.id} {_train_size(t, config):.1f}")
            state.note_train(t.id)
            _LAST_TRAIN[t.id] = turn
            short -= 1
    return out
