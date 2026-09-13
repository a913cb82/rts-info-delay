"""Score computation — per faction total pop + total army size."""

from engine.config import GameConfig
from engine.world import World


def compute_score(world: World, faction: int | None = None, config: GameConfig | None = None) -> int:
    """Compute score for a faction or total.

    If faction is None, returns dict? But tests call compute_score(w, faction=0) expecting int.
    If faction given, return that faction's score.
    If no faction, return total? We'll handle both.
    """
    if config is None:
        from engine.config import GameConfig as _GC
        config = _GC()
    total = 0
    # If faction specified, compute only that faction
    if faction is not None:
        pop = sum(t.population for t in world.towns if t.faction == faction)
        asize = sum(a.size for a in world.armies if a.faction == faction)
        return int(pop + asize)
    else:
        # Return dict per faction? But compute_score called with faction param only, so this branch not needed
        # For runner.score compatibility, we also provide score(world, config) dict version
        # We'll compute per-faction dict
        scores: dict[int, int] = {}
        factions = set(t.faction for t in world.towns) | set(a.faction for a in world.armies)
        for f in factions:
            scores[f] = compute_score(world, faction=f, config=config)
        # Also handle empty faction
        return scores  # type: ignore

def score(world: World, config: GameConfig) -> dict[int, int]:
    """Compatibility wrapper for runner.main.score — returns per-faction dict."""
    # Use compute_score per faction
    factions = set(t.faction for t in world.towns) | set(a.faction for a in world.armies)
    # Ensure at least faction 0 present? Runner tests expect result[0] even if empty
    if not factions:
        return {0: 0}
    result: dict[int, int] = {}
    for f in factions:
        result[f] = compute_score(world, faction=f, config=config)
    # Also ensure faction 0 exists
    if 0 not in result:
        result[0] = 0
    return result
