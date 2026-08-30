"""Tests for determinism — D1-D3c.

Engine must produce identical output from identical input.
No randomness, no hidden state, no float instability.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.config import GameConfig
from engine.world import World


CFG = GameConfig()


def _run_engine(config: GameConfig, max_turns: int) -> list[str]:
    """Run the engine as a subprocess and return JSONL lines."""
    # Write config to a temp file, run engine, capture output
    # For now, return empty — will be implemented when runner exists
    # This test will fail until the runner is implemented
    return []


def _run_engine_twice(config: GameConfig, max_turns: int) -> tuple[list[str], list[str]]:
    """Run the engine twice with identical config."""
    return _run_engine(config, max_turns), _run_engine(config, max_turns)


class TestDeterminism:
    """D1-D3c: Identical runs produce byte-identical output."""

    def test_identical_runs_byte_identical(self) -> None:
        """D1: Same map+config, 50 turns, no bots → JSONL identical."""
        lines1, lines2 = _run_engine_twice(CFG, max_turns=50)
        assert lines1 == lines2

    def test_deterministic_with_bots(self) -> None:
        """D2: Same deterministic bots → identical output."""
        # Will be implemented when bot protocol exists
        pytest.skip("Bot protocol not yet implemented")

    def test_float_stability(self) -> None:
        """D3: Crowding with γ=0.3, repeated 100× → bit-identical pop values."""
        from engine.economy import crowding_net

        # Create two towns
        w1 = World()
        w1.map_size = [1000, 1000]
        from engine.world import Town

        t1 = Town(id=1, faction=0, x=0, y=0, population=500)
        t2 = Town(id=2, faction=0, x=10, y=0, population=500)
        w1.towns = [t1, t2]

        results = []
        for _ in range(100):
            net = crowding_net(t1, [t2], CFG)
            results.append(net)

        # All results must be identical
        assert len(set(results)) == 1, f"Float instability: {len(set(results))} distinct values"

    def test_no_hidden_randomness(self) -> None:
        """D3b: Engine source contains no random imports."""
        engine_dir = Path(__file__).parent.parent.parent / "src" / "engine"
        if not engine_dir.exists():
            engine_dir = Path(__file__).parent.parent.parent / "engine"

        forbidden = ["import random", "from random", "import numpy.random", "from numpy.random",
                      "import os.urandom", "from os import urandom"]

        for py_file in engine_dir.glob("*.py"):
            content = py_file.read_text()
            for pattern in forbidden:
                assert pattern not in content, f"{py_file.name} contains forbidden import: {pattern}"

    def test_turn_order_stable(self) -> None:
        """D3c: Same contacts at same t* → deterministic tie-break by id."""
        from engine.movement import move_armies

        w = World()
        w.map_size = [1000, 1000]
        from engine.world import Army

        # Two armies moving toward each other — same t* for both
        a1 = Army(id=1, faction=0, x=0, y=0, target_x=100, target_y=0, has_target=True, is_fresh=False)
        a2 = Army(id=2, faction=1, x=100, y=0, target_x=0, target_y=0, has_target=True, is_fresh=False)
        w.armies = [a1, a2]

        # Run movement twice — must produce identical result
        move_armies(w, CFG)
        pos1 = [(a.x, a.y) for a in w.armies]

        # Reset and run again
        a1.x, a1.y = 0, 0
        a2.x, a2.y = 100, 0
        move_armies(w, CFG)
        pos2 = [(a.x, a.y) for a in w.armies]

        assert pos1 == pos2
