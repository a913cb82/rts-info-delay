"""Greedy — simplest useful bot: TRAIN if safe, else chase nearest enemy."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _forecast_pos, BotState, bot_main,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []

    # TRAIN in all own towns
    for t in state.own_towns():
        if can_train_safely(t, conservative=False):
            if t.spent_on_train == 0:
                out.append(f"TRAIN {t.id}")

    # Armies: chase nearest enemy town or enemy army
    enemy_towns = [{"x": t.x, "y": t.y} for t in state.towns.values() if t.faction != faction]
    enemy_armies = [{"x": a.x, "y": a.y, "has_target": a.has_target, "target_x": a.target_x, "target_y": a.target_y}
                    for a in state.armies.values() if a.faction != faction]

    # Precompute forecast positions for enemy armies
    forecast_enemies = []
    for e in enemy_armies:
        fx, fy = _forecast_pos(e, 1.0, config)
        forecast_enemies.append({"fx": fx, "fy": fy})

    for p in state.own_armies():
        if p.is_viceroy and p.has_target:
            continue
        if enemy_towns:
            nearest = min(enemy_towns, key=lambda t: math.hypot(t["x"] - p.x, t["y"] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest['x']:.1f} {nearest['y']:.1f}")
        elif forecast_enemies:
            e = min(forecast_enemies, key=lambda e: math.hypot(e["fx"] - p.x, e["fy"] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {e['fx']:.1f} {e['fy']:.1f}")

    return out


if __name__ == "__main__":
    bot_main(decide_orders)
