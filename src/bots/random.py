"""Random — balanced wanderer. Trains, sometimes builds, sometimes wanders."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import _hash, BotState, bot_main, find_build_site, towns_by_train_priority, PEAK_LOW, PEAK_HIGH


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    own_t = state.own_towns()

    for t in towns_by_train_priority(state, conservative=False):
        h = _hash(state.turn, t.id, 7)
        if PEAK_LOW <= t.population <= PEAK_HIGH and h % 2 == 0:
            continue
        out.append(f"TRAIN {t.id}")

    for p in state.own_armies():
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        if state.army_has_target(p.id):
            if state.has_pending_build(p.id):
                continue
            tgt = state.army_target(p.id)
            if tgt and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
                out.append(f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}")
            continue
        h = _hash(state.turn, p.id, 3)
        if h % 5 < 3:
            site = find_build_site(state, config, p.x, p.y, rmin=100, rmax=330, salt=11)
            if site:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {site[0]:.1f} {site[1]:.1f}")
        elif own_t:
            ht = _hash(state.turn, p.id, 5) % len(own_t)
            t = own_t[ht]
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {t.x:.1f} {t.y:.1f}")
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
