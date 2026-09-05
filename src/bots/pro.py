"""Pro — best-of-all. Situation selector over every tier doctrine."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, bot_main, defense_train_ok, drop_dead_notes, inbound_force, order_move, find_build_site, inbound_eta, note_wave_watch, should_hold_home


def _home_count(state: BotState, t) -> int:
    return sum(1 for a in state.own_armies()
               if math.hypot(a.x - t.x, a.y - t.y) <= 20.0)


def _foe_garrison(state: BotState, u) -> int:
    """Standing defenders imputed to foe town u (nearest same-faction town)."""
    n = 0
    for a in state.world.armies:
        if a.faction == state.faction or a.faction != u.faction:
            continue
        same = [t for t in state.world.towns if t.faction == u.faction]
        if min(same, key=lambda t: math.hypot(a.x - t.x, a.y - t.y)).id == u.id:
            n += 1
    return n


def _raid_target(state: BotState, config: GameConfig, priced: bool = True):
    """Priced raid target (unready-weighted) + required force, or None.

    Take needs N >= S+W+1 (standing + printable-before-arrival); the prize
    must clear a risk premium (theft pays — the army isn't spent, only
    risked, so cost*N is not subtracted). Unpriced (big-war denial)
    returns the max-pressure target regardless of affordability."""
    faction = state.faction
    eff = config.build_efficiency
    cost = config.army_cost
    floor = config.death_threshold
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    war_foes = {t.faction for t in enemy_towns} | {
        a.faction for a in state.world.armies if a.faction != faction}
    duel_ctx = len(war_foes) <= 1
    if duel_ctx:
        cands = [t for t in enemy_towns
                 if t.population * (1.0 - eff) > cost * eff + 200]
    else:
        cands = list(enemy_towns)
    if not cands:
        return None
    fieldable = [a for a in state.own_armies()
                 if not state.army_has_target(a.id)]
    reach = min((math.hypot(a.x - u.x, a.y - u.y)
                 for a in fieldable for u in cands),
                default=float("inf"))
    best = None
    for u in cands:
        s = _foe_garrison(state, u)
        printable = max(0.0, (u.population - cost - floor) / cost)
        arrival_t = min((math.hypot(a.x - u.x, a.y - u.y)
                         for a in fieldable),
                        default=float("inf")) / max(1.0, config.army_speed)
        w = min(printable, arrival_t)
        need = int(s + w + 1)
        prize = u.population * (1.0 - eff)
        dist = min((math.hypot(a.x - u.x, a.y - u.y) for a in fieldable),
                   default=float("inf"))
        if not priced:
            score = u.population / (1.0 + dist / 300.0)
            if best is None or score > best[0]:
                best = (score, u, need)
        elif need <= len(fieldable) and prize > 200:
            score = prize / (1.0 + dist / 300.0) / (1.0 + s + w)
            if best is None or score > best[0]:
                best = (score, u, need)
    if best is None:
        return None
    return best[1], best[2]


def _void_note_busy(state: BotState) -> bool:
    """An expansion is already in flight (a note to nowhere-known)."""
    towns = list(state.world.towns)
    for a in state.own_armies():
        tgt = state.army_target(a.id)
        if tgt and all(math.hypot(tgt[0] - t.x, tgt[1] - t.y) > 20
                       for t in towns):
            return True
    return False


def _can_train_pro(state: BotState, town) -> bool:
    if town.population < 1500 or town.population > 90000:
        return False
    if town.id in state._pending_trains and state.turn <= state._pending_trains[town.id]:
        return False
    cap = state.world.faction_capital(state.faction)
    if cap:
        dist = math.hypot(cap.x - town.x, cap.y - town.y)
        if dist > 100 and town.population < 1500 + int(dist / 150 * 400):
            return False
    return True


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


def _expansion_demand(state: BotState, config: GameConfig) -> bool:
    """Settler pipeline demand: void (no known foes) expands on logistic
    merit while no expansion is in flight; contested expands only past
    the payback bar (1e8/P turns) — darkness shields growers, contest
    prices expansion. The buzzer falls out (turns_left -> 0 kills demand)."""
    if _void_note_busy(state):
        return False
    foe_known = any(t.faction != state.faction for t in state.world.towns) \
        or any(a.faction != state.faction for a in state.world.armies)
    if not foe_known:
        return True
    turns_left = config.max_turns - state.turn
    payers = [t.population for t in state.own_towns()]
    return bool(payers) and turns_left >= 1e8 / max(payers)


def _stage_trains(state: BotState, config: GameConfig) -> list[str]:
    # P3b: empty-field economy — no foes means nothing to fight or settle
    # against; holding compounds (policy optimum 5254: never train).
    if not any(t.faction != state.faction for t in state.world.towns) and not any(
            a.faction != state.faction for a in state.world.armies):
        return []
    out: list[str] = []
    cost = config.army_cost
    floor = config.death_threshold
    force = inbound_force(state, config)
    home = {t.id: _home_count(state, t) for t in state.own_towns()}
    # Raid pipeline: pack deficit for the priced target (trains are
    # fungible — every train below fills it).
    sel = _raid_target(state, config)
    if sel is not None:
        _, need = sel
        fieldable = sum(1 for a in state.own_armies()
                        if not state.army_has_target(a.id))
        deficit = [max(0, need - fieldable)]
    else:
        deficit = [0]
    expand = _expansion_demand(state, config)
    cands = sorted(state.own_towns(),
                   key=lambda t: (0 if state.should_train_for_overcrowding(t) else 1,
                                  state.get_growth(t.id), t.population))
    for t in cands:
        if state.should_yield():
            break
        if t.id in state._pending_trains and state.turn <= state._pending_trains[t.id]:
            continue
        eta_n = force.get(t.id)
        want = False
        bare = False
        if eta_n is not None:
            eta, n = eta_n
            if defense_train_ok(t.population, cost, floor, eta, home[t.id], n):
                want = True
                bare = (home[t.id] == n - 1)  # doomed-town convert branch
        if deficit[0] > 0:
            want = True
        if expand:
            want = True
        if not want:
            continue
        if bare:
            if t.population >= cost:
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
                deficit[0] = max(0, deficit[0] - 1)
        elif (_can_train_pro(state, t)
                and t.population - cost >= floor - 1e-9):
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
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
    # Hold rule (Step 2): per threatened town keep min(home, N+1) — the
    # +1th is highest-leverage; beyond it extras are free. Hopeless towns
    # (D <= N-2, training can't save) keep none — defenders retreat via
    # the normal logic below instead of annihilating in place.
    held: set[int] = set()
    if duel_ctx:
        for t in state.own_towns():
            if t.id not in force:
                continue
            _, n = force[t.id]
            here = sorted((a for a in state.own_armies()
                           if math.hypot(a.x - t.x, a.y - t.y) <= 20.0),
                          key=lambda a: math.hypot(a.x - t.x, a.y - t.y))
            if len(here) <= n - 2:
                continue  # hopeless: retreat, don't annihilate
            for a in here[:min(len(here), n + 1)]:
                held.add(a.id)
    sel = _raid_target(state, config, priced=duel_ctx)
    for p in state.own_armies():
        if state.should_yield():
            break
        if state.army_has_target(p.id):
            continue  # handled by the builds stage
        if p.id in held:
            continue
        # G-defense (duel-only per P6): second-wave watch still holds one.
        if duel_ctx and should_hold_home(state, config, p, inbound, hold_second):
            continue
        if sel is not None:
            nearest, need = sel
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
            # G2: settle on demand only (same gate as trains: void merit
            # or contested payback) — else recycle home for +500 pop-add,
            # but ONLY in true peace: marching home under known threat
            # just delivers defenders to the builds-merge (guard_duty t31).
            # In war-footing the army holds position (staying is the order).
            site = find_build_site(state, config, p.x, p.y, rmin=80, rmax=300, salt=11, who=p.id) \
                if _expansion_demand(state, config) else None
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
