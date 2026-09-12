"""turtle economy — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403
from .threat import *  # noqa: F401,F403
from .raid import *  # noqa: F401,F403
from .settle import *  # noqa: F401,F403
from .intel import _dark  # noqa: F401
from .raid import _overmatch  # noqa: F401

def towns_by_train_priority(state: "BotState", conservative: bool = False) -> list[Town]:
    cands = [t for t in state.own_towns() if state.can_train_here(t, conservative=conservative)]
    # overcrowded cluster reps first, then by growth asc (most negative), then pop asc
    def key(t: Town):
        over = 0 if state.should_train_for_overcrowding(t) else 1
        return (over, state.get_growth(t.id), t.population)
    cands.sort(key=key)
    return cands

def train_floor(state: "BotState", config) -> float:
    """Cost-aware train floor: cost + death-threshold + half-cost growth
    buffer (a train must leave the town alive AND viable: greedy t1701,
    ~1300 pop, one 1000-train left 322 < 500 threshold — dead. The old
    hardcoded 1500 assumed cost-500)."""
    cost = getattr(config, "army_cost", 500) or 500
    thresh = getattr(config, "death_threshold", 500) or 500
    foe_known = any(t.faction != state.faction for t in state.world.towns) \
        or any(a.faction != state.faction for a in state.world.armies)
    if not foe_known and not state._foe_first_seen:
        return cost + thresh  # true void: regrow is safe, legacy floor
    return cost + thresh + cost / 2.0

def can_train_standard(state: "BotState", town) -> bool:
    """Comfort gates (pro/greedy shared): floor-90000, no double-order,
    far towns need proportionally more (messenger+muster depth)."""
    config = state.config
    floor = train_floor(state, config) if config else 1500
    if town.population < floor or town.population > 90000:
        return False
    if town.id in state._pending_trains and state.turn <= state._pending_trains[town.id]:
        return False
    cap = state.world.faction_capital(state.faction)
    if cap:
        dist = math.hypot(cap.x - town.x, cap.y - town.y)
        if dist > 100 and town.population < floor + int(dist / 150 * 400):
            return False
    return True

def demand_trains(state: "BotState", config, can_train,
                  params: "DemandParams | None" = None) -> list[str]:
    """Demand-gated trains (shared Step 2 core): threat muster by outcome
    rule, raid pipeline (pack deficit for the priced target), expansion
    pipeline (void merit / contested rates+payback), plus the prober
    pipeline (`probe_armies`: scouting needs an army, armies need demand
    — the first prober breaks the cycle; pairs with S0 scouting, so only
    bots that scout pass >0). One train per town max (engine cap);
    trains are fungible across demands (deficit shared)."""
    if params is None:
        params = DemandParams()
    out: list[str] = []
    cost = config.army_cost
    # Print cap (r54 lesson: expander printed 120 for 9 towns, 101 idle).
    # Drowning in idle bodies: threat musters still print (survival),
    # everything else waits (packs/expansion/probes use the pile first).
    idle_free = sum(1 for a in state.own_armies()
                    if not state.army_has_target(a.id))
    drowning = idle_free > 2 * max(1, len(state.own_towns()))
    floor = config.death_threshold
    # Standing guard (deterrence posture, Step 2 remainder): D==0 vs a
    # LONE inbound (N==1) within 12 trains early (visible guards make
    # raids price +1). Hopeless (N>=2) holds (don't donate); outcome-rule
    # owns ETA<=4; this extends to 4<ETA<=12.
    # No strip-mine muster: converting compounding pop to idle armies is
    # self-tax without strikes (empty_3000: -1000 with zero battles).
    # Muster stays demand-gated; the buzzer contributes holds (shared
    # hold-set), arrival caps, and no-settle. Strikes filed (Step 6+).
    force = inbound_force(state, config)
    guard_force = inbound_force(state, config, max_eta=12.0)
    home = {t.id: home_count(state, t) for t in state.own_towns()}
    sel = raid_target(state, config, margin=params.raid_margin)
    if sel is not None:
        _, need, _ = sel
        fieldable = sum(1 for a in state.own_armies()
                        if not state.army_has_target(a.id))
        # Pack cap (pre-siege): beyond-need races decline (don't chase
        # receding needs into treadmills). Empire-scaled (r57 lesson:
        # flat 6 + needs 10-12 = permanent peace, zero captures): big
        # empires field big packs (3 + 2/town); small bots stay capped.
        pack_cap = 3 + 2 * len(state.own_towns())
        deficit = [max(0, min(need, pack_cap) - fieldable)]
    else:
        deficit = [0]
    # Strike deficit (windows close!): pack for blitz/buzzer takes too.
    sk = strike_target(state, config, margin=params.raid_margin)
    if sk is not None:
        _, sk_need = sk
        _fieldable = sum(1 for a in state.own_armies()
                         if not state.army_has_target(a.id))
        deficit[0] = max(deficit[0], min(sk_need, 3 + 2 * len(state.own_towns())) - _fieldable, 0)
    expand = expansion_demand(state, config, params)
    cands = sorted(state.own_towns(),
                   key=lambda t: (0 if state.should_train_for_overcrowding(t) else 1,
                                  state.get_growth(t.id), t.population))
    # No in-loop yield: the trains stage is atomic (anytime prefix
    # property) — trains are cheap, and a partial muster is worse than
    # a late one.
    for i, t in enumerate(cands):
        if i > 0 and i % 8 == 0 and state.should_yield():
            break  # clock discipline: partial trains stand (97-town sprawl
        # otherwise blows the turn budget inside site_pays sigmas)
        if t.id in state._pending_trains and state.turn <= state._pending_trains[t.id]:
            continue
        eta_n = force.get(t.id)
        want = False
        bare = False
        if eta_n is None:
            _g = guard_force.get(t.id)
            if _g is not None and home.get(t.id, 0) == 0 and _g[1] == 1 \
                    and _overmatch(state, 1.5):
                want = True
        if eta_n is not None:
            eta, n = eta_n
            if defense_train_ok(t.population, cost, floor + params.depth_extra, eta,
                                home[t.id], n, window=params.threat_window,
                                turns_left=config.max_turns - state.turn):
                want = True
                bare = (home[t.id] == n - 1)  # doomed-town convert branch
                if bare:
                    # Convert needs a REAL attacker: fresh + (close or
                    # closing-vector). Ghosts and transiting scouts must not
                    # trigger suicide (aggressive t1807: 27-turn phantom).
                    speed = max(1.0, config.army_speed)
                    raiders = inbound_armies(state, config, t.id)
                    bare = any(math.hypot(a.x - t.x, a.y - t.y) / speed <= 2.0
                               or closing_on(state, a.id, t.x, t.y)
                               for a in raiders)
                if bare:
                    # Mutual-save beats deny (greedy t1817: converted a
                    # healthy 1483 capital vs 1 raider 110km out, then the
                    # 483 remainder died under threshold). Convert-deny only
                    # when no guard is printable in time (eta < 1) or the
                    # town can't survive printing one (else print: N-for-N
                    # mutual saves towns worth more than the muster).
                    if eta >= 1.0 and t.population - cost >= config.death_threshold:
                        bare = False
        if deficit[0] > 0:
            want = True
        if expand and not drowning:
            want = True
        if len(state.own_armies()) < params.probe_armies and not drowning:
            want = True
        # Blindness rotation (r41 lesson: 10 prints all game, then 9500t
        # dark peace): when map-blind, fund up to probe+2 (eyes + reserve
        # — one army can't scout-map-raid simultaneously).
        if _dark(state) and len(state.own_armies()) < params.probe_armies + 2 \
                and not drowning:
            want = True
        # Blind eyes (r45 lesson: 3 noted-but-useless armies >= probe+2,
        # yet stone blind — bodies aren't eyes). Dark + scoutless +
        # affordable prints eyes directly, at most 1/300t.
        if _dark(state) and state._scout_id is None \
                and getattr(state, "_scout_id2", None) is None \
                and not state.__dict__.get("_mapper") \
                and state.turn - state.__dict__.get("_last_scout_print", -10 ** 9) >= 300 \
                and can_train(state, t) \
                and t.population - cost >= floor + params.depth_extra - 1e-9:
            want = True
            state.__dict__["_last_scout_print"] = state.turn
        if not want:
            continue
        if bare:
            if t.population >= cost:
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
                deficit[0] = max(0, deficit[0] - 1)
        elif (can_train(state, t)
                and t.population - cost >= floor + params.depth_extra - 1e-9):
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
    return out

