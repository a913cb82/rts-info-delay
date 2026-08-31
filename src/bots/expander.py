"""Expander — colonizer, not fighter. Pure function, deterministic."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _hash, _site, _can_train, _forecast_pos, _enemy_towns,
    BotState, bot_main,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()
    own_a = state.own_armies()
    enemies = [{"x": a.x, "y": a.y} for a in state.armies.values() if a.faction != faction]

    # TRAIN: conservative (skip peak, require >1600)
    for t in own_t:
        if t.spent_on_train > 0:
            continue
        if state.can_train_safely(t.id, conservative=True):
            out.append(f"TRAIN {t.id}")

    # Each army builds or tours
    for p in own_a:
        if p.is_viceroy and p.has_target:
            continue
        h = _hash(state.turn, p.id, 11)
        if h % 3 == 0:
            # Build
            cap = state.world.faction_capital(faction)
            if cap:
                sx, sy = _site(state.turn, p.id, config,
                               [{"x": t.x, "y": t.y, "population": t.population} for t in own_t],
                               salt=11, rmin=120, rmax=280, around={"x": cap.x, "y": cap.y})
                # Don't build near enemies
                if enemies and min(math.hypot(sx - e["x"], sy - e["y"]) for e in enemies) < config.info_speed:
                    # Tour instead
                    low = min(own_t, key=lambda t: t.population) if own_t else None
                    if low:
                        out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {low.x:.1f} {low.y:.1f}")
                    continue
                out.append(f"BUILD {p.id} {sx:.1f} {sy:.1f}")
        else:
            # Tour to nearest low-pop own town (not capital)
            non_cap = [t for t in own_t if not t.is_capital]
            if non_cap:
                nearest = min(non_cap, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")

    return out


if __name__ == "__main__":
    bot_main(decide_orders)
