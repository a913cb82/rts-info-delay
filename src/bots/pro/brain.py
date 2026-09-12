"""Pro — best-of-all. Situation selector over every tier doctrine."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .intel import *
from .scout import *
from .threat import *
from .raid import *
from .settle import *
from .economy import *


def _pro_hopeless(state: BotState, config: GameConfig, bar: float) -> bool:
    """Port of turtle's hopeless: home force can't grow before contact and
    is outnumbered."""
    faction = state.faction
    own_t = state.own_towns()
    threat_eta = float("inf")
    for a in state.world.armies:
        if a.faction == faction:
            continue
        for t in own_t:
            eta = math.hypot(a.x - t.x, a.y - t.y) / max(1.0, config.army_speed)
            if eta < threat_eta:
                threat_eta = eta
    if threat_eta == float("inf"):
        return False
    reinforce = any(t.population + (state.get_growth(t.id) or 3.0) * threat_eta
                    >= min(bar, config.army_cost + 200) for t in own_t)
    foes = sum(1 for a in state.world.armies if a.faction != faction)
    return not reinforce and len(state.own_armies()) <= foes


def _one_colony(state: BotState, config: GameConfig) -> bool:
    """One-colony compounder (gate push): the pure compounder's capital
    logistic-caps at ~99k; a second town >=150km out (no crowding) adds
    ~90k by t10000 for ~1k of lost compounding. Found ONCE, early,
    far from all towns; never again. Needs: 1 town, affordable
    (>=2500 = floor 1500 + cost), >=4000t left, no settler in flight."""
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
    # One-colony settler FIRST (must fire in void too — the whole
    # compounder game is played without contact; the logistic math does
    # not care, and the old never-train-in-void rule gated it off).
    if _one_colony(state, config):
        cap = state.world.faction_capital(state.faction)
        if cap is not None and cap.id not in state._pending_trains:
            out.append(f"TRAIN {cap.id}")
            state.note_train(cap.id)
            return out
    # P3b: empty-field economy — no foes means nothing to fight or settle
    # against; holding compounds (policy optimum 5254: never train).
    # Pro-only (void settlers need trains in the other bots).
    if not any(t.faction != state.faction for t in state.world.towns) and not any(
            a.faction != state.faction for a in state.world.armies):
        return []
    out.extend(demand_trains(state, config, can_train_standard))
    return out


def _army_targets(state: BotState, config: GameConfig):
    faction = state.faction
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    enemy_armies = [a for a in state.world.armies if a.faction != faction]
    return enemy_towns, enemy_armies


def _stage_moves(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    enemy_towns, enemy_armies = _army_targets(state, config)
    # War-heat inputs (before note_wave_watch overwrites _wave_ids): own
    # deaths this turn = last turn's tracked ids gone (minus builds).
    _cur_ids = {a.id for a in state.own_armies()}
    _died = bool(state._wave_ids
                 and (state._wave_ids - _cur_ids - set(state._pending_builds)))
    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    force = inbound_force(state, config)
    # P6: home defense is duel-only. In multi-faction wars holding one home
    # bleeds pressure and loses slowly (endurance 6424->904); there, all-out.
    war_foes = {t.faction for t in enemy_towns} | {a.faction for a in enemy_armies}
    duel_ctx = len(war_foes) <= 1
    # Siege-mode (fight-heat, not contact): blind bots misread bloodbaths as
    # duels and sit via P2-holds until dead. Fights (own deaths + foe
    # disappearances from my 10km bubbles = engagements resolved) heat;
    # quiet loitering never heats (no bubble contact, nothing vanishes).
    # Heat decays slowly (half-life ~140t): sustained wars stay armed.
    _IR = config.interact_radius
    _near = set()
    for a in state.world.armies:
        if a.faction == state.faction:
            continue
        for u in state.own_towns():
            if abs(a.x - u.x) <= _IR + 1e-9 and abs(a.y - u.y) <= _IR + 1e-9 \
                    and (a.x - u.x) ** 2 + (a.y - u.y) ** 2 <= (_IR + 1e-9) ** 2:
                _near.add(a.id)
                break
        else:
            for q in state.own_armies():
                if abs(a.x - q.x) <= _IR + 1e-9 and abs(a.y - q.y) <= _IR + 1e-9 \
                        and (a.x - q.x) ** 2 + (a.y - q.y) ** 2 <= (_IR + 1e-9) ** 2:
                    _near.add(a.id)
                    break
    _resolved = state._prev_near - _near
    state._prev_near = _near
    if _died or _resolved:
        state._war_heat = min(30.0, state._war_heat + (1.0 if _died else 0.0)
                              + min(3.0, float(len(_resolved))))
    else:
        state._war_heat *= 0.995
    siege = duel_ctx and state._war_heat >= 5.0
    # Hold rule (Step 2, shared): per threatened town keep min(home, N+1).
    held: set[int] = hold_defenders(state, config, force) if duel_ctx else set()
    sel = raid_target(state, config, priced=duel_ctx)
    # Pack gate: an unaffordable-but-valuable target builds (trains fire),
    # it doesn't march — undersized packs donate. Idle armies hold as the
    # growing pack.
    free_n = sum(1 for a in state.own_armies()
                 if not state.army_has_target(a.id) and a.id not in held)
    pack_building = sel is not None and sel[1] > free_n
    # Probe in force: pack-building vs visibly-empty (S==0) still sends
    # the first NEARBY free army (recon by fire — bounded risk, gains
    # intel + takes vs passive; prints observed calibrate the follow-on).
    # Far unknowns hold for the pack (no 600km donations into printers).
    probe_armed = pack_building and sel[2] == 0
    probe_sent = False
    probe_reach = 6.0 * max(1.0, config.army_speed)
    probe_tgt = sel[0] if probe_armed else None
    for p in state.own_armies():
        if state.should_yield():
            break
        if state.army_has_target(p.id):
            continue  # handled by the builds stage
        if p.id in held:
            continue
        # One-colony march: the printed settler founds the second town
        # >=160km out before any raid/pack logic can poach it.
        if _one_colony(state, config):
            site = find_build_site(state, config, p.x, p.y,
                                   rmin=160, rmax=300, salt=11, who=p.id)
            if site is not None:
                out.extend(order_move(state, config, p, site[0], site[1]))
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
            # Siege release: persistent-fight duels are bloodbaths the bot
            # can't see (intel shows one foe). Hold-everything then dies
            # slowly; surplus marches via normal gates (held-set keeps N+1).
            if duel and not siege and enemy_armies and not spent:
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
            # Pack-only interceptions (D2 fix): never march a lone army
            # to meet a known foe army — 1v1 mutuals waste 1000 pop AND
            # strip the capital naked for the single-raider take. Solos
            # hold (garrison); field meetings are 2v1+ via the raid pack
            # (sel branch) or not at all. (Foe scouts roam free — accepted;
            # killing one costs the guard that the pack then needs.)
            continue
        else:
            # G2: settle on demand only (same gate as trains: void merit
            # or contested payback) — else recycle home for +500 pop-add,
            # but ONLY in true peace: marching home under known threat
            # just delivers defenders to the builds-merge (guard_duty t31).
            # In war-footing the army holds position (staying is the order).
            site = find_build_site(state, config, p.x, p.y, rmin=80, rmax=300, salt=11, who=p.id) \
                if expansion_demand(state, config, void_horizon=500) else None
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
        if state.has_pending_build(p.id):
            continue
        tgt = state.army_target(p.id)
        if tgt is None:
            continue
        is_enemy_target = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in enemy_towns)
        if not is_enemy_target and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
            # War-footing: a home-bound army holds as a defender, never
            # merges — disbanding into +500 under known threat throws the
            # defense away (guard_duty t31). Peace merges as before.
            foe_known = bool(enemy_towns) or any(
                a.faction != faction for a in state.world.armies)
            own_home = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20
                           for t in state.world.towns if t.faction == faction)
            if foe_known and own_home:
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
