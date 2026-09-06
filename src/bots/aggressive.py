"""Aggressive — conqueror. Trains eagerly, chases enemies, expands when clear."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, DemandParams, bot_main, evac_plan, hopeless_capital, coverage_orders, demand_trains, drive_scout, drop_dead_notes, expansion_demand, recall_deficit, find_build_site, en_route, hold_defenders, war_print_need, inbound_eta, inbound_force, assault_verified, fire_followups, jit_ready, maybe_assign_scout, note_wave_watch, probe_ok, order_move, order_march_exact, dispatch_settler, raid_target, reinforce_orders, should_hold_home, site_pays, strike_target, stay_behind_hold, tip_safe, respin_tip, maybe_schedule_scout, pack_print, second_wind, bloodlust, victory_lap, reprint_ok


def _can_train_aggressive(state: BotState, town) -> bool:
    """Thin cushion (fights): floor only + pending guard. Forward towns
    must print (raid logistics) — no distance rule, no peak cap."""
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
    # Evac (shared drain-and-flee; predators flee doom too).
    _sw = second_wind(state, config)
    if _sw:
        return _sw
    _vl = victory_lap(state, config)
    if _vl:
        return _vl
    _evac = evac_plan(state, config, hopeless_capital(state, config))
    if any(o.startswith("MOVE_CAPITAL") for o in _evac):
        out.extend(_evac)
        return out
    out.extend(_evac)

    # Step 2, aggressive params (predator): thin cushion (depth 0),
    # marginal+initiative raids (margin 100), economic expansion rare
    # (payback x3 — foundings are military staging, below), 1 prober.
    out.extend(demand_trains(state, config, _can_train_aggressive, DemandParams(
        raid_margin=100.0, payback_mult=3.0, probe_armies=1)))

    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    enemy_armies = [a for a in state.world.armies if a.faction != faction]
    own_t = state.own_towns()
    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    force = inbound_force(state, config)
    held = hold_defenders(state, config, force)
    out.extend(fire_followups(state, config))  # queued second waves fire first
    # A1 lives inside raid_target now (duel-gated viability + priced
    # selection, margin 100 for initiative). Priced for duels, pressure
    # for big wars.
    war_foes = {t.faction for t in enemy_towns} | {a.faction for a in enemy_armies}
    duel_ctx = len(war_foes) <= 1
    sel = raid_target(state, config, priced=duel_ctx, margin=100.0)
    free_ids = [a.id for a in state.own_armies()
                if not state.army_has_target(a.id) and a.id not in held]
    free_n = len(free_ids)
    pack_building = sel is not None and sel[1] > free_n \
        and not jit_ready(state, config, sel[0], sel[1], free_ids,
        sel[0].faction)
    probe_armed = pack_building and probe_ok(state, sel)
    out.extend(pack_print(state, config, sel, free_n, _can_train_aggressive))
    probe_tgt = sel[0] if probe_armed else None
    probe_reach = 6.0 * max(1.0, config.army_speed)
    out.extend(recall_deficit(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
    _sk = strike_target(state, config, margin=100.0)
    # Local superiority (r121: global `not enemy_armies` veto = 4
    # prints/game; no veto = feeding. Strike unless a foe army sits on
    # the target (within 200km) — towns fall, armies don't get fed).
    sk_march = None
    if _sk is not None:
        _tx, _ty = _sk[0].x, _sk[0].y
        if not any(math.hypot(a.x - _tx, a.y - _ty) <= 200.0
                   for a in enemy_armies):
            sk_march = _sk
    fc_chase = BotForecast(state, config)
    for p in state.own_armies():
        if state.should_yield():
            break
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
            # only BUILD if target is not an enemy town (attack needs capture, not BUILD)
            is_enemy_target = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in enemy_towns)
            rx, ry = state.reckoned_pos(config, p.id)
            if not is_enemy_target and math.hypot(rx - tgt[0], ry - tgt[1]) < config.interact_radius + 10:
                # War-footing: home-bound armies hold (shared guard_duty
                # lesson) — merges need TRUE void (never-seen), never
                # eviction-flicker (shared endgame lesson).
                own_home = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20
                               for t in own_t)
                if state._foe_first_seen and own_home:
                    continue
                cap = state.world.faction_capital(faction)
                _max_turns = getattr(config, "max_turns", 3000) or 3000
                if own_home and cap is not None and math.hypot(tgt[0] - cap.x, tgt[1] - cap.y) < 20 \
                        and _max_turns - state.turn < 500:
                    continue
                # Suppressed arrivals (shared Step 4 lite): void-site
                # foundings whose purpose lapsed re-decide instead of
                # gifting hostages. True-void always founds.
                if not own_home and state._foe_first_seen and not expansion_demand(
                        state, config, payback_mult=3.0):
                    state._army_targets.pop(p.id, None)
                    continue
                if not own_home and not site_pays(state, config, tgt[0], tgt[1]):
                    state._army_targets.pop(p.id, None)
                    continue
                if not own_home and not tip_safe(state, config, tgt[0], tgt[1]):
                    # Persist the re-task as a note FIRST (order_move is
                    # quiescence-gated and may emit [] — a popped-without-note
                    # army gets S0-stolen into an infinite probe loop).
                    rs = respin_tip(state, config, tgt[0], tgt[1])
                    dest = rs if rs is not None else (
                        (cap.x, cap.y) if cap is not None else None)
                    if dest is not None:
                        out.extend(order_march_exact(state, config, p, dest[0], dest[1]))
                    continue
                out.append(f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}")
            continue
        if p.id in held:
            continue
        if should_hold_home(state, config, p, inbound, hold_second):
            continue
        # Stay-behind vs live threat (shared): last home guard holds.
        if stay_behind_hold(state, config, p, force):
            continue
        # Strike (windows close!): clear-field blitz/buzzer mass march —
        # unless one is already en route (per-target singularity).
        # Predator overwhelm (range doctrine: aggressive never caps strikes —
        # bounces waste whole packs, overkill wastes +2. Extras hold only
        # for packs/patrols via singularity).
        if sk_march is not None and not en_route(state, sk_march[0].x, sk_march[0].y):
            _skm = sum(1 for a in state.own_armies()
                       if state.army_has_target(a.id) and state.army_target(a.id) is not None
                       and abs(state.army_target(a.id)[0] - sk_march[0].x) < 15
                       and abs(state.army_target(a.id)[1] - sk_march[0].y) < 15)
            out.extend(order_move(state, config, p, sk_march[0].x, sk_march[0].y))
            continue
        # Pack gate subsumes A2 departure-sync (need covers defendedness;
        # the old retrench-march trickled). Undersized packs hold, except
        # one nearby probe vs visibly-empty (bounded recon by fire).
        if pack_building:
            if not probe_armed or probe_tgt is None \
                    or en_route(state, probe_tgt.x, probe_tgt.y) \
                    or math.hypot(p.x - probe_tgt.x, p.y - probe_tgt.y) > probe_reach:
                continue
        if sel is not None:
            # A3: leader-targeting survives inside raid_target's pressure
            # branch (big wars); duels march the priced take at +1.
            # Stale-belief targets hold for re-verify (fratricide).
            nearest, _, _ = sel
            if assault_verified(state, nearest):
                # Last-guard hold (predator bleeds home chasing kills):
                # the only army home stays home; extras raid.
                _home = [t for t in own_t
                         if math.hypot(p.x - t.x, p.y - t.y) <= 20.0]
                _other_home = any(a.id != p.id and any(
                    math.hypot(a.x - t.x, t.y - t.y) <= 20.0 for t in own_t)
                    for a in state.own_armies())
                if _home and not _other_home:
                    continue
                out.extend(order_move(state, config, p, nearest.x, nearest.y))
        elif enemy_armies:
            forecast = [(fc_chase.forecast_army_pos(e), e) for e in enemy_armies]
            (fx, fy), _ = min(forecast, key=lambda x: math.hypot(x[0][0] - p.x, x[0][1] - p.y))
            out.extend(order_move(state, config, p, fx, fy))
        else:
            # S0: no-contact scout first (Step 2 prereq) — probe deep
            # before founding; falls back to settling below.
            if maybe_assign_scout(state, config, p):
                out.extend(drive_scout(state, config, p) or [])
                continue
            # Military staging (not economic settling): found toward the
            # raid target while no own town stands within 150km of it —
            # forward bases are raid infrastructure. Staging builds WITH
            # the pack (a forward town prints locally: short arrival ->
            # small W -> completable needs; without it packs chase
            # receding needs forever). Marginal horizon 500 kills only
            # late-war obsolete-before-arrival outposts (viable t32).
            # Economic settling waits for pack completion (concentrate).
            staged = False
            if sel is not None \
                    and config.max_turns - state.turn >= 500:
                tgt, _, _ = sel
                if not any(math.hypot(t.x - tgt.x, t.y - tgt.y) <= 150.0
                           for t in own_t):
                    staged = True
            site = None
            if staged or (expansion_demand(state, config, DemandParams(payback_mult=3.0))
                          and not pack_building):
                site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=340, salt=11, who=p.id)
            # Site veto for economic foundings (staging bypasses: its value
            # is position, not pop).
            if site is not None and not staged and not war_print_need(state, config) \
                    and not site_pays(state, config, site[0], site[1]):
                site = None
            if site:
                out.extend(dispatch_settler(state, config, p, site[0], site[1]))
    # Idle patrols last (doctrine: leftovers sweep stalest sectors).
    out.extend(coverage_orders(state, config))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
