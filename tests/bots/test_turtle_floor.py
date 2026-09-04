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
