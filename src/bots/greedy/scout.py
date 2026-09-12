"""greedy scout — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
from .intel import *  # noqa: F401,F403
from .settle import expansion_demand  # noqa: F401
import json
import sys
import time
from dataclasses import dataclass, field
from engine.world import World, Town, Army
import math
from engine.config import GameConfig

def _scout_contact(state: "BotState", config) -> bool:
    """True iff raid/defense logic should own all armies: a viable town
    (duel-core gate; everything in multi-foe wars) or any foe army."""
    f = state.faction
    foe_towns = [t for t in state.world.towns if t.faction != f]
    if any(a.faction != f for a in state.world.armies):
        return True
    war_foes = {t.faction for t in foe_towns}
    viable = ([t for t in foe_towns if scout_viable(state, config, t)]
              if len(war_foes) <= 1 else list(foe_towns))
    return bool(viable)


def scout_hop_target(state: "BotState", config, p, hop: int) -> tuple[float, float]:
    """Next 50km hop: straight faction-spread ray, bent off known towns.
    Tries base, ±45°, ±90°; first segment clearing all known towns by
    15km wins; all-blocked falls back to base (rare blunder accepted).
    Probe memory: also bends off own towns and fellow-probe destinations
    (20km), so repeat probes don't re-fly settled rays into duplicate
    merges. Memory points underfoot (< interact+15 of p) are skipped —
    the scout stands on its own capital at dispatch. Foe logic is
    untouched (danger keeps no underfoot exemption)."""
    size = (config.map_size if config is not None
            and getattr(config, "map_size", None) else [1000, 1000])
    interact = (config.interact_radius if config is not None
                and getattr(config, "interact_radius", None) else 10.0)
    f = state.faction
    known = [(t.x, t.y, 15.0) for t in state.world.towns if t.faction != f]
    for t in state.world.towns:
        if t.faction == f and math.hypot(t.x - p.x, t.y - p.y) >= interact + 15.0:
            known.append((t.x, t.y, 20.0))
    for aid, tgt in sorted(state._army_targets.items()):
        if (aid != p.id and tgt is not None
                and math.hypot(tgt[0] - p.x, tgt[1] - p.y) >= interact + 15.0):
            known.append((tgt[0], tgt[1], 20.0))
    base = f * (2 * math.pi / 5)
    for turn in (0.0, math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2):
        ang = base + turn
        tx = min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(ang)))
        ty = min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(ang)))
        if all(_seg_dist(p.x, p.y, tx, ty, qx, qy) >= r for qx, qy, r in known):
            return (tx, ty)
    return (min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(base))),
            min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(base))))


def maybe_assign_scout(state: "BotState", config, p) -> bool:
    """Mark p as the scout iff no actionable contact exists yet — true
    void OR rubble-only (a visible decoy is not a reason to stay home)."""
    if state._scout_id is not None or state.turn < SCOUT_MIN_TURN:
        return False
    if p.is_viceroy or _scout_contact(state, config):
        return False
    state._scout_id = p.id
    state._scout_leg = 0
    return True


def _expected_delay(state: "BotState", config, x: float, y: float) -> int:
    cap = state.world.faction_capital(state.faction)
    info = (config.info_speed if config is not None else 150.0)
    if cap is None:
        return 1
    return max(1, math.ceil(math.hypot(x - cap.x, y - cap.y) / info))


def ready_to_dispatch(state: "BotState", config, p) -> bool:
    """Quiescence gate: order MOVE_TO only from converged intel.

    The messenger from-check allows ~1 turn of movement; intel older
    than that vs a marching army is a guaranteed dead letter (which then
    strands the army behind a stale note). Converged = trail newest age
    >= 2x expected delay (nothing in flight), or a noted arrival aged >=
    delay (truth static at note since before intel). No trail = idle."""
    tr = state._trails.get(p.id)
    if not tr or len(tr) < 2:
        # never (or once) seen: idle/spawn-stationary by construction.
        return True
    t_new, x, y = tr[-1]
    d = _expected_delay(state, config, x, y)
    if state.turn - t_new >= 2 * d:
        return True
    tgt = state.army_target(p.id)
    if (tgt is not None and math.hypot(x - tgt[0], y - tgt[1]) <= 20
            and state.turn - t_new >= d):
        return True
    return False


def order_move(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    """MOVE_TO from converged intel (quiescence-gated) + note. [] when
    the order would die in flight — retry next turns, it converges."""
    if not ready_to_dispatch(state, config, p):
        return []
    state.note_move(p.id, float(tx), float(ty))
    return [f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {float(tx):.1f} {float(ty):.1f}"]


def _dispatch_leg(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    return order_move(state, config, p, tx, ty)


def scout_viable(state: "BotState", config, t) -> bool:
    """Duel-core viability: captured half must clear floor + margin."""
    eff = config.build_efficiency if config is not None else 0.5
    cost = config.army_cost if config is not None else 1000
    return t.population * (1.0 - eff) > cost * eff + 200


def _seg_dist(px, py, tx, ty, qx, qy) -> float:
    dx, dy = tx - px, ty - py
    d2 = dx * dx + dy * dy
    if d2 < 1e-9:
        return math.hypot(qx - px, qy - py)
    s = max(0.0, min(1.0, ((qx - px) * dx + (qy - py) * dy) / d2))
    return math.hypot(qx - (px + dx * s), qy - (py + dy * s))


def drop_dead_notes(state: "BotState") -> None:
    """Clear MOVE_TO notes whose army is statically elsewhere: the order
    died in flight (messenger from-check on stale intel) and has_target
    would otherwise block fresh orders forever. The signal is trail
    freshness beyond the intel delay: a mover's snapshots keep arriving
    (delayed, but flowing), while a static army goes delivery-silent, so
    a trail older than expected-delay + 2 at one spot >20km off-note
    means stranded. Catches dispatch-time deaths too (army never left).
    Viceroys exempt (flight notes are live by construction)."""
    cap = state.world.faction_capital(state.faction)
    info = (state.config.info_speed if state.config is not None else 150.0)
    for aid, tgt in list(state._army_targets.items()):
        a = state.world.get_army(aid)
        if a is None or getattr(a, "is_viceroy", False):
            continue
        tr = state._trails.get(aid)
        if not tr:
            continue
        t_new, x, y = tr[-1]
        if cap is not None:
            exp_delay = math.ceil(math.hypot(x - cap.x, y - cap.y) / info)
        else:
            exp_delay = 1
        if state.turn - t_new < exp_delay + 2:
            continue  # intel still flowing
        if math.hypot(x - tgt[0], y - tgt[1]) > 20:
            del state._army_targets[aid]


def drive_scout(state: "BotState", config, p):
    """Advance the marked scout; None = not-a-scout (handle normally).

    Unmarks for viable towns (raid logic owns) and foe armies (defense
    owns). Stays out on rubble-only contact, hopping around it, so the
    probe never accidentally captures starvation (trap lesson)."""
    if state._scout_id != p.id:
        return None
    if p.is_viceroy:
        state._scout_id = None
        state._scout_leg = 0
        return None
    if _scout_contact(state, config):
        # Contact: raid/defense owns the army fresh — drop the stale hop
        # target or it hijacks the army into founding next to the prize.
        state._scout_id = None
        state._scout_leg = 0
        state._army_targets.pop(p.id, None)
        return None
    tgt = state.army_target(p.id)
    if tgt is None:
        return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, state._scout_leg))
    if math.hypot(p.x - tgt[0], p.y - tgt[1]) >= 20:
        return []  # mid-hop or waiting arrival-intel: hold
    # arrived: next hop only from quiescent intel (else the order dies in
    # flight); the leg steps exactly when the hop dispatches, never twice
    # on persistent arrival-intel.
    if not ready_to_dispatch(state, config, p):
        return []
    state._scout_leg += 1
    if state._scout_leg >= SCOUT_HOPS:
        # hops exhausted with no contact: builds stage founds on the
        # kept target (settle-as-scout); normal logic owns again. But a
        # kept target inside an own town's founding range is a duplicate
        # merge, not a founding — drop the note so builds don't fire on
        # it (normal site choice or recycle owns instead). And fallback
        # founding is for TRUE void (foe never seen — recycle's capability
        # contract); with foe history the army recycles or raids instead
        # (void_contact t328: -460 late luxury). expansion_demand covers
        # the contested-payback remainder.
        state._scout_id = None
        if tgt is not None and state._foe_first_seen:
            # Foe history: fallback founding faces the same EV bar as any
            # expansion (rates + horizon) — true void keeps the capability
            # contract (recycle), history without demand recycles or raids.
            if not expansion_demand(state, config, void_horizon=500):
                state._army_targets.pop(p.id, None)
                tgt = None
        if tgt is not None:
            interact = (config.interact_radius if config is not None
                        and getattr(config, "interact_radius", None) else 10.0)
            if any(t.faction == state.faction and math.hypot(t.x - tgt[0], t.y - tgt[1]) <= interact + 10.0
                   for t in state.world.towns):
                state._army_targets.pop(p.id, None)
            elif not expansion_demand(state, config):
                state._army_targets.pop(p.id, None)
        return []
    return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, state._scout_leg))



