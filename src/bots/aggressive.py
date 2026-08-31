"""Aggressive — chases nearest enemy, TRAINs greedily."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _forecast_pos,
    BotState, bot_main,
    can_train_safely,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()
    own_a = state.own_armies()

    # TRAIN: every town that can afford it
    for t in own_t:
        if can_train_safely(t, conservative=False):
            out.append(f"TRAIN {t.id}")

    # Chase: nearest enemy town, or forecast enemy army position
    enemy_towns = [{"x": t.x, "y": t.y} for t in state.world.towns if t.faction != faction]
    enemy_armies = [{"x": a.x, "y": a.y, "has_target": a.has_target,
                     "target_x": a.target_x, "target_y": a.target_y}
                    for a in state.world.armies if a.faction != faction]

    for p in own_a:
        if p.is_viceroy and p.has_target:
            continue
        if enemy_towns:
            nearest = min(enemy_towns, key=lambda t: math.hypot(t["x"] - p.x, t["y"] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest['x']:.1f} {nearest['y']:.1f}")
        elif enemy_armies:
            forecast = [{"fx": _forecast_pos(e, 1.0, config)[0],
                         "fy": _forecast_pos(e, 1.0, config)[1]} for e in enemy_armies]
            e = min(forecast, key=lambda e: math.hypot(e["fx"] - p.x, e["fy"] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {e['fx']:.1f} {e['fy']:.1f}")

    return out


if __name__ == "__main__":
    bot_main(decide_orders)
