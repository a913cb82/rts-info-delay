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
            lg=Ledger(cc)
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
                lg=Ledger(cc)
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
        lg=Ledger(cfg)
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
def bench_ledger():
    # skip ledger bench - API mismatch, not critical for engine perf
    # will add proper ledger bench later
    pass

if __name__=="__main__":
    print("=== bench suite ===")
    bench_crowding()
    bench_step_no_armies()
    bench_movement()
    bench_combat()
    bench_heavy_snapshot()
    bench_ledger()
    print("\n--- summary sorted ---")
    for n,ms in sorted(RESULTS, key=lambda x: -x[1]):
        print(f"{ms:7.2f} ms  {n}")
