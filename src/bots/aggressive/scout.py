"""aggressive scout — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403
from .settle import *  # noqa: F401,F403
from .raid import *  # noqa: F401,F403
from .intel import _dark  # noqa: F401

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


def scout_hop_target(state: "BotState", config, p, hop: int, gen: int = 0) -> tuple[float, float]:
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
    base = f * (2 * math.pi / 5) + gen * 2.399963 + hop * 0.35
    # Fan-out: each probe generation rotates the ray by the golden angle
    # (successive scouts cover different country), and each leg spirals
    # ~20 deg so one probe sweeps area instead of flying one straight ray.
    for turn in (0.0, math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2):
        ang = base + turn
        tx = min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(ang)))
        ty = min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(ang)))
        if all(_seg_dist(p.x, p.y, tx, ty, qx, qy) >= r for qx, qy, r in known):
            return (tx, ty)
    return (min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(base))),
            min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(base))))


def _scout_slot(state: "BotState", pid: int) -> int:
    """Which probe slot (1, 2) an army holds, else 0."""
    if state._scout_id == pid:
        return 1
    if getattr(state, "_scout_id2", None) == pid:
        return 2
    return 0


def _scout_unmark(state: "BotState", slot: int) -> None:
    if slot == 2:
        state._scout_id2 = None
        state._scout_leg2 = 0
    else:
        state._scout_id = None
        state._scout_leg = 0


def coverage_orders(state: "BotState", config) -> list[str]:
    """Idle patrols (doctrine: idle armies explore, never sit). Leftover
    unnoted field armies sweep the stalest coverage sectors (4x4 grid,
    stamped per payload). Nearest-idle to stalest-cell, one per cell.
    Runs LAST in moves stages (packs/scouts/settlers take theirs first).
    Notes via order_move (pendulum-breaker + amnesty bound them)."""
    import math as _math
    idle = [a for a in state.own_armies()
            if not state.army_has_target(a.id)
            and not getattr(a, "is_viceroy", False)
            and a.id != state._scout_id
            and a.id != getattr(state, "_scout_id2", None)]
    if not idle:
        return []
    size = (config.map_size if config is not None
            and getattr(config, "map_size", None) else [1000, 1000])
    n = 4
    cover = state.__dict__.get("_cover", {})
    cells = []
    for cx in range(n):
        for cy in range(n):
            seen = cover.get((cx, cy), -10 ** 9)
            cells.append((state.turn - seen, (cx + 0.5) / n * size[0],
                          (cy + 0.5) / n * size[1]))
    cells.sort(key=lambda c: -c[0])
    out: list[str] = []
    free = list(idle)
    for _, tx, ty in cells:
        if not free:
            break
        p = min(free, key=lambda a: _math.hypot(a.x - tx, a.y - ty))
        if _math.hypot(p.x - tx, p.y - ty) < 30:
            continue  # cell already has a body: keep sweeping elsewhere
        out.extend(order_move(state, config, p, tx, ty))
        free.remove(p)
    return out


def maybe_schedule_scout(state: "BotState", config):
    """Cartographic schedule (r35 lesson): neighbors-fresh != covered —
    fronts go blind and 94k rocks sit unpunished. Dark peace scouts
    every 500t (r58 lesson: 1500t cadence leaves empires blind all
    game); contact keeps 1500t. One surplus idle army per slot (fresh
    gen ray, existing fan machinery). Skips when a pack needs everyone."""
    period = 500 if _dark(state) else 1500
    if state.turn % period != (state.faction * 300) % period:
        return None
    if state._scout_id is not None and getattr(state, "_scout_id2", None) is not None:
        return None
    try:
        sel = raid_target(state, config, priced=True)
    except Exception:
        sel = None
    idle = [a for a in state.own_armies()
            if not a.is_viceroy and not state.army_has_target(a.id)
            and a.id != state._scout_id and a.id != getattr(state, "_scout_id2", None)]
    if sel is not None and sel[1] >= len(idle):
        return None  # pack needs everyone
    if not idle:
        return None
    if _scout_contact(state, config) and not _dark(state):
        return None  # real war on: raid/defense owns the field
    p = idle[0]
    if maybe_assign_scout(state, config, p):
        return drive_scout(state, config, p) or []
    return None


def maybe_assign_scout(state: "BotState", config, p) -> bool:
    """Mark p as a scout iff no actionable contact exists yet — true
    void OR rubble-only (a visible decoy is not a reason to stay home).
    Two concurrent probes (fan-out): the second takes a fresh generation
    ray, so scouts spread across the map instead of one line."""
    # No settle-first block here (TRIED + REVERTED): delaying the first
    # scout for a near-home settler breaks the S0 intel-first contract
    # (10 pinned tests + epistemics: void might hold foes, scouting
    # resolves it; far-but-interior tips win games). Clustering is handled
    # by the 65km floor (both paths), not by reordering missions.
    # No stay-behind block here (REVERTED): the first print must scout
    # (S0 contract, test-pinned) — and t1495's deny-convert was CORRECT
    # (1096 pop can't print a guard vs N=1 inbound anyway; convert
    # denies). Stay-behind lives in settled play (2+ armies), not probe.
    # Refound imperative (r61 + doctrine: townless armies settle, not
    # scout — exile colonies seed comebacks; lots of small = growth).
    if not state.own_towns():
        return False
    for slot, sid in ((1, state._scout_id), (2, getattr(state, "_scout_id2", None))):
        if sid is not None:
            # Dead scout frees the slot (else one death ends scouting forever).
            if state.world.get_army(sid) is None:
                _scout_unmark(state, slot)
            else:
                continue
        if state.turn < SCOUT_MIN_TURN:
            return False
        if p.is_viceroy:
            return False
        if _scout_contact(state, config) and not _dark(state):
            return False  # owned by raid/defense — unless blind (re-arm)
        if state.army_has_target(p.id):
            # Tasked armies are owned (kept scout tips go to builds, packs
            # to war): re-assigning steals the tip every hop-12 unmark and
            # the probe loops forever, never founding (0 foundings/3000t).
            return False
        state._scout_gen = getattr(state, "_scout_gen", -1) + 1
        if slot == 2:
            state._scout_id2 = p.id
            state._scout_leg2 = 0
            state._scout_gen2 = state._scout_gen
        else:
            state._scout_id = p.id
            state._scout_leg = 0
            state._scout_gen1 = state._scout_gen
        return True
    return False


def _expected_delay(state: "BotState", config, x: float, y: float) -> int:
    cap = state.world.faction_capital(state.faction)
    info = (config.info_speed if config is not None else 150.0)
    if cap is None:
        return 1
    return max(1, math.ceil(math.hypot(x - cap.x, y - cap.y) / info))


def ready_to_dispatch(state: "BotState", config, p) -> bool:
    """Freshness gate: order MOVE_TO when intel is fresh enough.

    Send-all era (was: quiescence — order only when the trail went
    quiet, proving nothing in flight). Every-turn delivery keeps trails
    permanently fresh, so quiescence almost never passed and armies
    froze on live notes (pro scout-7: 8000 turns, same order, no moves).
    Inverted rule: order from fresh intel (lag within 3x expected +
    margin); hold only when ancient (mail broken, don't compound error).
    Re-notes are idempotent, so stacking risk is nil."""
    tr = state._trails.get(p.id)
    if not tr or len(tr) < 2:
        # never (or once) seen: idle/spawn-stationary by construction.
        return True
    t_new, x, y = tr[-1]
    d = _expected_delay(state, config, x, y)
    return state.turn - t_new <= 3 * d + 2


def order_move(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    """MOVE_TO from converged intel (quiescence-gated) + note. [] when
    the order would die in flight — retry next turns, it converges."""
    if not ready_to_dispatch(state, config, p):
        return []
    state.note_move(p.id, float(tx), float(ty))
    rx, ry = state.reckoned_pos(config, p.id)
    return [f"MOVE_TO {p.id} {rx:.1f} {ry:.1f} {float(tx):.1f} {float(ty):.1f}"]


def dispatch_settler(state: "BotState", config, p, sx: float, sy: float) -> list[str]:
    """Settler MOVE_TO -> BUILD chain via the command queue: march now,
    BUILD scheduled for arrival (march time + messenger delay + slack).
    The BUILD fires on schedule even if arrival notes die (tip-loss saga)
    and defers if the march runs late; arrival detection stays as backup.
    Tag per army (re-tasks cancel the chain)."""
    import math as _math
    speed = max(1.0, config.army_speed)
    info = (config.info_speed if config is not None else 150.0) or 150.0
    march = _math.hypot(p.x - sx, p.y - sy) / speed
    delay = _math.ceil(_math.hypot(p.x - sx, p.y - sy) / info)
    fire = state.turn + int(_math.ceil(march)) + delay + 2
    tag = f"settle{p.id}"
    state.cancel_queued(tag)
    out = order_march_exact(state, config, p, sx, sy)
    state.queue_order(fire, f"BUILD {p.id} {sx:.1f} {sy:.1f}", tag)
    return out


def order_march_exact(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    """Unconditional noted march (bypasses quiescence): for own armies
    re-tasking from a hold (tip respins, recycle-home). Quiescence
    deadlocks there — a stationary army goes delivery-silent, its trail
    never converges, ready stays false forever, no orders flow, it never
    moves (army 5 held 24 turns at its tip). The from-risk is nil (army
    stationary: botpos error << messenger tolerance). Marching armies
    keep the gated order_move."""
    state.note_move(p.id, float(tx), float(ty))
    state._tip_grace[p.id] = state.turn + 30
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



def amnesty_notes(state: "BotState") -> None:
    """Note amnesty (r43 lesson: 27 armies noted 6000t+, nothing wants
    them, nothing releases them). Field notes older than 300t pop and
    re-decide fresh — valid plans reform in one turn (same sel, same
    tip); stale locks break. Home notes, scouts, viceroys, pending
    builds exempt (holding is their job).
    Guard rotation (r53 lesson: 39 idle, home notes never expire):
    every 1500t (faction-phased) home notes pop too — real threats
    re-hold next turn (hold_defenders runs every decide); quiet fronts
    release garrisons to the field. One turn of re-tasking per 1500."""
    rotate = state.turn % 1500 == (state.faction * 311) % 1500
    for aid, tgt in list(state._army_targets.items()):
        if aid == state._scout_id or aid == getattr(state, "_scout_id2", None):
            continue
        a = state.world.get_army(aid)
        if a is None or getattr(a, "is_viceroy", False):
            continue
        if state.has_pending_build(aid):
            continue
        if any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in state.world.towns
               if t.faction == state.faction):
            if not rotate:
                continue  # home note: guards hold (except rotation)
            state._army_targets.pop(aid, None)
            state.__dict__.get("_march_origin", {}).pop(aid, None)
            continue
        org = state.__dict__.get("_march_origin", {}).get(aid)
        if org is None or state.turn - org[2] <= 300:
            continue
        state._army_targets.pop(aid, None)
        state.__dict__.get("_march_origin", {}).pop(aid, None)


def drop_dead_notes(state: "BotState") -> None:
    """Clear MOVE_TO notes whose army is statically elsewhere: the order
    died in flight (messenger from-check on stale intel) and has_target
    would otherwise block fresh orders forever. The signal is trail
    freshness beyond the intel delay: a mover's snapshots keep arriving
    (delayed, but flowing), while a static army goes delivery-silent, so
    a trail older than expected-delay + 2 at one spot >20km off-note
    means stranded. Catches dispatch-time deaths too (army never left).
    Viceroys exempt (flight notes are live by construction)."""
    silence_watch(state, state.config)
    amnesty_notes(state)
    cap = state.world.faction_capital(state.faction)
    info = (state.config.info_speed if state.config is not None else 150.0)
    for aid, tgt in list(state._army_targets.items()):
        a = state.world.get_army(aid)
        if a is None or getattr(a, "is_viceroy", False):
            continue
        if aid == state._scout_id or aid == getattr(state, "_scout_id2", None):
            continue  # scout notes are drive-managed (hop legs re-note
            # constantly; trail-staleness misreads march holds as stranded
            # and pops the tip every few turns — the infinite probe loop)
        if aid in state._tip_grace and state.turn <= state._tip_grace[aid]:
            continue  # kept-tip grace (unmark/respin notes survive the
            # delivery lag + quiescence holds that fake strandedness)
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
        # Note age-cap: notes older than 100 turns without arrival are
        # stale intent (dead letters, obsolete raids) — drop and re-decide
        # fresh. (Pro t7000-8500: 22 armies sat home 1500 turns on dead
        # notes, never marching at priced thin towns.)
        noted_at = state.__dict__.get("_march_origin", {}).get(aid, (0, 0, 0))[2]
        if state.turn - noted_at > 100:
            del state._army_targets[aid]
            continue
        if math.hypot(x - tgt[0], y - tgt[1]) <= 20:
            continue  # trail shows arrival (freshest intel, not lagging
            # botpos — kept scout tips wait for builds here, never pop)
        if math.hypot(x - tgt[0], y - tgt[1]) > 20:
            del state._army_targets[aid]


MAPPER_HOPS = 8
MAPPER_HOP_KM = 150.0
MAPPER_MAX = 2


def mapper_hop_target(state: "BotState", config, p) -> tuple[float, float]:
    """Next mapping hop: tour the quadrant centroids in order (legs % 4).
    (Was: stalest-quadrant chase — arrival freshens it, the far side goes
    stalest, eternal 300km pendulum: mapper-33 painted 5301km of line.)
    A fixed tour covers the map once, then the patrol releases."""
    size = (config.map_size if config is not None
            and getattr(config, "map_size", None) else [1000, 1000])
    cx, cy = size[0] / 2.0, size[1] / 2.0
    quads = [(cx / 2, cy / 2), (cx + cx / 2, cy / 2),
             (cx / 2, cy + cy / 2), (cx + cx / 2, cy + cy / 2)]
    legs = state.__dict__.get("_mapper", {}).get(p.id, 0)
    qx, qy = quads[legs % 4]
    import math as _math
    d = _math.hypot(qx - p.x, qy - p.y)
    if d < 1e-9:
        return (qx, qy)
    step = min(MAPPER_HOP_KM, d)
    return (min(size[0] - 20.0, max(20.0, p.x + step * (qx - p.x) / d)),
            min(size[1] - 20.0, max(20.0, p.y + step * (qy - p.y) / d)))


def drive_mapper(state: "BotState", config, p):
    """Advance a mapping patrol; None = done (release to normal logic).
    Legs step on arrival (dead-reckoned); no founding (pure eyes)."""
    import math as _math
    legs = state.__dict__.get("_mapper", {}).get(p.id)
    if legs is None:
        return None
    if legs >= MAPPER_HOPS:
        state.__dict__.get("_mapper", {}).pop(p.id, None)
        state._army_targets.pop(p.id, None)
        return None
    tgt = state.army_target(p.id)
    if tgt is None:
        return _dispatch_leg(state, config, p, *mapper_hop_target(state, config, p))
    rx, ry = state.reckoned_pos(config, p.id)
    if _math.hypot(rx - tgt[0], ry - tgt[1]) >= 20:
        return []  # en route or awaiting arrival-intel: hold
    if not ready_to_dispatch(state, config, p):
        return []
    state.__dict__.setdefault("_mapper", {})[p.id] = legs + 1
    return _dispatch_leg(state, config, p, *mapper_hop_target(state, config, p))


def drive_scout(state: "BotState", config, p):
    """Advance the marked scout; None = not-a-scout (handle normally).

    Unmarks for viable towns (raid logic owns) and foe armies (defense
    owns). Stays out on rubble-only contact, hopping around it, so the
    probe never accidentally captures starvation (trap lesson)."""
    slot = _scout_slot(state, p.id)
    if slot == 0:
        return None
    still_key = "_scout_still" if slot == 1 else "_scout_still2"
    leg = state._scout_leg2 if slot == 2 else state._scout_leg
    gen = getattr(state, "_scout_gen2", 0) if slot == 2 else getattr(state, "_scout_gen1", 0)
    def _bump(n: int) -> int:
        if slot == 2:
            state._scout_leg2 = n
        else:
            state._scout_leg = n
        return n
    if p.is_viceroy:
        _scout_unmark(state, slot)
        return None
    if _scout_contact(state, config):
        # Contact: raid/defense owns the army fresh — drop the stale hop
        # target or it hijacks the army into founding next to the prize.
        _scout_unmark(state, slot)
        state._army_targets.pop(p.id, None)
        return None
    tgt = state.army_target(p.id)
    if tgt is None:
        return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, leg, gen))
    # Arrival on dead-reckoned pos (own march physics exact; botpos lags
    # 30km+ behind truth and freezes for holding armies).
    rx, ry = state.reckoned_pos(config, p.id)
    if math.hypot(rx - tgt[0], ry - tgt[1]) >= 20:
        state.__dict__.pop(still_key, None)
        return []  # mid-hop or waiting arrival-intel: hold
    # arrived: next hop only from quiescent intel (else the order dies in
    # flight); the leg steps exactly when the hop dispatches, never twice
    # on persistent arrival-intel.
    if not ready_to_dispatch(state, config, p):
        # Still-arrival force: a holding scout goes delivery-silent, its
        # trail never converges, ready stays false forever — legs stall
        # one short of unmark and the scout sits at its tip for 1600+
        # turns (aggressive t1365-t3000). Persistent static arrival
        # (past delivery lag) forces the leg; phantom-early unmarks are
        # harmless (tip kept early, army catches up and founds).
        info = (config.info_speed if config is not None else 150.0) or 150.0
        cap = state.world.faction_capital(state.faction)
        exp = math.ceil(math.hypot(p.x - cap.x, p.y - cap.y) / info) if cap else 1
        st = state.__dict__.get(still_key)
        if st is None or math.hypot(p.x - st[0], p.y - st[1]) > 1e-6:
            state.__dict__[still_key] = (p.x, p.y, 1)
            return []
        if st[2] < exp + 2:
            state.__dict__[still_key] = (p.x, p.y, st[2] + 1)
            return []
        state.__dict__.pop(still_key, None)
    else:
        state.__dict__.pop(still_key, None)
    if not ready_to_dispatch(state, config, p):
        return []
    leg = _bump(leg + 1)
    if leg >= SCOUT_HOPS:
        # hops exhausted with no contact: convert the tip HERE (drive owns
        # it end-to-end — handing a kept note to builds loses it 7 ways:
        # drop_dead, S0 re-steal, quiescence deadlock, grace expiry,
        # arrival-lag, respin-None, cap-march death-letters). Arrived +
        # gated -> BUILD now; bad tip -> respin note+march (queued BUILD
        # fires on arrival); builds stays as backup only.
        _scout_unmark(state, slot)
        if tgt is not None:
            interact = (config.interact_radius if config is not None
                        and getattr(config, "interact_radius", None) else 10.0)
            if any(t.faction == state.faction and math.hypot(t.x - tgt[0], t.y - tgt[1]) <= interact + 10.0
                   for t in state.world.towns):
                state._army_targets.pop(p.id, None)
            else:
                state._tip_grace[p.id] = state.turn + 20
                rx, ry = state.reckoned_pos(config, p.id)
                if math.hypot(rx - tgt[0], ry - tgt[1]) <= interact + 10.0:
                    foe_known = any(t.faction != state.faction for t in state.world.towns) \
                        or any(a.faction != state.faction for a in state.world.armies)
                    demand_ok = (not state._foe_first_seen) or expansion_demand(state, config)
                    if (not foe_known or demand_ok) and site_pays(state, config, tgt[0], tgt[1]) \
                            and tip_safe(state, config, tgt[0], tgt[1]):
                        state.note_build(p.id)
                        return [f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}"]
                rs = respin_tip(state, config, tgt[0], tgt[1])
                if rs is not None:
                    # Full chain: march + scheduled BUILD (fires on arrival
                    # even if notes die; arrival detection is backup).
                    return dispatch_settler(state, config, p, rs[0], rs[1])
        return []
    return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, leg, gen))



