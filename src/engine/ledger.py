"""Event ledger — time-stamped events with per-faction delayed visibility."""

from __future__ import annotations

import math
from array import array
from collections import deque
from dataclasses import dataclass
from enum import Enum

import numpy as np
from numba import njit


class EventKind(Enum):
    ARMY_SPAWN = "army_spawn"
    TOWN_SPAWN = "town_spawn"
    TOWN_CAPTURE = "town_capture"
    TOWN_DEATH = "town_death"
    ARMY_MOVE = "army_move"
    ARMY_DEATH = "army_death"
    BATTLE = "battle"
    TOWN_UPDATE = "town_update"
    ARMY_UPDATE = "army_update"


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
        # Tagging (Phase 1): factions observing this entry at generation.
        # Ledger-internal only — never serialized to bots (seer lists leak
        # other factions' positions).
        vis = kw.pop("visible_to", None)
        self.visible_to: set = set(vis) if vis else set()
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
        # _version bumps on every log/evict; the columnar snapshot cache
        # keys on it.
        self._version: int = 0
        # window in turns = max_dist / info_speed
        self._window = self.map_diagonal / self.info_speed if self.info_speed != 0 else 10.0
        # S (Phase 1): per-faction last landing turn, 0 if never landed.
        # Tagged entries with generation turn < S never deliver.
        self.S: dict[int, int] = {}
        # Live-registry for tombstones: (kind, id) -> last-known (x, y).
        self._known_ids: set = set()
        self._known_pos: dict = {}
        # Columnar delivery accelerator (Phase 2): one row per update entry,
        # appended at generation alongside the Event log. Tags are a faction
        # bitmask (faction f -> bit 1 << f). Rows never move; _c_start
        # advances past evicted turns (compacts when half-dead).
        self._c_turn = array("q")
        self._c_x = array("d")
        self._c_y = array("d")
        self._c_row = array("q")
        self._c_tag = array("q")
        self._c_pay: list = []
        self._c_seq = array("q")
        # Per dense entity row: last turn its snapshot changed (-1 = new).
        # Lets delivery skipnovalue-change rows without payload compares.
        self._chg: list = []
        # Last snapshot per entity key (generation-side change detection).
        self._last_snap: dict = {}
        self._c_start: int = 0
        self._c_row_of: dict = {}
        self._c_key_of: list = []
        self._col_cache = None

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
            self._version += 1

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
                self._version += 1
            else:
                break
        # Advance the columnar store past the same cutoff (rows are in
        # turn order, so this is amortised O(evicted)).
        cturn = self._c_turn
        start = self._c_start
        n = len(cturn)
        while start < n and cturn[start] + self._window < now - 1e-9:
            start += 1
        if start != self._c_start:
            self._c_start = start
            self._col_cache = None
        if start > 0 and start * 2 >= len(cturn):
            del self._c_turn[:start]
            del self._c_x[:start]
            del self._c_y[:start]
            del self._c_row[:start]
            del self._c_tag[:start]
            del self._c_pay[:start]
            del self._c_seq[:start]
            self._c_start = 0
            self._col_cache = None

    def set_landing(self, faction: int, turn: int) -> None:
        """Record faction's last landing turn S (0 = never landed)."""
        self.S[int(faction)] = int(turn)

    def generate(self, world, turn: int, line_of_sight: float = 150.0) -> None:
        """Append one tagged state entry per observed entity (Phase 1).

        Unconditional but observation-gated: every entity observed by at
        least one faction gets an entry every turn; entities nobody
        observes get none (live entities are always self-observed at
        dist 0, so in practice only unwatched deaths skip). Removed ids
        yield one death entry tagged with observers of the site
        (last-known pos basis), then leave the registry.
        """
        turn = int(turn)
        los = float(line_of_sight)
        los2 = los * los
        # Faction entity positions (LOS anchors) this turn.
        anchors: dict[int, list] = {}
        for t in world.towns:
            anchors.setdefault(t.faction, []).append((t.x, t.y))
        for a in world.armies:
            anchors.setdefault(a.faction, []).append((a.x, a.y))

        def observers(x: float, y: float) -> set:
            out = set()
            for f, pts in anchors.items():
                for px, py in pts:
                    dx = px - x
                    dy = py - y
                    if dx * dx + dy * dy <= los2 + 1e-9:
                        out.add(f)
                        break
            return out

        live: set = set()
        positions: dict = {}
        for t in world.towns:
            key = ("town", t.id)
            live.add(key)
            positions[key] = (t.x, t.y, t.faction)
            vis = observers(t.x, t.y)
            if not vis:
                continue
            payload = {"id": t.id, "faction": t.faction,
                       "population": int(round(t.population)),
                       "is_capital": bool(t.is_capital)}
            ev = Event(turn=turn, x=t.x, y=t.y, kind=EventKind.TOWN_UPDATE,
                       payload=payload, visible_to=vis)
            self.log(ev)
            self._column(turn, t.x, t.y, ("town", t.id), vis, payload, ev.seq)
        for a in world.armies:
            key = ("army", a.id)
            live.add(key)
            positions[key] = (a.x, a.y, a.faction)
            vis = observers(a.x, a.y)
            if not vis:
                continue
            payload = {"id": a.id, "faction": a.faction, "alive": True,
                       "is_viceroy": bool(a.is_viceroy)}
            ev = Event(turn=turn, x=a.x, y=a.y, kind=EventKind.ARMY_UPDATE,
                       payload=payload, visible_to=vis)
            self.log(ev)
            self._column(turn, a.x, a.y, ("army", a.id), vis, payload, ev.seq)
        # Tombstones: vanished ids, tagged with observers of the site.
        for key in self._known_ids:
            if key in live:
                continue
            kind, eid = key
            x, y, fac = self._known_pos.get(key, (0.0, 0.0, -1))
            vis = observers(x, y)
            if not vis:
                continue
            if kind == "town":
                payload = {"id": eid, "faction": fac, "population": 0,
                           "is_capital": False}
                ek = EventKind.TOWN_UPDATE
            else:
                payload = {"id": eid, "faction": fac, "alive": False,
                           "is_viceroy": False}
                ek = EventKind.ARMY_UPDATE
            ev = Event(turn=turn, x=x, y=y, kind=ek, payload=payload,
                       visible_to=vis)
            self.log(ev)
            self._column(turn, x, y, key, vis, payload, ev.seq)
        self._known_ids = live
        self._known_pos = positions

    def _ensure_row(self, key):
        row = self._c_row_of.get(key)
        if row is None:
            row = len(self._c_key_of)
            self._c_row_of[key] = row
            self._c_key_of.append(key)
            self._chg.append(-1)
        return row

    def _column(self, turn: int, x: float, y: float, key, vis: set, payload: dict, seq) -> None:
        """Append one delivery-accelerator row (called for every entry)."""
        # Release cached snapshots FIRST: frombuffer views pin the arrays
        # and appends fail while any view lives.
        self._col_cache = None
        row = self._ensure_row(key)
        mask = 0
        for f in vis:
            mask |= 1 << int(f)
        self._c_turn.append(turn)
        self._c_x.append(x)
        self._c_y.append(y)
        self._c_row.append(row)
        self._c_tag.append(mask)
        self._c_pay.append(payload)
        self._c_seq.append(seq if seq is not None else -1)

    def columns(self):
        """Flat numpy arrays over live column rows (shared per version)."""
        import numpy as np
        cached = self._col_cache
        if cached is not None and cached[0] == self._version and cached[1] == self._c_start:
            return cached[2]
        s = self._c_start
        arr = (np.frombuffer(self._c_turn, dtype=np.int64)[s:],
               np.frombuffer(self._c_x, dtype=np.float64)[s:],
               np.frombuffer(self._c_y, dtype=np.float64)[s:],
               np.frombuffer(self._c_row, dtype=np.int64)[s:],
               np.frombuffer(self._c_tag, dtype=np.int64)[s:],
               np.frombuffer(self._c_seq, dtype=np.int64)[s:],
               self._c_pay[s:],
               len(self._c_key_of),
               np.asarray(self._chg, dtype=np.int64))
        self._col_cache = (self._version, s, arr)
        return arr

    def query(self, faction: int, capital_x: float, capital_y: float, now: float) -> list[Event]:
        """Reference delivery: entries passing TAG + DELAY + S (Phase 1).

        No send-state (every passing entry returned, newest and oldest
        alike) — the Phase 2 builder adds slimming on top and is tested
        for equivalence with this.
        """
        s = self.S.get(faction, 0)
        info = self.info_speed or 150.0
        out = []
        for ev in self.events:
            if ev.kind not in (EventKind.TOWN_UPDATE, EventKind.ARMY_UPDATE):
                continue
            if faction not in ev.visible_to:
                continue
            t = getattr(ev, "turn", getattr(ev, "t", 0))
            if t < s:
                continue
            dist = math.hypot(ev.x - capital_x, ev.y - capital_y)
            if t + dist / info <= now + 1e-9:
                out.append(ev)
        return out




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
