"""Bot-side benchmarks: update() + decide() cost per tier.

Usage: PYTHONPATH=src .venv/bin/python benchmarks/bot_bench.py
Two workloads: quiet turn (5 pop_change, the 95% case) and heavy backlog
(2000 mixed events). Reports med ms for update and decide per bot tier.
"""
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bots.common import BotState
from engine.config import GameConfig
from engine.world import Town
import bots.expander as expander
import bots.aggressive as aggressive
import bots.turtle as turtle
import bots.pro as pro_mod

CFG = GameConfig()
TIERS = {
    "expander": expander.decide_orders,
    "aggressive": aggressive.decide_orders,
    "turtle": turtle.decide_orders,
    "pro": pro_mod.decide_orders,
}


def make_state(n_towns=6, n_armies=4):
    st = BotState()
    st.init(CFG, 0)
    for i in range(n_towns):
        st.world.towns.append(Town(id=i, faction=0, x=100.0 + i * 137.0,
                                   y=100.0 + i * 89.0, population=20000.0,
                                   is_capital=(i == 0)))
    from engine.world import Army
    for i in range(n_armies):
        st.world.armies.append(Army(id=100 + i, faction=0, x=150.0 + i * 40.0,
                                    y=150.0, target_x=150.0 + i * 40.0,
                                    target_y=150.0, has_target=False))
    return st


def quiet_events(st):
    return [{"kind": "pop_change", "id": t.id, "population": t.population + 5.0}
            for t in st.world.towns]


def heavy_events(n=2000):
    evts = []
    for i in range(n):
        k = i % 6
        if k == 0:
            evts.append({"kind": "pop_change", "id": i % 6, "population": 20000.0 + i})
        elif k == 1:
            evts.append({"kind": "army_spawn", "id": 1000 + i, "faction": i % 5,
                         "x": float(i % 1000), "y": float((i * 7) % 1000)})
        elif k == 2:
            evts.append({"kind": "army_move", "id": 1000 + i - 1,
                         "x": float(i % 1000), "y": float((i * 7) % 1000)})
        elif k == 3:
            evts.append({"kind": "army_death", "id": 1000 + i - 1,
                         "x": 0.0, "y": 0.0})
        elif k == 4:
            evts.append({"kind": "town_spawn", "id": 500 + i, "faction": i % 5,
                         "x": float(i % 1000), "y": float((i * 7) % 1000),
                         "population": 500.0})
        else:
            evts.append({"kind": "battle", "x": 500.0, "y": 500.0,
                         "turn": 10, "payload": {}})
    return evts


def bench_update(st, evts, reps=7):
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        st.update(st.turn + 1, list(evts))
        ts.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ts)


def bench_decide(st, decide, reps=7):
    st.deadline = time.time() + 60
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        decide(st, CFG)
        ts.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ts)


def main():
    print("=== quiet turn (6 towns, 5 pop_change) ===")
    for name, decide in TIERS.items():
        st = make_state()
        u = bench_update(st, quiet_events(st))
        d = bench_decide(st, decide)
        print(f"{name:10} update {u:7.3f}ms  decide {d:7.3f}ms  total {u + d:7.3f}ms")
    print("=== heavy backlog (2000 mixed events) ===")
    h = heavy_events()
    for name, decide in TIERS.items():
        st = make_state()
        u = bench_update(st, h)
        d = bench_decide(st, decide)
        print(f"{name:10} update {u:7.3f}ms  decide {d:7.3f}ms  total {u + d:7.3f}ms")


if __name__ == "__main__":
    main()
