"""Pro — best-of-all. Situation selector over every tier doctrine."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, bot_main, coverage_orders, can_train_standard, defense_train_ok, demand_trains, drive_scout, drop_dead_notes, en_route, evac_plan, expansion_demand, hold_defenders, war_print_need, inbound_force, jit_ready, maybe_assign_scout, order_move, order_march_exact, dispatch_settler, find_build_site, inbound_eta, note_wave_watch, drive_mapper, mapper_hop_target, MAPPER_MAX, _dark, probe_ok, raid_target, raid_targets, recall_deficit, reinforce_orders, should_hold_home, site_pays, strike_target, stay_behind_hold, tip_safe, respin_tip, maybe_schedule_scout, pack_print


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


def _one_colony(state: BotState, config: GameConfig) -> bool:
    """One-colony compounder (gate win, ported): the pure compounder's
    capital logistic-caps at ~99k; a second town >=150km out (no
    crowding) adds ~90k by t10000 for ~1k of lost compounding. Found
    ONCE, early; needs 1 town, >=2500 pop, >=4000t left, no settler out."""
    own_t = state.own_towns()
    if len(own_t) != 1:
        return False
    turns_left = (getattr(config, "max_turns", 10000) or 10000) - state.turn
    if turns_left < 4000:
        return False
    cap = state.world.faction_capital(state.faction)
    if cap is None:
        return False
    floor = config.army_cost + config.death_threshold
    if cap.population < floor + config.army_cost:
        return False
    for a in state.own_armies():
        tgt = state.army_target(a.id)
        if tgt is not None and all(
                math.hypot(tgt[0] - t.x, tgt[1] - t.y) > 20 for t in own_t):
            return False  # settler already marching
    return True


def _stage_trains(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    if _one_colony(state, config):
        cap = state.world.faction_capital(state.faction)
        if cap is not None and cap.id not in state._pending_trains:
            out.append(f"TRAIN {cap.id}")
            state.note_train(cap.id)
            return out
    # P3b: empty-field economy — no foes means nothing to fight or settle
    # against; holding compounds (policy optimum 5254: never train).
    # Pro-only (void settlers need trains in the other bots). Recon
    # exception: exactly one prober (intel has option value; pairs with
    # S0 below — without it pro is blind forever). Survivable floor
    # (pop-cost >= death threshold, ~1500): the 2500 floor poverty-
    # trapped r47 (capital 500-1400 all game, zero prints, blind and
    # poor forever). No early return either — demand's void branch
    # settles the dark (settlers observe en route; economy first).
    if not any(t.faction != state.faction for t in state.world.towns) and not any(
            a.faction != state.faction for a in state.world.armies):
        if not state.own_armies():
            for t in state.own_towns():
                if can_train_standard(state, t) \
                        and t.population - config.army_cost >= config.death_threshold - 1e-9:
                    return [f"TRAIN {t.id}"]
        # (fall through: demand's void branch settles dark fields)
    out = demand_trains(state, config, can_train_standard)
    # Scout-print (r31 lesson): blind + scoutless + affordable -> print
    # eyes (darkness re-arms scouting, but prints must fund it; the S0
    # prober only covers true void, not post-contact blindness).
    if not out and _dark(state) and state._scout_id is None \
            and getattr(state, "_scout_id2", None) is None \
            and not state.__dict__.get("_mapper") and not state._pending_trains:
        cands = sorted((t for t in state.own_towns()
                        if can_train_standard(state, t)
                        and t.population - config.army_cost >= config.death_threshold - 1e-9),
                       key=lambda t: -t.population)
        if cands:
            out.append(f"TRAIN {cands[0].id}")
            state.note_train(cands[0].id)
    return out


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
    sels = raid_targets(state, config, 3, priced=duel_ctx) if sel is not None else []
    marched: dict[int, int] = {}  # target town id -> packet size sent
    packets: dict = {}  # tgt id -> (tgt, need, [army ids]) JIT flush
    _sk = strike_target(state, config)
    sk_march = _sk if _sk is not None and not enemy_armies else None
    # Pack gate: an unaffordable-but-valuable target builds (trains fire),
    # it doesn't march — undersized packs donate. Idle armies hold as the
    # growing pack.
    free_ids = [a.id for a in state.own_armies()
                if not state.army_has_target(a.id) and a.id not in held]
    free_n = len(free_ids)
    pack_building = sel is not None and sel[1] > free_n \
        and not jit_ready(state, config, sel[0], sel[1], free_ids,
        sel[0].faction)
    # Pack-driven print (shared): shortfall with nothing printing funds it.
    out.extend(pack_print(state, config, sel, free_n, can_train_standard))
    # Probe in force: pack-building vs visibly-empty (S==0) still sends
    # ONE nearby free army (recon by fire — bounded risk, gains intel +
    # takes vs passive; prints observed calibrate the follow-on). One
    # means one: a probe already en route suppresses duplicates (per-turn
    # flags trickle-donate into garrisoning foes — endgame lesson).
    # Far unknowns hold for the pack (no 600km donations into printers).
    probe_armed = pack_building and probe_ok(state, sel)
    probe_tgt = sel[0] if probe_armed else None
    probe_reach = 6.0 * max(1.0, config.army_speed)
    # Meeting (Step 3): deficit-threats recall settlers first (bodies
    # home before tasking; recalled notes route via builds to guards).
    out.extend(recall_deficit(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
    fc_chase = BotForecast(state, config)
    for p in state.own_armies():
        if state.should_yield():
            break
        # Recon (owed): a marked scout is driven, never tasked otherwise.
        sc = drive_scout(state, config, p)
        if sc is not None:
            out.extend(sc)
            continue
        mp = drive_mapper(state, config, p)
        if mp is not None:
            out.extend(mp)
            continue
        if state.army_has_target(p.id):
            continue  # handled by the builds stage
        if p.id in held:
            continue
        # One-colony march (see _one_colony): found before raid logic.
        if _one_colony(state, config):
            site = find_build_site(state, config, p.x, p.y,
                                   rmin=160, rmax=300, salt=11, who=p.id)
            if site is not None:
                out.extend(order_move(state, config, p, site[0], site[1]))
                continue
        # G-defense (duel-only per P6): second-wave watch still holds one.
        if duel_ctx and should_hold_home(state, config, p, inbound, hold_second):
            continue
        # Stay-behind vs live threat (shared): last home guard holds.
        if stay_behind_hold(state, config, p, force):
            continue
        # Strike (windows close!): clear-field blitz/buzzer takes march
        # immediately (mass) — unless one is already en route (per-target
        # singularity: notes are live, no flags). Fielded foes route to
        # rope/sel below.
        if sk_march is not None and not en_route(state, sk_march[0].x, sk_march[0].y):
            out.extend(order_move(state, config, p, sk_march[0].x, sk_march[0].y))
            continue
        if pack_building:
            if not probe_armed or probe_tgt is None \
                    or en_route(state, probe_tgt.x, probe_tgt.y) \
                    or math.hypot(p.x - probe_tgt.x, p.y - probe_tgt.y) > probe_reach:
                continue  # pack not ready: hold (trains are building it)
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
            packeted = False
            for tgt, tneed, _ in [(nearest, need, None)] + [(u, n, s) for (u, n, s) in sels if u.id != nearest.id]:
                if marched.get(tgt.id, 0) >= tneed:
                    continue
                if tgt.id != nearest.id and en_route(state, tgt.x, tgt.y):
                    continue
                # JIT packets: collect (don't emit); only full packets
                # march post-loop (partials trickle and die in detail —
                # pro t7000-9000 bled 29->3 in piecemeal mutuals/solos).
                packets.setdefault(tgt.id, (tgt, tneed, []))[2].append(p.id)
                marched[tgt.id] = marched.get(tgt.id, 0) + 1
                packeted = True
                break
            if packeted:
                continue
            continue  # surplus past all needs holds (no over-muster)
        elif enemy_armies:
            forecast = [(fc_chase.forecast_army_pos(e), e) for e in enemy_armies]
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
            if site is not None and not war_print_need(state, config) \
                    and not site_pays(state, config, site[0], site[1]):
                site = None
            if site:
                out.extend(dispatch_settler(state, config, p, site[0], site[1]))
            elif state.own_towns():
                foe_known = any(t.faction != state.faction for t in state.world.towns) \
                    or any(a.faction != state.faction for a in state.world.armies)
                if not foe_known:
                    home = min(state.own_towns(), key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
                    out.extend(order_move(state, config, p, home.x, home.y))
    # JIT packet flush: only full packets march (partials hold for next
    # turn's recompute — trickling dies in detail).
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
        rx, ry = state.reckoned_pos(config, p.id)
        # Arrival-treadmill release (r17 lesson): a FIELD army arrived at
        # its note >30 turns with nothing resolving (no BUILD, no battle,
        # no capture — ghost notes on dead towns, quiescence-locked
        # respins) drops the note and re-decides next turn. Home guards
        # exempt (holding is their job). 6-stack haunted rubble 3000t.
        if math.hypot(rx - tgt[0], ry - tgt[1]) < config.interact_radius + 10:
            own_home = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20
                           for t in state.world.towns if t.faction == faction)
            if not own_home:
                holds = state.__dict__.setdefault("_arr_hold", {})
                holds[p.id] = holds.get(p.id, 0) + 1
                if holds[p.id] > 30:
                    holds.pop(p.id, None)
                    state._army_targets.pop(p.id, None)
                    # Mapper release (not bare pop — bare pops re-note the
                    # same deterministic tip and re-lock): freed field
                    # armies map the dark (post-contact scouting) instead.
                    if len(state.__dict__.get("_mapper", {})) < MAPPER_MAX:
                        state.__dict__.setdefault("_mapper", {})[p.id] = 0
                        out.extend(order_move(state, config, p,
                                              *mapper_hop_target(state, config, p)))
                    else:
                        # Mapper cap full: bare-pop anyway (re-decide beats
                        # haunting; the next freed army maps instead).
                        state._army_targets.pop(p.id, None)
                    continue
        else:
            state.__dict__.get("_arr_hold", {}).pop(p.id, None)
        if not is_enemy_target and math.hypot(rx - tgt[0], ry - tgt[1]) < config.interact_radius + 10:
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
            # Foe-gate (both founding paths): guns-hot tips recycle
            # home instead of founding (void tips found at any distance).
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
    _sched = maybe_schedule_scout(state, config)
    sc_out = list(_sched) if _sched else []
    out.extend(sc_out)
    # P4: evac (shared drain-and-flee, computed: endure established).
    # Covers naked-home 3-pack marches.
    _evac = evac_plan(state, config, _pro_hopeless(state, config, 1700),
                      established_stays=True)
    if any(o.startswith("MOVE_CAPITAL") for o in _evac):
        return _evac
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
