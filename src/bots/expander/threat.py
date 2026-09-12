"""expander threat — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403
from .intel import _memoized  # noqa: F401

def closing_on(state: "BotState", aid: int, tx: float, ty: float) -> bool:
    """Attack-vector test: foe army aid heads at (tx, ty) (trail heading
    aligns with bearing + range closing). Transiting scouts (passing by,
    not attacking) must not trigger deny-converts — bare-convert needs
    this or close range. No trail (fresh contact) assumes closing."""
    import math as _math
    tr = state._trails.get(aid)
    if not tr or len(tr) < 2:
        return True
    (t0, x0, y0), (t1, x1, y1) = tr[-2], tr[-1]
    dx, dy = x1 - x0, y1 - y0
    if dx * dx + dy * dy < 1e-9:
        return True  # stationary foe at range: assume hostile
    bx, by = tx - x1, ty - y1
    bl = _math.hypot(bx, by)
    if bl < 1e-9:
        return True
    dl = _math.hypot(dx, dy)
    closing = (dx * bx + dy * by) / (dl * bl) > 0.5
    was = _math.hypot(x0 - tx, y0 - ty)
    return closing and bl <= was

def inbound_armies(state: "BotState", config, tid: int) -> list:
    """Fresh foe armies imputed to own town tid (same assignment as
    inbound_force: nearest-own-town, guards excluded). For vector tests."""
    import math as _math
    own_t = state.own_towns()
    tgt = next((t for t in own_t if t.id == tid), None)
    if tgt is None:
        return []
    foe_towns = [t for t in state.world.towns if t.faction != state.faction]
    out = []
    for a in fresh_foe_armies(state):
        guarded = False
        for u in foe_towns:
            if u.faction == a.faction and _math.hypot(a.x - u.x, a.y - u.y) <= 15:
                guarded = True
                break
        if guarded:
            continue
        if min(own_t, key=lambda u: _math.hypot(a.x - u.x, a.y - u.y)).id != tid:
            continue
        out.append(a)
    return out

def staging_eta(state: "BotState", config: "GameConfig") -> dict[int, float]:
    """Per-own-town staging threat ETA from known foe towns.

    A foe town inside striking distance (home LOS) of an own town is raid
    staging, i.e. threat: ETA = dist/army_speed is an upper bound (armies
    may already march, so the true ETA is sooner). Unlike armies, a town
    counts toward EVERY own town in range (it can strike any of them).
    Beyond LOS it is strategic intel, not tactical threat."""
    import math as _math
    faction = state.faction
    los = getattr(config, "line_of_sight", None) or 150.0
    speed = max(1.0, config.army_speed)

    def _compute():
        out: dict[int, float] = {}
        for t in state.own_towns():
            best = float("inf")
            for u in state.world.towns:
                if u.faction == faction:
                    continue
                d = _math.hypot(u.x - t.x, u.y - t.y)
                if d <= los:
                    best = min(best, d / speed)
            if best != float("inf"):
                out[t.id] = best
        return out
    return _memoized(state, ("staging_eta", los, speed), _compute)

def foe_print_factor(state: "BotState", faction: int, grace: int = 20) -> float:
    """Opponent print calibration for W (printable-before-arrival).

    Rate-calibrated (r34 lesson): two prints in 8000 turns is not a
    remuster threat — W must scale by OBSERVED print rate, not mere
    fielding. Sterile-observed factions (towns seen grace+ turns, zero
    prints) count zero. Fresh intel assumes live (dark-spring grace).
    A print per ~200 turns sustains full W; slower drips scale down."""
    first = state._foe_first_seen.get(faction, state.turn)
    if state.turn - first < grace:
        return 1.0
    prints = state._foe_prints.get(faction, 0)
    if prints <= 0:
        return 0.0
    return min(1.0, prints / max(1.0, (state.turn - first) / 200.0))

def buzzer_active(state: "BotState", config) -> bool:
    """Strip-mine flip (Step 6): retaliation time has run out — guards
    are free (no forgone growth) and raids are cheap. Last 10% (min 20
    turns): founding/pipelines die, pop becomes force, everything
    unguarded is taken."""
    max_turns = getattr(config, "max_turns", 3000) or 3000
    return max_turns - state.turn <= max(20, max_turns // 10)

def inbound_force(state: "BotState", config: "GameConfig",
                  max_eta: float = 8.0) -> dict[int, tuple[float, int]]:
    """Per-own-town inbound threat (ETA, force) by nearest-own-town.

    Same assignment as inbound_eta, plus the count: N raiders imputed to
    the town nearest each of them. Stationary foe guards sitting on
    their own towns are excluded (not inbound)."""
    import math as _math
    faction = state.faction
    speed = max(1.0, config.army_speed)

    def _compute():
        own_t = state.own_towns()
        foe_towns = [t for t in state.world.towns if t.faction != faction]
        foes = fresh_foe_armies(state)
        # Guard set once (armies sitting on their own towns), not per pair.
        guarded = set()
        for a in foes:
            for u in foe_towns:
                if u.faction == a.faction and _math.hypot(a.x - u.x, a.y - u.y) <= 15:
                    guarded.add(a.id)
                    break
        out: dict[int, tuple[float, int]] = {}
        # Timeout guard fires only at pathological scale (50000+ pairs ≈
        # 5ms+; normal states never check the clock here, keeping
        # scripted-clock tests exact).
        big = len(own_t) * len(state.world.armies) > 50000
        # Nearest-own-town per foe, computed ONCE (not per town-foe pair:
        # 43 towns x 20 foes x 43 scan = 37k pairs blew the 16ms budget).
        nearest: dict[int, int] = {}
        for a in foes:
            if a.id in guarded:
                continue
            nearest[a.id] = min(own_t, key=lambda u: _math.hypot(a.x - u.x, a.y - u.y)).id
        for i, t in enumerate(own_t):
            if big and i % 16 == 0 and state.should_yield():
                break  # timeout guard: partial map stands (threats known so far)
            best = float("inf")
            n = 0
            for a in foes:
                if nearest.get(a.id) != t.id:
                    continue
                eta = _math.hypot(a.x - t.x, a.y - t.y) / speed
                if eta < best:
                    best = eta
                n += 1
            if best <= max_eta:
                out[t.id] = (best, n)
        return out
    return _memoized(state, ("inbound_force", max_eta, speed), _compute)

def defense_train_ok(population: float, cost: float, floor: float,
                     eta: float, home: int, n: int, window: float = 4.0,
                     turns_left: float = 3000.0) -> bool:
    """Defense-train predicate (shared): train iff the marginal army
    improves the outcome — D == N-1 flips take->save (last-stand: bypass
    the floor, the town falls anyway, convert). D == N flips mutual->clean
    only on short horizons (turns_left <= 500): clean saves a standing
    army (terminal score + options) but spends compounding pop — long
    horizons prefer the cheaper mutual (spend static, keep compounding).
    Otherwise hold: D > N already won, D < N-1 already lost (save armies)."""
    if eta > window or n < 1:
        return False
    if home < n - 1 or home > n:
        return False
    if home == n - 1:
        return population >= cost
    return turns_left <= 500 and population - cost >= floor

def inbound_eta(state: "BotState", config: "GameConfig",
                max_eta: float = 8.0) -> dict[int, float]:
    """Per-own-town inbound threat ETA (nearest-own-town prediction).

    An enemy army counts toward the own town nearest to IT. Stationary
    guards sitting on their own towns are excluded (they are not inbound).
    Spend-signal: armies only. Staging (foe towns) is a POSITIONING signal
    (recall/hold, via staging_eta) — mustering costs 1000 against a town
    that may never produce force, while recall is free insurance.
    Returns {town_id: min_eta} for towns with eta <= max_eta."""
    return {tid: eta for tid, (eta, _) in
            inbound_force(state, config, max_eta).items()}

def note_wave_watch(state: "BotState") -> bool:
    """Second-wave watch: a known own army that vanished (not via noted
    BUILD) died in battle — foes double-train, so hold one home for 6 turns.
    Call once per decide; returns whether the watch is active."""
    cur_ids = {a.id for a in state.own_armies()}
    if state._wave_ids and (state._wave_ids - cur_ids - set(state._pending_builds)):
        state._wave_hold_until = state.turn + 6
    state._wave_ids = set(cur_ids)
    return state.turn <= state._wave_hold_until

def should_hold_home(state: "BotState", config: "GameConfig", army,
                     inbound: dict[int, float], wave_watch: bool) -> bool:
    """Keep >=1 army on a threatened town (inbound seen, or second wave
    expected). Extras march."""
    import math as _math
    home_t = next((t for t in state.own_towns()
                   if _math.hypot(army.x - t.x, army.y - t.y) <= 20), None)
    if home_t is None:
        return False
    if home_t.id not in inbound and not wave_watch:
        return False
    others = sum(1 for a in state.own_armies()
                 if a.id != army.id and _math.hypot(a.x - home_t.x, a.y - home_t.y) <= 20)
    return others == 0

def home_count(state: "BotState", t, radius: float = 20.0) -> int:
    return sum(1 for a in state.own_armies()
               if math.hypot(a.x - t.x, a.y - t.y) <= radius)

def recall_deficit(state: "BotState", config) -> list:
    from .scout import order_move  # noqa: F401 (lazy: breaks import cycle; runtime-safe)
    """Conditional recall (shared Step 3 meeting): threatened towns with
    home D < inbound N recall noted settlers (nearest first, up to the
    deficit). Sufficient garrisons let settlers work (blanket recall
    stalls expansion in contact games). Staging (foe towns in striking
    distance) recalls BLANKET — threat-footing concentrates everything
    (count unknown; beheading risk dominates expansion pause). Scouts
    exempt (intel continuity; muster covers the deficit).
    Viceroys/pending-builds exempt."""
    out: list = []
    recalled: set = set()
    stage = staging_eta(state, config)
    # Fresh staging only (first-seen <= 10 turns): urgent (force may be
    # coming inside intel lag). Stale staging without force is an outpost
    # (blanket-recalling for outposts freezes all expansion forever —
    # area-denial by staging; deficit-loop covers real force).
    fresh_stage = False
    for tid in list(stage):
        if state.turn - state._first_seen.get(("town", tid), state.turn) <= 10:
            fresh_stage = True
            break
    if fresh_stage:
        for a in state.own_armies():
            if not a.is_viceroy and state.army_has_target(a.id) \
                    and not state.has_pending_build(a.id) \
                    and a.id != state._scout_id \
                    and a.id != getattr(state, "_scout_id2", None):
                home = min(state.own_towns(),
                           key=lambda t: math.hypot(a.x - t.x, a.y - t.y),
                           default=None)
                if home is not None:
                    out.extend(order_move(state, config, a, home.x, home.y))
                    recalled.add(a.id)
    force = inbound_force(state, config)
    if not force:
        return out
    for tid, (_, n) in force.items():
        town = state.world.get_town(tid)
        if town is None or town.faction != state.faction:
            continue
        home = home_count(state, town)
        if home <= n - 2:
            continue  # hopeless: settlers lineage, don't feed the grinder
        need = max(0, n - home)
        if need <= 0:
            continue
        cands = sorted((a for a in state.own_armies()
                        if not a.is_viceroy and state.army_has_target(a.id)
                        and not state.has_pending_build(a.id)
                        and a.id != state._scout_id
                        and a.id != getattr(state, "_scout_id2", None)
                        and not committed_raid(state, a.id)
                        and a.id not in recalled),
                       key=lambda a: math.hypot(a.x - town.x, a.y - town.y))
        for a in cands[:need]:
            out.extend(order_move(state, config, a, town.x, town.y))
    return out

def reinforce_orders(state: "BotState", config) -> list:
    from .scout import order_move  # noqa: F401 (lazy: breaks import cycle; runtime-safe)
    """Cross-town reinforcement (shared Step 3 meeting v1): deficit
    towns (D < N) pull nearest surplus to mutual (fill to N), arriving
    in time (march <= ETA-1 — too-late holds, no donation marches).
    Surplus = home + untargeted + unheld (hold-set keeps min(home, N+1)
    + buzzer guards, so surplus never strips a defense). Unthreatened
    towns strip bare (no threat needs no guard)."""
    out: list = []
    force = inbound_force(state, config)
    if not force:
        return out
    speed = max(1.0, config.army_speed)
    held = hold_defenders(state, config, force)
    home_of: dict = {}
    for a in state.own_armies():
        for t in state.own_towns():
            if math.hypot(a.x - t.x, a.y - t.y) <= 20.0:
                home_of[a.id] = t.id
                break
    surplus = [a for a in state.own_armies()
               if a.id in home_of and a.id not in held
               and not state.army_has_target(a.id)]
    deficits: list = []
    for t in state.own_towns():
        eta_n = force.get(t.id)
        if eta_n is None:
            continue
        eta, n = eta_n
        if home_count(state, t) < n:
            deficits.append((eta, n, t))
    for eta, n, t in sorted(deficits, key=lambda e: e[0]):
        need = n - home_count(state, t)
        cands = sorted((a for a in surplus
                        if not state.army_has_target(a.id)),
                       key=lambda a: math.hypot(a.x - t.x, a.y - t.y))
        for a in cands:
            if need <= 0:
                break
            if math.hypot(a.x - t.x, a.y - t.y) / speed <= max(0.0, eta - 1):
                out.extend(order_move(state, config, a, t.x, t.y))
                surplus.remove(a)
                need -= 1
    return out

def evac_plan(state: "BotState", config, hopeless: bool, established_stays: bool = True) -> list:
    """Drain-and-flee (shared Step 5): hopeless capital flies to
    max-separation, mustering everything portable first (drain t, fly
    t+1 via _draining flag; ETA<=1 flies now, no time to drain).
    Established empires endure (brain > hub) unless established_stays
    is False (turtle/expander flee any doom)."""
    out: list = []
    cap = state.world.faction_capital(state.faction)
    if cap is None:
        state._draining = False
        return out
    evacuating = any(a.faction == state.faction and a.is_viceroy
                     for a in state.world.armies)
    if evacuating:
        state._draining = False
        return out
    towns = state.own_towns()
    established = len(towns) >= 3 or max((t.population for t in towns), default=0) >= 20000
    if not hopeless or (established and established_stays):
        state._draining = False
        return out
    if cap.population < 2 * config.army_cost:
        state._draining = False
        return out
    foes = [a for a in state.world.armies if a.faction != state.faction]
    if not foes:
        state._draining = False
        return out
    eta = min(math.hypot(a.x - cap.x, a.y - cap.y) for a in foes) / max(1.0, config.army_speed)
    if eta > 1.0 and not state._draining:
        # Drain turn: strip every town to husk (pop >= cost, no floor —
        # leaving!) into the exodus convoy; fly next turn.
        state._draining = True
        for t in towns:
            if t.population >= config.army_cost \
                    and not (t.id in state._pending_trains
                             and state.turn <= state._pending_trains[t.id]):
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
        return out
    state._draining = False
    fx = sum(a.x for a in foes) / len(foes)
    fy = sum(a.y for a in foes) / len(foes)
    dx, dy = cap.x - fx, cap.y - fy
    dist = math.hypot(dx, dy) or 1.0
    ex = min(980.0, max(20.0, cap.x + dx / dist * 250.0))
    ey = min(980.0, max(20.0, cap.y + dy / dist * 250.0))
    return [f"MOVE_CAPITAL {ex:.1f} {ey:.1f}"]

def stay_behind_hold(state: "BotState", config, p, force, window: float = 4.0) -> bool:
    """Stay-behind vs live threat: the last home guard holds (no offense)
    while inbound sits inside the outcome window. Offense pulled the only
    guard with N=1 at ETA 2.9 (aggressive t1807: home 1->0, bare-convert
    fired, capital suicided). Threat-gated (void S0 unaffected — contact
    stops scouting anyway)."""
    import math as _math
    for t in state.own_towns():
        if _math.hypot(p.x - t.x, p.y - t.y) > 20:
            continue
        e = force.get(t.id)
        if e is not None and e[0] <= window and home_count(state, t) <= 1:
            return True
    return False

def hold_defenders(state: "BotState", config, force: dict) -> set:
    """Hold-set (shared Step 2 core): per threatened town keep
    min(home, N+1) — the +1th is highest-leverage; beyond it extras are
    free. Hopeless towns (D <= N-2) keep none — defenders retreat via
    normal logic instead of annihilating in place. Buzzer adds a blind
    guard (one home per rich town — cheap now, snipers come)."""
    held: set = set()
    for t in state.own_towns():
        if t.id not in force:
            continue
        _, n = force[t.id]
        here = sorted((a for a in state.own_armies()
                       if math.hypot(a.x - t.x, a.y - t.y) <= 20.0),
                      key=lambda a: math.hypot(a.x - t.x, a.y - t.y))
        if len(here) <= n - 2:
            continue  # hopeless: retreat, don't annihilate
        for a in here[:min(len(here), n + 1)]:
            held.add(a.id)
    if buzzer_active(state, config):
        for t in state.own_towns():
            if t.population >= 2 * config.army_cost:
                here = [a for a in state.own_armies()
                        if a.id not in held
                        and math.hypot(a.x - t.x, a.y - t.y) <= 20.0]
                # Spare-only: never park the LAST army (it might be the
                # striker — first-strike dominates at the buzzer (GTO s6)).
                if len(here) >= 2:
                    held.add(min(here, key=lambda a: math.hypot(a.x - t.x, a.y - t.y)).id)
    # Step 4 conquest guard: towns taken within 25 turns (starvation
    # window) keep one veteran (raiders re-take starving conquests free).
    for t in state.own_towns():
        if state.turn - state._taken_at.get(t.id, -1000) <= 25:
            here = [a for a in state.own_armies()
                    if a.id not in held
                    and math.hypot(a.x - t.x, a.y - t.y) <= 20.0]
            if here:
                held.add(min(here, key=lambda a: math.hypot(a.x - t.x, a.y - t.y)).id)
    return held

