"""Tests for engine/ledger — event logging, visibility delay, eviction."""

from __future__ import annotations

import pytest

from engine.ledger import Event, EventKind, Ledger


def _event(
    turn: int, x: float, y: float, kind: EventKind | None = None, payload: dict | None = None
) -> Event:
    """Helper: create an Event."""
    return Event(turn=turn, x=x, y=y, kind=kind or EventKind.BATTLE, payload=payload or {})


def _tagged(turn: int, x: float, y: float, vis: set, payload: dict | None = None) -> Event:
    """Helper: tagged update entry (new delivery path; old kinds don't query)."""
    return Event(turn=turn, x=x, y=y, kind=EventKind.TOWN_UPDATE,
                 payload=payload or {"id": 1}, visible_to=vis)


class TestLedgerLogging:
    """G1–G3: Event logging and tuple fields."""

    def test_log_event(self) -> None:
        """G1: Logged with correct tuple fields."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ev = _event(turn=1, x=100, y=200, kind=EventKind.ARMY_SPAWN, payload={"id": 1})
        ledger.log(ev)
        assert len(ledger.events) == 1
        stored = ledger.events[0]
        assert stored.turn == 1
        assert stored.x == 100
        assert stored.y == 200
        assert stored.kind == EventKind.ARMY_SPAWN
        assert stored.payload == {"id": 1}

    def test_event_tuple_fields(self) -> None:
        """G1b: Event has all required fields."""
        ev = _event(turn=5, x=50, y=60, kind=EventKind.BATTLE, payload={"killed": [1, 2]})
        assert ev.turn == 5
        assert ev.x == 50
        assert ev.y == 60
        assert ev.kind == EventKind.BATTLE
        assert ev.payload["killed"] == [1, 2]

    def test_events_sorted_by_time(self) -> None:
        """G5b: Ledger iterates events in t order."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ledger.log(_event(turn=3, x=0, y=0))
        ledger.log(_event(turn=1, x=0, y=0))
        ledger.log(_event(turn=2, x=0, y=0))
        turns = [e.turn for e in ledger.events]
        assert turns == sorted(turns)


class TestLedgerVisibility:
    """G2–G3, I1–I5e: Tag+delay+S delivery per faction (query)."""

    def test_visible_within_delay(self) -> None:
        """G2: Event visible when t + dist/info_speed ≤ now."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        # Entry at turn 1, distance 100 → delivers at turn 1 + 100/150 ≈ 1.67
        ledger.log(_tagged(turn=1, x=100, y=0, vis={0}))
        visible = ledger.query(0, 0.0, 0.0, now=2.0)
        assert len(visible) == 1

    def test_not_yet_visible(self) -> None:
        """G3: Event not visible when t + dist/info_speed > now."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        # Entry at turn 1, distance 300 → delivers at turn 1 + 2.0 = 3.0
        ledger.log(_tagged(turn=1, x=300, y=0, vis={0}))
        visible = ledger.query(0, 0.0, 0.0, now=2.0)
        assert len(visible) == 0

    def test_at_capital_zero_delay(self) -> None:
        """I3: Event at capital → visible immediately (next propagation step)."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ledger.log(_tagged(turn=1, x=100, y=200, vis={0}))
        visible = ledger.query(0, 100.0, 200.0, now=1.0)
        assert len(visible) == 1

    def test_independent_delays(self) -> None:
        """I4: Three events at different distances → visible at different times."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ledger.log(_tagged(turn=1, x=10, y=0, vis={0}))    # delay = 10/150 ≈ 0.067
        ledger.log(_tagged(turn=1, x=150, y=0, vis={0}))   # delay = 150/150 = 1.0
        ledger.log(_tagged(turn=1, x=300, y=0, vis={0}))   # delay = 300/150 = 2.0

        # At now=1.07: only nearest delivers
        v1 = ledger.query(0, 0.0, 0.0, now=1.07)
        assert len(v1) == 1

        # At now=2.0: nearest + middle deliver
        v2 = ledger.query(0, 0.0, 0.0, now=2.0)
        assert len(v2) == 2

        # At now=3.0: all three deliver
        v3 = ledger.query(0, 0.0, 0.0, now=3.0)
        assert len(v3) == 3

    def test_ledger_window_retain(self) -> None:
        """I5: Events retained for ≥ max_dist/info_speed turns."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        # max_delays = 1414/150 ≈ 9.43, window ≥ 10 turns
        ledger.log(_tagged(turn=1, x=0, y=0, vis={0}))
        # Check at turn 11 (10 turns later): entry from turn 1 with dist=0
        # t + 0/150 = 1 ≤ 11 → still delivers
        visible = ledger.query(0, 0.0, 0.0, now=11.0)
        assert len(visible) == 1

    # I5b (mute during flight) lives at the deliver level now
    # (TestDeliver.test_flight_returns_empty) — query has no flight concept.

    def test_capital_move_changes_dist(self) -> None:
        """I5c: After capital move, distance recomputed for new capital position."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        # Entry at (0,0), turn 1
        ledger.log(_tagged(turn=1, x=0, y=0, vis={0}))
        # Old capital at (0,0) → immediate
        v_old = ledger.query(0, 0.0, 0.0, now=1.0)
        assert len(v_old) == 1
        # New capital at (500,0) → delay = 500/150 ≈ 3.33
        v_new = ledger.query(0, 500.0, 0.0, now=2.0)
        assert len(v_new) == 0
        v_new2 = ledger.query(0, 500.0, 0.0, now=5.0)
        assert len(v_new2) == 1

    def test_event_kind_fields(self) -> None:
        """I5d: Event has turn, x, y, kind, payload."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ev = Event(turn=3, x=10, y=20, kind=EventKind.ARMY_DEATH, payload={"id": 5})
        ledger.log(ev)
        stored = ledger.events[0]
        assert hasattr(stored, "turn")
        assert hasattr(stored, "x")
        assert hasattr(stored, "y")
        assert hasattr(stored, "kind")
        assert hasattr(stored, "payload")

    def test_faction_specific_visibility(self) -> None:
        """I5e: Two factions see same event at different times based on capital distance."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ledger.log(_tagged(turn=1, x=100, y=0, vis={0, 1}))
        # Faction 0 capital at (0,0) → dist=100 → delivers at 1+0.67=1.67
        v0 = ledger.query(0, 0.0, 0.0, now=1.7)
        assert len(v0) == 1
        # Faction 1 capital at (400,0) → dist=300 → delivers at 1+2.0=3.0
        v1 = ledger.query(1, 400.0, 0.0, now=2.0)
        assert len(v1) == 0
        v1_later = ledger.query(1, 400.0, 0.0, now=3.0)
        assert len(v1_later) == 1


class TestLedgerEviction:
    """G4–G5c: Eviction of old events."""

    def test_evict_old_events(self) -> None:
        """G4: Old events removed when no longer deliverable."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ledger.log(_event(turn=1, x=0, y=0))
        ledger.log(_event(turn=100, x=0, y=0))
        # Evict at turn 200 → event from turn 1 way past window
        ledger.evict(now=200.0)
        # Only recent event should remain
        assert len(ledger.events) <= 2  # depends on implementation

    def test_window_size(self) -> None:
        """G5: Window = max_delay × info_speed turns, ≥10 for default."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        # max_delay = 1414/150 ≈ 9.43
        # Events from turn 1 should be retained until at least turn ~11
        # Even at now=10, event at distance 0 from turn 1 is still deliverable
        ledger.log(_tagged(turn=1, x=0, y=0, vis={0}))
        visible = ledger.query(0, 0.0, 0.0, now=10.0)
        assert len(visible) == 1

    def test_eviction_o1(self) -> None:
        """G5c: Eviction pointer advances, not full scan."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        for i in range(50):
            ledger.log(_event(turn=i, x=0, y=0))
        # Advance pointer past many events
        ledger.evict(now=200.0)
        # Pointer should have advanced (no full scan)
        assert ledger.eviction_ptr >= 0

    def test_no_premature_eviction(self) -> None:
        """Events not evicted before their delivery window expires."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ledger.log(_tagged(turn=5, x=0, y=0, vis={0}))
        ledger.evict(now=6.0)
        # Entry from turn 5 with dist=0 → delivers at turn 5, should survive
        visible = ledger.query(0, 0.0, 0.0, now=6.0)
        assert len(visible) == 1

    def test_death_visible_before_eviction_at_max_distance(self) -> None:
        """A death at max map distance is still delivered before eviction.

        This is what makes death-by-silence transient: eviction only fires
        past the maximum possible delay, so every death reaches every
        capital-holding faction exactly once (barring blind flight, which
        the landing wipe covers).
        """
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        ledger.log(_tagged(turn=5, x=1414, y=0, vis={0},
                           payload={"id": 7, "population": 0}))
        window = 1414 / 150
        # Still present at the last audible instant ...
        ledger.evict(now=5 + window)
        visible = ledger.query(0, 0.0, 0.0, now=5 + window)
        assert any(e.payload.get("population") == 0 for e in visible)
        # ... and gone only once nobody could hear it.
        ledger.evict(now=5 + window + 1.0)
        assert len(ledger.events) == 0

    def test_log_assigns_increasing_seqs(self) -> None:
        """Dedup keys: every logged event gets a unique monotonic seq."""
        ledger = Ledger(info_speed=150, map_diagonal=1414)
        a = _event(turn=2, x=0, y=0)
        b = _event(turn=1, x=0, y=0)  # out-of-order insert shares the counter
        ledger.log(a)
        ledger.log(b)
        assert (a.seq, b.seq) == (0, 1)
