"""Expander — the colonist. Trains whenever affordable, always builds outward."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotState, DemandParams, bot_main, buzzer_active, demand_trains, drive_scout, drop_dead_notes, expansion_demand, recall_deficit, find_build_site, hold_defenders, inbound_eta, inbound_force, jit_ready, maybe_assign_scout, note_wave_watch, order_move, raid_target, reinforce_orders, should_hold_home


def _can_train_expander(state: BotState, town) -> bool:
    """Floor only + pending guard (sprawl prints everywhere affordable)."""
    return town.population >= 1500


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out
    drop_dead_notes(state)  # unstrand armies whose orders died in flight
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
    sel = raid_target(state, config, margin=300.0)
    free_ids = [a.id for a in state.own_armies()
                if not state.army_has_target(a.id) and a.id not in held]
    free_n = len(free_ids)
    pack_building = sel is not None and sel[1] > free_n \
        and not jit_ready(state, config, sel[0], sel[1], free_ids)
    probe_armed = pack_building and sel[2] == 0
    probe_tgt = sel[0] if probe_armed else None
    probe_reach = 6.0 * max(1.0, config.army_speed)
    probe_sent = False
    if probe_tgt is not None:
        for a in state.own_armies():
            tgt = state.army_target(a.id)
            if tgt is not None and math.hypot(tgt[0] - probe_tgt.x, tgt[1] - probe_tgt.y) <= 20.0:
                probe_sent = True
                break
    out.extend(recall_deficit(state, config))
    out.extend(reinforce_orders(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
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
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            if tgt is None:
                continue
            tx, ty = tgt
            if math.hypot(p.x - tx, p.y - ty) < config.interact_radius + 10:
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
                out.append(f"BUILD {p.id} {tx:.1f} {ty:.1f}")
            continue
        # Second-wave watch legacy (shared hold-set above does the work).
        if should_hold_home(state, config, p, inbound, hold_second):
            continue
        # Pack gate (shared pattern): undersized packs hold, except one
        # nearby probe vs visibly-empty.
        if pack_building:
            if not probe_armed or probe_sent or probe_tgt is None or \
                    math.hypot(p.x - probe_tgt.x, p.y - probe_tgt.y) > probe_reach:
                continue
            probe_sent = True
        # Counter-raid: march the priced take when ready.
        if sel is not None and not pack_building:
            nearest, _, _ = sel
            out.extend(order_move(state, config, p, nearest.x, nearest.y))
            continue
        # Buzzer (Step 6): no settling (never repays) — hold instead.
        if buzzer_active(state, config):
            continue
        # S0: no-contact scout first (Step 2 prereq) — probe deep before
        # founding; falls back to settling below.
        if maybe_assign_scout(state, config, p):
            out.extend(drive_scout(state, config, p) or [])
            continue
        # Sprawl settling (demand-gated, no site veto — race over pop).
        site = None
        if expansion_demand(state, config, DemandParams(
                payback_mult=0.3, void_horizon=100, rates=False, serial=False)):
            site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=350, salt=11, who=p.id)
        if site:
            sx, sy = site
            out.extend(order_move(state, config, p, sx, sy))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
