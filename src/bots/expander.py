"""Expander — colonizer. Trains aggressively, always builds new settlements."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _hash, _site,
    BotState, bot_main,
    can_train_safely,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()
    own_a = state.own_armies()

    # TRAIN: train from every town that can afford it
    for t in own_t:
        if can_train_safely(t, conservative=False):
            out.append(f"TRAIN {t.id}")

    # BUILD: idle armies move to build site then build
    for p in own_a:
        if p.is_viceroy and p.has_target:
            continue
        cap = state.world.faction_capital(faction)
        if not cap:
            continue
        sx, sy = _site(state.turn, p.id, config,
                       [{"x": t.x, "y": t.y, "population": t.population} for t in own_t],
                       salt=11, rmin=100, rmax=300, around={"x": cap.x, "y": cap.y})
        dist = math.hypot(p.x - sx, p.y - sy)
        if dist < config.interact_radius + 5:
            # Close enough — build
            out.append(f"BUILD {p.id} {sx:.1f} {sy:.1f}")
        else:
            # Move toward build site
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {sx:.1f} {sy:.1f}")

    return out


if __name__ == "__main__":
    bot_main(decide_orders)
