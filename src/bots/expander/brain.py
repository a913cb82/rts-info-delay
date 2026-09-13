"""Expander — the colonist. Trains whenever affordable, always builds outward."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .intel import *
from .scout import *
from .threat import *
from .raid import *
from .settle import *
from .economy import *


def _can_train_expander(state: BotState, town) -> bool:
    """Floor only + pending guard (sprawl prints everywhere affordable).
    Capital-compound rule (raider autopsy: the capital training settlers
    down to ~1500 is what gets it killed — a rich capital converts a
    raider for free, a poor one dies). Once colonies exist, the capital
    only prints above 6000; colonies carry the sprawl (expendable)."""
    from .economy import train_floor
    floor = train_floor(state, state.config)
    cap = state.world.faction_capital(state.faction)
    if cap is not None and town.id == cap.id and len(state.own_towns()) > 1:
        floor = max(floor, 6000.0)
    return town.population >= floor


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out
    drop_dead_notes(state)  # unstrand armies whose orders died in flight
    _sched = maybe_schedule_scout(state, config)
    sc_out = list(_sched) if _sched else []
    out.extend(sc_out)
    own_t = state.own_towns()

    # Step 2, expander params (sprawl): core-only musters (depth +1000;
    # colonies are tripwires, not fortresses), counter-raids (margin 300),
    # impatient expansion (payback x0.3, horizon 100, parallel, rates
    # overridden — sprawl accepts -EV for slots/print; race-sites filed).
    out.extend(demand_trains(state, config, _can_train_expander, DemandParams(
        # Sprawl cadence: keep the tuned floor (1500+1000: a settler
        # leaves >=1500, survivable vs one raider — the 200 variant
        # created a vulnerable 700-window and died 4/6 games).
        depth_extra=1000.0, raid_margin=300.0, payback_mult=0.3,
        probe_armies=1, void_horizon=100, rates=False, serial=False)))
    # Standing guard (era-expander weakness, autopsy-verified: a single
    # raider beheads a naked capital while armies settle — pro's army 2
    # turns out, capital 0 defenders, dead t2733). One guard per rich
    # town once a foe army is VISIBLE (deterrence vs nobody is waste —
    # r129); conservative floor so guards never ride the death line.
    if any(a.faction != faction for a in state.world.armies):
        _home = {t.id: home_count(state, t) for t in own_t}
        for t in sorted(own_t, key=lambda x: -x.population):
            if _home.get(t.id, 0) == 0 and t.id not in state._pending_trains \
                    and t.population - config.army_cost \
                    >= config.death_threshold + 1000:
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
                break

    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    force = inbound_force(state, config)
    held = hold_defenders(state, config, force)
    sel = raid_target(state, config, margin=300.0)
    free_ids = [a.id for a in state.own_armies()
                if not state.army_has_target(a.id) and a.id not in held]
    free_n = len(free_ids)
    pack_building = sel is not None and sel[1] > free_n \
        and not jit_ready(state, config, sel[0], sel[1], free_ids,
        sel[0].faction)
    probe_armed = pack_building and probe_ok(state, sel)
    out.extend(pack_print(state, config, sel, free_n, _can_train_expander))
    probe_tgt = sel[0] if probe_armed else None
    probe_reach = 6.0 * max(1.0, config.army_speed)
    out.extend(recall_deficit(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
    packets: dict = {}  # tgt id -> (tgt, need, [aids]) JIT flush
    _sk = strike_target(state, config, margin=300.0)
    _sk_foes = [a for a in state.world.armies if a.faction != faction]
    sk_march = _sk if _sk is not None and not _sk_foes else None
    for p in state.own_armies():
        if state.should_yield():
            break
        if p.id in held:
            continue
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        sc = drive_scout(state, config, p)
        if sc is not None:
            out.extend(sc)
            continue
        # Stay-behind vs live threat (shared): last home guard holds.
        if stay_behind_hold(state, config, p, force):
            continue
        # Strike (windows close!): clear-field blitz/buzzer mass march —
        # unless one is already en route (per-target singularity).
        if sk_march is not None and not en_route(state, sk_march[0].x, sk_march[0].y):
            out.extend(order_move(state, config, p, sk_march[0].x, sk_march[0].y))
            continue
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            if tgt is None:
                continue
            tx, ty = tgt
            rx, ry = state.reckoned_pos(config, p.id)
            if math.hypot(rx - tx, ry - ty) < config.interact_radius + 10:
                # War-footing hold + suppressed-arrival re-decision (shared
                # Step 2/4-lite lessons): merges need TRUE void; lapsed
                # void foundings re-task instead of gifting hostages.
                own_home = any(math.hypot(tx - t.x, ty - t.y) < 20
                               for t in own_t)
                if state._foe_first_seen and own_home:
                    continue
                cap = state.world.faction_capital(faction)
                _max_turns = getattr(config, "max_turns", 3000) or 3000
                if own_home and cap is not None and math.hypot(tx - cap.x, ty - cap.y) < 20 \
                        and _max_turns - state.turn < 500:
                    continue
                if not own_home and state._foe_first_seen and not expansion_demand(
                        state, config, DemandParams(payback_mult=0.3, void_horizon=100,
                                                  rates=False, serial=False)):
                    state._army_targets.pop(p.id, None)
                    continue
                if not own_home and not tip_safe(state, config, tx, ty):
                    # Persist the re-task as a note FIRST (order_move is
                    # quiescence-gated and may emit [] — a popped-without-note
                    # army gets S0-stolen into an infinite probe loop).
                    rs = respin_tip(state, config, tx, ty)
                    dest = rs if rs is not None else (
                        (cap.x, cap.y) if cap is not None else None)
                    if dest is not None:
                        out.extend(order_march_exact(state, config, p, dest[0], dest[1]))
                    continue
                out.append(f"BUILD {p.id} {tx:.1f} {ty:.1f}")
            continue
        # Second-wave watch legacy (shared hold-set above does the work).
        if should_hold_home(state, config, p, inbound, hold_second):
            continue
        # Pack gate (shared pattern): undersized packs hold, except one
        # nearby probe vs visibly-empty.
        if pack_building:
            if not probe_armed or probe_tgt is None \
                    or en_route(state, probe_tgt.x, probe_tgt.y) \
                    or math.hypot(p.x - probe_tgt.x, p.y - probe_tgt.y) > probe_reach:
                continue
        # Counter-raid: march the priced take when ready — JIT packets
        # (collect; full packets flush post-loop). Staggered onesies
        # arrive piecemeal, wait, get recalled, re-raid (30-army shuttle
        # fleet) — mass or hold.
        if sel is not None and not pack_building:
            nearest, need, _ = sel
            packets.setdefault(nearest.id, (nearest, need, []))[2].append(p.id)
            continue
        # Buzzer (Step 6): no settling (never repays) — hold instead.
        if buzzer_active(state, config):
            continue
        # S0: no-contact scout first (Step 2 prereq) — probe deep before
        # founding; falls back to settling below.
        if maybe_assign_scout(state, config, p):
            out.extend(drive_scout(state, config, p) or [])
            continue
        # Sprawl settling (demand-gated; site veto applies — sprawl
        # accepts -EV patience, not fratricide (unbounded sprawl slows
        # decides past clock on long games: empty_10000 lesson). True
        # races override via filed race-sites (no racing rival exists).
        site = None
        if expansion_demand(state, config, DemandParams(
                payback_mult=0.3, void_horizon=100, rates=False, serial=False)):
            site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=350, salt=11, who=p.id)
        if site is not None and not site_pays(state, config, site[0], site[1]):
            site = None
        if site:
            sx, sy = site
            # Evasion (settler survival): foe armies within 50km of the
            # direct segment trigger a 100km-perpendicular dogleg waypoint
            # (dodge stale predictions; survive marches; found more).
            dx, dy = sx - p.x, sy - p.y
            seg = math.hypot(dx, dy) or 1.0
            for f in state.world.armies:
                if f.faction == faction:
                    continue
                t = max(0.0, min(1.0, ((f.x - p.x) * dx + (f.y - p.y) * dy) / (seg * seg)))
                cx, cy = p.x + t * dx, p.y + t * dy
                if math.hypot(f.x - cx, f.y - cy) <= 50.0:
                    nx, ny = -dy / seg, dx / seg
                    mx = (config.map_size[0] if config.map_size else 1000.0) - 20.0
                    my = (config.map_size[1] if len(config.map_size or []) > 1 else 1000.0) - 20.0
                    sx = min(mx, max(20.0, (p.x + sx) / 2 + nx * 100.0))
                    sy = min(my, max(20.0, (p.y + sy) / 2 + ny * 100.0))
                    break
            out.extend(dispatch_settler(state, config, p, sx, sy))
    # JIT packet flush: only full packets march.
    by_id = {a.id: a for a in state.own_armies()}
    for tgt_id, (tgt, tneed, members) in packets.items():
        if len(members) >= tneed or jit_ready(state, config, tgt, tneed, members, tgt.faction):
            for aid in members:
                a = by_id.get(aid)
                if a is not None:
                    out.extend(order_move(state, config, a, tgt.x, tgt.y))
    # Idle patrols last (doctrine: leftovers sweep stalest sectors).
    out.extend(coverage_orders(state, config))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
