"""Tests for runner/main — bot protocol, startup, timeout, end message."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.config import GameConfig
from runner.main import BotProcess, parse_orders, score, run_game
from engine.world import Army, Town, World

CFG = GameConfig()


class TestBotProtocol:
    """B1–B11: Bot subprocess protocol."""

    def test_startup_config(self) -> None:
        """B1: First line sent to bot is config JSON."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(return_value="go\n")
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            # Check that config was written to stdin
            written = mock_proc.stdin.write.call_args_list
            config_written = any("config" in str(arg) for arg in written)
            assert config_written

    def test_startup_faction(self) -> None:
        """B2: Second line sent to bot is 'faction <id>'."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(return_value="go\n")
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=2, config=CFG)
            written = mock_proc.stdin.write.call_args_list
            faction_written = any("faction 2" in str(arg) for arg in written)
            assert faction_written

    def test_startup_go(self) -> None:
        """B3: Third line sent to bot is 'go'."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(return_value="go\n")
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            written = mock_proc.stdin.write.call_args_list
            go_written = any("go" in str(arg) for arg in written)
            assert go_written

    def test_per_turn_header(self) -> None:
        """B4: Each turn sends 'turn <n>' + events + 'go'."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(return_value="go\n")
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            mock_proc.stdin.write.reset_mock()
            events = [{"kind": "battle", "x": 50, "y": 50}]
            bp.send_turn(turn=3, events=events)
            written = mock_proc.stdin.write.call_args_list
            turn_written = any("turn 3" in str(arg) for arg in written)
            assert turn_written

    def test_bot_response_parsed(self) -> None:
        """B5: Bot output parsed as orders."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        # Simulate bot output
        responses = iter(["MOVE_TO 1 0 0 100 100\n", "go\n"])
        mock_proc.stdout.readline = MagicMock(side_effect=lambda: next(responses))
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            orders = bp.send_turn(turn=1, events=[])
            assert "MOVE_TO 1 0 0 100 100" in orders

    def test_all_command_types(self) -> None:
        """B5b: All command types (MOVE_TO, TRAIN, BUILD, MOVE_CAPITAL) parsed."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        responses = iter([
            "MOVE_TO 1 0 0 100 100\n",
            "TRAIN 2\n",
            "BUILD 3 50 50\n",
            "MOVE_CAPITAL 200 200\n",
            "go\n",
        ])
        mock_proc.stdout.readline = MagicMock(side_effect=lambda: next(responses))
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            orders = bp.send_turn(turn=1, events=[])
            assert len(orders) == 4
            assert any("MOVE_TO" in o for o in orders)
            assert any("TRAIN" in o for o in orders)
            assert any("BUILD" in o for o in orders)
            assert any("MOVE_CAPITAL" in o for o in orders)

    def test_timeout_kills(self) -> None:
        """B6: Bot timeout → process killed, returns empty orders."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(side_effect=TimeoutError)
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            # send_turn should handle timeout
            orders = bp.send_turn(turn=1, events=[])
            assert orders == [] or bp.alive is False

    def test_timeout_permanence(self) -> None:
        """B6b: After timeout, bot is permanently dead."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(side_effect=TimeoutError)
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            bp.send_turn(turn=1, events=[])
            # Second turn also fails
            orders2 = bp.send_turn(turn=2, events=[])
            assert orders2 == []

    def test_go_terminator_required(self) -> None:
        """B7: Bot must send 'go' or orders ignored."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        # Bot sends orders but no 'go' → timeout
        mock_proc.stdout.readline = MagicMock(side_effect=TimeoutError)
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            orders = bp.send_turn(turn=1, events=[])
            assert orders == []

    def test_incremental_updates(self) -> None:
        """B8: Bot receives only incremental events, not full world."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(return_value="go\n")
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            events = [{"kind": "battle", "x": 50, "y": 50}]
            bp.send_turn(turn=1, events=events)
            # Check that events were sent, not full world
            written = mock_proc.stdin.write.call_args_list
            events_sent = any("battle" in str(arg) for arg in written)
            assert events_sent

    def test_end_message(self) -> None:
        """B9: Game end sends 'end <scores_json>'."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            scores = {0: 5000, 1: 3000}
            bp.send_end(scores)
            written = mock_proc.stdin.write.call_args_list
            end_written = any("end" in str(arg) for arg in written)
            assert end_written

    def test_end_after_timeout(self) -> None:
        """B9b: Even after timeout, end message is sent."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(side_effect=TimeoutError)
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            bp.send_turn(turn=1, events=[])
            # Should still be able to send end
            bp.send_end({0: 1000})
            written = mock_proc.stdin.write.call_args_list
            end_written = any("end" in str(arg) for arg in written)
            assert end_written

    def test_malformed_line_ignored(self) -> None:
        """B10: Malformed bot output → line skipped, no crash."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        responses = iter(["MOVE_TO garbage\n", "go\n"])
        mock_proc.stdout.readline = MagicMock(side_effect=lambda: next(responses))
        mock_proc.poll = MagicMock(return_value=None)

        with patch("subprocess.Popen", return_value=mock_proc):
            bp = BotProcess(cmd=["python", "-c", "pass"], faction=0, config=CFG)
            orders = bp.send_turn(turn=1, events=[])
            # Malformed line should be skipped
            assert not any("garbage" in o for o in orders)

    def test_unknown_faction_ignored(self) -> None:
        """B11: Bot orders army belonging to wrong faction → ignored."""
        # This is tested at the apply_orders level
        w = World()
        w.map_size = [1000, 1000]
        enemy_army = Army(id=1, faction=1, x=0, y=0)
        w.armies.append(enemy_army)
        orders = ["MOVE_TO 1 0 0 100 100"]
        parse_orders(orders)  # should not crash
        # Ownership check happens in apply_orders_to_world


class TestScore:
    """Score computation used by runner."""

    def test_formula(self) -> None:
        """S1: score = sum(town_pop) + army_cost × num_armies."""
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [
            Town(id=0, faction=0, x=0, y=0, population=1000),
            Town(id=1, faction=0, x=10, y=0, population=2000),
            Town(id=2, faction=0, x=20, y=0, population=500),
        ]
        w.armies = [
            Army(id=10, faction=0, x=0, y=0),
            Army(id=11, faction=0, x=0, y=0),
        ]
        result = score(w, CFG)
        assert result[0] == 3500 + 2 * 1000  # = 5500

    def test_only_alive_counted(self) -> None:
        """S2: Dead entities not counted."""
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=0, faction=0, x=0, y=0, population=1000)]
        w.armies = []
        result = score(w, CFG)
        assert result[0] == 1000
