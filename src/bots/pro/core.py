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
        self._foe_first_seen: dict[int, int] = {}  # faction -> turn first observed
        self._foe_prints: dict[int, int] = {}  # faction -> fielded-force count seen
        self._scout_id: int | None = None  # S0: probing army (hops in _army_targets)
        self._scout_leg: int = 0
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
        self._foe_first_seen = {}
        self._foe_prints = {}
        self._scout_id = None
        self._scout_leg = 0
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
        prev_faction = {}
        for tid in touched_towns:
            t = self.world.get_town(tid)
            if t is not None:
                prev[tid] = t.population
                prev_faction[tid] = t.faction
        known_armies = {a.id for a in self.world.armies}
        for ev in events:
            self._apply_update(ev)
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
            tuple(sorted(self._foe_first_seen.items())),
            tuple(sorted(self._foe_prints.items())),
            self._scout_id,
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
            rep = min(cluster, key=lambda t: (t.population, self._growth.get(t.id, 0), _hash(self.turn, t.id, 99)))
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


def scout_hop_target(state: "BotState", config, p, hop: int) -> tuple[float, float]:
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
    base = f * (2 * math.pi / 5)
    for turn in (0.0, math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2):
        ang = base + turn
        tx = min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(ang)))
        ty = min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(ang)))
        if all(_seg_dist(p.x, p.y, tx, ty, qx, qy) >= r for qx, qy, r in known):
            return (tx, ty)
    return (min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(base))),
            min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(base))))


def maybe_assign_scout(state: "BotState", config, p) -> bool:
    """Mark p as the scout iff no actionable contact exists yet — true
    void OR rubble-only (a visible decoy is not a reason to stay home)."""
    if state._scout_id is not None or state.turn < SCOUT_MIN_TURN:
        return False
    if p.is_viceroy or _scout_contact(state, config):
        return False
    state._scout_id = p.id
    state._scout_leg = 0
    return True


def _expected_delay(state: "BotState", config, x: float, y: float) -> int:
    cap = state.world.faction_capital(state.faction)
    info = (config.info_speed if config is not None else 150.0)
    if cap is None:
        return 1
    return max(1, math.ceil(math.hypot(x - cap.x, y - cap.y) / info))


def ready_to_dispatch(state: "BotState", config, p) -> bool:
    """Quiescence gate: order MOVE_TO only from converged intel.

    The messenger from-check allows ~1 turn of movement; intel older
    than that vs a marching army is a guaranteed dead letter (which then
    strands the army behind a stale note). Converged = trail newest age
    >= 2x expected delay (nothing in flight), or a noted arrival aged >=
    delay (truth static at note since before intel). No trail = idle."""
    tr = state._trails.get(p.id)
    if not tr or len(tr) < 2:
        # never (or once) seen: idle/spawn-stationary by construction.
        return True
    t_new, x, y = tr[-1]
    d = _expected_delay(state, config, x, y)
    if state.turn - t_new >= 2 * d:
        return True
    tgt = state.army_target(p.id)
    if (tgt is not None and math.hypot(x - tgt[0], y - tgt[1]) <= 20
            and state.turn - t_new >= d):
        return True
    return False


def order_move(state: "BotState", config, p, tx: float, ty: float) -> list[str]:
    """MOVE_TO from converged intel (quiescence-gated) + note. [] when
    the order would die in flight — retry next turns, it converges."""
    if not ready_to_dispatch(state, config, p):
        return []
    state.note_move(p.id, float(tx), float(ty))
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


def drop_dead_notes(state: "BotState") -> None:
    """Clear MOVE_TO notes whose army is statically elsewhere: the order
    died in flight (messenger from-check on stale intel) and has_target
    would otherwise block fresh orders forever. The signal is trail
    freshness beyond the intel delay: a mover's snapshots keep arriving
    (delayed, but flowing), while a static army goes delivery-silent, so
    a trail older than expected-delay + 2 at one spot >20km off-note
    means stranded. Catches dispatch-time deaths too (army never left).
    Viceroys exempt (flight notes are live by construction)."""
    cap = state.world.faction_capital(state.faction)
    info = (state.config.info_speed if state.config is not None else 150.0)
    for aid, tgt in list(state._army_targets.items()):
        a = state.world.get_army(aid)
        if a is None or getattr(a, "is_viceroy", False):
            continue
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
        if math.hypot(x - tgt[0], y - tgt[1]) > 20:
            del state._army_targets[aid]


def drive_scout(state: "BotState", config, p):
    """Advance the marked scout; None = not-a-scout (handle normally).

    Unmarks for viable towns (raid logic owns) and foe armies (defense
    owns). Stays out on rubble-only contact, hopping around it, so the
    probe never accidentally captures starvation (trap lesson)."""
    if state._scout_id != p.id:
        return None
    if p.is_viceroy:
        state._scout_id = None
        state._scout_leg = 0
        return None
    if _scout_contact(state, config):
        # Contact: raid/defense owns the army fresh — drop the stale hop
        # target or it hijacks the army into founding next to the prize.
        state._scout_id = None
        state._scout_leg = 0
        state._army_targets.pop(p.id, None)
        return None
    tgt = state.army_target(p.id)
    if tgt is None:
        return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, state._scout_leg))
    if math.hypot(p.x - tgt[0], p.y - tgt[1]) >= 20:
        return []  # mid-hop or waiting arrival-intel: hold
    # arrived: next hop only from quiescent intel (else the order dies in
    # flight); the leg steps exactly when the hop dispatches, never twice
    # on persistent arrival-intel.
    if not ready_to_dispatch(state, config, p):
        return []
    state._scout_leg += 1
    if state._scout_leg >= SCOUT_HOPS:
        # hops exhausted with no contact: builds stage founds on the
        # kept target (settle-as-scout); normal logic owns again. But a
        # kept target inside an own town's founding range is a duplicate
        # merge, not a founding — drop the note so builds don't fire on
        # it (normal site choice or recycle owns instead). And fallback
        # founding is for TRUE void (foe never seen — recycle's capability
        # contract); with foe history the army recycles or raids instead
        # (void_contact t328: -460 late luxury). expansion_demand covers
        # the contested-payback remainder.
        state._scout_id = None
        if tgt is not None and state._foe_first_seen:
            # Foe history: fallback founding faces the same EV bar as any
            # expansion (rates + horizon) — true void keeps the capability
            # contract (recycle), history without demand recycles or raids.
            if not expansion_demand(state, config, void_horizon=500):
                state._army_targets.pop(p.id, None)
                tgt = None
        if tgt is not None:
            interact = (config.interact_radius if config is not None
                        and getattr(config, "interact_radius", None) else 10.0)
            if any(t.faction == state.faction and math.hypot(t.x - tgt[0], t.y - tgt[1]) <= interact + 10.0
                   for t in state.world.towns):
                state._army_targets.pop(p.id, None)
            elif not expansion_demand(state, config):
                state._army_targets.pop(p.id, None)
        return []
    return _dispatch_leg(state, config, p, *scout_hop_target(state, config, p, state._scout_leg))


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


def foe_print_factor(state: "BotState", faction: int, grace: int = 20) -> float:
    """Opponent print calibration for W (printable-before-arrival).

    Factions that have fielded force count full; sterile-observed factions
    (towns seen grace+ turns, zero prints) count zero — unready means
    can't print OR won't print. Fresh intel assumes live (dark-spring
    grace: absence of evidence is not evidence yet)."""
    if state._foe_prints.get(faction, 0) > 0:
        return 1.0
    first = state._foe_first_seen.get(faction, state.turn)
    return 1.0 if state.turn - first < grace else 0.0


def buzzer_active(state: "BotState", config) -> bool:
    """Strip-mine flip (Step 6): retaliation time has run out — guards
    are free (no forgone growth) and raids are cheap. Last 10% (min 20
    turns): founding/pipelines die, pop becomes force, everything
    unguarded is taken."""
    max_turns = getattr(config, "max_turns", 3000) or 3000
    return max_turns - state.turn <= max(20, max_turns // 10)


def inbound_force(state: "BotState", config: "GameConfig",
                  max_eta: float = 8.0) -> dict[int, tuple[float, int]]:
    """Per-own-town inbound threat (ETA, force) by nearest-own-town.

    Same assignment as inbound_eta, plus the count: N raiders imputed to
    the town nearest each of them. Stationary foe guards sitting on
    their own towns are excluded (not inbound)."""
    import math as _math
    faction = state.faction
    own_t = state.own_towns()
    foe_towns = [t for t in state.world.towns if t.faction != faction]
    out: dict[int, tuple[float, int]] = {}
    for t in own_t:
        best = float("inf")
        n = 0
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
            n += 1
        if best <= max_eta:
            out[t.id] = (best, n)
    return out


def dark_pack(state: "BotState", config: "GameConfig",
            window: float = 30.0, stale_after: float = 4.0) -> int:
    """Unaccounted foe mass: foe armies last seen within `window` turns
    but not fresh (older than `stale_after`). A pack that exists but
    isn't visible — the inbound threat model can't see it, so neither
    muster nor hold fires, and the capital sits naked. Ghosts (seen
    longer ago than `window`) are ignored: long-dead or irrelevant.
    Returns the count (0 = the field is empty, seen, or dead)."""
    now = state.turn
    n = 0
    for a in state.world.armies:
        if a.faction == state.faction:
            continue
        seen = state._last_seen.get(("army", a.id))
        if seen is None:
            continue
        age = now - seen
        if age <= stale_after:
            continue  # fresh-visible: normal inbound logic owns it
        if age > window:
            continue  # ghost
        n += 1
    return n


def defense_train_ok(population: float, cost: float, floor: float,
                     eta: float, home: int, n: int, window: float = 4.0) -> bool:
    """Defense-train predicate (shared): train iff the marginal army
    improves the outcome — D == N-1 flips take->save (last-stand: bypass
    the floor, the town falls anyway, convert), D == N flips mutual->clean
    (floor applies: don't gut a town to save armies). Otherwise hold:
    D > N is already won, D < N-1 is already lost (save the armies)."""
    if eta > window or n < 1:
        return False
    if home < n - 1 or home > n:
        return False
    if home == n - 1:
        return population >= cost
    return population - cost >= floor


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


# ── Step 2 demand API (shared, parameterized personalities) ──
# Personalities are parameter shifts on this backbone (GTO.md s9): pro
# pays full price on time; the others deviate on schedule via depth_extra
# (muster cushion), raid_margin (theft bar), payback_mult (expansion
# patience) — never by different rules.

def home_count(state: "BotState", t, radius: float = 20.0) -> int:
    return sum(1 for a in state.own_armies()
               if math.hypot(a.x - t.x, a.y - t.y) <= radius)


def foe_garrison(state: "BotState", u) -> int:
    """Standing defenders imputed to foe town u (nearest same-faction town)."""
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


def can_train_standard(state: "BotState", town) -> bool:
    """Comfort gates (pro/greedy shared): 1500-90000, no double-order,
    far towns need proportionally more (messenger+muster depth)."""
    if town.population < 1500 or town.population > 90000:
        return False
    if town.id in state._pending_trains and state.turn <= state._pending_trains[town.id]:
        return False
    cap = state.world.faction_capital(state.faction)
    if cap:
        dist = math.hypot(cap.x - town.x, cap.y - town.y)
        if dist > 100 and town.population < 1500 + int(dist / 150 * 400):
            return False
    return True


def demand_trains(state: "BotState", config, can_train,
                  *, depth_extra: float = 0.0, raid_margin: float = 200.0,
                  payback_mult: float = 1.0, threat_window: float = 4.0,
                  probe_armies: int = 0, void_horizon: int = 500,
                  block_expand: bool = False) -> list[str]:
    """Demand-gated trains (shared Step 2 core): threat muster by outcome
    rule, raid pipeline (pack deficit for the priced target), expansion
    pipeline (void merit / contested payback), plus the prober pipeline
    (`probe_armies`: scouting needs an army, armies need demand — the
    first prober breaks the cycle; pairs with S0 scouting, so only bots
    that scout pass >0). One train per town max (engine cap);
    `depth_extra` thickens the muster cushion per personality; trains are
    fungible across demands (deficit shared)."""
    out: list[str] = []
    cost = config.army_cost
    floor = config.death_threshold
    # No strip-mine muster: converting compounding pop to idle armies is
    # self-tax without strikes (empty_3000: -1000 with zero battles).
    # Muster stays demand-gated; the buzzer contributes holds (shared
    # hold-set), arrival caps, and no-settle. Strikes filed (Step 6+).
    force = inbound_force(state, config)
    home = {t.id: home_count(state, t) for t in state.own_towns()}
    sel = raid_target(state, config, margin=raid_margin)
    if sel is not None:
        _, need, _ = sel
        fieldable = sum(1 for a in state.own_armies()
                        if not state.army_has_target(a.id))
        deficit = [max(0, need - fieldable)]
    else:
        deficit = [0]
    expand = False if block_expand else expansion_demand(
        state, config, payback_mult, void_horizon)
    cands = sorted(state.own_towns(),
                   key=lambda t: (0 if state.should_train_for_overcrowding(t) else 1,
                                  state.get_growth(t.id), t.population))
    # No in-loop yield: the trains stage is atomic (anytime prefix
    # property) — trains are cheap, and a partial muster is worse than
    # a late one.
    for t in cands:
        if t.id in state._pending_trains and state.turn <= state._pending_trains[t.id]:
            continue
        eta_n = force.get(t.id)
        want = False
        bare = False
        if eta_n is not None:
            eta, n = eta_n
            if defense_train_ok(t.population, cost, floor + depth_extra, eta,
                                home[t.id], n, window=threat_window):
                want = True
                bare = (home[t.id] == n - 1)  # doomed-town convert branch
        if deficit[0] > 0:
            want = True
        if expand:
            want = True
        if len(state.own_armies()) < probe_armies:
            want = True
        if not want:
            continue
        if bare:
            if t.population >= cost:
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
                deficit[0] = max(0, deficit[0] - 1)
        elif (can_train(state, t)
                and t.population - cost >= floor + depth_extra - 1e-9):
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
    return out


def hold_defenders(state: "BotState", config, force: dict) -> set:
    """Hold-set (shared Step 2 core): per threatened town keep
    min(home, N+1) — the +1th is highest-leverage; beyond it extras are
    free. Hopeless towns (D <= N-2) keep none — defenders retreat via
    normal logic instead of annihilating in place. Buzzer adds a blind
    guard (one home per rich town — cheap now, snipers come)."""
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
                if here:
                    held.add(min(here, key=lambda a: math.hypot(a.x - t.x, a.y - t.y)).id)
    return held
