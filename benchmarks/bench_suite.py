#!/usr/bin/env python3
"""Fast bench suite covering 1→3036 scale. Run: PYTHONPATH=src .venv/bin/python benchmarks/bench_suite.py"""
import time, json, math, random, statistics
import numpy as np
import sys
sys.path.insert(0, "src")
from engine.config import GameConfig
from engine.world import World, Town, Army
from engine import economy, movement, combat, ledger, spatial, step, world as wmod

CFG = GameConfig()
RESULTS=[]

def timeit(fn, repeat=5, warmup=1):
    for _ in range(warmup): fn()
    ts=[]
    for _ in range(repeat):
        t0=time.perf_counter()
        fn()
        ts.append((time.perf_counter()-t0)*1000)
    return statistics.median(ts), min(ts), max(ts)

def bench(name, fn, **kw):
    med, mn, mx = timeit(fn, **kw)
    RESULTS.append((name, med))
    print(f"{name:35s} {med:7.2f} ms  (min {mn:6.2f} max {mx:6.2f})")
    return med

# 1. crowding 500 towns (the test_performance case)
def make_towns(n, seed=99):
    rng=np.random.default_rng(seed)
    return [Town(id=i, faction=0, x=float(rng.random()*1000), y=float(rng.random()*1000), population=float(rng.uniform(500,50000))) for i in range(n)]

def bench_crowding():
    towns=make_towns(500,99)
    def fn():
        for t in towns: economy.crowding_net(t, towns, CFG)
    bench("crowding 500 towns", fn, repeat=7)
    # batch version if available
    if hasattr(economy, "crowding_nets_batch"):
        def fn2(): economy.crowding_nets_batch(towns, CFG)
        bench("crowding batch 500", fn2, repeat=7)

# 2. step no armies
def load_world_from_map(path):
    with open(path) as f: data=json.load(f)
    cfg=GameConfig.from_dict(data)
    w=World()
    w.map_size=data.get("map_size", [1000,1000])
    # parse settlements
    # full.json has settlements: list of {id, faction, x, y, population, is_capital}
    towns=data.get("settlements") or data.get("towns") or []
    for t in towns:
        w.towns.append(Town(id=t["id"], faction=t["faction"], x=t["x"], y=t["y"], population=t.get("population",5000), is_capital=t.get("is_capital", False)))
    # also load config map csv if needed? For bench we just use towns list.
    return w, cfg

def bench_step_no_armies():
    for path, name in [("maps/empty.json","empty 5 towns"), ("maps/full.json","full 415 towns")]:
        try:
            w,cfg = load_world_from_map(path)
        except Exception as e:
            print(f"skip {name}: {e}"); continue
        # need ledger/record stubs; just bench _phase_economy + movement + combat?
        # Use step.step wrapper with no orders
        from engine.ledger import Ledger
        # clone for repeat
        def make_fn():
            ww, cc = load_world_from_map(path)
            import math
            lg=Ledger(cc.info_speed, math.hypot(*ww.map_size))
            # init ledger with turn 0 events? not needed
            def fn():
                # ensure deterministic: copy towns
                step.step(ww, cc, lg, rec, turn=1, orders=[])
            return fn
        # warmup already
        # bench just economy phase on that world to avoid ledger complexities
        def econ_fn():
            ww, cc = load_world_from_map(path)
            # bench crowding via apply_growth snapshot
            from engine.economy import apply_growth
            # apply_growth mutates, so copy
            snapshot = [Town(id=t.id, faction=t.faction, x=t.x, y=t.y, population=t.population, is_capital=t.is_capital) for t in ww.towns]
            tmp=World(); tmp.map_size=ww.map_size; tmp.towns=snapshot
            apply_growth(tmp, cc)
        bench(f"economy apply_growth {name}", econ_fn, repeat=5)
        # also bench full step with correct signature if possible
        try:
            def full_fn():
                ww, cc = load_world_from_map(path)
                lg=Ledger(cc.info_speed, math.hypot(*ww.map_size))
                step.step(ww, cc, lg, 1, {})
            bench(f"step no armies {name}", full_fn, repeat=5)
        except Exception as e:
            print(f"step bench skip {name}: {e}")

# 3. movement 1000 armies + combat 1000
def bench_movement():
    for n in [200, 1000]:
        w=World(); w.map_size=[1000,1000]
        rng=np.random.default_rng(1)
        for i in range(n):
            x=float(rng.random()*1000); y=float(rng.random()*1000)
            tx=float(rng.random()*1000); ty=float(rng.random()*1000)
            w.armies.append(Army(id=i, faction=i%5, x=x, y=y, target_x=tx, target_y=ty, has_target=True))
        # also need some towns for movement vs towns
        for i in range(100):
            w.towns.append(Town(id=10000+i, faction=i%5, x=float(rng.random()*1000), y=float(rng.random()*1000), population=5000))
        def fn():
            # copy positions to avoid mutation carryover: reset armies
            # movement mutates, so rebuild
            movement.move_armies(w, CFG)
            # reset for next repeat - easiest: re-randomize
            for a in w.armies:
                a.x=float(rng.random()*1000); a.y=float(rng.random()*1000)
        bench(f"movement {n} armies +100 towns", fn, repeat=7)

def bench_combat():
    for n in [200, 1000]:
        w=World(); w.map_size=[1000,1000]
        rng=np.random.default_rng(2)
        w.armies=[Army(id=i, faction=i%2, x=float(rng.random()*1000), y=float(rng.random()*1000)) for i in range(n)]
        def fn():
            # need copy because combat mutates world
            ww=World(); ww.map_size=[1000,1000]
            ww.armies=[Army(id=a.id, faction=a.faction, x=a.x, y=a.y) for a in w.armies]
            ww.towns=[]
            combat.resolve_combat(ww, CFG)
        bench(f"combat {n} armies", fn, repeat=7)
        # also capture
        def fn2():
            ww=World(); ww.map_size=[1000,1000]
            ww.armies=[Army(id=a.id, faction=a.faction, x=a.x, y=a.y) for a in w.armies[:100]]
            ww.towns=[Town(id=i, faction= (i%2)^1, x=float(rng.random()*1000), y=float(rng.random()*1000), population=5000) for i in range(100)]
            combat.resolve_captures(ww, CFG)
        bench(f"captures 100 armies vs 100 towns", fn2, repeat=7)
        break

# 4. heavy snapshot turn 19->20 (207 towns + 3036 armies)
def bench_heavy_snapshot():
    # construct synthetic worst-case similar to measured: 207 towns clustered, 3036 armies stacked near towns
    w=World(); w.map_size=[1000,1000]
    rng=np.random.default_rng(3)
    # 207 towns ~ from full.json distribution but random for bench
    towns=make_towns(207, seed=7)
    # give them faction spread 5
    for i,t in enumerate(towns): t.faction=i%5; t.is_capital=(i<5)
    w.towns=towns
    # 3036 armies, 80% near towns (stacked), 20% en route
    armies=[]
    for i in range(3036):
        if i%5==0:
            # en route random
            x=float(rng.random()*1000); y=float(rng.random()*1000)
            tx=float(rng.random()*1000); ty=float(rng.random()*1000)
            has=True
        else:
            # stacked near random town within 10
            t=rng.choice(towns)
            x=t.x + float(rng.uniform(-8,8)); y=t.y + float(rng.uniform(-8,8))
            tx,ty=x,y; has=False
        armies.append(Army(id=i, faction=i%5, x=x, y=y, target_x=tx, target_y=ty, has_target=has))
    w.armies=armies
    from engine.ledger import Ledger
    cfg=CFG
    # bench single step turn 20
    def fn():
        # deep copy world for repeatability
        ww=World(); ww.map_size=[1000,1000]
        ww.towns=[Town(id=t.id, faction=t.faction, x=t.x, y=t.y, population=t.population, is_capital=t.is_capital) for t in w.towns]
        ww.armies=[Army(id=a.id, faction=a.faction, x=a.x, y=a.y, target_x=a.target_x, target_y=a.target_y, has_target=a.has_target) for a in w.armies]
        ww._next_army_id=w._next_army_id if hasattr(w, '_next_army_id') else 100000
        ww._next_town_id=w._next_town_id if hasattr(w, '_next_town_id') else 100000
        import math
        lg=Ledger(cfg.info_speed, math.hypot(1000, 1000))
        step.step(ww, cfg, lg, 20, {})
    bench("step heavy 207t+3036a (t19→20)", fn, repeat=3)
    # also micro benches on that scale
    def fn_move():
        ww=World(); ww.map_size=[1000,1000]
        ww.armies=[Army(id=a.id, faction=a.faction, x=a.x, y=a.y, target_x=a.target_x, target_y=a.target_y, has_target=a.has_target) for a in w.armies]
        ww.towns=[Town(id=t.id, faction=t.faction, x=t.x, y=t.y, population=t.population, is_capital=t.is_capital) for t in w.towns]
        movement.move_armies(ww, cfg)
    bench("movement heavy 3036a vs 207t", fn_move, repeat=5)
    def fn_weak():
        lst=[Army(id=a.id, faction=a.faction, x=a.x, y=a.y) for a in w.armies[:1000]]
        combat.compute_weaknesses(lst, cfg)
    bench("weakness 1000 armies", fn_weak, repeat=7)

# 5. ledger visibility 500 turns
def bench_builder_full():
    """EVENT_REWORK pipeline bench (reporting; gates live in tests/engine/test_perf_budget.py).

    Heavy rig + real turn-20 full.json capture: generate ms, delivery ms
    (5 factions, warmed send-states), wire bytes/faction cold (first
    contact, full re-announce) and warm (steady diff), ledger memory.
    """
    import gc, json, sys
    from engine.ledger import Ledger
    from engine.delivery import build_updates
    # --- heavy rig ---
    w = World(); w.map_size = [1000, 1000]
    rng = np.random.default_rng(3)
    towns = make_towns(207, seed=7)
    for i, t in enumerate(towns): t.faction = i % 5; t.is_capital = (i < 5)
    w.towns = towns
    for i in range(3036):
        t = rng.choice(towns)
        w.armies.append(Army(id=i, faction=i % 5, x=t.x + float(rng.uniform(-8, 8)),
                             y=t.y + float(rng.uniform(-8, 8))))
    lg = Ledger(CFG.info_speed, math.hypot(1000, 1000))
    lg.generate(w, 20, line_of_sight=150.0)
    bench("builder heavy generate 207t+3036a", lambda: lg.generate(w, 21, line_of_sight=150.0), repeat=5)
    caps = {}
    for f in range(5):
        c = next(t for t in w.towns if t.faction == f and t.is_capital)
        caps[f] = (c.x, c.y)
    cold = [build_updates(lg, f, 0, caps[f], 21.0) for f in range(5)]
    for f in range(5):
        build_updates(lg, f, 0, caps[f], 21.0)
    bench("builder heavy delivery x5 warm", lambda: [build_updates(lg, f, 0, caps[f], 21.0) for f in range(5)], repeat=5)
    cold_b = [len(json.dumps(u).encode()) for u in cold]
    warm = [build_updates(lg, f, 0, caps[f], 21.0) for f in range(5)]
    warm_b = [len(json.dumps(u).encode()) for u in warm]
    print(f"builder heavy wire/faction cold {sum(cold_b)//5} B (n={[len(u) for u in cold]}) "
          f"warm {sum(warm_b)//5} B (n={[len(u) for u in warm]})")
    # --- memory spot-check (Phase 1 requirement) ---
    evs = list(lg.events)
    sample = evs[::max(1, len(evs) // 200)][:200]
    per = sum(sys.getsizeof(e) + sys.getsizeof(e.payload) + sys.getsizeof(e.visible_to) for e in sample) / max(1, len(sample))
    col_b = sum(len(a) * a.itemsize for a in
                (lg._c_turn, lg._c_x, lg._c_y, lg._c_row, lg._c_tag, lg._c_seq))
    print(f"builder heavy ledger entries {len(evs)} (~{per * len(evs) / 1e6:.1f} MB events, "
          f"{col_b / 1e6:.1f} MB columns) + send-state/faction ~{len(states[0].snaps) + len(states[0].deliv)} rows")
    # --- real turn-20 full.json capture ---
    data = json.load(open("maps/full.json"))
    cfg2 = GameConfig.from_dict(data)
    w2 = World(); w2.map_size = data.get("map_size", [1000, 1000])
    w2.parse_map(data["map"])
    lg2 = Ledger(cfg2.info_speed, math.hypot(*w2.map_size))
    for turn in range(1, 21):
        orders = {}
        for t in w2.towns:
            if t.is_capital:
                orders.setdefault(t.faction, []).append(f"TRAIN {t.id}")
        step.step(w2, cfg2, lg2, turn, orders)
    bench("builder full20 generate 415t+100a", lambda: (lg2.generate(w2, 21, line_of_sight=cfg2.line_of_sight), lg2.evict(21.0)), repeat=5)
    gc.collect()

if __name__=="__main__":
    print("=== bench suite ===")
    bench_crowding()
    bench_step_no_armies()
    bench_movement()
    bench_combat()
    bench_heavy_snapshot()
    bench_builder_full()
    print("\n--- summary sorted ---")
    for n,ms in sorted(RESULTS, key=lambda x: -x[1]):
        print(f"{ms:7.2f} ms  {n}")
