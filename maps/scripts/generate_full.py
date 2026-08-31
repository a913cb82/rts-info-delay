"""Generate full.json — packed map with two-grid settlement placement.

Two-grid approach:
- Layer 1: large/medium towns on 80km grid (pop varies by distance from faction center)
- Layer 2: villages on 40km grid filling gaps between larger towns
- Capitals placed at population-weighted center of each faction's territory

Verification checks: gaps, density, capital centering, village surround, equilibrium.
"""

import json
import math
import sys

MAP_SIZE = 1000
N_FACTIONS = 5


def faction_centers():
    R = 280
    return [
        (500 + R * math.cos(math.radians(90 + i * 72)),
         500 + R * math.sin(math.radians(90 + i * 72)))
        for i in range(N_FACTIONS)
    ]


def nearest_fi(x, y, centers):
    return min(range(len(centers)), key=lambda i: math.hypot(x - centers[i][0], y - centers[i][1]))


def generate_map():
    """Two-grid: large towns on 80km grid, villages on 40km grid filling gaps."""
    centers = faction_centers()
    settlements = []

    # Layer 1: large/medium towns on 80km grid
    for x in range(25, MAP_SIZE, 80):
        for y in range(25, MAP_SIZE, 80):
            fi = nearest_fi(x, y, centers)
            cx, cy = centers[fi]
            dist = math.hypot(x - cx, y - cy)
            if dist < 120:
                pop = 8000
            elif dist < 200:
                pop = 3000
            elif dist < 300:
                pop = 1500
            elif dist < 400:
                pop = 800
            else:
                pop = 500
            settlements.append((x, y, pop, fi))

    # Place capitals at exact population-weighted center of each faction
    for fi in range(N_FACTIONS):
        ft = [(x, y, p) for x, y, p, f in settlements if f == fi]
        tp = sum(p for _, _, p in ft)
        if tp > 0:
            px = sum(x * p for x, y, p in ft) / tp
            py = sum(y * p for _, y, p in ft) / tp
            # Remove nearest non-capital and place capital at exact center
            best_idx = None
            best_dist = float("inf")
            for i, (x, y, p, f) in enumerate(settlements):
                if f == fi and p != 50000:
                    d = math.hypot(x - px, y - py)
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
            if best_idx is not None:
                settlements.pop(best_idx)
            settlements.append((px, py, 50000, fi))

    # Layer 2: villages on 40km grid, filling gaps
    large_positions = {(int(x // 40), int(y // 40)) for x, y, _, _ in settlements}
    for x in range(25, MAP_SIZE, 40):
        for y in range(25, MAP_SIZE, 40):
            gx, gy = int(x // 40), int(y // 40)
            if (gx, gy) not in large_positions:
                fi = nearest_fi(x, y, centers)
                settlements.append((x, y, 500, fi))

    return settlements


def settlements_to_csv(settlements):
    lines = ["x,y,type,population"]
    for x, y, pop, fi in settlements:
        lines.append(f"{x:.1f},{y:.1f},{chr(65 + fi)},{pop}")
    return "\n".join(lines) + "\n"


def check_all(settlements):
    """Run all verification checks."""
    n = len(settlements)
    print(f"Total: {n} settlements")
    all_pass = True

    # 1. Gaps
    filled = set()
    for x, y, _, _ in settlements:
        filled.add((int(x // 50), int(y // 50)))
    total_cells = (MAP_SIZE // 50) ** 2
    pct = (total_cells - len(filled)) / total_cells * 100
    ok = pct < 5
    if not ok: all_pass = False
    print(f"  Gaps: {pct:.1f}% — {'OK' if ok else 'FAIL'}")

    # 2. Density
    qcounts = {}
    for x, y, _, _ in settlements:
        q = (int(x // 100), int(y // 100))
        qcounts[q] = qcounts.get(q, 0) + 1
    vals = list(qcounts.values())
    avg = sum(vals) / len(vals)
    max_dev = max(abs(v - avg) for v in vals)
    ok = max_dev < avg * 0.8
    if not ok: all_pass = False
    print(f"  Density: avg={avg:.1f} dev={max_dev:.1f} — {'OK' if ok else 'FAIL'}")

    # 3. Capital centering
    centers = faction_centers()
    for fi in range(N_FACTIONS):
        ft = [(x, y, p) for x, y, p, f in settlements if f == fi]
        caps = [(x, y) for x, y, p, f in settlements if f == fi and p == 50000]
        if not caps:
            continue
        cx, cy = caps[0]
        tp = sum(p for _, _, p in ft)
        px = sum(x * p for x, y, p in ft) / tp
        py = sum(y * p for _, y, p in ft) / tp
        dist = math.hypot(cx - px, cy - py)
        ok = dist < 30
        if not ok: all_pass = False
        print(f"  Capital {fi}: dist={dist:.0f} — {'OK' if ok else 'FAIL'}")

    # 4. Villages surround larger (all factions' villages count)
    all_villages = [(x, y) for x, y, p, _ in settlements if p <= 1000]
    all_larger = [(x, y, p) for x, y, p, _ in settlements if p > 1000]
    fails = 0
    for lx, ly, lp in all_larger:
        quads = {0: False, 1: False, 2: False, 3: False}
        for vx, vy in all_villages:
            angle = math.atan2(vy - ly, vx - lx)
            quad = int((angle + math.pi) / (math.pi / 2)) % 4
            quads[quad] = True
        if sum(quads.values()) < 3:
            fails += 1
    surround_ok = fails == 0
    if not surround_ok:
        all_pass = False
        print(f"  Villages surround: {fails} larger towns lack 3+ sides — FAIL")
    else:
        print(f"  Villages surround: OK")

    # 5. Village distribution
    vcounts = {}
    for x, y, p, _ in settlements:
        if p <= 1000:
            q = (int(x // 100), int(y // 100))
            vcounts[q] = vcounts.get(q, 0) + 1
    vtotal = (MAP_SIZE // 100) ** 2
    vpct = len(vcounts) / vtotal * 100
    ok = vpct > 40
    if not ok: all_pass = False
    print(f"  Villages: {len(vcounts)}/{vtotal} ({vpct:.1f}%) — {'OK' if ok else 'FAIL'}")

    # 6. Equilibrium
    from engine.config import GameConfig as GC
    from engine.world import World
    from engine.step import step
    from engine.ledger import Ledger
    csv = settlements_to_csv(settlements)
    cfg = GC()
    cfg.map = csv
    cfg.map_size = [MAP_SIZE, MAP_SIZE]
    world = World()
    world.map_size = [MAP_SIZE, MAP_SIZE]
    world.parse_map(csv)
    pops = {(t.id, t.faction): [t.population] for t in world.towns}
    ledger = Ledger(cfg.info_speed, math.hypot(MAP_SIZE, MAP_SIZE))
    for turn in range(1, 51):
        step(world, cfg, ledger, turn=turn, orders={})
        for t in world.towns:
            k = (t.id, t.faction)
            if k not in pops:
                pops[k] = [0] * turn
            pops[k].append(t.population)
    fast_shrink = sum(1 for h in pops.values() if (h[-1] - h[0]) < -100)
    n_pops = len(pops)
    ok = fast_shrink < n_pops * 0.05
    if not ok: all_pass = False
    print(f"  Equilibrium: {fast_shrink}/{n_pops} fast-shrinking — {'OK' if ok else 'FAIL'}")

    return all_pass


if __name__ == "__main__":
    settlements = generate_map()
    passed = check_all(settlements)
    csv = settlements_to_csv(settlements)

    config = {
        "map": csv.rstrip("\n"),
        "map_size": [MAP_SIZE, MAP_SIZE],
        "max_turns": 500,
        "info_speed": 150.0,
        "army_speed": 50.0,
        "army_cost": 1000,
        "interact_radius": 10.0,
        "population_cap": 100000.0,
        "population_growth": 0.001,
        "build_efficiency": 0.5,
        "equilibrium_spacing": 0.1,
        "crowding_decay": 0.8,
        "crowding_asymmetry": 0.01,
    }

    with open("maps/full.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nWrote maps/full.json ({len(settlements)} settlements)")
    print(f"All checks: {'PASS' if passed else 'FAIL'}")
