"""Aggressive — conqueror. Trains eagerly, chases enemies, expands when clear."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, bot_main, drive_scout, drop_dead_notes, find_build_site, inbound_eta, maybe_assign_scout, note_wave_watch, order_move, should_hold_home, towns_by_train_priority


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out
    drop_dead_notes(state)  # unstrand armies whose orders died in flight

    for t in towns_by_train_priority(state, conservative=False):
        if state.should_yield():
            break
        out.append(f"TRAIN {t.id}")

    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    enemy_armies = [a for a in state.world.armies if a.faction != faction]
    own_t = state.own_towns()
    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    # A1: viability gate — only march at towns worth holding: captured
    # pop (halved) must clear the death floor + margin, else the raid
    # buys a starvation (starve_trap lesson). Computed once (used by idle
    # march below AND the arrival-sync check above).
    war_foes = {t.faction for t in enemy_towns} | {a.faction for a in enemy_armies}
    if len(war_foes) <= 1:
        viable = [t for t in enemy_towns
                  if t.population * (1.0 - config.build_efficiency)
                  > config.army_cost * config.build_efficiency + 200]
    else:
        viable = list(enemy_towns)

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
            if not is_enemy_target and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
                out.append(f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}")
            continue
        if should_hold_home(state, config, p, inbound, hold_second):
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
            out.extend(order_move(state, config, p, nearest.x, nearest.y))
        elif enemy_armies:
            fc = BotForecast(state, config)
            forecast = [(fc.forecast_army_pos(e), e) for e in enemy_armies]
            (fx, fy), _ = min(forecast, key=lambda x: math.hypot(x[0][0] - p.x, x[0][1] - p.y))
            out.extend(order_move(state, config, p, fx, fy))
        else:
            # S0: no-contact scout first (Step 2 prereq) — probe deep
            # before founding; falls back to settling below.
            if maybe_assign_scout(state, config, p):
                out.extend(drive_scout(state, config, p) or [])
                continue
            site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=340, salt=11, who=p.id)
            if site:
                out.extend(order_move(state, config, p, site[0], site[1]))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
