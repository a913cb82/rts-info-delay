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


def test_can_train_safely():
    t = Town(id=0, faction=0, x=100, y=100, population=5000, is_capital=True)
    assert can_train_safely(t) is True
    t.population = 1499
    assert can_train_safely(t) is False
    t.population = 5000
    assert can_train_safely(t, conservative=True) is True
    t.population = 40000  # in peak window
    assert can_train_safely(t, conservative=True) is False

