"""Expander — the colonist. Trains whenever affordable, always builds outward."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotState, bot_main, can_train_safely, find_build_site


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()

    for t in own_t:
        if state.can_train_here(t, conservative=False):
            out.append(f"TRAIN {t.id}")

    for p in state.own_armies():
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            if tgt is None:
                continue
            tx, ty = tgt
            if math.hypot(p.x - tx, p.y - ty) < config.interact_radius + 10:
                out.append(f"BUILD {p.id} {tx:.1f} {ty:.1f}")
            continue
        site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=350, salt=11)
        if site:
            sx, sy = site
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {sx:.1f} {sy:.1f}")
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
