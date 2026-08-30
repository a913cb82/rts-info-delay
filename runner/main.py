"""Game runner — spawns bot subprocesses, manages stdin/stdout, runs game loop."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from engine.config import GameConfig
from engine.ledger import Ledger
from engine.record import write_config_line, write_turn_line
from engine.step import step
from engine.world import World


class BotProcess:
    """Manages a single bot subprocess (persistent across turns)."""

    proc: subprocess.Popen
    faction: int
    alive: bool

    def __init__(self, cmd: list[str], faction: int, config: GameConfig) -> None:
        """Spawn subprocess, send startup (config, faction, go)."""
        ...

    def send_turn(self, turn: int, events: list[dict]) -> list[str]:
        """Send turn header + events, read orders until 'go'.

        Returns list of order strings (without 'go').
        Returns [] on timeout or crash (marks bot dead).
        """
        ...

    def send_end(self, scores: dict[int, int]) -> None:
        """Send end message, then kill process."""
        ...

    def kill(self) -> None:
        """Kill subprocess."""
        ...


def run_game(
    config: GameConfig,
    bots: dict[int, list[str]],
    record_path: Path | None = None,
) -> dict[int, int]:
    """Run a full game.

    Args:
        config: Game configuration.
        bots: {faction_id: command} for each bot.
        record_path: If given, write JSONL game record here.

    Returns:
        {faction: score} at game end.
    """
    ...


def score(world: World, config: GameConfig) -> dict[int, int]:
    """Compute per-faction scores.

    score = total_town_population + army_cost × num_armies
    """
    ...


def parse_orders(lines: list[str]) -> list[str]:
    """Validate and return raw order lines from bot stdout."""
    ...


def apply_orders_to_world(
    world: World, faction: int, orders: list[str], config: GameConfig
) -> None:
    """Queue orders as messengers for delivery (MOVE_CAPITAL instant)."""
    ...
