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
        if enemy_towns:
            nearest = min(enemy_towns, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")
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
