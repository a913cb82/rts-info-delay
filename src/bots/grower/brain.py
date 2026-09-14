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
_FOE_MAX: dict[int, float] = {}
_PACK_TOWN: int | None = None  # town currently training the raid pack
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


def _densify_list(state, config) -> list[tuple[float, float]]:
    """All 4km-ring points around <=MAX towns, sorted (pop, dist), cached
    by town signature (per-army rescans killed the clock on contact)."""
    own = state.own_towns()
    key = ("dense", tuple(sorted((t.id, round(t.x, 1), round(t.y, 1)) for t in own)))
    hit = _SITE_CACHE.get(key)
    if hit is not None:
        return hit
    mw, mh = config.map_size if getattr(config, "map_size", None) else (1000, 1000)
    small = [t for t in own if t.population <= DENSE_MAX_POP]
    cands = []
    for t in small:
        for ring_r in (DENSE_DIST, DENSE_DIST * 2):
            for k in range(6):
                ang = k * math.pi / 3
                x, y = t.x + ring_r * math.cos(ang), t.y + ring_r * math.sin(ang)
                if x < 5 or x > mw - 5 or y < 5 or y > mh - 5:
                    continue
                if any(math.hypot(x - u.x, y - u.y) < DENSE_DIST for u in own):
                    continue
                cands.append((t.population, math.hypot(x - t.x, y - t.y), (x, y)))
    cands.sort(key=lambda c: (c[0], c[1]))
    out = [c[2] for c in cands]
    _SITE_CACHE[key] = out
    if len(_SITE_CACHE) > 8:
        _SITE_CACHE.pop(next(iter(_SITE_CACHE)))
    return out


def _densify_site(state, config, exclude=None) -> tuple[float, float] | None:
    """Nearest 4km-ring point around a <=300 town (mild-gradient infill)."""
    excl = list(exclude) if exclude else []
    for site in _densify_list(state, config):
        if any(math.hypot(site[0] - ex, site[1] - ey) < DENSE_DIST for ex, ey in excl):
            continue
        return site
    return None


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    global _PACK_TOWN
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
    # RAID STAGE (v3raid): intel-gated min-size raids (T4 prize>=200,
    # muster-aware need, affordable-lock). v3 peace + predator steal.
    _pool = sum(a.size for a in idle)
    # BLITZ-1 (demolition): 3 simultaneous colony-hits. Colonies (100-300)
    # defend alone (1 train/town/turn); mothers muster but can't cover them.
    _raids: list = []
    # EATER-1: stagnants (<=2 towns at t2000+) get full-invaded (mothers too:
    # no muster vs weak). Peers keep colony-only blitz rules.
    _town_counts: dict = {}
    for t in state.world.towns:
        if t.faction != state.faction and t.faction is not None:
            _town_counts[t.faction] = _town_counts.get(t.faction, 0) + 1
    _stagnant_factions = {f for f, n in _town_counts.items() if n <= 2} if turn >= 2000 else set()
    _foe_towns = [t for t in state.world.towns
                  if t.faction != state.faction and t.faction is not None
                  and ((100.0 <= t.population <= 300.0)
                       or (t.faction in _stagnant_factions and t.population >= 100.0))]
    if _foe_towns and not state.should_yield():
        _spd = max(1.0, getattr(config, "army_speed", 50.0) or 50.0)
        _home = own_t[0] if own_t else None
        _cands = []
        for _u in _foe_towns:
            _d = min([math.hypot(a.x - _u.x, a.y - _u.y) for a in idle] or [1e9])
            if _home is not None:
                _d = min(_d, math.hypot(_home.x - _u.x, _home.y - _u.y))
            _garr = sum(a.size for a in state.world.armies
                        if a.faction == _u.faction
                        and math.hypot(a.x - _u.x, a.y - _u.y) <= 20.0)
            _need = _garr + 30.0  # colonies: flat margin, no muster-track
            _prize = _u.population * 0.5
            if _prize < 50.0:
                continue
            _biggest = max([t.population * (getattr(config, "max_train_frac", 0.1) or 0.1) for t in own_t] or [0])
            if _need > _pool + 8 * max(30.0, _biggest):
                continue
            _cands.append((_prize - _need * 1.5 - _d * 0.1, _u, _need))
        _cands.sort(key=lambda c: -c[0])
        _seen_towns: set = set()
        for _sc, _u, _nd in _cands:
            if _u.id in _seen_towns:
                continue
            _seen_towns.add(_u.id)
            _raids.append((_u, _nd))
            if len(_raids) >= 3:
                break
    if not _raids:
        _PACK_TOWN = None  # no locks: stale pack-tag must not hold pioneers
    _raid = _raids[0] if _raids else None  # compat for assembly/want below
    # packs march FIRST (before pioneers spend the pool)
    _raid_hold = False
    if _raids and not state.should_yield() and idle:
        for _rt, _rn in list(_raids):
            _sent = any((tgt := state.army_target(a.id)) is not None
                        and math.hypot(tgt[0] - _rt.x, tgt[1] - _rt.y) <= 10.0
                        for a in state.own_armies())
            if _sent:
                continue
            _pack = max(idle, key=lambda a: a.size)
            if _pack.size >= _rn:
                out.append(f"MOVE_TO {_pack.id} {_pack.x:.1f} {_pack.y:.1f} {_rt.x:.1f} {_rt.y:.1f}")
                idle = [a for a in idle if a.id != _pack.id]
                _pool = sum(a.size for a in idle)
            else:
                _raid_hold = (_PACK_TOWN is not None
                              and _PACK_TOWN in state._pending_trains)
    used_sites: list[tuple[float, float]] = []
    for a in sorted(idle, key=lambda x: x.id):
        if state.should_yield():
            break
        if _raid_hold:
            continue  # assembling raid: pioneers pause (boosts above still run)
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

    # 2b. rich-town assembly (v4: 500+ towns feed packs (mothers stall
    # ~570; 700-gate never fires -- traced). 10%-trains form packs;
    # cooled() keeps floors so growth is never taxed. Bounded: pack only.
    _unmet = [(_u, _nd) for _u, _nd in _raids if _nd > _pool / max(1, len(_raids))]
    if _unmet and not state.should_yield():
        _rt, _rn = max(_unmet, key=lambda z: z[1])
        # PREEMPT: no pending-guard (growth occupies mothers 24/7; assembly
        # runs first in out-list so it wins the engine's standing-order dedup;
        # growth-cands below excludes _PACK_TOWN so nothing doubles).
        _rich = sorted((t for t in own_t if t.population >= 500.0 and t.id not in mustered),
                       key=lambda t: t.population, reverse=True)
        if _rich:
            out.append(f"TRAIN {_rich[0].id} {_train_size(_rich[0], config):.1f}")
            state.note_train(_rich[0].id)
            _LAST_TRAIN[_rich[0].id] = turn
            _PACK_TOWN = _rich[0].id
    # 2d. SCOUT-FAN (fan-1): t100, 4x5-size diagonals, 300km. Below MIN_ARMY
    # (unclaimable); hold on arrival; reports ride mail. Survival lottery.
    if turn >= 100 and turn < 110 and not state.should_yield():
        _cap = state.world.faction_capital(state.faction)
        if _cap is not None:
            mw, mh = config.map_size if getattr(config, "map_size", None) else (1000, 1000)
            _sent = sum(1 for a in state.own_armies()
                        if a.size <= 8.0 and state.army_has_target(a.id))
            if _sent < 4 and _cap.population >= 400.0:
                _dirs = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
                _di = _sent % 4
                _dx, _dy = _dirs[_di]
                # PREEMPT (pending-guard starves: capital trains 24/7; fan
                # order runs before growth-trains so it wins dedup).
                if _sent < 4:
                    out.append(f"TRAIN {_cap.id} 5.0")
                    state.note_train(_cap.id)
                # march the smallest untargeted to the fan point
                _cands = sorted((a for a in idle if a.size <= 8.0 and not state.army_has_target(a.id)),
                                key=lambda a: a.size)
                if _cands:
                    _sc = _cands[0]
                    _fx = min(max(_cap.x + _dx * 300.0, 5.0), mw - 5)
                    _fy = min(max(_cap.y + _dy * 300.0, 5.0), mh - 5)
                    out.append(f"MOVE_TO {_sc.id} {_sc.x:.1f} {_sc.y:.1f} {_fx:.1f} {_fy:.1f}")
                    idle = [a for a in idle if a.id != _sc.id]
    # 3. growth trains (JIT: only when missions outnumber idle armies).
    want = len([t for t in own_t if t.id != cap_id and t.population < BOOST_BELOW
                 and not any(math.hypot(t.x - ex, t.y - ey) < 5.0 for ex, ey in enroute)])
    if not pioneer_busy and _lattice_site(state, config, used_sites + enroute) is not None:
        want += 1
    if not dense_busy and _densify_site(state, config, used_sites + enroute) is not None:
        want += 1
    short = want - len(idle)
    if short > 0:
        cands = sorted((t for t in own_t if t.id not in mustered and cooled(t)
                        and t.id != _PACK_TOWN),  # RESERVE: pack-town feeds packs, not pioneers
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
