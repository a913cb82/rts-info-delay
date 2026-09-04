"""Aggressive — conqueror. Trains eagerly, chases enemies, expands when clear."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, bot_main, find_build_site, towns_by_train_priority


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out

    for t in towns_by_train_priority(state, conservative=False):
        if state.should_yield():
            break
        out.append(f"TRAIN {t.id}")

    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    enemy_armies = [a for a in state.world.armies if a.faction != faction]
    own_t = state.own_towns()
    # second-wave watch: a known own army that vanished (not via noted
    # BUILD) died in battle — the enemy double-trains, so hold one home
    # for 6 turns. Survives on the state object across turns.
    cur_ids = {a.id for a in state.own_armies()}
    known = getattr(state, "_agg_ids", set())
    pending_b = set(getattr(state, "_pending_builds", {}))
    if known and (known - cur_ids - pending_b):
        state._agg_hold_until = state.turn + 6
    state._agg_ids = set(cur_ids)
    hold_second = state.turn <= getattr(state, "_agg_hold_until", -1)
    # inbound: enemy armies predicted at MY towns (nearest-own-town rule).
    # Home armies hold against inbound instead of chasing ghosts (Elo lesson:
    # viability-chasing left the capital empty, greedy walked in t8).
    # stationary guards sitting on their own towns are not inbound.
    foe_towns = [t for t in state.world.towns if t.faction != faction]
    inbound: dict[int, float] = {}
    for t in own_t:
        best = float("inf")
        for a in state.world.armies:
            if a.faction == faction:
                continue
            if any(math.hypot(a.x - u.x, a.y - u.y) <= 15 for u in foe_towns if u.faction == a.faction):
                continue
            if min(own_t, key=lambda u: math.hypot(a.x - u.x, a.y - u.y)).id != t.id:
                continue
            eta = math.hypot(a.x - t.x, a.y - t.y) / max(1.0, config.army_speed)
            if eta < best:
                best = eta
        if best <= 8:
            inbound[t.id] = best
    # A1: viability gate — only march at towns worth holding: captured
    # pop (halved) must clear the death floor + margin, else the raid
    # buys a starvation (starve_trap lesson). Computed once (used by idle
    # march below AND the arrival-sync check above).
    viable = [t for t in enemy_towns
              if t.population * (1.0 - config.build_efficiency)
              > config.army_cost * config.build_efficiency + 200]

    for p in state.own_armies():
        if state.should_yield():
            break
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            if tgt is None:
                continue
            # only BUILD if target is not an enemy town (attack needs capture, not BUILD)
            is_enemy_target = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in enemy_towns)
            if not is_enemy_target and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
                out.append(f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}")
            continue
        # home-hold: keep >=1 army on a threatened town (inbound seen, or
        # second wave expected). Extras march.
        home_t = next((t for t in own_t if math.hypot(p.x - t.x, p.y - t.y) <= 20), None)
        if home_t is not None and (home_t.id in inbound or hold_second):
            others = sum(1 for a in state.own_armies()
                         if a.id != p.id and math.hypot(a.x - home_t.x, a.y - home_t.y) <= 20)
            if others == 0:
                continue
        if viable:
            # A3: leader-targeting — value towns by faction strength per km,
            # not bare distance (dent the leader while it compounds).
            fscore: dict[int, float] = {}
            for t in state.world.towns:
                fscore[t.faction] = fscore.get(t.faction, 0.0) + t.population
            for a in state.world.armies:
                fscore[a.faction] = fscore.get(a.faction, 0.0) + 1000.0
            nearest = max(viable, key=lambda t: fscore.get(t.faction, 0.0) / (1.0 + math.hypot(t.x - p.x, t.y - p.y) / 300.0))
            # A2: departure sync — hold a lone army at home when its target
            # is defended and the home town can retrench (a packmate is one
            # train away). Same-turn arrival kills clean; trickle trades.
            # (Arrival-sync proved unworkable: 1-turn decision lag +
            # 1-turn messenger lag + stale intel vs 50km/turn marches.)
            defended = any(math.hypot(e.x - nearest.x, e.y - nearest.y) <= 10 for e in enemy_armies)
            if defended and len(state.own_armies()) == 1:
                home = min(state.own_towns(), key=lambda t: math.hypot(t.x - p.x, t.y - p.y), default=None)
                if home is not None and home.population >= 2 * config.army_cost:
                    continue  # wait for the pack; march together next turns
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")
            state.note_move(p.id, nearest.x, nearest.y)
        elif enemy_armies:
            fc = BotForecast(state, config)
            forecast = [(fc.forecast_army_pos(e), e) for e in enemy_armies]
            (fx, fy), _ = min(forecast, key=lambda x: math.hypot(x[0][0] - p.x, x[0][1] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {fx:.1f} {fy:.1f}")
        else:
            site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=340, salt=11)
            if site:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {site[0]:.1f} {site[1]:.1f}")
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
