"""Aggressive — chases nearest enemy town/army, with forecast and TRAIN gate."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _hash, _can_train, _forecast_pos, _enemy_towns,
    BotState, bot_main,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()
    own_a = state.own_armies()
    enemies = [{"x": a.x, "y": a.y, "has_target": a.has_target, "target_x": a.target_x, "target_y": a.target_y}
               for a in state.armies.values() if a.faction != faction]

    # TRAIN
    for t in own_t:
        if t.spent_on_train > 0:
            continue
        if state.can_train_safely(t.id, conservative=False):
            out.append(f"TRAIN {t.id}")

    # Guard capital with one army
    cap = state.world.faction_capital(faction)
    guarded = False
    if cap:
        for p in own_a:
            if p.is_viceroy and p.has_target:
                continue
            dist = math.hypot(p.x - cap.x, p.y - cap.y)
            if dist < 100 and not guarded:
                guarded = True
                continue  # stay put

    # Chase: nearest enemy town or forecast enemy army
    for p in own_a:
        if p.is_viceroy and p.has_target:
            continue
        e_towns = [{"x": t.x, "y": t.y} for t in state.towns.values() if t.faction != faction]
        if e_towns:
            nearest = min(e_towns, key=lambda t: math.hypot(t["x"] - p.x, t["y"] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest['x']:.1f} {nearest['y']:.1f}")
        elif enemies:
            # Chase forecast position
            forecast_enemies = []
            for e in enemies:
                fx, fy = _forecast_pos(e, 1.0, config)
                forecast_enemies.append({"fx": fx, "fy": fy})
            e = min(forecast_enemies, key=lambda e: math.hypot(e["fx"] - p.x, e["fy"] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {e['fx']:.1f} {e['fy']:.1f}")

    return out


if __name__ == "__main__":
    bot_main(decide_orders)
