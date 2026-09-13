"""S1 RAID SNOWBALL: scripted 10k-turn conquest compounding.

Scenarios (faction A = raider, oracle scripts, string orders via step()):
  A) A raids idle-B every 2000t (60-army), boosts captives (BUILD), vs A-idle control
  B) A raids mustering-B (reactive TRAIN), vs A-idle control
  C) A double-raids alternating idle victims B/C, raid size = 10% of capital (re-raid bigger)
Usage: python benchmarks/raid_snowball.py [A|B|C|all]
"""
import json
import sys

sys.path.insert(0, "src")
from engine.config import GameConfig
from engine.world import World
from engine import step as stepmod

MAP_A = """300.0,500.0,A,600
700.0,500.0,B,600
560.0,420.0,B,500
560.0,580.0,B,500
740.0,420.0,B,500
740.0,580.0,B,500
840.0,500.0,B,500"""

MAP_C = """500.0,500.0,A,600
200.0,500.0,B,600
280.0,420.0,B,500
280.0,580.0,B,500
800.0,500.0,C,600
720.0,420.0,C,500
720.0,580.0,C,500"""

RAID_TURNS = [200, 2200, 4200, 6200, 8200]


def make_world(map_csv, max_turns=10000):
    d = json.loads(open("maps/empty.json").read())
    d["map"] = map_csv
    d["max_turns"] = max_turns
    cfg = GameConfig.from_dict(d)
    w = World()
    w.map_size = d.get("map_size", [1000, 1000])
    w.parse_map(map_csv)
    return w, cfg


def fscore(w, faction):
    return (sum(t.population for t in w.towns if t.faction == faction)
            + sum(a.size for a in w.armies if a.faction == faction))


def towns_of(w, faction):
    return [t for t in w.towns if t.faction == faction]


def armies_of(w, faction):
    return [a for a in w.armies if a.faction == faction]


def nearest_foe_town(w, ax, ay, foes):
    cands = [t for t in w.towns if t.faction in foes]
    if not cands:
        return None
    # colonies first (capital last: losing it cripples messenger math), then nearest
    cands.sort(key=lambda t: ((0 if not t.is_capital else 1),
                              (t.x - ax) ** 2 + (t.y - ay) ** 2))
    return cands[0]


class Raider:
    """Cycle: TRAIN at capital -> march to nearest foe town -> BUILD boost -> idle."""

    def __init__(self, raid_turns, foes, size_fn=None):
        self.raid_turns = list(raid_turns)
        self.foes = list(foes)
        self.size_fn = size_fn or (lambda w, cap: 60.0)
        self.phase = "idle"
        self.aid = None
        self.tx = self.ty = None
        self.raids = 0
        self.takes = 0

    def __call__(self, t, w):
        orders = []
        caps = [x for x in towns_of(w, 0) if x.is_capital]
        if not caps:
            return orders
        cap = caps[0]
        if self.phase == "idle":
            if t in self.raid_turns:
                tgt = nearest_foe_town(w, cap.x, cap.y, self.foes)
                if tgt is None:
                    return orders
                size = self.size_fn(w, cap)
                self.tx, self.ty = tgt.x, tgt.y
                self.phase = "train"
                return [f"TRAIN {cap.id} {size:.1f}"]
            return orders
        mine = [a for a in armies_of(w, 0) if a.id == self.aid]
        if self.phase == "train":
            # army spawned?
            fresh = [a for a in armies_of(w, 0)
                     if abs(a.x - cap.x) < 1e-6 and abs(a.y - cap.y) < 1e-6
                     and not a.has_target]
            if fresh:
                a = fresh[0]
                self.aid = a.id
                self.phase = "march"
                self.raids += 1
                return [f"MOVE_TO {a.id} {a.x} {a.y} {self.tx} {self.ty}"]
            # TRAIN may still be in flight; retry if no army yet after a while
            if not armies_of(w, 0):
                size = self.size_fn(w, cap)
                return [f"TRAIN {cap.id} {size:.1f}"]
            return orders
        if not mine:
            # army died (mustered) -> idle till next cycle
            self.phase = "idle"
            self.aid = None
            return orders
        a = mine[0]
        if self.phase == "march":
            # arrived? (within 10km capture range of target point)
            if (a.x - self.tx) ** 2 + (a.y - self.ty) ** 2 < 100.0:
                # check flip: town at target now ours?
                tgt = [x for x in w.towns
                       if abs(x.x - self.tx) < 1e-6 and abs(x.y - self.ty) < 1e-6]
                if tgt and tgt[0].faction == 0:
                    self.takes += 1
                    self.phase = "boost"
                    return [f"BUILD {a.id} {self.tx} {self.ty} {a.size:.1f}"]
                # blocked/enemy stack: wait a bit, then give up
                self.wait = getattr(self, "wait", 0) + 1
                if self.wait > 15:
                    self.phase = "idle"
                    self.wait = 0
                return orders
            # still marching (or messenger delay): re-issue if stationary w/o target
            if not a.has_target:
                return [f"MOVE_TO {a.id} {a.x} {a.y} {self.tx} {self.ty}"]
            return orders
        if self.phase == "boost":
            # BUILD messenger takes dist/150 turns; confirm army spent then idle
            if a.size < 1.0:
                self.phase = "idle"
                self.aid = None
            elif not getattr(self, "boost_sent", False):
                self.boost_sent = True
                return [f"BUILD {a.id} {self.tx} {self.ty} {a.size:.1f}"]
            else:
                # still waiting on messenger; re-issue
                return [f"BUILD {a.id} {self.tx} {self.ty} {a.size:.1f}"]
            return orders
        return orders

    def reset_cycle_flags(self):
        self.boost_sent = False
        self.wait = 0


def muster(faction, radius=200.0, cap_stack=200.0):
    """Reactive defense: threatened towns TRAIN 10% until home stack >= cap."""

    def script(t, w):
        orders = []
        raiders = armies_of(w, 0)
        if not raiders:
            return orders
        for town in towns_of(w, faction):
            home = sum(a.size for a in armies_of(w, faction)
                       if abs(a.x - town.x) < 1e-6 and abs(a.y - town.y) < 1e-6)
            if home >= cap_stack:
                continue
            threat = any((a.x - town.x) ** 2 + (a.y - town.y) ** 2 < radius ** 2
                         for a in raiders)
            if threat:
                orders.append(f"TRAIN {town.id} {town.population * 0.1:.1f}")
        return orders

    return script


def run(map_csv, turns, a_script, b_script=None, c_script=None, log_every=2000,
        label=""):
    w, cfg = make_world(map_csv, max_turns=turns)
    raider = a_script
    hist = []
    for t in range(1, turns + 1):
        orders = {0: raider(t, w) if raider else []}
        if b_script:
            orders[1] = b_script(t, w)
        if c_script:
            orders[2] = c_script(t, w)
        if raider and hasattr(raider, "phase") and raider.phase == "idle":
            raider.reset_cycle_flags()
        stepmod.step(w, cfg, None, t, orders)
        if t % log_every == 0 or t == turns:
            hist.append((t, round(fscore(w, 0), 1),
                         round(sum(fscore(w, f) for f in (1, 2)), 1),
                         len(towns_of(w, 0))))
    a = hist[-1]
    print(f"{label}: t10000 A={a[1]} foes={a[2]} A-towns={a[3]} "
          f"raids={raider.raids if raider else 0} takes={raider.takes if raider else 0}")
    for t, fa, ff, n in hist[:-1]:
        print(f"   t={t} A={fa} foes={ff} A-towns={n}")
    return a[1]


def scenario(which):
    TURNS = 10000
    if which == "A":
        r = Raider(RAID_TURNS, [1])
        s_raid = run(MAP_A, TURNS, r, label="A raid-vs-idle ")
        s_idle = run(MAP_A, TURNS, None, label="A idle-control")
        print(f"A-DELTA vs idle: {s_raid - s_idle:+.0f}")
    elif which == "B":
        r = Raider(RAID_TURNS, [1])
        s_raid = run(MAP_A, TURNS, r, b_script=muster(1), label="B raid-vs-muster")
        s_idle = run(MAP_A, TURNS, None, label="B idle-control ")
        print(f"B-DELTA vs idle: {s_raid - s_idle:+.0f}")
    elif which == "C":
        cap10 = lambda w, cap: round(cap.population * 0.1, 1)
        r = Raider(RAID_TURNS, [1, 2], size_fn=cap10)
        s_raid = run(MAP_C, TURNS, r, label="C dbl-raid idle ")
        s_idle = run(MAP_C, TURNS, None, label="C idle-control")
        print(f"C-DELTA vs idle: {s_raid - s_idle:+.0f}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    for w in (["A", "B", "C"] if arg == "all" else [arg]):
        scenario(w)
