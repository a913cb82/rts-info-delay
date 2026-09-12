"""Turtle — fortifier. Trains only when calm, builds close, garrisons."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .core import BotState, bot_main, drop_dead_notes, defense_train_ok, order_move, find_build_site, staging_eta, towns_by_train_priority, PEAK_LOW, PEAK_HIGH


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out
    drop_dead_notes(state)  # unstrand armies whose orders died in flight
    own_t = state.own_towns()

    # T1: threat-responsive threshold. Nearest inbound enemy ETA sets the
    # train bar: 2600 in peace, down to 1200 as contact approaches.
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
    # towns hoard at 2600 (cluster cap) while threatened ones spend.
    any_threat = any(e <= 10 for e in town_eta.values())

    def town_bar(t) -> int:
        e = town_eta[t.id]
        if e <= 4:
            return 1200
        if e <= 10:
            return 1700
        # Deep sleep (turtle scored 10-20k because peace-time prints at
        # 2000/2600 kept towns hovering near the bar — pop IS the tall
        # score). Rich before printing: compounding towns convert raiders
        # for free (the compounder's survival trick); poor ones die.
        if any_enemy and not any_threat:
            return 5000
        return 7000

    bar = min((town_bar(t) for t in own_t), default=2600)

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

    # EVAC: doomed capital + 1000 pop + no viceroy airborne — fly the
    # commander out to coords AWAY from the threat. The viceroy founds a new
    # capital on arrival; a faction with a viceroy in flight survives the old
    # capital's fall. Needs no existing town (founds one).
    evacuating = any(a.faction == faction and a.is_viceroy for a in state.world.armies)
    # evac needs 2x cost: the viceroy takes 1000 and the old town must stay
    # above the death floor (suicide-evacs at ~1000 killed the cap for
    # nothing — wake lesson vs synced raiders).
    if cap is not None and not evacuating and hopeless and cap.population >= 2 * config.army_cost:
        foes = [a for a in state.world.armies if a.faction != faction]
        if foes:
            fx = sum(a.x for a in foes) / len(foes)
            fy = sum(a.y for a in foes) / len(foes)
            dx, dy = cap.x - fx, cap.y - fy
            dist = math.hypot(dx, dy) or 1.0
            ex = min(980.0, max(20.0, cap.x + dx / dist * 250.0))
            ey = min(980.0, max(20.0, cap.y + dy / dist * 250.0))
            out.append(f"MOVE_CAPITAL {ex:.1f} {ey:.1f}")
            return out

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
                                window=3.0)

    # Sub-2600 bars bypass can_train_here (its 2600 conservative bar would
    # veto the whole point of T1/wake); engine-validity only. Eligibility is
    # per-town: only threatened towns spend below 2600.
    threatened = threat_eta <= 10
    relaxed_ids = {t.id for t in own_t if town_bar(t) < 2600}
    # peacetime picket: with no threat visible, a single army is enough for
    # an enemy you can't see (stops the t1+t2 double-tap with zero intel).
    # Single-town factions always picket (their only production); multi-town
    # factions hoard until a threat shows (cluster cap).
    picket_out = any_threat or (len(own_t) <= 1 and len(state.own_armies()) == 0)
    if relaxed_ids and picket_out:
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
    need_garrison = threatened and not home and cap is not None

    # one builder at a time
    built = False
    for p in sorted(state.own_armies(), key=lambda a: min((math.hypot(a.x - t.x, a.y - t.y) for t in own_t), default=0)):
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        # recall first: threatened settlers abort and come home (2v1 beats
        # waves, 1v1 only trades — every home army counts). Skipped when
        # hopeless: the settler lineages instead.
        if threatened and not hopeless and cap is not None and state.army_has_target(p.id) and not state.has_pending_build(p.id):
            out.extend(order_move(state, config, p, cap.x, cap.y))
            continue
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            if tgt and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
                # threatened: hold as an army (trades the next wave) instead
                # of disbanding into a town about to be attacked
                if threatened and any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) <= 20 for t in own_t):
                    continue
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
        if not built and own_t:
            # threatened home armies hold position — never dispatch them out
            if threatened and any(math.hypot(p.x - t.x, p.y - t.y) <= 20 for t in own_t):
                continue
            biggest = max(own_t, key=lambda t: t.population)
            # Spacing (turtle was its own worst neighbour: satellites
            # at 40-140km sit inside the 150km crowding radius, taxing
            # BOTH towns' growth — and growth IS the tall score).
            # Still tall, still calm-only: just far enough to compound
            # independently.
            # Count-cap-3-maintain (anti-sprawl-stunt): stop founding at 3
            # towns (maintain 3, refill losses below it). Beyond 3 spreads thin
            # (more mouths, same pop -> stunt at 10k, outscored 3rd-4th). At 3,
            # freed pop compounds EXISTING to 60k+ (180k total beats 150k pro;
            # narrow quality wins -> mu 60+). Still fortress (few spaced guarded).
            site = None
            if len(own_t) < 3:
                site = find_build_site(state, config, biggest.x, biggest.y, rmin=180, rmax=320, salt=13, who=p.id)
            if site:
                out.extend(order_move(state, config, p, site[0], site[1]))
                built = True
        # garrison remainder
        if not built or state.army_has_target(p.id):
            continue
        if own_t:
            nearest = min(own_t, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
            if math.hypot(p.x - nearest.x, p.y - nearest.y) > 20:
                out.extend(order_move(state, config, p, nearest.x, nearest.y))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
