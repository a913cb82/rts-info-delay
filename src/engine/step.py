"""Turn resolution — the main step function orchestrating all phases."""

from __future__ import annotations

from engine.config import GameConfig
from engine.ledger import Event, EventKind, Ledger
from engine.world import World


def step(
    world: World,
    config: GameConfig,
    ledger: Ledger,
    turn: int,
    orders: dict[int, list[str]],
) -> None:
    """Execute one full turn.

    Resolution order:
    1. Command   — parse and queue orders
    2. Propagation — advance messengers, deliver orders
    3. Movement  — armies move, path-blocking stops
    4. Combat    — weakness kills (simultaneous)
    5. Economy   — growth, TRAIN spawns, BUILD consumes
    6. Knowledge — log events, evict old ledger entries
    """
    ...


def _phase_command(
    world: World, config: GameConfig, orders: dict[int, list[str]], turn: int
) -> None:
    """Parse bot orders, create messengers (or execute MOVE_CAPITAL instantly)."""
    ...


def _phase_propagation(
    world: World, config: GameConfig, turn: int
) -> list[dict]:
    """Advance messengers, execute delivered commands, collect events."""
    ...


def _phase_movement(world: World, config: GameConfig) -> list[dict]:
    """Advance armies toward targets, resolve path-blocking contacts."""
    ...


def _phase_combat(world: World, config: GameConfig) -> list[dict]:
    """Resolve weakness-based simultaneous deaths."""
    ...


def _phase_economy(world: World, config: GameConfig) -> list[dict]:
    """Apply growth, execute standing TRAIN/BUILD, check town death."""
    ...


def _phase_knowledge(
    ledger: Ledger, events: list[dict], config: GameConfig, turn: int
) -> None:
    """Log events to ledger, evict old entries."""
    ...
