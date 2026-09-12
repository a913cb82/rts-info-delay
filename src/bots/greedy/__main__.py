from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
"""python -m bots.greedy"""
from .protocol import *
from .brain import decide_orders

if __name__ == "__main__":
    bot_main(decide_orders)
