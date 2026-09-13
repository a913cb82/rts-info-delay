"""Per-phase timing: 1000 towns + 1000 armies, several dispositions.

Run:  PYTHONPATH=src python benchmarks/phase_bench.py
"""

import sys
import time

sys.path.insert(0, "src")

from engine.config import GameConfig
from engine.ledger import Ledger
from engine.world import Army, Town, World
from engine.step import (_phase_command, _phase_propagation, _phase_movement,
                         _phase_combat, _phase_economy, _phase_knowledge)

R = 68.0  # >1000 towns at 4km lattice (sliced to 1000)


def lattice(rmax, s):
    pts = []
    row = 0
    y = -rmax
    while y <= rmax + 1e-9:
        off = (s / 2.0) if (row % 2) else 0.0
        x = -rmax + off
        while x <= rmax + 1e-9:
            if x * x + y * y <= rmax * rmax:
                pts.append((x, y))
            x += s
        y += s * 0.8660254
        row += 1
    return pts


def base_world(ntowns=1000):
    assert len(lattice(R, 4.0)) >= ntowns
    w = World()
    w.map_size = [1000, 1000]
    pts = lattice(R, 4.0)[:ntowns]
    for k, (x, y) in enumerate(pts):
        w.towns.append(Town(id=k, faction=0, x=x, y=y, population=300.0))
    return w, pts


def add_armies(w, pts, size=500.0, faction=1):
    for j, (x, y) in enumerate(pts):
        w.armies.append(Army(id=5000 + j, faction=faction, x=x, y=y, size=size))


def scenario_idle_towns():
    """1000 armies camped on towns (max forage overlap)."""
    w, pts = base_world()
    add_armies(w, pts[:1000])
    for a in w.armies:
        a.sx, a.sy = a.x, a.y
    return w


def scenario_idle_wilderness():
    """1000 armies idle in empty land (towns tile the home disc)."""
    w, _ = base_world()
    for j in range(1000):
        x = 300 + (j % 40) * 5
        y = -200 + (j // 40) * 5
        w.armies.append(Army(id=5000 + j, faction=1, x=x, y=y, size=500.0))
    for a in w.armies:
        a.sx, a.sy = a.x, a.y
    return w


def scenario_march_towns():
    """1000 armies marching across town country."""
    w, pts = base_world()
    add_armies(w, [(-R + 5, -R + 10 + j * (2 * R - 20) / 999) for j in range(1000)])
    for a in w.armies:
        a.sx, a.sy = a.x, a.y
        a.target_x, a.target_y = R - 5, a.y
        a.has_target = True
    return w


def scenario_march_wilderness():
    """1000 armies marching through empty land (towns tile the home disc)."""
    w, _ = base_world()
    for j in range(1000):
        y = -200 + j * 400 / 999
        w.armies.append(Army(id=5000 + j, faction=1, x=300, y=y, size=500.0))
    for a in w.armies:
        a.sx, a.sy = a.x, a.y
        a.target_x, a.target_y = 700, a.y
        a.has_target = True
    return w


def scenario_combat():
    """500 intermingled pairs, two factions, within kill radius."""
    w, pts = base_world(1000)
    for j in range(500):
        x, y = pts[j]
        w.armies.append(Army(id=5000 + 2 * j, faction=1, x=x - 2, y=y, size=500.0))
        w.armies.append(Army(id=5000 + 2 * j + 1, faction=2, x=x + 2, y=y, size=500.0))
    for a in w.armies:
        a.sx, a.sy = a.x, a.y
    return w


def scenario_mixed():
    """Realistic mix: 400 camped, 300 marching towns, 200 wilderness idle, 100 fighting."""
    w, pts = base_world(1000)
    for j in range(400):
        x, y = pts[j]
        w.armies.append(Army(id=5000 + j, faction=1, x=x, y=y, size=500.0))
    for j in range(300):
        y = -R + 10 + j * (2 * R - 20) / 299
        w.armies.append(Army(id=5400 + j, faction=1, x=-R + 5, y=y, size=500.0))
        a = w.armies[-1]
        a.target_x, a.target_y = R - 5, y
        a.has_target = True
    for j in range(200):
        w.armies.append(Army(id=5700 + j, faction=1, x=500 + (j % 20) * 5, y=500 + (j // 20) * 5, size=500.0))
    for j in range(50):
        x, y = pts[400 + j]
        w.armies.append(Army(id=5900 + 2 * j, faction=1, x=x - 2, y=y, size=500.0))
        w.armies.append(Army(id=5900 + 2 * j + 1, faction=2, x=x + 2, y=y, size=500.0))
    for a in w.armies:
        a.sx, a.sy = a.x, a.y
    return w


def time_phases(w, cfg, turn=1):
    ledger = Ledger(cfg.info_speed, 1414)
    out = {}
    t0 = time.perf_counter()
    _phase_command(w, cfg, {}, turn)
    out["command"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    _phase_propagation(w, cfg, turn)
    out["prop"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    _phase_movement(w, cfg)
    out["move"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    _, pre = _phase_combat(w, cfg)
    out["combat"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    _phase_economy(w, cfg, ledger=ledger, turn=turn, pre_capture_factions=pre)
    out["economy"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    _phase_knowledge(ledger, cfg, turn, w)
    out["know"] = time.perf_counter() - t0
    return out


def main():
    cfg = GameConfig()
    scenarios = [
        ("idle-towns", scenario_idle_towns),
        ("idle-wilderness", scenario_idle_wilderness),
        ("march-towns", scenario_march_towns),
        ("march-wilderness", scenario_march_wilderness),
        ("combat", scenario_combat),
        ("mixed", scenario_mixed),
    ]
    print(f"{'scenario':<17}{'command':>9}{'prop':>9}{'move':>9}{'combat':>9}{'economy':>9}{'know':>9}{'TOTAL':>9}", flush=True)
    for name, fn in scenarios:
        w = fn()
        assert len(w.towns) == 1000 and len(w.armies) == 1000, (len(w.towns), len(w.armies))
        time_phases(w, cfg)  # warmup
        w = fn()
        acc = None
        reps = 3
        for _ in range(reps):
            w = fn()
            r = time_phases(w, cfg)
            acc = r if acc is None else {k: acc[k] + r[k] for k in r}
        ms = {k: acc[k] / reps * 1000 for k in acc}
        tot = sum(ms.values())
        print(f"{name:<17}{ms['command']:>9.1f}{ms['prop']:>9.1f}{ms['move']:>9.1f}"
              f"{ms['combat']:>9.1f}{ms['economy']:>9.1f}{ms['know']:>9.1f}{tot:>9.1f}", flush=True)


if __name__ == "__main__":
    main()
