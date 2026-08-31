"""Bots common — shared helpers and BotState for rl_game_min scripted tiers.

Tuned for rl_game_min defaults:
  map 1000, pop_cap 100k (peak 50k → 25/week), army_cost 1000,
  crowding: d_eq=0.4*sqrt(min), decay 0.3 (flat → long-range), asym 0.006.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army

SITE_MARGIN = 15.0
TRAIN_SURVIVE = 500  # death threshold = cost*efficiency

# Mid-size window where growth is >20/week — avoid TRAINing there
PEAK_LOW = 35000
PEAK_HIGH = 65000


# ── Deterministic hash ──

def _hash(turn: int, i: int, salt: int = 0) -> int:
    h = (turn * 73856093) ^ (i * 19349663) ^ (salt * 83492791)
    return h & 0x7FFFFFFF


# ── View helpers ──

def _own(view, kind: str):
    own = view.get("own_" + kind)
    if own is not None:
        return own
    if view.get("dead"):
        return []
    fid = view.get("faction", 0)
    return [p for p in view.get(kind, []) if p.get("faction") == fid]


def _busy(view) -> set:
    b = {o["entity"] for o in view.get("orders", [])}
    for p in view.get("own_armies", []):
        if p.get("order_kind", 0):
            b.add(p["id"])
    return b


def _world(view):
    fc = view.get("forecast")
    return view if fc is None else fc


def _enemies(view):
    fid = view.get("faction", 0)
    return [a for a in view.get("armies", []) if a.get("faction") != fid]


def _enemy_towns(view):
    fid = view.get("faction", 0)
    return [t for t in view.get("towns", []) if t.get("faction") != fid]


def _site(turn, i, cfg, own_towns, salt=0, rmin=80.0, rmax=250.0, around=None):
    """Deterministic site sampling, crowding-aware."""
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
    """Predict army position delta_turns in future, at army_speed."""
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


def _can_train(pop: float, cfg, conservative: bool = False) -> bool:
    """TRAIN gate: survive and not in peak window if conservative."""
    if pop < cfg.army_cost + TRAIN_SURVIVE + (500 if conservative else 100):
        return False
    if conservative and PEAK_LOW <= pop <= PEAK_HIGH:
        return False
    if pop > 90000:
        return False
    return True


# ── BotState: shared world tracking ──

@dataclass
class TownInfo:
    id: int
    faction: int
    x: float
    y: float
    population: float
    is_capital: bool
    # Tracking
    prev_population: float = 0.0  # population at start of last turn
    spent_on_train: float = 0.0   # total pop spent on TRAIN this turn
    inferred_growth: float = 0.0  # inferred growth this turn (delta + spent)

    @property
    def net_change(self) -> float:
        """Population change this turn (negative = lost pop)."""
        return self.population - self.prev_population

    @property
    def growth(self) -> float:
        """Inferred growth amount (always positive or zero)."""
        return self.inferred_growth


@dataclass
class ArmyInfo:
    id: int
    faction: int
    x: float
    y: float
    has_target: bool = False
    target_x: float = 0.0
    target_y: float = 0.0
    is_viceroy: bool = False


class BotState:
    """Shared bot state that tracks world between turns.

    All bots can use this to:
    - Get the current world view (towns, armies)
    - Know how much each town grew (inferred from pop delta)
    - Know how much each town spent on TRAIN
    - Make informed TRAIN decisions (don't over-train)
    """

    def __init__(self):
        self.faction: int = 0
        self.config: GameConfig | None = None
        self.world: World = World()
        self.turn: int = 0
        self.towns: dict[int, TownInfo] = {}  # id -> TownInfo
        self.armies: dict[int, ArmyInfo] = {}  # id -> ArmyInfo

    def init(self, config: GameConfig, faction: int):
        """Called once at startup."""
        self.config = config
        self.faction = faction
        self.world.map_size = config.map_size
        # Parse starting map
        if config.map:
            self.world.parse_map(config.map)
            # Build initial TownInfo/ArmyInfo from parsed map
            for t in self.world.towns:
                self.towns[t.id] = TownInfo(
                    id=t.id, faction=t.faction, x=t.x, y=t.y,
                    population=t.population, is_capital=t.is_capital,
                    prev_population=t.population,
                )
            for a in self.world.armies:
                self.armies[a.id] = ArmyInfo(
                    id=a.id, faction=a.faction, x=a.x, y=a.y,
                    has_target=a.has_target, target_x=a.target_x, target_y=a.target_y,
                    is_viceroy=a.is_viceroy,
                )

    def update(self, turn: int, events: list[dict]):
        """Update world state from events. Call at start of each turn before deciding orders."""
        self.turn = turn

        # Snapshot previous populations for growth inference
        prev_pops = {tid: t.population for tid, t in self.towns.items()}

        # Apply events to internal world (same as bot main loops)
        for ev in events:
            kind = ev.get("kind")
            if kind == "army_spawn":
                if not self.world.get_army(ev.get("id")):
                    a = Army(
                        id=ev["id"],
                        faction=ev.get("faction", self.faction),
                        x=ev.get("x", 0),
                        y=ev.get("y", 0),
                        is_fresh=True,
                    )
                    a.is_viceroy = ev.get("is_viceroy", False)
                    self.world.armies.append(a)
            elif kind == "town_spawn":
                if not self.world.get_town(ev.get("id")):
                    t = Town(
                        id=ev["id"],
                        faction=ev.get("faction", self.faction),
                        x=ev.get("x", 0),
                        y=ev.get("y", 0),
                        population=ev.get("population", 500),
                        is_capital=ev.get("is_capital", False),
                    )
                    self.world.towns.append(t)
            elif kind == "army_move":
                a = self.world.get_army(ev.get("id"))
                if a:
                    a.x = ev.get("x", a.x)
                    a.y = ev.get("y", a.y)
            elif kind == "army_death":
                self.world.remove_army(ev.get("id"))
            elif kind == "town_death":
                self.world.remove_town(ev.get("id"))

        self.world._turn = turn

        # Rebuild TownInfo and ArmyInfo from world
        new_towns: dict[int, TownInfo] = {}
        for t in self.world.towns:
            existing = self.towns.get(t.id)
            if existing:
                # Update existing — keep tracking fields
                existing.x = t.x
                existing.y = t.y
                existing.faction = t.faction
                existing.is_capital = t.is_capital
                existing.prev_population = existing.population
                existing.population = t.population
                existing.spent_on_train = 0.0
                existing.inferred_growth = 0.0
                new_towns[t.id] = existing
            else:
                # New town
                info = TownInfo(
                    id=t.id, faction=t.faction, x=t.x, y=t.y,
                    population=t.population, is_capital=t.is_capital,
                    prev_population=t.population,
                )
                new_towns[t.id] = info
        self.towns = new_towns

        # Rebuild armies
        new_armies: dict[int, ArmyInfo] = {}
        for a in self.world.armies:
            new_armies[a.id] = ArmyInfo(
                id=a.id, faction=a.faction, x=a.x, y=a.y,
                has_target=a.has_target, target_x=a.target_x, target_y=a.target_y,
                is_viceroy=a.is_viceroy,
            )
        self.armies = new_armies

    def record_train(self, town_id: int):
        """Record that we sent a TRAIN order for this town. Call when issuing TRAIN."""
        t = self.towns.get(town_id)
        if t:
            t.spent_on_train += self.config.army_cost if self.config else 1000

    def infer_growth(self):
        """After orders are sent, infer growth from population deltas.

        Call after the turn runs and update() is called again with new events.
        But since we don't have the post-step pop yet at order time, we estimate:
        growth ≈ prev_pop * growth_rate * (1 - prev_pop/pop_cap) * crowding_net
        We can't compute crowding_net without full world, so we just track the raw delta
        and let _can_train use it for next-turn decisions.

        Actually, the key insight is simpler: we know what we spent on TRAIN.
        If pop decreased by more than we spent, growth was insufficient.
        If pop increased despite spending, growth was strong.
        """
        for t in self.towns.values():
            if t.faction != self.faction:
                continue
            delta = t.population - t.prev_population
            # delta = growth - spent_on_train
            # So growth = delta + spent_on_train
            t.inferred_growth = max(0, delta + t.spent_on_train)

    def own_towns(self) -> list[TownInfo]:
        """Return this faction's towns."""
        return [t for t in self.towns.values() if t.faction == self.faction]

    def own_armies(self) -> list[ArmyInfo]:
        """Return this faction's armies."""
        return [a for a in self.armies.values() if a.faction == self.faction]

    def can_train_safely(self, town_id: int, conservative: bool = False) -> bool:
        """Can we safely TRAIN from this town without killing it?

        Uses inferred growth to predict whether the town can sustain training.
        """
        t = self.towns.get(town_id)
        if not t or t.faction != self.faction:
            return False

        # Basic survival check
        if not _can_train(t.population, self.config, conservative):
            return False

        # If we have growth data, check if pop can sustain training
        if t.prev_population > 0 and t.spent_on_train > 0:
            # We already spent this turn; check if remaining pop is safe
            remaining = t.population - t.spent_on_train
            if remaining < self.config.army_cost + TRAIN_SURVIVE:
                return False

        return True

    def growth_rate(self, town_id: int) -> float:
        """Estimated weekly growth rate for this town (inferred from last turn)."""
        t = self.towns.get(town_id)
        if not t or t.prev_population <= 0:
            return 0.0
        return t.inferred_growth

    def to_view(self) -> dict:
        """Build a view dict compatible with existing decide_orders functions."""
        return {
            "faction": self.faction,
            "turn": self.turn,
            "armies": [
                {
                    "id": a.id, "faction": a.faction,
                    "x": a.x, "y": a.y,
                    "has_target": a.has_target,
                    "target_x": a.target_x, "target_y": a.target_y,
                    "is_viceroy": a.is_viceroy,
                }
                for a in self.armies.values()
            ],
            "towns": [
                {
                    "id": t.id, "faction": t.faction,
                    "x": t.x, "y": t.y,
                    "population": t.population,
                    "is_capital": t.is_capital,
                    "prev_population": t.prev_population,
                    "inferred_growth": t.inferred_growth,
                    "spent_on_train": t.spent_on_train,
                }
                for t in self.towns.values()
            ],
        }


# ── Shared subprocess protocol ──

def _read_startup():
    """Read config + faction from stdin at startup."""
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
    """Read turn header + events from stdin. Returns (turn, events) or None on EOF."""
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
    """Shared bot main loop. Usage: bot_main(my_decide_orders)

    decide_fn signature: (state: BotState, config: GameConfig) -> list[str]
    """
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

        # Update world from events
        state.update(turn, events)

        # Let bot decide orders
        orders = decide_fn(state, cfg)

        # Record TRAIN orders for tracking
        for o in orders:
            parts = o.strip().split()
            if parts and parts[0].upper() == "TRAIN" and len(parts) >= 2:
                try:
                    state.record_train(int(parts[1]))
                except (ValueError, IndexError):
                    pass

        # Output orders
        for o in orders:
            sys.stdout.write(o + "\n")
        sys.stdout.write("go\n")
        sys.stdout.flush()
