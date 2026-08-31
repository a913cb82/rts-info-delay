"""Tests for engine/config — defaults, overrides, field names."""

from __future__ import annotations

from dataclasses import fields

from engine.config import GameConfig


class TestConfig:
    """X1–X5: GameConfig defaults, overrides, field names."""

    def test_default_values(self) -> None:
        """X1: All 13 default field values match PLAN."""
        cfg = GameConfig()
        assert cfg.map_size == [1000, 1000]
        assert cfg.max_turns == 500
        assert cfg.turn_time_ms == 1000
        assert cfg.info_speed == 150.0
        assert cfg.army_speed == 50.0
        assert cfg.army_cost == 1000
        assert cfg.interact_radius == 10.0
        assert cfg.population_cap == 100_000.0
        assert cfg.population_growth == 0.001
        assert cfg.build_efficiency == 0.5
        assert cfg.equilibrium_spacing == 0.1
        assert cfg.crowding_decay == 0.8
        assert cfg.crowding_asymmetry == 0.01

    def test_config_overrides(self) -> None:
        """X2: from_dict overrides specified fields, keeps defaults."""
        cfg = GameConfig.from_dict({"army_speed": 30})
        assert cfg.army_speed == 30
        # All other defaults preserved
        assert cfg.info_speed == 150.0
        assert cfg.army_cost == 1000
        assert cfg.interact_radius == 10.0
        assert cfg.population_cap == 100_000.0
        assert cfg.population_growth == 0.001
        assert cfg.build_efficiency == 0.5
        assert cfg.equilibrium_spacing == 0.1
        assert cfg.crowding_decay == 0.8
        assert cfg.crowding_asymmetry == 0.01
        assert cfg.map_size == [1000, 1000]
        assert cfg.max_turns == 500
        assert cfg.turn_time_ms == 1000

    def test_field_names_match_plan(self) -> None:
        """X3: Field names use PLAN names, not k/gamma/c."""
        names = {f.name for f in fields(GameConfig)}
        assert "equilibrium_spacing" in names
        assert "crowding_decay" in names
        assert "crowding_asymmetry" in names
        assert "population_cap" in names
        # Old/regression names must NOT exist
        assert "k" not in names
        assert "gamma" not in names
        assert "c" not in names

    def test_no_num_factions(self) -> None:
        """X4: num_factions is not a config field (inferred from map)."""
        names = {f.name for f in fields(GameConfig)}
        assert "num_factions" not in names

    def test_map_field_is_csv(self) -> None:
        """X5: map field is a string (CSV entity list), not a dict."""
        cfg = GameConfig()
        assert isinstance(cfg.map, str)
        assert not isinstance(cfg.map, dict)
