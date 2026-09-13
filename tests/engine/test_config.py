"""Tests for engine/config — defaults, overrides, field names."""

from __future__ import annotations

from dataclasses import fields

from engine.config import GameConfig


class TestConfig:
    """X1–X5: GameConfig defaults, overrides, field names."""

    def test_default_values(self) -> None:
        """X1: All default field values match PLAN."""
        cfg = GameConfig()
        assert cfg.map_size == [1000, 1000]
        assert cfg.max_turns == 500
        assert cfg.turn_time_ms == 1000
        assert cfg.info_speed == 150.0
        assert cfg.army_speed == 50.0
        assert cfg.army_cost == 1000
        assert cfg.max_train_frac == 0.1
        assert cfg.interact_radius == 10.0
        assert cfg.turns_per_year == 52.0
        assert cfg.farm_radius_km == 5.0
        assert cfg.rural_density == 30.0
        assert cfg.cart_distance_km == 20.0
        assert cfg.farm_workers_yield == 1.3
        assert cfg.farm_decay_at_radius == 0.9
        assert cfg.birth_rate == 0.024  # net surviving (gross 0.035 x ~0.7)
        assert cfg.death_rate == 0.031
        assert cfg.max_improvement == 0.75
        assert cfg.market_scaling == 1.3
        assert cfg.migration_share == 0.005
        assert cfg.surplus_mobility == 0.05
        assert cfg.migration_scale_km == 50.0
        assert cfg.melt_per_km == 0.005
        assert cfg.starvation_elasticity == 1.6
        assert cfg.town_min_population == 10.0
        assert cfg.build_efficiency == 0.9
        assert cfg.capture_loss == 0.5

    def test_config_overrides(self) -> None:
        """X2: from_dict overrides specified fields, keeps defaults."""
        cfg = GameConfig.from_dict({"army_speed": 30})
        assert cfg.army_speed == 30
        # All other defaults preserved
        assert cfg.info_speed == 150.0
        assert cfg.army_cost == 1000
        assert cfg.max_train_frac == 0.1
        assert cfg.interact_radius == 10.0
        assert cfg.turns_per_year == 52.0
        assert cfg.farm_radius_km == 5.0
        assert cfg.rural_density == 30.0
        assert cfg.cart_distance_km == 20.0
        assert cfg.farm_workers_yield == 1.3
        assert cfg.farm_decay_at_radius == 0.9
        assert cfg.birth_rate == 0.024  # net surviving (gross 0.035 x ~0.7)
        assert cfg.death_rate == 0.031
        assert cfg.max_improvement == 0.75
        assert cfg.market_scaling == 1.3
        assert cfg.migration_share == 0.005
        assert cfg.surplus_mobility == 0.05
        assert cfg.migration_scale_km == 50.0
        assert cfg.melt_per_km == 0.005
        assert cfg.starvation_elasticity == 1.6
        assert cfg.town_min_population == 10.0
        assert cfg.build_efficiency == 0.9
        assert cfg.capture_loss == 0.5
        assert cfg.map_size == [1000, 1000]
        assert cfg.max_turns == 500
        assert cfg.turn_time_ms == 1000

    def test_field_names_match_plan(self) -> None:
        """X3: Field names use PLAN names, not k/gamma/c."""
        names = {f.name for f in fields(GameConfig)}
        assert "farm_radius_km" in names
        assert "rural_density" in names
        assert "cart_distance_km" in names
        assert "farm_workers_yield" in names
        assert "birth_rate" in names
        assert "death_rate" in names
        assert "max_improvement" in names
        assert "migration_share" in names
        assert "surplus_mobility" in names
        assert "town_min_population" in names
        assert "melt_per_km" in names
        assert "starvation_elasticity" in names
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
