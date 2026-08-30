"""Event ledger — time-stamped events with per-faction delayed visibility."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum


class EventKind(Enum):
    ARMY_SPAWN = "army_spawn"
    TOWN_SPAWN = "town_spawn"
    ARMY_MOVE = "army_move"
    ARMY_DEATH = "army_death"
    BATTLE = "battle"


@dataclass
class Event:
    turn: int
    x: float
    y: float
    kind: EventKind
    payload: dict


class Ledger:
    """Append-only event log with time-based visibility per faction.

    Events are visible to a faction when:
        t + dist(event, capital) / info_speed ≤ now

    During MOVE_CAPITAL flight: no events delivered.
    """

    events: deque[Event]
    eviction_ptr: int  # pointer into sorted events for O(1) amortised eviction

    def __init__(self, info_speed: float, map_diagonal: float) -> None:
        ...

    def log(self, event: Event) -> None:
        """Append an event."""
        ...

    def visible_events(
        self, faction: int, capital_x: float, capital_y: float, now: float
    ) -> list[Event]:
        """Return events visible to faction at current turn.

        Returns [] if faction is mid-MOVE_CAPITAL flight.
        """
        ...

    def evict(self, now: float) -> None:
        """Remove events no longer deliverable to anyone."""
        ...

    def _visibility_delay(self, event: Event, capital_x: float, capital_y: float) -> float:
        """Turn at which event becomes visible: event.t + dist / info_speed."""
        ...
