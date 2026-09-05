"""Event ledger — time-stamped events with per-faction delayed visibility."""

from __future__ import annotations

import math
from array import array
from collections import deque
from dataclasses import dataclass
from enum import Enum

import numpy as np
from numba import njit


@njit
def _observe_masks(ex, ey, skip, facs, f_start, f_len, anc_x, anc_y,
                   los2, full_mask, out):
    """Bitmask of observing factions per entity (flat anchor scan).

    Same float64 ops and comparison as the reference scan, so tags are
    bit-identical; the OR-mask makes discovery order irrelevant to
    determinism. Live entities pass their own faction as skip (they
    self-observe at dist 0 by construction); deaths pass -1."""
    eps = 1e-9
    for i in range(ex.shape[0]):
        mask = 0
        sk = skip[i]
        skbit = np.int64(0)
        if sk >= 0:
            skbit = np.int64(1) << np.int64(sk)
        target = full_mask ^ skbit
        for fi in range(facs.shape[0]):
            f = facs[fi]
            if sk >= 0 and f == sk:
                continue
            bit = np.int64(1) << np.int64(f)
            base = f_start[fi]
            for k in range(base, base + f_len[fi]):
                dx = anc_x[k] - ex[i]
                dy = anc_y[k] - ey[i]
                if dx * dx + dy * dy <= los2 + eps:
                    mask |= bit
                    break
            if mask == target:
                break
        out[i] = mask


def _precompile_observe():
    # Pay JIT once at import, never mid-game (house rule opt10).
    ex = np.zeros(4, dtype=np.float64)
    sk = np.full(4, -1, dtype=np.int64)
    fa = np.zeros(1, dtype=np.int64)
    st = np.zeros(1, dtype=np.int64)
    ln = np.zeros(1, dtype=np.int64)
    out = np.zeros(4, dtype=np.int64)
    _observe_masks(ex, ex, sk, fa, st, ln, ex, ex, 22500.0,
                   np.int64(1), out)


_precompile_observe()


class EventKind(Enum):
    # Wire carries only state updates. Step/record dicts use plain kind
    # strings (never this enum); nothing else logs ledger entries.
    TOWN_UPDATE = "town_update"
    ARMY_UPDATE = "army_update"


@dataclass
class Event:
    turn: int = 0
    x: float = 0.0
    y: float = 0.0
    kind: EventKind = EventKind.ARMY_UPDATE
    payload: dict = None  # type: ignore
    def __init__(self, turn: int = 0, x: float = 0.0, y: float = 0.0,
                 kind: EventKind = EventKind.ARMY_UPDATE,
                 payload: dict | None = None,
                 visible_to=None) -> None:
        self.turn = int(turn)
        self.x = float(x)
        self.y = float(y)
        self.kind = kind
        self.payload = payload if payload is not None else {}
        # Tagging: factions observing this entry at generation.
        # Ledger-internal only — never serialized to bots (seer lists leak
        # other factions' positions).
        self.visible_to: set = set(visible_to) if visible_to else set()


class Ledger:
    """Append-only event log with time-based visibility per faction.

    Events are visible to a faction when:
        t + dist(event, capital) / info_speed ≤ now

    During MOVE_CAPITAL flight: no events delivered.
    """

    events: deque[Event]
    eviction_ptr: int  # pointer into sorted events for O(1) amortised eviction

    def __init__(self, info_speed: float = 150.0, map_diagonal: float = 1414.0) -> None:
        self.info_speed = float(info_speed)
        self.map_diagonal = float(map_diagonal)
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
        """Append an entry (sorted by turn). Assigns the entry its seq."""
        event.seq = self._next_seq  # type: ignore[attr-defined]
        self._next_seq += 1
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
        # Flat per-faction anchor arrays + one batched kernel call. Tags
        # are bit-identical to the reference scan (same float64 ops).
        fac_xs: dict[int, list] = {}
        fac_ys: dict[int, list] = {}
        for t in world.towns:
            fac_xs.setdefault(t.faction, []).append(t.x)
            fac_ys.setdefault(t.faction, []).append(t.y)
        for a in world.armies:
            fac_xs.setdefault(a.faction, []).append(a.x)
            fac_ys.setdefault(a.faction, []).append(a.y)
        facs = sorted(fac_xs)
        nf = len(facs)
        f_start = np.empty(nf, dtype=np.int64)
        f_len = np.empty(nf, dtype=np.int64)
        ax_parts = []
        ay_parts = []
        full_mask = np.int64(0)
        for fi, f in enumerate(facs):
            xs = fac_xs[f]
            f_start[fi] = sum(f_len[:fi]) if fi else 0
            f_len[fi] = len(xs)
            ax_parts.append(np.asarray(xs, dtype=np.float64))
            ay_parts.append(np.asarray(fac_ys[f], dtype=np.float64))
            full_mask |= np.int64(1) << np.int64(f)
        anc_x = np.concatenate(ax_parts) if ax_parts else np.zeros(0, dtype=np.float64)
        anc_y = np.concatenate(ay_parts) if ay_parts else np.zeros(0, dtype=np.float64)
        facs_np = np.asarray(facs, dtype=np.int64)

        towns = world.towns
        armies = world.armies
        nt = len(towns)
        na = len(armies)
        ex = np.empty(nt + na, dtype=np.float64)
        ey = np.empty(nt + na, dtype=np.float64)
        skip = np.empty(nt + na, dtype=np.int64)
        for i, t in enumerate(towns):
            ex[i] = t.x
            ey[i] = t.y
            skip[i] = t.faction
        for j, a in enumerate(armies):
            ex[nt + j] = a.x
            ey[nt + j] = a.y
            skip[nt + j] = a.faction
        masks = np.empty(nt + na, dtype=np.int64)
        _observe_masks(ex, ey, skip, facs_np, f_start, f_len, anc_x, anc_y,
                       los2, full_mask, masks)

        def vis_of(idx: int, own: int) -> set:
            m = int(masks[idx])
            return {f for f in facs if (m >> f) & 1} | {own}

        live: set = set()
        positions: dict = {}
        for i, t in enumerate(towns):
            key = ("town", t.id)
            live.add(key)
            positions[key] = (t.x, t.y, t.faction)
            vis = vis_of(i, t.faction)
            # Command net: the ex-owner hears of a capture (flipped
            # faction since last generate) — losses are reported home.
            old = self._known_pos.get(key)
            if old is not None and old[2] != t.faction and old[2] in facs:
                vis = set(vis) | {old[2]}
            payload = {"id": t.id, "faction": t.faction,
                       "population": int(round(t.population)),
                       "is_capital": bool(t.is_capital)}
            ev = Event(turn=turn, x=t.x, y=t.y, kind=EventKind.TOWN_UPDATE,
                       payload=payload, visible_to=vis)
            self.log(ev)
            self._column(turn, t.x, t.y, key, vis, payload, ev.seq)
        for j, a in enumerate(armies):
            key = ("army", a.id)
            live.add(key)
            positions[key] = (a.x, a.y, a.faction)
            vis = vis_of(nt + j, a.faction)
            payload = {"id": a.id, "faction": a.faction, "alive": True,
                       "is_viceroy": bool(a.is_viceroy)}
            ev = Event(turn=turn, x=a.x, y=a.y, kind=EventKind.ARMY_UPDATE,
                       payload=payload, visible_to=vis)
            self.log(ev)
            self._column(turn, a.x, a.y, key, vis, payload, ev.seq)
        # Tombstones: vanished ids, tagged with observers of the site.
        gone = [key for key in self._known_ids if key not in live]
        if gone:
            gx = np.empty(len(gone), dtype=np.float64)
            gy = np.empty(len(gone), dtype=np.float64)
            for gi, key in enumerate(gone):
                x, y, fac = self._known_pos.get(key, (0.0, 0.0, -1))
                gx[gi] = x
                gy[gi] = y
            gskip = np.full(len(gone), -1, dtype=np.int64)
            gmasks = np.empty(len(gone), dtype=np.int64)
            _observe_masks(gx, gy, gskip, facs_np, f_start, f_len, anc_x,
                           anc_y, los2, full_mask, gmasks)
            for gi, key in enumerate(gone):
                m = int(gmasks[gi])
                kind, eid = key
                x, y, fac = self._known_pos.get(key, (0.0, 0.0, -1))
                vis = {f for f in facs if (m >> f) & 1}
                # Command net: owners always hear of own losses (death
                # news is not sight-gated home — unwitnessed deaths
                # otherwise haunt mirrors forever as fresh ghosts).
                if fac in facs:
                    vis.add(fac)
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
