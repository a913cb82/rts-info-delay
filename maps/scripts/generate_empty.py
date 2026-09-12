"""Generate empty.json — minimal map, 1 settlement per player at 500 pop."""

import json
import math

MAP_SIZE = 1000
R = 280
cx, cy = 500, 500

csv_lines = ["x,y,type,population"]
for i in range(5):
    theta = math.radians(90 + i * 72)
    x = cx + R * math.cos(theta)
    y = cy + R * math.sin(theta)
    csv_lines.append(f"{x:.1f},{y:.1f},{chr(65 + i)},500")

config = {
    "map": "\n".join(csv_lines),
    "map_size": [MAP_SIZE, MAP_SIZE],
    "max_turns": 500,
    "info_speed": 150.0,
    "army_speed": 50.0,
    "army_cost": 1000,
    "interact_radius": 10.0,
    "land_capacity": 300000.0,
    "population_growth": 8.2e-05,
    "build_efficiency": 0.9,
    "capture_loss": 0.5,
    "access_alpha": 1.8e-05,
    "kernel_scale": 270.0,
    "migration_mu": 2.7e-09,
}

with open("maps/empty.json", "w") as f:
    json.dump(config, f, indent=2)

print(f"Wrote maps/empty.json ({len(csv_lines)-1} settlements)")
