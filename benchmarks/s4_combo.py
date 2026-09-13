"""S4 COMBO: raid early + conveyor mid + boosts + late spike vs each-alone vs idle.

Arms (same map A600 @ (400,500) + idle-B600 @ (600,500); score = faction-0):
  combo : raid t100 (TRAIN60->capture) + 2 breeder colonies + boosts ~1500t + drain-spike t7000+
  raid  : raid t100 only, then idle (B eliminated; nothing left to re-raid)
  grow  : T0 conveyor 6x~47 @20km ring, no raid
  idle  : nothing
Usage: python benchmarks/s4_combo.py
"""
import json
import sys

sys.path.insert(0, "src")
from engine.config import GameConfig
from engine.world import World
from engine import step as stepmod

MAP = "400.0,500.0,A,600\n600.0,500.0,B,600"
MOTHER = (400.0, 500.0)
PREY = (600.0, 500.0)
TURNS = 10000


def make_world():
    d = json.loads(open("maps/empty.json").read())
    d["map"] = MAP
    d["max_turns"] = TURNS
    cfg = GameConfig.from_dict(d)
    w = World()
    w.map_size = d.get("map_size", [1000, 1000])
    w.parse_map(MAP)
    return w, cfg


def f0score(w):
    return (sum(t.population for t in w.towns if t.faction == 0)
            + sum(a.size for a in w.armies if a.faction == 0))


def idle_armies_at(w, x, y):
    return [a for a in w.armies if a.faction == 0 and not a.has_target
            and abs(a.x - x) < 1e-6 and abs(a.y - y) < 1e-6]


def town_at(w, x, y, fac=0):
    for t in w.towns:
        if t.faction == fac and abs(t.x - x) < 1e-6 and abs(t.y - y) < 1e-6:
            return t
    return None


def prey_taken(w):
    t = town_at(w, *PREY)
    return t is not None and t.faction == 0


class Serial:
    """One mission at a time: TRAIN src->march dest->BUILD/done."""

    def __init__(self, missions):
        self.m = missions  # list of dicts {op,src,dest,size,state,aid}
        self.i = 0

    def __call__(self, t, w):
        # skip missions whose time hasn't come
        while self.i < len(self.m) and t < self.m[self.i].get("at", 1):
            return []
        if self.i >= len(self.m):
            return []
        m = self.m[self.i]
        src, dest = m["src"], m["dest"]
        st = m.get("state", "train")
        if st == "train":
            town = town_at(w, *src)
            if town is None:
                self.i += 1
                return []
            size = m["size"]() if callable(m["size"]) else m["size"]
            size = min(size, 0.1 * town.population * 0.999)
            if size < 1:
                return []
            m["state"] = "march"
            return [{"command": "TRAIN", "town_id": town.id, "size": size}]
        # march/build: find our army (idle, at src) or track by aid
        a = None
        if m.get("aid") is not None:
            a = w.get_army(m["aid"])
            if a is None or a.faction != 0:
                self.i += 1
                return []
        else:
            cands = idle_armies_at(w, *src)
            if not cands:
                # army may be spawned but standing? else wait
                return []
            a = cands[0]
            m["aid"] = a.id
        if abs(a.x - dest[0]) < 1e-6 and abs(a.y - dest[1]) < 1e-6:
            # Cash out: BUILD converts eaters to pop AND removes mouths.
            # (Never leave a parked garrison on a prize: it eats the harvest
            #  and steals later arrivals via same-spot merge.)
            self.i += 1
            return [{"command": "BUILD", "army_id": a.id,
                     "x": dest[0], "y": dest[1], "size": a.size}]
        if not a.has_target:
            return [{"command": "MOVE_TO", "army_id": a.id,
                     "to_x": dest[0], "to_y": dest[1], "amount": 0.0}]
        return []


def drain(t, w):
    """Late spike: every feeder TRAINs 10% whenever free; idle armies march+BUILD into mother."""
    if t < 7000:
        return []
    orders = []
    claimed = set()
    for a in w.armies:
        if a.faction != 0 or a.has_target:
            continue
        if abs(a.x - MOTHER[0]) < 1e-6 and abs(a.y - MOTHER[1]) < 1e-6:
            orders.append({"command": "BUILD", "army_id": a.id,
                           "x": MOTHER[0], "y": MOTHER[1], "size": a.size})
        else:
            orders.append({"command": "MOVE_TO", "army_id": a.id,
                           "to_x": MOTHER[0], "to_y": MOTHER[1], "amount": 0.0})
        claimed.add(a.id)
    # feeders train if no outstanding idle army sitting on them (avoid pileup)
    for town in list(w.towns):
        if town.faction != 0 or town.population < 60:
            continue
        if abs(town.x - MOTHER[0]) < 1e-6 and abs(town.y - MOTHER[1]) < 1e-6:
            continue  # mother is the sink, not a feeder
        if any(abs(a.x - town.x) < 1e-6 and abs(a.y - town.y) < 1e-6
               for a in w.armies if a.faction == 0):
            continue
        orders.append({"command": "TRAIN", "town_id": town.id,
                       "size": 0.1 * town.population * 0.999})
    return orders


def combo_script():
    ring = [(420.0, 500.0), (380.0, 500.0)]
    missions = [
        {"op": "raid", "src": MOTHER, "dest": PREY, "size": 60.0, "at": 100},
        {"op": "found", "src": MOTHER, "dest": ring[0], "size": 50.0, "at": 150},
        {"op": "found", "src": MOTHER, "dest": ring[1], "size": 50.0, "at": 500},
    ]
    # boosts of captive every ~1500t (TRAIN mother -> BUILD captive)
    for at in (1600, 3100, 4600, 6100):
        missions.append({"op": "boost", "src": MOTHER, "dest": PREY,
                         "size": 50.0, "at": at})
    s = Serial(missions)

    def script(t, w):
        o = s(t, w)
        if t >= 7000:
            return o + drain(t, w)
        return o
    return script


def raid_script():
    s = Serial([{"op": "raid", "src": MOTHER, "dest": PREY, "size": 60.0, "at": 100}])
    return s


def grow_script():
    import math
    missions = []
    for k in range(6):
        ang = math.pi * k / 3
        dest = (400.0 + 20 * math.cos(ang), 500.0 + 20 * math.sin(ang))
        missions.append({"op": "found", "src": MOTHER, "dest": dest,
                         "size": 47.0, "at": 1 + 300 * k})
    return Serial(missions)


def run(name, script):
    w, cfg = make_world()
    snap = {}
    for t in range(1, TURNS + 1):
        orders = script(t, w) if script else []
        stepmod.step(w, cfg, None, t, orders)
        if t in (1000, 3000, 7000, TURNS):
            snap[t] = round(f0score(w), 1)
    print(f"{name}: " + " ".join(f"t{k}={v}" for k, v in snap.items())
          + f" towns={[(round(x.x), round(x.population)) for x in w.towns if x.faction == 0]}",
          flush=True)


if __name__ == "__main__":
    run("idle ", None)
    run("grow ", grow_script())
    run("raid ", raid_script())
    run("combo", combo_script())
