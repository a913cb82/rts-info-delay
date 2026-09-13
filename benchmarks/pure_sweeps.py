"""Pure-growth sweeps (honest costs, 500-start, t10000 metric)."""
import math
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "benchmarks")
from exp_growth import make_world, run, wait_army


def found_ring(n, dist=20.0, size=50.0, max_turns=10000):
    """Found n colonies honestly, then idle. Returns final (score, towns)."""
    cx, cy = 500.0, 500.0
    sites = [(cx + dist * math.cos(a), cy + dist * math.sin(a))
             for a in [i * 2 * math.pi / n for i in range(n)]]
    st = {"i": 0, "phase": "train"}

    def script(t, w):
        if st["i"] >= len(sites):
            return []
        tx, ty = sites[st["i"]]
        if st["phase"] == "train":
            mother = next(x for x in w.towns if x.id == 0)
            if mother.population < 500:
                return []
            st["phase"] = "march"
            return [{"command": "TRAIN", "town_id": 0, "size": size}]
        a = wait_army(w)
        if a is None:
            return []
        if st["phase"] == "march":
            st["phase"] = "build"
            return [{"command": "MOVE_TO", "army_id": a.id, "to_x": tx, "to_y": ty, "amount": 0.0}]
        if st["phase"] == "build" and abs(a.x - tx) < 1e-6 and abs(a.y - ty) < 1e-6:
            st["phase"] = "train"
            st["i"] += 1
            return [{"command": "BUILD", "army_id": a.id, "x": tx, "y": ty, "size": size}]
        return []
    w, cfg = make_world()
    hist = run(w, cfg, max_turns, script, log_every=max_turns)
    t, s, towns, armies = hist[-1]
    return round(s, 1), [(i, round(p, 1)) for i, p in towns]


def cycle_boost(size=50.0, floor=450.0, max_turns=10000):
    """Repeat: train `size` when mother >= floor; boost smallest colony, else pioneer @20km E."""
    st = {"phase": "train", "mode": None, "tx": 520.0, "pia": 0}

    def script(t, w):
        mother = next((x for x in w.towns if x.id == 0), None)
        if mother is None:
            return []
        cols = [x for x in w.towns if x.id != 0]
        if st["phase"] == "train":
            if mother.population < max(floor, size + 200):
                return []
            small = [c for c in cols if c.population < 150]
            if small:
                c = min(small, key=lambda c: c.population)
                st.update(mode="boost", tx=c.x, ty=c.y)
            else:
                st.update(mode="pioneer", tx=500.0 + 20.0 * (st["pia"] + 1), ty=500.0)
                st["pia"] += 1
            st["phase"] = "march"
            return [{"command": "TRAIN", "town_id": 0, "size": size}]
        a = wait_army(w)
        if a is None:
            return []
        if st["phase"] == "march":
            st["phase"] = "build"
            return [{"command": "MOVE_TO", "army_id": a.id, "to_x": st["tx"], "to_y": st["ty"], "amount": 0.0}]
        if st["phase"] == "build" and abs(a.x - st["tx"]) < 1e-6 and abs(a.y - st["ty"]) < 1e-6:
            st["phase"] = "train"
            return [{"command": "BUILD", "army_id": a.id, "x": st["tx"], "y": st["ty"], "size": size}]
        return []
    w, cfg = make_world()
    hist = run(w, cfg, max_turns, script, log_every=max_turns)
    t, s, towns, armies = hist[-1]
    return round(s, 1), [(i, round(p, 1)) for i, p in towns]


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "N":
        for n in (2, 4, 6, 10):
            s, towns = found_ring(n)
            print(f"N={n}: score={s} towns={towns}", flush=True)
    elif mode == "CAD":
        for size, floor in ((50.0, 500.0), (50.0, 450.0), (30.0, 400.0), (30.0, 350.0)):
            s, towns = cycle_boost(size, floor)
            print(f"size={size} floor={floor}: score={s} towns={towns}", flush=True)
