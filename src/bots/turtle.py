"""Turtle — fortifier. Trains only when calm, builds close, garrisons."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotState, bot_main, coverage_orders, buzzer_active, drop_dead_notes, defense_train_ok, evac_plan, foe_garrison, order_move, order_march_exact, dispatch_settler, find_build_site, recall_deficit, reinforce_orders, staging_eta, towns_by_train_priority, PEAK_LOW, PEAK_HIGH, tip_safe, respin_tip, maybe_schedule_scout, second_wind, victory_lap, reprint_ok


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

    # T1: threat-responsive threshold. Nearest inbound enemy ETA sets the
    # train bar: 2200 in peace (1600 sleep-light), down to 1200 as
    # contact approaches.
    cap = state.world.faction_capital(faction)
    threat_eta = float("inf")
    for a in state.world.armies:
        if a.faction == faction:
            continue
        for t in own_t:
            d = math.hypot(a.x - t.x, a.y - t.y)
            eta = d / max(1.0, config.army_speed)
            if eta < threat_eta:
                threat_eta = eta
    # per-town threat: a town reacts only to armies coming AT it (cluster
    # lesson: the cap hoards while the exclave delays; global threat made
    # the cap spend on a fight aimed elsewhere).
    any_enemy = any(t.faction != faction for t in state.world.towns)
    # target prediction: an enemy marches at MY town nearest to IT (not
    # nearest to me). Only that town counts the threat — robust to intel
    # delay, unlike reading the army's stated target (arrives too late).
    town_eta: dict[int, float] = {}
    town_inbound: dict[int, int] = {}
    stage = staging_eta(state, config)
    threat_eta = min(threat_eta, min(stage.values(), default=float("inf")))
    for t in own_t:
        best = float("inf")
        n = 0
        for a in state.world.armies:
            if a.faction == faction:
                continue
            nearest = min(own_t, key=lambda u: math.hypot(a.x - u.x, a.y - u.y))
            if nearest.id != t.id:
                continue
            eta = math.hypot(a.x - t.x, a.y - t.y) / max(1.0, config.army_speed)
            if eta < best:
                best = eta
            if eta <= 3:
                n += 1
        # Spend-signal stays army-only (staging moves settlers, never
        # opens the war chest — see inbound_eta). town_eta feeds the
        # muster bars and last-stand; threat_eta above feeds recall/hold.
        town_eta[t.id] = best
        town_inbound[t.id] = n

    # Sleep lightly (2000) only while NO threat is visible anywhere: the
    # danger is then unseen/distant (wake). Once a threat shows, unthreatened
    # towns hoard at 2200 (cluster cap) while threatened ones spend.
    any_threat = any(e <= 10 for e in town_eta.values())

    def town_bar(t) -> int:
        e = town_eta[t.id]
        if e <= 4:
            return 1200
        if e <= 10:
            return 1700
        # Wakes early (r66: turtle hoarded to 2000+, first print t1500,
        # 5 prints/game — fortress, not coma). Sleep-light 1600 in
        # peace; threatened towns spend, hoard cap 2200.
        if any_enemy and not any_threat:
            return 1600
        return 2200

    bar = min((town_bar(t) for t in own_t), default=2200)

    all_calm = all(t.population >= town_bar(t) and not (PEAK_LOW <= t.population <= PEAK_HIGH) for t in own_t) if own_t else False

    # hopeless: home force can't grow before contact (no affordable
    # reinforcement) and is outnumbered — settlers lineage instead of
    # trickling into lost trades.
    threatened = threat_eta != float("inf")
    seen_enemies = sum(1 for a in state.world.armies if a.faction != faction)
    own_armed = len(state.own_armies())
    can_reinforce = False
    if threatened:
        for t in own_t:
            g = state.get_growth(t.id) or 3.0
            if t.population + g * max(0.0, threat_eta) >= min(bar, config.army_cost + 200):
                can_reinforce = True
                break
    hopeless = threatened and not can_reinforce and own_armed <= seen_enemies

    # EVAC (shared drain-and-flee, turtle ENDURES: established stays —
    # fortresses don't abandon towns (they fall!); hopeless musters
    # everything home instead. Flight only when the capital itself is
    # doomed past mustering.)
    _sw = second_wind(state, config)
    if _sw:
        return _sw
    _vl = victory_lap(state, config)
    if _vl:
        return _vl
    # Free-food walk-ins (cheap-suite: turtle scored 3453 vs stub's 5484 —
    # never attacks, not even undefended food. Fresh-empty, close,
    # profitable towns take 1 walker; fortress doctrine otherwise holds).
    _free = [a for a in state.own_armies()
             if not state.army_has_target(a.id) and not a.is_viceroy]
    # Last-guard stays (tk5 lesson: mutual leaves 1, it walks for food,
    # capital falls naked. Walkers need company or an empty home.)
    if len(_free) == 1 and any(math.hypot(_free[0].x - t.x, _free[0].y - t.y) <= 20
                               for t in own_t):
        _free = []
    if _free:
        _best = None
        for u in state.world.towns:
            if u.faction == faction:
                continue
            if foe_garrison(state, u) != 0:
                continue
            if state.turn - state._last_seen.get(("town", u.id), -10**9) > 150:
                continue  # stale empties are traps, not food
            _d = min(math.hypot(a.x - u.x, a.y - u.y) for a in _free)
            if _d > 400:
                continue
            _prize = u.population * (1.0 - config.build_efficiency)
            if _prize < config.army_cost + 200:
                continue
            if _best is None or _prize > _best[0]:
                _best = (_prize, u)
        if _best is not None:
            _walker = min(_free, key=lambda a: math.hypot(a.x - _best[1].x, a.y - _best[1].y))
            out.extend(order_move(state, config, _walker, _best[1].x, _best[1].y))
    _evac = evac_plan(state, config, hopeless, established_stays=True)
    if any(o.startswith("MOVE_CAPITAL") for o in _evac):
        out.extend(_evac)
        return out
    out.extend(_evac)

    # T3: last-stand — a threat imputed to THIS town arriving in <=3 and
    # the town still standing: train whatever is affordable, rules be
    # damned (the town falls anyway; convert pop to force). Fires ONLY
    # when home defenders are strictly outnumbered (D < N): a defender
    # that mutual-saves (1v1) must hold, never gut its own town — the
    # spending kills as surely as the raid (turtle_defend t9 lesson).
    # Deliberately per-town, not global (Step 1 survive floor).
    def _home_count(t) -> int:
        return sum(1 for a in state.own_armies()
                   if math.hypot(a.x - t.x, a.y - t.y) <= config.interact_radius + 10)

    def last_stand(t) -> bool:
        return defense_train_ok(t.population, config.army_cost,
                                config.death_threshold,
                                town_eta.get(t.id, float("inf")),
                                _home_count(t), town_inbound.get(t.id, 0),
                                window=3.0,
                                turns_left=config.max_turns - state.turn)

    # Sub-2200 bars bypass can_train_here (its 2200 conservative bar would
    # veto the whole point of T1/wake); engine-validity only. Eligibility is
    # per-town: only threatened towns spend below 2200.
    # No buzzer strip-mine: self-tax without strikes (shared verdict).
    relaxed_ids = {t.id for t in own_t if town_bar(t) < 2200}
    # peacetime picket: with no threat visible, a single army is enough for
    # an enemy you can't see (stops the t1+t2 double-tap with zero intel).
    # Single-town factions always picket (their only production); multi-town
    # factions hoard until a threat shows (cluster cap).
    # Picket depth (turtle-kill lesson: lone picket mutuals, snipe follows.
    # Rich singletons picket two — mutual leaves one.)
    _rich_single = (len(own_t) <= 1 and own_t and own_t[0].population >= 1500)
    picket_out = any_threat or (len(own_t) <= 1 and len(state.own_armies()) == 0) \
        or (_rich_single and len(state.own_armies()) == 1)
    _force_picket2 = (_rich_single and len(state.own_armies()) == 1
                      and all(t.id not in state._pending_trains for t in own_t))
    if _force_picket2:
        cands = sorted((t for t in own_t
                        if t.population - config.army_cost >= config.death_threshold - 1e-9),
                       key=lambda t: -t.population)[:1]
    elif relaxed_ids and picket_out:
        cands = sorted((t for t in own_t
                        if t.id in relaxed_ids
                        and (last_stand(t)
                             or (t.population >= min(town_bar(t), config.army_cost + 200)
                                 and t.population - config.army_cost >= config.death_threshold - 1e-9))
                        and t.id not in state._pending_trains),
                       key=lambda t: -t.population)
    else:
        cands = list(towns_by_train_priority(state, conservative=True))
    for t in cands:
        if state.should_yield():
            break
        if not _force_picket2:
            if t.id not in relaxed_ids and not all_calm and not state.should_train_for_overcrowding(t):
                continue
            if t.id not in relaxed_ids and t.population < town_bar(t):
                continue
        out.append(f"TRAIN {t.id}")
        state.note_train(t.id)
        break  # one train per turn as per turtle doctrine

    # cap-concentration: outlying towns are delay, not fortresses. Split
    # garrisons measured 1635 vs 2180 concentrated (2v1 wins, 1v1s trade).
    home = [a for a in state.own_armies()
            if any(math.hypot(a.x - t.x, a.y - t.y) <= 20 for t in own_t)] if own_t else []
    # Garrison depth (fortress: 1 in dark, 2 when threatened + rich —
    # deterrence without over-muster (a little greed: armies cost growth).
    _home_cap = sum(1 for a in home
                    if cap is not None and math.hypot(a.x - cap.x, a.y - cap.y) <= 20) \
        if cap is not None else 0
    _want_home = 2 if (threatened and cap is not None and cap.population >= 3000) else 1
    _foe_known = any(t.faction != faction for t in state.world.towns) \
        or any(a.faction != faction for a in state.world.armies)
    # Tall-guard minimum (r96: F4 led tall with 0 guard, beheaded t6865
    # at 12k. Tall needs 1 home ALWAYS, not only when threatened/dark).
    need_garrison = cap is not None and (_home_cap < 1 or (_home_cap < _want_home and (threatened or not _foe_known)))

    # Forward picket (owed): single-town turtle posts one idle army 100km
    # out while the universe is dark (zero foe intel — towns AND armies).
    # The FIRST foe intel (even a town: threat located, tripwire spent)
    # recalls it (muster/concentration need every body); expiry (100 turns
    # silent) rotates it home as guard with no blind re-posting. Posted
    # pickets skip the builds loop below.
    _PICKET_DIST = 100.0
    _PICKET_EXPIRY = 100
    _foe_intel = any(t.faction != faction for t in state.world.towns) \
        or any(a.faction != faction for a in state.world.armies)
    if state._picket is not None:
        _pid, _since = state._picket
        _pa = state.world.get_army(_pid)
        if _pa is None or _pa.faction != faction:
            state._picket = None
        elif _foe_intel or state.turn - _since > _PICKET_EXPIRY:
            _home = min(own_t, key=lambda t: math.hypot(_pa.x - t.x, _pa.y - t.y))
            _orders = order_move(state, config, _pa, _home.x, _home.y)
            if _orders:
                out.extend(_orders)
                state._picket = None
    if state._picket is None and len(own_t) == 1 and not _foe_intel:
        _cands = sorted((a for a in state.own_armies()
                         if not a.is_viceroy and not state.army_has_target(a.id)),
                        key=lambda a: (min(math.hypot(a.x - t.x, a.y - t.y) for t in own_t), a.id))
        if _cands:
            _p = _cands[0]
            # Dark universe: faction-ray (blind guess, either side can be
            # wrong — recall-on-intel bounds the cost to a march).
            _ang = faction * (2 * math.pi / 5)
            _dx, _dy = math.cos(_ang), math.sin(_ang)
            _dist = math.hypot(_dx, _dy) or 1.0
            _wx = min(980.0, max(20.0, own_t[0].x + _dx / _dist * _PICKET_DIST))
            _wy = min(980.0, max(20.0, own_t[0].y + _dy / _dist * _PICKET_DIST))
            _orders = order_move(state, config, _p, _wx, _wy)
            if _orders:
                out.extend(_orders)
                state._picket = (_p.id, state.turn)

    # one builder at a time
    built = False
    # Meeting (Step 3, shared): deficit-threats recall settlers (replaces
    # the old blanket recall — sufficient garrisons let settlers work).
    out.extend(recall_deficit(state, config))
    # Meeting (Step 3 v1): surplus reinforces deficits in time.
    out.extend(reinforce_orders(state, config))
    for p in sorted(state.own_armies(), key=lambda a: min((math.hypot(a.x - t.x, a.y - t.y) for t in own_t), default=0)):
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        if state._picket is not None and p.id == state._picket[0]:
            continue  # posted picket: picket block owns it, never settle it
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            rx, ry = state.reckoned_pos(config, p.id)
            if tgt and math.hypot(rx - tgt[0], ry - tgt[1]) < config.interact_radius + 10:
                # threatened: hold as an army (trades the next wave) instead
                # of disbanding into a town about to be attacked
                if threatened and any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) <= 20 for t in own_t):
                    continue
                own_home = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in own_t)
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
                if not own_home and not reprint_ok(state, config):
                    state._army_targets.pop(p.id, None)
                else:
                    out.append(f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}")
                built = True
            continue
        if need_garrison and cap is not None:
            # closest idle army becomes the garrison instead of a builder
            if math.hypot(p.x - cap.x, p.y - cap.y) > 20:
                out.extend(order_move(state, config, p, cap.x, cap.y))
            need_garrison = False
            built = True
            continue
        if not built and own_t and not buzzer_active(state, config):
            # threatened home armies hold position — never dispatch them out
            if threatened and any(math.hypot(p.x - t.x, p.y - t.y) <= 20 for t in own_t):
                continue
            biggest = max(own_t, key=lambda t: t.population)
            site = find_build_site(state, config, biggest.x, biggest.y, rmin=40, rmax=140, salt=13, who=p.id)
            # Safe-only settle (fortress: sure-safe or not at all — no foe
            # town within 350km of the site, no foe army within 300km of
            # the capital).
            if site is not None and (
                    any(math.hypot(site[0] - t.x, site[1] - t.y) < 350
                        for t in state.world.towns if t.faction != faction)
                    or any(math.hypot(cap.x - a.x, cap.y - a.y) < 300
                           for a in state.world.armies if a.faction != faction)):
                site = None
            if site:
                out.extend(dispatch_settler(state, config, p, site[0], site[1]))
                built = True
        # garrison remainder: idle patrols (doctrine), not home-sit.
        # (coverage_orders batches leftovers below; threatened home
        # armies already continued above.)
        if not built or state.army_has_target(p.id):
            continue
    # Idle patrols last (doctrine: leftovers sweep stalest sectors).
    out.extend(coverage_orders(state, config))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
