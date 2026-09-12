"""turtle raid — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403
from .intel import _memoized  # noqa: F401

def garrison_map(state: "BotState") -> dict:
    """Standing defenders per foe town (nearest same-faction town),
    computed once per turn (shared by raid_target + strike_target —
    per-town calls recomputed it 2xT times per decide)."""
    def _compute():
        by_faction: dict = {}
        for t in state.world.towns:
            by_faction.setdefault(t.faction, []).append(t)
        counts: dict = {}
        for a in fresh_foe_armies(state):
            same = by_faction.get(a.faction)
            if not same:
                continue
            w = min(same, key=lambda t: math.hypot(a.x - t.x, a.y - t.y))
            counts[w.id] = counts.get(w.id, 0) + 1
        return counts
    return _memoized(state, ("garrison_map",), _compute)

def foe_garrison(state: "BotState", u) -> int:
    """Standing defenders imputed to foe town u (nearest same-faction town).
    Grave-memory prices in: bloodied (our army died here <150t ago) imputes
    >= 1 — dead armies tell no tales, so stale s=0 would otherwise keep
    approving onesie raids into unseen garrisons.
    Blind-attack floor (GTO rush doctrine, r38 lesson): s=0 from STALE
    intel is unconfirmed — assume muster-3 (never raid blind-small).
    Fresh s=0 (observed empty under send-all) still takes at need 1."""
    s = garrison_map(state).get(u.id, 0)
    if state.__dict__.get("_bloodied", {}).get(u.id, -10**9) >= state.turn - 150:
        s = max(s, 1)
    if s == 0 and state.turn - state._last_seen.get(("town", u.id), -10**9) > 150:
        s = 3
        # Stale-age premium (r55 lesson: stale floor 3 vs real garrison 8
        # — pro bled 43 undersized packs vs ghost-coast towns). Unseen
        # towns accumulate guards: +1 per 500t stale, cap +3.
        age = state.turn - state._last_seen.get(("town", u.id), state.turn)
        s += min(3, age // 500)
    return s
    s = garrison_map(state).get(u.id, 0)
    if state.__dict__.get("_bloodied", {}).get(u.id, -10**9) >= state.turn - 150:
        s = max(s, 1)
    return s

def pack_print(state: "BotState", config, sel, free_n, can_train) -> list[str]:
    """Pack-driven print (shared r40 lesson): shortfall with nothing
    printing toward it orders the missing member (packs otherwise hold
    forever while towns compound for the foe). Respects floors."""
    if sel is None:
        return []
    if sel[1] - free_n <= 0 or state._pending_trains:
        return []
    cands = sorted((t for t in state.own_towns()
                    if can_train(state, t)
                    and t.population - config.army_cost >= config.death_threshold - 1e-9),
                   key=lambda t: -t.population)
    if not cands:
        return []
    state.note_train(cands[0].id)
    return [f"TRAIN {cands[0].id}"]

def probe_ok(state: "BotState", sel) -> bool:
    """Lone-probe gate: visibly-empty (s == 0) AND no fresh grave.
    A probe that died at the target within 150 turns means garrison the
    intel missed — hold for the full pack instead of re-feeding onesies."""
    return sel[2] == 0 and state.__dict__.get("_bloodied", {}).get(sel[0].id, -10**9) < state.turn - 150

def raid_targets(state: "BotState", config, k: int = 1, priced: bool = True,
                 margin: float = 200.0):
    from .threat import buzzer_active, foe_print_factor  # noqa: F401 (lazy: breaks import cycle; runtime-safe)
    """Top-k priced raid targets + required forces (ranked). Powers
    parallel thin-takes: vs ungarrisoned sprawl, need-sized packets hit
    several towns at once instead of marching the whole pack at one.

    Take needs N >= S+W+1 (standing + printable-before-arrival); the prize
    must clear `margin` (theft pays — the army is not spent, only risked).
    No fieldable gate: an unaffordable-but-valuable target starts a
    PIPELINE (trains build the pack over turns); callers gate the MARCH
    on need <= free. Unpriced (big-war denial) returns max-pressure."""
    faction = state.faction
    eff = config.build_efficiency
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
    ranked: list = []
    _big = len(cands) * max(1, len(fieldable)) > 50000
    for i, u in enumerate(cands):
        if _big and i % 8 == 0 and state.should_yield():
            break  # timeout guard: best-so-far stands
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
        # Buzzer (r50 lesson: t9000+ silence — needs exceed everyone).
        # Retaliation time has run out: no future to defend, so W -> 0
        # explicitly (arrival doesn't collapse on its own). Bare S+1+dist.
        if buzzer_active(state, config):
            w = 0.0
        need = int(s + w + 1)
        prize = u.population * (1.0 - eff)
        dist = min((math.hypot(a.x - u.x, a.y - u.y) for a in fieldable),
                   default=float("inf"))
        # Latency caution (doctrine): far fights are dangerous (slow
        # reinforce, stale intel) — +1 need per 300km. Nearby empties
        # still take cheap; far ones muster deep or wait.
        if dist != float("inf"):
            need += int(dist // 300.0)
        # Remuster guard (r51 lesson: buzzer W=0 reintroduced onesies —
        # pro lost 54 vs printing towns. S=0 observed + printer foe =
        # remuster before arrival: onesies never suffice). Printers cost
        # +1; sterile-observed foes still take cheap.
        if foe_print_factor(state, u.faction) > 0.3:
            need += 1
        if not priced:
            score = u.population / (1.0 + dist / 300.0)
            ranked.append((score, u, need, s))
            if best is None or score > best[0]:
                best = (score, u, need, s)
        elif prize > margin:
            # Bird-in-hand: an executable take now beats a bigger prize
            # after print-turns (opportunity cost + compounding). Pipeline
            # targets discount by turns-to-ready. Capitals carry a
            # beheading premium (permanent; universal GTO).
            score = prize / (1.0 + dist / 300.0) / (1.0 + s + w) \
                / (1.0 + max(0, need - len(fieldable)))
            if u.is_capital:
                score *= 1.5
            ranked.append((score, u, need, s))
            if best is None or score > best[0]:
                best = (score, u, need, s)
    if best is None:
        return None
    ranked.sort(key=lambda r: -r[0])
    return [(u, need, s) for _, u, need, s in ranked[:max(1, k)]]

def raid_target(state: "BotState", config, priced: bool = True,
                margin: float = 200.0):
    """Top-1 priced raid target (raid_targets wrapper; exact-compatible)."""
    r = raid_targets(state, config, 1, priced, margin)
    return r[0] if r else None

def jit_ready(state: "BotState", config, target, need: int, free_ids: list,
              foe_faction: int | None = None) -> bool:
    """Just-in-time packs (Step 3 tempo): march iff the pack is complete
    (need <= free) or completes en route (arrival >= print-deficit at
    own-town print rate). Long marches leave now and build on the way;
    short marches wait and dash complete. Symmetric print keeps the gap
    roughly constant (march-now >= wait); out-printed races are declined
    by the pack cap (demand_trains), not here. foe_faction reserved for
    reactive calibration (currently unused — gap-stable default)."""
    if need <= len(free_ids):
        return True
    towns = state.own_towns()
    if not towns or not free_ids:
        return False
    by_id = {a.id: a for a in state.own_armies()}
    dists = [math.hypot(by_id[i].x - target.x, by_id[i].y - target.y)
               for i in free_ids if i in by_id]
    if not dists:
        return False
    arrival = min(dists) / max(1.0, config.army_speed)
    print_turns = (need - len(free_ids)) / max(1, len(towns))
    # Strict: ties hold (print can lag a turn; arriving exactly-even is
    # a coin flip on intel delay, and flips favor the defender).
    return arrival > print_turns

def _overmatch(state: "BotState", ratio: float = 1.5) -> bool:
    """Deterrence needs overmatch (Step 2 remainder): guard-early only
    when my score >= ratio x the strongest foe (weaker foes decline +EV
    raids vs visible guards; peers mutual-accept anyway (early-muster is
    pure timing-tax — wait for last-moment))."""
    fscore: dict = {}
    for t in state.world.towns:
        fscore[t.faction] = fscore.get(t.faction, 0.0) + t.population
    for a in state.world.armies:
        fscore[a.faction] = fscore.get(a.faction, 0.0) + 1000.0
    my = fscore.get(state.faction, 0.0)
    foe_best = max((v for f, v in fscore.items() if f != state.faction), default=0.0)
    return my >= ratio * foe_best if foe_best > 0 else True

def strike_target(state: "BotState", config, buzzer_window: int = 30,
                  blitz_reach: float = 2.0, margin: float = 200.0):
    """Strike doctrine (Step 6+ / early-window unified), two modes:
    BLITZ (anytime): S+1 takes landing within blitz_reach turns — they
    can't print before contact (strike before they print!). BUZZER
    (turns_left <= window): W = 0 takes landing inside the window
    (retaliation can't arrive). Both need executable force (need <=
    free) and clear prize>margin. Returns (target, need) or None.
    Breaks peaceful equilibria (the only breaker when all-credible)."""
    faction = state.faction
    eff = config.build_efficiency
    cost = config.army_cost
    speed = max(1.0, config.army_speed)
    turns_left = (getattr(config, "max_turns", 3000) or 3000) - state.turn
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    cands = [t for t in enemy_towns
             if t.population * (1.0 - eff) > cost * eff + 200]
    if not cands:
        return None
    fieldable = [a for a in state.own_armies()
                 if not state.army_has_target(a.id)]
    if not fieldable:
        return None
    best = None
    _big = len(cands) * max(1, len(fieldable)) > 50000
    for i, u in enumerate(cands):
        if _big and i % 8 == 0 and state.should_yield():
            break  # timeout guard: best-so-far stands
        s = foe_garrison(state, u)
        arrival = min(math.hypot(a.x - u.x, a.y - u.y) for a in fieldable) / speed
        prize = u.population * (1.0 - eff)
        if prize <= margin:
            continue
        need = None
        if arrival <= blitz_reach:
            need = s + 1  # blitz: they can't print before contact
        elif turns_left <= buzzer_window and arrival <= turns_left:
            need = s + 1  # buzzer: W = 0, retaliation can't arrive
        if need is None or need > len(fieldable):
            continue
        score = prize / (1.0 + arrival / 50.0)
        if best is None or score > best[0]:
            best = (score, u, need)
    if best is None:
        return None
    return best[1], best[2]

