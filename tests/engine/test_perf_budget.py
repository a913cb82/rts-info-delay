"""Perf budget gates for the EVENT_REWORK pipeline (generation + delivery).

Pin current numbers as ceilings; fail loudly on regression. Follows the
house rules: settled GC, repeated measurement, paired same-box. Budgets
sit ~20-50% above measured bests to avoid flake, tight enough to catch
real regressions (e.g. reintroducing the double-loop observer scan blows
the heavy budget by 2x).
"""
import gc
import json
import math
import time

import numpy as np

from engine.config import GameConfig
from engine.delivery import build_updates
from engine.ledger import Ledger
from engine.world import Army, Town, World

CFG = GameConfig()

# Measured bests (2026-09, numba observer kernel): heavy ~25ms,
# full20 ~3.4ms, delivery-5 ~1ms. Heavy budget carries +10ms headroom:
# the gate catches 2x regressions (the 63ms double loop), not suite-load
# noise (one 30ms-flake observed under a full-suite run).
HEAVY_BUDGET_MS = 35.0
FULL20_BUDGET_MS = 5.0
DELIVERY_BUDGET_MS = 3.0


def _med(fn, n=5):
    ts = []
    for _ in range(n):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    return ts[len(ts) // 2]


def _heavy_world():
    rng = np.random.default_rng(3)
    w = World()
    w.map_size = [1000, 1000]
    towns = [Town(id=i, faction=i % 5, x=float(rng.random() * 1000),
                  y=float(rng.random() * 1000), population=1000.0,
                  is_capital=(i < 5)) for i in range(207)]
    w.towns = towns
    for i in range(3036):
        t = towns[i % 207]
        w.armies.append(Army(id=i, faction=i % 5,
                             x=t.x + float(rng.uniform(-8, 8)),
                             y=t.y + float(rng.uniform(-8, 8))))
    return w


def test_heavy_generate_budget() -> None:
    w = _heavy_world()
    lg = Ledger(CFG.info_speed, math.hypot(1000, 1000))
    lg.generate(w, 20, line_of_sight=150.0)  # warm registries
    ms = _med(lambda: lg.generate(w, 21, line_of_sight=150.0))
    print(f"\nheavy generate: {ms:.2f} ms (budget {HEAVY_BUDGET_MS})")
    assert ms <= HEAVY_BUDGET_MS


def test_full20_generate_budget() -> None:
    from engine import step as stepmod
    data = json.load(open("maps/full.json"))
    cfg = GameConfig.from_dict(data)
    w = World()
    w.map_size = data.get("map_size", [1000, 1000])
    w.parse_map(data["map"])
    lg = Ledger(cfg.info_speed, math.hypot(*w.map_size))
    for turn in range(1, 21):
        orders = {}
        for t in w.towns:
            if t.is_capital:
                orders.setdefault(t.faction, []).append(f"TRAIN {t.id}")
        stepmod.step(w, cfg, lg, turn, orders)
    ms = _med(lambda: (lg.generate(w, 21, line_of_sight=cfg.line_of_sight),
                       lg.evict(21.0)))
    print(f"\nfull20 generate: {ms:.2f} ms (budget {FULL20_BUDGET_MS})")
    assert ms <= FULL20_BUDGET_MS


def test_heavy_delivery_budget() -> None:
    w = _heavy_world()
    lg = Ledger(CFG.info_speed, math.hypot(1000, 1000))
    lg.generate(w, 21, line_of_sight=150.0)
    caps = {}
    for f in range(5):
        c = next(t for t in w.towns if t.faction == f and t.is_capital)
        caps[f] = (c.x, c.y)
    states = {f: None for f in range(5)}
    for f in range(5):  # warm send-states (steady state)
        build_updates(lg, f, states[f], 0, caps[f], 21.0)
    ms = _med(lambda: [build_updates(lg, f, states[f], 0, caps[f], 21.0)
                       for f in range(5)])
    print(f"\nheavy delivery x5 warm: {ms:.2f} ms (budget {DELIVERY_BUDGET_MS})")
    assert ms <= DELIVERY_BUDGET_MS
