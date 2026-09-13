"""greedy raid — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
from .intel import *  # noqa: F401,F403
from .threat import *  # noqa: F401,F403
import math
from engine.config import GameConfig

def foe_garrison(state: "BotState", u) -> int:
    """
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
Standing defenders imputed to foe town u (nearest same-faction town)."""
    n = 0
    for a in state.world.armies:
        if a.faction == state.faction or a.faction != u.faction:
            continue
        same = [t for t in state.world.towns if t.faction == u.faction]
        if min(same, key=lambda t: math.hypot(a.x - t.x, a.y - t.y)).id == u.id:
            n += 1
    return n



def raid_target(state: "BotState", config, priced: bool = True,
                margin: float = 200.0):
    """Priced raid target (unready-weighted) + required force, or None.

    Take needs N >= S+W+1 (standing + printable-before-arrival); the prize
    must clear `margin` (theft pays — the army isn't spent, only risked).
    No fieldable gate: an unaffordable-but-valuable target starts a
    PIPELINE (trains build the pack over turns); callers gate the MARCH
    on need <= free. Unpriced (big-war denial) returns max-pressure."""
    faction = state.faction
    eff = config.capture_loss
    cost = config.army_cost
    floor = config.death_threshold
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    war_foes = {t.faction for t in enemy_towns} | {
        a.faction for a in state.world.armies if a.faction != faction}
    duel_ctx = len(war_foes) <= 1
    if duel_ctx:
        cands = [t for t in enemy_towns
                 if t.population * (1.0 - eff) > cost * eff + 200]
    else:
        cands = list(enemy_towns)
    if not cands:
        return None
    fieldable = [a for a in state.own_armies()
                 if not state.army_has_target(a.id)]
    best = None
    for u in cands:
        s = foe_garrison(state, u)
        printable = max(0.0, (u.population - cost - floor) / cost)
        arrival_t = min((math.hypot(a.x - u.x, a.y - u.y)
                         for a in fieldable),
                        default=float("inf")) / max(1.0, config.army_speed)
        # Can't land after the buzzer: pointless march. (W collapses
        # naturally as turns_left -> 0 — retaliation becomes impossible.)
        turns_left = (getattr(config, "max_turns", 3000) or 3000) - state.turn
        if arrival_t > turns_left:
            continue
        w = min(printable, arrival_t) * foe_print_factor(state, u.faction)
        need = int(s + w + 1)
        prize = u.population * (1.0 - eff)
        dist = min((math.hypot(a.x - u.x, a.y - u.y) for a in fieldable),
                   default=float("inf"))
        if not priced:
            score = u.population / (1.0 + dist / 300.0)
            if best is None or score > best[0]:
                best = (score, u, need, s)
        elif prize > margin:
            # Bird-in-hand: an executable take now beats a bigger prize
            # after print-turns (opportunity cost + compounding). Pipeline
            # targets discount by turns-to-ready.
            score = prize / (1.0 + dist / 300.0) / (1.0 + s + w) \
                / (1.0 + max(0, need - len(fieldable)))
            if best is None or score > best[0]:
                best = (score, u, need, s)
    if best is None:
        return None
    return best[1], best[2], best[3]



