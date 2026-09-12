"""pro settle — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403
from .intel import _hash  # noqa: F401

SITE_MARGIN = 15.0


def _site(turn, i, cfg, own_towns, salt=0, rmin=80.0, rmax=250.0, around=None):
    th = cfg.map_size[0] if isinstance(cfg.map_size, (list, tuple)) else 1000
    c = around if around is not None else {"x": th / 2, "y": th / 2}
    max_pop = max((t.get("population", 500) for t in own_towns), default=500)
    need = 0.4 * math.sqrt(max_pop) * 2
    need = max(need, 30.0)
    for k in range(12):
        h = _hash(turn, i, salt + k)
        ang = (h % 360) / 360 * 2 * math.pi
        d = rmin + ((h // 360) % 1000) / 1000 * (rmax - rmin)
        x = c["x"] + d * math.cos(ang)
        y = c["y"] + d * math.sin(ang)
        if x < SITE_MARGIN or y < SITE_MARGIN or x > th - SITE_MARGIN or y > th - SITE_MARGIN:
            continue
        if any(math.hypot(x - t["x"], y - t["y"]) < max(need, cfg.interact_radius) for t in own_towns):
            continue
        return x, y
    return (
        min(th - SITE_MARGIN, max(SITE_MARGIN, c["x"])),
        min(th - SITE_MARGIN, max(SITE_MARGIN, c["y"])),
    )


# ── Shared build-site finder ──

_build_site_cache: dict[tuple, tuple[float, float] | None] = {}

def find_build_site(state, config: GameConfig, ref_x: float, ref_y: float, rmin: float = 80, rmax: float = 300, salt: int = 0, who: int = 0) -> tuple[float, float] | None:
    """Deterministic site spin, stable per army: `who` (army/town id) —
    never the turn — seeds the hash, so re-queries across turns return
    the same site and headings hold through note-drops and waits.
    Different armies spread via id + position."""
    key = (state.turn, int(ref_x), int(ref_y), rmin, rmax, salt, who, state.faction)
    if key in _build_site_cache:
        return _build_site_cache[key]
    th = config.map_size[0] if isinstance(config.map_size, (list, tuple)) else 1000
    cands: list[tuple[float, float, float, float]] = []
    # pre-filter towns near ref for faster crowding (only within rmax+150)
    nearby_towns = [t for t in state.world.towns if math.hypot(t.x - ref_x, t.y - ref_y) < rmax + 200]
    if not nearby_towns:
        nearby_towns = state.world.towns[:50]  # fallback small sample
    for k in range(16):
        h = _hash(who, int(ref_x * 7 + ref_y * 13) & 0xFFFF, salt + k)
        ang = (h % 3600) / 3600 * 2 * math.pi
        d = rmin + ((h // 3600) % 1000) / 1000 * (rmax - rmin)
        x = ref_x + d * math.cos(ang)
        y = ref_y + d * math.sin(ang)
        x = max(SITE_MARGIN, min(th - SITE_MARGIN, x))
        y = max(SITE_MARGIN, min(th - SITE_MARGIN, y))
        min_dist = 999.0
        for t in nearby_towns:
            md = math.hypot(x - t.x, y - t.y)
            if md < min_dist:
                min_dist = md
                if min_dist < config.interact_radius + 10:
                    break
        if min_dist < config.interact_radius + 10:
            continue
        crowding = 0.0
        for t in nearby_towns:
            dist = math.hypot(x - t.x, y - t.y)
            if 1 < dist < 150:
                d_eq = 0.1 * math.sqrt(max(0.0, min(t.population, 500)))
                crowding += (d_eq / dist) ** 0.8
        cands.append((x, y, min_dist, crowding))
        if len(cands) >= 6:
            break
    if not cands:
        _build_site_cache[key] = None
        # prune cache
        if len(_build_site_cache) > 2000:
            _build_site_cache.clear()
        return None
    cands.sort(key=lambda c: (-c[2], c[3]))
    res = (cands[0][0], cands[0][1])
    _build_site_cache[key] = res
    if len(_build_site_cache) > 2000:
        _build_site_cache.clear()
    return res


_build_sites_cache: dict = {}


def find_build_sites(state, config: GameConfig, ref_x: float, ref_y: float,
                     rmin: float = 80, rmax: float = 300, salt: int = 0,
                     who: int = 0, k: int = 3) -> list[tuple[float, float]]:
    """Best-first site plus diverse alternates (salt-shifted spins).
    For search candidates (M2): sites[0] is the heuristic best (the
    find_build_site pick); the rest are distinct alternates for the
    rollout rank to judge."""
    key = (state.turn, int(ref_x), int(ref_y), rmin, rmax, salt, who, state.faction, k)
    if key in _build_sites_cache:
        return _build_sites_cache[key]
    # Reuse the singular (identical ranking: best == sites[0]).
    out: list[tuple[float, float]] = []
    seen: set[tuple[int, int]] = set()
    for dk in range(16):
        site = find_build_site(state, config, ref_x, ref_y, rmin, rmax,
                               salt + dk * 977, who)
        if site is None:
            continue
        q = (round(site[0]), round(site[1]))
        if q in seen:
            continue
        seen.add(q)
        out.append(site)
        if len(out) >= k:
            break
    _build_sites_cache[key] = out
    if len(_build_sites_cache) > 2000:
        _build_sites_cache.clear()
    return out

# ── BotState ──


def void_note_busy(state: "BotState") -> bool:
    """An expansion is already in flight (a note to nowhere-known)."""
    towns = list(state.world.towns)
    for a in state.own_armies():
        tgt = state.army_target(a.id)
        if tgt and all(math.hypot(tgt[0] - t.x, tgt[1] - t.y) > 20
                       for t in towns):
            return True
    return False


def expansion_demand(state: "BotState", config, payback_mult: float = 1.0,
                     void_horizon: int = 0) -> bool:
    """Settler pipeline demand. Void (no known foes): colonies ARE the
    void economy (no serialization — a scout's hop note must not block
    the pipeline), but a marginal colony still needs ~500 turns to repay
    (-500 + ~1/turn): settle-branch passes void_horizon=500, S0-fallback
    keeps 0 (capability contract: probe-then-found is recycle's goal).
    Contested: expand iff the colony stream beats the home marginal
    stream (rate comparison on TRUE spend-aware growth — a fresh site at
    ~0.75/turn vs a crowded home at ~0.3) with horizon to amortize
    (payback_mult scales patience) and one in flight at a time.
    Darkness shields growers; the buzzer falls out."""
    foe_known = any(t.faction != state.faction for t in state.world.towns) \
        or any(a.faction != state.faction for a in state.world.armies)
    if not foe_known:
        # True void (never seen) expands; eviction-void (seen, stale) is
        # NOT peace (empty t2780: stale intel must not read as void).
        if state._foe_first_seen:
            pass  # fall through to contested caution below
        else:
            return config.max_turns - state.turn >= void_horizon
    if void_note_busy(state):
        return False
    turns_left = config.max_turns - state.turn
    if turns_left < payback_mult * 500:
        return False
    home_rate = max((state.get_growth(t.id) or 3.0) for t in state.own_towns()) \
        if state.own_towns() else 3.0
    return 0.75 > home_rate


