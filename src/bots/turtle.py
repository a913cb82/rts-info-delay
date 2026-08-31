"""Turtle — conservative. Trains only when calm, builds one at a time."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _site, can_train_safely,
    BotState, bot_main,
    PEAK_LOW, PEAK_HIGH,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()
    own_a = state.own_armies()

    # Only train when calm: no town in peak window, all above threshold
    all_calm = all(
        t.population >= 2500 and not (PEAK_LOW <= t.population <= PEAK_HIGH)
        for t in own_t
    )

    for t in own_t:
        if all_calm and can_train_safely(t, conservative=True):
            out.append(f"TRAIN {t.id}")

    # Build: one builder at a time, only when calm
    builders = 0
    if all_calm and own_t:
        biggest = max(own_t, key=lambda t: t.population)
        for p in sorted(own_a, key=lambda a: math.hypot(a.x - biggest.x, a.y - biggest.y)):
            if builders >= 1:
                break
            if p.is_viceroy and p.has_target:
                continue
            if any(o.startswith(f"BUILD {p.id}") or o.startswith(f"MOVE_TO {p.id}") for o in out):
                continue
            sx, sy = _site(state.turn, p.id, config,
                           [{"x": t.x, "y": t.y, "population": t.population} for t in own_t],
                           salt=13, rmin=40, rmax=100, around={"x": biggest.x, "y": biggest.y})
            dist = math.hypot(p.x - sx, p.y - sy)
            if dist < config.interact_radius + 5:
                out.append(f"BUILD {p.id} {sx:.1f} {sy:.1f}")
                builders += 1
            else:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {sx:.1f} {sy:.1f}")
                builders += 1

    # Garrison idle armies near nearest town
    for p in own_a:
        if p.is_viceroy and p.has_target:
            continue
        if any(o.startswith(f"BUILD {p.id}") or o.startswith(f"MOVE_TO {p.id}") for o in out):
            continue
        if own_t:
            nearest = min(own_t, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
            dist = math.hypot(p.x - nearest.x, p.y - nearest.y)
            if dist > 20:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")

    return out


if __name__ == "__main__":
    bot_main(decide_orders)
