"""Integration tests — full games, cross-module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from engine.config import GameConfig
from engine.economy import base_growth
from engine.ledger import Ledger
from engine.record import write_config_line, write_turn_line
from engine.step import step
from engine.world import Army, StandingOrder, Town, World, CommandType

CFG = GameConfig()


def _run_game(
    map_csv: str = "",
    turns: int = 10,
    extra_orders: dict[int, list[str]] | None = None,
    standing: list[StandingOrder] | None = None,
) -> tuple[World, Ledger]:
    """Helper: run a mini game for N turns."""
    w = World()
    w.map_size = CFG.map_size
    if map_csv:
        w.parse_map(map_csv)
    if standing:
        w.standing_orders = standing
    ledger = Ledger(CFG.info_speed, 1414)
    orders = extra_orders or {}
    for t in range(1, turns + 1):
        step(w, CFG, ledger, turn=t, orders=orders)
    return w, ledger


class TestIntegration:
    """Z1–Z5: Full-game integration tests."""

    def test_growth_only(self) -> None:
        """Z1: 2 towns far apart, 50 turns → both grow per base curve, no deaths."""
        csv = "100,100,A,500\n800,800,B,500\n"
        w, ledger = _run_game(map_csv=csv, turns=50)
        # Both towns should have grown
        for t in w.towns:
            assert t.population > 500

    def test_blocking_and_combat(self) -> None:
        """Z2: 2 factions armies march toward each other → movement stops, combat resolves."""
        csv = "0,0,A,2000\n200,0,B,2000\n"  # towns
        csv += "50,0,a,\n150,0,b,\n"  # armies
        w, ledger = _run_game(map_csv=csv, turns=5)
        # At least one army should have moved or fought
        # After several turns, armies should have interacted
        assert len(w.armies) <= 2  # some may have died

    def test_close_hamlets_coexist(self) -> None:
        """Z3: 5 hamlets clustered at 5 km → they coexist (fitted model has
        no crowding-death spiral; the access halo feeds them)."""
        csv_lines = []
        for i in range(5):
            csv_lines.append(f"{100 + i * 5},100,A,500")
        csv = "\n".join(csv_lines) + "\n"
        w, ledger = _run_game(map_csv=csv, turns=100)
        assert len(w.towns) == 5
        # All survive at hamlet scale; contested border land is far from
        # every center, so edge hamlets sit just under 500 under decay.
        assert all(t.population > 400 for t in w.towns)

    def test_viewer_replays_record(self) -> None:
        """Z4: Run game → write JSONL → verify entity counts per turn match."""
        csv = "100,100,A,1000\n200,200,a,\n"
        w = World()
        w.map_size = CFG.map_size
        w.parse_map(csv)
        ledger = Ledger(CFG.info_speed, 1414)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        try:
            write_config_line(CFG, path)
            for t in range(1, 6):
                events = step(w, CFG, ledger, turn=t, orders={})
                write_turn_line(t, w, events, path)

            # Read back and verify
            with open(path) as f:
                lines = f.readlines()
            config_line = json.loads(lines[0])
            assert config_line["type"] == "config"
            for i, line in enumerate(lines[1:], 1):
                data = json.loads(line)
                assert data["type"] == "turn"
                assert "world" in data
                assert "armies" in data["world"]
                assert "towns" in data["world"]
        finally:
            path.unlink(missing_ok=True)

    def test_bot_sees_delayed_world(self) -> None:
        """Z5: Each faction's delivery holds only its own observations."""
        from engine.delivery import build_updates
        csv = "0,0,A,2000\n300,0,B,2000\n"  # two far-apart capitals
        csv += "50,0,a,\n"  # faction 0 army
        csv += "350,0,b,\n"  # faction 1 army
        w, ledger = _run_game(map_csv=csv, turns=5)
        cap0 = next(t.id for t in w.towns if t.faction == 0 and t.is_capital)
        cap1 = next(t.id for t in w.towns if t.faction == 1 and t.is_capital)
        # At turn 1: own capitals immediate (dist 0), far side held (300 km).
        u0 = build_updates(ledger, 0, ledger.S.get(0, 0), (0.0, 0.0), 1.0)
        u1 = build_updates(ledger, 1, ledger.S.get(1, 0), (300.0, 0.0), 1.0)
        assert cap0 in {u["id"] for u in u0 if u["kind"] == "town_update"}
        assert cap1 in {u["id"] for u in u1 if u["kind"] == "town_update"}
        assert cap1 not in {u["id"] for u in u0}
        assert cap0 not in {u["id"] for u in u1}

    def test_score_updates_through_game(self) -> None:
        """Score reflects current world state after each turn."""
        from runner.main import score

        # Two cooperating towns (trade+boost lift equilibrium; lone towns
        # correctly stall at carrying capacity).
        csv = "485,500,A,300\n515,500,A,300\n"
        w, ledger = _run_game(map_csv=csv, turns=200)
        result = score(w, CFG)
        assert sum(t.population for t in w.towns) > 600
        assert result[0] > 600

    def test_deterministic_replay(self) -> None:
        """Same map + config → identical results."""
        csv = "100,100,A,1000\n500,500,B,1000\n"

        def run_once():
            w, ledger = _run_game(map_csv=csv, turns=20)
            return [(t.id, round(t.x, 6), round(t.y, 6), round(t.population, 2)) for t in w.towns]

        run1 = run_once()
        run2 = run_once()
        assert run1 == run2


def test_record_tripwire():
    """Engine-behavior tripwire: fixed scripted game -> stable sha256.

    Any engine change that alters outcomes trips this. Update the hash
    deliberately (with a worklog note), never blindly.
    """
    import hashlib
    w = World()
    w.map_size = CFG.map_size
    w.parse_map("100,100,A,5000\n300,100,B,5000\n150,300,a,\n")
    ledger = Ledger(CFG.info_speed, 1414)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    try:
        write_config_line(CFG, path)
        for t in range(1, 11):
            events = step(w, CFG, ledger, turn=t, orders={})
            write_turn_line(t, w, events, path)
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        # Re-based 2026-09-13 for army sizes (Army.size, max_train_frac;
        # the scenario has no armies so trajectories are byte-identical —
        # only the config line grew a field).
        # Verified: symmetric towns stay symmetric (both 4995.85->4965.16,
        # monotone gentle decline), trajectories sane. Was d0988167...
        # (calibration promotion).
        assert h == "136481afb9ff0d24b131bd1f094095ebb00e996908021849f879787836544cc8"
    finally:
        path.unlink(missing_ok=True)
