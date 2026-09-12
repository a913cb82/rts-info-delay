"""pro search — distilled planning (M1 stepper; candidates/worlds later).

Standalone (imports stdlib only): no numpy/numba, no engine, no BotState,
so bot cold-start stays light. Config is a plain dict (caller converts).
"""
from .stepper import make_state, prune, step, score, rollout

__all__ = ["make_state", "prune", "step", "score", "rollout"]
