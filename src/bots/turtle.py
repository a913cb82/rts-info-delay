"""Turtle — fortifier. Trains only when calm, builds close, garrisons."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotState, bot_main, find_build_site, towns_by_train_priority, PEAK_LOW, PEAK_HIGH


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out
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
    for t in own_t:
        best = float("inf")
        for a in state.world.armies:
            if a.faction == faction:
                continue
            nearest = min(own_t, key=lambda u: math.hypot(a.x - u.x, a.y - u.y))
            if nearest.id != t.id:
                continue
            eta = math.hypot(a.x - t.x, a.y - t.y) / max(1.0, config.army_speed)
            if eta < best:
                best = eta
        town_eta[t.id] = best

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
        if any_enemy and not any_threat:
            return 2000
        return 2600

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

    # T3: last-stand — enemy at the gates and town still standing:
    # train whatever is affordable, rules be damned.
    doomed = threat_eta <= 3 and any(t.population >= config.army_cost + 200 for t in own_t)

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
                        and t.population >= min(town_bar(t), config.army_cost + 200)
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
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {cap.x:.1f} {cap.y:.1f}")
            state.note_move(p.id, cap.x, cap.y)
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
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {cap.x:.1f} {cap.y:.1f}")
            need_garrison = False
            built = True
            continue
        if not built and own_t:
            # threatened home armies hold position — never dispatch them out
            if threatened and any(math.hypot(p.x - t.x, p.y - t.y) <= 20 for t in own_t):
                continue
            biggest = max(own_t, key=lambda t: t.population)
            site = find_build_site(state, config, biggest.x, biggest.y, rmin=40, rmax=140, salt=13)
            if site:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {site[0]:.1f} {site[1]:.1f}")
                built = True
        # garrison remainder
        if not built or state.army_has_target(p.id):
            continue
        if own_t:
            nearest = min(own_t, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
            if math.hypot(p.x - nearest.x, p.y - nearest.y) > 20:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
