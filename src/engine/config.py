"""Game configuration — all tunable parameters with PLAN.md defaults."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, asdict
from typing import Any


@dataclass
class GameConfig:
    # Map
    map_size: list[int] = field(default_factory=lambda: [1000, 1000])
    map: str = ""  # CSV entity list

    # Timing (byo-yomi per bot: main_time_ms reservoir, then one period of
    # turn_time_ms cap with +time_increment_ms per turn)
    max_turns: int = 500
    turn_time_ms: int = 1000
    time_increment_ms: float = 10.0
    main_time_ms: float = 1000.0

    # Units
    info_speed: float = 150.0
    line_of_sight: float = 150.0
    army_speed: float = 50.0
    army_cost: int = 1000
    interact_radius: float = 10.0

    # Agrarian economy (2026-09-13). Annual rates; the engine converts
    # to per-turn with `turns_per_year`. Raw materials:
    #   production  Y_i = (1+boost_i) * min(rural_density*area_i, farm_workers_yield*P_i)
    #   births      B_i = birth_rate * P_i * S_i/(S_i + h*P_i), h = birth/death - 1
    #   deaths      D_i = death_rate * P_i
    #   trade       surplus=Y-P exports to deficits, caps enforced (conservative)
    #   migration   natural increase share + surplus-labour share move up the hierarchy
    #   market      boost = market_premium * mkt/(mkt+P_market), mkt from non-farm population
    turns_per_year: float = 52.0        # weeks per year (1 turn = 1 week)
    farm_radius_km: float = 5.0          # R: farm walking radius
    rural_density: float = 30.0          # people/km2 the land feeds (c.1600)
    cart_distance_km: float = 20.0       # carting doubles grain price
    farm_workers_yield: float = 1.3      # people fed per farm worker (near-field)
    farm_decay_at_radius: float = 0.0    # yield lost at the farm radius (0 = flat ring)
    farm_decay_shape: float = 2.0        # distance-decay exponent p
    birth_rate: float = 0.035            # crude birth rate, per person per year
    death_rate: float = 0.031            # crude death rate, per person per year
    market_premium: float = 0.25         # max farm-output premium from market access
    market_scaling: float = 1.0          # gamma: urban service scaling exponent
    migration_share: float = 0.5         # theta: share of natural increase that emigrates
    surplus_mobility: float = 0.05       # nu: share of surplus labour that emigrates per year
    migration_scale_km: float = 50.0     # migration distance scale
    town_min_population: float = 10.0    # minimum settlement size (die at or below)
    build_efficiency: float = 0.9        # BUILD/MOVE_CAPITAL yield: army_cost x this = 900 pop
    capture_loss: float = 0.5            # population fraction lost when a town is captured

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GameConfig:
        """Create config from bot-protocol JSON object, ignoring unknown keys."""
        cfg = cls()
        valid = {f.name for f in fields(cls)}
        for k, v in d.items():
            if k in valid:
                setattr(cfg, k, v)
        return cfg

    def to_dict(self) -> dict[str, Any]:
        """Serialise for bot protocol and game record."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @property
    def death_threshold(self) -> float:
        """Legacy policy floor (army_cost x build_efficiency, 900).

        Kept for the bots' survive-floor heuristics; the ENGINE's death
        rule is `town_min_population` (10)."""
        return self.army_cost * self.build_efficiency
