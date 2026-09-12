"""Best 100,000-person layout for growth (one-turn rates).

Sites on a 10 km hex lattice (cell 87 km2 > ring 79, no crowding).
Towns spread by farthest-point sampling; villages are the sites
closest to a town. Measures the single-turn per-capita rate (services
resolve in-turn) and prints the top layouts.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.config import GameConfig
from engine.economy import _step_core
from engine.world import Town, World

CFG = GameConfig()
TOTAL = 100_000.0
S = 10.0


def sites(rmax):
    out = []
    j = 0
    while j * S * math.sqrt(3) / 2 <= rmax:
        y = j * S * math.sqrt(3) / 2
        off = S / 2 if j % 2 else 0.0
        i = 0
        while off + i * S <= rmax:
            x = off + i * S
            for sx in ((1, -1) if x else (1,)):
                for sy in ((1, -1) if y else (1,)):
                    if math.hypot(x, y) <= rmax:
                        out.append((sx * x, sy * y))
            i += 1
        j += 1
    seen, uniq = set(), []
    for p in out:
        k = (round(p[0], 3), round(p[1], 3))
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    c = min(uniq, key=lambda p: math.hypot(*p))
    uniq.remove(c)
    uniq.insert(0, c)
    return uniq


def spread(sl, n):
    chosen = [sl[0]]
    while len(chosen) < n:
        best, bd = None, -1.0
        for p in sl:
            if p in chosen:
                continue
            d = min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in chosen)
            if d > bd:
                bd, best = d, p
        chosen.append(best)
    return chosen


def layout(n_t, T, n_v):
    P = (TOTAL - n_t * T) / n_v
    rmax = math.sqrt((n_v + n_t) * 90 / math.pi) + 12
    sl = sites(rmax)
    towns = spread(sl, n_t) if n_t else []

    def dmin(p):
        return min((math.hypot(p[0] - q[0], p[1] - q[1]) for q in towns), default=1e9)

    villages = sorted((p for p in sl if p not in towns), key=dmin)[:n_v]
    spec = [(500.0, 500.0, T) for _ in towns]
    spec += [(500 + x, 500 + y, P) for x, y in villages]
    return spec


def rate(spec):
    towns = [Town(id=i, faction=0, x=x, y=y, population=p, is_capital=(i == 0))
             for i, (x, y, p) in enumerate(spec)]
    total = sum(t.population for t in towns)
    n2, _s = _step_core(towns, [1000, 1000], CFG)
    return (sum(n2) - total) / total * 52.0 * 100.0


if __name__ == "__main__":
    rows = []
    for n_t, T in [(0, 0), (1, 2400), (1, 4800), (1, 9600), (1, 14400),
                   (2, 4800), (2, 9600), (4, 4800), (9, 4800)]:
        for n_v in (60, 80, 100, 120, 140, 180, 240, 333):
            if n_t * T >= TOTAL:
                continue
            P = (TOTAL - n_t * T) / n_v
            if P > 1900:
                continue
            g = rate(layout(n_t, T, n_v))
            rows.append((g, n_t, T, n_v, P))
    rows.sort(reverse=True)
    print(f"{'%/yr':>8} {'towns':>6} {'T':>7} {'n_v':>5} {'P_v':>7}")
    for g, n_t, T, n_v, P in rows[:15]:
        print(f"{g:+8.4f} {n_t:6d} {T:7.0f} {n_v:5d} {P:7.0f}")
