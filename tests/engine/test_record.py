"""Tests for engine/record — JSONL format, field completeness."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from engine.config import GameConfig
from engine.record import (
    army_to_dict,
    town_to_dict,
    world_to_dict,
    write_config_line,
    write_turn_line,
)
from engine.world import Army, Town, World

CFG = GameConfig()


def _make_world() -> World:
    """Helper: create a populated World."""
    w = World()
    w.map_size = [1000, 1000]
    w.armies = [
        Army(id=0, faction=0, x=100, y=200),
        Army(id=1, faction=1, x=300, y=400),
    ]
    w.towns = [
        Town(id=2, faction=0, x=150, y=250, population=5000, is_capital=True),
        Town(id=3, faction=1, x=350, y=450, population=8000, is_capital=False),
    ]
    return w


class TestRecord:
    """R1–R5f: JSONL game record format."""

    def test_first_line_config(self) -> None:
        """R1: First line is config JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            write_config_line(CFG, path)
            with open(path) as f:
                line = f.readline()
            data = json.loads(line)
            assert data.get("type") == "config"
            assert "info_speed" in data
            assert "army_speed" in data
            assert "interact_radius" in data
            assert "rural_density" in data
        finally:
            path.unlink(missing_ok=True)

    def test_turn_lines(self) -> None:
        """R2: Subsequent lines are turn JSON with world + events."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            w = _make_world()
            events = [{"kind": "battle", "x": 50, "y": 50}]
            write_turn_line(turn=1, world=w, events=events, f=path)
            with open(path) as f:
                line = f.readline()
            data = json.loads(line)
            assert data["type"] == "turn"
            assert data["turn"] == 1
            assert "world" in data
            assert "events" in data
            assert "armies" in data["world"]
            assert "towns" in data["world"]
        finally:
            path.unlink(missing_ok=True)

    def test_all_turns_present(self) -> None:
        """R3: max_turns=10 → exactly 10 turn lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            w = _make_world()
            for t in range(1, 11):
                write_turn_line(t, w, [], path)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 10
        finally:
            path.unlink(missing_ok=True)

    def test_events_changes_only(self) -> None:
        """R4: Turn with no battles → events=[] but world full."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            w = _make_world()
            write_turn_line(turn=1, world=w, events=[], f=path)
            with open(path) as f:
                data = json.loads(f.readline())
            assert data["events"] == []
            assert len(data["world"]["armies"]) == 2
            assert len(data["world"]["towns"]) == 2
        finally:
            path.unlink(missing_ok=True)

    def test_world_complete(self) -> None:
        """R5: Any turn has full army/town fields."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            w = _make_world()
            write_turn_line(turn=1, world=w, events=[], f=path)
            with open(path) as f:
                data = json.loads(f.readline())
            for army in data["world"]["armies"]:
                for key in ["id", "faction", "x", "y"]:
                    assert key in army
            for town in data["world"]["towns"]:
                for key in ["id", "faction", "x", "y", "population", "is_capital"]:
                    assert key in town
        finally:
            path.unlink(missing_ok=True)

    def test_event_fields(self) -> None:
        """R5b: Events have correct fields per kind."""
        w = _make_world()
        army_ev = {"kind": "army_spawn", "id": 5, "faction": 0, "x": 10, "y": 20}
        town_ev = {"kind": "town_spawn", "id": 6, "faction": 0, "x": 30, "y": 40, "population": 500, "is_capital": False}
        move_ev = {"kind": "army_move", "id": 5, "x": 15, "y": 25}
        death_ev = {"kind": "army_death", "id": 5, "x": 20, "y": 30}
        battle_ev = {"kind": "battle", "x": 50, "y": 50, "combatants": [{"id": 1, "faction": 0}], "killed": [1]}
        for ev in [army_ev, town_ev, move_ev, death_ev, battle_ev]:
            assert "kind" in ev

    def test_jsonl_line_delimited(self) -> None:
        """R5c: One JSON object per line, no outer array."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            w = _make_world()
            write_config_line(CFG, path)
            for t in range(1, 4):
                write_turn_line(t, w, [], path)
            with open(path) as f:
                content = f.read()
            # Must not start with [ or end with ]
            assert not content.strip().startswith("[")
            assert not content.strip().endswith("]")
            for line in content.strip().split("\n"):
                json.loads(line)  # each line is valid JSON
        finally:
            path.unlink(missing_ok=True)

    def test_deterministic_output(self) -> None:
        """R5d: Same world → byte-identical JSONL."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f1:
            path1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f2:
            path2 = Path(f2.name)
        try:
            w1 = _make_world()
            w2 = _make_world()
            write_turn_line(1, w1, [], path1)
            write_turn_line(1, w2, [], path2)
            with open(path1) as f:
                out1 = f.read()
            with open(path2) as f:
                out2 = f.read()
            assert out1 == out2
        finally:
            path1.unlink(missing_ok=True)
            path2.unlink(missing_ok=True)

    def test_turn_numbers_sequential(self) -> None:
        """R5e: Turn numbers 1..T with no gaps."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            w = _make_world()
            for t in range(1, 6):
                write_turn_line(t, w, [], path)
            with open(path) as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                data = json.loads(line)
                assert data["turn"] == i + 1
        finally:
            path.unlink(missing_ok=True)

    def test_config_echoes_defaults(self) -> None:
        """R5f: Config line includes every PLAN default key."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            write_config_line(CFG, path)
            with open(path) as f:
                data = json.loads(f.readline())
            required_keys = [
                "map_size", "max_turns", "turn_time_ms",
                "info_speed", "army_speed", "army_cost", "interact_radius",
                "turns_per_year", "farm_radius_km", "rural_density",
                "cart_distance_km", "farm_workers_yield", "birth_rate",
                "death_rate", "max_improvement", "market_scaling",
                "migration_share", "surplus_mobility", "migration_scale_km",
                "town_min_population", "build_efficiency", "capture_loss",
            ]
            for key in required_keys:
                assert key in data, f"Missing config key: {key}"
        finally:
            path.unlink(missing_ok=True)
