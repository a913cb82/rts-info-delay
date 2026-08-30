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
    is_fresh: bool = False  # immune from combat/movement this turn when True (set on spawn, cleared next turn)


@dataclass
class Town:
    id: int
    faction: int
    x: float
    y: float
    population: float
    is_capital: bool = False


@dataclass
class Messenger:
    """In-flight order heading toward a target entity."""

    faction: int
    command: CommandType
    target_id: int
    target_type: str  # "army" or "town"
    # Command payload
    args: list[float] = field(default_factory=list)
    # Delivery tracking
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

    # Map bounds for clamping
    map_size: list[int] = field(default_factory=lambda: [1000, 1000])

    # Optional ledger for medium tests that check w.ledger
    ledger: object | None = None

    # Id allocation
    _next_id: int = 0

    def allocate_id(self) -> int:
        """Return next unique entity id."""
        nid = self._next_id
        self._next_id += 1
        return nid

    def get_army(self, id: int) -> Army | None:
        """Look up army by id."""
        for a in self.armies:
            if a.id == id:
                return a
        return None

    def get_town(self, id: int) -> Town | None:
        """Look up town by id."""
        for t in self.towns:
            if t.id == id:
                return t
        return None

    def remove_army(self, id: int) -> None:
        """Remove army by id."""
        self.armies = [a for a in self.armies if a.id != id]
        # Also cleanup standing orders targeting this army (BUILD, MOVE_TO)
        self.standing_orders = [so for so in self.standing_orders if not (so.target_type == "army" and so.target_id == id)]

    def remove_town(self, id: int) -> None:
        """Remove town by id."""
        self.towns = [t for t in self.towns if t.id != id]
        # Cleanup standing orders targeting this town (TRAIN)
        self.standing_orders = [so for so in self.standing_orders if not (so.target_type == "town" and so.target_id == id)]

    def clamp_position(self, x: float, y: float) -> tuple[float, float]:
        """Clamp position to map edges."""
        # map_size may be missing or set externally
        try:
            mx, my = self.map_size[0], self.map_size[1]
        except Exception:
            mx, my = 1000, 1000
        cx = max(0.0, min(float(x), float(mx)))
        cy = max(0.0, min(float(y), float(my)))
        return (cx, cy)

    def parse_map(self, csv_text: str) -> None:
        """Parse starting map CSV, populate armies/towns, assign capitals."""
        # Reset
        self.towns = []
        self.armies = []
        # Track capitals per faction
        seen_capital: set[int] = set()
        if not csv_text:
            return
        lines = csv_text.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # skip header if starts with x, (like x,y,type,population)
            if line.lower().startswith("x,"):
                # Check if first char is letter, but header case
                # If line contains non-numeric first field, treat as header
                parts = line.split(",")
                # Try to parse first field as float; if fails, skip line
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
            # Determine if town or army
            is_town = 'A' <= c <= 'Z'
            is_army = 'a' <= c <= 'z'
            if not (is_town or is_army):
                continue
            try:
                x = float(x_str)
                y = float(y_str)
            except:
                continue
            # Clamp
            x, y = self.clamp_position(x, y)
            if is_town:
                faction = ord(c) - ord('A')
                # parse population
                pop = 0.0
                if pop_str != "":
                    try:
                        pop = float(pop_str)
                    except:
                        pop = 0.0
                else:
                    # missing pop treat as 0 or skip – we treat as 0
                    pop = 0.0
                is_cap = faction not in seen_capital
                if is_cap:
                    seen_capital.add(faction)
                # For towns, ensure x,y are float
                town = Town(id=self.allocate_id(), faction=faction, x=float(x), y=float(y), population=float(pop), is_capital=is_cap)
                self.towns.append(town)
            else:  # army
                faction = ord(c) - ord('a')
                army = Army(id=self.allocate_id(), faction=faction, x=float(x), y=float(y))
                self.armies.append(army)

    def armies_for_faction(self, faction: int) -> list[Army]:
        """Return all armies belonging to faction."""
        return [a for a in self.armies if a.faction == faction]

    def towns_for_faction(self, faction: int) -> list[Town]:
        """Return all towns belonging to faction."""
        return [t for t in self.towns if t.faction == faction]

    def faction_capital(self, faction: int) -> Town | None:
        """Return the capital town for a faction."""
        for t in self.towns:
            if t.faction == faction and t.is_capital:
                return t
        return None

    def num_factions(self) -> int:
        """Number of distinct factions present."""
        facs = set()
        for t in self.towns:
            facs.add(t.faction)
        for a in self.armies:
            facs.add(a.faction)
        return len(facs)
