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


# NOTE: TestPickets / TestPicketIntel removed when the tall turtle was ported
# (850b426 lineage): that turtle predates the forward-picket feature. Restore
# these tests together with the picket code if pickets are ported forward.
