"""Step 1 — survive floor: no TRAIN may leave a town below the death
floor (500) unless last-stand-doomed (threat imputed to THIS town with
ETA <= 3 and the train affordable).

Map-level scenario infeasible (proven in worklog: score-neutral training
+ capture-halving + doomed-coverage erase the delta), so the benchmark
for this 3-line rule is decide-level: scripted states in, orders out.
"""
import pytest

from engine.config import GameConfig
from bots.common import BotState
from bots.turtle import decide_orders

CFG = GameConfig()
FLOOR = CFG.death_threshold  # 500


def _town_update(tid, x, y, faction=0, pop=2000, cap=False):
    return {"kind": "town_update", "id": tid, "x": x, "y": y,
            "faction": faction, "population": pop, "is_capital": cap}


def _army_update(aid, x, y, faction=0, alive=True, viceroy=False):
    return {"kind": "army_update", "id": aid, "x": x, "y": y,
            "faction": faction, "alive": alive, "is_viceroy": viceroy}


def _turtle_state(town_pop, foe_xy=None):
    """Single-town turtle (faction 0) at (300,500); optional foe army."""
    b = BotState()
    b.init(CFG, 0)
    evs = [_town_update(1, 300, 500, faction=0, pop=town_pop, cap=True)]
    if foe_xy is not None:
        evs.append(_army_update(9, foe_xy[0], foe_xy[1], faction=1))
    b.update(1, evs)
    return b


def _trains(state):
    return [o for o in decide_orders(state, CFG) if o.startswith("TRAIN")]


class TestSurviveFloor:
    def test_thin_threatened_town_holds(self) -> None:
        # foe 170km out: ETA 3.4 <= 4 fires the 1200 bar, but 1400-1000 =
        # 400 < 500 floor and the town is NOT overrun (ETA > 3) -> hold.
        assert _trains(_turtle_state(1400, (470, 500))) == []

    def test_last_stand_still_trains(self) -> None:
        # foe 100km out: ETA 2 <= 3 overruns this town -> convert to force.
        assert _trains(_turtle_state(1400, (400, 500))) == ["TRAIN 1"]

    def test_fat_town_unaffected(self) -> None:
        # 2600-1000 = 1600 >= floor -> trains exactly as before.
        assert _trains(_turtle_state(2600, (470, 500))) == ["TRAIN 1"]

    def test_no_threat_no_train(self) -> None:
        # control: unseen universe, thin town hoards.
        assert _trains(_turtle_state(1400, None)) == []


class TestLastStandMargin:
    def test_last_stand_trains_at_exact_affordability(self) -> None:
        # 1029 bark (turtle_defend t21): foe 100km out (ETA 2 <= 3), the
        # town falls anyway — convert pop to force. The +200 cushion must
        # not veto the exact situation last-stand exists for.
        assert _trains(_turtle_state(1029, (400, 500))) == ["TRAIN 1"]


class TestStagingThreat:
    def test_staging_town_recalls_settler(self) -> None:
        # Known foe town 100km out (no army seen yet): staging, i.e.
        # threat — a noted settler aborts and comes home.
        b = BotState()
        b.init(CFG, 0)
        evs = [_town_update(1, 300, 500, faction=0, pop=2000, cap=True),
               _town_update(2, 200, 500, faction=1, pop=900, cap=False),
               _army_update(7, 250, 500, faction=0)]
        b.update(1, evs)
        b.note_move(7, 150.0, 500.0)
        orders = decide_orders(b, CFG)
        assert any(o.startswith("MOVE_TO 7 ") and "300.0" in o
                   for o in orders), orders


class TestLastStandCounts:
    def test_last_stand_holds_when_defender_home(self) -> None:
        # 1029 bark with a defender standing: 1v1 mutual-saves at full
        # pop — training guts the town for nothing. HOLD.
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [_town_update(1, 300, 500, faction=0, pop=1029, cap=True),
                     _army_update(9, 400, 500, faction=1),
                     _army_update(7, 300, 500, faction=0)])
        assert _trains(b) == []

    def test_last_stand_fires_when_outnumbered(self) -> None:
        # Same, but two raiders vs one defender: the town falls without
        # the train — convert.
        b = BotState()
        b.init(CFG, 0)
        b.update(1, [_town_update(1, 300, 500, faction=0, pop=1029, cap=True),
                     _army_update(9, 400, 500, faction=1),
                     _army_update(10, 420, 500, faction=1),
                     _army_update(7, 300, 500, faction=0)])
        assert _trains(b) == ["TRAIN 1"]


class TestPickets:
    """Forward tripwire pickets (owed): single-town turtle posts one idle
    army 100km toward threat/ray; recalls on contact/threat/expiry; dead
    slot frees (never stuck)."""

    def _turtle(self, towns, armies=(), turn=1):
        from bots.common import BotState
        b = BotState()
        b.init(CFG, 0)
        evs = [{"kind": "town_update", "id": t[0], "x": t[1], "y": t[2],
                "faction": t[3], "population": t[4], "is_capital": t[5]}
               for t in towns]
        evs += [{"kind": "army_update", "id": a[0], "x": a[1], "y": a[2],
                 "faction": a[3], "alive": True, "is_viceroy": False}
                for a in armies]
        b.update(turn, evs)
        return b

    def test_designates_forward(self) -> None:
        from bots.turtle import decide_orders
        b = self._turtle([(1, 300, 500, 0, 3000, True)], [(7, 300, 500, 0)])
        orders = decide_orders(b, CFG)
        moves = [o for o in orders if o.startswith("MOVE_TO 7 ")]
        assert len(moves) == 1
        _, _, _, _, tx, ty = moves[0].split()
        import math
        assert 90 < math.hypot(float(tx) - 300, float(ty) - 500) < 115
        assert b._picket is not None and b._picket[0] == 7

    def test_recalls_on_contact(self) -> None:
        from bots.turtle import decide_orders
        b = self._turtle([(1, 300, 500, 0, 3000, True)])
        b._picket = (7, 1)
        b.update(2, [{"kind": "army_update", "id": 7, "x": 400, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False},
                     {"kind": "army_update", "id": 9, "x": 450, "y": 500,
                      "faction": 1, "alive": True, "is_viceroy": False}])
        orders = decide_orders(b, CFG)
        assert any(o.startswith("MOVE_TO 7 ") and "300.0" in o for o in orders)
        assert b._picket is None

    def test_expiry_recalls(self) -> None:
        from bots.turtle import decide_orders
        b = self._turtle([(1, 300, 500, 0, 3000, True)])
        b._picket = (7, 1)
        b.update(150, [{"kind": "army_update", "id": 7, "x": 400, "y": 500,
                        "faction": 0, "alive": True, "is_viceroy": False}])
        orders = decide_orders(b, CFG)
        assert any(o.startswith("MOVE_TO 7 ") for o in orders)
        assert b._picket is None

    def test_dead_slot_frees(self) -> None:
        from bots.turtle import decide_orders
        b = self._turtle([(1, 300, 500, 0, 3000, True)], [(7, 300, 500, 0)])
        b._picket = (7, 1)
        b.update(2, [])  # army 7 gone from intel (dead), no armies at all
        b.world.armies = []
        orders = decide_orders(b, CFG)
        assert b._picket is None


class TestPicketIntel:
    def test_no_designate_with_foe_town(self) -> None:
        from bots.turtle import decide_orders
        b = TestPickets()._turtle([(1, 300, 500, 0, 3000, True),
                                   (2, 600, 500, 1, 900, False)],
                                  [(7, 300, 500, 0)])
        decide_orders(b, CFG)
        assert b._picket is None  # threat located: guard stays home

    def test_staging_recalls(self) -> None:
        from bots.turtle import decide_orders
        b = TestPickets()._turtle([(1, 300, 500, 0, 3000, True)])
        b._picket = (7, 1)
        b.update(2, [{"kind": "town_update", "id": 2, "x": 200, "y": 500,
                      "faction": 1, "population": 900, "alive": True,
                      "is_capital": False},
                     {"kind": "army_update", "id": 7, "x": 400, "y": 500,
                      "faction": 0, "alive": True, "is_viceroy": False}])
        orders = decide_orders(b, CFG)
        assert any(o.startswith("MOVE_TO 7 ") for o in orders)
        assert b._picket is None
