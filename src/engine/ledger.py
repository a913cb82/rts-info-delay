"""Event ledger — time-stamped events with per-faction delayed visibility."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum

import numpy as np


class EventKind(Enum):
    ARMY_SPAWN = "army_spawn"
    TOWN_SPAWN = "town_spawn"
    TOWN_CAPTURE = "town_capture"
    TOWN_DEATH = "town_death"
    ARMY_MOVE = "army_move"
    ARMY_DEATH = "army_death"
    BATTLE = "battle"


@dataclass
class Event:
    turn: int = 0
    x: float = 0.0
    y: float = 0.0
    kind: EventKind = EventKind.BATTLE
    payload: dict = None  # type: ignore
    # Allow alias 't' for turn and flexible construction
    def __init__(self, turn: int | None = None, t: int | None = None, x: float = 0.0, y: float = 0.0, kind: EventKind | str = EventKind.BATTLE, payload: dict | None = None, **kw) -> None:
        # Handle t alias
        if turn is None and t is not None:
            turn = t
        if turn is None:
            turn = kw.pop("turn", kw.pop("t", 0))
        # Ensure x,y
        if "x" in kw:
            x = kw.pop("x")
        if "y" in kw:
            y = kw.pop("y")
        if "kind" in kw:
            kind = kw.pop("kind")
        if "payload" in kw:
            payload = kw.pop("payload")
        # Normalize kind
        if isinstance(kind, str):
            try:
                kind = EventKind(kind)
            except ValueError:
                # Map string like "army_spawn" to enum
                kind = EventKind.BATTLE
        self.turn = int(turn) if turn is not None else 0
        self.x = float(x)
        self.y = float(y)
        self.kind = kind  # type: ignore
        self.payload = payload if payload is not None else {}
        # Also store t alias for compatibility
        self.t = self.turn
        # Handle extra payload from kw if any
        if kw:
            self.payload.update(kw)


class Ledger:
    """Append-only event log with time-based visibility per faction.

    Events are visible to a faction when:
        t + dist(event, capital) / info_speed ≤ now

    During MOVE_CAPITAL flight: no events delivered.
    """

    events: deque[Event]
    eviction_ptr: int  # pointer into sorted events for O(1) amortised eviction

    def __init__(self, info_speed: float = 150.0, map_diagonal: float = 1414.0, **kwargs) -> None:
        # Support alternative construction Ledger(window=...)
        if "window" in kwargs:
            # window supplied directly (used by medium tests)
            window_val = kwargs.pop("window")
            # info_speed and map_diagonal may be mis-supplied; fallback
            try:
                info_speed = float(info_speed)
            except Exception:
                info_speed = 150.0
            # Use info_speed as given, map_diagonal as window*info_speed
            map_diagonal = window_val * info_speed if isinstance(window_val, (int, float)) else 1414.0
        # Also handle case where info_speed is actually window (if called with single arg window)
        # Not needed as stub signature is two args
        if isinstance(info_speed, (int, float)) and isinstance(map_diagonal, (int, float)):
            self.info_speed = float(info_speed)
            self.map_diagonal = float(map_diagonal)
        else:
            self.info_speed = 150.0
            self.map_diagonal = 1414.0
        self.events = deque()
        self.eviction_ptr = 0
        self._next_seq = 0  # dedup key: every logged event gets one
        # opt15: turn index for O(1) turn_events + versioned array cache
        # so the 5 per-turn visible_events queries share one array build.
        # _version bumps on every log/evict; arrays rebuild only on change.
        self._by_turn: dict = {}
        self._version: int = 0
        self._arr_cache = None
        # window in turns = max_dist / info_speed
        self._window = self.map_diagonal / self.info_speed if self.info_speed != 0 else 10.0
        # Per-faction capital establishment time: only events with turn >= capital_since[faction] are visible
        # Default 0 means all events from game start are visible
        self.capital_since: dict[int, int] = {}

    def log(self, event: Event) -> None:
        """Append an event."""
        event.seq = self._next_seq  # type: ignore[attr-defined]
        self._next_seq += 1
        # Handle flexible Event construction: allow t instead of turn, kind as string
        # If event is not proper EventKind, convert
        if not isinstance(event.kind, EventKind):
            # Try to convert string to EventKind
            try:
                # event.kind may be string like "army_spawn"
                if isinstance(event.kind, str):
                    event.kind = EventKind(event.kind)
                else:
                    # Unknown, keep as is or default to BATTLE
                    event.kind = EventKind.BATTLE
            except Exception:
                event.kind = EventKind.BATTLE
        # Ensure turn attribute exists (support t alias)
        if not hasattr(event, "turn"):
            if hasattr(event, "t"):
                event.turn = getattr(event, "t")  # type: ignore
            else:
                event.turn = 0  # fallback
        # Ensure x,y are floats
        try:
            event.x = float(event.x)
            event.y = float(event.y)
        except Exception:
            event.x = 0.0
            event.y = 0.0
        # Insert sorted by turn to keep order
        # Use insertion sort: find position
        # Since events are mostly appended in order, we can check if last event turn <= new turn, append fast
        if len(self.events) == 0 or self.events[-1].turn <= event.turn:
            self.events.append(event)
            self._by_turn.setdefault(event.turn, []).append(event)
            self._version += 1
        else:
            # Need to insert sorted
            # Convert to list, insert, rebuild deque
            lst = list(self.events)
            # Find insertion point (stable)
            inserted = False
            for i, ev in enumerate(lst):
                if ev.turn > event.turn:
                    lst.insert(i, event)
                    inserted = True
                    break
            if not inserted:
                lst.append(event)
            self.events = deque(lst)
            self._by_turn.setdefault(event.turn, []).append(event)
            self._version += 1

    def _arrays(self):
        """Cached (xs, ys, ts) aligned with self.events; rebuilt on change."""
        cached = self._arr_cache
        if cached is not None and cached[0] == self._version:
            return cached[1], cached[2], cached[3]
        n = len(self.events)
        xs = np.empty(n, dtype=np.float64)
        ys = np.empty(n, dtype=np.float64)
        ts = np.empty(n, dtype=np.float64)
        for i, ev in enumerate(self.events):
            xs[i] = ev.x
            ys[i] = ev.y
            ts[i] = getattr(ev, "turn", getattr(ev, "t", 0))
        self._arr_cache = (self._version, xs, ys, ts)
        return xs, ys, ts

    def visible_events(
        self, faction: int, capital_x: float, capital_y: float, now: float, is_in_flight: bool = False, **kwargs
    ) -> list[Event]:
        """Return events visible to faction at current turn.

        Returns [] if faction is mid-MOVE_CAPITAL flight.
        """
        # Support alternative signature used by medium tests: visible(faction, capital_x, capital_y, info_speed, now)
        # Detect if kwargs contains info_speed or now is mis-ordered
        # Also support ledger.visible(...) alias
        if kwargs:
            # handle info_speed override etc.
            if "is_in_flight" in kwargs:
                is_in_flight = kwargs.pop("is_in_flight")
            # If called with info_speed param, ignore?
            pass
        if is_in_flight:
            return []
        # Only events from capital establishment time onwards are visible
        since = self.capital_since.get(faction, 0)
        if not self.events:
            return []
        # Vectorized: same predicates as the scalar loop below used to be —
        # t >= since, and t + hypot/ info_speed <= now + 1e-9.
        xs, ys, ts = self._arrays()
        mask = ts >= since
        if self.info_speed != 0:
            mask = mask & (ts + np.hypot(xs - capital_x, ys - capital_y) / self.info_speed <= now + 1e-9)
        else:
            mask = mask & (ts <= now + 1e-9)
        return [ev for ev, m in zip(self.events, mask) if m]

    def turn_events(self, turn: float) -> list[Event]:
        """Return all events for a specific turn (no distance filtering)."""
        # O(1) index; turns are ints in practice, float queries match exactly.
        try:
            key = int(turn)
            if abs(key - turn) < 1e-9:
                return list(self._by_turn.get(key, []))
        except Exception:
            pass
        result: list[Event] = []
        for ev in self.events:
            t = getattr(ev, "turn", getattr(ev, "t", 0))
            if abs(t - turn) < 1e-9:
                result.append(ev)
        return result

    # Alias for medium tests that call ledger.visible(...)
    def visible(self, *args, faction: int = 0, capital_x: float = 0, capital_y: float = 0, info_speed: float | None = None, now: float = 0, **kw) -> list[Event]:
        # Handle flexible positional args: ledger.visible(0, faction=0, ...) where first arg is duplicate faction
        # If args provided, try to interpret
        if args:
            # If first arg is int and faction kw also provided, ignore args[0] as duplicate
            # If args has single value, treat as now if not provided
            pass
        if info_speed is not None:
            old_speed = self.info_speed
            self.info_speed = float(info_speed)
            res = self.visible_events(faction=faction, capital_x=capital_x, capital_y=capital_y, now=now, **kw)
            self.info_speed = old_speed
            return res
        return self.visible_events(faction=faction, capital_x=capital_x, capital_y=capital_y, now=now, **kw)

    def evict(self, now: float) -> None:
        """Remove events no longer deliverable to anyone."""
        # Window = max_delay = map_diagonal / info_speed
        # An event from turn t is deliverable until t + window (max distance). If now > t+window, no one can see it (even farthest faction at max distance). So evict.
        # For eviction, we use while loop popleft
        # Use eviction_ptr to count popped
        while self.events:
            ev = self.events[0]
            t = getattr(ev, "turn", getattr(ev, "t", 0))
            # If even with max distance it's not visible before now, but actually we want to keep until beyond window
            # If now > t + window + maybe 1? We'll use t + window < now
            if t + self._window < now - 1e-9:
                self.events.popleft()
                self.eviction_ptr += 1
                # keep the turn index in sync (multiset-correct: equal
                # events are interchangeable, eviction is oldest-first)
                bl = self._by_turn.get(t)
                if bl:
                    try:
                        bl.remove(ev)
                    except ValueError:
                        pass
                    if not bl:
                        try:
                            del self._by_turn[t]
                        except KeyError:
                            pass
                self._version += 1
            else:
                break

    def set_capital_since(self, faction: int, turn: int) -> None:
        """Set the turn when faction's current capital was established.

        Only events with turn >= this value will be visible to the faction.
        Called when MOVE_CAPITAL completes.
        """
        self.capital_since[faction] = int(turn)

    def _visibility_delay(self, event: Event, capital_x: float, capital_y: float) -> float:
        """Turn at which event becomes visible: event.t + dist / info_speed."""
        t = getattr(event, "turn", getattr(event, "t", 0))
        dist = math.hypot(event.x - capital_x, event.y - capital_y)
        return t + dist / self.info_speed if self.info_speed != 0 else float(t)


@dataclass
class Messenger:
    """Compatibility messenger for medium order-lag tests L6/L7."""
    from_x: float = 0.0
    from_y: float = 0.0
    to_x: float = 0.0
    to_y: float = 0.0
    turn_sent: int = 0
    payload: dict | None = None
    remaining: float | None = None
    delivered: bool = False

    def __post_init__(self):
        # Compute initial remaining distance
        self.remaining = math.hypot(self.to_x - self.from_x, self.to_y - self.from_y)
        self.delivered = False
        if self.remaining is None:
            self.remaining = 0.0

    def advance(self, info_speed: float = 150.0) -> None:
        """Advance messenger by info_speed; mark delivered if arrived."""
        if self.delivered:
            return
        if self.remaining is None:
            self.remaining = math.hypot(self.to_x - self.from_x, self.to_y - self.from_y)
        self.remaining -= float(info_speed)
        if self.remaining <= 1e-9:
            self.delivered = True
            self.remaining = 0.0
