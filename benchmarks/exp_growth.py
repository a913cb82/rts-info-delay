"""New-engine growth lab: scripted scenarios from a 500-pop village.

Drives step() directly with structured orders (no fog/delay noise).
Usage: python benchmarks/exp_growth.py [E1|E2|E3|E4]
"""
import json
import sys

sys.path.insert(0, "src")
from engine.config import GameConfig
from engine.world import World
from engine import step as stepmod

BASE = json.loads(open("maps/empty.json").read().split('"map"')[0] + '"map":"" }') \
    if False else None


def make_cfg(max_turns=3000, map_csv="500.0,500.0,A,500"):
    d = json.loads(open("maps/empty.json").read())
    d["map"] = map_csv
    d["max_turns"] = max_turns
    return GameConfig.from_dict(d), d.get("map_size", [1000, 1000])


def make_world(map_csv="500.0,500.0,A,500"):
    cfg, map_size = make_cfg(map_csv=map_csv)
    w = World()
    w.map_size = map_size
    w.parse_map(map_csv)
    return w, cfg


def score(w):
    return sum(t.population for t in w.towns) + sum(a.size for a in w.armies)


def run(w, cfg, turns, script=None, log_every=500):
    """script(turn, w) -> list of structured order dicts."""
    hist = []
    for t in range(1, turns + 1):
        orders = script(t, w) if script else []
        stepmod.step(w, cfg, None, t, orders)
        if t % log_every == 0 or t == turns:
            hist.append((t, round(score(w), 1),
                         [(x.id, round(x.population, 1)) for x in w.towns],
                         [(x.id, round(x.size, 1)) for x in w.armies]))
    return hist


def show(hist):
    for t, s, towns, armies in hist:
        print(f"t={t} score={s} towns={towns} armies={armies}")


def e1_idle():
    """Single 500 town, no orders: equilibrium?"""
    w, cfg = make_world()
    show(run(w, cfg, 3000))


def wait_army(w, faction=0):
    for a in w.armies:
        if a.faction == faction:
            return a
    return None


def found_script(dist, size=50.0, every=None):
    """TRAIN size, march `dist` east, BUILD. Repeat every `every` turns."""
    st = {"phase": "train", "aid": None, "next": 1}

    def script(t, w):
        if every is not None and t >= st["next"] and st["phase"] == "train":
            st["phase"] = "march"
            return [{"command": "TRAIN", "town_id": 0, "size": size}]
        if every is None and t == 1:
            st["phase"] = "march"
            return [{"command": "TRAIN", "town_id": 0, "size": size}]
        a = wait_army(w)
        if a is None:
            if st["phase"] != "train":
                st["phase"] = "train"
                st["next"] = t + (every or 10 ** 9)
            return []
        if st["phase"] == "march":
            st["phase"] = "build"
            st["aid"] = a.id
            return [{"command": "MOVE_TO", "army_id": a.id,
                     "to_x": 500.0 + dist, "to_y": 500.0, "amount": 0.0}]
        if st["phase"] == "build" and abs(a.x - (500.0 + dist)) < 1e-6 \
                and abs(a.y - 500.0) < 1e-6:
            st["phase"] = "train"
            st["next"] = t + (every or 10 ** 9)
            return [{"command": "BUILD", "army_id": a.id,
                     "x": 500.0 + dist, "y": 500.0, "size": size}]
        return []
    return script


def e2_found_near():
    """One 45-pop colony 20km east: mother recovery + net score?"""
    w, cfg = make_world()
    show(run(w, cfg, 3000, found_script(20.0)))


def e3_distances():
    """Colony distance sweep: survival + total score at t=3000."""
    for dist in (8.0, 15.0, 30.0, 60.0):
        w, cfg = make_world()
        hist = run(w, cfg, 3000, found_script(dist), log_every=3000)
        t, s, towns, armies = hist[-1]
        print(f"dist={dist} score={s} towns={towns} armies={armies}")


def e4_spam():
    """Found a colony every 300 turns (20 east, leapfrog): total vs count."""
    w, cfg = make_world()
    # leapfrog: each new colony goes 20km further east from the last town
    st = {"phase": "train", "next": 1, "base": 500.0, "n": 0}

    def script(t, w):
        if st["phase"] == "train" and t >= st["next"]:
            st["phase"] = "march"
            return [{"command": "TRAIN", "town_id": 0, "size": 50.0}]
        a = wait_army(w)
        if a is None:
            return []
        tx = st["base"] + 20.0
        if st["phase"] == "march":
            st["phase"] = "build"
            return [{"command": "MOVE_TO", "army_id": a.id,
                     "to_x": tx, "to_y": 500.0, "amount": 0.0}]
        if st["phase"] == "build" and abs(a.x - tx) < 1e-6 and abs(a.y - 500.0) < 1e-6:
            st["phase"] = "train"
            st["next"] = t + 300
            st["base"] = tx
            st["n"] += 1
            return [{"command": "BUILD", "army_id": a.id,
                     "x": tx, "y": 500.0, "size": 50.0}]
        return []
    show(run(w, cfg, 3000, script))


if __name__ == "__main__":
    {"E1": e1_idle, "E2": e2_found_near, "E3": e3_distances, "E4": e4_spam}[sys.argv[1]]()
