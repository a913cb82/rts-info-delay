"""Stub bot — does nothing. Useful for testing runner infrastructure."""

from __future__ import annotations

from engine.config import GameConfig
from .common import BotState, bot_main


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    return []


if __name__ == "__main__":
    bot_main(decide_orders)
