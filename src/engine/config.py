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

    # Economy — fitted realism growth model (2026-09-12; all 2 s.f.)
    #   g(P) = aP - (a/K)P^2 - cP^3
    #   W(i,j) = alpha*Pi*sig((Pj-Pi)/gate)*e^-(d/rho)^2 * win(d)
    #          + mu*Pi*Pj/(Pi+Pj)*(Pi-Pj)*e^-(d/rho) * win(d)
    population_growth: float = 8.2e-05   # a: fertility (linear term)
    land_capacity: float = 300_000.0     # K: saturation, b = a/K
    urban_sink: float = 1.0e-14          # c: cubic urban mortality
    access_alpha: float = 1.8e-05        # alpha: market access strength
    kernel_scale: float = 270.0          # rho: shared kernel decay (km)
    migration_mu: float = 2.7e-09        # mu: gravity migration strength
    service_gate: float = 30.0           # sigmoid width of "bigger serves smaller"
    town_min_population: float = 0.0     # death floor (0 = only at pop <= 0)
    build_efficiency: float = 0.5

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
        """Legacy policy floor (army_cost x build_efficiency, 500).

        Kept for the bots' survive-floor heuristics; the ENGINE's death
        rule is `town_min_population` (0 in the fitted model)."""
        return self.army_cost * self.build_efficiency
