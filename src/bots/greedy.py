"""Greedy — raider. Most eager trainer, opportunistic attacker/builder."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, DemandParams, bot_main, can_train_standard, demand_trains, drive_scout, drop_dead_notes, expansion_demand, find_build_site, en_route, hold_defenders, war_print_need, inbound_eta, inbound_force, jit_ready, maybe_assign_scout, note_wave_watch, order_move, order_march_exact, dispatch_settler, raid_target, recall_deficit, reinforce_orders, should_hold_home, site_pays, strike_target, stay_behind_hold, tip_safe, respin_tip


def _stage_trains(state: BotState, config: GameConfig) -> list[str]:
    # Step 2, greedy params (present-biased skipper): rich-only incident
    # muster (depth +500), transfer-positive raids only (margin 500),
    # cherry-pick expansion (payback x2). No P3b — void settlers need trains.
    return demand_trains(state, config, can_train_standard, DemandParams(
        depth_extra=500.0, raid_margin=500.0, payback_mult=2.0,
        probe_armies=1))


def _army_targets(state: BotState, config: GameConfig):
    faction = state.faction
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    enemy_armies = [a for a in state.world.armies if a.faction != faction]
    return enemy_towns, enemy_armies


def _stage_moves(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    enemy_towns, enemy_armies = _army_targets(state, config)
    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    force = inbound_force(state, config)
    held = hold_defenders(state, config, force)
    sel = raid_target(state, config, margin=500.0)
    free_ids = [a.id for a in state.own_armies()
                if not state.army_has_target(a.id) and a.id not in held]
    free_n = len(free_ids)
    pack_building = sel is not None and sel[1] > free_n \
        and not jit_ready(state, config, sel[0], sel[1], free_ids,
        sel[0].faction)
    probe_armed = pack_building and sel[2] == 0
    probe_tgt = sel[0] if probe_armed else None
    probe_reach = 6.0 * max(1.0, config.army_speed)
    out.extend(recall_deficit(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
    _sk = strike_target(state, config, margin=500.0)
    sk_march = _sk if _sk is not None and not enemy_armies else None
    fc_chase = BotForecast(state, config)
    for p in state.own_armies():
        if state.should_yield():
            break
        sc = drive_scout(state, config, p)
        if sc is not None:
            out.extend(sc)
            continue
        if state.army_has_target(p.id):
            continue  # handled by the builds stage
        # G-defense (shared hold-set) + second-wave watch legacy.
        if p.id in held:
            continue
        if should_hold_home(state, config, p, inbound, hold_second):
            continue
        # Stay-behind vs live threat (shared): last home guard holds.
        if stay_behind_hold(state, config, p, force):
            continue
        # Strike (windows close!): clear-field blitz/buzzer mass march —
        # unless one is already en route (per-target singularity).
        if sk_march is not None and not en_route(state, sk_march[0].x, sk_march[0].y):
            out.extend(order_move(state, config, p, sk_march[0].x, sk_march[0].y))
            continue
        # Priced takes only (transfer-positive): march the selected victim
        # when the pack is ready, else hold while trains build it.
        # Viability lives inside raid_target (duel-gated).
        if pack_building:
            if not probe_armed or probe_tgt is None \
                    or en_route(state, probe_tgt.x, probe_tgt.y) \
                    or math.hypot(p.x - probe_tgt.x, p.y - probe_tgt.y) > probe_reach:
                continue
        if sel is not None:
            nearest, _, _ = sel
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
            # G2: settle on demand (cherry-pick x2) — else recycle home,
            # peace-only (war-footing holds; disbanding feeds merges).
            site = find_build_site(state, config, p.x, p.y, rmin=80, rmax=300, salt=11, who=p.id) \
                if expansion_demand(state, config, DemandParams(payback_mult=2.0)) else None
            if site is not None and not war_print_need(state, config) \
                    and not site_pays(state, config, site[0], site[1]):
                site = None
            if site:
                out.extend(dispatch_settler(state, config, p, site[0], site[1]))
            elif state.own_towns():
                foe_known = bool(enemy_towns) or bool(enemy_armies)
                if not foe_known:
                    home = min(state.own_towns(), key=lambda t: math.hypot(t.x - p.x, t.y - t.y))
                    out.extend(order_move(state, config, p, home.x, home.y))
    return out


def _stage_builds(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    faction = state.faction
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    for p in state.own_armies():
        if state.should_yield():
            break
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        if not state.army_has_target(p.id):
            continue
        if state._scout_id == p.id:
            continue  # scout waypoints are not destinations: drive owns them
        if state.has_pending_build(p.id):
            continue
        tgt = state.army_target(p.id)
        if tgt is None:
            continue
        is_enemy_target = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in enemy_towns)
        if not is_enemy_target and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
            # War-footing: home-bound armies hold as defenders (shared
            # guard_duty lesson) — merges need TRUE void (never-seen),
            # never eviction-flicker (shared endgame lesson).
            own_home = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20
                           for t in state.world.towns if t.faction == faction)
            if state._foe_first_seen and own_home:
                continue
            cap = state.world.faction_capital(faction)
            _max_turns = getattr(config, "max_turns", 3000) or 3000
            if own_home and cap is not None and math.hypot(tgt[0] - cap.x, tgt[1] - cap.y) < 20 \
                    and _max_turns - state.turn < 500:
                continue
            # Suppressed arrivals (shared Step 4 lite): void-site foundings
            # whose purpose lapsed re-decide (drop the note, normal logic
            # owns) instead of gifting hostages. True-void always founds.
            if not own_home and state._foe_first_seen and not expansion_demand(
                    state, config, payback_mult=2.0):
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
    return out


_STAGES = [("trains", _stage_trains), ("moves", _stage_moves), ("builds", _stage_builds)]


def decide_stages(state: BotState, config: GameConfig) -> list[tuple[str, list[str]]]:
    """Idea 2: full stage outputs (introspection/testing; decide_orders is lazy)."""
    return [(name, fn(state, config)) for name, fn in _STAGES]


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    if state.should_yield():
        return out
    drop_dead_notes(state)  # unstrand armies whose orders died in flight
    # Idea 2: lazy stages — an expired clock skips later stages entirely
    # instead of paying their compute, keeping the important prefix.
    # Idea 6: low bank skips straight to trains-only (no moves/builds cost).
    low = state.effort(getattr(state, "clock_budget_ms", None)) == "low"
    for name, fn in _STAGES:
        if low and name != "trains":
            break
        out.extend(fn(state, config))
        if state.should_yield():
            break
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
