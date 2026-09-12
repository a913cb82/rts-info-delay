"""aggressive intel — split from core.py (mechanical, behavior-identical)."""

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
            self._first_seen.setdefault(("town", eid), self.turn)
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
        if len(hist) == 4 and hist[-1][2] - hist[0][2] <= 300 \
                and len({h[:2] for h in hist}) >= 3:
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
    threat_window: float = 4.0
    probe_armies: int = 0
    void_horizon: int | None = None  # None = min(500, max_turns-50)
    rates: bool = True
    serial: bool = True



def en_route(state: "BotState", x: float, y: float, radius: float = 20.0) -> bool:
    """A probe/march already heads within radius of (x,y) (notes are
    live state — a march just ordered suppresses duplicates THIS decide
    too, no flags needed)."""
    for a in state.own_armies():
        tgt = state.army_target(a.id)
        if tgt is not None and math.hypot(tgt[0] - x, tgt[1] - y) <= radius:
            return True
    return False


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
