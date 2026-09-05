"""Step 2 prerequisite — no-contact scout: probe before founding.

When no foe has ever been observed (blind universe), the first settler
becomes a scout: chained 250km legs in a faction-spread direction, never
founding en route; on final-leg arrival with still no contact it founds
(settle-as-scout fallback — the builds stage fires on the kept target).
Any foe observation unmarks instantly (normal raid/settle logic owns all
armies from the next turn). Legs ride _army_targets (fingerprint + wipe
cover them); only the _scout_id scalar is extra.
"""
import math

from engine.config import GameConfig
from bots.common import BotState

CFG = GameConfig()
SCOUT_MIN_TURN = 3
SCOUT_LEGS = 3
SCOUT_LEG_KM = 250.0


def _scout_bot():
    b = BotState()
    b.init(CFG, 0)
    return b


def _feed(b, turn, towns=(), armies=()):
    evs = [{"kind": "town_update", "id": t[0], "x": t[1], "y": t[2],
            "faction": t[3], "population": t[4], "is_capital": t[5]}
           for t in towns]
    evs += [{"kind": "army_update", "id": a[0], "x": a[1], "y": a[2],
             "faction": a[3], "alive": True, "is_viceroy": False}
            for a in armies]
    b.update(turn, evs)
    return b


class TestAssign:
    def test_void_assigns_and_dispatches_leg0(self) -> None:
        from bots.common import maybe_assign_scout, drive_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 200, 500, 0)])
        p = b.world.get_army(7)
        assert maybe_assign_scout(b, CFG, p) is True
        assert b._scout_id == 7
        orders = drive_scout(b, CFG, p)
        assert orders == ["MOVE_TO 7 200.0 500.0 250.0 500.0"]

    def test_second_scout_fans_out(self) -> None:
        # Two concurrent probes take different rays (fan-out, not one line).
        from bots.common import maybe_assign_scout, drive_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 200, 500, 0), (8, 200, 500, 0)])
        assert maybe_assign_scout(b, CFG, b.world.get_army(7)) is True
        assert maybe_assign_scout(b, CFG, b.world.get_army(8)) is True
        assert b._scout_id == 7 and b._scout_id2 == 8
        o1 = drive_scout(b, CFG, b.world.get_army(7))
        o2 = drive_scout(b, CFG, b.world.get_army(8))
        assert o1 == ["MOVE_TO 7 200.0 500.0 250.0 500.0"]  # gen-0 legacy ray
        assert o2 != o1  # gen-1 golden-angle ray
        assert maybe_assign_scout(b, CFG, b.world.get_army(7)) is False  # both busy

    def test_viable_contact_never_assigns(self) -> None:
        from bots.common import maybe_assign_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True),
                           (2, 320, 500, 1, 3000, False)],
              armies=[(7, 200, 500, 0)])
        assert maybe_assign_scout(b, CFG, b.world.get_army(7)) is False
        assert b._scout_id is None

    def test_rubble_only_assigns(self) -> None:
        # A visible decoy is not actionable contact: scout past it.
        from bots.common import maybe_assign_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True),
                           (2, 320, 500, 1, 800, False)],
              armies=[(7, 200, 500, 0)])
        assert maybe_assign_scout(b, CFG, b.world.get_army(7)) is True
        assert b._scout_id == 7

    def test_assigns_on_first_payload(self) -> None:
        # Turn-0 observations ride the first payload: turn 1 with no foe
        # in the mirror is already a void — no waiting.
        from bots.common import maybe_assign_scout
        b = _scout_bot()
        _feed(b, 1, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 200, 500, 0)])
        assert maybe_assign_scout(b, CFG, b.world.get_army(7)) is True


class TestDrive:
    def _scouted(self):
        from bots.common import maybe_assign_scout, drive_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 200, 500, 0)])
        p = b.world.get_army(7)
        assert maybe_assign_scout(b, CFG, p) is True
        assert drive_scout(b, CFG, p) == ["MOVE_TO 7 200.0 500.0 250.0 500.0"]
        return b

    def test_en_route_holds_silent(self) -> None:
        # Mid-hop truth lags reckoned arrival: phantom-early hop is
        # harmless (tip kept, army catches up and founds).
        from bots.common import drive_scout
        b = self._scouted()
        _feed(b, 4, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 220, 500, 0)])
        orders = drive_scout(b, CFG, b.world.get_army(7))
        assert orders and orders[0].startswith("MOVE_TO 7 ")

    def test_arrival_advances_hop(self) -> None:
        # Fresh intel dispatches the next hop promptly (send-all era).
        from bots.common import drive_scout
        b = self._scouted()
        _feed(b, 8, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 250, 500, 0)])
        orders = drive_scout(b, CFG, b.world.get_army(7))
        # fan-out spiral: leg 1 bends +0.35 rad off the faction ray.
        assert orders == ["MOVE_TO 7 250.0 500.0 297.0 517.1"]
        assert b._scout_id == 7 and b._scout_leg == 1

    def test_final_arrival_unmarks_keeps_target(self) -> None:
        # Builds stage founds on the kept target; the mark must go so
        # normal logic owns the army again.
        from bots.common import drive_scout
        b = self._scouted()
        b._scout_leg = 11
        b._army_targets[7] = (250.0, 500.0)
        _feed(b, 20, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 250, 500, 0)])
        assert drive_scout(b, CFG, b.world.get_army(7)) == []
        assert b._scout_id is None
        assert b.army_has_target(7) is True

    def test_rubble_bends_next_hop(self) -> None:
        # Non-viable contact must NOT hand back to normal logic (the old
        # code unmarked here and the ex-scout blundered into the decoy).
        # The next hop bends off the rubble while the scout stays out.
        from bots.common import drive_scout, maybe_assign_scout
        b = _scout_bot()
        _feed(b, 9, towns=[(1, 200, 500, 0, 3000, True),
                           (2, 400, 500, 1, 900, False)],
              armies=[(7, 360, 500, 0)])
        p = b.world.get_army(7)
        assert maybe_assign_scout(b, CFG, p) is True
        orders = drive_scout(b, CFG, p)
        assert b._scout_id == 7
        assert orders and orders[0].startswith("MOVE_TO 7")
        tx, ty = float(orders[0].split()[4]), float(orders[0].split()[5])
        # base hop (410, 500) runs through the decoy: bent ≥20km lateral
        assert abs(ty - 500.0) >= 20.0

    def test_viable_contact_unmarks_for_raid(self) -> None:
        from bots.common import drive_scout
        b = self._scouted()
        _feed(b, 9, towns=[(1, 200, 500, 0, 3000, True),
                           (2, 700, 500, 1, 4000, False)],
              armies=[(7, 450, 500, 0)])
        assert drive_scout(b, CFG, b.world.get_army(7)) is None
        assert b._scout_id is None

    def test_foe_army_unmarks_for_defense(self) -> None:
        from bots.common import drive_scout
        b = self._scouted()
        _feed(b, 9, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 450, 500, 0), (9, 500, 500, 1)])
        assert drive_scout(b, CFG, b.world.get_army(7)) is None
        assert b._scout_id is None

    def test_viable_contact_drops_stale_hop(self) -> None:
        # The kept hop target must not hijack the army into founding next
        # to the prize once raid logic owns it (trap lesson, second half).
        from bots.common import drive_scout
        b = self._scouted()
        _feed(b, 9, towns=[(1, 200, 500, 0, 3000, True),
                           (2, 700, 500, 1, 4000, False)],
              armies=[(7, 450, 500, 0)])
        assert b.army_has_target(7) is True  # hop note from _scouted
        assert drive_scout(b, CFG, b.world.get_army(7)) is None
        assert b.army_has_target(7) is False


class TestDeadNotes:
    """Stale MOVE_TO notes strand armies: the order died (messenger
    from-check on stale intel), the army sits somewhere else, and
    has_target blocks all fresh orders. Trail-stillness detects it."""

    def _stranded(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        _feed(b, 10, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 485, 535, 0)])
        b._army_targets[7] = (550.0, 500.0)  # raid note, messenger died
        # one more identical sighting, then delivery silence (static
        # snapshots don't resend): the trail goes stale elsewhere.
        _feed(b, 11, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 485, 535, 0)])
        for t in (12, 13):
            _feed(b, t, towns=[(1, 200, 500, 0, 3000, True)])
        return b

    def test_stranded_note_cleared(self) -> None:
        from bots.common import drop_dead_notes
        b = self._stranded()
        # trail newest is turn 11 (delay 2 + 2 grace): still flowing at 13
        drop_dead_notes(b)
        assert b._army_targets.get(7) == (550.0, 500.0)
        for t in (14, 15, 16):
            _feed(b, t, towns=[(1, 200, 500, 0, 3000, True)])
        drop_dead_notes(b)
        assert 7 not in b._army_targets

    def test_marching_note_kept(self) -> None:
        from bots.common import BotState, drop_dead_notes
        b = BotState()
        b.init(CFG, 0)
        _feed(b, 10, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 400, 535, 0)])
        b._army_targets[7] = (550.0, 500.0)
        for t, x in ((11, 450), (12, 500), (13, 535)):
            _feed(b, t, towns=[(1, 200, 500, 0, 3000, True)],
                  armies=[(7, x, 535, 0)])
        drop_dead_notes(b)
        assert b._army_targets.get(7) == (550.0, 500.0)

    def test_at_note_kept(self) -> None:
        from bots.common import BotState, drop_dead_notes
        b = BotState()
        b.init(CFG, 0)
        _feed(b, 10, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 550, 500, 0)])
        b._army_targets[7] = (550.0, 500.0)
        _feed(b, 11, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 550, 500, 0)])
        for t in (12, 13):
            _feed(b, t, towns=[(1, 200, 500, 0, 3000, True)])
        drop_dead_notes(b)
        assert b._army_targets.get(7) == (550.0, 500.0)


class TestReadyToDispatch:
    """Freshness gate (send-all era): order MOVE_TO when intel is fresh
    (lag within 3x expected + margin); hold only when ancient. (Was:
    quiescence — order only on quiet trails. Every-turn delivery keeps
    trails fresh, so quiescence froze armies on live notes.)"""

    def _bot(self):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        return b

    def test_quiescent_idle_dispatches(self) -> None:
        from bots.common import ready_to_dispatch
        b = self._bot()
        _feed(b, 1, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 200, 500, 0)])
        for t in (2, 3, 4, 5):
            _feed(b, t, towns=[(1, 200, 500, 0, 3000, True)])
        assert ready_to_dispatch(b, CFG, b.world.get_army(7)) is True

    def test_marching_fresh_dispatches(self) -> None:
        from bots.common import ready_to_dispatch
        b = self._bot()
        _feed(b, 10, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 400, 500, 0)])
        for t, x in ((11, 450), (12, 500), (13, 550)):
            _feed(b, t, towns=[(1, 200, 500, 0, 3000, True)],
                  armies=[(7, x, 500, 0)])
        assert ready_to_dispatch(b, CFG, b.world.get_army(7)) is True

    def test_ancient_holds(self) -> None:
        from bots.common import ready_to_dispatch
        b = self._bot()
        _feed(b, 10, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 400, 500, 0)])
        b._army_targets[7] = (450.0, 500.0)
        _feed(b, 11, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 450, 500, 0)])
        assert ready_to_dispatch(b, CFG, b.world.get_army(7)) is True
        for t in range(12, 30):
            _feed(b, t, towns=[(1, 200, 500, 0, 3000, True)])
        # trail age 19 > 3d+2 (d=2): mail broken, hold.
        assert ready_to_dispatch(b, CFG, b.world.get_army(7)) is False

    def test_order_move_emits_when_fresh(self) -> None:
        from bots.common import order_move
        b = self._bot()
        _feed(b, 10, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 400, 500, 0)])
        _feed(b, 11, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 450, 500, 0)])
        got = order_move(b, CFG, b.world.get_army(7), 600, 500)
        assert got == ["MOVE_TO 7 450.0 500.0 600.0 500.0"]
        assert b._army_targets.get(7) == (600, 500)


class TestProbeMemory:
    """Second probes must not re-fly settled rays (empty_3000: three
    +500 duplicate merges from deterministic repeat rays)."""

    def test_second_scout_bends_off_kept_note(self) -> None:
        from bots.common import maybe_assign_scout, drive_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 200, 500, 0)])
        p7 = b.world.get_army(7)
        assert maybe_assign_scout(b, CFG, p7) is True
        assert drive_scout(b, CFG, p7) == ["MOVE_TO 7 200.0 500.0 250.0 500.0"]
        # First probe finishes (fallback unmarks) but its settler note
        # persists — the production duplicate-merge setup.
        b._scout_id = None
        assert b._army_targets.get(7) == (250.0, 500.0)
        _feed(b, 4, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 200, 500, 0), (8, 200, 500, 0)])
        p8 = b.world.get_army(8)
        assert maybe_assign_scout(b, CFG, p8) is True
        orders = drive_scout(b, CFG, p8)
        assert orders and orders[0].startswith("MOVE_TO 8 ")
        assert orders != ["MOVE_TO 8 200.0 500.0 250.0 500.0"]

    def test_fallback_near_own_town_releases(self) -> None:
        from bots.common import drive_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True),
                           (2, 400, 500, 0, 1500, False)],
              armies=[(7, 390, 500, 0)])
        b._scout_id = 7
        b._scout_leg = 11
        b.note_move(7, 400.0, 500.0)  # kept hop target on own town
        assert drive_scout(b, CFG, b.world.get_army(7)) == []
        assert b._scout_id is None
        assert 7 not in b._army_targets  # builds must not found there

    def test_fallback_far_from_towns_keeps_note(self) -> None:
        from bots.common import drive_scout
        b = _scout_bot()
        _feed(b, 3, towns=[(1, 200, 500, 0, 3000, True)],
              armies=[(7, 590, 500, 0)])
        b._scout_id = 7
        b._scout_leg = 11
        b.note_move(7, 600.0, 500.0)
        assert drive_scout(b, CFG, b.world.get_army(7)) == []
        assert b._scout_id is None
        assert b._army_targets.get(7) == (600.0, 500.0)  # settle-as-scout
