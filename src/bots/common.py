"""Bots common — shared helpers and BotState for rl_game_min scripted tiers."""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army

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

def find_build_site(state, config: GameConfig, ref_x: float, ref_y: float, rmin: float = 80, rmax: float = 300, salt: int = 0) -> tuple[float, float] | None:
    key = (state.turn, int(ref_x), int(ref_y), rmin, rmax, salt, state.faction)
    if key in _build_site_cache:
        return _build_site_cache[key]
    th = config.map_size[0] if isinstance(config.map_size, (list, tuple)) else 1000
    cands: list[tuple[float, float, float, float]] = []
    # pre-filter towns near ref for faster crowding (only within rmax+150)
    nearby_towns = [t for t in state.world.towns if math.hypot(t.x - ref_x, t.y - ref_y) < rmax + 200]
    if not nearby_towns:
        nearby_towns = state.world.towns[:50]  # fallback small sample
    for k in range(16):
        h = _hash(state.turn, int(ref_x * 7 + ref_y * 13) & 0xFFFF, salt + k)
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
        self._trails: dict = {}  # army_id -> deque[(turn, x, y)] (velocity)
        self._wave_ids: set = set()
        self._wave_hold_until: int = -1
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
        self._trails = {}
        self._wave_ids = set()
        self._wave_hold_until = -1

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
                    t.faction = int(ev.get("faction", t.faction))
                    t.x = float(ev.get("x", t.x))
                    t.y = float(ev.get("y", t.y))
                    t.population = float(ev.get("population", t.population))
                    t.is_capital = bool(ev.get("is_capital", t.is_capital))
            self._last_seen[("town", eid)] = self.turn
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
        # else: tolerant — battles are gone, unknown kinds ignored.

    def _remove_town(self, tid: int) -> None:
        self.world.remove_town(tid)
        self._pending_trains.pop(tid, None)
        self._growth.pop(tid, None)
        self._prev_pop.pop(tid, None)

    def _remove_army(self, aid: int) -> None:
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
        self.turn = turn
        self._last_turn = turn
        # Snapshot prev pops for towns this batch names, then apply absolutely.
        touched_towns, _ = _batch_ids(events)
        prev = {}
        for tid in touched_towns:
            t = self.world.get_town(tid)
            if t is not None:
                prev[tid] = t.population
        for ev in events:
            self._apply_update(ev)
        if events:
            # Field flips (faction/flag) don't change list lengths, so the
            # world's index wouldn't rebuild without this (mark_dirty
            # contract: production mutation sites all mark).
            self.world.mark_dirty()
        for tid in touched_towns:
            t = self.world.get_town(tid)
            if t is None:
                self._growth.pop(tid, None)
                continue
            if tid in prev:
                self._growth[tid] = self._growth.get(tid, 0.0) + (t.population - prev[tid])
            else:
                self._growth.setdefault(tid, 0.0)
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
        self._army_targets[army_id] = (tx, ty)

    def note_build(self, army_id: int):
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
        self._pending_trains[town_id] = self.turn + delay + 1

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
        return self._growth.get(town_id, 0.0)

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
            rep = min(cluster, key=lambda t: (t.population, self._growth.get(t.id, 0), _hash(self.turn, t.id, 99)))
            return rep.id == town.id
        return False

# ── BotForecast: separate from BotState, constructed from it ──

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
        extrapolates the bot-kept position trail by mail lag."""
        if isinstance(army, dict):
            aid, x, y = army["id"], army["x"], army["y"]
        else:
            aid, x, y = army.id, army.x, army.y
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


def inbound_eta(state: "BotState", config: "GameConfig",
                max_eta: float = 8.0) -> dict[int, float]:
    """Per-own-town inbound threat ETA (nearest-own-town prediction).

    An enemy army counts toward the own town nearest to IT. Stationary
    guards sitting on their own towns are excluded (they are not inbound).
    Returns {town_id: min_eta} for towns with eta <= max_eta."""
    import math as _math
    faction = state.faction
    own_t = state.own_towns()
    foe_towns = [t for t in state.world.towns if t.faction != faction]
    out: dict[int, float] = {}
    for t in own_t:
        best = float("inf")
        for a in state.world.armies:
            if a.faction == faction:
                continue
            if any(_math.hypot(a.x - u.x, a.y - u.y) <= 15
                   for u in foe_towns if u.faction == a.faction):
                continue
            if min(own_t, key=lambda u: _math.hypot(a.x - u.x, a.y - u.y)).id != t.id:
                continue
            eta = _math.hypot(a.x - t.x, a.y - t.y) / max(1.0, config.army_speed)
            if eta < best:
                best = eta
        if best <= max_eta:
            out[t.id] = best
    return out


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
        # Track issued orders locally (delay-aware decisions + evac flag).
        state.note_orders(orders)
        for o in orders:
            sys.stdout.write(o + "\n")
        sys.stdout.write("go\n")
        sys.stdout.flush()
