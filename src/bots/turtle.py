"""Turtle — fortifier. Trains only when calm, builds close, garrisons."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotState, bot_main, can_train_safely, find_build_site, PEAK_LOW, PEAK_HIGH


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()

    all_calm = all(t.population >= 2600 and not (PEAK_LOW <= t.population <= PEAK_HIGH) for t in own_t) if own_t else False

    for t in own_t:
        if all_calm and state.can_train_here(t, conservative=True):
            out.append(f"TRAIN {t.id}")

    # one builder at a time
    built = False
    for p in sorted(state.own_armies(), key=lambda a: min((math.hypot(a.x - t.x, a.y - t.y) for t in own_t), default=0)):
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            if tgt and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
                out.append(f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}")
                built = True
            continue
        if not built and own_t:
            biggest = max(own_t, key=lambda t: t.population)
            site = find_build_site(state, config, biggest.x, biggest.y, rmin=40, rmax=140, salt=13)
            if site:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {site[0]:.1f} {site[1]:.1f}")
                built = True
        # garrison remainder
        if not built or state.army_has_target(p.id):
            continue
        if own_t:
            nearest = min(own_t, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
            if math.hypot(p.x - nearest.x, p.y - nearest.y) > 20:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
