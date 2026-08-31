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
class BotState:
    """Bot's view of the world, built from events only."""

    def __init__(self):
        self.faction: int = 0
        self.config: GameConfig | None = None
        self.world: World = World()
        self.turn: int = 0

    def init(self, config: GameConfig, faction: int):
        self.config = config
        self.faction = faction
        self.world.map_size = config.map_size
        if config.map:
            self.world.parse_map(config.map)

    def update(self, turn: int, events: list[dict]):
        self.turn = turn
        from engine.events import apply_events
        apply_events(self.world, events, self.config)
        self.world._turn = turn

    def own_towns(self) -> list[Town]:
        return [t for t in self.world.towns if t.faction == self.faction]

    def own_armies(self) -> list[Army]:
        return [a for a in self.world.armies if a.faction == self.faction]


def can_train_safely(town: Town, conservative: bool = False) -> bool:
    if town.population < 1500:
        return False
    if conservative:
        if town.population < 2500:
            return False
        if PEAK_LOW <= town.population <= PEAK_HIGH:
            return False
    return True


# ── Shared subprocess protocol ──




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

        # Output orders
        for o in orders:
            sys.stdout.write(o + "\n")
        sys.stdout.write("go\n")
        sys.stdout.flush()
