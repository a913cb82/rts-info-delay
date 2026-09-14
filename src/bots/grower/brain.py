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
_FOUNDED_SITES: list = []  # (x, y, turn) of our founding-BUILDs (boost-timing)
_FOE_MAX: dict[int, float] = {}
_PACK_TOWN: int | None = None  # town currently training the raid pack
_RANK_MODE = 0  # 0=race, 3=siege, 4=feast (meta composition-modes)
_RANK_AT = -10 ** 9
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
    # META-1 composition reader (field archetypes; hysteresis via _RANK_AT).
    # raiders: foe armies with targets (marching!); growers: foe towns>4 any;
    # stagnants: foe factions at <=2 towns (post-t2000).
    global _RANK_MODE, _RANK_AT
    _raiders_inbound = any(state.army_has_target(a.id) for a in foe_armies)
    _foe_town_counts: dict = {}
    for t in state.world.towns:
        if t.faction != state.faction and t.faction is not None:
            _foe_town_counts[t.faction] = _foe_town_counts.get(t.faction, 0) + 1
    _any_grower = any(n > 4 for n in _foe_town_counts.values())
    _any_stagnant = any(n <= 2 for n in _foe_town_counts.values()) and turn >= 2000
    if turn - _RANK_AT >= 500:
        _RANK_AT = turn
        if _raiders_inbound:
            _RANK_MODE = 3  # siege: full-muster+turtle (deny snowball)
        elif _any_stagnant:
            _RANK_MODE = 4  # feast: eater-invade (free captures)
        else:
            _RANK_MODE = 0  # race: compound-max (zero raid-tax)
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
    # BOOST-TIMING: in-window (200-1500t) colonies only; newborns solo-fast,
    # ancients are feeders. Unknown-age boosts (safe default).
    needy = [t for t in sorted(
        (t for t in own_t if t.id != cap_id and t.population < BOOST_BELOW
         and 200.0 <= _town_age(t) <= 1500.0),
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
    _raid = None
    _stag = {f for f, n in _foe_town_counts.items() if n <= 2} if _RANK_MODE == 4 else set()
    _foe_towns = [t for t in state.world.towns
                  if t.faction != state.faction and t.faction is not None
                  and (t.population >= 400
                       or (t.faction in _stag and t.population >= 100.0))]
    if _RANK_MODE == 3:
        _foe_towns = []  # siege: no raids (turtle denies snowball)
    if _foe_towns and not state.should_yield():
        _spd = max(1.0, getattr(config, "army_speed", 50.0) or 50.0)
        _home = own_t[0] if own_t else None
        _best = None
        for _u in _foe_towns:
            _d = min([math.hypot(a.x - _u.x, a.y - _u.y) for a in idle] or [1e9])
            if _home is not None:
                _d = min(_d, math.hypot(_home.x - _u.x, _home.y - _u.y))
            _march_t = _d / _spd + 2.0
            _garr = sum(a.size for a in state.world.armies
                        if a.faction == _u.faction
                        and math.hypot(a.x - _u.x, a.y - _u.y) <= 20.0)
            _FOE_MAX[_u.id] = max(_FOE_MAX.get(_u.id, 0.0), _u.population)
            _mustering = _u.population < _FOE_MAX[_u.id] - 30.0
            _need = _garr + (_u.population * 0.15 * _march_t if _mustering else 15.0) + 30.0
            _prize = _u.population * 0.5
            if _prize < 200:
                continue
            _biggest = max([t.population * (getattr(config, "max_train_frac", 0.1) or 0.1) for t in own_t] or [0])
            if _need > _pool + 8 * max(30.0, _biggest):
                continue
            _score = _prize - _need * 1.5 - _d * 0.1
            if _best is None or _score > _best[0]:
                _best = (_score, _u, _need)
        if _best is not None:
            _raid = (_best[1], _best[2])
        else:
            _PACK_TOWN = None  # no lock: stale pack-tag must not hold pioneers
    # raid marches FIRST (pack before pioneers spend it)
    _raid_hold = False
    if _raid is not None and not state.should_yield() and idle:
        _rt, _rn = _raid
        _pack = max(idle, key=lambda a: a.size)
        if _pack.size >= _rn:
            out.append(f"MOVE_TO {_pack.id} {_pack.x:.1f} {_pack.y:.1f} {_rt.x:.1f} {_rt.y:.1f}")
            idle = [a for a in idle if a.id != _pack.id]
            _pool = sum(a.size for a in idle)
            _PACK_TOWN = None
        else:
            # v4: hold ONLY while OUR pack-train is in flight (purpose-tagged;
            # growth-trains must never hold pioneers -- that was the 700-stall).
            _raid_hold = (_PACK_TOWN is not None
                          and _PACK_TOWN in state._pending_trains)
    global _FOUNDED_SITES
    used_sites: list[tuple[float, float]] = []
    def _town_age(t) -> float:
        _best = None
        for _sx, _sy, _st in _FOUNDED_SITES:
            if math.hypot(t.x - _sx, t.y - _sy) <= 10.0:
                _age = turn - _st
                if _best is None or _age < _best:
                    _best = _age
        return _best if _best is not None else 10 ** 9  # unknown: boost (safe)
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
            _FOUNDED_SITES.append((site[0], site[1], turn))
        else:
            out.append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {site[0]:.1f} {site[1]:.1f}")
        used_sites.append(site)

    # 2b. rich-town assembly (v4: 500+ towns feed packs (mothers stall
    # ~570; 700-gate never fires -- traced). 10%-trains form packs;
    # cooled() keeps floors so growth is never taxed. Bounded: pack only.
    if _raid is not None and _pool < _raid[1] and not state.should_yield():
        _rt, _rn = _raid
        _rich = sorted((t for t in own_t if t.population >= 500.0 and t.id not in mustered
                        and t.id not in state._pending_trains),
                       key=lambda t: t.population, reverse=True)
        if _rich:
            out.append(f"TRAIN {_rich[0].id} {_train_size(_rich[0], config):.1f}")
            state.note_train(_rich[0].id)
            _LAST_TRAIN[_rich[0].id] = turn
            _PACK_TOWN = _rich[0].id
    # 2c. PRE-SEND (order-latency exploit, see docs/bot/PRESEND.md): busy
    # pioneers within (msg_eta+1) march-turns of their site get their BUILD
    # now, so the messenger lands with them (saves observe+roundtrip ~2t/leg).
    # Dropped sends are free (army not yet landed; retry next turn).
    if not state.should_yield():
        _cap = state.world.faction_capital(state.faction)
        if _cap is not None:
            _spd = max(1.0, getattr(config, "army_speed", 50.0) or 50.0)
            _idle_ids = {x.id for x in idle}
            for a in state.own_armies():
                if state.should_yield():
                    break
                if a.is_viceroy or a.id in _idle_ids:
                    continue
                tgt = state.army_target(a.id)
                if tgt is None:
                    continue
                # intended site: a planned found/boost point near the target
                _site = None
                for _cand in list(needy) + used_sites:
                    _cx, _cy = (_cand.x, _cand.y) if hasattr(_cand, "x") else (_cand[0], _cand[1])
                    if math.hypot(tgt[0] - _cx, tgt[1] - _cy) <= 10.0:
                        _site = (_cx, _cy)
                        break
                if _site is None:
                    continue
                _army_eta = math.hypot(a.x - _site[0], a.y - _site[1]) / _spd
                _msg_eta = math.hypot(_cap.x - a.x, _cap.y - a.y) / 150.0
                if _army_eta <= _msg_eta + 1.0:
                    out.append(f"BUILD {a.id} {_site[0]:.1f} {_site[1]:.1f} {a.size:.1f}")
    # 3. growth trains (JIT: only when missions outnumber idle armies).
    want = len([t for t in own_t if t.id != cap_id and t.population < BOOST_BELOW
                 and 200.0 <= _town_age(t) <= 1500.0
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
