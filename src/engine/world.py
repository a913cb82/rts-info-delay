"""World state — armies, towns, factions, and the map."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class CommandType(IntEnum):
    MOVE_TO = 0
    TRAIN = 1
    BUILD = 2
    MOVE_CAPITAL = 3


@dataclass
class Army:
    id: int
    faction: int
    x: float
    y: float
    target_x: float = 0.0
    target_y: float = 0.0
    has_target: bool = False
    is_viceroy: bool = False
    size: float = 1000.0


@dataclass
class Town:
    id: int
    faction: int
    x: float
    y: float
    population: float
    is_capital: bool = False
    last_improvement: float = 0.0


@dataclass
class Messenger:
    """In-flight order heading toward a target entity."""

    faction: int
    command: CommandType
    target_id: int
    target_type: str  # "army" or "town"
    args: list[float] = field(default_factory=list)
    remaining_dist: float = 0.0


@dataclass
class StandingOrder:
    """Active standing order on an entity (TRAIN / MOVE_TO)."""

    command: CommandType
    target_id: int
    target_type: str
    args: list[float] = field(default_factory=list)


@dataclass
class World:
    armies: list[Army] = field(default_factory=list)
    towns: list[Town] = field(default_factory=list)
    messengers: list[Messenger] = field(default_factory=list)
    standing_orders: list[StandingOrder] = field(default_factory=list)
    map_size: list[int] = field(default_factory=lambda: [1000, 1000])
    ledger: object | None = None
    _next_id: int = 0
    # indexes (excluded from repr)
    _army_by_id: dict[int, Army] = field(default_factory=dict, repr=False, compare=False)
    _town_by_id: dict[int, Town] = field(default_factory=dict, repr=False, compare=False)
    _capital_by_faction: dict[int, Town] = field(default_factory=dict, repr=False, compare=False)
    _towns_by_faction: dict[int, list[Town]] = field(default_factory=dict, repr=False, compare=False)
    _armies_by_faction: dict[int, list[Army]] = field(default_factory=dict, repr=False, compare=False)
    _index_dirty: bool = field(default=True, repr=False, compare=False)

    def allocate_id(self) -> int:
        # ensure no collision with existing ids (handles manual id assignment in tests)
        while True:
            nid = self._next_id
            self._next_id += 1
            if nid not in self._town_by_id and nid not in self._army_by_id:
                # also check lists for case where indexes not yet rebuilt
                if any(t.id == nid for t in self.towns) or any(a.id == nid for a in self.armies):
                    continue
                return nid

    def _rebuild_indexes(self) -> None:
        self._army_by_id = {a.id: a for a in self.armies}
        self._town_by_id = {t.id: t for t in self.towns}
        # faction caches also rebuilt but kept for id-only fast path; faction queries will still use linear scan for correctness
        self._capital_by_faction = {}
        self._towns_by_faction = {}
        self._armies_by_faction = {}
        for t in self.towns:
            self._towns_by_faction.setdefault(t.faction, []).append(t)
            # keep FIRST capital per faction (matches old linear-scan order)
            if t.is_capital and t.faction not in self._capital_by_faction:
                self._capital_by_faction[t.faction] = t
        for a in self.armies:
            self._armies_by_faction.setdefault(a.faction, []).append(a)
        self._index_dirty = False

    def _ensure_indexes(self) -> None:
        if self._index_dirty or len(self._army_by_id) != len(self.armies) or len(self._town_by_id) != len(self.towns):
            self._rebuild_indexes()

    def mark_dirty(self) -> None:
        self._index_dirty = True

    def get_army(self, id: int) -> Army | None:
        # fast path dict
        if not self._index_dirty and self._army_by_id:
            v = self._army_by_id.get(id)
            if v is not None:
                return v
            # not found -> check if stale (army was added directly via list append)
            if len(self._army_by_id) == len(self.armies):
                return None
        # fallback ensure
        self._ensure_indexes()
        return self._army_by_id.get(id)

    def get_town(self, id: int) -> Town | None:
        if not self._index_dirty and self._town_by_id:
            v = self._town_by_id.get(id)
            if v is not None:
                return v
            if len(self._town_by_id) == len(self.towns):
                return None
        self._ensure_indexes()
        return self._town_by_id.get(id)

    def remove_army(self, id: int) -> None:
        self.remove_armies([id])

    def remove_armies(self, ids) -> None:
        # Batch removal: single-pass filters instead of O(A) per id.
        dead = set(ids)
        if not dead:
            return
        self.armies = [a for a in self.armies if a.id not in dead]
        self.standing_orders = [so for so in self.standing_orders if not (so.target_type == "army" and so.target_id in dead)]
        for id in dead:
            if id in self._army_by_id:
                del self._army_by_id[id]
        # invalidate faction cache
        self._index_dirty = True

    def remove_town(self, id: int) -> None:
        self.towns = [t for t in self.towns if t.id != id]
        self.standing_orders = [so for so in self.standing_orders if not (so.target_type == "town" and so.target_id == id)]
        if id in self._town_by_id:
            del self._town_by_id[id]
        self._index_dirty = True

    def clamp_position(self, x: float, y: float) -> tuple[float, float]:
        try:
            mx, my = self.map_size[0], self.map_size[1]
        except Exception:
            mx, my = 1000, 1000
        cx = max(0.0, min(float(x), float(mx)))
        cy = max(0.0, min(float(y), float(my)))
        return (cx, cy)

    def parse_map(self, csv_text: str) -> None:
        self.towns = []
        self.armies = []
        self._index_dirty = True
        seen_capital: set[int] = set()
        if not csv_text:
            return
        lines = csv_text.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("x,"):
                parts = line.split(",")
                try:
                    float(parts[0].strip())
                except:
                    continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            x_str = parts[0].strip()
            y_str = parts[1].strip()
            type_str = parts[2].strip()
            pop_str = parts[3].strip() if len(parts) > 3 else ""
            if not type_str:
                continue
            c = type_str[0]
            is_town = 'A' <= c <= 'Z'
            is_army = 'a' <= c <= 'z'
            if not (is_town or is_army):
                continue
            try:
                x = float(x_str)
                y = float(y_str)
            except:
                continue
            x, y = self.clamp_position(x, y)
            if is_town:
                faction = ord(c) - ord('A')
                pop = 0.0
                if pop_str != "":
                    try:
                        pop = float(pop_str)
                    except:
                        pop = 0.0
                is_cap = faction not in seen_capital
                if is_cap:
                    seen_capital.add(faction)
                town = Town(id=self.allocate_id(), faction=faction, x=float(x), y=float(y), population=float(pop), is_capital=is_cap)
                self.towns.append(town)
            else:
                faction = ord(c) - ord('a')
                army = Army(id=self.allocate_id(), faction=faction, x=float(x), y=float(y))
                self.armies.append(army)
        # Stacked towns are impossible to create in-game (BUILD merges,
        # viceroy founding merges into friendly towns), so a stacked map
        # is an authoring error, not a state to price. Checked post-clamp.
        for i in range(len(self.towns)):
            ti = self.towns[i]
            for j in range(i + 1, len(self.towns)):
                tj = self.towns[j]
                if abs(ti.x - tj.x) < 1e-9 and abs(ti.y - tj.y) < 1e-9:
                    raise ValueError(
                        f"stacked towns in map: town {ti.id} (faction {ti.faction}) "
                        f"and town {tj.id} (faction {tj.faction}) both at "
                        f"({ti.x}, {tj.y})")
        self.mark_dirty()

    def armies_for_faction(self, faction: int) -> list[Army]:
        # Cached; correct because every in-place faction/is_capital mutation
        # site marks the index dirty (see mark_dirty callers in combat/step/events).
        self._ensure_indexes()
        return list(self._armies_by_faction.get(faction, []))

    def towns_for_faction(self, faction: int) -> list[Town]:
        self._ensure_indexes()
        return list(self._towns_by_faction.get(faction, []))

    def faction_capital(self, faction: int) -> Town | None:
        self._ensure_indexes()
        return self._capital_by_faction.get(faction)

    def num_factions(self) -> int:
        facs = set()
        for t in self.towns: facs.add(t.faction)
        for a in self.armies: facs.add(a.faction)
        return len(facs)

    # helpers to keep indexes consistent on direct appends - callers use list append, so we hook via method
    def add_army(self, army: Army) -> None:
        self.armies.append(army)
        self._army_by_id[army.id] = army
        self._armies_by_faction.setdefault(army.faction, []).append(army)

    def add_town(self, town: Town) -> None:
        self.towns.append(town)
        self._town_by_id[town.id] = town
        self._towns_by_faction.setdefault(town.faction, []).append(town)
        if town.is_capital:
            self._capital_by_faction[town.faction] = town
