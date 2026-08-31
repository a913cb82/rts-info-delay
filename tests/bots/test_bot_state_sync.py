"""BotState sync tests — verify update() correctly processes events."""

from __future__ import annotations

import math
import pytest
from engine.config import GameConfig
from engine.world import World, Town, Army
from engine.events import apply_events
from bots.common import BotState, can_train_safely


CFG = GameConfig()


def _bot_with_town(fid=0, x=100, y=100, pop=5000, cap=True, tid=0) -> BotState:
    bot = BotState()
    bot.init(CFG, fid)
    t = Town(id=tid, faction=fid, x=x, y=y, population=pop, is_capital=cap)
    bot.world.towns.append(t)
    return bot


def test_train_reduces_pop():
    bot = _bot_with_town(pop=5000)
    bot.update(1, [{"kind": "army_spawn", "id": 10, "faction": 0, "x": 100, "y": 100, "is_viceroy": False}])
    t = bot.world.get_town(0)
    assert t is not None and t.population == 4000
    assert bot.world.get_army(10) is not None


def test_train_multiple_times():
    bot = _bot_with_town(pop=5000)
    bot.update(1, [{"kind": "army_spawn", "id": 10, "faction": 0, "x": 100, "y": 100, "is_viceroy": False}])
    bot.update(2, [{"kind": "army_spawn", "id": 11, "faction": 0, "x": 100, "y": 100, "is_viceroy": False}])
    t = bot.world.get_town(0)
    assert t is not None and t.population == 3000
    assert len(bot.world.armies) == 2


def test_train_viceroy_no_pop_reduce():
    bot = _bot_with_town(pop=5000)
    bot.update(1, [{"kind": "army_spawn", "id": 10, "faction": 0, "x": 100, "y": 100, "is_viceroy": True}])
    t = bot.world.get_town(0)
    assert t is not None and t.population == 5000


def test_train_no_matching_town():
    bot = _bot_with_town(x=100, y=100)
    bot.update(1, [{"kind": "army_spawn", "id": 10, "faction": 0, "x": 500, "y": 500, "is_viceroy": False}])
    t = bot.world.get_town(0)
    assert t is not None and t.population == 5000


def test_town_spawn_adds_town():
    bot = _bot_with_town()
    bot.update(1, [{"kind": "town_spawn", "id": 1, "faction": 0, "x": 200, "y": 200, "population": 500, "is_capital": False}])
    assert bot.world.get_town(1) is not None


def test_town_death_removes():
    bot = _bot_with_town()
    bot.update(1, [{"kind": "town_death", "id": 0}])
    assert bot.world.get_town(0) is None


def test_army_death_removes():
    bot = _bot_with_town()
    bot.world.armies.append(Army(id=10, faction=0, x=100, y=100))
    bot.update(1, [{"kind": "army_death", "id": 10}])
    assert bot.world.get_army(10) is None


def test_army_move_updates_position():
    bot = _bot_with_town()
    bot.world.armies.append(Army(id=10, faction=0, x=100, y=100))
    bot.update(1, [{"kind": "army_move", "id": 10, "x": 200, "y": 200}])
    a = bot.world.get_army(10)
    assert a is not None and a.x == 200 and a.y == 200


def test_town_capture_changes_faction():
    bot = _bot_with_town(fid=1, tid=0)
    bot.update(1, [{"kind": "town_capture", "id": 0, "new_faction": 0, "population": 2500, "was_capital": True}])
    t = bot.world.get_town(0)
    assert t is not None and t.faction == 0 and t.population == 2500


def test_town_capture_becomes_capital():
    bot = _bot_with_town(fid=1, tid=0, cap=True)
    bot.update(1, [{"kind": "town_capture", "id": 0, "new_faction": 0, "population": 2500, "was_capital": True}])
    t = bot.world.get_town(0)
    assert t is not None and t.is_capital


def test_train_then_death():
    bot = _bot_with_town(pop=5000)
    bot.update(1, [{"kind": "army_spawn", "id": 10, "faction": 0, "x": 100, "y": 100, "is_viceroy": False}])
    assert bot.world.get_town(0).population == 4000
    bot.update(2, [{"kind": "town_death", "id": 0}])
    assert bot.world.get_town(0) is None


def test_capture_then_train():
    bot = _bot_with_town(fid=1, tid=0, pop=5000)
    bot.update(1, [{"kind": "town_capture", "id": 0, "new_faction": 0, "population": 5000}])
    assert bot.world.get_town(0).faction == 0
    bot.update(2, [{"kind": "army_spawn", "id": 10, "faction": 0, "x": 100, "y": 100, "is_viceroy": False}])
    assert bot.world.get_town(0).population == 4000


def test_multiple_events_same_turn():
    bot = _bot_with_town(pop=5000)
    bot.update(1, [
        {"kind": "army_spawn", "id": 10, "faction": 0, "x": 100, "y": 100, "is_viceroy": False},
        {"kind": "town_spawn", "id": 1, "faction": 0, "x": 200, "y": 200, "population": 500},
        {"kind": "army_death", "id": 10},
    ])
    assert bot.world.get_town(0).population == 4000
    assert bot.world.get_town(1) is not None
    assert bot.world.get_army(10) is None


def test_can_train_safely():
    t = Town(id=0, faction=0, x=100, y=100, population=5000, is_capital=True)
    assert can_train_safely(t) is True
    t.population = 1999
    assert can_train_safely(t) is False
    t.population = 5000
    assert can_train_safely(t, conservative=True) is True
    t.population = 40000  # in peak window
    assert can_train_safely(t, conservative=True) is False
