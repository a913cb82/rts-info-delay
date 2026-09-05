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
        # crowding so the two trade off in one currency.
        los = getattr(config, "line_of_sight", None) or 150.0
        for t in state.world.towns:
            if t.faction == state.faction:
                continue
            dist = math.hypot(x - t.x, y - t.y)
            if 1 < dist < los:
                d_eq = 0.1 * math.sqrt(max(0.0, min(t.population, 500)))
                guns += (d_eq / dist) ** 0.8
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
        # Near-support (GTO crowding strategy: settle as close to existing
        # towns as the 65km floor allows — closer = cheaper march +
        # reinforcement; the floor + crowding price the packing, distance
        # beyond 150km pays a soft support penalty (far colonies die
        # unsupported). More smaller towns compound faster, but each pays
        # full sunk (army_cost) and needs its own 65km+ of land.
        far = max(0.0, (d_own - 150.0) / 150.0) if own else 0.0
        cands.append((x, y, min_dist, crowding + guns + room + far, d_own))
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
        # else: tolerant — battles are gone, unknown kinds ignored.

    def _remove_town(self, tid: int) -> None:
        self.world.remove_town(tid)
        self._pending_trains.pop(tid, None)
        self._growth.pop(tid, None)
        self._prev_pop.pop(tid, None)

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
                for t in self.world.towns:
                    if t.faction != self.faction and abs(t.x - sx) < interact + 15 \
                            and abs(t.y - sy) < interact + 15 \
                            and math.hypot(t.x - sx, t.y - sy) <= interact + 15:
                        self._bloodied[t.id] = self.turn
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
    return (min(size[0] - 20.0, max(20.0, p.x + SCOUT_HOP_KM * math.cos(base))),
            min(size[1] - 20.0, max(20.0, p.y + SCOUT_HOP_KM * math.sin(base))))


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
    for slot, sid in ((1, state._scout_id), (2, getattr(state, "_scout_id2", None))):
        if sid is not None:
            # Dead scout frees the slot (else one death ends scouting forever).
            if state.world.get_army(sid) is None:
                _scout_unmark(state, slot)
            else:
                continue
        if state.turn < SCOUT_MIN_TURN:
            return False
        if p.is_viceroy or _scout_contact(state, config):
            return False
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
    silence is normal). Piggybacks drop_dead_notes (all five, per turn)."""
    import math as _math
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
            # void note (settler tip, dead-town ghost): no blood, but a
            # ghost still cleans below (overdue-vs-physics) so the slot
            # and targeting free up.
            pass
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
    """Next mapping hop: toward the stalest quadrant centroid. Quadrants
    split the map; staleness = oldest town intel inside (unknown country
    with no known towns counts stalest — unexplored draws mappers)."""
    size = (config.map_size if config is not None
            and getattr(config, "map_size", None) else [1000, 1000])
    cx, cy = size[0] / 2.0, size[1] / 2.0
    quads = [(cx / 2, cy / 2), (cx + cx / 2, cy / 2),
             (cx / 2, cy + cy / 2), (cx + cx / 2, cy + cy / 2)]
    stale = []
    for qx, qy in quads:
        oldest = -10 ** 9
        known = False
        for t in state.world.towns:
            if (t.x < cx) == (qx < cx) and (t.y < cy) == (qy < cy):
                known = True
                ls = state._last_seen.get(("town", t.id), -10 ** 9)
                oldest = max(oldest, ls)
        stale.append((oldest if known else -10 ** 18, qx, qy))
    stale.sort(key=lambda r: r[0])
    qx, qy = stale[0][1], stale[0][2]
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
                eta = _math.hypot(a.x - t.x, a.y - t.y) / speed
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
    approving onesie raids into unseen garrisons."""
    s = garrison_map(state).get(u.id, 0)
    if state.__dict__.get("_bloodied", {}).get(u.id, -10**9) >= state.turn - 150:
        s = max(s, 1)
    return s


def probe_ok(state: "BotState", sel) -> bool:
    """Lone-probe gate: visibly-empty (s == 0) AND no fresh grave.
    A probe that died at the target within 150 turns means garrison the
    intel missed — hold for the full pack instead of re-feeding onesies."""
    return sel[2] == 0 and state.__dict__.get("_bloodied", {}).get(sel[0].id, -10**9) < state.turn - 150


def raid_targets(state: "BotState", config, k: int = 1, priced: bool = True,
                 margin: float = 200.0):
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
        need = int(s + w + 1)
        prize = u.population * (1.0 - eff)
        dist = min((math.hypot(a.x - u.x, a.y - u.y) for a in fieldable),
                   default=float("inf"))
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
    stream (rate comparison on TRUE spend-aware growth — a fresh site at
    ~0.75/turn vs a crowded home at ~0.3) with horizon to amortize
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
            return config.max_turns - state.turn >= vhor
    # War-print (fortress-phase): threatened with horizon prints towns
    # for capacity (military, bypasses veto downstream).
    if war_print_need(state, config):
        return True
    if params.serial and void_note_busy(state):
        return False
    turns_left = config.max_turns - state.turn
    if turns_left < chor:
        return False
    if not params.rates:
        return True  # sprawl overrides marginal math (documented)
    home_rate = max((state.get_growth(t.id) or 3.0) for t in state.own_towns()) \
        if state.own_towns() else 3.0
    return 0.75 > home_rate


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
    threat_window: float = 4.0
    probe_armies: int = 0
    void_horizon: int | None = None  # None = min(500, max_turns-50)
    rates: bool = True
    serial: bool = True


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
        # Pack cap 6 (pre-siege): beyond-need races decline (don't chase
        # receding needs into treadmills; siege raises the cap later).
        deficit = [max(0, min(need, 6) - fieldable)]
    else:
        deficit = [0]
    # Strike deficit (windows close!): pack for blitz/buzzer takes too.
    sk = strike_target(state, config, margin=params.raid_margin)
    if sk is not None:
        _, sk_need = sk
        _fieldable = sum(1 for a in state.own_armies()
                         if not state.army_has_target(a.id))
        deficit[0] = max(deficit[0], min(sk_need, 6) - _fieldable, 0)
    expand = expansion_demand(state, config, params)
    cands = sorted(state.own_towns(),
                   key=lambda t: (0 if state.should_train_for_overcrowding(t) else 1,
                                  state.get_growth(t.id), t.population))
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
                    bare = any(math.hypot(a.x - t.x, a.y - t.y) / speed <= 2.0
                               or closing_on(state, a.id, t.x, t.y)
                               for a in raiders)
        if deficit[0] > 0:
            want = True
        if expand:
            want = True
        if len(state.own_armies()) < params.probe_armies:
            want = True
        if not want:
            continue
        if bare:
            if t.population >= cost:
                out.append(f"TRAIN {t.id}")
                state.note_train(t.id)
                deficit[0] = max(0, deficit[0] - 1)
        elif (can_train(state, t)
                and t.population - cost >= floor + params.depth_extra - 1e-9):
            out.append(f"TRAIN {t.id}")
            state.note_train(t.id)
            deficit[0] = max(0, deficit[0] - 1)
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
        for a in cands:
            if need <= 0:
                break
            if math.hypot(a.x - t.x, a.y - t.y) / speed <= max(0.0, eta - 1):
                out.extend(order_move(state, config, a, t.x, t.y))
                surplus.remove(a)
                need -= 1
    return out


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
