"""pro threat — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403

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



def foe_print_factor(state: "BotState", faction: int, grace: int = 20) -> float:
    """Opponent print calibration for W (printable-before-arrival).

    Factions that have fielded force count full; sterile-observed factions
    (towns seen grace+ turns, zero prints) count zero — unready means
    can't print OR won't print. Fresh intel assumes live (dark-spring
    grace: absence of evidence is not evidence yet)."""
    if state._foe_prints.get(faction, 0) > 0:
        return 1.0
    first = state._foe_first_seen.get(faction, state.turn)
    return 1.0 if state.turn - first < grace else 0.0



def buzzer_active(state: "BotState", config) -> bool:
    """Strip-mine flip (Step 6): retaliation time has run out — guards
    are free (no forgone growth) and raids are cheap. Last 10% (min 20
    turns): founding/pipelines die, pop becomes force, everything
    unguarded is taken."""
    max_turns = getattr(config, "max_turns", 3000) or 3000
    return max_turns - state.turn <= max(20, max_turns // 10)



def closing_contacts(state: "BotState", config: "GameConfig",
                     min_speed: float = 15.0) -> int:
    """Foe armies verifiably closing on my towns (early warning).

    Trail velocity toward the nearest own town (>min_speed km/turn).
    Single-point contacts (just entered vision = moving inward by
    construction) count. Stale trails (>20t, gone not closing) don't.
    Stationary/unknown-velocity contacts don't (they're the parked
    loiterers guards already price). Zero new state (trails exist)."""
    import math as _m
    faction = state.faction
    own_t = state.own_towns()
    if not own_t:
        return 0
    speed = max(1.0, config.army_speed)
    n = 0
    for a in state.world.armies:
        if a.faction == faction:
            continue
        trail = (state._trails.get(a.id)
                 if hasattr(state, "_trails") else None) or ()
        if len(trail) < 2:
            n += 1  # new sighting inside vision = closing in
            continue
        (t0, x0, y0), (t1, x1, y1) = trail[-2], trail[-1]
        if state.turn - t1 > 20:
            continue  # stale (gone, not closing)
        dt = t1 - t0
        if dt <= 0:
            continue
        d0 = min(_m.hypot(x0 - u.x, y0 - u.y) for u in own_t)
        d1 = min(_m.hypot(x1 - u.x, y1 - u.y) for u in own_t)
        if (d0 - d1) / dt > min_speed:
            n += 1
    return n


def mustering_staging(state: "BotState", config: "GameConfig") -> int:
    """Foe staging towns (<=150km) with field activity nearby.

    Forces loitering near (15-100km, not garrisoned on) a staging town =
    mustering/pressure. Quiet neighboring colonies (zero armies) don't
    count (the contact-streak over-fire, fixed). Guards-on-town excluded
    (garrison, like inbound_force)."""
    import math as _m
    faction = state.faction
    own_t = state.own_towns()
    if not own_t:
        return 0
    n = 0
    for u in state.world.towns:
        if u.faction == faction:
            continue
        if min(_m.hypot(u.x - t.x, u.y - t.y) for t in own_t) > 150.0:
            continue
        for a in state.world.armies:
            if a.faction != u.faction:
                continue
            d = _m.hypot(a.x - u.x, a.y - u.y)
            if 15.0 < d <= 100.0:
                n += 1
                break
    return n


def siege_active(state: "BotState", config: "GameConfig") -> bool:
    """Bloodbath the bot can't count (intel shows <=1 foe faction) but
    can hear: closing contacts (early warning) or mustering staging.
    Quiet neighbors (close towns, zero armies, nothing closing) stay
    silent; approaching raiders arm. Duel-quiet behavior unchanged."""
    war_foes = ({t.faction for t in state.world.towns if t.faction != state.faction}
                | {a.faction for a in state.world.armies if a.faction != state.faction})
    if len(war_foes) > 1:
        return False  # true multi-foe: existing bloodbath rules own this
    return closing_contacts(state, config) > 0 or mustering_staging(state, config) > 0


def inbound_force(state: "BotState", config: "GameConfig",
                  max_eta: float = 8.0) -> dict[int, tuple[float, int]]:
    """Per-own-town inbound threat (ETA, force) by nearest-own-town.

    Same assignment as inbound_eta, plus the count: N raiders imputed to
    the town nearest each of them. Stationary foe guards sitting on
    their own towns are excluded (not inbound)."""
    import math as _math
    faction = state.faction
    own_t = state.own_towns()
    foe_towns = [t for t in state.world.towns if t.faction != faction]
    out: dict[int, tuple[float, int]] = {}
    for t in own_t:
        best = float("inf")
        n = 0
        for a in state.world.armies:
            if a.faction == faction:
                continue
            if any(_math.hypot(a.x - u.x, a.y - u.y) <= 15
                    for u in foe_towns if u.faction == a.faction):
                continue
            if min(own_t, key=lambda u: _math.hypot(a.x - u.x, a.y - u.y)).id != t.id:
                continue
            eta = _math.hypot(a.x - t.x, a.y - t.y) / max(1.0, config.army_speed)
            if eta < best:
                best = eta
            n += 1
        if best <= max_eta:
            out[t.id] = (best, n)
    return out



def defense_train_ok(population: float, cost: float, floor: float,
                     eta: float, home: int, n: int, window: float = 4.0) -> bool:
    """Defense-train predicate (shared): train iff the marginal army
    improves the outcome — D == N-1 flips take->save (last-stand: bypass
    the floor, the town falls anyway, convert), D == N flips mutual->clean
    (floor applies: don't gut a town to save armies). Otherwise hold:
    D > N is already won, D < N-1 is already lost (save the armies)."""
    if eta > window or n < 1:
        return False
    if home < n - 1 or home > n:
        return False
    if home == n - 1:
        return population >= cost
    return population - cost >= floor



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



