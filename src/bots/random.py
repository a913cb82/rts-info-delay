"""Random — baseline, deterministic via _hash, with TRAIN gate."""

from __future__ import annotations

import math
from engine.config import GameConfig
from .common import (
    _hash, _site, _can_train, BotState, bot_main,
    TRAIN_SURVIVE, PEAK_LOW, PEAK_HIGH,
)


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    """Pure function: (world, faction, config) → list[order_strings]."""
    faction = state.faction
    out: list[str] = []
    busy: set[int] = set()
    own_t = state.own_towns()
    own_a = state.own_armies()

    # TRAIN: if pop > 2000 or small and safe
    for t in own_t:
        if t.id in busy:
            continue
        # Don't train if we already spent here this turn
        if t.spent_on_train > 0:
            continue
        if state.can_train_safely(t.id, conservative=False):
            # Extra gate: skip peak window 50% of time
            h = _hash(state.turn, t.id, 7)
            if PEAK_LOW <= t.population <= PEAK_HIGH and h % 2 == 0:
                continue
            out.append(f"TRAIN {t.id}")

    # BUILD / wander
    for p in own_a:
        if p.id in busy:
            continue
        if p.is_viceroy and p.has_target:
            continue
        h = _hash(state.turn, p.id, 3)
        # 20% build if idle and safe site
        if h % 5 == 0 and own_t:
            cap = state.world.faction_capital(faction)
            if cap:
                sx, sy = _site(state.turn, p.id, config, [{"x": t.x, "y": t.y, "population": t.population} for t in own_t], salt=11, rmin=100, rmax=350, around={"x": cap.x, "y": cap.y})
                out.append(f"BUILD {p.id} {sx:.1f} {sy:.1f}")
                busy.add(p.id)
                continue
        # wander toward random own town
        if own_t:
            ht = _hash(state.turn, p.id, 5) % len(own_t)
            t = own_t[ht]
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {t.x:.1f} {t.y:.1f}")
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
