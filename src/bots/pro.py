"""Pro — best-of-all. Situation selector over every tier doctrine."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, bot_main, can_train_standard, defense_train_ok, demand_trains, drive_scout, drop_dead_notes, expansion_demand, hold_defenders, inbound_force, jit_ready, maybe_assign_scout, order_move, find_build_site, inbound_eta, note_wave_watch, raid_target, recall_deficit, reinforce_orders, should_hold_home, site_pays


def _pro_hopeless(state: BotState, config: GameConfig, bar: float) -> bool:
    """D<N hopelessness (Step 5): the worst inbound threat cannot be met
    even printing everything printable-in-time (1/town/turn TRAIN cap) —
    pop affordability is necessary but not sufficient (a reinforcement
    that still loses is a donation). Established empires almost never
    qualify (deep print); young ones do."""
    faction = state.faction
    own_t = state.own_towns()
    if not own_t:
        return False
    force = inbound_force(state, config, max_eta=8.0)
    if not force:
        return False
    tid, (eta, n) = min(force.items(), key=lambda kv: kv[1][0])
    town = next(t for t in own_t if t.id == tid)
    home = sum(1 for a in state.own_armies()
               if math.hypot(a.x - town.x, a.y - town.y) <= 20.0)
    eta_turns = max(0, int(math.ceil(eta)))
    printable = sum(eta_turns for t in own_t
                    if t.population >= config.army_cost)
    return home + printable < n


def _stage_trains(state: BotState, config: GameConfig) -> list[str]:
    # P3b: empty-field economy — no foes means nothing to fight or settle
    # against; holding compounds (policy optimum 5254: never train).
    # Pro-only (void settlers need trains in the other bots). Recon
    # exception: exactly one prober (intel has option value; pairs with
    # S0 below — without it pro is blind forever) — but never spending
    # the lineage seed (succession: prober at 1500 floor-locks the town;
    # settle first, scout second when poor).
    if not any(t.faction != state.faction for t in state.world.towns) and not any(
            a.faction != state.faction for a in state.world.armies):
        if not state.own_armies():
            for t in state.own_towns():
                if can_train_standard(state, t) and t.population >= 2500 \
                        and t.population - config.army_cost >= config.death_threshold - 1e-9:
                    return [f"TRAIN {t.id}"]
        return []
    return demand_trains(state, config, can_train_standard)


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
    # P6: home defense is duel-only. In multi-faction wars holding one home
    # bleeds pressure and loses slowly (endurance 6424->904); there, all-out.
    war_foes = {t.faction for t in enemy_towns} | {a.faction for a in enemy_armies}
    duel_ctx = len(war_foes) <= 1
    # Hold rule (Step 2, shared): per threatened town keep min(home, N+1).
    held: set[int] = hold_defenders(state, config, force) if duel_ctx else set()
    sel = raid_target(state, config, priced=duel_ctx)
    # Pack gate: an unaffordable-but-valuable target builds (trains fire),
    # it doesn't march — undersized packs donate. Idle armies hold as the
    # growing pack.
    free_ids = [a.id for a in state.own_armies()
                if not state.army_has_target(a.id) and a.id not in held]
    free_n = len(free_ids)
    pack_building = sel is not None and sel[1] > free_n \
        and not jit_ready(state, config, sel[0], sel[1], free_ids)
    # Probe in force: pack-building vs visibly-empty (S==0) still sends
    # ONE nearby free army (recon by fire — bounded risk, gains intel +
    # takes vs passive; prints observed calibrate the follow-on). One
    # means one: a probe already en route suppresses duplicates (per-turn
    # flags trickle-donate into garrisoning foes — endgame lesson).
    # Far unknowns hold for the pack (no 600km donations into printers).
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
    # Meeting (Step 3): deficit-threats recall settlers first (bodies
    # home before tasking; recalled notes route via builds to guards).
    out.extend(recall_deficit(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
    for p in state.own_armies():
        if state.should_yield():
            break
        # Recon (owed): a marked scout is driven, never tasked otherwise.
        sc = drive_scout(state, config, p)
        if sc is not None:
            out.extend(sc)
            continue
        if state.army_has_target(p.id):
            continue  # handled by the builds stage
        if p.id in held:
            continue
        # G-defense (duel-only per P6): second-wave watch still holds one.
        if duel_ctx and should_hold_home(state, config, p, inbound, hold_second):
            continue
        if pack_building:
            if not probe_armed or probe_sent or probe_tgt is None or \
                    math.hypot(p.x - probe_tgt.x, p.y - probe_tgt.y) > probe_reach:
                continue  # pack not ready: hold (trains are building it)
            probe_sent = True
        if sel is not None:
            nearest, need, _ = sel
            # P1: leader-targeting (A3) + departure-sync (A2) on the greedy base.
            fscore: dict[int, float] = {}
            for t in state.world.towns:
                fscore[t.faction] = fscore.get(t.faction, 0.0) + t.population
            for a in state.world.armies:
                fscore[a.faction] = fscore.get(a.faction, 0.0) + 1000.0
            # P2: counter-punch vs peers+ — hold everything while the foe
            # has field armies (they attack into our 2v1 and die clean),
            # then counter with the pack when the field is empty.
            # (Marching the pack out naked lost the race 2245->1647.)
            my_score = fscore.get(state.faction, 0.0)
            foe_score = fscore.get(nearest.faction, 0.0)
            peer = foe_score >= 0.7 * my_score
            # P5: rope-a-dope is DUEL-only (1 foe faction, <=2 foe towns).
            # In big wars it deadlocks (release never fires) and passivity
            # loses slowly (attrition 4226->1900); there, departure-sync.
            foe_factions = {t.faction for t in enemy_towns} | {a.faction for a in enemy_armies}
            foe_town_count = sum(1 for t in enemy_towns if t.faction == nearest.faction)
            duel = peer and len(foe_factions) == 1 and foe_town_count <= 2
            # P3a: counter-release — pack marches when the field is empty
            # OR the target faction is spent (<0.5x, bled on our 2v1).
            # (3-pack forced marches re-lost the home race 3249->1647;
            # evac saves the commander, not the score. Rope stays.)
            spent = foe_score < 0.5 * my_score and len(state.own_armies()) >= 2
            if duel and enemy_armies and not spent:
                continue  # rope-a-dope: let them come
            if not duel:
                # Big wars: pure pressure (old-greedy style). ANY hold here
                # cedes initiative and dies slowly (endurance lessons); the
                # duel doctrine above stays gated. March.
                pass
            if peer and len(state.own_armies()) < 2:
                home = min(state.own_towns(), key=lambda t: math.hypot(t.x - p.x, t.y - p.y), default=None)
                if home is not None and home.population >= 2 * config.army_cost:
                    continue  # solo vs peer with empty field: wait for pack
            out.extend(order_move(state, config, p, nearest.x, nearest.y))
        elif enemy_armies:
            fc = BotForecast(state, config)
            forecast = [(fc.forecast_army_pos(e), e) for e in enemy_armies]
            (fx, fy), _ = min(forecast, key=lambda x: math.hypot(x[0][0] - p.x, x[0][1] - p.y))
            out.extend(order_move(state, config, p, fx, fy))
        else:
            # Recon first (S0): probe deep before founding; falls back to
            # settling below.
            if maybe_assign_scout(state, config, p):
                out.extend(drive_scout(state, config, p) or [])
                continue
            # G2: settle on demand only (same gate as trains: void merit
            # or contested payback) — else recycle home for +500 pop-add,
            # but ONLY in true peace: marching home under known threat
            # just delivers defenders to the builds-merge (guard_duty t31).
            # In war-footing the army holds position (staying is the order).
            site = find_build_site(state, config, p.x, p.y, rmin=80, rmax=300, salt=11, who=p.id) \
                if expansion_demand(state, config) else None
            # Site veto (fratricide): even a demanded colony must clear
            # growth>margin at its site (shared empty_3000 lesson).
            if site is not None and not site_pays(state, config, site[0], site[1]):
                site = None
            if site:
                out.extend(order_move(state, config, p, site[0], site[1]))
            elif state.own_towns():
                foe_known = any(t.faction != state.faction for t in state.world.towns) \
                    or any(a.faction != state.faction for a in state.world.armies)
                if not foe_known:
                    home = min(state.own_towns(), key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
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
            # War-footing: a home-bound army holds as a defender, never
            # merges — disbanding into +500 under known threat throws the
            # defense away (guard_duty t31). Merges need TRUE void
            # (never-seen): eviction-flicker (seen, stale) must not read
            # as peace (endgame merge-cycle). Peace merges as before.
            own_home = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20
                           for t in state.world.towns if t.faction == faction)
            if state._foe_first_seen and own_home:
                continue
            # Merge horizon (recycle treadmill): home-capital merges are
            # -500 now for compounding later — hold on short horizons
            # (standing armies beat treadmill merges; recycle lesson).
            cap = state.world.faction_capital(faction)
            _max_turns = getattr(config, "max_turns", 3000) or 3000
            if own_home and cap is not None and math.hypot(tgt[0] - cap.x, tgt[1] - cap.y) < 20 \
                    and _max_turns - state.turn < 500:
                continue
            # Suppressed arrivals (Step 4 lite): a void-site founding whose
            # purpose lapsed (foe history since dispatch, demand dead now)
            # re-decides instead of gifting hostages (pro_defense t10:
            # founded into a raid, captured t12). True-void foundings
            # (capability contract) always fire.
            if not own_home and state._foe_first_seen and not expansion_demand(
                    state, config):
                state._army_targets.pop(p.id, None)
                continue
            # Arrival site re-check (crowding shifts en route): fratricide
            # veto even for kept notes (true-void crowded own-colonies too).
            if not own_home and not site_pays(state, config, tgt[0], tgt[1]):
                state._army_targets.pop(p.id, None)
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
    # P4: evac (turtle doctrine) — hopeless + 2x cost: fly the commander
    # out to coords away from the threat. Covers naked-home 3-pack marches.
    cap = state.world.faction_capital(state.faction)
    evacuating = any(a.faction == state.faction and a.is_viceroy for a in state.world.armies)
    if cap is not None and not evacuating and cap.population >= 2 * config.army_cost \
            and _pro_hopeless(state, config, 1700):
        foes = [a for a in state.world.armies if a.faction != state.faction]
        if foes:
            fx = sum(a.x for a in foes) / len(foes)
            fy = sum(a.y for a in foes) / len(foes)
            dx, dy = cap.x - fx, cap.y - fy
            dist = math.hypot(dx, dy) or 1.0
            ex = min(980.0, max(20.0, cap.x + dx / dist * 250.0))
            ey = min(980.0, max(20.0, cap.y + dy / dist * 250.0))
            return [f"MOVE_CAPITAL {ex:.1f} {ey:.1f}"]
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
