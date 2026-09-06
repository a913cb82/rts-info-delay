"""Expander — the colonist. Trains whenever affordable, always builds outward."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotState, DemandParams, bot_main, evac_plan, hopeless_capital, coverage_orders, buzzer_active, demand_trains, drive_scout, drop_dead_notes, expansion_demand, recall_deficit, find_build_site, en_route, hold_defenders, inbound_eta, inbound_force, assault_verified, fire_followups, sync_hold, jit_ready, maybe_assign_scout, note_wave_watch, probe_ok, order_move, order_march_exact, dispatch_settler, raid_target, reinforce_orders, should_hold_home, site_pays, strike_target, stay_behind_hold, tip_safe, respin_tip, maybe_schedule_scout, pack_print, second_wind, bloodlust, victory_lap, dead_foes


def _can_train_expander(state: BotState, town) -> bool:
    """Floor only + pending guard (sprawl prints everywhere affordable)."""
    from .common import train_floor
    return town.population >= train_floor(state, state.config)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out
    drop_dead_notes(state)  # unstrand armies whose orders died in flight
    _sched = maybe_schedule_scout(state, config)
    sc_out = list(_sched) if _sched else []
    out.extend(sc_out)
    # Evac (shared drain-and-flee; sprawl flees any doom).
    _sw = second_wind(state, config)
    if _sw:
        return _sw
    _vl = victory_lap(state, config)
    if _vl:
        return _vl
    _evac = evac_plan(state, config, hopeless_capital(state, config),
                       established_stays=False)
    if any(o.startswith("MOVE_CAPITAL") for o in _evac):
        out.extend(_evac)
        return out
    out.extend(_evac)
    own_t = state.own_towns()

    # Step 2, expander params (sprawl): core-only musters (depth +1000;
    # colonies are tripwires, not fortresses), counter-raids (margin 300),
    # impatient expansion (payback x0.3, horizon 100, parallel, rates
    # overridden — sprawl accepts -EV for slots/print; race-sites filed).
    out.extend(demand_trains(state, config, _can_train_expander, DemandParams(
        depth_extra=1000.0, raid_margin=300.0, payback_mult=0.3,
        probe_armies=1, void_horizon=100, rates=False, serial=False)))

    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    force = inbound_force(state, config)
    held = hold_defenders(state, config, force)
    out.extend(fire_followups(state, config))  # queued second waves fire first
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
        # Overkill cap (user: don't go overboard — strike mass marches
        # EVERYONE at one town). Cap marchers at need+2 (extras hold for
        # packs/patrols).
        if sk_march is not None and not en_route(state, sk_march[0].x, sk_march[0].y):
            _skm = sum(1 for a in state.own_armies()
                       if state.army_has_target(a.id) and state.army_target(a.id) is not None
                       and abs(state.army_target(a.id)[0] - sk_march[0].x) < 15
                       and abs(state.army_target(a.id)[1] - sk_march[0].y) < 15)
            if bloodlust(state, config) or _skm < sk_march[1] + 2:
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
            site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=350, salt=11, who=p.id), far_ok=True
        if site is not None and not site_pays(state, config, site[0], site[1]):
            site = None
        if site:
            sx, sy = site
            out.extend(dispatch_settler(state, config, p, sx, sy))
    # JIT packet flush: only full packets march.
    by_id = {a.id: a for a in state.own_armies()}
    for tgt_id, (tgt, tneed, members) in packets.items():
        if (len(members) >= tneed and (bloodlust(state, config) or tgt.faction in dead_foes(state) or assault_verified(state, tgt))) or jit_ready(state, config, tgt, tneed, members, tgt.faction):
            held = sync_hold(state, config, tgt.x, tgt.y, members)
            # Follow-on queue (user: take then fan out — pre-plan the
            # second wave: 2 nearest other foe towns. Fired on arrival
            # (grave/ours note) with zero idle turns between waves).
            foes = sorted((u for u in state.world.towns
                           if u.faction != state.faction and u.id != tgt.id),
                          key=lambda u: (u.x - tgt.x) ** 2 + (u.y - tgt.y) ** 2)[:2]
            # Overkill cap: march need (+1 spare), rest hold.
            sent = 0
            for aid in members:
                if aid in held:
                    continue  # near armies wait: land together
                if not bloodlust(state, config) and sent >= tneed + 1:
                    break
                a = by_id.get(aid)
                if a is not None:
                    out.extend(order_move(state, config, a, tgt.x, tgt.y))
                    sent += 1
                    if foes:
                        state.__dict__.setdefault("_followup", {})[aid] = [
                            (u.x, u.y) for u in foes]
            if sent > 0:
                # Attempt ledger, once per flush (shared with probe_ok +
                # recon caps — unseen deaths never blood).
                state.__dict__.setdefault("_assaults", {}).setdefault(tgt.id, []).append(state.turn)
    # Idle patrols last (doctrine: leftovers sweep stalest sectors).
    out.extend(coverage_orders(state, config))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
