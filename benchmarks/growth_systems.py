"""Growth-system interface: the suite scores *systems*, not the engine.

A system is anything that maps town populations forward in time.
Checks in growth_realism.py touch ONLY the methods below, so a
candidate mechanics (or parameter retune) plugs in by implementing
them — the suite file stays untouched::

    python benchmarks/growth_realism.py --system engine      # current
    python benchmarks/growth_realism.py --system candidate   # future

Towns are engine Town objects (positions + pops). The simplicity
guardrail keeps candidates in this shape: closed-form per-town +
pairwise, no per-town memory unless the bench blesses it. nets() is
the hot path and must stay vector-friendly (numpy/numba batch); the
perf check times exactly this method.
"""

from engine import economy as eco
from engine.config import GameConfig


class GrowthSystem:
    """Interface. Subclass and register in SYSTEMS."""

    name = "<unnamed>"

    def isolated(self, pop):
        """Net growth per turn of a lone town of `pop`."""
        raise NotImplementedError

    def nets(self, towns):
        """Per-town net growth per turn for the layout. THE hot path."""
        raise NotImplementedError

    def step(self, world, n=1):
        """Advance a World in place by n turns (trajectory checks)."""
        raise NotImplementedError

    @property
    def death_threshold(self):
        raise NotImplementedError

    @property
    def nparams(self):
        """Counted econ parameters (simplicity guardrail)."""
        raise NotImplementedError

    def describe(self):
        return self.name


class EngineGrowth(GrowthSystem):
    """Current engine: fitted base curve + directed interaction kernel."""

    name = "engine"

    def __init__(self, cfg=None):
        self.cfg = cfg or GameConfig()  # defaults match maps/*.json

    def isolated(self, pop):
        return eco.base_growth(float(pop), self.cfg)

    def nets(self, towns):
        # Canonical path is the batch kernel (per-town crowding_net is a
        # separate code path; the suite scores one path, not their agreement).
        return eco.crowding_nets_batch(towns, self.cfg)

    def step(self, world, n=1):
        for _ in range(n):
            eco.apply_growth(world, self.cfg)

    @property
    def death_threshold(self):
        return self.cfg.death_threshold

    @property
    def nparams(self):
        return 5  # growth, cap, eq_spacing, decay, asymmetry


SYSTEMS = {"engine": EngineGrowth()}

try:  # candidate plug-in (duck-typed; no import cycle)
    from candidate_growth import FITTED, FITTED_VARIANT, FittedGrowth  # noqa: E402
    SYSTEMS["fitted"] = FittedGrowth(FITTED, **FITTED_VARIANT)
except Exception as _e:  # pragma: no cover
    print(f"candidate_growth unavailable: {_e}")
