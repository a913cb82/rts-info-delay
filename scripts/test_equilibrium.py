"""Test equilibrium of a map layout by running a few turns and checking pop changes."""

import math
import sys
sys.path.insert(0, "src")

from engine.config import GameConfig
from engine.world import World, Town
from engine.step import step
from engine.ledger import Ledger


def run_sim(csv: str, turns: int = 10) -> dict:
    """Run simulation and return pop tracking."""
    cfg = GameConfig()
    cfg.map = csv
    cfg.map_size = [1000, 1000]
    cfg.max_turns = turns

    world = World()
    world.map_size = [1000, 1000]
    world.parse_map(csv)

    # Track pops
    pops = {}  # (id, faction) -> [pop_per_turn]
    for t in world.towns:
        pops[(t.id, t.faction)] = [t.population]

    ledger = Ledger(cfg.info_speed, math.hypot(1000, 1000))
    for turn in range(1, turns + 1):
        step(world, cfg, ledger, turn=turn, orders={})
        for t in world.towns:
            key = (t.id, t.faction)
            if key not in pops:
                pops[key] = [0] * turn
            pops[key].append(t.population)

    return pops


def analyze(pops: dict, turns: int = 10):
    """Print analysis of pop changes."""
    print(f"{'ID':>4} {'Fac':>3} {'Start':>8} {'End':>8} {'Delta':>8} {'Rate':>8} Status")
    for (tid, fac), history in sorted(pops.items()):
        start = history[0] if history else 0
        end = history[-1] if history else 0
        delta = end - start
        rate = delta / max(1, turns - 1) if len(history) > 1 else 0
        if abs(delta) < 50:
            status = "EQUILIBRIUM"
        elif delta > 0:
            status = "GROWING"
        else:
            status = "SHRINKING"
        print(f"{tid:>4} {fac:>3} {start:>8.0f} {end:>8.0f} {delta:>+8.0f} {rate:>+8.1f} {status}")


# Generate map
R = 280
cx, cy = 500, 500
pentagon_pts = []
for i in range(5):
    theta = math.radians(90 + i * 72)
    pentagon_pts.append((cx + R * math.cos(theta), cy + R * math.sin(theta)))

# Layout template: (radius, angle_offset_deg, pop)
# Capital in center, towns spread out, villages filling gaps
# Increased radii to reduce crowding
template = [
    (0,   0,   50000),   # capital
    (70,  -20, 12000),   # medium town
    (75,  20,  10000),   # medium town
    (130, -25, 3000),    # small town
    (135, 15,  2500),    # small town
    (190, -15, 1500),    # village
    (195, 10,  1200),    # village
    (240, -5,  800),     # village
    (245, 20,  600),     # village
    (280, 0,   500),     # village (at edge)
]

csv_lines = ["x,y,type,population"]
for faction_idx, (fcx, fcy) in enumerate(pentagon_pts):
    center_angle = math.atan2(fcy - cy, fcx - cx)
    for r, angle_offset, pop in template:
        a = center_angle + math.radians(angle_offset)
        x = fcx + r * math.cos(a)
        y = fcy + r * math.sin(a)
        x = max(10, min(990, x))
        y = max(10, min(990, y))
        csv_lines.append(f"{x:.1f},{y:.1f},{chr(ord('A') + faction_idx)},{pop}")

csv = "\n".join(csv_lines) + "\n"
print(f"Map: {len(csv_lines)-1} towns")
print(f"Equilibrium spacing: {0.3}")
print(f"Crowding decay: {0.4}")
print()

pops = run_sim(csv, turns=20)
analyze(pops, turns=20)

# Find equilibrium distance for key pairs
print("\nEquilibrium distances (d_eq = 0.3 * sqrt(min(A, B))):")
for a_pop, b_pop in [(50000, 50000), (50000, 12000), (12000, 10000), (12000, 3000), (3000, 1500), (1500, 500)]:
    d_eq = 0.3 * math.sqrt(min(a_pop, b_pop))
    print(f"  {a_pop:>6} vs {b_pop:>6}: d_eq = {d_eq:.1f} km")
