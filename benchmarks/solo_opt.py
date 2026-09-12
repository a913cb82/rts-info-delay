import json, os, sys, math, time
sys.path.insert(0, "src")
from engine.config import GameConfig
from engine.world import World
from engine import step as stepmod
from engine.ledger import Ledger
MAP = os.environ.get("SOLO_MAP", "maps/solo.json")
MAXT = int(os.environ.get("SOLO_MAXT", "10000"))
d = json.load(open(MAP))
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
_GRID = [(float(gx), float(gy)) for gx in range(30, 1000, 10) for gy in range(40, 1000, 10)]
_sites = {"key": None, "sp": None, "list": []}


def _rebuild_sites():
    """Valid sites (>= spacing from every town), best first.

    Full rescan only when towns/spacing changed; invalid cells exit on
    the first violating town (squared distance), so a filled map scans
    in milliseconds instead of re-mining all towns for every cell."""
    sp = _cur_sp[0]
    sp2 = sp * sp
    towns = w.towns
    out = []
    for x, y in _GRID:
        md2 = 1e18
        ok = True
        for t in towns:
            d2 = (x - t.x) * (x - t.x) + (y - t.y) * (y - t.y)
            if d2 < sp2:
                ok = False
                break
            if d2 < md2:
                md2 = d2
        if ok:
            out.append((md2, x, y))
    out.sort(key=lambda r: (-r[0], r[1], r[2]))  # max min-dist, then gx, gy
    _sites["key"] = tuple(t.id for t in towns)  # ids: catches same-len swaps
    _sites["sp"] = sp
    _sites["list"] = out


def best_site(exclude):
    if _sites["key"] != tuple(t.id for t in w.towns) or _sites["sp"] != _cur_sp[0]:
        _rebuild_sites()
    sp2 = _cur_sp[0] * _cur_sp[0]
    ex = list(exclude) if exclude else []
    for _md2, x, y in _sites["list"]:
        for exx, exy in ex:
            if (x - exx) * (x - exx) + (y - exy) * (y - exy) < sp2:
                break
        else:
            return (x, y)
    return None
t0 = time.perf_counter()
for turn in range(1, MAXT + 1):
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
    if turn % max(1, MAXT // 10) == 0 or turn == MAXT:
        pops = sorted([t.population for t in w.towns if t.faction == 0], reverse=True)
        bands = [(0, 1000), (1000, 5000), (5000, 20000), (20000, 50000), (50000, 1e9)]
        bk = [sum(1 for p in pops if lo <= p < hi) for lo, hi in bands]
        print(f"t{turn}: {len(pops)} towns top {[round(p) for p in pops[:3]]} bands {bk} armies {len([a for a in w.armies if a.faction==0])}", flush=True)
score = sum(t.population for t in w.towns if t.faction == 0) + 1000*sum(1 for a in w.armies if a.faction == 0)
pops_all = [t.population for t in w.towns if t.faction == 0]
bands = [(0, 1000), (1000, 5000), (5000, 20000), (20000, 50000), (50000, 1e9)]
res = {"thresh": THRESH, "spacing": SPACING, "stop": STOP, "source": SOURCE,
       "buckets": [sum(1 for p in pops_all if lo <= p < hi) for lo, hi in bands],
       "top": [round(p) for p in sorted(pops_all, reverse=True)[:5]],
       "sp_late": SP_LATE, "switch": SWITCH, "maxt": MAXT, "map": MAP,
       "towns": sum(1 for t in w.towns if t.faction == 0),
       "score": round(score), "elapsed_s": round(time.perf_counter() - t0, 1)}
print("RESULT " + json.dumps(res), flush=True)
