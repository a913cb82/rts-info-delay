import json, sys, math, time
sys.path.insert(0, "src")
from engine.config import GameConfig
from engine.world import World
from engine import step as stepmod
from engine.ledger import Ledger
d = json.load(open("/tmp/solo.json"))
cfg = GameConfig.from_dict({k: v for k, v in d.items() if k != "type"})
THRESH, SPACING, STOP = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
SOURCE = int(sys.argv[4]) if len(sys.argv) > 4 else 0
w = World(); w.map_size = d.get("map_size", [1000, 1000]); w.parse_map(d["map"])
lg = Ledger(cfg.info_speed, math.hypot(*w.map_size))
marching = {}  # aid -> (tx,ty); seen ids; expecting list of sites
seen = set(); expecting = []
foundings = []
SP_LATE = float(__import__("sys").argv[5]) if len(__import__("sys").argv) > 5 else -1.0
SWITCH = int(__import__("sys").argv[6]) if len(__import__("sys").argv) > 6 else 7000
_cur_sp = [150.0]
def best_site(exclude):
    best, bd = None, -1.0
    gx = 30
    while gx < 1000:
        gy = 40
        while gy < 1000:
            md = min([math.hypot(gx-t.x, gy-t.y) for t in w.towns] or [1e9])
            if exclude and min([math.hypot(gx-x, gy-y) for x, y in exclude] or [1e9]) < _cur_sp[0]:
                gy += 10; continue
            if md >= _cur_sp[0] and md > bd:
                bd, best = md, (float(gx), float(gy))
            gy += 10
        gx += 10
    return best
t0 = time.perf_counter()
for turn in range(1, 10001):
    _cur_sp[0] = SP_LATE if (SP_LATE > 0 and turn >= SWITCH) else SPACING
    orders = {0: []}
    for a in w.armies:
        if a.faction == 0 and a.id in marching:
            tx, ty = marching[a.id]
            if math.hypot(a.x-tx, a.y-ty) <= 10.0:
                orders[0].append(f"BUILD {a.id} {tx:.1f} {ty:.1f}")
            else:
                orders[0].append(f"MOVE_TO {a.id} {a.x:.1f} {a.y:.1f} {tx:.1f} {ty:.1f}")
    if turn <= STOP:
        claimed = list(marching.values()) + expecting
        if SOURCE == 2:
            # site-outer (logistics): best site, then NEAREST eligible
            # source (minimize march; border towns feed frontier sites,
            # interior engine keeps compounding).
            while True:
                site = best_site(claimed)
                if site is None: break
                cands = sorted([t for t in w.towns if t.faction == 0 and t.population >= THRESH],
                               key=lambda t: math.hypot(t.x-site[0], t.y-site[1]))
                if not cands: break
                orders[0].append(f"TRAIN {cands[0].id}")
                expecting.append(site); claimed.append(site)
        elig = [t for t in w.towns if t.faction == 0 and t.population >= THRESH] if SOURCE != 2 else []
        if SOURCE == 1:
            def crowd(t):
                return sum(1 for u in w.towns if u.id != t.id and math.hypot(u.x-t.x, u.y-t.y) <= 150.0)
            elig = sorted(elig, key=lambda t: (-crowd(t), -t.population))
        else:
            elig = sorted(elig, key=lambda t: -t.population)
        for t in elig:
            if True:
                site = best_site(claimed)
                if site is None: break
                orders[0].append(f"TRAIN {t.id}")
                expecting.append(site); claimed.append(site)
    stepmod.step(w, cfg, lg, turn, orders)
    # assign expecting sites to newly spawned armies; drop consumed (built) from marching
    live = {a.id for a in w.armies if a.faction == 0}
    for aid in list(marching):
        if aid not in live:
            # built (founded) or died; if it was at site -> founding happened (count via towns below)
            del marching[aid]
    new_ids = [a.id for a in w.armies if a.faction == 0 and a.id not in seen and a.id not in marching]
    seen |= set(live)
    while expecting and new_ids:
        marching[new_ids.pop(0)] = expecting.pop(0)
    if expecting and turn % 500 == 0:
        expecting = []  # train failed (shouldn't happen); don't jam
    if turn in (2000, 4000, 6000, 8000, 10000):
        pops = sorted([t.population for t in w.towns if t.faction == 0], reverse=True)
        print(f"t{turn}: {len(pops)} towns top {[round(p) for p in pops[:3]]} armies {len([a for a in w.armies if a.faction==0])}", flush=True)
score = sum(t.population for t in w.towns if t.faction == 0) + 1000*sum(1 for a in w.armies if a.faction == 0)
print(f"THRESH {THRESH} SPACING {SPACING} STOP {STOP} -> towns {sum(1 for t in w.towns if t.faction==0)} score {round(score)} ({time.perf_counter()-t0:.1f}s)", flush=True)
