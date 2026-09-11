"""Expander — the colonist. Trains whenever affordable, always builds outward."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotState, bot_main, buzzer_active, drive_scout, drop_dead_notes, find_build_site, inbound_eta, maybe_assign_scout, note_wave_watch, order_move, should_hold_home, towns_by_train_priority


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    faction = state.faction
    out: list[str] = []
    if state.should_yield():
        return out
    drop_dead_notes(state)  # unstrand armies whose orders died in flight
    own_t = state.own_towns()

    for t in towns_by_train_priority(state, conservative=False):
        if state.should_yield():
            break
        out.append(f"TRAIN {t.id}")

    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    # Buzzer blind guards (Step 6): one home per rich town. (Normal holds
    # stay on should_hold_home until the Step 2 expander rollout.)
    buzz_held: set = set()
    if buzzer_active(state, config):
        for t in state.own_towns():
            if t.population >= 2 * config.army_cost:
                here = [a for a in state.own_armies()
                        if a.id not in buzz_held
                        and math.hypot(a.x - t.x, a.y - t.y) <= 20.0]
                if here:
                    buzz_held.add(min(here, key=lambda a: math.hypot(a.x - t.x, a.y - t.y)).id)
    for p in state.own_armies():
        if state.should_yield():
            break
        if p.id in buzz_held:
            continue
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        sc = drive_scout(state, config, p)
        if sc is not None:
            out.extend(sc)
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
        # E1: guard — keep >=1 home vs inbound/second wave (shared).
        if should_hold_home(state, config, p, inbound, hold_second):
            continue
        # Buzzer (Step 6): no settling (never repays) — hold instead.
        # Rich towns get their blind guard via hold_defenders below.
        if buzzer_active(state, config):
            continue
        # S0: no-contact scout first (Step 2 prereq) — probe deep before
        # founding; falls back to settling below.
        if maybe_assign_scout(state, config, p):
            out.extend(drive_scout(state, config, p) or [])
            continue
        site = find_build_site(state, config, p.x, p.y, rmin=120, rmax=350, salt=11, who=p.id)
        if site:
            sx, sy = site
            out.extend(order_move(state, config, p, sx, sy))
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
