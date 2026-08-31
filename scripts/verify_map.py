"""Settlement placement: two-grid approach, geometric + equilibrium verification."""

import math
import sys
sys.path.insert(0, "src")

from engine.config import GameConfig
from engine.world import World
from engine.step import step
from engine.ledger import Ledger

MAP_SIZE = 1000
N_FACTIONS = 5


def faction_centers():
    R = 280
    return [(500 + R * math.cos(math.radians(90 + i * 72)),
             500 + R * math.sin(math.radians(90 + i * 72))) for i in range(N_FACTIONS)]


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

    # Place capitals at population-weighted center of each faction
    for fi in range(N_FACTIONS):
        ft = [(x, y, p) for x, y, p, f in settlements if f == fi]
        tp = sum(p for _, _, p in ft)
        if tp > 0:
            px = sum(x * p for x, y, p in ft) / tp
            py = sum(y * p for _, y, p in ft) / tp
            # Replace nearest 8k town with capital, or add if none close
            best_idx = None
            best_dist = float('inf')
            for i, (x, y, p, f) in enumerate(settlements):
                if f == fi and p == 8000:
                    d = math.hypot(x - px, y - py)
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
            if best_idx is not None:
                x, y, _, _ = settlements[best_idx]
                settlements[best_idx] = (x, y, 50000, fi)
            else:
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


def run_sim(csv, turns=50):
    cfg = GameConfig()
    cfg.map = csv
    cfg.map_size = [MAP_SIZE, MAP_SIZE]
    world = World()
    world.map_size = [MAP_SIZE, MAP_SIZE]
    world.parse_map(csv)
    pops = {(t.id, t.faction): [t.population] for t in world.towns}
    ledger = Ledger(cfg.info_speed, math.hypot(MAP_SIZE, MAP_SIZE))
    for turn in range(1, turns + 1):
        step(world, cfg, ledger, turn=turn, orders={})
        for t in world.towns:
            k = (t.id, t.faction)
            if k not in pops:
                pops[k] = [0] * turn
            pops[k].append(t.population)
    return world, pops


def check_all(settlements):
    n = len(settlements)
    print(f"Total: {n} settlements")

    # 1. Gaps
    filled = set()
    for x, y, _, _ in settlements:
        filled.add((int(x // 50), int(y // 50)))
    total_cells = (MAP_SIZE // 50) ** 2
    pct = (total_cells - len(filled)) / total_cells * 100
    print(f"  Gaps: {pct:.1f}% — {'OK' if pct < 5 else 'FAIL'}")

    # 2. Density
    qcounts = {}
    for x, y, _, _ in settlements:
        q = (int(x // 100), int(y // 100))
        qcounts[q] = qcounts.get(q, 0) + 1
    vals = list(qcounts.values())
    avg = sum(vals) / len(vals)
    max_dev = max(abs(v - avg) for v in vals)
    print(f"  Density: avg={avg:.1f} dev={max_dev:.1f} — {'OK' if max_dev < avg * 0.8 else 'FAIL'}")

    # 3. Capital centering
    centers = faction_centers()
    all_ok = True
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
        if not ok:
            all_ok = False
        print(f"  Capital {fi}: dist={dist:.0f} — {'OK' if ok else 'FAIL'}")

    # 4. Villages surround larger
    surround_ok = True
    for fi in range(N_FACTIONS):
        ft = [(x, y, p) for x, y, p, f in settlements if f == fi]
        villages = [(x, y) for x, y, p in ft if p <= 1000]
        larger = [(x, y, p) for x, y, p in ft if p > 1000]
        fails = 0
        for lx, ly, lp in larger:
            quads = {0: False, 1: False, 2: False, 3: False}
            for vx, vy in villages:
                angle = math.atan2(vy - ly, vx - lx)
                quad = int((angle + math.pi) / (math.pi / 2)) % 4
                quads[quad] = True
            if sum(quads.values()) < 3:
                fails += 1
                surround_ok = False
        if fails:
            print(f"  Faction {fi}: {fails} larger towns lack 3+ village sides")
    if surround_ok:
        print(f"  Villages surround: OK")

    # 5. Village distribution
    vcounts = {}
    for x, y, p, _ in settlements:
        if p <= 1000:
            q = (int(x // 100), int(y // 100))
            vcounts[q] = vcounts.get(q, 0) + 1
    vtotal = (MAP_SIZE // 100) ** 2
    vpct = len(vcounts) / vtotal * 100
    print(f"  Villages: {len(vcounts)}/{vtotal} ({vpct:.1f}%) — {'OK' if vpct > 40 else 'FAIL'}")

    # 6. Equilibrium
    csv = settlements_to_csv(settlements)
    _, pops = run_sim(csv, turns=50)
    fast_shrink = sum(1 for h in pops.values() if (h[-1] - h[0]) < -100)
    n_pops = len(pops)
    print(f"  Equilibrium: {fast_shrink}/{n_pops} fast-shrinking — {'OK' if fast_shrink < n_pops * 0.05 else 'FAIL'}")


if __name__ == "__main__":
    settlements = generate_map()
    check_all(settlements)
    csv = settlements_to_csv(settlements)
    with open("viewer/public/pentagon_map.csv", "w") as f:
        f.write(csv)
    print(f"\nCSV written to viewer/public/pentagon_map.csv")
