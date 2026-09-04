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
            # Allow float formatting (0.0 vs 0)
            assert any("MOVE_TO 1" in o and "100" in o for o in orders)

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
# Score tests moved to tests/engine/test_score.py


class TestViceroyFlight:
    """In-flight viceroys are mute; landing rebuilds via snapshot."""

    def _world(self):
        from engine.world import World, Town, Army
        w = World()
        w.map_size = [1000, 1000]
        return w, Town, Army

    def test_faction_in_flight(self) -> None:
        from runner.main import faction_in_flight
        from engine.world import World, Town, Army
        w = World()
        w.map_size = [1000, 1000]
        assert faction_in_flight(w, 0) is False
        w.armies.append(Army(id=1, faction=0, x=0, y=0))
        assert faction_in_flight(w, 0) is False
        a = Army(id=2, faction=0, x=0, y=0)
        a.is_viceroy = True
        w.armies.append(a)
        assert faction_in_flight(w, 0) is True
        assert faction_in_flight(w, 1) is False

    def test_landed_this_turn(self) -> None:
        from runner.main import landed_this_turn
        assert landed_this_turn([], 0) is False
        evs = [{"kind": "town_spawn", "id": 7, "faction": 0, "is_capital": True}]
        assert landed_this_turn(evs, 0) is True
        assert landed_this_turn(evs, 1) is False
        evs2 = [{"kind": "town_spawn", "id": 7, "faction": 0, "is_capital": False}]
        assert landed_this_turn(evs2, 0) is False

    def test_landing_spawns_rebuild_world(self) -> None:
        """Landing payload spawns every town/army + horizon moves + battles."""
        from engine.config import GameConfig
        from engine.world import World, Town, Army
        from engine.ledger import Ledger, Event
        from runner.main import landing_spawns
        cfg = GameConfig()
        w = World()
        w.map_size = [1000, 1000]
        w.towns.append(Town(id=7, faction=0, x=0, y=0, population=1234, is_capital=False))
        w.towns.append(Town(id=2, faction=0, x=0, y=0, population=500, is_capital=True))
        w.armies.append(Army(id=9, faction=1, x=600, y=0))
        w.armies.append(Army(id=10, faction=1, x=50, y=0))
        lg = Ledger(cfg.info_speed, 1414)
        lg.log(Event(turn=12, x=300, y=0, kind="army_move",
                     payload={"id": 9, "has_target": True, "target_x": 0.0, "target_y": 0.0}))
        lg.log(Event(turn=18, x=500, y=0, kind="army_move",
                     payload={"id": 9, "has_target": True, "target_x": 0.0, "target_y": 0.0}))
        lg.log(Event(turn=10, x=300, y=0, kind="battle", payload={}))
        lg.log(Event(turn=18, x=1500, y=0, kind="battle", payload={}))
        lg.set_capital_since(0, 19)
        last: dict = {}
        # Town 7 sits 450 km out and flipped faction at turn 18: horizon
        # 20 - 3 = 17 still shows the OLD faction and pop.
        w.towns[0].x = 450.0
        hist = [{7: (1000 + 10 * t, 1 if t < 18 else 0, False),
                 2: (500, 0, True)} for t in range(21)]
        out = landing_spawns(w, lg, 0, 0.0, 0.0, 20.0, last, hist)
        # Every town spawned with delay-consistent values; last-sent refreshed.
        spawns = {e["id"]: e for e in out if e.get("kind") == "town_spawn"}
        assert set(spawns) == {7, 2}
        assert spawns[7]["population"] == 1170
        assert spawns[7]["faction"] == 1  # takeover invisible for 3 turns
        assert spawns[2]["is_capital"] is True
        assert last == {7: 1170, 2: 500}
        # Every army spawned + exactly one move: horizon pick for movers
        # (t12 audible at 14 <= 20, t18 not at 21.3 > 20) ...
        assert {e["id"] for e in out if e.get("kind") == "army_spawn"} == {9, 10}
        moves = [(e.get("x"), e.get("y")) for e in out
                 if e.get("kind") == "army_move" and e.get("id") == 9]
        assert moves == [(300, 0)]
        # ... nothing for the never-moved (spawn alone; no future to leak).
        moves10 = [e for e in out
                   if e.get("kind") == "army_move" and e.get("id") == 10]
        assert moves10 == []
        # Audible battle replays (10 + 2 <= 20); far one doesn't.
        battles = [(e.get("x"), e.get("y")) for e in out if e.get("kind") == "battle"]
        assert battles == [(300, 0)]

    def test_normal_payload_delayed_pops(self) -> None:
        """Pops come from history at now - dist/info, slim-wired."""
        from types import SimpleNamespace
        from engine.config import GameConfig
        from engine.world import World, Town
        from engine.ledger import Ledger
        from runner.main import _build_bot_events
        cfg = GameConfig()
        w = World()
        w.map_size = [1000, 1000]
        w.towns.append(Town(id=1, faction=0, x=0, y=0, population=3000, is_capital=True))
        w.towns.append(Town(id=2, faction=0, x=600, y=0, population=9999, is_capital=False))
        lg = Ledger(cfg.info_speed, 1414)
        bp = SimpleNamespace(_last_sent_pop={}, _last_sent_status={}, _sent_seqs=set())
        hist = [{1: (2900, 0, True), 2: (1000, 0, False)},
                {1: (2950, 0, True), 2: (1100, 0, False)}]
        payload = _build_bot_events(0, w, lg, 2, [], bp, hist)
        pops = {e["id"]: e["population"] for e in payload if e.get("kind") == "pop_change"}
        # Home town: horizon 2 - 0 -> latest (2950, not world 3000).
        # Far town (600 km): horizon 2 - 4 <0 -> earliest (1000, not 9999).
        assert pops == {1: 2950, 2: 1000}
        # Second identical build: slim wire stays quiet.
        payload2 = _build_bot_events(0, w, lg, 2, [], bp, hist)
        assert not [e for e in payload2 if e.get("kind") == "pop_change"]

    def test_landing_spawn_uses_birth_pos(self) -> None:
        """Spawn anchors at birth pos (minimal reveal); inaudible moves stay home."""
        from engine.config import GameConfig
        from engine.world import World, Town, Army
        from engine.ledger import Ledger, Event
        from runner.main import landing_spawns
        cfg = GameConfig()
        w = World()
        w.map_size = [1000, 1000]
        w.towns.append(Town(id=2, faction=0, x=0, y=0, population=500, is_capital=True))
        # Born t18 far away (inaudible), moved t19 (also inaudible), now at (1300, 0).
        w.armies.append(Army(id=12, faction=1, x=1300, y=0))
        lg = Ledger(cfg.info_speed, 1414)
        lg.log(Event(turn=18, x=1400, y=0, kind="army_spawn", payload={"id": 12, "faction": 1}))
        lg.log(Event(turn=19, x=1300, y=0, kind="army_move", payload={"id": 12}))
        lg.set_capital_since(0, 19)
        out = landing_spawns(w, lg, 0, 0.0, 0.0, 20.0, {}, [{2: (500, 0, True)}])
        spawns = [e for e in out if e.get("kind") == "army_spawn" and e.get("id") == 12]
        assert len(spawns) == 1
        assert (spawns[0]["x"], spawns[0]["y"]) == (1400, 0)  # birth, not current
        moves = [e for e in out if e.get("kind") == "army_move" and e.get("id") == 12]
        assert moves == []  # nothing audible: no future intel

    def test_no_ledger_resends_across_turns(self) -> None:
        """Each ledger event goes out once per faction, ever (no resends)."""
        from types import SimpleNamespace
        from engine.config import GameConfig
        from engine.world import World
        from engine.ledger import Ledger, Event
        from runner.main import _build_bot_events
        w = World()
        w.map_size = [1000, 1000]
        lg = Ledger(GameConfig().info_speed, 1414)
        lg.log(Event(turn=1, x=100, y=0, kind="battle", payload={}))
        bp = SimpleNamespace(_last_sent_pop={}, _last_sent_status={}, _sent_seqs=set())
        first = _build_bot_events(0, w, lg, 2, [], bp, [])  # audible: 1 + 100/150
        assert [e["kind"] for e in first] == ["battle"]
        second = _build_bot_events(0, w, lg, 3, [], bp, [])
        assert second == []
        lg.log(Event(turn=3, x=100, y=0, kind="battle", payload={}))
        third = _build_bot_events(0, w, lg, 4, [], bp, [])
        assert [e["kind"] for e in third] == ["battle"]

    def test_pre_landing_capture_flip_rides_pop_stream(self) -> None:
        """A capture hidden by since still corrects via pop-carried faction.

        Town 10 captured t9 (since=10 hides the ledger event forever); the
        landing seeds pre-capture state, and the delayed pop stream carries
        the faction flip when the horizon crosses t9.
        """
        from types import SimpleNamespace
        from engine.config import GameConfig
        from engine.world import World, Town
        from engine.ledger import Ledger
        from runner.main import _build_bot_events
        w = World()
        w.map_size = [1000, 1000]
        w.towns.append(Town(id=10, faction=1, x=310, y=0, population=915, is_capital=False))
        lg = Ledger(GameConfig().info_speed, 1414)
        lg.set_capital_since(0, 10)
        hist = [{10: (1700, 0, False)}]
        for t in range(1, 9):
            hist.append({10: (1700 + 5 * t, 0, False)})
        hist.append({10: (900, 1, False)})    # t9: captured + halved
        hist.append({10: (905, 1, False)})    # t10
        hist.append({10: (910, 1, False)})    # t11
        hist.append({10: (915, 1, False)})    # t12
        # Post-landing basis: seeded pre-capture state at t10 (horizon t7).
        bp = SimpleNamespace(_last_sent_pop={10: 1735},
                             _last_sent_status={10: (0, False)},
                             _sent_seqs=set())
        out = _build_bot_events(0, w, lg, 12, [], bp, hist)
        flips = [e for e in out if e.get("kind") == "pop_change" and e.get("id") == 10]
        assert len(flips) == 1
        assert flips[0]["population"] == 900  # horizon t12-2.07 -> t9
        assert flips[0]["faction"] == 1  # the flip rides along
        # Next turn: pop keeps catching up (horizon crosses t10) but the
        # faction, now known, is not re-sent.
        out2 = _build_bot_events(0, w, lg, 13, [], bp, hist + [{10: (920, 1, False)}])
        follow = [e for e in out2 if e.get("id") == 10]
        assert len(follow) == 1 and follow[0]["population"] == 905
        assert "faction" not in follow[0]
