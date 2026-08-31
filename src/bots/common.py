"""Bots common — shared helpers and BotState for rl_game_min scripted tiers."""

from __future__ import annotations

import json
import math
import sys
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

def _forecast_pos(army: dict, delta_turns: float, cfg) -> tuple[float, float]:
    if not army.get("has_target") or army.get("target_x") is None:
        return army["x"], army["y"]
    dx = army["target_x"] - army["x"]
    dy = army["target_y"] - army["y"]
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return army["x"], army["y"]
    travel = cfg.army_speed * delta_turns
    if travel >= dist:
        return army["target_x"], army["target_y"]
    s = travel / dist
    return army["x"] + dx * s, army["y"] + dy * s

def _eta(from_pos: dict, to_pos: dict, cfg) -> float:
    return math.hypot(from_pos["x"] - to_pos["x"], from_pos["y"] - to_pos["y"]) / max(1.0, cfg.army_speed)

# ── Shared build-site finder ──

def find_build_site(state, config: GameConfig, ref_x: float, ref_y: float, rmin: float = 80, rmax: float = 300, salt: int = 0) -> tuple[float, float] | None:
    th = config.map_size[0] if isinstance(config.map_size, (list, tuple)) else 1000
    # Sample candidates
    cands: list[tuple[float, float, float, float]] = []  # x,y,min_dist, crowding
    for k in range(24):
        h = _hash(state.turn, int(ref_x * 7 + ref_y * 13) & 0xFFFF, salt + k)
        ang = (h % 3600) / 3600 * 2 * math.pi
        d = rmin + ((h // 3600) % 1000) / 1000 * (rmax - rmin)
        x = ref_x + d * math.cos(ang)
        y = ref_y + d * math.sin(ang)
        x = max(SITE_MARGIN, min(th - SITE_MARGIN, x))
        y = max(SITE_MARGIN, min(th - SITE_MARGIN, y))
        # distance to nearest town (any faction)
        min_dist = min((math.hypot(x - t.x, y - t.y) for t in state.world.towns), default=999)
        if min_dist < config.interact_radius + 10:
            continue
        # crowding proxy: count neighbours within 150 km weighted
        crowding = 0.0
        for t in state.world.towns:
            dist = math.hypot(x - t.x, y - t.y)
            if dist < 150 and dist > 1:
                # rough contribution
                d_eq = 0.1 * math.sqrt(min(t.population, 500))
                crowding += (d_eq / dist) ** 0.8
        cands.append((x, y, min_dist, crowding))
    if not cands:
        return None
    # Score: prefer large min_dist and low crowding
    cands.sort(key=lambda c: (-c[2], c[3]))
    return cands[0][0], cands[0][1]

# ── BotState ──

@dataclass
class BotState:
    def __init__(self):
        self.faction: int = 0
        self.config: GameConfig | None = None
        self.world: World = World()
        self.turn: int = 0
        self._army_targets: dict[int, tuple[float, float]] = {}
        self._pending_trains: dict[int, int] = {}  # town_id -> expiry turn (when pop_change expected)
        self._pending_builds: dict[int, int] = {}  # army_id -> expiry turn
        self._prev_pop: dict[int, float] = {}
        self._growth: dict[int, float] = {}
        self._cluster_cache: tuple[int, list[list[Town]]] | None = None

    def init(self, config: GameConfig, faction: int):
        self.config = config
        self.faction = faction
        self.world.map_size = config.map_size
        if config.map:
            self.world.parse_map(config.map)

    def update(self, turn: int, events: list[dict]):
        self.turn = turn
        prev = {t.id: t.population for t in self.world.towns}
        from engine.events import apply_events
        apply_events(self.world, events, self.config)
        self._growth = {}
        for t in self.world.towns:
            if t.id in prev:
                self._growth[t.id] = t.population - prev[t.id]
            else:
                self._growth[t.id] = 0.0
        self._prev_pop = prev
        # sync local target tracker with engine has_target
        for a in list(self.world.armies):
            if not a.has_target and a.id in self._army_targets:
                # engine says no target but we thought it had one — delivered move arrived or was cancelled
                # keep until army actually arrives? remove if army is idle
                pass
        # remove dead armies from tracker
        alive = {a.id for a in self.world.armies}
        for aid in list(self._army_targets.keys()):
            if aid not in alive:
                del self._army_targets[aid]
        # expire pending trains whose pop_change has arrived (pop dropped) or timed out
        for tid in list(self._pending_trains.keys()):
            t = self.world.get_town(tid)
            if t is None or self.turn > self._pending_trains[tid]:
                del self._pending_trains[tid]
            elif t.population < 1200:
                # pop dropped, train confirmed
                del self._pending_trains[tid]
        for aid in list(self._pending_builds.keys()):
            if aid not in alive or self.turn > self._pending_builds[aid]:
                self._pending_builds.pop(aid, None)
        # if engine now has has_target true, mirror it
        for a in self.world.armies:
            if a.has_target:
                self._army_targets[a.id] = (a.target_x, a.target_y)
            elif a.id in self._army_targets:
                # engine says idle but we have a pending target — it may be that
                # the MOVE_TO messenger has not yet been delivered (1 turn delay).
                # keep tracking; will sync next turn when army_move arrives
                pass
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

    def can_train_here(self, town: Town, conservative: bool = False) -> bool:
        if not can_train_safely(town, conservative):
            return False
        # distance-aware safety: distant towns appear 1-2 turns stale, require extra buffer
        cap = self.world.faction_capital(self.faction)
        if cap:
            dist = math.hypot(cap.x - town.x, cap.y - town.y)
            turns_behind = dist / (self.config.info_speed if self.config else 150)
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
        return math.hypot(x - self.cap_x, y - self.cap_y) / max(1, self.info_speed)

    def forecast_army_pos(self, army: Army | dict, turns_ahead: float | None = None) -> tuple[float, float]:
        if isinstance(army, dict):
            x, y = army["x"], army["y"]
            has_target = army.get("has_target")
            tx, ty = army.get("target_x"), army.get("target_y")
        else:
            x, y = army.x, army.y
            has_target = army.has_target
            tx, ty = army.target_x, army.target_y
        if not has_target or tx is None:
            return x, y
        if turns_ahead is None:
            turns_ahead = self._turns_stale(x, y)
        dx, dy = tx - x, ty - y
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            return x, y
        travel = self.army_speed * turns_ahead
        if travel >= dist:
            return tx, ty
        s = travel / dist
        return x + dx * s, y + dy * s

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
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("turn "):
            try:
                turn = int(line.split()[1])
            except Exception:
                turn = 0
        elif line == "go":
            if turn is not None:
                return turn, ev
        elif line.startswith("end "):
            return -1, []
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
        turn, events = r
        if turn == -1:
            break
        state.update(turn, events)
        orders = decide_fn(state, cfg)
        for o in orders:
            # track MOVE_TO / TRAIN / BUILD locally for delay-aware decisions
            if o.startswith("MOVE_TO"):
                try:
                    parts = o.split()
                    if len(parts) == 6:
                        aid = int(parts[1]); tx = float(parts[4]); ty = float(parts[5])
                        state.note_move(aid, tx, ty)
                    elif len(parts) == 4:
                        aid = int(parts[1]); tx = float(parts[2]); ty = float(parts[3])
                        state.note_move(aid, tx, ty)
                except Exception:
                    pass
            elif o.startswith("BUILD"):
                try:
                    aid = int(o.split()[1])
                    state.note_build(aid)
                except Exception:
                    pass
            elif o.startswith("TRAIN"):
                try:
                    tid = int(o.split()[1])
                    state.note_train(tid)
                except Exception:
                    pass
            sys.stdout.write(o + "\n")
        sys.stdout.write("go\n")
        sys.stdout.flush()
