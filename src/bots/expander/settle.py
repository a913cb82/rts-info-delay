"""expander settle — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403
from .intel import _hash  # noqa: F401
from .intel import _memoized  # noqa: F401
from .threat import inbound_force  # noqa: F401

def _site(turn, i, cfg, own_towns, salt=0, rmin=80.0, rmax=250.0, around=None):
    th = cfg.map_size[0] if isinstance(cfg.map_size, (list, tuple)) else 1000
    c = around if around is not None else {"x": th / 2, "y": th / 2}
    max_pop = max((t.get("population", 500) for t in own_towns), default=500)
    need = 0.4 * math.sqrt(max_pop) * 2
    need = max(need, 30.0)
    for k in range(12):
        h = _hash(turn, i, salt + k)
        ang = (h % 360) / 360 * 2 * math.pi
        d = rmin + ((h // 360) % 1000) / 1000 * (rmax - rmin)
        x = c["x"] + d * math.cos(ang)
        y = c["y"] + d * math.sin(ang)
        if x < SITE_MARGIN or y < SITE_MARGIN or x > th - SITE_MARGIN or y > th - SITE_MARGIN:
            continue
        if any(math.hypot(x - t["x"], y - t["y"]) < max(need, cfg.interact_radius) for t in own_towns):
            continue
        return x, y
    return (
        min(th - SITE_MARGIN, max(SITE_MARGIN, c["x"])),
        min(th - SITE_MARGIN, max(SITE_MARGIN, c["y"])),
    )

def respin_tip(state: "BotState", config, tx: float, ty: float):
    """Re-spin a bad scout tip through the sensible-site optimizer
    (near-tip range): the tip region is virgin void (room max, guns
    usually cold) — the optimizer finds the best site NEAR the tip
    instead of founding at the ray-clamped endpoint. Returns a gated
    site or None (then march home)."""
    for salt, rmax in ((77, 250), (78, 250)):
        site = find_build_site(state, config, tx, ty, rmin=180, rmax=rmax,
                               salt=salt, who=int(tx + ty) & 0xFFFF)
        if site is None:
            continue
        if not tip_safe(state, config, site[0], site[1]):
            continue
        if not site_pays(state, config, site[0], site[1]):
            continue
        return site
    return None

def tip_safe(state: "BotState", config, tx: float, ty: float) -> bool:
    """Foe-gate for foundings (both paths: scout-tip + normal settle):
    the site must be guns-cold (no foe towns/armies within strike
    range). Void sites found at ANY distance (first colonies live 600km
    out, safe while nothing is out there — a distance ceiling killed ALL
    expansion: 0 foundings/3000t). Contested tips recycle home instead
    (aggressive's edge colonies died under foe guns, not from distance)."""
    import math as _math
    los = getattr(config, "line_of_sight", None) or 150.0
    for t in state.world.towns:
        if t.faction == state.faction:
            continue
        if _math.hypot(tx - t.x, ty - t.y) < los:
            return False
    for a in state.world.armies:
        if a.faction == state.faction:
            continue
        if _math.hypot(tx - a.x, ty - a.y) < los:
            return False
    # Room: ray tips clamp at the map edge (all four settlers founded
    # at x/y = 20/980) — edge tips re-spin, interior tips found.
    th = 1000.0
    try:
        ms = config.map_size
        th = ms[0] if isinstance(ms, (list, tuple)) else float(ms)
    except Exception:
        pass
    if min(tx, th - tx, ty, th - ty) < 100.0:
        return False
    # Own-spacing floor (GTO pairs): tips bypassed the 65km floor and
    # stacked at 38km (pro east cluster) — same rule, both paths.
    for t in state.world.towns:
        if t.faction == state.faction:
            if _math.hypot(tx - t.x, ty - t.y) < 65.0:
                return False
    return True

_build_site_cache: dict = {}


def find_build_site(state, config: GameConfig, ref_x: float, ref_y: float, rmin: float = 80, rmax: float = 300, salt: int = 0, who: int = 0) -> tuple[float, float] | None:
    """Deterministic site spin, stable per army: `who` (army/town id) —
    never the turn — seeds the hash, so re-queries across turns return
    the same site and headings hold through note-drops and waits.
    Different armies spread via id + position."""
    key = (state.turn, int(ref_x), int(ref_y), rmin, rmax, salt, who, state.faction)
    if key in _build_site_cache:
        return _build_site_cache[key]
    th = config.map_size[0] if isinstance(config.map_size, (list, tuple)) else 1000
    cands: list[tuple[float, float, float, float]] = []
    # pre-filter towns near ref for faster crowding (only within rmax+150)
    nearby_towns = [t for t in state.world.towns if math.hypot(t.x - ref_x, t.y - ref_y) < rmax + 200]
    if not nearby_towns:
        nearby_towns = state.world.towns[:50]  # fallback small sample
    _big_site = len(nearby_towns) > 300
    for k in range(16):
        if _big_site and k % 4 == 0 and state.should_yield():
            break  # timeout guard: return best-so-far (healthy budgets never trip)
        h = _hash(who, int(ref_x * 7 + ref_y * 13) & 0xFFFF, salt + k)
        ang = (h % 3600) / 3600 * 2 * math.pi
        d = rmin + ((h // 3600) % 1000) / 1000 * (rmax - rmin)
        x = ref_x + d * math.cos(ang)
        y = ref_y + d * math.sin(ang)
        x = max(SITE_MARGIN, min(th - SITE_MARGIN, x))
        y = max(SITE_MARGIN, min(th - SITE_MARGIN, y))
        min_dist = 999.0
        for t in nearby_towns:
            md = math.hypot(x - t.x, y - t.y)
            if md < min_dist:
                min_dist = md
                if min_dist < config.interact_radius + 10:
                    break
        if min_dist < config.interact_radius + 10:
            continue
        # Sensible placement (empty_10000 lesson: max-min_dist picked
        # rmax, ratcheted to the map edge, clamped and stacked there).
        # Floor: no founding within 65km of an own town (GTO pairs —
        # fratricide). NO hard ceiling: void expansion must reach far
        # (first colonies live 600km out, safe while guns-cold) — distance
        # is a soft preference (nearest support wins ties) and foe
        # proximity gates at arrival (tip_supported there is foe-gated).
        # Headless bots (no own towns) keep farthest-escape behavior.
        own = [t for t in state.world.towns if t.faction == state.faction]
        d_own = min((math.hypot(x - t.x, y - t.y) for t in own), default=0.0)
        if own and d_own < 65.0:
            continue
        crowding = 0.0
        guns = 0.0
        for t in nearby_towns:
            dist = math.hypot(x - t.x, y - t.y)
            if 1 < dist < 150:
                d_eq = 0.1 * math.sqrt(max(0.0, min(t.population, 500)))
                crowding += (d_eq / dist) ** 0.8
        # GTO placement: don't found under foe guns (pro t4655 colony
        # died in 5 turns — founded in greedy's face). Penalty ∝ foe
        # towns + armies within strike range (LOS), same shape as
        # crowding so the two trade off in one currency. Foe-shadow
        # (doctrine: settle AWAY from believed enemies): known foe towns
        # repel out to 300km (beyond-LOS shadow — direction matters even
        # when guns can't reach yet).
        los = getattr(config, "line_of_sight", None) or 150.0
        for t in state.world.towns:
            if t.faction == state.faction:
                continue
            dist = math.hypot(x - t.x, y - t.y)
            if 1 < dist < los:
                d_eq = 0.1 * math.sqrt(max(0.0, min(t.population, 500)))
                guns += (d_eq / dist) ** 0.8
            elif los <= dist < 300.0:
                guns += 0.5 * (300.0 - dist) / 300.0
        for a in state.world.armies:
            if a.faction == state.faction:
                continue
            dist = math.hypot(x - a.x, y - a.y)
            if 1 < dist < los:
                guns += (0.5 / dist) ** 0.8
        # Growth room (option value): interior sites keep 360° of future
        # slots, edge sites halve them. Penalize the edge deficit (150km
        # room ideal) in crowding currency.
        edge = min(x, th - x, y, th - y)
        room = max(0.0, (150.0 - edge) / 150.0)
        # Near-support (doctrine: not too far — quickly noticed and
        # defended. GTO crowding strategy: settle as close to existing
        # towns as the 65km floor allows — closer = cheaper march +
        # reinforcement; the floor + crowding price the packing, distance
        # beyond 150km pays a STEEP support penalty (far colonies die
        # unsupported). More smaller towns compound faster, but each pays
        # full sunk (army_cost) and needs its own 65km+ of land.
        far = max(0.0, (d_own - 150.0) / 75.0) if own else 0.0
        cands.append((x, y, min_dist, crowding + guns + room + far, d_own))
        # No early break: the first spins are not the best (room-passing
        # spins hide late in the sequence — collect all 16, sort picks).
    if not cands:
        _build_site_cache[key] = None
        # prune cache
        if len(_build_site_cache) > 2000:
            _build_site_cache.clear()
        return None
    if own:
        # GTO order: lowest total cost (crowding + guns + edge-room),
        # then nearest support, then nearest the capital hub (short
        # reinforcement chains beat deep ones).
        cap = state.world.faction_capital(state.faction)
        cx, cy = (cap.x, cap.y) if cap else (th / 2, th / 2)
        cands.sort(key=lambda c: (c[3], c[4], math.hypot(c[0] - cx, c[1] - cy)))
    else:
        cands.sort(key=lambda c: (-c[2], c[3]))  # headless escape: farthest
    res = (cands[0][0], cands[0][1])
    _build_site_cache[key] = res
    if len(_build_site_cache) > 2000:
        _build_site_cache.clear()
    return res

def void_note_busy(state: "BotState") -> bool:
    """A settler expansion is already in flight (a note to nowhere-
    known). Scout hop notes don't count (the scout's own hops must not
    block the settler pipeline — recycle lesson) — but ignoring ALL void
    notes floods void trains (endgame lesson: unbounded settlers)."""
    towns = list(state.world.towns)
    for a in state.own_armies():
        if a.id == state._scout_id or a.id == getattr(state, "_scout_id2", None):
            continue
        tgt = state.army_target(a.id)
        if tgt and all(math.hypot(tgt[0] - t.x, tgt[1] - t.y) > 20
                       for t in towns):
            return True
    return False

def _void_horizon(state: "BotState", config, explicit: int | None) -> int:
    """Marginal colony horizon: 500 turns to repay (-500 + ~1/turn),
    capped by game length (no foundings in the last 50 turns — buzzer).
    Explicit overrides (expander sprints 100, S0-fallback 0 capability)."""
    if explicit is not None:
        return explicit
    max_turns = getattr(config, "max_turns", 3000) or 3000
    return min(500, max_turns - 50)

def expansion_demand(state: "BotState", config,
                     params: "DemandParams | None" = None,
                     *, payback_mult: float | None = None,
                     void_horizon: int | None = None) -> bool:
    """Settler pipeline demand. Void (no known foes): colonies ARE the
    void economy (no serialization — a scout's hop note must not block
    the pipeline), but a marginal colony still needs ~500 turns to repay
    (-500 + ~1/turn): settle-branch passes void_horizon=500, S0-fallback
    keeps 0 (capability contract: probe-then-found is recycle's goal).
    Contested: expand iff the colony stream beats the home marginal
    stream (rate comparison on TRUE spend-aware growth — a fresh small
    colony grows ~1.2/turn uncrowded (doctrine: lots of small = great
    growth) vs a crowded home at ~0.3) with horizon to amortize
    (payback_mult scales patience) and one in flight at a time (serial;
    sprawl personalities parallelize). Darkness shields growers; the
    buzzer falls out."""
    if params is None:
        params = DemandParams()
    mult = params.payback_mult if payback_mult is None else payback_mult
    _exp = void_horizon if void_horizon is not None else params.void_horizon
    vhor = _void_horizon(state, config, _exp)
    chor = min(mult * 500, (getattr(config, "max_turns", 3000) or 3000) - 50)
    foe_known = any(t.faction != state.faction for t in state.world.towns) \
        or any(a.faction != state.faction for a in state.world.armies)
    if not foe_known:
        # True void (never seen) expands; eviction-void (seen, stale) is
        # NOT peace (empty t2780: stale intel must not read as void).
        if state._foe_first_seen:
            pass  # fall through to contested caution below
        else:
            return config.max_turns - state.turn >= vhor
    # War-print (fortress-phase): threatened with horizon prints towns
    # for capacity (military, bypasses veto downstream).
    if war_print_need(state, config):
        return True
    if params.serial and void_note_busy(state):
        return False
    turns_left = config.max_turns - state.turn
    if turns_left < chor:
        return False
    if not params.rates:
        return True  # sprawl overrides marginal math (documented)
    # Land grab (r48 lesson: foundings stop t2000+, small towns never
    # expand — rate-arbitrage blocks them forever since an uncrowded
    # home grows ~1-2/turn vs a colony's 0.75). Below 20k, expansion is
    # throughput (parallel compounding), not arbitrage: afford +
    # horizon suffices (serial + site_pays still filter downstream).
    total_pop = sum(t.population for t in state.own_towns())
    if total_pop < 20000:
        return True
    # Median home (r61 lesson: max-growth vetoes everything — one fast
    # uncrowded home blocks colonies forever; a crowded median justifies).
    rates = sorted((state.get_growth(t.id) or 3.0) for t in state.own_towns())
    home_rate = rates[len(rates) // 2] if rates else 3.0
    return 1.2 > home_rate

def _crowd_sigma(state: "BotState", config, x: float, y: float, p: float,
                 extra: tuple | None = None) -> float:
    """Engine crowding sigma at (x,y) for pop p (extra = optional new
    neighbor (ex, ey, epop) included). Transcribed from crowding_net."""
    import math as _math
    eq = getattr(config, "equilibrium_spacing", 0.1) or 0.1
    decay = getattr(config, "crowding_decay", 0.8) or 0.8
    asym_k = getattr(config, "crowding_asymmetry", 0.01) or 0.01
    crange = getattr(config, "info_speed", 150.0) or 150.0
    # Per-turn coord table: world is static during decide, so normalize
    # once (no per-call list-copy, no per-town isinstance — 780 calls x
    # 97 towns was 75k isinstance checks alone). extra appended per call.
    base = _memoized(state, ("town_coords",),
                     lambda: [(t.x, t.y, t.population) for t in state.world.towns])
    towns = base if extra is None else base + [extra]
    # Range prefilter: terms beyond crange contribute exactly 0 (the loop
    # `continue`s them) — skip with a bounding box first. At 97-town
    # sprawl this is ~20x (780 calls x 97 scans blew the turn budget).
    tot = 0.0
    for tx, ty, pn in towns:
        if abs(tx - x) > crange or abs(ty - y) > crange:
            continue
        d = _math.hypot(tx - x, ty - y)
        if d < 1e-9 or d > crange + 1e-9:
            continue
        pn = max(1.0, pn)
        tot += (1.0 + asym_k * _math.log(pn / max(1.0, p))) * \
            ((eq * _math.sqrt(min(pn, p)) / d) ** decay)
    return tot

def site_pays(state: "BotState", config, x: float, y: float) -> bool:
    """Founding veto (fratricide): NET empire growth with the colony
    minus without must clear amortized founding cost (500/turns_left +
    margin). Counts both the colony's stream AND the crowding it deals
    home (externality!) — a colony that stunts home more than it earns
    is vetoed even when its own growth looks fine. Unknown/void sites
    (no intel to tax them) allow. Military staging bypasses (position).
    Empty_3000 lesson: full-map foundings fratricide (-4346)."""
    import math as _math
    cap = getattr(config, "population_cap", 100000.0) or 100000.0
    growth = getattr(config, "population_growth", 0.001) or 0.001
    max_turns = getattr(config, "max_turns", 3000) or 3000
    towns = [t for t in state.own_towns()]
    if not towns:
        return True
    new = (x, y, 500.0)
    net = 0.0
    for t in towns:
        base = growth * t.population * (1.0 - t.population / cap)
        # s0 is site-invariant (world static during decide): memoize per
        # turn (97-town sprawl recomputed it per site — half the sigmas).
        s0 = _memoized(state, ("crowd_s0", t.id),
                       lambda t=t: _crowd_sigma(state, config, t.x, t.y, t.population))
        s1 = _crowd_sigma(state, config, t.x, t.y, t.population, extra=new)
        net += base * (1.0 - s1) - base * (1.0 - s0)
    s_new = _crowd_sigma(state, config, x, y, 500.0)
    # Colony stream PROJECTED (compounding!): a static 500-pop stream
    # (~0.5/turn) never repays 1000 sunk, vetoing everything — but the
    # colony grows (500 -> 1300+ over 1600 turns). Linearized average pop
    # over horizon (capped), home externality stays static (conservative).
    horizon = max(1, max_turns - state.turn)
    avg_pop = min(cap * 0.5, 500.0 * (1.0 + growth * horizon))
    net += growth * avg_pop * (1.0 - avg_pop / cap) * (1.0 - s_new)
    # Sunk = full settler price (army_cost to print; the 500-pop town is
    # what's gained, counted in net above — not the cost). Cost-aware
    # (was hardcoded 500, half the true 1000 price: over-founded).
    cost = getattr(config, "army_cost", 500) or 500
    amort = cost / max(1, max_turns - state.turn) + 0.1
    return net > amort

def war_print_need(state: "BotState", config) -> bool:
    """Fortress-phase print-towns (Step 2 remainder): MULTI-raider
    pressure (max inbound N >= 2 — a lone probe is mustered, not
    out-printed) with horizon to amortize (>=500) — print capacity,
    not pop. Bypasses the site veto (military value); rear-area safety
    comes from max-min-dist siting (far from towns incl. foes)."""
    force = inbound_force(state, config)
    if not force or max(n for _, n in force.values()) < 2:
        return False
    return (getattr(config, "max_turns", 3000) or 3000) - state.turn >= 500

