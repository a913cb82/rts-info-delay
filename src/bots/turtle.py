"""Turtle — hunkers down, garrisons, shy build. Pure function."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _site, _can_train,
    BotState, bot_main,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()
    own_a = state.own_armies()

    # All towns calm?
    all_calm = all(
        t.population >= 1500 and not (35000 <= t.population <= 65000)
        for t in own_t
    )

    # TRAIN: very conservative, all calm, pop >= 3000
    for t in own_t:
        if t.spent_on_train > 0:
            continue
        if t.population < 3000:
            continue
        if not all_calm:
            continue
        if state.can_train_safely(t.id, conservative=True):
            out.append(f"TRAIN {t.id}")

    # BUILD: only one builder, only when all calm
    builders = 0
    if all_calm and own_t:
        biggest = max(own_t, key=lambda t: t.population)
        # Sort armies by distance to biggest town
        sorted_a = sorted(own_a, key=lambda a: math.hypot(a.x - biggest.x, a.y - biggest.y))
        for p in sorted_a:
            if builders >= 1:
                break
            if p.is_viceroy and p.has_target:
                continue
            sx, sy = _site(state.turn, p.id, config,
                           [{"x": t.x, "y": t.y, "population": t.population} for t in own_t],
                           salt=13, rmin=40, rmax=100, around={"x": biggest.x, "y": biggest.y})
            out.append(f"BUILD {p.id} {sx:.1f} {sy:.1f}")
            builders += 1

    # Garrison idle armies near nearest town
    for p in own_a:
        if p.is_viceroy and p.has_target:
            continue
        if any(o.startswith(f"BUILD {p.id}") for o in out):
            continue
        if own_t:
            nearest = min(own_t, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
            dist = math.hypot(p.x - nearest.x, p.y - nearest.y)
            if dist > 20:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")

    return out


if __name__ == "__main__":
    bot_main(decide_orders)
