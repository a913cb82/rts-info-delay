"""Generate full.json — kernel + population grid, 3 tunables.

Tunables:
  KERNEL_RADIUS   — how far from faction centres the density extends (km)
  KERNEL_DROP     — drop-off shape: "linear", "quadratic", "gaussian"
  POP_POWER       — pop^POWER applied to density for settlement count
  N_TOWNS         — total settlements to place
"""

import json, math, random, sys
import numpy as np
sys.path.insert(0, "src")
from engine.config import GameConfig

MAP_SIZE = 1000
GRID_RES = 50
N_FACTIONS = 5
RANDOM_SEED = 42

# ── The 3 tunables ────────────────────────────────────────────────────
KERNEL_RADIUS = 320       # km — faction influence radius
KERNEL_DROP   = "gaussian" # "linear", "quadratic", "gaussian"
POP_POWER     = 0.6       # density^POWER determines placement weight
N_TOWNS       = 420

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

CELL = MAP_SIZE / GRID_RES
_cx = (np.arange(GRID_RES) + 0.5) * CELL
_cy = (np.arange(GRID_RES) + 0.5) * CELL
_ccx, _ccy = np.meshgrid(_cx, _cy, indexing="ij")


def faction_centers():
    R = 280
    return [(500 + R * math.cos(math.radians(90 + i * 72)),
             500 + R * math.sin(math.radians(90 + i * 72)))
            for i in range(N_FACTIONS)]


def nearest_fi(x, y, centers):
    return min(range(N_FACTIONS),
               key=lambda i: math.hypot(x - centers[i][0], y - centers[i][1]))


# ── Kernel ────────────────────────────────────────────────────────────

def kernel_weight(dist, radius, drop):
    """Normalised distance [0,1] → weight [0,1]."""
    t = np.clip(dist / radius, 0, 1)
    if drop == "linear":
        return 1 - t
    elif drop == "quadratic":
        return 1 - t * t
    elif drop == "gaussian":
        return np.exp(-0.5 * (dist / (radius * 0.5)) ** 2)
    return 1 - t


def build_density(centers):
    """Sum kernel from each faction centre.  Shape (GRID_RES, GRID_RES)."""
    grid = np.zeros((GRID_RES, GRID_RES))
    for cx, cy in centers:
        d = np.sqrt((_ccx - cx)**2 + (_ccy - cy)**2)
        grid += kernel_weight(d, KERNEL_RADIUS, KERNEL_DROP)
    # normalise to [0, 1]
    mx = grid.max()
    if mx > 0: grid /= mx
    return grid


def build_placement_weight(density, settlements):
    """Density^POWER minus spacing penalty from existing towns."""
    # population-weighted density for placement
    w = density ** POP_POWER

    if not settlements:
        return w
    sx = np.array([x for x, *_ in settlements])
    sy = np.array([y for _, y, *_ in settlements])
    dx = _ccx[:, :, None] - sx[None, None, :]
    dy = _ccy[:, :, None] - sy[None, None, :]
    closest = np.sqrt(dx*dx + dy*dy).min(axis=2)
    spacing = 55  # km — enforced minimum spacing
    mask = closest < spacing
    penalty = 1 - (closest[mask] / spacing) ** 2
    w[mask] *= (1 - penalty)
    return w


def choose_cell(weight):
    flat = weight.ravel()
    total = flat.sum()
    if total == 0:
        idx = random.randint(0, len(flat) - 1)
    else:
        idx = np.random.choice(len(flat), p=flat / total)
    return int(idx // GRID_RES), int(idx % GRID_RES)


# ── Pop from logspace ─────────────────────────────────────────────────

def random_pop():
    lp = random.uniform(math.log10(500), math.log10(50000))
    pop = int(10 ** lp)
    return max(500, round(pop / 100) * 100 if pop < 1000 else round(pop / 500) * 500)


# ── Generate ──────────────────────────────────────────────────────────

def generate_map():
    centers = faction_centers()
    density = build_density(centers)
    settlements = []

    # seed capitals
    for fi, (cx, cy) in enumerate(centers):
        settlements.append((cx, cy, 50000, fi))

    # place remaining towns
    while len(settlements) < N_TOWNS:
        w = build_placement_weight(density, settlements)
        gi, gj = choose_cell(w)
        wx = float(np.clip((gi + 0.5) * CELL + random.gauss(0, CELL * 0.3), 5, MAP_SIZE - 5))
        wy = float(np.clip((gj + 0.5) * CELL + random.gauss(0, CELL * 0.3), 5, MAP_SIZE - 5))
        fi = nearest_fi(wx, wy, centers)
        settlements.append((wx, wy, random_pop(), fi))
        if len(settlements) % 100 == 0:
            print(f"  {len(settlements)}")

    # rebalance faction pop
    settlements = rebalance(settlements, centers)
    return settlements, density


def rebalance(settlements, centers):
    for _ in range(500):
        pops = [sum(p for _, _, p, f in settlements if f == fi) for fi in range(N_FACTIONS)]
        target = sum(pops) / N_FACTIONS
        hi = max(range(N_FACTIONS), key=lambda i: pops[i])
        lo = min(range(N_FACTIONS), key=lambda i: pops[i])
        if pops[hi] - pops[lo] < target * 0.02:
            break
        # find best border settlement to move: closest to lo center, not capital
        best = None; best_d = float("inf")
        for i, (x, y, p, f) in enumerate(settlements):
            if f != hi or p >= 40000:
                continue
            d = math.hypot(x - centers[lo][0], y - centers[lo][1])
            if d < best_d:
                best_d = d; best = i
        if best is None:
            break
        x, y, p, _ = settlements[best]
        settlements[best] = (x, y, p, lo)
    return settlements


# ── CSV / simulate ────────────────────────────────────────────────────

def to_csv(settlements):
    lines = ["x,y,type,population"]
    for fi in range(N_FACTIONS):
        ft = sorted([(x, y, p, f) for x, y, p, f in settlements if f == fi],
                     key=lambda t: -t[2])
        for x, y, pop, f in ft:
            lines.append(f"{x:.1f},{y:.1f},{chr(65+f)},{pop}")
    return "\n".join(lines) + "\n"


def simulate(settlements):
    from engine.world import World
    from engine.step import step
    from engine.ledger import Ledger
    csv = to_csv(settlements)
    cfg = GameConfig(); cfg.map = csv; cfg.map_size = [MAP_SIZE, MAP_SIZE]
    w = World(); w.map_size = [MAP_SIZE, MAP_SIZE]; w.parse_map(csv)
    init = {(t.id, t.faction): t.population for t in w.towns}
    ledger = Ledger(cfg.info_speed, math.hypot(MAP_SIZE, MAP_SIZE))
    step(w, cfg, ledger, turn=1, orders={})
    return [(t.x, t.y, init.get((t.id, t.faction), t.population),
             t.faction, (t.population - init.get((t.id, t.faction), t.population))
             / max(1, init.get((t.id, t.faction), 1)) * 100)
            for t in w.towns]


# ── Render ────────────────────────────────────────────────────────────

def render_png(data, density, filename="maps/full_preview.png"):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return

    img = Image.new("RGB", (MAP_SIZE, MAP_SIZE), (200, 220, 200))
    draw = ImageDraw.Draw(img)

    # draw density as faint green overlay
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except Exception:
        font = ImageFont.load_default()

    # faction boundary lines
    for fi in range(N_FACTIONS):
        for fj in range(fi + 1, N_FACTIONS):
            centers = faction_centers()
            cx1, cy1 = centers[fi]; cx2, cy2 = centers[fj]
            mx, my = (cx1+cx2)/2, (cy1+cy2)/2
            a = math.atan2(cy2-cy1, cx2-cx1) + math.pi/2
            draw.line([(mx - 500*math.cos(a), my - 500*math.sin(a)),
                       (mx + 500*math.cos(a), my + 500*math.sin(a))],
                      fill=(170, 190, 170), width=1)

    colors = [(220,60,60),(60,120,220),(60,180,60),(220,160,40),(180,60,180)]
    for x, y, ini, fi, pct in data:
        r = 6 if ini >= 40000 else 4 if ini >= 5000 else 3 if ini >= 1000 else 2
        col = colors[fi % len(colors)]
        draw.ellipse([x-r, y-r, x+r, y+r], fill=col, outline=(0, 0, 0))
        if ini >= 3000:
            draw.text((x+r+2, y-6), f"{pct:+.1f}%", fill=(0,0,0), font=font)

    for fi, (cx, cy) in enumerate(faction_centers()):
        draw.text((cx-4, cy-4), str(fi), fill=(0,0,0), font=font)

    # Legend
    y0 = MAP_SIZE - 18
    for fi in range(N_FACTIONS):
        tp = sum(d[2] for d in data if d[3] == fi)
        x0 = 10 + fi * 200
        draw.rectangle([x0, y0, x0+10, y0+10], fill=colors[fi], outline=(0,0,0))
        draw.text((x0+14, y0-1), f"F{fi}: {tp:,} pop", fill=(0,0,0), font=font)

    img.save(filename)
    print(f"PNG  {filename}")


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    settlements, density = generate_map()

    print(f"\n{len(settlements)} towns  kernel={KERNEL_DROP} r={KERNEL_RADIUS}  pop_power={POP_POWER}")
    for fi in range(N_FACTIONS):
        tp = sum(p for _, _, p, f in settlements if f == fi)
        print(f"  F{fi}: {tp:7d} pop  {sum(1 for _, _, _, f in settlements if f == fi):3d} towns")

    data = simulate(settlements)
    print("\n  Size           n    avg%     range")
    for label, lo, hi in [("<1k", 0, 1000), ("1-5k", 1000, 5000),
                          ("5-20k", 5000, 20000), (">20k", 20000, 999999)]:
        g = [d for d in data if lo <= d[2] < hi]
        if g:
            avg = sum(d[4] for d in g)/len(g)
            print(f"  {label:14s} {len(g):3d}  {avg:+.2f}%  [{min(d[4] for d in g):+.1f}%, {max(d[4] for d in g):+.1f}%]")

    render_png(data, density)

    csv = to_csv(settlements)
    cfg = {
        "map": csv.rstrip("\n"), "map_size": [MAP_SIZE, MAP_SIZE], "max_turns": 500,
        "info_speed": 150.0, "army_speed": 50.0, "army_cost": 1000,
        "interact_radius": 10.0, "population_cap": 100000.0,
        "population_growth": 0.001, "build_efficiency": 0.5,
        "equilibrium_spacing": 0.1, "crowding_decay": 0.8, "crowding_asymmetry": 0.01,
    }
    with open("maps/full.json", "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"Wrote maps/full.json")
