"""Game configuration — all tunable parameters with PLAN.md defaults."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, asdict
from typing import Any


@dataclass
class GameConfig:
    # Map
    map_size: list[int] = field(default_factory=lambda: [1000, 1000])
    map: str = ""  # CSV entity list

    # Timing
    max_turns: int = 500
    turn_time_ms: int = 1000

    # Units
    info_speed: float = 150.0
    army_speed: float = 50.0
    army_cost: int = 1000
    interact_radius: float = 10.0

    # Economy
    population_cap: float = 100_000.0
    population_growth: float = 0.001
    build_efficiency: float = 0.5

    # Crowding
    equilibrium_spacing: float = 0.4
    crowding_decay: float = 0.3
    crowding_asymmetry: float = 0.006

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
        """Town dies below this population (army_cost × build_efficiency)."""
        return self.army_cost * self.build_efficiency
