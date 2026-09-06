"""Bots common — shared helpers and BotState for rl_game_min scripted tiers."""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army


@dataclass
class _GhostTown:
    """Last-known town for blood matching (mirror only holds living)."""
    id: int
    x: float
    y: float
    faction: int

SITE_MARGIN = 15.0
TRAIN_SURVIVE = 500

PEAK_LOW = 35000
PEAK_HIGH = 65000

# ── Deterministic hash ──

def _hash(turn: int, i: int, salt: int = 0) -> int:
    h = (turn * 73856093) ^ (i * 19349663) ^ (salt * 83492791)
    return h & 0x7FFFFFFF

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

def _memoized(state: "BotState", key, compute):
    """Per-turn compute cache (BotState._memo reset on turn advance and
    wipe): shared geometry (inbound/staging/garrisons) is identical for
    every caller within a decide — compute once, not 7x. World is static
    during decide (orders only queue), so same-turn reuse is exact."""
    m = state.__dict__.get("_memo")
    if m is None or m[0] != state.turn:
        m = state.__dict__["_memo"] = (state.turn, {})
    _, d = m
    if key not in d:
        d[key] = compute()
    return d[key]


def respin_tip(state: "BotState", config, tx: float, ty: float):
    """Re-spin a bad scout tip through the sensible-site optimizer
    (near-tip range): the tip region is virgin void (room max, guns
    usually cold) — the optimizer finds the best site NEAR the tip
    instead of founding at the ray-clamped endpoint. Returns a gated
    site or None (then march home)."""
    for salt, rmax in ((77, 250), (78, 250), (79, 150)):
        site = find_build_site(state, config, tx, ty, rmin=40, rmax=rmax,
                               salt=salt, who=int(tx + ty) & 0xFFFF)
        if site is None:
            continue
        if not tip_safe(state, config, site[0], site[1]):
            continue
        if not site_pays(state, config, site[0], site[1]):
            continue
        return site
    return None


def tip_safe(state: "BotState", config, tx: float, ty: float) -> bool:
    """Foe-gate for foundings (both paths: scout-tip + normal settle):
    the site must be guns-cold (no foe towns/armies within strike
    range). Void sites found at ANY distance (first colonies live 600km
    out, safe while nothing is out there — a distance ceiling killed ALL
    expansion: 0 foundings/3000t). Contested tips recycle home instead
    (aggressive's edge colonies died under foe guns, not from distance)."""
    import math as _math
    los = getattr(config, "line_of_sight", None) or 150.0
    for t in state.world.towns:
        if t.faction == state.faction:
            continue
        if _math.hypot(tx - t.x, ty - t.y) < los:
            return False
    for a in state.world.armies:
        if a.faction == state.faction:
            continue
        if _math.hypot(tx - a.x, ty - a.y) < los:
            return False
    # Room: ray tips clamp at the map edge (all four settlers founded
    # at x/y = 20/980) — edge tips re-spin, interior tips found.
    th = 1000.0
    try:
        ms = config.map_size
        th = ms[0] if isinstance(ms, (list, tuple)) else float(ms)
    except Exception:
        pass
    if min(tx, th - tx, ty, th - ty) < 100.0:
        return False
    # Own-spacing floor (GTO pairs): tips bypassed the 65km floor and
    # stacked at 38km (pro east cluster) — same rule, both paths.
    for t in state.world.towns:
        if t.faction == state.faction:
            if _math.hypot(tx - t.x, ty - t.y) < 65.0:
                return False
    return True


def _batch_ids(events) -> tuple[set, set]:
    """Town/army ids a batch names (growth bookkeeping scope)."""
    towns: set = set()
    armies: set = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        eid = ev.get("id")
        if eid is None:
            continue
        if ev.get("kind") == "town_update":
            towns.add(eid)
        elif ev.get("kind") == "army_update":
            armies.add(eid)
    return towns, armies

# ── Shared build-site finder ──

_build_site_cache: dict[tuple, tuple[float, float] | None] = {}

def find_build_site(state, config: GameConfig, ref_x: float, ref_y: float, rmin: float = 80, rmax: float = 300, salt: int = 0, who: int = 0, far_ok: bool = False) -> tuple[float, float] | None:
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
    _big_site = len(nearby_towns) > 300
    for k in range(16):
        if _big_site and k % 4 == 0 and state.should_yield():
            break  # timeout guard: return best-so-far (healthy budgets never trip)
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
        # Sensible placement (empty_10000 lesson: max-min_dist picked
        # rmax, ratcheted to the map edge, clamped and stacked there).
        # Floor: no founding within 65km of an own town (GTO pairs —
        # fratricide). NO hard ceiling: void expansion must reach far
        # (first colonies live 600km out, safe while guns-cold) — distance
        # is a soft preference (nearest support wins ties) and foe
        # proximity gates at arrival (tip_supported there is foe-gated).
        # Headless bots (no own towns) keep farthest-escape behavior.
        own = [t for t in state.world.towns if t.faction == state.faction]
        d_own = min((math.hypot(x - t.x, y - t.y) for t in own), default=0.0)
        if own and d_own < 65.0:
            continue
        crowding = 0.0
        guns = 0.0
        for t in nearby_towns:
            dist = math.hypot(x - t.x, y - t.y)
            if 1 < dist < 150:
                d_eq = 0.1 * math.sqrt(max(0.0, min(t.population, 500)))
                crowding += (d_eq / dist) ** 0.8
        # GTO placement: don't found under foe guns (pro t4655 colony
        # died in 5 turns — founded in greedy's face). Penalty ∝ foe
        # towns + armies within strike range (LOS), same shape as
        # crowding so the two trade off in one currency. Foe-shadow
        # (doctrine: settle AWAY from believed enemies): known foe towns
        # repel out to 300km (beyond-LOS shadow — direction matters even
        # when guns can't reach yet).
        los = getattr(config, "line_of_sight", None) or 150.0
        for t in state.world.towns:
            if t.faction == state.faction:
                continue
            dist = math.hypot(x - t.x, y - t.y)
            if 1 < dist < los:
                d_eq = 0.1 * math.sqrt(max(0.0, min(t.population, 500)))
                guns += (d_eq / dist) ** 0.8
            elif los <= dist < 300.0:
                guns += 0.5 * (300.0 - dist) / 300.0
        for a in state.world.armies:
            if a.faction == state.faction:
                continue
            dist = math.hypot(x - a.x, y - a.y)
            if 1 < dist < los:
                guns += (0.5 / dist) ** 0.8
        # Growth room (option value): interior sites keep 360° of future
        # slots, edge sites halve them. Penalize the edge deficit (150km
        # room ideal) in crowding currency.
        edge = min(x, th - x, y, th - y)
        room = max(0.0, (150.0 - edge) / 150.0)
        # Near-support (doctrine: not too far — quickly noticed and
        # defended. GTO crowding strategy: settle as close to existing
        # towns as the 65km floor allows — closer = cheaper march +
        # reinforcement; the floor + crowding price the packing, distance
        # beyond 150km pays a STEEP support penalty (far colonies die
        # unsupported). More smaller towns compound faster, but each pays
        # full sunk (army_cost) and needs its own 65km+ of land.
        # Sprawl siting (r131: champ settles far-rich 600km; HEAD's steep
        # 150km penalty herds colonies into near-marginal crowding. far_ok
        # (expander) softens to r63: gentle preference, no wall.
        if far_ok:
            far = max(0.0, (d_own - 400.0) / 200.0) if own else 0.0
        else:
            far = max(0.0, (d_own - 150.0) / 75.0) if own else 0.0
        # Diffusion memory (user: support glows, danger shadows persist
        # across turns — stale danger remembered where scouts died).
        # Quantized (site-stability: headings hold unless memory shifts
        # a lot — 0.25 steps don't flip rankings on noise).
        # Field-memory off for sprawl test (r138: stale shadows may herd
        # colonies marginal; champ's dumb scoring picks rich).
        field = 0.0 if far_ok else -round(state._field_at(x, y) * 4.0) / 4.0 * 0.3
        cands.append((x, y, min_dist, crowding + guns + room + far + field, d_own))
        # No early break: the first spins are not the best (room-passing
        # spins hide late in the sequence — collect all 16, sort picks).
    if not cands:
        _build_site_cache[key] = None
        # prune cache
        if len(_build_site_cache) > 2000:
            _build_site_cache.clear()
        return None
    if own:
        # GTO order: lowest total cost (crowding + guns + edge-room),
        # then nearest support, then nearest the capital hub (short
        # reinforcement chains beat deep ones).
        cap = state.world.faction_capital(state.faction)
        cx, cy = (cap.x, cap.y) if cap else (th / 2, th / 2)
        cands.sort(key=lambda c: (c[3], c[4], math.hypot(c[0] - cx, c[1] - cy)))
    else:
        cands.sort(key=lambda c: (-c[2], c[3]))  # headless escape: farthest
    res = (cands[0][0], cands[0][1])
    _build_site_cache[key] = res
    if len(_build_site_cache) > 2000:
        _build_site_cache.clear()
    return res

# ── BotState ──

@dataclass
class BotState:
    def __init__(self):
        self.faction: int = 0
        self.config: GameConfig | None = None
        self.world: World = World()
        self.turn: int = 0
        self._army_targets: dict[int, tuple[float, float]] = {}
        self._pending_trains: dict[int, int] = {}  # town_id -> expiry turn (when town_update pop drop expected)
        self._pending_builds: dict[int, int] = {}  # army_id -> expiry turn
        self._prev_pop: dict[int, float] = {}
        self._growth: dict[int, float] = {}
        self._cluster_cache: tuple[int, list[list[Town]]] | None = None
        self.deadline: float | None = None  # set per turn by bot_main
        self._stale_cache: dict = {}  # idea 3: (x, y) -> turns-stale, valid for _stale_key
        self.evac_ordered: bool = False  # own MOVE_CAPITAL issued, flight unconfirmed
        self._last_turn: int | None = None  # last payload turn (jump detector)
        self._last_seen: dict = {}  # (kind, id) -> delivery turn (staleness)
        self._first_seen: dict = {}  # (kind, id) -> first delivery turn
        self._taken_at: dict = {}  # town_id -> turn it flipped to mine (Step 4)
        self._memo: tuple = (-1, {})  # (turn, {}) per-turn compute cache
        self._trails: dict = {}  # army_id -> deque[(turn, x, y)] (velocity)
        self._wave_ids: set = set()
        self._wave_hold_until: int = -1
        self._foe_first_seen: dict[int, int] = {}  # faction -> turn first observed
        self._foe_prints: dict[int, int] = {}  # faction -> fielded-force count seen
        self._scout_id: int | None = None  # S0: probing army (hops in _army_targets)
        self._scout_id2: int | None = None  # second concurrent probe (fan-out: different ray)
        self._scout_gen: int = -1  # probe generation (first assign -> 0, legacy ray)
        self._scout_gen1: int = 0
        self._scout_gen2: int = 0
        self._bloodied: dict[int, int] = {}  # foe town id -> turn our army died there
        self._grave_pos: dict[int, tuple] = {}  # foe town id -> last-known (x, y)
        self._mapper: dict[int, int] = {}  # army id -> legs done (post-contact mapping patrols)
        self._tip_grace: dict = {}  # army_id -> turn until which drop_dead spares its note
        self._scout_leg: int = 0
        self._scout_leg2: int = 0
        self._picket: tuple | None = None  # turtle forward tripwire (army_id, since_turn)
        self._draining: bool = False  # Step 5: drain turn done, fly next
        self._stale_key = None
        self._standing_orders: tuple | None = None  # idea 4: (orders, fingerprint)
        self._plan: tuple | None = None  # idea 5: (orders, valid_until_turn)
        self.clock_budget_ms: float | None = None  # idea 6: set by bot_main

    def init(self, config: GameConfig, faction: int):
        self.config = config
        self.faction = faction
        self.world.map_size = config.map_size
        # No map pre-seed (bots never receive geography): empty start, the
        # first payload creates the own capital.

    def _wipe_for_amnesia(self) -> None:
        """Forget EVERYTHING on a confirmed landing (order-flag amnesia).

        Fired when the stream jumps with evac_ordered set: the flight
        happened. World mirror plus all trackers go; config, faction, and
        turn bookkeeping survive (the caller sets them after).
        """
        w = World()
        w.map_size = list(self.config.map_size) if self.config and self.config.map_size else [1000, 1000]
        self.world = w
        self._memo = (-1, {})
        self._army_targets = {}
        self._pending_trains = {}
        self._pending_builds = {}
        self._prev_pop = {}
        self._growth = {}
        self._cluster_cache = None
        self._stale_cache = {}
        self._stale_key = None
        self._standing_orders = None
        self._plan = None
        self._last_seen = {}
        self._first_seen = {}
        self._taken_at = {}
        self._trails = {}
        self._tip_grace = {}
        self.__dict__.pop("_queue", None)
        self.__dict__.pop("_march_origin", None)
        self._wave_ids = set()
        self._foe_first_seen = {}
        self._foe_prints = {}
        self._bloodied = {}
        self._grave_pos = {}
        self._mapper = {}
        self._picket = None
        self._draining = False
        self._scout_id = None
        self._scout_leg = 0
        self._scout_id2 = None
        self._scout_leg2 = 0
        self._scout_gen1 = 0
        self._scout_gen2 = 0
        self._scout_gen = -1  # probe generation: first probe flies the legacy
        # faction ray (gen 0); each new scout rotates by the golden angle
        self._wave_hold_until = -1

    def _stamp_cover(self, x: float, y: float) -> None:
        """Sector coverage stamp (doctrine: idle patrols sweep stalest
        ground). 4x4 sectors over the map; every observed position marks
        its sector seen-this-turn."""
        try:
            size = self.config.map_size if self.config is not None else [1000, 1000]
            n = 4
            cx = min(n - 1, max(0, int(x / size[0] * n)))
            cy = min(n - 1, max(0, int(y / size[1] * n)))
            self.__dict__.setdefault("_cover", {})[(cx, cy)] = self.turn
        except Exception:
            pass

    def _diffuse_explore_field(self) -> None:
        """Exploration pheromone field (user: diffusion exploration with
        sources/sinks). 16x16 staleness field, persisted: every observed
        position splats freshness (sink: seen = 0), all cells evaporate
        upward (+0.5/10t toward cap 10 = sources: unvisited ground glows
        staler), then 3x3 blur (gradients stay smooth). Coverage descends
        it (climb to stalest); sits alongside the 4x4 stamp grid (which
        stays for cheap staleness reads)."""
        try:
            n = 16
            cap = 10.0
            size = self.config.map_size if self.config is not None else [1000, 1000]
            f = self.__dict__.setdefault("_explore_field", {})
            for k in list(f):
                f[k] = min(cap, f[k] + 0.5)
                if f[k] >= cap and k in f:
                    pass
            for (kind, eid), t in list(self._last_seen.items()):
                if t < self.turn - 10:
                    continue
                if kind == "town":
                    u = self.world.get_town(eid)
                    x, y = (u.x, u.y) if u else (None, None)
                else:
                    a = self.world.get_army(eid)
                    x, y = (a.x, a.y) if a else (None, None)
                if x is None:
                    continue
                cx = min(n - 1, max(0, int(x / size[0] * n)))
                cy = min(n - 1, max(0, int(y / size[1] * n)))
                f[(cx, cy)] = 0.0
            blur: dict = {}
            for (cx, cy), v in f.items():
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if 0 <= nx < n and 0 <= ny < n:
                            w = 0.5 if (nx, ny) == (cx, cy) else 0.0625
                            blur[(nx, ny)] = blur.get((nx, ny), 0.0) + v * w
            self.__dict__["_explore_field"] = blur
        except Exception:
            pass

    def _explore_at(self, x: float, y: float) -> float:
        """Sample exploration staleness (high = unvisited, climb it)."""
        try:
            n = 16
            size = self.config.map_size if self.config is not None else [1000, 1000]
            cx = min(n - 1, max(0, int(x / size[0] * n)))
            cy = min(n - 1, max(0, int(y / size[1] * n)))
            return self.__dict__.get("_explore_field", {}).get((cx, cy), 10.0)
        except Exception:
            return 10.0

    def _diffuse_site_field(self) -> None:
        """Siting diffusion field (user: sources/sinks with memory).
        10x10 grid, persisted per turn: own towns splat +1 (support
        source), foe towns -2 and foe armies -1 (danger sinks), everything
        decays x0.98 (memory fades), then one 3x3 blur (diffusion spreads
        intel to neighbors — danger casts a shadow, support a glow).
        find_build_site samples it (stale danger remembered where scouts
        died; support glows near the empire)."""
        try:
            n = 10
            size = self.config.map_size if self.config is not None else [1000, 1000]
            f = self.__dict__.setdefault("_site_field", {})
            for k in list(f):
                f[k] *= 0.85  # per-10t tick
                if abs(f[k]) < 0.01:
                    del f[k]
            _dead = dead_foes(self, self.config)
            for t in self.world.towns:
                if t.faction != self.faction and t.faction in _dead:
                    continue  # dead rivals cast no shadow (r113 unfreeze)
                cx = min(n - 1, max(0, int(t.x / size[0] * n)))
                cy = min(n - 1, max(0, int(t.y / size[1] * n)))
                f[(cx, cy)] = f.get((cx, cy), 0.0) + (1.0 if t.faction == self.faction else -2.0)
            for a in self.world.armies:
                if a.faction == self.faction:
                    continue
                cx = min(n - 1, max(0, int(a.x / size[0] * n)))
                cy = min(n - 1, max(0, int(a.y / size[1] * n)))
                f[(cx, cy)] = f.get((cx, cy), 0.0) - 1.0
            blur: dict = {}
            for (cx, cy), v in f.items():
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if 0 <= nx < n and 0 <= ny < n:
                            w = 0.5 if (nx, ny) == (cx, cy) else 0.0625
                            blur[(nx, ny)] = blur.get((nx, ny), 0.0) + v * w
            self.__dict__["_site_field"] = blur
        except Exception:
            pass

    def _field_at(self, x: float, y: float) -> float:
        """Sample the siting diffusion field (support+, danger-)."""
        try:
            n = 10
            size = self.config.map_size if self.config is not None else [1000, 1000]
            cx = min(n - 1, max(0, int(x / size[0] * n)))
            cy = min(n - 1, max(0, int(y / size[1] * n)))
            return self.__dict__.get("_site_field", {}).get((cx, cy), 0.0)
        except Exception:
            return 0.0

    def _diffuse_threat_field(self) -> None:
        """Threat diffusion field (cool grids: foe armies as moving danger
        sinks, fast decay (x0.7/10t — armies move!), 3x3 blur. Scout hops
        and settler tips sample it (gradient descent away from danger),
        replacing binary bends with smooth cost."""
        try:
            n = 10
            size = self.config.map_size if self.config is not None else [1000, 1000]
            f = self.__dict__.setdefault("_threat_field", {})
            for k in list(f):
                f[k] *= 0.7
                if abs(f[k]) < 0.01:
                    del f[k]
            for a in self.world.armies:
                if a.faction == self.faction:
                    continue
                cx = min(n - 1, max(0, int(a.x / size[0] * n)))
                cy = min(n - 1, max(0, int(a.y / size[1] * n)))
                f[(cx, cy)] = f.get((cx, cy), 0.0) - 1.0
            blur: dict = {}
            for (cx, cy), v in f.items():
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if 0 <= nx < n and 0 <= ny < n:
                            w = 0.5 if (nx, ny) == (cx, cy) else 0.0625
                            blur[(nx, ny)] = blur.get((nx, ny), 0.0) + v * w
            self.__dict__["_threat_field"] = blur
        except Exception:
            pass

    def _diffuse_oppor_field(self) -> None:
        """Opportunity diffusion field (campaigns: rich foe towns as prize
        sources, slow decay (x0.9/10t — towns don't move!), 3x3 blur.
        Raid scoring samples it (cluster premium: takes near other rich
        towns seed followup-rich campaigns)."""
        try:
            n = 10
            size = self.config.map_size if self.config is not None else [1000, 1000]
            f = self.__dict__.setdefault("_oppor_field", {})
            for k in list(f):
                f[k] *= 0.9
                if abs(f[k]) < 0.05:
                    del f[k]
            for t in self.world.towns:
                if t.faction == self.faction:
                    continue
                cx = min(n - 1, max(0, int(t.x / size[0] * n)))
                cy = min(n - 1, max(0, int(t.y / size[1] * n)))
                f[(cx, cy)] = f.get((cx, cy), 0.0) + min(3.0, t.population / 20000.0)
            blur: dict = {}
            for (cx, cy), v in f.items():
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if 0 <= nx < n and 0 <= ny < n:
                            w = 0.5 if (nx, ny) == (cx, cy) else 0.0625
                            blur[(nx, ny)] = blur.get((nx, ny), 0.0) + v * w
            self.__dict__["_oppor_field"] = blur
        except Exception:
            pass

    def _oppor_at(self, x: float, y: float) -> float:
        """Sample the opportunity field (prize neighborhood)."""
        try:
            n = 10
            size = self.config.map_size if self.config is not None else [1000, 1000]
            cx = min(n - 1, max(0, int(x / size[0] * n)))
            cy = min(n - 1, max(0, int(y / size[1] * n)))
            return self.__dict__.get("_oppor_field", {}).get((cx, cy), 0.0)
        except Exception:
            return 0.0

    def _threat_at(self, x: float, y: float) -> float:
        """Sample the threat field (negative near foe armies)."""
        try:
            n = 10
            size = self.config.map_size if self.config is not None else [1000, 1000]
            cx = min(n - 1, max(0, int(x / size[0] * n)))
            cy = min(n - 1, max(0, int(y / size[1] * n)))
            return self.__dict__.get("_threat_field", {}).get((cx, cy), 0.0)
        except Exception:
            return 0.0

    def _apply_update(self, ev: dict) -> None:
        """Upsert one state update (absolute). Unknown kinds ignored."""
        from collections import deque
        kind = ev.get("kind")
        eid = ev.get("id")
        if eid is None:
            return
        if kind == "town_update":
            if not ev.get("population"):
                self._remove_town(eid)
            else:
                t = self.world.get_town(eid)
                if t is None:
                    t = Town(id=eid, faction=int(ev.get("faction", -1)),
                             x=float(ev.get("x", 0.0)), y=float(ev.get("y", 0.0)),
                             population=float(ev.get("population", 0.0)),
                             is_capital=bool(ev.get("is_capital", False)))
                    self.world.towns.append(t)
                else:
                    if t.faction == self.faction and int(ev.get("faction", t.faction)) != self.faction:
                        # Lost a town (seen mine, now foe): ex-own assaults
                        # need fresh intel (r91 fratricide).
                        self.__dict__.setdefault("_lost_towns", set()).add(eid)
                        self.__dict__.setdefault("_lost_turn", {})[eid] = self.turn
                    t.faction = int(ev.get("faction", t.faction))
                    t.x = float(ev.get("x", t.x))
                    t.y = float(ev.get("y", t.y))
                    t.population = float(ev.get("population", t.population))
                    t.is_capital = bool(ev.get("is_capital", t.is_capital))
            self._last_seen[("town", eid)] = self.turn
            self._first_seen.setdefault(("town", eid), self.turn)
            # Drop-watch (r119: ghost towns compound monotonically; live
            # towns sawtooth (prints). A >20% drop below max-seen = activity
            # = somebody home).
            _tp = float(ev.get("population", 0.0))
            _mx = self.__dict__.setdefault("_town_maxpop", {})
            if _tp > _mx.get(eid, 0.0):
                _mx[eid] = _tp
            elif _tp < 0.8 * _mx.get(eid, 0.0):
                _tf = ev.get("faction", None)
                if _tf is not None and int(_tf) != self.faction:
                    self.__dict__.setdefault("_foe_active", {})[int(_tf)] = self.turn
            self._stamp_cover(float(ev.get("x", 0.0)), float(ev.get("y", 0.0)))
        elif kind == "army_update":
            if ev.get("alive") is False:
                self._remove_army(eid)
            else:
                a = self.world.get_army(eid)
                if a is None:
                    a = Army(id=eid, faction=int(ev.get("faction", -1)),
                             x=float(ev.get("x", 0.0)), y=float(ev.get("y", 0.0)),
                             is_viceroy=bool(ev.get("is_viceroy", False)))
                    self.world.armies.append(a)
                else:
                    a.faction = int(ev.get("faction", a.faction))
                    a.x = float(ev.get("x", a.x))
                    a.y = float(ev.get("y", a.y))
                    a.is_viceroy = bool(ev.get("is_viceroy", a.is_viceroy))
                tr = self._trails.get(eid)
                if tr is None:
                    tr = self._trails[eid] = deque(maxlen=4)
                tr.append((self.turn, a.x, a.y))
            self._last_seen[("army", eid)] = self.turn
            self._first_seen.setdefault(("army", eid), self.turn)
            _ff = ev.get("faction", None)
            if _ff is not None and int(_ff) != self.faction:
                self.__dict__.setdefault("_foe_army_seen", {})[int(_ff)] = self.turn
            self._stamp_cover(float(ev.get("x", 0.0)), float(ev.get("y", 0.0)))
        # else: tolerant — battles are gone, unknown kinds ignored.

    def _remove_town(self, tid: int) -> None:
        t = self.world.get_town(tid)
        if t is not None:
            # Last-known position (blood matching post-dates removals:
            # town tombstones arrive with/before army tombstones).
            self.__dict__.setdefault("_town_lastpos", {})[tid] = (t.x, t.y, t.faction)
        self.world.remove_town(tid)
        self._pending_trains.pop(tid, None)
        self._growth.pop(tid, None)
        self._prev_pop.pop(tid, None)

    def _note_grave(self, tid: int, x: float, y: float) -> None:
        """Record a grave (blood + last-known position). Positions let
        later notes match dead towns (mirror only holds the living)."""
        self._bloodied[tid] = self.turn
        # Fortress learning (r110: meatgrinders repeat at the SAME town.
        # Each death doubles the avoid window: 150, 300, 600... cap 2400t).
        _bc = self.__dict__.setdefault("_blood_count", {})
        _bc[tid] = _bc.get(tid, 0) + 1
        self.__dict__.setdefault("_grave_pos", {})[tid] = (x, y)

    def _remove_army(self, aid: int) -> None:
        # Grave memory (anti-onesie): our army dying at a known foe town
        # means garrison the intel missed — bloodied towns refuse lone
        # probes until a full pack is ready (dead armies tell no tales,
        # so without this the stale s=0 re-arms the probe forever).
        a = self.world.get_army(aid)
        tr = self._trails.get(aid)
        if a is not None and a.faction == self.faction:
            interact = 10.0
            if self.config is not None:
                interact = float(getattr(self.config, "interact_radius", 10.0) or 10.0)
            # Candidate death sites: NOTE target first (where it was sent —
            # exact even in fog), last-seen trail second (stale by mail lag).
            sites = []
            tgt = self._army_targets.get(aid)
            if tgt is not None:
                sites.append(tgt)
            if tr:
                sites.append((tr[-1][1], tr[-1][2]))
            for sx, sy in sites:
                hit = False
                cands = list(self.world.towns)
                for tid, (lx, ly, lf) in self.__dict__.get("_town_lastpos", {}).items():
                    if self.world.get_town(tid) is None:
                        cands.append(_GhostTown(tid, lx, ly, lf))
                for t in cands:
                    if t.faction != self.faction and abs(t.x - sx) < interact + 15 \
                            and abs(t.y - sy) < interact + 15 \
                            and math.hypot(t.x - sx, t.y - sy) <= interact + 15:
                        self._note_grave(t.id, t.x, t.y)
                        hit = True
                        break
                if hit:
                    break
        self.world.remove_army(aid)
        self._army_targets.pop(aid, None)
        self._trails.pop(aid, None)

    def note_orders(self, orders: list[str]) -> None:
        """Track issued orders locally (delay-aware decisions + evac flag)."""
        for o in orders:
            if not isinstance(o, str):
                continue
            try:
                if o.startswith("MOVE_TO"):
                    parts = o.split()
                    if len(parts) == 6:
                        self.note_move(int(parts[1]), float(parts[4]), float(parts[5]))
                    elif len(parts) == 4:
                        self.note_move(int(parts[1]), float(parts[2]), float(parts[3]))
                elif o.startswith("BUILD"):
                    self.note_build(int(o.split()[1]))
                elif o.startswith("TRAIN"):
                    self.note_train(int(o.split()[1]))
                elif o.startswith("MOVE_CAPITAL"):
                    self.evac_ordered = True
            except Exception:
                pass

    def update(self, turn: int, events: list[dict]):
        events = [ev for ev in (events or []) if isinstance(ev, dict)]
        # Order-flag amnesia: a jump with evac_ordered set means the flight
        # happened → wipe everything and rebuild from this batch. Sequential
        # means the order FAILED → clear the flag, no wipe. The flag is
        # consumed either way; config/faction/turn bookkeeping survive.
        jumped = self._last_turn is not None and turn > self._last_turn + 1
        if self.evac_ordered:
            if jumped:
                self._wipe_for_amnesia()
            self.evac_ordered = False
        # Idea 1: growth is folded per applied update and reset on turn
        # advance.
        if turn != self.turn:
            self._growth = {}
            if turn % 10 == 0:
                self._diffuse_site_field()  # diffusion ticks 10t (perf)
                self._diffuse_threat_field()
                self._diffuse_oppor_field()
                self._diffuse_explore_field()
        self.turn = turn
        self._last_turn = turn
        # Snapshot prev pops for towns this batch names, then apply absolutely.
        touched_towns, _ = _batch_ids(events)
        prev = {}
        prev_faction = {}
        for tid in touched_towns:
            t = self.world.get_town(tid)
            if t is not None:
                prev[tid] = t.population
                prev_faction[tid] = t.faction
        known_armies = {a.id for a in self.world.armies}
        for ev in events:
            self._apply_update(ev)
            # Step 4: take-time (faction flip TO mine) for conquest guards.
            if ev.get("kind") == "town_update":
                _tid = ev.get("id")
                _nt = self.world.get_town(_tid) if _tid is not None else None
                if _nt is not None and _nt.faction == self.faction \
                        and _tid in prev_faction and prev_faction[_tid] != self.faction:
                    self._taken_at[_tid] = self.turn
        if events:
            # Field flips (faction/flag) don't change list lengths, so the
            # world's index wouldn't rebuild without this (mark_dirty
            # contract: production mutation sites all mark).
            self.world.mark_dirty()
        # Spend-aware growth: own train drops (-cost per own spawn) and
        # capture halves (faction flip) are not growth. Credits apply in a
        # pre-pass (pure addition — commutes across same-turn chunks, so
        # incremental replay matches). A train drop misread as collapse
        # poisons hopelessness (guard_duty: a correct muster read as -997
        # and fired a mystery evac).
        cost = getattr(getattr(self, "config", None), "army_cost", 1000) or 1000
        for ev in events:
            ef = ev.get("faction")
            if isinstance(ef, int) and ef != self.faction:
                self._foe_first_seen.setdefault(ef, self.turn)
                if ev.get("kind") == "army_update":
                    eid = ev.get("id")
                    if eid is not None and eid not in known_armies:
                        self._foe_prints[ef] = self._foe_prints.get(ef, 0) + 1
                        self.__dict__.setdefault("_foe_last_print", {})[ef] = self.turn
            if ev.get("kind") == "army_update" and ev.get("faction") == self.faction:
                eid = ev.get("id")
                if eid is not None and eid not in known_armies:
                    a = self.world.get_army(eid)
                    if a is not None:
                        near = [t for t in self.world.towns
                                if t.faction == self.faction and math.hypot(a.x - t.x, a.y - t.y) <= 20.0]
                        if near:
                            host = min(near, key=lambda t: math.hypot(a.x - t.x, a.y - t.y))
                            self._growth[host.id] = self._growth.get(host.id, 0.0) + cost
        for tid in touched_towns:
            t = self.world.get_town(tid)
            if t is None:
                self._growth.pop(tid, None)
                continue
            if tid not in prev:
                self._growth.setdefault(tid, 0.0)
                continue
            if tid in prev_faction and prev_faction[tid] != t.faction:
                # captured: strip the halve, keep the growth (chunk-proof:
                # same result whether the flip shares a batch or not).
                eff = getattr(getattr(self, "config", None), "build_efficiency", 0.5) or 0.5
                self._growth[tid] = self._growth.get(tid, 0.0) + (t.population - prev[tid] * (1.0 - eff))
                continue
            self._growth[tid] = self._growth.get(tid, 0.0) + (t.population - prev[tid])
        self._prev_pop = prev
        # Dead-army tracker cleanup happens in _remove_army at apply time.
        # expire pending trains whose pop drop has arrived or timed out
        for tid in list(self._pending_trains.keys()):
            t = self.world.get_town(tid)
            if t is None or self.turn > self._pending_trains[tid]:
                del self._pending_trains[tid]
            elif t.population < 1200:
                # pop dropped, train confirmed
                del self._pending_trains[tid]
        for aid in list(self._pending_builds.keys()):
            if self.world.get_army(aid) is None or self.turn > self._pending_builds[aid]:
                self._pending_builds.pop(aid, None)
        # No engine intent mirror (D1: destinations never go over the wire).
        # Own intent lives in _army_targets via note_move; foe intent is
        # inferred from position trails by BotForecast.
        self.world._turn = turn

    def note_move(self, army_id: int, tx: float, ty: float):
        # Pendulum-breaker (r56 lesson: pro marched 91km for 1 capture).
        # Target flip-flop (3+ distinct notes within 300t) stands the army
        # down at its nearest own town (fresh origin: amnesty-exempt 300t).
        # Shuttles waste marches; standing down frees the body for real
        # tasking next rotation.
        hist = self.__dict__.setdefault("_note_hist", {}).setdefault(army_id, [])
        hist.append((round(tx / 50.0), round(ty / 50.0), self.turn))
        while len(hist) > 4:
            hist.pop(0)
        # Flip-flop (3+ distinct in 1000t) OR alternation (A..A revisit:
        # r75's 1.4M km shuttle ran 2 targets; r81's redeploys drift sel
        # every 500t — wide windows catch slow drift and fast shuttles).
        if len(hist) == 4 and hist[-1][2] - hist[0][2] <= 1000 \
                and (len({h[:2] for h in hist}) >= 3
                     or hist[-1][:2] == hist[-3][:2] != hist[-2][:2]):
            home = min((t for t in self.world.towns if t.faction == self.faction),
                       key=lambda t: __import__("math").hypot(
                           (self.world.get_army(army_id) or t).x - t.x,
                           (self.world.get_army(army_id) or t).y - t.y),
                       default=None)
            if home is not None:
                tx, ty = home.x, home.y
                hist.clear()
        self._army_targets[army_id] = (tx, ty)
        # March origin for dead-reckoning (own intent is exact: the engine
        # marches deterministically, but delivery goes silent for holding
        # armies and lags marching ones — botpos can sit 30km behind truth
        # forever, defeating arrival detection; reckoned_pos fixes it).
        a = self.world.get_army(army_id)
        if a is not None:
            self.__dict__.setdefault("_march_origin", {})[army_id] = (a.x, a.y, self.turn)

    def reckoned_pos(self, config, aid: int) -> tuple[float, float]:
        """Dead-reckoned own-army position: march origin + speed x elapsed
        toward the noted dest (capped). Exact for compliant marches."""
        import math as _math
        a = self.world.get_army(aid)
        if a is None:
            return (0.0, 0.0)
        tgt = self._army_targets.get(aid)
        org = self.__dict__.get("_march_origin", {}).get(aid)
        if tgt is None or org is None:
            return (a.x, a.y)
        fx, fy, t0 = org
        speed = max(1.0, config.army_speed) if config else 50.0
        dx, dy = tgt[0] - fx, tgt[1] - fy
        full = _math.hypot(dx, dy)
        if full < 1e-9:
            return (a.x, a.y)
        step = speed * max(0, self.turn - t0)
        if step >= full:
            return (tgt[0], tgt[1])
        return (fx + dx * step / full, fy + dy * step / full)

    def note_build(self, army_id: int):
        # BUILD-retry cap (r62 lesson: 103 armies re-BUILDing failed
        # sites 1500t+ — each BUILD refreshes pending, never expiring).
        # 3 tries at a site, then abandon (pop note+pending: re-decide
        # settles elsewhere or patrols). Success founds (town_spawn) and
        # the army leaves the pending set via expiry.
        tries = self.__dict__.setdefault("_build_tries", {})
        tries[army_id] = tries.get(army_id, 0) + 1
        if tries[army_id] > 3:
            tries.pop(army_id, None)
            self._pending_builds.pop(army_id, None)
            self._army_targets.pop(army_id, None)
            self.__dict__.get("_march_origin", {}).pop(army_id, None)
            return
        cap = self.world.faction_capital(self.faction)
        tgt = self._army_targets.get(army_id) or self.army_target(army_id)
        if cap and tgt:
            dist = math.hypot(cap.x - tgt[0], cap.y - tgt[1])
            delay = max(1, math.ceil(dist / (self.config.info_speed if self.config else 150)))
        else:
            delay = 1
        self._pending_builds[army_id] = self.turn + delay + 1

    def has_pending_build(self, army_id: int) -> bool:
        return army_id in self._pending_builds and self.turn <= self._pending_builds[army_id]

    def note_train(self, town_id: int):
        cap = self.world.faction_capital(self.faction)
        town = self.world.get_town(town_id)
        if cap and town:
            dist = math.hypot(cap.x - town.x, cap.y - town.y)
            delay = max(1, math.ceil(dist / (self.config.info_speed if self.config else 150)))
        else:
            delay = 1
        # Cover the execution queue too (r134: pending expired while a
        # queued TRAIN awaited its 1/town slot -> duplicate re-issue ->
        # multi-execute suicide. +30 covers queue depth).
        self._pending_trains[town_id] = self.turn + delay + 30

    # Ideas 4+5: quiet-turn skip and plan queue.
    def is_quiet(self, events) -> bool:
        """Idea 4: quiet iff the payload is empty — any update breaks sleep."""
        for ev in events or []:
            if isinstance(ev, dict):
                return False
        return True

    def push_plan(self, orders, valid_until_turn: int) -> None:
        """Idea 5: precomputed orders to issue verbatim until expiry/intel."""
        self._plan = (list(orders), valid_until_turn)

    def _live_plan(self, events):
        p = self._plan
        if not p:
            return None
        orders, valid_until = p
        if self.turn > valid_until or not self.is_quiet(events):
            self._plan = None
            return None
        return orders

    def queue_order(self, fire_turn: int, order: str, tag: str | None = None) -> None:
        """Schedule a command for a future turn (bot-side command queue).
        Fired by bot_main after the fresh decide (fresh re-tasks win:
        MOVE_TO validates the note still matches, TRAIN re-checks
        affordability, BUILD re-checks arrival (defers if late)). Uses:
        scout-patrol legs (pre-programmed paths, timed to arrive as the
        army does) and settler MOVE_TO -> BUILD chains (the BUILD fires
        on schedule even if arrival notes die). Turn-based (no
        wall-clock) — fully deterministic."""
        q = self.__dict__.setdefault("_queue", [])
        q.append([int(fire_turn), str(order), tag])
        try:
            parts = str(order).split()
            if parts[0] == "MOVE_TO" and len(parts) >= 6:
                self.note_move(int(parts[1]), float(parts[4]), float(parts[5]))
        except Exception:
            pass

    def cancel_queued(self, tag: str) -> None:
        """Drop all queued commands with tag (re-tasked armies cancel
        their scheduled legs/chains)."""
        q = self.__dict__.get("_queue")
        if q:
            self.__dict__["_queue"] = [e for e in q if e[2] != tag]

    def pop_due_orders(self, config) -> list[str]:
        """Fire due queued commands (fire_turn <= turn) with validation.
        Late settler BUILDs defer (re-queue +3) instead of dropping —
        slow marches still found. MOVE_CAPITAL + unknown never auto-fire
        (too final). Returns fired orders."""
        q = self.__dict__.get("_queue", [])
        out: list[str] = []
        keep: list = []
        for fire, order, tag in sorted(q):
            if fire > self.turn:
                keep.append([fire, order, tag])
                continue
            parts = order.split()
            kind = parts[0] if parts else ""
            if kind == "MOVE_TO" and len(parts) >= 6:
                try:
                    aid = int(parts[1])
                    a = self.world.get_army(aid)
                    if a is None:
                        continue
                    cur = self.army_target(aid)
                    if cur is not None and (abs(cur[0] - float(parts[4])) > 1e-6
                                           or abs(cur[1] - float(parts[5])) > 1e-6):
                        continue
                    out.append(order)
                except Exception:
                    continue
            elif kind == "TRAIN" and len(parts) >= 2:
                try:
                    t = self.world.get_town(int(parts[1]))
                    cost = getattr(config, "army_cost", 500) or 500
                    thresh = getattr(config, "death_threshold", 500) or 500
                    if t is None or t.faction != self.faction:
                        continue
                    if t.population - cost < thresh - 1e-9:
                        continue
                    out.append(order)
                except Exception:
                    continue
            elif kind == "BUILD" and len(parts) >= 4:
                try:
                    aid = int(parts[1])
                    a = self.world.get_army(aid)
                    if a is None or self.has_pending_build(aid):
                        continue
                    bx, by = float(parts[2]), float(parts[3])
                    ir = getattr(config, "interact_radius", 10.0) or 10.0
                    rx, ry = self.reckoned_pos(config, aid)
                    if math.hypot(rx - bx, ry - by) > ir + 10:
                        keep.append([self.turn + 3, order, tag])
                        continue
                    out.append(order)
                except Exception:
                    continue
        self.__dict__["_queue"] = keep
        return out

    def _fingerprint(self):
        """Idea 4: decide-relevant state summary. Replay is valid only while
        this is stable: membership (ids/factions), quantized pops, exact-ish
        positions (any real move invalidates), own noted targets, pending
        trackers, and a 25-turn heartbeat bounding all other staleness."""
        fp = (
            tuple(sorted((t.id, t.faction, int(t.population) // 100) for t in self.world.towns)),
            tuple(sorted((a.id, a.faction, int(a.x), int(a.y)) for a in self.world.armies)),
            tuple(sorted(self._pending_trains.items())),
            tuple(sorted(self._pending_builds.items())),
            tuple(sorted(self._army_targets.items())),
            tuple(sorted((e[0], e[1], e[2]) for e in self.__dict__.get("_queue", []))),
            tuple(sorted(self._foe_first_seen.items())),
            tuple(sorted(self._foe_prints.items())),
            tuple(sorted(self._first_seen.items())),
            tuple(sorted(self._taken_at.items())),
            self._draining,
            self._picket,
            self._scout_id,
            self._scout_id2,
            self.turn // 25,
        )
        return fp

    def cached_or_decide(self, decide_fn, config, events):
        """Ideas 4+5: plan > quiet-cache > fresh decide.

        Fresh results are cached only on fully-applied quiet turns, so the
        cache never serves state computed from a partial backlog; and replay
        requires a stable fingerprint, so affordability/growth/marches force
        a fresh decide even with no military events.
        """
        plan = self._live_plan(events)
        if plan is not None:
            return list(plan)
        quiet = self.is_quiet(events)
        fp = self._fingerprint()
        if quiet and self._standing_orders is not None:
            if self._standing_orders[1] == fp:
                return list(self._standing_orders[0])
        orders = decide_fn(self, config)
        if quiet:
            # Fingerprint AFTER decide: personalities note moves/trains
            # mid-decide, and replay must compare against that post-state.
            self._standing_orders = (list(orders), self._fingerprint())
        else:
            self._standing_orders = None
        return orders

    def effort(self, clock_ms) -> str:
        """Idea 6: None -> full, under 25ms -> low, else full."""
        if clock_ms is None:
            return "full"
        try:
            return "low" if float(clock_ms) < 25 else "full"
        except Exception:
            return "full"

    def stale_turns(self, x: float, y: float) -> float:
        """Idea 3: memoized dist-to-capital/info_speed.

        Towns never move, so per-turn answers repeat; the cache is keyed
        by (turn, capital id+pos) and cleared whenever any of those change.
        """
        cap = self.world.faction_capital(self.faction)
        key = (self.turn,
               cap.id if cap else -1,
               cap.x if cap else 0.0,
               cap.y if cap else 0.0)
        if key != self._stale_key:
            self._stale_key = key
            self._stale_cache = {}
        ck = (x, y)
        v = self._stale_cache.get(ck)
        if v is None:
            speed = (self.config.info_speed if self.config else 150) or 150
            cx, cy = (cap.x, cap.y) if cap else (500.0, 500.0)
            v = math.hypot(x - cx, y - cy) / max(1, speed)
            self._stale_cache[ck] = v
        return v

    def can_train_here(self, town: Town, conservative: bool = False) -> bool:
        if not can_train_safely(town, conservative):
            return False
        # distance-aware safety: distant towns appear 1-2 turns stale, require extra buffer
        cap = self.world.faction_capital(self.faction)
        if cap:
            dist = math.hypot(cap.x - town.x, cap.y - town.y)
            turns_behind = self.stale_turns(town.x, town.y)
            # require extra 400 pop per turn of staleness (growth ~3/turn at 5k, but TRAIN costs 1000)
            extra = int(turns_behind * 400)
            if town.population < (2600 if conservative else 1600) + extra:
                # only enforce extra if distant (>100 km)
                if dist > 100 and town.population < (2600 if conservative else 1600) + extra:
                    return False
        # pending TRAIN not yet confirmed via pop_change
        if town.id in self._pending_trains and self.turn <= self._pending_trains[town.id]:
            return False
        return True

    def own_towns(self) -> list[Town]:
        return [t for t in self.world.towns if t.faction == self.faction]

    def own_armies(self) -> list[Army]:
        return [a for a in self.world.armies if a.faction == self.faction]

    def army_has_target(self, aid: int) -> bool:
        a = self.world.get_army(aid)
        if a and a.has_target:
            return True
        return aid in self._army_targets

    def army_target(self, aid: int) -> tuple[float, float] | None:
        a = self.world.get_army(aid)
        if a and a.has_target:
            return (a.target_x, a.target_y)
        return self._army_targets.get(aid)

    def time_remaining_ms(self) -> float:
        if self.deadline is None:
            return 9999
        return max(0, (self.deadline - time.time()) * 1000)

    # Idea 9 margins (measured 2026-09: instant round-trip med 0.15ms,
    # p99 0.45ms, max 11ms scheduling spike in 1000). Total unusable 8ms
    # of the clock: 3ms flush margin + 5ms think margin. Covers stalls up
    # to ~7ms landing inside the sub-ms check-to-flush window (rare^2);
    # the old 30ms double margin (15+15) is not reinstated without data.
    FLUSH_MARGIN_MS = 3.0
    YIELD_AT_MS = 5.0

    def should_yield(self) -> bool:
        return self.time_remaining_ms() < self.YIELD_AT_MS

    def get_growth(self, town_id: int) -> float:
        v = self._growth.get(town_id, 0.0)
        return v if isinstance(v, (int, float)) else 0.0

    def overcrowded_clusters(self) -> list[list[Town]]:
        if self._cluster_cache and self._cluster_cache[0] == self.turn:
            return self._cluster_cache[1]
        cands = []
        for t in self.own_towns():
            if t.id in self._pending_trains and self.turn <= self._pending_trains[t.id]:
                continue
            g = self._growth.get(t.id, 0)
            if g < -1e-9 and 500 <= t.population < 35000:
                cands.append(t)
        clusters: list[list[Town]] = []
        visited = set()
        for t in cands:
            if t.id in visited:
                continue
            queue = [t]; comp: list[Town] = []; visited.add(t.id)
            while queue:
                cur = queue.pop()
                comp.append(cur)
                for other in cands:
                    if other.id in visited:
                        continue
                    if math.hypot(cur.x - other.x, cur.y - other.y) <= 150:
                        visited.add(other.id)
                        queue.append(other)
            clusters.append(comp)
        self._cluster_cache = (self.turn, clusters)
        return clusters

    def should_train_for_overcrowding(self, town: Town) -> bool:
        for cluster in self.overcrowded_clusters():
            if town.id not in {t.id for t in cluster}:
                continue
            # Stable rep (id-seeded tie-break, never the turn — turn-keyed
            # reps flap cluster targeting nightly (same disease as sites).
            rep = min(cluster, key=lambda t: (t.population, self._growth.get(t.id, 0), _hash(t.id, t.id, 99)))
            return rep.id == town.id
        return False

# ── BotForecast: separate from BotState, constructed from it ──

# S0: no-contact scout (Step 2 prerequisite) — probe before founding.
# MIN_TURN 1: the first payload already carries turn-0 observations, so a
# contact game shows foes immediately; anything unseen at turn 1 is void.
# HOPS of 50km (one march-turn each), replotted only while stationary:
# mid-course retargeting of a moving army is structurally dead (2-turn
# intel lag vs 1-step messenger projection + 10km tolerance), so the
# probe hops and waits for arrival-intel. Hop endpoints sit inside
# already-observed ground, so with known-town avoidance the probe cannot
# blunder into a capture (trap lesson). After SCOUT_HOPS with no contact
# it founds (settle-as-scout fallback).
SCOUT_MIN_TURN = 1
SCOUT_HOPS = 12
SCOUT_HOP_KM = 50.0


def _dark(state: "BotState", window: int = 300) -> bool:
    """Map-blind: no foe town with fresh intel (r31 lesson — pro sat
    8500 turns seeing only its capital). Darkness re-arms scouting
    post-contact (existing drive machinery, fan-out included)."""
    return _memoized(state, ("dark", window), lambda: _dark_compute(state, window))


def _dark_compute(state: "BotState", window: int) -> bool:
    for t in state.world.towns:
        if t.faction == state.faction:
            continue
        if state.turn - state._last_seen.get(("town", t.id), -10 ** 9) <= window:
            return False
    return True


def _scout_contact(state: "BotState", config) -> bool:
    """True iff raid/defense logic should own all armies: a viable town
    (duel-core gate; everything in multi-foe wars) or any foe army."""
    f = state.faction
    foe_towns = [t for t in state.world.towns if t.faction != f]
    if any(a.faction != f for a in state.world.armies):
        return True
    war_foes = {t.faction for t in foe_towns}
    viable = ([t for t in foe_towns if scout_viable(state, config, t)]
              if len(war_foes) <= 1 else list(foe_towns))
    return bool(viable)


def scout_hop_target(state: "BotState", config, p, hop: int, gen: int = 0) -> tuple[float, float]:
    """Next 50km hop: straight faction-spread ray, bent off known towns.
    Tries base, ±45°, ±90°; first segment clearing all known towns by
    15km wins; all-blocked falls back to base (rare blunder accepted).
    Probe memory: also bends off own towns and fellow-probe destinations
    (20km), so repeat probes don't re-fly settled rays into duplicate
    merges. Memory points underfoot (< interact+15 of p) are skipped —
    the scout stands on its own capital at dispatch. Foe logic is
    untouched (danger keeps no underfoot exemption)."""
    size = (config.map_size if config is not None
            and getattr(config, "map_size", None) else [1000, 1000])
    interact = (config.interact_radius if config is not None
                and getattr(config, "interact_radius", None) else 10.0)
    f = state.faction
    known = [(t.x, t.y, 15.0) for t in state.world.towns if t.faction != f]
    for t in state.world.towns:
        if t.faction == f and math.hypot(t.x - p.x, t.y - p.y) >= interact + 15.0:
            known.append((t.x, t.y, 20.0))
    for aid, tgt in sorted(state._army_targets.items()):
        if (aid != p.id and tgt is not None
                and math.hypot(tgt[0] - p.x, tgt[1] - p.y) >= interact + 15.0):
            known.append((tgt[0], tgt[1], 20.0))
    # Scout-meetings (r86: 6 pure field-1v1s, both die — lone explorers
    # collide in the void). Bend hops off observed foe armies too (30km
    # clearance; stale positions still repel — a moved foe leaves the
    # ray safe, a stayed foe kills the scout).
    for a in state.world.armies:
        if a.faction != f and a.id != p.id:
            known.append((a.x, a.y, 30.0))
    base = f * (2 * math.pi / 5) + gen * 2.399963 + hop * 0.35
    # Fan-out: each probe generation rotates the ray by the golden angle
    # (successive scouts cover different country), and each leg spirals
    # ~20 deg so one probe sweeps area instead of flying one straight ray.
    for turn in (0.0, math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2):
        ang = base + turn
        tx = min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(ang)))
        ty = min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(ang)))
        if all(_seg_dist(p.x, p.y, tx, ty, qx, qy) >= r for qx, qy, r in known):
            return (tx, ty)
    # All bent-blocked: gradient descent on the threat field (cool grids
    # — smooth danger cost picks the least-bad ray instead of blundering
    # into the base ray).
    cands = []
    for turn in (0.0, math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2):
        ang = base + turn
        tx = min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(ang)))
        ty = min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(ang)))
        try:
            cost = -state._threat_at(tx, ty)
        except Exception:
            cost = 0.0
        cands.append((cost, tx, ty))
    cands.sort()
    return (cands[0][1], cands[0][2])


def _scout_slot(state: "BotState", pid: int) -> int:
    """Which probe slot (1, 2) an army holds, else 0."""
    if state._scout_id == pid:
        return 1
    if getattr(state, "_scout_id2", None) == pid:
        return 2
    return 0


def _scout_unmark(state: "BotState", slot: int) -> None:
    if slot == 2:
        state._scout_id2 = None
        state._scout_leg2 = 0
    else:
        state._scout_id = None
        state._scout_leg = 0


def coverage_orders(state: "BotState", config) -> list[str]:
    """Idle patrols (doctrine: idle armies explore, never sit). Leftover
    unnoted field armies sweep the stalest coverage sectors (4x4 grid,
    stamped per payload). Nearest-idle to stalest-cell, one per cell.
    Runs LAST in moves stages (packs/scouts/settlers take theirs first).
    Notes via order_move (pendulum-breaker + amnesty bound them).
    Pack-muster guard (r68: coverage scattered a 5/6 pack to patrol
    sectors — undersized packs hold, then coverage eats them and they
    never converge): when a priced sel needs everyone, stand down."""
    import math as _math
    idle = [a for a in state.own_armies()
            if not state.army_has_target(a.id)
            and not getattr(a, "is_viceroy", False)
            and a.id != state._scout_id
            and a.id != getattr(state, "_scout_id2", None)
            # Home firewall (r93: coverage patrolled guards away -> naked
            # towns reprinted (82-print treadmill). Home bodies hold
            # position implicitly (no note = no cascade); packs grab them
            # when needed (unnoted). Patrols use field bodies only.
            and not any(_math.hypot(a.x - t.x, a.y - t.y) <= 20
                        for t in state.world.towns if t.faction == state.faction)]
    # Parking lot (r89: 29 patrols parked on centroids — arrived notes
    # freeze (quiescence: arrived → silent → not-ready → no re-task).
    # Noted-but-arrived AT a sector centroid is a parked patrol (pack
    # notes point at towns, never centroids): re-task it now.
    size0 = (config.map_size if config is not None
             and getattr(config, "map_size", None) else [1000, 1000])
    n0 = 4
    cents = [((cx + 0.5) / n0 * size0[0], (cy + 0.5) / n0 * size0[1])
             for cx in range(n0) for cy in range(n0)]
    for a in state.own_armies():
        if getattr(a, "is_viceroy", False) or a.id == state._scout_id \
                or a.id == getattr(state, "_scout_id2", None):
            continue
        if not state.army_has_target(a.id) or state.has_pending_build(a.id):
            continue
        tgt = state.army_target(a.id)
        if tgt is None:
            continue
        if not any(_math.hypot(tgt[0] - cx, tgt[1] - cy) < 40 for cx, cy in cents):
            continue  # not a patrol note (packs point at towns)
        try:
            rx, ry = state.reckoned_pos(config, a.id)
        except Exception:
            rx, ry = a.x, a.y
        if _math.hypot(rx - tgt[0], ry - tgt[1]) >= 30:
            continue  # still en route
        state._army_targets.pop(a.id, None)  # parked: re-task below
        state.__dict__.get("_march_origin", {}).pop(a.id, None)
        idle.append(a)
    if not idle:
        return []
    # S0-guard (r83: early bloodbath — first print scouts, capital naked,
    # first packs walk in t2300+. The lone first army holds the capital;
    # scouting starts with the second print).
    if len(idle) == 1 and len(state.own_armies()) == 1:
        cap = state.world.faction_capital(state.faction)
        sole = idle[0]
        if cap is not None and _math.hypot(sole.x - cap.x, sole.y - cap.y) > 20:
            return order_move(state, config, sole, cap.x, cap.y)
        return []
    # Pack-muster guard only when packs plausibly need everyone (small
    # idles; huge idles patrol — holding 12 bodies for a maybe-pack is
    # worse than sweeping). Full pricing scan, so gate it.
    if len(idle) <= 12:
        try:
            sel = raid_target(state, config, priced=True)
        except Exception:
            sel = None
        if sel is not None and sel[1] >= len(idle):
            return []  # pack needs everyone
    size = (config.map_size if config is not None
            and getattr(config, "map_size", None) else [1000, 1000])
    n = 4
    cover = state.__dict__.get("_cover", {})
    cells = []
    for cx in range(n):
        for cy in range(n):
            seen = cover.get((cx, cy), -10 ** 9)
            cells.append((state.turn - seen, (cx + 0.5) / n * size[0],
                          (cy + 0.5) / n * size[1]))
    cells.sort(key=lambda c: -c[0])
    out: list[str] = []
    free = list(idle)
    # Diffusion gradient (user: scouting flows on the pheromone field).
    # Per-army ascent: from the army's cell, step to the stalest
    # 8-neighbor on the 16x16 explore field (3 steps) — patrols push
    # into stale frontiers instead of teleport-assigning to
    # global-stalest (which re-treads). Cells within 300km only
    # (nearby-first); leftovers micro (150km).
    en = 16
    def _ecell(x, y):
        return (min(en - 1, max(0, int(x / size[0] * en))),
                min(en - 1, max(0, int(y / size[1] * en))))
    # Meatgrinder exclusion (r106: patrols walked through town12's 2-guard
    # 9 times — coverage centroids ignore towns. Cells holding foe towns
    # are unclaimable (packs assault towns; patrols never stroll in).
    foe_cells = {_ecell(u.x, u.y) for u in state.world.towns
                 if u.faction != state.faction}
    def _estale(cx, cy):
        return state._explore_at((cx + 0.5) / en * size[0], (cy + 0.5) / en * size[1])
    claimed: set = set(foe_cells)
    for p in list(free):
        cx, cy = _ecell(p.x, p.y)
        for _ in range(3):
            opts = [(_estale(nx, ny), nx, ny)
                    for nx in (cx - 1, cx, cx + 1) for ny in (cy - 1, cy, cy + 1)
                    if 0 <= nx < en and 0 <= ny < en and (nx, ny) != (cx, cy)
                    and (nx, ny) not in claimed]
            if not opts:
                break
            opts.sort(reverse=True)
            if opts[0][0] <= _estale(cx, cy):
                break  # local freshest: hold the gradient here
            _, cx, cy = opts[0]
        if (cx, cy) in claimed:
            continue
        tx, ty = (cx + 0.5) / en * size[0], (cy + 0.5) / en * size[1]
        if _math.hypot(p.x - tx, p.y - ty) < 30:
            continue
        if _math.hypot(p.x - tx, p.y - ty) > 300:
            continue
        out.extend(order_move(state, config, p, tx, ty))
        claimed.add((cx, cy))
        free.remove(p)
    # (leftovers micro-patrol: nearest stale cell within 150km (busy +
    # positioned, no churn). Doctrine: idle >few turns is suspicious —
    # every body works every turn. One rotating far patrol per 500t
    # covers far eyes (r73).)
    if free:
        for _, tx, ty in cells:
            if not free:
                break
            p = min(free, key=lambda a: _math.hypot(a.x - tx, a.y - ty))
            if _math.hypot(p.x - tx, p.y - ty) < 30:
                continue
            if _math.hypot(p.x - tx, p.y - ty) > 150:
                continue  # micro only; far eyes rotate below
            out.extend(order_move(state, config, p, tx, ty))
            free.remove(p)
    if free and state.turn % 500 == (state.faction * 137) % 500:
        for _, tx, ty in cells:
            if not free:
                break
            p = min(free, key=lambda a: _math.hypot(a.x - tx, a.y - ty))
            if _math.hypot(p.x - tx, p.y - ty) < 30:
                continue
            out.extend(order_move(state, config, p, tx, ty))
            free.remove(p)
            break  # one far patrol per rotation
    return out


def maybe_schedule_scout(state: "BotState", config):
    """Cartographic schedule (r35 lesson): neighbors-fresh != covered —
    fronts go blind and 94k rocks sit unpunished. Dark peace scouts
    every 500t (r58 lesson: 1500t cadence leaves empires blind all
    game); contact keeps 1500t. One surplus idle army per slot (fresh
    gen ray, existing fan machinery). Skips when a pack needs everyone."""
    period = 500 if _dark(state) else 1500
    if state.turn % period != (state.faction * 300) % period:
        return None
    if state._scout_id is not None and getattr(state, "_scout_id2", None) is not None:
        return None
    try:
        sel = raid_target(state, config, priced=True)
    except Exception:
        sel = None
    idle = [a for a in state.own_armies()
            if not a.is_viceroy and not state.army_has_target(a.id)
            and a.id != state._scout_id and a.id != getattr(state, "_scout_id2", None)]
    if sel is not None and sel[1] >= len(idle):
        return None  # pack needs everyone
    if not idle:
        # Dark-release (showcase lesson): a lone guard is never idle,
        # so single-army bots map nothing and die blind. In the dark,
        # release the youngest guard as scout — eyes beat a second
        # spear when no contact exists in 300t. Never strip naked
        # (r-loop: pro released its only guard and got captured):
        # need 2+ armies or a replacement already printing.
        if not _dark(state):
            return None
        if len(state.own_armies()) < 2 and not state._pending_trains:
            return None
        guards = [a for a in state.own_armies()
                  if not a.is_viceroy and a.id != state._scout_id
                  and a.id != getattr(state, "_scout_id2", None)]
        if not guards:
            return None
        p = max(guards, key=lambda a: a.id)
        if maybe_assign_scout(state, config, p):
            return drive_scout(state, config, p) or []
        return None
    if _scout_contact(state, config) and not _dark(state):
        return None  # real war on: raid/defense owns the field
    p = idle[0]
    if maybe_assign_scout(state, config, p):
        return drive_scout(state, config, p) or []
    return None


def maybe_assign_scout(state: "BotState", config, p) -> bool:
    """Mark p as a scout iff no actionable contact exists yet — true
    void OR rubble-only (a visible decoy is not a reason to stay home).
    Two concurrent probes (fan-out): the second takes a fresh generation
    ray, so scouts spread across the map instead of one line."""
    # No settle-first block here (TRIED + REVERTED): delaying the first
    # scout for a near-home settler breaks the S0 intel-first contract
    # (10 pinned tests + epistemics: void might hold foes, scouting
    # resolves it; far-but-interior tips win games). Clustering is handled
    # by the 65km floor (both paths), not by reordering missions.
    # No stay-behind block here (REVERTED): the first print must scout
    # (S0 contract, test-pinned) — and t1495's deny-convert was CORRECT
    # (1096 pop can't print a guard vs N=1 inbound anyway; convert
    # denies). Stay-behind lives in settled play (2+ armies), not probe.
    # Refound imperative (r61 + doctrine: townless armies settle, not
    # scout — exile colonies seed comebacks; lots of small = growth).
    if not state.own_towns():
        return False
    # (No S0-guard here: scouts are often sole + foes-known; blocking
    # them blinds. The coverage S0-guard holds unscouted lone armies.)
    for slot, sid in ((1, state._scout_id), (2, getattr(state, "_scout_id2", None))):
        if sid is not None:
            # Dead scout frees the slot (else one death ends scouting forever).
            if state.world.get_army(sid) is None:
                _scout_unmark(state, slot)
            else:
                continue
        if state.turn < SCOUT_MIN_TURN:
            return False
        if p.is_viceroy:
            return False
        if _scout_contact(state, config) and not _dark(state):
            return False  # owned by raid/defense — unless blind (re-arm)
        if state.army_has_target(p.id):
            # Tasked armies are owned (kept scout tips go to builds, packs
            # to war): re-assigning steals the tip every hop-12 unmark and
            # the probe loops forever, never founding (0 foundings/3000t).
            return False
        state._scout_gen = getattr(state, "_scout_gen", -1) + 1
        if slot == 2:
            state._scout_id2 = p.id
            state._scout_leg2 = 0
            state._scout_gen2 = state._scout_gen
        else:
            state._scout_id = p.id
            state._scout_leg = 0
            state._scout_gen1 = state._scout_gen
        return True
    return False


def _expected_delay(state: "BotState", config, x: float, y: float) -> int:
    cap = state.world.faction_capital(state.faction)
    info = (config.info_speed if config is not None else 150.0)
    if cap is None:
        return 1
    return max(1, math.ceil(math.hypot(x - cap.x, y - cap.y) / info))


def ready_to_dispatch(state: "BotState", config, p) -> bool:
    """Freshness gate: order MOVE_TO when intel is fresh enough.

    Send-all era (was: quiescence — order only when the trail went
    quiet, proving nothing in flight). Every-turn delivery keeps trails
    permanently fresh, so quiescence almost never passed and armies
    froze on live notes (pro scout-7: 8000 turns, same order, no moves).
    Inverted rule: order from fresh intel (lag within 3x expected +
    margin); hold only when ancient (mail broken, don't compound error).
    Re-notes are idempotent, so stacking risk is nil."""
    tr = state._trails.get(p.id)
    if not tr or len(tr) < 2:
        # never (or once) seen: idle/spawn-stationary by construction.
        return True
    t_new, x, y = tr[-1]
    d = _expected_delay(state, config, x, y)
    return state.turn - t_new <= 3 * d + 2


def order_move(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    """MOVE_TO from converged intel (quiescence-gated) + note. [] when
    the order would die in flight — retry next turns, it converges."""
    if not ready_to_dispatch(state, config, p):
        return []
    state.note_move(p.id, float(tx), float(ty))
    rx, ry = state.reckoned_pos(config, p.id)
    return [f"MOVE_TO {p.id} {rx:.1f} {ry:.1f} {float(tx):.1f} {float(ty):.1f}"]


def dispatch_settler(state: "BotState", config, p, sx: float, sy: float) -> list[str]:
    """Settler MOVE_TO -> BUILD chain via the command queue: march now,
    BUILD scheduled for arrival (march time + messenger delay + slack).
    The BUILD fires on schedule even if arrival notes die (tip-loss saga)
    and defers if the march runs late; arrival detection stays as backup.
    Tag per army (re-tasks cancel the chain)."""
    import math as _math
    speed = max(1.0, config.army_speed)
    info = (config.info_speed if config is not None else 150.0) or 150.0
    march = _math.hypot(p.x - sx, p.y - sy) / speed
    delay = _math.ceil(_math.hypot(p.x - sx, p.y - sy) / info)
    fire = state.turn + int(_math.ceil(march)) + delay + 2
    tag = f"settle{p.id}"
    state.cancel_queued(tag)
    out = order_march_exact(state, config, p, sx, sy)
    state.queue_order(fire, f"BUILD {p.id} {sx:.1f} {sy:.1f}", tag)
    return out


def order_march_exact(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    """Unconditional noted march (bypasses quiescence): for own armies
    re-tasking from a hold (tip respins, recycle-home). Quiescence
    deadlocks there — a stationary army goes delivery-silent, its trail
    never converges, ready stays false forever, no orders flow, it never
    moves (army 5 held 24 turns at its tip). The from-risk is nil (army
    stationary: botpos error << messenger tolerance). Marching armies
    keep the gated order_move."""
    state.note_move(p.id, float(tx), float(ty))
    state._tip_grace[p.id] = state.turn + 30
    return [f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {float(tx):.1f} {float(ty):.1f}"]


def _dispatch_leg(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    return order_move(state, config, p, tx, ty)


def scout_viable(state: "BotState", config, t) -> bool:
    """Duel-core viability: captured half must clear floor + margin."""
    eff = config.build_efficiency if config is not None else 0.5
    cost = config.army_cost if config is not None else 1000
    return t.population * (1.0 - eff) > cost * eff + 200


def _seg_dist(px, py, tx, ty, qx, qy) -> float:
    dx, dy = tx - px, ty - py
    d2 = dx * dx + dy * dy
    if d2 < 1e-9:
        return math.hypot(qx - px, qy - py)
    s = max(0.0, min(1.0, ((qx - px) * dx + (qy - py) * dy) / d2))
    return math.hypot(qx - (px + dx * s), qy - (py + dy * s))


def silence_watch(state: "BotState", config) -> None:
    """Overdue raiders are presumed dead (fog eats tombstones: death
    news reaches observers of the site only, never home). A noted army
    unheard-of past 2x round-trip + margin bloodies its foe-town target
    and drops the note — silence is the signal dead armies can't send.
    Marching armies report flowing snapshots (trail fresh); holders with
    home notes never match foe towns; scouts exempt (still-arrival
    silence is normal). Piggybacks drop_dead_notes (all five, per turn).
    Town-forget via observed absence (RTS FoW: last-known persists;
    erase only when re-watched ground is empty). A mirror foe unseen
    while an own observer (town or reckoned army) watches its ground
    long enough for news to arrive (age > dist/info + 1) is GONE —
    towns to graves, armies dropped. Stale-but-unwatched intel is kept
    (genuinely unknown). Replaces wall-clock forgetting (r59)."""
    import math as _math
    los = float(getattr(config, "line_of_sight", 150.0) or 150.0)
    info = max(1.0, float(getattr(config, "info_speed", 150.0) or 150.0))
    observers = [(t.x, t.y) for t in state.world.towns if t.faction == state.faction]
    for a in state.own_armies():
        try:
            observers.append(state.reckoned_pos(config, a.id))
        except Exception:
            observers.append((a.x, a.y))
    for t in list(state.world.towns):
        if t.faction == state.faction:
            continue
        if ("town", t.id) not in state._last_seen:
            continue  # never observed (constructed worlds): not stale
        last = state._last_seen.get(("town", t.id), -10 ** 9)
        if last >= state.turn:
            continue
        for ox, oy in observers:
            if _math.hypot(ox - t.x, oy - t.y) <= los \
                    and state.turn - last > _math.hypot(ox - t.x, oy - t.y) / info + 2:
                state.__dict__.setdefault("_grave_pos", {})[t.id] = (t.x, t.y)
                try:
                    state.world.towns.remove(t)
                except ValueError:
                    pass
                break
    for a in list(state.world.armies):
        if a.faction == state.faction:
            continue
        if ("army", a.id) not in state._last_seen:
            continue
        last = state._last_seen.get(("army", a.id), -10 ** 9)
        if last >= state.turn:
            continue
        for ox, oy in observers:
            if _math.hypot(ox - a.x, oy - a.y) <= los \
                    and state.turn - last > _math.hypot(ox - a.x, oy - a.y) / info + 2:
                try:
                    state._remove_army(a.id)
                except Exception:
                    pass
                break
    cap = state.world.faction_capital(state.faction)
    if cap is None:
        return
    speed = max(1.0, getattr(config, "army_speed", 50.0) or 50.0)
    info = max(1.0, getattr(config, "info_speed", 150.0) or 150.0)
    interact = float(getattr(config, "interact_radius", 10.0) or 10.0)
    scouts = {state._scout_id, getattr(state, "_scout_id2", None)}
    for aid, tgt in list(state._army_targets.items()):
        if aid in scouts:
            continue
        a = state.world.get_army(aid)
        if a is None or getattr(a, "is_viceroy", False):
            continue  # observed deaths blood in _remove_army already
        hit = None
        for u in state.world.towns:
            if u.faction != state.faction and abs(u.x - tgt[0]) < interact + 15 \
                    and abs(u.y - tgt[1]) < interact + 15 \
                    and _math.hypot(u.x - tgt[0], u.y - tgt[1]) <= interact + 15:
                hit = u
                break
        if hit is None:
            # No live town matches: maybe a grave (dead towns leave the
            # mirror). Grave-haunting release (r37: 20 armies noted to
            # dead town-4 sat 2000t): pop immediately (live targets keep
            # raiding — blood is suspicion, absence is proof).
            for gid, (gx, gy) in state.__dict__.get("_grave_pos", {}).items():
                # No age bound (dead is dead; refound towns are live in
                # mirror and skip) — faded graves must not re-lock notes.
                if state.world.get_town(gid) is None and \
                        abs(gx - tgt[0]) < interact + 15 and abs(gy - tgt[1]) < interact + 15 and \
                        _math.hypot(gx - tgt[0], gy - tgt[1]) <= interact + 15:
                    state._army_targets.pop(aid, None)
                    state.__dict__.get("_march_origin", {}).pop(aid, None)
                    break
            if aid not in state._army_targets:
                continue  # released above; ghost-clean below unneeded
        tr = state._trails.get(aid)
        last_heard = tr[-1][0] if tr else -10 ** 9
        org = state.__dict__.get("_march_origin", {}).get(aid)
        if org is not None:
            last_heard = max(last_heard, org[2])  # note birth: no trail yet
        # Visibility affirmations (exact seen-age; trails lie by lag).
        last_heard = max(last_heard, state._last_seen.get(("army", aid), -10 ** 9))
        mail = _math.hypot(cap.x - tgt[0], cap.y - tgt[1]) / info
        march = _math.hypot(cap.x - tgt[0], cap.y - tgt[1]) / speed
        if state.turn - last_heard <= 2 * (mail + march) + 20:
            continue
        if hit is not None:
            state.__dict__.setdefault("_bloodied", {})[hit.id] = state.turn
            state.__dict__.setdefault("_grave_pos", {})[hit.id] = (hit.x, hit.y)
        # Ghost-cleaning (r25 trace: army 17 dead-unseen, mirror-kept +
        # re-noted 2000t — the re-note loop defeats drop_dead's age-cap
        # because origin refreshes every decide). Overdue-vs-physics
        # (elapsed since origin dwarfs march+mail) means dead-or-stuck:
        # forget locally (live armies re-observe back in — self-healing).
        ox, oy, ot = org if org is not None else (tgt[0], tgt[1], last_heard)
        if state.turn - ot > 3 * (mail + march) + 50:
            state.world.remove_army(aid)
            state._trails.pop(aid, None)
            state._army_targets.pop(aid, None)
            state.__dict__.get("_march_origin", {}).pop(aid, None)
            continue
        state._army_targets.pop(aid, None)
        state.__dict__.get("_march_origin", {}).pop(aid, None)


def amnesty_notes(state: "BotState") -> None:
    """Note amnesty (r43 lesson: 27 armies noted 6000t+, nothing wants
    them, nothing releases them). Field notes older than 300t pop and
    re-decide fresh — valid plans reform in one turn (same sel, same
    tip); stale locks break. Home notes, scouts, viceroys, pending
    builds exempt (holding is their job).
    Guard rotation (r53 lesson: 39 idle, home notes never expire):
    every 1500t (faction-phased) home notes pop too — real threats
    re-hold next turn (hold_defenders runs every decide); quiet fronts
    release garrisons to the field. One turn of re-tasking per 1500."""
    rotate = state.turn % 1500 == (state.faction * 311) % 1500
    for aid, tgt in list(state._army_targets.items()):
        if aid == state._scout_id or aid == getattr(state, "_scout_id2", None):
            continue
        a = state.world.get_army(aid)
        if a is None or getattr(a, "is_viceroy", False):
            continue
        if state.has_pending_build(aid):
            continue
        if any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in state.world.towns
               if t.faction == state.faction):
            if not rotate:
                continue  # home note: guards hold (except rotation)
            state._army_targets.pop(aid, None)
            state.__dict__.get("_march_origin", {}).pop(aid, None)
            continue
        org = state.__dict__.get("_march_origin", {}).get(aid)
        if org is None or state.turn - org[2] <= 300:
            continue
        state._army_targets.pop(aid, None)
        state.__dict__.get("_march_origin", {}).pop(aid, None)


def drop_dead_notes(state: "BotState") -> None:
    """Clear MOVE_TO notes whose army is statically elsewhere: the order
    died in flight (messenger from-check on stale intel) and has_target
    would otherwise block fresh orders forever. The signal is trail
    freshness beyond the intel delay: a mover's snapshots keep arriving
    (delayed, but flowing), while a static army goes delivery-silent, so
    a trail older than expected-delay + 2 at one spot >20km off-note
    means stranded. Catches dispatch-time deaths too (army never left).
    Viceroys exempt (flight notes are live by construction)."""
    silence_watch(state, state.config)
    amnesty_notes(state)
    cap = state.world.faction_capital(state.faction)
    info = (state.config.info_speed if state.config is not None else 150.0)
    for aid, tgt in list(state._army_targets.items()):
        a = state.world.get_army(aid)
        if a is None or getattr(a, "is_viceroy", False):
            continue
        if aid == state._scout_id or aid == getattr(state, "_scout_id2", None):
            continue  # scout notes are drive-managed (hop legs re-note
            # constantly; trail-staleness misreads march holds as stranded
            # and pops the tip every few turns — the infinite probe loop)
        if aid in state._tip_grace and state.turn <= state._tip_grace[aid]:
            continue  # kept-tip grace (unmark/respin notes survive the
            # delivery lag + quiescence holds that fake strandedness)
        tr = state._trails.get(aid)
        if not tr:
            continue
        t_new, x, y = tr[-1]
        if cap is not None:
            exp_delay = math.ceil(math.hypot(x - cap.x, y - cap.y) / info)
        else:
            exp_delay = 1
        if state.turn - t_new < exp_delay + 2:
            continue  # intel still flowing
        # Note age-cap: notes older than 100 turns without arrival are
        # stale intent (dead letters, obsolete raids) — drop and re-decide
        # fresh. (Pro t7000-8500: 22 armies sat home 1500 turns on dead
        # notes, never marching at priced thin towns.)
        noted_at = state.__dict__.get("_march_origin", {}).get(aid, (0, 0, 0))[2]
        if state.turn - noted_at > 100:
            del state._army_targets[aid]
            continue
        if math.hypot(x - tgt[0], y - tgt[1]) <= 20:
            continue  # trail shows arrival (freshest intel, not lagging
            # botpos — kept scout tips wait for builds here, never pop)
        if math.hypot(x - tgt[0], y - tgt[1]) > 20:
            del state._army_targets[aid]


MAPPER_HOPS = 8
MAPPER_HOP_KM = 150.0
MAPPER_MAX = 2


def mapper_hop_target(state: "BotState", config, p) -> tuple[float, float]:
    """Next mapping hop: tour the quadrant centroids in order (legs % 4).
    (Was: stalest-quadrant chase — arrival freshens it, the far side goes
    stalest, eternal 300km pendulum: mapper-33 painted 5301km of line.)
    A fixed tour covers the map once, then the patrol releases."""
    size = (config.map_size if config is not None
            and getattr(config, "map_size", None) else [1000, 1000])
    cx, cy = size[0] / 2.0, size[1] / 2.0
    quads = [(cx / 2, cy / 2), (cx + cx / 2, cy / 2),
             (cx / 2, cy + cy / 2), (cx + cx / 2, cy + cy / 2)]
    legs = state.__dict__.get("_mapper", {}).get(p.id, 0)
    qx, qy = quads[legs % 4]
    import math as _math
    d = _math.hypot(qx - p.x, qy - p.y)
    if d < 1e-9:
        return (qx, qy)
    step = min(MAPPER_HOP_KM, d)
    return (min(size[0] - 20.0, max(20.0, p.x + step * (qx - p.x) / d)),
            min(size[1] - 20.0, max(20.0, p.y + step * (qy - p.y) / d)))


def drive_mapper(state: "BotState", config, p):
    """Advance a mapping patrol; None = done (release to normal logic).
    Legs step on arrival (dead-reckoned); no founding (pure eyes)."""
    import math as _math
    legs = state.__dict__.get("_mapper", {}).get(p.id)
    if legs is None:
        return None
    if legs >= MAPPER_HOPS:
        state.__dict__.get("_mapper", {}).pop(p.id, None)
        state._army_targets.pop(p.id, None)
        return None
    tgt = state.army_target(p.id)
    if tgt is None:
        return _dispatch_leg(state, config, p, *mapper_hop_target(state, config, p))
    rx, ry = state.reckoned_pos(config, p.id)
    if _math.hypot(rx - tgt[0], ry - tgt[1]) >= 20:
        return []  # en route or awaiting arrival-intel: hold
    if not ready_to_dispatch(state, config, p):
        return []
    state.__dict__.setdefault("_mapper", {})[p.id] = legs + 1
    return _dispatch_leg(state, config, p, *mapper_hop_target(state, config, p))


def drive_scout(state: "BotState", config, p):
    """Advance the marked scout; None = not-a-scout (handle normally).

    Unmarks for viable towns (raid logic owns) and foe armies (defense
    owns). Stays out on rubble-only contact, hopping around it, so the
    probe never accidentally captures starvation (trap lesson)."""
    slot = _scout_slot(state, p.id)
    if slot == 0:
        return None
    still_key = "_scout_still" if slot == 1 else "_scout_still2"
    leg = state._scout_leg2 if slot == 2 else state._scout_leg
    gen = getattr(state, "_scout_gen2", 0) if slot == 2 else getattr(state, "_scout_gen1", 0)
    def _bump(n: int) -> int:
        if slot == 2:
            state._scout_leg2 = n
        else:
            state._scout_leg = n
        return n
    if p.is_viceroy:
        _scout_unmark(state, slot)
        return None
    if _scout_contact(state, config):
        # Contact: raid/defense owns the army fresh — drop the stale hop
        # target or it hijacks the army into founding next to the prize.
        _scout_unmark(state, slot)
        state._army_targets.pop(p.id, None)
        return None
    tgt = state.army_target(p.id)
    if tgt is None:
        return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, leg, gen))
    # Arrival on dead-reckoned pos (own march physics exact; botpos lags
    # 30km+ behind truth and freezes for holding armies).
    rx, ry = state.reckoned_pos(config, p.id)
    if math.hypot(rx - tgt[0], ry - tgt[1]) >= 20:
        state.__dict__.pop(still_key, None)
        return []  # mid-hop or waiting arrival-intel: hold
    # arrived: next hop only from quiescent intel (else the order dies in
    # flight); the leg steps exactly when the hop dispatches, never twice
    # on persistent arrival-intel.
    if not ready_to_dispatch(state, config, p):
        # Still-arrival force: a holding scout goes delivery-silent, its
        # trail never converges, ready stays false forever — legs stall
        # one short of unmark and the scout sits at its tip for 1600+
        # turns (aggressive t1365-t3000). Persistent static arrival
        # (past delivery lag) forces the leg; phantom-early unmarks are
        # harmless (tip kept early, army catches up and founds).
        info = (config.info_speed if config is not None else 150.0) or 150.0
        cap = state.world.faction_capital(state.faction)
        exp = math.ceil(math.hypot(p.x - cap.x, p.y - cap.y) / info) if cap else 1
        st = state.__dict__.get(still_key)
        if st is None or math.hypot(p.x - st[0], p.y - st[1]) > 1e-6:
            state.__dict__[still_key] = (p.x, p.y, 1)
            return []
        if st[2] < exp + 2:
            state.__dict__[still_key] = (p.x, p.y, st[2] + 1)
            return []
        state.__dict__.pop(still_key, None)
    else:
        state.__dict__.pop(still_key, None)
    if not ready_to_dispatch(state, config, p):
        return []
    leg = _bump(leg + 1)
    if leg >= SCOUT_HOPS:
        # hops exhausted with no contact: convert the tip HERE (drive owns
        # it end-to-end — handing a kept note to builds loses it 7 ways:
        # drop_dead, S0 re-steal, quiescence deadlock, grace expiry,
        # arrival-lag, respin-None, cap-march death-letters). Arrived +
        # gated -> BUILD now; bad tip -> respin note+march (queued BUILD
        # fires on arrival); builds stays as backup only.
        _scout_unmark(state, slot)
        if tgt is not None:
            interact = (config.interact_radius if config is not None
                        and getattr(config, "interact_radius", None) else 10.0)
            if any(t.faction == state.faction and math.hypot(t.x - tgt[0], t.y - tgt[1]) <= interact + 10.0
                   for t in state.world.towns):
                state._army_targets.pop(p.id, None)
            else:
                state._tip_grace[p.id] = state.turn + 20
                rx, ry = state.reckoned_pos(config, p.id)
                if math.hypot(rx - tgt[0], ry - tgt[1]) <= interact + 10.0:
                    foe_known = any(t.faction != state.faction for t in state.world.towns) \
                        or any(a.faction != state.faction for a in state.world.armies)
                    demand_ok = (not state._foe_first_seen) or expansion_demand(state, config)
                    if (not foe_known or demand_ok) and site_pays(state, config, tgt[0], tgt[1]) \
                            and tip_safe(state, config, tgt[0], tgt[1]):
                        state.note_build(p.id)
                        return [f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}"]
                rs = respin_tip(state, config, tgt[0], tgt[1])
                if rs is not None:
                    # Full chain: march + scheduled BUILD (fires on arrival
                    # even if notes die; arrival detection is backup).
                    return dispatch_settler(state, config, p, rs[0], rs[1])
        return []
    return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, leg, gen))


class BotForecast:
    """Forecast world state compensating for info delay.

    Built from a BotState snapshot; does not mutate the BotState.
    Basic mode: interpolate each moving army forward by the turns its
    events are stale (dist to capital // info_speed * army_speed).
    Advanced hooks (TODO): my_orders, en_route orders, battle forecast.
    """
    def __init__(self, state: "BotState", config: GameConfig | None = None):
        self.state = state
        self.config = config or state.config
        self.turn = state.turn
        cap = state.world.faction_capital(state.faction)
        self.cap_x = cap.x if cap else 500
        self.cap_y = cap.y if cap else 500
        self.info_speed = (config.info_speed if config else 150) or 150
        self.army_speed = (config.army_speed if config else 50) or 50

    def _turns_stale(self, x: float, y: float) -> float:
        # Idea 3: same memo shape as BotState (per-instance, positions repeat
        # within one forecast pass).
        ck = (x, y)
        v = self.__dict__.get("_stale_memo")
        if v is None:
            v = self.__dict__["_stale_memo"] = {}
        hit = v.get(ck)
        if hit is None:
            hit = math.hypot(x - self.cap_x, y - self.cap_y) / max(1, self.info_speed)
            v[ck] = hit
        return hit

    def forecast_army_pos(self, army: Army | dict, turns_ahead: float | None = None) -> tuple[float, float]:
        """Intent-free forecast: own noted targets are exact; foe motion
        extrapolates the bot-kept position trail by mail lag. Memoized
        per foe per turn (same foe forecast N armies — compute once)."""
        if isinstance(army, dict):
            aid, x, y = army["id"], army["x"], army["y"]
        else:
            aid, x, y = army.id, army.x, army.y
        if turns_ahead is None:
            return _memoized(self.state, ("forecast_pos", aid),
                             lambda: self._forecast_army_pos_inner(aid, x, y, None))
        return self._forecast_army_pos_inner(aid, x, y, turns_ahead)

    def _forecast_army_pos_inner(self, aid, x: float, y: float, turns_ahead) -> tuple[float, float]:
        if turns_ahead is None:
            turns_ahead = self._turns_stale(x, y)
        tgt = self.state._army_targets.get(aid)
        if tgt is not None:
            dx, dy = tgt[0] - x, tgt[1] - y
            dist = math.hypot(dx, dy)
            if dist < 1e-9:
                return x, y
            travel = self.army_speed * turns_ahead
            if travel >= dist:
                return tgt[0], tgt[1]
            s = travel / dist
            return x + dx * s, y + dy * s
        trail = self.state._trails.get(aid) or ()
        if len(trail) >= 2:
            (t0, x0, y0), (t1, x1, y1) = trail[-2], trail[-1]
            dt = t1 - t0
            if dt > 0 and (x1 != x0 or y1 != y0):
                vx, vy = (x1 - x0) / dt, (y1 - y0) / dt
                return x + vx * turns_ahead, y + vy * turns_ahead
        return x, y

    def forecast_all_armies(self) -> dict[int, tuple[float, float]]:
        out: dict[int, tuple[float, float]] = {}
        for a in self.state.world.armies:
            out[a.id] = self.forecast_army_pos(a)
        return out

    def forecast_enemy_towns_for_attack(self) -> list[Town]:
        # Enemy towns don't move; no forecast needed, but hook for conquest prediction
        return [t for t in self.state.world.towns if t.faction != self.state.faction]

    # --- Advanced hooks for later ---
    def with_my_orders(self, orders: list[str]) -> "BotForecast":
        """Return a copy where my moving armies are clamped at target and BUILD orders become towns."""
        # Shallow copy for chaining; does not mutate original state.world
        import copy
        forecasted = copy.deepcopy(self.state.world)
        # Apply my MOVE_TO: set target (my orders are instant from my perspective)
        for o in orders:
            parts = o.split()
            if not parts:
                continue
            if parts[0] == "MOVE_TO" and len(parts) == 6:
                try:
                    aid = int(parts[1]); tx = float(parts[4]); ty = float(parts[5])
                    a = forecasted.get_army(aid)
                    if a:
                        a.target_x = tx; a.target_y = ty; a.has_target = True
                except Exception:
                    pass
            elif parts[0] == "BUILD" and len(parts) == 4:
                try:
                    aid = int(parts[1])
                    # BUILD forecast: army at its target becomes town — handled in forecast_battles/town_spawn
                    pass
                except Exception:
                    pass
        # Clamp my moving armies: they never move beyond target
        for a in forecasted.armies:
            if a.faction == self.state.faction and a.has_target:
                fx, fy = self.forecast_army_pos(a, turns_ahead=20)
                # forecast far ahead to get target clamp
                a.x, a.y = fx, fy
        # TODO: forecast BUILD -> town, forecast battles
        nf = BotForecast.__new__(BotForecast)
        nf.state = self.state
        nf.config = self.config
        nf.turn = self.turn
        nf.cap_x = self.cap_x; nf.cap_y = self.cap_y
        nf.info_speed = self.info_speed; nf.army_speed = self.army_speed
        nf._forecasted_world = forecasted  # type: ignore
        return nf

    def with_en_route_orders(self, orders: list[str]) -> "BotForecast":
        """Forecast where en-route BUILDs will have completed."""
        # TODO: for each army with pending BUILD (state.has_pending_build), predict town at its target
        return self

    def forecast_battles(self) -> list[dict]:
        """Predict battles from forecasted positions."""
        # TODO: run combat weakness check on forecasted positions
        return []


def towns_by_train_priority(state: "BotState", conservative: bool = False) -> list[Town]:
    cands = [t for t in state.own_towns() if state.can_train_here(t, conservative=conservative)]
    # overcrowded cluster reps first, then by growth asc (most negative), then pop asc
    def key(t: Town):
        over = 0 if state.should_train_for_overcrowding(t) else 1
        return (over, state.get_growth(t.id), t.population)
    cands.sort(key=key)
    return cands


def fresh_foe_armies(state: "BotState", cutoff: int = 12) -> list:
    """Foe armies with fresh intel (age <= cutoff turns). Kills ghosts:
    unobserved departures/deaths freeze last-seen intel (no updates flow
    outside LOS), and threat/garrison math treated 27-turn-old phantoms
    as live inbound — aggressive suicided its capital (t1807) over a foe
    that truth shows nowhere within 400km. Cutoff 12 exceeds max
    plausible mail lag (map diagonal/150 ~ 10)."""
    out = []
    for a in state.world.armies:
        if a.faction == state.faction:
            continue
        age = state.turn - state._last_seen.get(("army", a.id), state.turn)
        if age <= cutoff:
            out.append(a)
    return out


def closing_on(state: "BotState", aid: int, tx: float, ty: float) -> bool:
    """Attack-vector test: foe army aid heads at (tx, ty) (trail heading
    aligns with bearing + range closing). Transiting scouts (passing by,
    not attacking) must not trigger deny-converts — bare-convert needs
    this or close range. No trail (fresh contact) assumes closing."""
    import math as _math
    tr = state._trails.get(aid)
    if not tr or len(tr) < 2:
        return True
    (t0, x0, y0), (t1, x1, y1) = tr[-2], tr[-1]
    dx, dy = x1 - x0, y1 - y0
    if dx * dx + dy * dy < 1e-9:
        return True  # stationary foe at range: assume hostile
    bx, by = tx - x1, ty - y1
    bl = _math.hypot(bx, by)
    if bl < 1e-9:
        return True
    dl = _math.hypot(dx, dy)
    closing = (dx * bx + dy * by) / (dl * bl) > 0.5
    was = _math.hypot(x0 - tx, y0 - ty)
    return closing and bl <= was


def inbound_armies(state: "BotState", config, tid: int) -> list:
    """Fresh foe armies imputed to own town tid (same assignment as
    inbound_force: nearest-own-town, guards excluded). For vector tests."""
    import math as _math
    own_t = state.own_towns()
    tgt = next((t for t in own_t if t.id == tid), None)
    if tgt is None:
        return []
    foe_towns = [t for t in state.world.towns if t.faction != state.faction]
    out = []
    for a in fresh_foe_armies(state):
        guarded = False
        for u in foe_towns:
            if u.faction == a.faction and _math.hypot(a.x - u.x, a.y - u.y) <= 15:
                guarded = True
                break
        if guarded:
            continue
        if min(own_t, key=lambda u: _math.hypot(a.x - u.x, a.y - u.y)).id != tid:
            continue
        out.append(a)
    return out


def committed_raid(state: "BotState", aid: int) -> bool:
    """Army noted at a foe town (committed raid: don't re-task!).
    Chase/strike/recall branches steal raiders mid-march (ping-pong:
    expander army 133 raided, got re-tasked home, re-raided — 30-army
    shuttle fleet). Committed raids stick until arrival/outcome."""
    import math as _math
    tgt = state.army_target(aid)
    if tgt is None:
        return False
    return any(t.faction != state.faction
               and _math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20
               for t in state.world.towns)


def staging_eta(state: "BotState", config: "GameConfig") -> dict[int, float]:
    """Per-own-town staging threat ETA from known foe towns.

    A foe town inside striking distance (home LOS) of an own town is raid
    staging, i.e. threat: ETA = dist/army_speed is an upper bound (armies
    may already march, so the true ETA is sooner). Unlike armies, a town
    counts toward EVERY own town in range (it can strike any of them).
    Beyond LOS it is strategic intel, not tactical threat."""
    import math as _math
    faction = state.faction
    los = getattr(config, "line_of_sight", None) or 150.0
    speed = max(1.0, config.army_speed)

    def _compute():
        out: dict[int, float] = {}
        for t in state.own_towns():
            best = float("inf")
            for u in state.world.towns:
                if u.faction == faction:
                    continue
                d = _math.hypot(u.x - t.x, u.y - t.y)
                if d <= los:
                    best = min(best, d / speed)
            if best != float("inf"):
                out[t.id] = best
        return out
    return _memoized(state, ("staging_eta", los, speed), _compute)


def foe_print_factor(state: "BotState", faction: int, grace: int = 20) -> float:
    """Opponent print calibration for W (printable-before-arrival).

    Rate-calibrated (r34 lesson): two prints in 8000 turns is not a
    remuster threat — W must scale by OBSERVED print rate, not mere
    fielding. Sterile-observed factions (towns seen grace+ turns, zero
    prints) count zero. Fresh intel assumes live (dark-spring grace).
    A print per ~200 turns sustains full W; slower drips scale down."""
    first = state._foe_first_seen.get(faction, state.turn)
    if state.turn - first < grace:
        return 1.0
    prints = state._foe_prints.get(faction, 0)
    if prints <= 0:
        return 0.0
    return min(1.0, prints / max(1.0, (state.turn - first) / 200.0))


def buzzer_active(state: "BotState", config) -> bool:
    """Strip-mine flip (Step 6): retaliation time has run out — guards
    are free (no forgone growth) and raids are cheap. Last 10% (min 20
    turns): founding/pipelines die, pop becomes force, everything
    unguarded is taken."""
    max_turns = getattr(config, "max_turns", 3000) or 3000
    return max_turns - state.turn <= max(20, max_turns // 10)


def foe_velocity(state: "BotState", aid: int) -> tuple[float, float]:
    """Enemy velocity from displacement between observations (user: react
    to attacks intelligently — direction + target from how far it moved
    since last seen). Trail delta, capped at army speed; (0,0) when
    unknown/stationary."""
    import math as _math
    trail = state._trails.get(aid) or ()
    if len(trail) >= 2:
        (t0, x0, y0), (t1, x1, y1) = trail[-2], trail[-1]
        dt = t1 - t0
        if dt > 0 and (x1 != x0 or y1 != y0):
            vx, vy = (x1 - x0) / dt, (y1 - y0) / dt
            sp = _math.hypot(vx, vy)
            cfg_sp = 50.0
            try:
                cfg_sp = max(1.0, state.config.army_speed)
            except Exception:
                pass
            if sp > cfg_sp:
                vx, vy = vx / sp * cfg_sp, vy / sp * cfg_sp
            return vx, vy
    return (0.0, 0.0)


def velocity_eta(vx: float, vy: float, ax: float, ay: float,
                 tx: float, ty: float, speed: float) -> float | None:
    """Turns for a foe at (ax,ay) moving (vx,vy) to reach town (tx,ty).
    None when not closing (transit — distance-ETA overstates these)."""
    import math as _math
    dx, dy = tx - ax, ty - ay
    dist = _math.hypot(dx, dy)
    if dist < 1e-9:
        return 0.0
    v_toward = (vx * dx + vy * dy) / dist  # closing speed
    if v_toward <= 0.05 * speed:
        return None  # not closing: transit or holding
    return dist / max(v_toward, 0.05 * speed)


def inbound_force(state: "BotState", config: "GameConfig",
                  max_eta: float = 8.0) -> dict[int, tuple[float, int]]:
    """Per-own-town inbound threat (ETA, force) by nearest-own-town.

    Same assignment as inbound_eta, plus the count: N raiders imputed to
    the town nearest each of them. Stationary foe guards sitting on
    their own towns are excluded (not inbound)."""
    import math as _math
    faction = state.faction
    speed = max(1.0, config.army_speed)

    def _compute():
        own_t = state.own_towns()
        foe_towns = [t for t in state.world.towns if t.faction != faction]
        foes = fresh_foe_armies(state)
        # Guard set once (armies sitting on their own towns), not per pair.
        guarded = set()
        for a in foes:
            for u in foe_towns:
                if u.faction == a.faction and _math.hypot(a.x - u.x, a.y - u.y) <= 15:
                    guarded.add(a.id)
                    break
        out: dict[int, tuple[float, int]] = {}
        # Timeout guard fires only at pathological scale (50000+ pairs ≈
        # 5ms+; normal states never check the clock here, keeping
        # scripted-clock tests exact).
        big = len(own_t) * len(state.world.armies) > 50000
        # Nearest-own-town per foe, computed ONCE (not per town-foe pair:
        # 43 towns x 20 foes x 43 scan = 37k pairs blew the 16ms budget).
        nearest: dict[int, int] = {}
        for a in foes:
            if a.id in guarded:
                continue
            nearest[a.id] = min(own_t, key=lambda u: _math.hypot(a.x - u.x, a.y - u.y)).id
        for i, t in enumerate(own_t):
            if big and i % 16 == 0 and state.should_yield():
                break  # timeout guard: partial map stands (threats known so far)
            best = float("inf")
            n = 0
            for a in foes:
                if nearest.get(a.id) != t.id:
                    continue
                # Velocity-aware ETA (user: react intelligently — direction
                # from displacement). Known velocity: closing -> project,
                # not closing -> transit (exclude, don't muster for it).
                # Unknown (stale trails) -> legacy distance-ETA.
                eta = _math.hypot(a.x - t.x, a.y - t.y) / speed
                vx, vy = foe_velocity(state, a.id)
                if vx != 0.0 or vy != 0.0:
                    veta = velocity_eta(vx, vy, a.x, a.y, t.x, t.y, speed)
                    if veta is None:
                        continue  # transit past, not inbound
                    eta = veta
                if eta < best:
                    best = eta
                n += 1
            if best <= max_eta:
                out[t.id] = (best, n)
        return out
    return _memoized(state, ("inbound_force", max_eta, speed), _compute)


def defense_train_ok(population: float, cost: float, floor: float,
                     eta: float, home: int, n: int, window: float = 4.0,
                     turns_left: float = 3000.0) -> bool:
    """Defense-train predicate (shared): train iff the marginal army
    improves the outcome — D == N-1 flips take->save (last-stand: bypass
    the floor, the town falls anyway, convert). D == N flips mutual->clean
    only on short horizons (turns_left <= 500): clean saves a standing
    army (terminal score + options) but spends compounding pop — long
    horizons prefer the cheaper mutual (spend static, keep compounding).
    Otherwise hold: D > N already won, D < N-1 already lost (save armies)."""
    if eta > window or n < 1:
        return False
    if home < n - 1 or home > n:
        return False
    if home == n - 1:
        return population >= cost
    return turns_left <= 500 and population - cost >= floor


def inbound_eta(state: "BotState", config: "GameConfig",
                max_eta: float = 8.0) -> dict[int, float]:
    """Per-own-town inbound threat ETA (nearest-own-town prediction).

    An enemy army counts toward the own town nearest to IT. Stationary
    guards sitting on their own towns are excluded (they are not inbound).
    Spend-signal: armies only. Staging (foe towns) is a POSITIONING signal
    (recall/hold, via staging_eta) — mustering costs 1000 against a town
    that may never produce force, while recall is free insurance.
    Returns {town_id: min_eta} for towns with eta <= max_eta."""
    return {tid: eta for tid, (eta, _) in
            inbound_force(state, config, max_eta).items()}


def note_wave_watch(state: "BotState") -> bool:
    """Second-wave watch: a known own army that vanished (not via noted
    BUILD) died in battle — foes double-train, so hold one home for 6 turns.
    Call once per decide; returns whether the watch is active."""
    cur_ids = {a.id for a in state.own_armies()}
    if state._wave_ids and (state._wave_ids - cur_ids - set(state._pending_builds)):
        state._wave_hold_until = state.turn + 6
    state._wave_ids = set(cur_ids)
    return state.turn <= state._wave_hold_until


def should_hold_home(state: "BotState", config: "GameConfig", army,
                     inbound: dict[int, float], wave_watch: bool) -> bool:
    """Keep >=1 army on a threatened town (inbound seen, or second wave
    expected). Extras march."""
    import math as _math
    home_t = next((t for t in state.own_towns()
                   if _math.hypot(army.x - t.x, army.y - t.y) <= 20), None)
    if home_t is None:
        return False
    if home_t.id not in inbound and not wave_watch:
        return False
    others = sum(1 for a in state.own_armies()
                 if a.id != army.id and _math.hypot(a.x - home_t.x, a.y - home_t.y) <= 20)
    return others == 0


def can_train_safely(town: Town, conservative: bool = False) -> bool:
    if town.population < 1600:
        return False
    if conservative:
        if town.population < 2600:
            return False
        if PEAK_LOW <= town.population <= PEAK_HIGH:
            return False
    if town.population > 90000:
        return False
    return True

# ── Shared subprocess protocol ──

def _read_startup():
    cfg = GameConfig()
    fac = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("config "):
            try:
                cfg = GameConfig.from_dict(json.loads(line[7:]))
            except Exception:
                pass
        elif line.startswith("faction "):
            try:
                fac = int(line.split()[1])
            except Exception:
                pass
        elif line == "go":
            break
        elif line.startswith("end "):
            sys.exit(0)
    return cfg, fac

def _read_turn():
    turn = None
    ev = []
    clock = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("turn "):
            try:
                turn = int(line.split()[1])
            except Exception:
                turn = 0
        elif line.startswith("clock "):
            try:
                clock = float(line.split()[1])
            except Exception:
                pass
        elif line == "go":
            if turn is not None:
                return turn, ev, clock
        elif line.startswith("end "):
            return -1, [], None
        elif line.startswith("{"):
            try:
                ev.append(json.loads(line))
            except Exception:
                pass
        else:
            try:
                ev.append(json.loads(line))
            except Exception:
                pass
    return None

def bot_main(decide_fn):
    cfg, faction = _read_startup()
    state = BotState()
    state.init(cfg, faction)
    import os as _os
    trace_dir = _os.environ.get("BOT_TRACE_DIR")
    trace_every = int(_os.environ.get("BOT_TRACE_EVERY", "25"))
    trace_fh = None
    if trace_dir:
        from pathlib import Path as _P
        _P(trace_dir).mkdir(parents=True, exist_ok=True)
        trace_fh = open(_P(trace_dir) / f"trace_{faction}.jsonl", "w", buffering=1)
    while True:
        r = _read_turn()
        if r is None:
            break
        turn, events, clock = r
        if turn == -1:
            break
        t_start = time.time()
        # deadline BEFORE update: a huge backlog must not blow the clock
        # before decide runs — update() yields mid-backlog and carries over.
        # deadline: Fischer clock from engine when sent, else legacy fixed budget
        if clock is None:
            try:
                ms = int(getattr(cfg, "turn_time_ms", 100))
            except Exception:
                ms = 100
            state.deadline = t_start + max(0.02, ms / 1000 - 0.015)
        else:
            state.deadline = t_start + max(0.005, clock / 1000 - BotState.FLUSH_MARGIN_MS / 1000)
        state.update(turn, events)
        state.clock_budget_ms = clock  # idea 6: effort level for this turn
        # Ideas 4+5: replay plans/standing orders on quiet turns.
        orders = state.cached_or_decide(decide_fn, cfg, events)
        _dec_ms = (time.time() - t_start) * 1000.0
        # Command queue: fresh decide first (re-tasks win), then fire due
        # scheduled commands (validated: notes/af prevalence/arrival).
        try:
            orders = list(orders) + state.pop_due_orders(cfg)
        except Exception:
            pass
        # Track issued orders locally (delay-aware decisions + evac flag).
        state.note_orders(orders)
        if trace_fh is not None and (turn % max(1, trace_every) == 0):
            try:
                trace_fh.write(json.dumps({
                    "turn": turn, "faction": faction, "ms": round(_dec_ms, 1),
                    "towns": [{"id": t.id, "f": t.faction, "pop": round(t.population),
                                 "x": round(t.x), "y": round(t.y), "cap": t.is_capital}
                                for t in state.world.towns],
                    "armies": [{"id": a.id, "f": a.faction, "x": round(a.x), "y": round(a.y)}
                                 for a in state.world.armies],
                    "notes": {str(k): [round(v[0]), round(v[1])] for k, v in state._army_targets.items()},
                    "scout": [state._scout_id, getattr(state, "_scout_id2", None)],
                    "mapper": sorted(state.__dict__.get("_mapper", {})),
                    "blood": sorted(state.__dict__.get("_bloodied", {})),
                    "orders": orders}) + "\n")
            except Exception:
                pass
        for o in orders:
            sys.stdout.write(o + "\n")
        sys.stdout.write("go\n")
        sys.stdout.flush()


# ── Step 2 demand API (shared, parameterized personalities) ──
# Personalities are parameter shifts on this backbone (GTO.md s9): pro
# pays full price on time; the others deviate on schedule via depth_extra
# (muster cushion), raid_margin (theft bar), payback_mult (expansion
# patience) — never by different rules.

def home_count(state: "BotState", t, radius: float = 20.0) -> int:
    return sum(1 for a in state.own_armies()
               if math.hypot(a.x - t.x, a.y - t.y) <= radius)


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
    _bt = state.__dict__.get("_bloodied", {}).get(u.id, -10**9)
    _bc = state.__dict__.get("_blood_count", {}).get(u.id, 0)
    if _bt >= state.turn - min(2400, 150 * (2 ** max(0, min(_bc, 5) - 1))):
        s = max(s, 1)
    if s == 0 and state.turn - state._last_seen.get(("town", u.id), -10**9) > 150:
        s = 3
        # Stale-age premium (r55 lesson: stale floor 3 vs real garrison 8
        # — pro bled 43 undersized packs vs ghost-coast towns). Unseen
        # towns accumulate guards: +1 per 500t stale, cap +3. Dead foes
        # are exempt (r113: ghost towns are food — no phantom guards).
        if u.faction not in dead_foes(state):
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
    """Lone-probe gate: visibly-empty (s == 0) AND no fresh grave AND
    FRESH emptiness (r93: 4 probe-mutuals vs turtle's guard — stale s=0
    hid the remustered guard; blood faded between feeds). A probe that
    died at the target within 150 turns means garrison the intel
    missed — hold for the full pack instead of re-feeding onesies."""
    if sel[2] != 0:
        return False
    if state.__dict__.get("_bloodied", {}).get(sel[0].id, -10**9) >= state.turn - 150:
        return False
    if state.turn - state._last_seen.get(("town", sel[0].id), -10 ** 9) > 100:
        return False
    # Attempt-cap (r101-102: probes re-fed vs guards — unseen deaths
    # never blood. Probes get ONE per target per 1000t (packs keep two
    # via recon cap); shared _assaults ledger.
    tries = [t for t in state.__dict__.get("_assaults", {}).get(sel[0].id, [])
             if state.turn - t < 1000]
    if len(tries) >= 1:
        return False
    return True


def _underdog(state: "BotState") -> bool:
    """Behind on towns vs the best-known foe (comeback variance)."""
    mine = sum(1 for t in state.world.towns if t.faction == state.faction)
    foes: dict = {}
    for t in state.world.towns:
        if t.faction != state.faction:
            foes[t.faction] = foes.get(t.faction, 0) + 1
    return bool(foes) and mine < max(foes.values())


def raid_targets(state: "BotState", config, k: int = 1, priced: bool = True,
                 margin: float = 200.0):
    """Top-k priced raid targets + required forces (ranked). Powers
    parallel thin-takes: vs ungarrisoned sprawl, need-sized packets hit
    several towns at once instead of marching the whole pack at one.

    Take needs N >= S+W+1 (standing + printable-before-arrival); the prize
    must clear `margin` (theft pays — the army is not spent, only risked).
    No fieldable gate: an unaffordable-but-valuable target starts a
    PIPELINE (trains build the pack over turns); callers gate the MARCH
    on need <= free. Unpriced (big-war denial) returns max-pressure.
    Memoized per args (r119: 4x/turn hog; pure vs world+intel)."""
    return _memoized(state, ("raid_targets", k, priced, margin),
                     lambda: _raid_targets(state, config, k, priced, margin))


def _raid_targets(state: "BotState", config, k: int = 1, priced: bool = True,
                  margin: float = 200.0):
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
    # Survivor gate (r79: thin-town ping-pong — 600-pop takes halve to
    # 300 and die same turn. Priced raids skip towns whose prize can't
    # survive capture (pop < 2x death threshold); denial/unpriced keeps
    # them (spite has its own math).)
    if priced:
        _survive = 2 * config.death_threshold
        cands = [t for t in cands if t.population >= _survive]
    if not cands:
        return None
    # Pricing arrival over ALL armies (r93: peacetime home-notes emptied
    # fieldable -> arrival inf -> sel None -> no packs/probes ever. Pricing
    # is not gating: callers gate the MARCH on need <= free separately).
    fieldable = [a for a in state.own_armies() if not getattr(a, "is_viceroy", False)]
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
        # Ghost-feast (r119: dead rivals' towns are free land — walk in
        # with 1, don't muster packs against the defenseless).
        if u.faction in dead_foes(state):
            need = 1
        # Underdog aggression (r65 lesson: winner-takes-all by t6000,
        # late dead. GTO variance: the favorite plays safe, the underdog
        # gambles). Behind on towns -> need -1 (min 1): desperate takes
        # seed comebacks and tax the leader.
        if _underdog(state):
            need = max(1, need - 1)
        # Leader-hate (r111: solo blowouts — F1 106k vs zeros, no contest.
        # Emergent gang-up: everyone prefers the pop-leader's towns
        # (need -1, min 1). No alliance, just shared incentives — taxes
        # runaways and seeds three-way races).
        _pops: dict[int, float] = {}
        _dead2 = dead_foes(state)
        _pops = {k: v for k, v in town_pops(state).items()
                 if k == faction or k not in _dead2}
        _foe_pops = {k: v for k, v in _pops.items() if k != faction}
        if _foe_pops and u.faction == max(_foe_pops, key=_foe_pops.get):
            _mine = _pops.get(faction, 0.0)
            if _foe_pops[u.faction] >= 1.5 * _mine:
                need = max(1, need - 1)
        if not priced:
            # Denial needs survivors too (r95: F0's 6 thin takes all died
            # same turn — spite vs 400-pop towns buys nothing). Skip
            # unsurvivable targets in unpriced mode as well.
            if u.population < 2 * config.death_threshold:
                continue
            score = u.population / (1.0 + dist / 300.0)
            # Opportunity premium (campaigns: takes near other rich towns
            # seed followup-rich waves; diffusion neighborhood bonus).
            try:
                score *= 1.0 + min(0.5, state._oppor_at(u.x, u.y) * 0.1)
            except Exception:
                pass
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


def void_note_busy(state: "BotState") -> bool:
    """A settler expansion is already in flight (a note to nowhere-
    known). Scout hop notes don't count (the scout's own hops must not
    block the settler pipeline — recycle lesson) — but ignoring ALL void
    notes floods void trains (endgame lesson: unbounded settlers)."""
    towns = list(state.world.towns)
    for a in state.own_armies():
        if a.id == state._scout_id or a.id == getattr(state, "_scout_id2", None):
            continue
        tgt = state.army_target(a.id)
        if tgt and all(math.hypot(tgt[0] - t.x, tgt[1] - t.y) > 20
                       for t in towns):
            return True
    return False


def _void_horizon(state: "BotState", config, explicit: int | None) -> int:
    """Marginal colony horizon: 500 turns to repay (-500 + ~1/turn),
    capped by game length (no foundings in the last 50 turns — buzzer).
    Explicit overrides (expander sprints 100, S0-fallback 0 capability)."""
    if explicit is not None:
        return explicit
    max_turns = getattr(config, "max_turns", 3000) or 3000
    return min(500, max_turns - 50)


def expansion_demand(state: "BotState", config,
                     params: "DemandParams | None" = None,
                     *, payback_mult: float | None = None,
                     void_horizon: int | None = None) -> bool:
    """Settler pipeline demand. Void (no known foes): colonies ARE the
    void economy (no serialization — a scout's hop note must not block
    the pipeline), but a marginal colony still needs ~500 turns to repay
    (-500 + ~1/turn): settle-branch passes void_horizon=500, S0-fallback
    keeps 0 (capability contract: probe-then-found is recycle's goal).
    Contested: expand iff the colony stream beats the home marginal
    stream (rate comparison on TRUE spend-aware growth — a fresh small
    colony grows ~1.2/turn uncrowded (doctrine: lots of small = great
    growth) vs a crowded home at ~0.3) with horizon to amortize
    (payback_mult scales patience) and one in flight at a time (serial;
    sprawl personalities parallelize). Darkness shields growers; the
    buzzer falls out."""
    if params is None:
        params = DemandParams()
    mult = params.payback_mult if payback_mult is None else payback_mult
    _exp = void_horizon if void_horizon is not None else params.void_horizon
    vhor = _void_horizon(state, config, _exp)
    chor = min(mult * 500, (getattr(config, "max_turns", 3000) or 3000) - 50)
    foe_known = any(t.faction != state.faction for t in state.world.towns) \
        or any(a.faction != state.faction for a in state.world.armies)
    if not foe_known:
        # True void (never seen) expands; eviction-void (seen, stale) is
        # NOT peace (empty t2780: stale intel must not read as void).
        if state._foe_first_seen:
            pass  # fall through to contested caution below
        else:
            # Reprint rule (duel lesson): settling spends the army
            # account — founding below reprint funds strands the empire
            # naked under the train floor (pro t2000: 2 towns 0 armies,
            # 1200 pop vs 1250 floor, never recovers). Expand in true
            # void only from strength (richest town holds floor + cost
            # + threshold after the spend).
            if config.max_turns - state.turn < vhor:
                return False
            if not params.serial:
                return True  # sprawl expands thin by design
            rich = max((t.population for t in state.own_towns()), default=0)
            cost = getattr(config, "army_cost", 500) or 500
            thresh = getattr(config, "death_threshold", 500) or 500
            return rich >= cost + thresh + cost + thresh
    # War-print (fortress-phase): threatened with horizon prints towns
    # for capacity (military, bypasses veto downstream).
    if war_print_need(state, config):
        return True
    if params.serial and void_note_busy(state):
        return False
    # Support ratio (r74 lead-change: F2 led 28k with 5 towns + 1 army,
    # expander picked them one by one — unconquerable sprawl is just
    # future enemy towns. Every town needs a guard or accept the loss:
    # no new colonies while towns outnumber armies + 1). Parallel
    # sprawl opts out (r63 lesson: expander's colonies are TRIPWIRES,
    # not fortresses — best historical Elo sprawled naked). Settlers en
    # route count (pending builds are bodies with jobs).
    # Threat-gated (cheap-suite: HEAD-pro settles 3x slower than its
    # 851ba30 ancestor vs passives — the ratio guards against LIVE
    # pickers, not quiet fields. Armed live foes -> hold; otherwise sprawl.
    _armed = any(a.faction != state.faction for a in state.world.armies)
    if params.serial and _armed \
            and len(state.own_towns()) > len(state.own_armies()) + 1:
        return False
    turns_left = config.max_turns - state.turn
    if turns_left < chor:
        return False
    if not params.rates:
        return True  # sprawl overrides marginal math (documented)
    # Land grab (r48 lesson: foundings stop t2000+, small towns never
    # expand — rate-arbitrage blocks them forever since an uncrowded
    # home grows ~1-2/turn vs a colony's 0.75). Below 20k, expansion is
    # throughput (parallel compounding), not arbitrage: afford +
    # horizon suffices (serial + site_pays still filter downstream).
    # Reprint rule, contested (zero lesson: contact-game founding
    # strands the same way — 2 poor towns, 0 armies, capital starves.
    # Serial personalities expand only from strength everywhere.)
    if params.serial:
        _rich = max((t.population for t in state.own_towns()), default=0)
        _cost = getattr(config, "army_cost", 500) or 500
        _thresh = getattr(config, "death_threshold", 500) or 500
        if _rich < _cost + _thresh + _cost + _thresh:
            return False
    total_pop = sum(t.population for t in state.own_towns())
    if total_pop < 20000:
        return True
    # Median home (r61 lesson: max-growth vetoes everything — one fast
    # uncrowded home blocks colonies forever; a crowded median justifies).
    rates = sorted((state.get_growth(t.id) or 3.0) for t in state.own_towns())
    home_rate = rates[len(rates) // 2] if rates else 3.0
    return 1.2 > home_rate


def reprint_ok(state: "BotState", config) -> bool:
    """Reprint funds (arrival-gate loop): richest own town holds floor
    + cost + threshold after the expansion spend (tracer-evidenced:
    scout-tip auto-founds at rich ~510 split into two starving towns)."""
    rich = max((t.population for t in state.own_towns()), default=0)
    cost = getattr(config, "army_cost", 500) or 500
    thresh = getattr(config, "death_threshold", 500) or 500
    return rich >= cost + thresh + cost + thresh


def train_floor(state: "BotState", config) -> float:
    """Cost-aware train floor: cost + death-threshold + half-cost growth
    buffer (a train must leave the town alive AND viable: greedy t1701,
    ~1300 pop, one 1000-train left 322 < 500 threshold — dead. The old
    hardcoded 1500 assumed cost-500)."""
    cost = getattr(config, "army_cost", 500) or 500
    thresh = getattr(config, "death_threshold", 500) or 500
    foe_known = any(t.faction != state.faction for t in state.world.towns) \
        or any(a.faction != state.faction for a in state.world.armies)
    if not foe_known and not state._foe_first_seen:
        return cost + thresh  # true void: regrow is safe, legacy floor
    # First-print urgency (r122: HEAD opens t1400 vs ancestors t1100 —
    # floor 2000 idles the starter. Armless = print at cost+thresh; the
    # first body unlocks scouting+settling, worth the thin buffer).
    if not state.own_armies():
        return cost + thresh
    return cost + thresh + cost / 2.0


def can_train_standard(state: "BotState", town) -> bool:
    """Comfort gates (pro/greedy shared): floor-90000, no double-order,
    far towns need proportionally more (messenger+muster depth)."""
    config = state.config
    floor = train_floor(state, config) if config else 1500
    if town.population < floor or town.population > 90000:
        return False
    if town.id in state._pending_trains and state.turn <= state._pending_trains[town.id]:
        return False
    cap = state.world.faction_capital(state.faction)
    if cap:
        dist = math.hypot(cap.x - town.x, cap.y - town.y)
        if dist > 100 and town.population < floor + int(dist / 150 * 400):
            return False
    return True


@dataclass
class DemandParams:
    """Personality as parameters (GTO.md s9): pro pays full price on
    time; the others deviate on schedule. depth_extra = muster cushion;
    raid_margin = theft bar; payback_mult = expansion patience;
    threat_window = muster foresight; probe_armies = scout pipeline;
    void_horizon = marginal colony horizon; rates = marginal colony
    must beat home (False = sprawl overrides); serial = one expansion
    at a time (False = parallel sprawl)."""
    depth_extra: float = 0.0
    raid_margin: float = 200.0
    payback_mult: float = 1.0
    threat_window: float = 6.0  # muster foresight (r63: pro saw the
    # raider at eta~4 but mail+print ate the window — capital fell
    # to 1 army with 4609 pop and zero guards. Muster a week out.)
    probe_armies: int = 0
    void_horizon: int | None = None  # None = min(500, max_turns-50)
    rates: bool = True
    serial: bool = True


def _capital_timely(state: "BotState", config, t, eta_n, cost: float) -> bool:
    """Only-timely-guard test: capital threatened, this town's fresh
    guard (print 1t + march) arrives no later than the threat, and no
    other own town fields a timely guard (else THEY print at floors)."""
    import math as _math
    cap = state.world.faction_capital(state.faction)
    if cap is None or t.id == cap.id:
        return False
    eta, _n = eta_n
    force = inbound_force(state, config)
    cap_eta = force.get(cap.id, (float("inf"), 0))[0]
    if cap_eta == float("inf"):
        return False  # capital not threatened: no exception
    speed = max(1.0, config.army_speed)
    mine = _math.hypot(t.x - cap.x, t.y - cap.y) / speed + 1.0
    if mine > cap_eta + 1e-9:
        return False  # arrives late: no exception
    for u in state.own_towns():
        if u.id in (t.id, cap.id):
            continue
        if u.population - cost >= config.death_threshold:
            ou = _math.hypot(u.x - cap.x, u.y - cap.y) / speed + 1.0
            if ou <= cap_eta + 1e-9:
                return False  # other town covers it: no exception
    return True


def demand_trains(state: "BotState", config, can_train,
                  params: "DemandParams | None" = None) -> list[str]:
    """Demand-gated trains (shared Step 2 core): threat muster by outcome
    rule, raid pipeline (pack deficit for the priced target), expansion
    pipeline (void merit / contested rates+payback), plus the prober
    pipeline (`probe_armies`: scouting needs an army, armies need demand
    — the first prober breaks the cycle; pairs with S0 scouting, so only
    bots that scout pass >0). One train per town max (engine cap);
    trains are fungible across demands (deficit shared)."""
    if params is None:
        params = DemandParams()
    out: list[str] = []
    cost = config.army_cost
    # Print cap (r54 lesson: expander printed 120 for 9 towns, 101 idle).
    # Drowning in idle bodies: threat musters still print (survival),
    # everything else waits (packs/expansion/probes use the pile first).
    idle_free = sum(1 for a in state.own_armies()
                    if not state.army_has_target(a.id))
    drowning = idle_free > 2 * max(1, len(state.own_towns()))
    floor = config.death_threshold
    # Standing guard (deterrence posture, Step 2 remainder): D==0 vs a
    # LONE inbound (N==1) within 12 trains early (visible guards make
    # raids price +1). Hopeless (N>=2) holds (don't donate); outcome-rule
    # owns ETA<=4; this extends to 4<ETA<=12.
    # No strip-mine muster: converting compounding pop to idle armies is
    # self-tax without strikes (empty_3000: -1000 with zero battles).
    # Muster stays demand-gated; the buzzer contributes holds (shared
    # hold-set), arrival caps, and no-settle. Strikes filed (Step 6+).
    force = inbound_force(state, config)
    guard_force = inbound_force(state, config, max_eta=12.0)
    home = {t.id: home_count(state, t) for t in state.own_towns()}
    sel = raid_target(state, config, margin=params.raid_margin)
    if sel is not None:
        _, need, _ = sel
        fieldable = sum(1 for a in state.own_armies()
                        if not state.army_has_target(a.id))
        # Pack cap (pre-siege): beyond-need races decline (don't chase
        # receding needs into treadmills). Empire-scaled (r57 lesson:
        # flat 6 + needs 10-12 = permanent peace, zero captures): big
        # empires field big packs (3 + 2/town); small bots stay capped.
        pack_cap = 3 + 2 * len(state.own_towns())
        deficit = [max(0, min(need, pack_cap) - fieldable)]
    else:
        deficit = [0]
    # Strike deficit (windows close!): pack for blitz/buzzer takes too.
    sk = strike_target(state, config, margin=params.raid_margin)
    if sk is not None:
        _, sk_need = sk
        _fieldable = sum(1 for a in state.own_armies()
                         if not state.army_has_target(a.id))
        deficit[0] = max(deficit[0], min(sk_need, 3 + 2 * len(state.own_towns())) - _fieldable, 0)
    expand = expansion_demand(state, config, params)
    # Threat-first (r76: early bloodbath — offense starves defense under
    # the 1/town train cap; packs print while capitals fall. Threatened
    # towns muster before anyone else spends).
    # Shrink-watch (duel lesson): lost a town recently + still losing =
    # gradual bleed evac never catches. Concentrate: unthreatened towns
    # print richest-first (rich gets guards, weak is accepted lost —
    # thin-spread poorest-first donates to raiders). Threatened first
    # always; peace keeps poorest-first (growth needs it).
    _lt = state.__dict__.get("_lost_turn", {})
    _shrinking = any(state.turn - _t <= 1500 for _t in _lt.values())
    cands = sorted(state.own_towns(),
                   key=lambda t: (0 if force.get(t.id) is not None else 1,
                                  0 if state.should_train_for_overcrowding(t) else 1,
                                  state.get_growth(t.id),
                                  -t.population if _shrinking else t.population))
    # No in-loop yield: the trains stage is atomic (anytime prefix
    # property) — trains are cheap, and a partial muster is worse than
    # a late one.
    for i, t in enumerate(cands):
        if i > 0 and i % 8 == 0 and state.should_yield():
            break  # clock discipline: partial trains stand (97-town sprawl
        # otherwise blows the turn budget inside site_pays sigmas)
        if t.id in state._pending_trains and state.turn <= state._pending_trains[t.id]:
            continue
        eta_n = force.get(t.id)
        want = False
        bare = False
        # Naked garrison (r92: expander 3t/0a sat naked, towns fell —
        # peace demand never musters guards (no threat seen). A town with
        # zero home armies prints one guard when affordable (deterrence;
        # onesies bounce off guards, walk into empties). Full floors.
        # Armed fields only (r129: champ fields 1 army vs HEAD's 60 idle
        # guards — deterrence vs nobody is pure waste; compound instead).
        _armed_field = any(a.faction != state.faction for a in state.world.armies)
        if eta_n is None and home.get(t.id, 0) == 0 and _armed_field:
            want = True
        if eta_n is None:
            _g = guard_force.get(t.id)
            if _g is not None and home.get(t.id, 0) == 0 and _g[1] == 1 \
                    and _overmatch(state, 1.5):
                want = True
        if eta_n is not None:
            eta, n = eta_n
            if defense_train_ok(t.population, cost, floor + params.depth_extra, eta,
                                home[t.id], n, window=params.threat_window,
                                turns_left=config.max_turns - state.turn):
                want = True
                bare = (home[t.id] == n - 1)  # doomed-town convert branch
                if bare:
                    # Convert needs a REAL attacker: fresh + (close or
                    # closing-vector). Ghosts and transiting scouts must not
                    # trigger suicide (aggressive t1807: 27-turn phantom).
                    speed = max(1.0, config.army_speed)
                    raiders = inbound_armies(state, config, t.id)
                    # Transit-vs-inbound (r63: greedy bare-converted TWO
                    # towns vs distant closing scouts that never came).
                    # Distant closing = transit (don't suicide for it).
                    bare = any(math.hypot(a.x - t.x, a.y - t.y) / speed <= 2.0
                               or (closing_on(state, a.id, t.x, t.y)
                                   and math.hypot(a.x - t.x, a.y - t.y) / speed <= 4.0)
                               for a in raiders)
                if bare:
                    # Mutual-save beats deny (greedy t1817: converted a
                    # healthy 1483 capital vs 1 raider 110km out, then the
                    # 483 remainder died under threshold). Convert-deny only
                    # when no guard is printable in time (eta < 1) or the
                    # town can't survive printing one (else print: N-for-N
                    # mutual saves towns worth more than the muster).
                    if eta >= 1.0 and t.population - cost >= config.death_threshold:
                        bare = False
        if deficit[0] > 0:
            want = True
        if expand and not drowning:
            want = True
        if len(state.own_armies()) < params.probe_armies and not drowning:
            want = True
        # Blindness rotation (r41 lesson: 10 prints all game, then 9500t
        # dark peace): when map-blind, fund up to probe+2 (eyes + reserve
        # — one army can't scout-map-raid simultaneously).
        if _dark(state) and len(state.own_armies()) < params.probe_armies + 2 \
                and not drowning:
            want = True
        # Blind eyes (r45 lesson: 3 noted-but-useless armies >= probe+2,
        # yet stone blind — bodies aren't eyes). Dark + scoutless +
        # affordable prints eyes directly, at most 1/300t.
        if _dark(state) and state._scout_id is None \
                and getattr(state, "_scout_id2", None) is None \
                and not state.__dict__.get("_mapper") \
                and state.turn - state.__dict__.get("_last_scout_print", -10 ** 9) >= 300 \
                and can_train(state, t) \
                and t.population - cost >= floor + params.depth_extra - 1e-9:
            want = True
            state.__dict__["_last_scout_print"] = state.turn
        if not want:
            continue
        # Crowding-collapse watch (r95 F0 town4 via BRAINSTORM #2:
        # declining towns must not print (except bare converts + capital
        # defense, handled above) — feeding a collapse donates. Threat
        # musters still fire (eta_n set); everything else stands down.
        if eta_n is None and (state.get_growth(t.id) or 0.0) < -1.0:
            continue
        if bare:
            # Print-safe, except timely field-meets (r123: champ2 autopsy
            # showed towns printed to pop=0 vs overwhelming force — but
            # timely-guard demands thin prints that MEET the raider
            # (eta>=1: army fields in time; the town's loss buys the
            # capital). Hopeless (eta<1) thin towns convert instead.
            _eta = eta_n[0] if eta_n is not None else 0.0
            _n = eta_n[1] if eta_n is not None else 99
            # Theater parity (r132: champ splits 1-2 per town — each town
            # sees n<=2 and all print thin and die. Thin prints need
            # global parity (own armies >= foe armies in mirror - 1).
            # Mirror-blindness (r133: parity counted mirror-visible armies;
            # champ's force was unseen at order time -> parity passed -> mail
            # arrived 100t later into a grave. Count recently-seen too.
            _own_ids = {a.id for a in state.own_armies()}
            _seen_ids = {eid for (kind, eid), _t in state._last_seen.items()
                         if kind == 'army' and state.turn - _t <= 300} - _own_ids
            _foe_n = sum(1 for a in state.world.armies if a.faction != state.faction)
            _foe_n = max(_foe_n, len(_seen_ids))
            _own_n = len(state.own_armies())
            if t.population - cost >= config.death_threshold \
                    or (_eta >= 1.0 and _n <= 2 and _own_n + 1 >= _foe_n):
                if t.population >= cost:
                    out.append(f"TRAIN {t.id}")
                    state.note_train(t.id)
                    deficit[0] = max(0, deficit[0] - 1)
        elif (can_train(state, t)
                and t.population - cost >= floor + params.depth_extra - 1e-9):
            # Noted (r135: main emission never noted -> re-issued every
            # turn -> queued multi-execute suicides).
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
        elif (not params.serial and can_train(state, t)
                and t.population - cost >= config.death_threshold):
            # Sprawl prints cheap (r126: floor creep 1500->2000 costs 500t
            # of compounding; champ out-grows HEAD by t2000. Tripwires
            # leave thresh, not full floor.)
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
        elif (params.serial and not state.own_armies() and can_train(state, t)
                and t.population - cost >= config.death_threshold):
            # First-print urgency at emission too (r122: gate said 1500
            # but emission demanded leaving 1500 = real floor 2500).
            # Serial only (r123: sprawlers compound — early prints spend
            # the t2000 war-chest; the champ out-grows, not out-prints).
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
        elif (eta_n is not None and t.population >= cost
                and _capital_timely(state, config, t, eta_n, cost)
                and state.__dict__.get('_timely_turn') != state.turn):
            # Capital-defense exception (user: a <1500 town prints when
            # it's the only timely guard for the capital. Floors protect
            # growth; the capital's survival outranks them. Marches via
            # reinforce_orders (Meeting); town may drop below threshold
            # (accepted trade: town for capital). ONE per decide (r128:
            # three 'only' guards all suicided vs one probe).
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            state.__dict__['_timely_turn'] = state.turn
        elif (expand and deficit[0] <= 0
                and t.population - cost >= config.death_threshold - 1e-9
                and t.id not in state._pending_trains
                # Guard-or-rich (r71: mirror settler-wave left capitals
                # empty — pro1 fell with 3 prints, 0 guards. Back-to-back
                # settler prints need a guard home or a rich town).
                and (len(state.own_armies()) >= 1 or t.population >= 3000)):
            # Settler floor (r70: losers sit poor — full floors lock the
            # first settler (1500-2000 vs 500-1500 towns). Expansion-only
            # want prints at survive-the-print pricing (pack deficit
            # excluded: musters keep full floors). Engine-validity only.
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
        elif (deficit[0] <= 0
                and _dark(state)
                and len(state.own_armies()) < params.probe_armies + 2
                and t.population - cost >= config.death_threshold - 1e-9
                and t.id not in state._pending_trains):
            # Second-body floor (r94: rotation wants eyes+reserve while
            # dark, but full floors block poor towns (first print scouts,
            # capital naked until contact). Survive-pricing funds the
            # second body; pack deficit excluded (musters keep floors).
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
    return out


def _crowd_sigma(state: "BotState", config, x: float, y: float, p: float,
                 extra: tuple | None = None) -> float:
    """Engine crowding sigma at (x,y) for pop p (extra = optional new
    neighbor (ex, ey, epop) included). Transcribed from crowding_net."""
    import math as _math
    eq = getattr(config, "equilibrium_spacing", 0.1) or 0.1
    decay = getattr(config, "crowding_decay", 0.8) or 0.8
    asym_k = getattr(config, "crowding_asymmetry", 0.01) or 0.01
    crange = getattr(config, "info_speed", 150.0) or 150.0
    # Per-turn coord table: world is static during decide, so normalize
    # once (no per-call list-copy, no per-town isinstance — 780 calls x
    # 97 towns was 75k isinstance checks alone). extra appended per call.
    base = _memoized(state, ("town_coords",),
                     lambda: [(t.x, t.y, t.population) for t in state.world.towns])
    towns = base if extra is None else base + [extra]
    # Range prefilter: terms beyond crange contribute exactly 0 (the loop
    # `continue`s them) — skip with a bounding box first. At 97-town
    # sprawl this is ~20x (780 calls x 97 scans blew the turn budget).
    tot = 0.0
    for tx, ty, pn in towns:
        if abs(tx - x) > crange or abs(ty - y) > crange:
            continue
        d = _math.hypot(tx - x, ty - y)
        if d < 1e-9 or d > crange + 1e-9:
            continue
        pn = max(1.0, pn)
        tot += (1.0 + asym_k * _math.log(pn / max(1.0, p))) * \
            ((eq * _math.sqrt(min(pn, p)) / d) ** decay)
    return tot


def site_pays(state: "BotState", config, x: float, y: float) -> bool:
    """Founding veto (fratricide): NET empire growth with the colony
    minus without must clear amortized founding cost (500/turns_left +
    margin). Counts both the colony's stream AND the crowding it deals
    home (externality!) — a colony that stunts home more than it earns
    is vetoed even when its own growth looks fine. Unknown/void sites
    (no intel to tax them) allow. Military staging bypasses (position).
    Empty_3000 lesson: full-map foundings fratricide (-4346)."""
    import math as _math
    cap = getattr(config, "population_cap", 100000.0) or 100000.0
    growth = getattr(config, "population_growth", 0.001) or 0.001
    max_turns = getattr(config, "max_turns", 3000) or 3000
    towns = [t for t in state.own_towns()]
    if not towns:
        return True
    new = (x, y, 500.0)
    net = 0.0
    for t in towns:
        base = growth * t.population * (1.0 - t.population / cap)
        # s0 is site-invariant (world static during decide): memoize per
        # turn (97-town sprawl recomputed it per site — half the sigmas).
        s0 = _memoized(state, ("crowd_s0", t.id),
                       lambda t=t: _crowd_sigma(state, config, t.x, t.y, t.population))
        s1 = _crowd_sigma(state, config, t.x, t.y, t.population, extra=new)
        net += base * (1.0 - s1) - base * (1.0 - s0)
    s_new = _crowd_sigma(state, config, x, y, 500.0)
    # Colony stream PROJECTED (compounding!): a static 500-pop stream
    # (~0.5/turn) never repays 1000 sunk, vetoing everything — but the
    # colony grows (500 -> 1300+ over 1600 turns). Linearized average pop
    # over horizon (capped), home externality stays static (conservative).
    horizon = max(1, max_turns - state.turn)
    avg_pop = min(cap * 0.5, 500.0 * (1.0 + growth * horizon))
    net += growth * avg_pop * (1.0 - avg_pop / cap) * (1.0 - s_new)
    # Sunk = full settler price (army_cost to print; the 500-pop town is
    # what's gained, counted in net above — not the cost). Cost-aware
    # (was hardcoded 500, half the true 1000 price: over-founded).
    cost = getattr(config, "army_cost", 500) or 500
    amort = cost / max(1, max_turns - state.turn) + 0.1
    return net > amort


def recall_deficit(state: "BotState", config) -> list:
    """Conditional recall (shared Step 3 meeting): threatened towns with
    home D < inbound N recall noted settlers (nearest first, up to the
    deficit). Sufficient garrisons let settlers work (blanket recall
    stalls expansion in contact games). Staging (foe towns in striking
    distance) recalls BLANKET — threat-footing concentrates everything
    (count unknown; beheading risk dominates expansion pause). Scouts
    exempt (intel continuity; muster covers the deficit).
    Viceroys/pending-builds exempt."""
    out: list = []
    recalled: set = set()
    stage = staging_eta(state, config)
    # Fresh staging only (first-seen <= 10 turns): urgent (force may be
    # coming inside intel lag). Stale staging without force is an outpost
    # (blanket-recalling for outposts freezes all expansion forever —
    # area-denial by staging; deficit-loop covers real force).
    fresh_stage = False
    for tid in list(stage):
        if state.turn - state._first_seen.get(("town", tid), state.turn) <= 10:
            fresh_stage = True
            break
    if fresh_stage:
        for a in state.own_armies():
            if not a.is_viceroy and state.army_has_target(a.id) \
                    and not state.has_pending_build(a.id) \
                    and a.id != state._scout_id \
                    and a.id != getattr(state, "_scout_id2", None):
                home = min(state.own_towns(),
                           key=lambda t: math.hypot(a.x - t.x, a.y - t.y),
                           default=None)
                if home is not None:
                    out.extend(order_move(state, config, a, home.x, home.y))
                    recalled.add(a.id)
    force = inbound_force(state, config)
    if not force:
        return out
    for tid, (_, n) in force.items():
        town = state.world.get_town(tid)
        if town is None or town.faction != state.faction:
            continue
        home = home_count(state, town)
        if home <= n - 2:
            continue  # hopeless: settlers lineage, don't feed the grinder
        need = max(0, n - home)
        if need <= 0:
            continue
        cands = sorted((a for a in state.own_armies()
                        if not a.is_viceroy and state.army_has_target(a.id)
                        and not state.has_pending_build(a.id)
                        and a.id != state._scout_id
                        and a.id != getattr(state, "_scout_id2", None)
                        and not committed_raid(state, a.id)
                        and a.id not in recalled),
                       key=lambda a: math.hypot(a.x - town.x, a.y - town.y))
        for a in cands[:need]:
            out.extend(order_move(state, config, a, town.x, town.y))
    return out


def reinforce_orders(state: "BotState", config) -> list:
    """Cross-town reinforcement (shared Step 3 meeting v1): deficit
    towns (D < N) pull nearest surplus to mutual (fill to N), arriving
    in time (march <= ETA-1 — too-late holds, no donation marches).
    Surplus = home + untargeted + unheld (hold-set keeps min(home, N+1)
    + buzzer guards, so surplus never strips a defense). Unthreatened
    towns strip bare (no threat needs no guard)."""
    out: list = []
    force = inbound_force(state, config)
    if not force:
        return out
    speed = max(1.0, config.army_speed)
    held = hold_defenders(state, config, force)
    home_of: dict = {}
    for a in state.own_armies():
        for t in state.own_towns():
            if math.hypot(a.x - t.x, a.y - t.y) <= 20.0:
                home_of[a.id] = t.id
                break
    surplus = [a for a in state.own_armies()
               if a.id in home_of and a.id not in held
               and not state.army_has_target(a.id)]
    deficits: list = []
    for t in state.own_towns():
        eta_n = force.get(t.id)
        if eta_n is None:
            continue
        eta, n = eta_n
        if home_count(state, t) < n:
            deficits.append((eta, n, t))
    for eta, n, t in sorted(deficits, key=lambda e: e[0]):
        need = n - home_count(state, t)
        cands = sorted((a for a in surplus
                        if not state.army_has_target(a.id)),
                       key=lambda a: math.hypot(a.x - t.x, a.y - t.y))
        # Cohort dispatch (r97: F1 fed 57 alone into 2 F0 — trickle dies.
        # Send the largest same-turn arrival cohort (need-capped); hold
        # the rest for the next wave instead of donating piecemeal).
        intime = [a for a in cands
                   if math.hypot(a.x - t.x, a.y - t.y) / speed <= max(0.0, eta - 1)]
        waves: dict = {}
        for a in intime:
            key = round(math.hypot(a.x - t.x, a.y - t.y) / speed)
            waves.setdefault(key, []).append(a)
        cohort = max(waves.values(), key=len) if waves else []
        for a in cohort[:max(0, need)]:
            out.extend(order_move(state, config, a, t.x, t.y))
            surplus.remove(a)
    return out


def assault_verified(state: "BotState", target) -> bool:
    """Pre-assault re-verify (r84: fratricide onesies vs stale-mirror
    towns that flipped back unseen). Foe-belief older than 800t holds
    the pack (approach re-scouts: observers near refresh or FoW-erase
    clears); fresh intel assaults. Never-seen (constructed) counts.
    Window 800t (r88: 300t froze the endgame — stale intel + verify =
    peace; fratricide needs ancient ghosts, not fresh-ish intel).
    Ex-own towns (r91: 8-fratricide vs a town that flipped back unseen
    — I should KNOW my own): assault needs fresh (<150t) belief."""
    if ("town", target.id) not in state._last_seen:
        return True
    if target.id in state.__dict__.get("_lost_towns", set()):
        return state.turn - state._last_seen.get(("town", target.id), -10 ** 9) <= 150
    # Opener (r125: champ compounds peacefully to an unbeatable 1.6x
    # by t3000; HEAD waits for blood that never comes. One unverified
    # need-sized strike per game before t2500 seeds first blood.
    # Never overrides ex-own (fratricide guard stands).)
    if state.turn < 2500 and not state.__dict__.get("_bloodied") and not state.__dict__.get("_assaults"):
        return True
    # Naked-settler punish (predator lesson: f5d81dd 40.0 raids cheap;
    # champs expand 4t/0a and get away with it vs patient bots). A town
    # first-seen young (<400t) with no foe army near it is a naked
    # colony — strike without waiting for re-verify. Never overrides
    # ex-own (fratricide guard stands).
    _fs = state._first_seen.get(("town", target.id))
    if _fs is not None and state.turn - _fs <= 400:
        import math as _m
        if not any(a.faction != state.faction
                   and _m.hypot(a.x - target.x, a.y - target.y) <= 150.0
                   for a in state.world.armies):
            return True
    return state.turn - state._last_seen.get(("town", target.id), -10 ** 9) <= 800


def fire_followups(state: "BotState", config) -> list[str]:
    """Fire queued follow-ons (take-then-fan-out with zero idle turns).
    A noted army whose target is arrived (ours/dead/gone) marches its
    queued second wave instead of idling one turn for re-decide."""
    import math as _math
    out: list[str] = []
    fu = state.__dict__.get("_followup", {})
    if not fu:
        return out
    for aid in list(fu):
        a = state.world.get_army(aid)
        if a is None:
            fu.pop(aid, None)
            continue
        tgt = state.army_target(aid)
        done = False
        if tgt is None:
            done = True
        else:
            try:
                rx, ry = state.reckoned_pos(config, aid)
            except Exception:
                rx, ry = a.x, a.y
            # Anticipate landing (user: preemptive campaign — fire the
            # followup when ≤1 turn out, don't wait a turn for the news).
            speed = max(1.0, config.army_speed)
            if _math.hypot(rx - tgt[0], ry - tgt[1]) < 20 + speed:
                done = True
            else:
                hit = None
                for u in state.world.towns:
                    if abs(u.x - tgt[0]) < 15 and abs(u.y - tgt[1]) < 15:
                        hit = u
                        break
                if hit is None or hit.faction == state.faction:
                    done = True  # grave or ours: wave landed
        if done:
            waves = fu.pop(aid, [])
            if waves:
                nx, ny = waves[0]
                out.extend(order_move(state, config, a, nx, ny))
                if len(waves) > 1:
                    fu[aid] = waves[1:]
    return out


def sync_hold(state: "BotState", config, tx: float, ty: float,
              members: list) -> set:
    """Arrival-sync hold-set (coordinated attacks land together: far
    armies leave first, near armies wait — piecemeal arrival dies in
    detail). Members whose travel is >1 turn shorter than the pack's
    longest hold this turn (re-decided each turn; the gap closes)."""
    import math as _math
    speed = max(1.0, config.army_speed)
    by_id = {a.id: a for a in state.own_armies()}
    arrs = {}
    for aid in members:
        a = by_id.get(aid)
        if a is None:
            continue
        try:
            rx, ry = state.reckoned_pos(config, aid)
        except Exception:
            rx, ry = a.x, a.y
        arrs[aid] = _math.hypot(rx - tx, ry - ty) / speed
    if not arrs:
        return set()
    latest = max(arrs.values())
    # Tight 0.5 (r90: 1.0 let far arrive a full turn early and die
    # alone — defeat in detail. Everyone lands the same turn).
    return {aid for aid, arr in arrs.items() if latest - arr > 0.5}


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
        return assault_verified(state, target)
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
    # Recon-by-fire (r68: 5/6 packs hold AT the gates forever — stale
    # premium blocks fair fights (real S often 0-2). Short by <=2 and
    # already there: attack, intel resolves on contact. Assault-once
    # (r69: 48 onesies vs real garrisons — re-assaults every 150t):
    # fresh blood (< 1000t) vetoes. Attempt-cap (r90: unseen deaths
    # never blood — 5 fed in 24t): <=2 assaults per target per 1000t.
    if arrival < 1.0 and 0 < need - len(free_ids) <= 2 \
            and state.__dict__.get("_bloodied", {}).get(target.id, -10 ** 9) < state.turn - 1000:
        tries = [t for t in state.__dict__.get("_assaults", {}).get(target.id, [])
                 if state.turn - t < 1000]
        if len(tries) < 2:
            state.__dict__.setdefault("_assaults", {}).setdefault(target.id, []).append(state.turn)
            return True
    # Strict: ties hold (print can lag a turn; arriving exactly-even is
    # a coin flip on intel delay, and flips favor the defender).
    return arrival > print_turns


def town_pops(state: "BotState") -> dict:
    """Per-faction believed pops, memoized per turn (r119: speed =
    survival — early clock is ~0ms and wobble kills)."""
    def _compute():
        pops: dict = {}
        for t in state.world.towns:
            pops[t.faction] = pops.get(t.faction, 0.0) + t.population
        return pops
    return _memoized(state, "town_pops", _compute)


def dead_foes(state: "BotState", config=None) -> set:
    """Factions that look dead (r113: SICK — 3 ghosts by t1750, survivors
    froze 8500t vs dead rivals' towns: stale threat never clears, packs
    never price, prints never come. A foe with no armies in the live
    world AND none seen in 2000t is dead: its towns are food, not
    threat)."""
    # Young games keep full caution (no history to judge by).
    if state.turn < 2000:
        return set()
    def _compute():
        # Mirror-blindness inverse (r137: stale mirror armies kept ghosts
        # 'live' forever. Live = seen in the last 500t.)
        live_army_factions = {a.faction for a in state.world.armies
                              if state.turn - state._last_seen.get(("army", a.id), -10**9) <= 500}
        out = set()
        foe_factions = ({t.faction for t in state.world.towns} |
                        {a.faction for a in state.world.armies} |
                        set(state.__dict__.get("_foe_army_seen", {})) |
                        set(state.__dict__.get("_foe_first_seen", {}))) - {state.faction}
        seen = state.__dict__.get("_foe_army_seen", {})
        last_print = state.__dict__.get("_foe_last_print", {})
        for f in foe_factions:
            if f in live_army_factions:
                continue
            # Printing foes are alive (r119: a printer fielding nothing
            # right now still remusters — ghost-feast is for the silent).
            if state.turn - last_print.get(f, -10**9) <= 2000:
                continue
            # Active towns are alive (pop-drop = prints at home).
            _active = state.__dict__.get("_foe_active", {})
            if state.turn - _active.get(f, -10**9) <= 2000:
                continue
            # Recently-met foes are alive (no history to judge — grace).
            _first = state.__dict__.get("_foe_first_seen", {})
            if state.turn - _first.get(f, state.turn) <= 2000:
                continue
            if state.turn - seen.get(f, -10**9) > 2000:
                out.add(f)
        return out
    return _memoized(state, "dead_foes", _compute)


def hospice(state: "BotState", config) -> list[str]:
    """Colony hospice (r124: mirror autopsy — 2 towns cratered to pop=0
    ~300t after founding (crowding shadows?). A young (<500t known)
    town below cost+thresh with negative growth is evacuated
    (TRAIN: pop escapes as an army) instead of ridden to zero."""
    out: list[str] = []
    thresh = getattr(config, "death_threshold", 500) or 500
    cost = getattr(config, "army_cost", 1000) or 1000
    force = inbound_force(state, config)
    for t in state.own_towns():
        # Doomed-only (r127: hospice TRAINed 3 healthy towns to death at
        # once — evacuation trades production for bodies. Only under fire.)
        if t.id not in force:
            continue
        if t.is_capital:
            continue
        if t.population >= cost + thresh:
            continue
        if (state.get_growth(t.id) or 0.0) >= 0:
            continue
        age = state.turn - state._first_seen.get(("town", t.id), state.turn)
        if age > 500:
            continue
        if t.population >= cost and not state.has_pending_build(t.id):
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
    return out


def victory_lap(state: "BotState", config) -> list[str]:
    """Victory-lap (r112: winner parks 61 idle armies + churn 176 while
    empty land sits unclaimed. No believed foe towns left: every
    printable town prints, every free army fans out settling (coverage
    already seeks dark cells). No defense needed — nobody's coming."""
    out: list[str] = []
    if any(t.faction != state.faction for t in state.world.towns):
        return out
    # Fog, not victory (r115: mirror is visibility-limited — unseen foes
    # are not dead foes. r136: victory TRAINs at pop>=cost with no floors
    # killed 3 towns (mail executes into graves). Require ALL known foe
    # factions dead, not just contact.
    _known_foes = ({t.faction for t in state.world.towns} | set(state.__dict__.get("_foe_army_seen", {})) | set(state.__dict__.get("_foe_first_seen", {}))) - {state.faction}
    if not _known_foes:
        return out
    if not _known_foes <= dead_foes(state):
        return out
    # Established winners only (single-town mirrors/openings are not
    # victories — need an empire or a late clock).
    if len(state.own_towns()) < 3 and state.turn < 3000:
        return out
    if state.turn > (getattr(config, "max_turns", 10000) or 10000) - 60:
        return out  # buzzer: foundings can't repay
    for t in state.own_towns():
        if t.population >= config.army_cost and not state.has_pending_build(t.id):
            out.append(f"TRAIN {t.id}")
    out.extend(coverage_orders(state, config))
    return out


def bloodlust(state: "BotState", config) -> bool:
    """Killer instinct (r110: SICK endgame stall — snowball decided at
    t4000 then coasts 6000t. A 3x population lead drops every brake:
    no verify windows, no overkill caps, no stale premiums — end it.
    Believed pops via world towns (mirror holds the living)."""
    pops = {k: v for k, v in town_pops(state).items()
            if k == state.faction or k not in dead_foes(state)}
    mine = pops.get(state.faction, 0.0)
    foes = [v for k, v in pops.items() if k != state.faction]
    return bool(foes) and mine >= 3.0 * max(foes)


def second_wind(state: "BotState", config) -> list[str]:
    """Second-wind protocol (r109: F1/F3 zombified — 3-5 prints ALL game,
    dead but present from t2000. A faction down to embers with living
    rivals stops husbanding and gambles: print everything printable,
    muster every body, march the nearest believed-foe town. Win or die
    trying — zombies help nobody, least of all the viewer)."""
    out: list[str] = []
    own_t = state.own_towns()
    if len(own_t) > 2 or len(state.own_armies()) > 1:
        return out
    if not own_t:
        return out
    # Collapse evidence (small-but-healthy openings must NOT trigger:
    # only fire after losing towns or late (turn>1500 still embered).
    if not state.__dict__.get("_lost_towns") and state.turn < 1500:
        return out
    # Living rivals? (believed foe towns; unknown = assume alive.)
    foes = [t for t in state.world.towns if t.faction != state.faction]
    if not foes:
        return out
    ours = {t.id for t in own_t}
    foe_towns = [t for t in foes if t.id not in ours]
    if not foe_towns:
        return out
    home = own_t[0]
    tgt = min(foe_towns, key=lambda t: (t.x - home.x) ** 2 + (t.y - home.y) ** 2)
    for t in own_t:
        if t.population >= config.army_cost and not state.has_pending_build(t.id):
            out.append(f"TRAIN {t.id}")
    for a in state.own_armies():
        out.extend(order_move(state, config, a, tgt.x, tgt.y))
    return out


def hopeless_capital(state: "BotState", config, bar: float = 1700.0) -> bool:
    """D<N hopelessness (shared Step 5): the worst inbound threat cannot
    be met even printing everything printable-in-time (1/town/turn TRAIN
    cap) — pop affordability is necessary but not sufficient (a
    reinforcement that still loses is a donation). Established empires
    almost never qualify (deep print); young ones do."""
    import math as _math
    own_t = state.own_towns()
    if not own_t:
        return False
    force = inbound_force(state, config, max_eta=8.0)
    if not force:
        return False
    tid, (eta, n) = min(force.items(), key=lambda kv: kv[1][0])
    town = next(t for t in own_t if t.id == tid)
    home = sum(1 for a in state.own_armies()
               if _math.hypot(a.x - town.x, a.y - town.y) <= 20.0)
    eta_turns = max(0, int(_math.ceil(eta)))
    printable = sum(eta_turns for t in own_t
                    if t.population >= config.army_cost)
    return home + printable < n


def evac_plan(state: "BotState", config, hopeless: bool, established_stays: bool = True) -> list:
    """Drain-and-flee (shared Step 5): hopeless capital flies to
    max-separation, mustering everything portable first (drain t, fly
    t+1 via _draining flag; ETA<=1 flies now, no time to drain).
    Established empires endure (brain > hub) unless established_stays
    is False (turtle/expander flee any doom)."""
    out: list = []
    cap = state.world.faction_capital(state.faction)
    if cap is None:
        state._draining = False
        return out
    evacuating = any(a.faction == state.faction and a.is_viceroy
                     for a in state.world.armies)
    if evacuating:
        state._draining = False
        return out
    towns = state.own_towns()
    established = len(towns) >= 3 or max((t.population for t in towns), default=0) >= 20000
    if not hopeless or (established and established_stays):
        state._draining = False
        return out
    if cap.population < 2 * config.army_cost:
        state._draining = False
        return out
    foes = [a for a in state.world.armies if a.faction != state.faction]
    if not foes:
        state._draining = False
        return out
    eta = min(math.hypot(a.x - cap.x, a.y - cap.y) for a in foes) / max(1.0, config.army_speed)
    if eta > 1.0 and not state._draining:
        # Drain turn: strip every town to husk (pop >= cost, no floor —
        # leaving!) into the exodus convoy; fly next turn.
        state._draining = True
        for t in towns:
            if t.population >= config.army_cost \
                    and not (t.id in state._pending_trains
                             and state.turn <= state._pending_trains[t.id]):
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
        return out
    state._draining = False
    fx = sum(a.x for a in foes) / len(foes)
    fy = sum(a.y for a in foes) / len(foes)
    dx, dy = cap.x - fx, cap.y - fy
    dist = math.hypot(dx, dy) or 1.0
    ex = min(980.0, max(20.0, cap.x + dx / dist * 250.0))
    ey = min(980.0, max(20.0, cap.y + dy / dist * 250.0))
    return [f"MOVE_CAPITAL {ex:.1f} {ey:.1f}"]


def war_print_need(state: "BotState", config) -> bool:
    """Fortress-phase print-towns (Step 2 remainder): MULTI-raider
    pressure (max inbound N >= 2 — a lone probe is mustered, not
    out-printed) with horizon to amortize (>=500) — print capacity,
    not pop. Bypasses the site veto (military value); rear-area safety
    comes from max-min-dist siting (far from towns incl. foes)."""
    force = inbound_force(state, config)
    if not force or max(n for _, n in force.values()) < 2:
        return False
    return (getattr(config, "max_turns", 3000) or 3000) - state.turn >= 500


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
    # Pricing over ALL armies (r93 cascade: home-notes blind executable
    # checks; callers gate the march separately).
    fieldable = [a for a in state.own_armies() if not getattr(a, "is_viceroy", False)]
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


def en_route(state: "BotState", x: float, y: float, radius: float = 20.0) -> bool:
    """A probe/march already heads within radius of (x,y) (notes are
    live state — a march just ordered suppresses duplicates THIS decide
    too, no flags needed)."""
    for a in state.own_armies():
        tgt = state.army_target(a.id)
        if tgt is not None and math.hypot(tgt[0] - x, tgt[1] - y) <= radius:
            return True
    return False


def stay_behind_hold(state: "BotState", config, p, force, window: float = 4.0) -> bool:
    """Stay-behind vs live threat: the last home guard holds (no offense)
    while inbound sits inside the outcome window. Offense pulled the only
    guard with N=1 at ETA 2.9 (aggressive t1807: home 1->0, bare-convert
    fired, capital suicided). Threat-gated (void S0 unaffected — contact
    stops scouting anyway)."""
    import math as _math
    for t in state.own_towns():
        if _math.hypot(p.x - t.x, p.y - t.y) > 20:
            continue
        e = force.get(t.id)
        if e is not None and e[0] <= window and home_count(state, t) <= 1:
            return True
    return False


def hold_defenders(state: "BotState", config, force: dict) -> set:
    """Hold-set (shared Step 2 core): per threatened town keep
    min(home, N+1) — the +1th is highest-leverage; beyond it extras are
    free. Hopeless towns (D <= N-2) keep none — defenders retreat via
    normal logic instead of annihilating in place. Buzzer adds a blind
    guard (one home per rich town — cheap now, snipers come). (Peacetime
    home-notes TRIED + REVERTED (r93 cascade: notes broke pricing,
    strike, recall, packets). Home firewall lives in coverage_orders.)"""
    held: set = set()
    for t in state.own_towns():
        if t.id not in force:
            continue
        _, n = force[t.id]
        here = sorted((a for a in state.own_armies()
                       if math.hypot(a.x - t.x, a.y - t.y) <= 20.0),
                      key=lambda a: math.hypot(a.x - t.x, a.y - t.y))
        if len(here) <= n - 2:
            continue  # hopeless: retreat, don't annihilate
        for a in here[:min(len(here), n + 1)]:
            held.add(a.id)
    if buzzer_active(state, config):
        for t in state.own_towns():
            if t.population >= 2 * config.army_cost:
                here = [a for a in state.own_armies()
                        if a.id not in held
                        and math.hypot(a.x - t.x, a.y - t.y) <= 20.0]
                # Spare-only: never park the LAST army (it might be the
                # striker — first-strike dominates at the buzzer (GTO s6)).
                if len(here) >= 2:
                    held.add(min(here, key=lambda a: math.hypot(a.x - t.x, a.y - t.y)).id)
    # Step 4 conquest guard: towns taken within 25 turns (starvation
    # window) keep one veteran (raiders re-take starving conquests free).
    for t in state.own_towns():
        if state.turn - state._taken_at.get(t.id, -1000) <= 25:
            here = [a for a in state.own_armies()
                    if a.id not in held
                    and math.hypot(a.x - t.x, a.y - t.y) <= 20.0]
            if here:
                held.add(min(here, key=lambda a: math.hypot(a.x - t.x, a.y - t.y)).id)
    return held

