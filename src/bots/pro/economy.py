"""pro economy — split from core.py (mechanical, behavior-identical)."""

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


def towns_by_train_priority(state: "BotState", conservative: bool = False) -> list[Town]:
    cands = [t for t in state.own_towns() if state.can_train_here(t, conservative=conservative)]
    # overcrowded cluster reps first, then by growth asc (most negative), then pop asc
    def key(t: Town):
        over = 0 if state.should_train_for_overcrowding(t) else 1
        return (over, state.get_growth(t.id), t.population)
    cands.sort(key=key)
    return cands


def can_train_standard(state: "BotState", town) -> bool:
    """Comfort gates (pro/greedy shared): 1500-90000, no double-order,
    far towns need proportionally more (messenger+muster depth)."""
    if town.population < 1500 or town.population > 90000:
        return False
    if town.id in state._pending_trains and state.turn <= state._pending_trains[town.id]:
        return False
    cap = state.world.faction_capital(state.faction)
    if cap:
        dist = math.hypot(cap.x - town.x, cap.y - town.y)
        if dist > 100 and town.population < 1500 + int(dist / 150 * 400):
            return False
    return True


def demand_trains(state: "BotState", config, can_train,
                  *, depth_extra: float = 0.0, raid_margin: float = 200.0,
                  payback_mult: float = 1.0, threat_window: float = 4.0,
                  probe_armies: int = 0, void_horizon: int = 500) -> list[str]:
    """Demand-gated trains (shared Step 2 core): threat muster by outcome
    rule, raid pipeline (pack deficit for the priced target), expansion
    pipeline (void merit / contested payback), plus the prober pipeline
    (`probe_armies`: scouting needs an army, armies need demand — the
    first prober breaks the cycle; pairs with S0 scouting, so only bots
    that scout pass >0). One train per town max (engine cap);
    `depth_extra` thickens the muster cushion per personality; trains are
    fungible across demands (deficit shared)."""
    out: list[str] = []
    cost = config.army_cost
    floor = config.death_threshold
    # No strip-mine muster: converting compounding pop to idle armies is
    # self-tax without strikes (empty_3000: -1000 with zero battles).
    # Muster stays demand-gated; the buzzer contributes holds (shared
    # hold-set), arrival caps, and no-settle. Strikes filed (Step 6+).
    force = inbound_force(state, config)
    home = {t.id: home_count(state, t) for t in state.own_towns()}
    sel = raid_target(state, config, margin=raid_margin)
    if sel is not None:
        _, need, _ = sel
        fieldable = sum(1 for a in state.own_armies()
                        if not state.army_has_target(a.id))
        deficit = [max(0, need - fieldable)]
    else:
        deficit = [0]
    expand = expansion_demand(state, config, payback_mult, void_horizon)
    cands = sorted(state.own_towns(),
                   key=lambda t: (0 if state.should_train_for_overcrowding(t) else 1,
                                  state.get_growth(t.id), t.population))
    # No in-loop yield: the trains stage is atomic (anytime prefix
    # property) — trains are cheap, and a partial muster is worse than
    # a late one.
    for t in cands:
        if t.id in state._pending_trains and state.turn <= state._pending_trains[t.id]:
            continue
        eta_n = force.get(t.id)
        want = False
        bare = False
        if eta_n is not None:
            eta, n = eta_n
            if defense_train_ok(t.population, cost, floor + depth_extra, eta,
                                home[t.id], n, window=threat_window):
                want = True
                bare = (home[t.id] == n - 1)  # doomed-town convert branch
        if deficit[0] > 0:
            want = True
        if expand:
            want = True
        # Buzzer strip-mine (free force): towns >=60k have ~zero/negative
        # marginal growth (logistic peak) — mustering to 60k costs nothing
        # (score-neutral now: 1000->1000) and fields take-snowball force
        # for the endgame (900+ turns). Growers (<60k) keep compounding.
        if buzzer_active(state, config) and t.population >= 60000:
            want = True
        if len(state.own_armies()) < probe_armies:
            want = True
        if not want:
            continue
        if bare:
            if t.population >= cost:
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
                deficit[0] = max(0, deficit[0] - 1)
        elif (can_train(state, t)
                and t.population - cost >= floor + depth_extra - 1e-9):
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
    return out


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
                if here:
                    held.add(min(here, key=lambda a: math.hypot(a.x - t.x, a.y - t.y)).id)
    return held

