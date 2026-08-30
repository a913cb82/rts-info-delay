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
    is_fresh: bool = True  # immune from combat/movement this turn


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

    # Id allocation
    _next_id: int = 0

    def allocate_id(self) -> int:
        """Return next unique entity id."""
        ...

    def get_army(self, id: int) -> Army | None:
        """Look up army by id."""
        ...

    def get_town(self, id: int) -> Town | None:
        """Look up town by id."""
        ...

    def remove_army(self, id: int) -> None:
        """Remove army by id."""
        ...

    def remove_town(self, id: int) -> None:
        """Remove town by id."""
        ...

    def clamp_position(self, x: float, y: float) -> tuple[float, float]:
        """Clamp position to map edges."""
        ...

    def parse_map(self, csv_text: str) -> None:
        """Parse starting map CSV, populate armies/towns, assign capitals."""
        ...

    def armies_for_faction(self, faction: int) -> list[Army]:
        """Return all armies belonging to faction."""
        ...

    def towns_for_faction(self, faction: int) -> list[Town]:
        """Return all towns belonging to faction."""
        ...

    def faction_capital(self, faction: int) -> Town | None:
        """Return the capital town for a faction."""
        ...

    def num_factions(self) -> int:
        """Number of distinct factions present."""
        ...
