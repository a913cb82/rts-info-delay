"""Search candidates + rank (M2): settle-site choice via rollout value.

The doctrine proposes (default site + top alternates); rank() picks by
100-turn rollout score with a margin rule (static-foe bias S3 + model
noise must not flip near-ties). Clock-gated (effort full only).
"""

from __future__ import annotations
import math

from .stepper import make_state, prune, rollout, score

MARGIN = 0.02
HORIZON = 100


def to_cfg(config) -> dict:
    return {"army_speed": config.army_speed, "interact_radius": config.interact_radius,
            "population_growth": config.population_growth, "population_cap": config.population_cap,
            "death_threshold": config.death_threshold, "army_cost": config.army_cost,
            "build_efficiency": config.build_efficiency}


def world_snapshot(state) -> tuple:
    """BotState.world (intel!) -> (town dicts, army dicts) for make_state."""
    towns = [{"id": t.id, "x": t.x, "y": t.y, "faction": t.faction,
              "population": t.population, "is_capital": t.is_capital}
             for t in state.world.towns]
    armies = []
    for a in state.own_armies():
        d = {"id": a.id, "x": a.x, "y": a.y, "faction": a.faction}
        tgt = state.army_target(a.id)
        if tgt is not None:
            d["target_x"], d["target_y"], d["has_target"] = tgt[0], tgt[1], True
        armies.append(d)
    for a in state.world.armies:
        if a.faction == state.faction:
            continue
        armies.append({"id": a.id, "x": a.x, "y": a.y, "faction": a.faction})
    return towns, armies


def site_plans(state, config, settler_id, sites):
    """Order-plans per candidate site: march now, build on arrival ETA."""
    cfg = to_cfg(config)
    sx, sy = None, None
    for a in state.own_armies():
        if a.id == settler_id:
            sx, sy = a.x, a.y
            break
    if sx is None:
        return []
    plans = []
    for (x, y) in sites:
        eta = max(1, math.ceil(math.hypot(x - sx, y - sy) / max(1.0, cfg["army_speed"])))
        plans.append(((x, y), {0: {"moves": {settler_id: (x, y)}},
                               eta: {"builds": {settler_id: (x, y)}}}))
    return plans


def rank(state, config, plans, default_idx=0, horizon=HORIZON, margin=MARGIN):
    """Rank order-plans by rollout value. Returns best index (default on
    ties/near-ties within margin, or clock-low). Pure function of intel."""
    if not plans:
        return default_idx
    towns, armies = world_snapshot(state)
    cfg = to_cfg(config)
    me = state.faction
    base = make_state(towns, armies)
    pstate = prune(base, me)
    vals = []
    for (site, plan) in plans:
        end = rollout(pstate, cfg, me, horizon,
                      lambda k, _p=plan: _p.get(k))
        vals.append(score(end, me))
    best = max(range(len(vals)), key=lambda i: vals[i])
    if vals[best] < vals[default_idx] * (1.0 + margin):
        return default_idx
    return best


def choose_site(state, config, p, rmin=160.0, rmax=300.0, salt=11, k=3):
    """Settle-site choice (M2 live search): heuristic best + alternates
    ranked by rollout value. Clock-gated (banked budget only); unknown
    budget or <2 sites -> heuristic best (deterministic, search-free)."""
    from ..settle import find_build_sites  # local: avoid import cycle
    sites = find_build_sites(state, config, p.x, p.y, rmin, rmax, salt, p.id, k)
    if len(sites) < 2:
        return sites[0] if sites else None
    if state.clock_budget_ms is None:
        return sites[0]
    if state.effort(state.clock_budget_ms) != "full":
        return sites[0]
    plans = site_plans(state, config, p.id, sites)
    return sites[rank(state, config, plans)]
