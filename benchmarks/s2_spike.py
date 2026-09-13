"""S2 spike-timing: hierarchy spike peak height/timing vs base scale. Idle, same faction."""
import json, math, sys, time
sys.path.insert(0, "src")
from engine.config import GameConfig
from engine.world import World
from engine import step as stepmod

def build_map(center_pop, nvill, vill_pop=300.0):
    lines = ["x,y,type,population", f"500.0,500.0,A,{center_pop}"]
    # concentric rings within carting range; scale counts with nvill
    rings = [(15.0, 0.2), (25.0, 0.3), (35.0, 0.3), (45.0, 0.2)]
    counts = [max(1, round(nvill * f)) for _, f in rings]
    # fix rounding drift
    counts[-1] += nvill - sum(counts)
    for (r, _), n in zip(rings, counts):
        for k in range(n):
            a = 2 * math.pi * k / n + r
            lines.append(f"{500.0 + r * math.cos(a):.2f},{500.0 + r * math.sin(a):.2f},A,{vill_pop}")
    return "\n".join(lines)

def run(center_pop, nvill, turns=10000):
    d = json.loads(open("maps/empty.json").read())
    d["map"] = build_map(center_pop, nvill)
    d["max_turns"] = turns
    cfg = GameConfig.from_dict(d)
    w = World()
    w.map_size = d.get("map_size", [1000, 1000])
    w.parse_map(d["map"])
    t0 = time.perf_counter()
    peak, peakt, traj = 0.0, 0, {}
    for t in range(1, turns + 1):
        stepmod.step(w, cfg, None, t, [])
        if t % 100 == 0 or t == turns:
            s = sum(x.population for x in w.towns)
            traj[t] = round(s, 1)
            if s > peak:
                peak, peakt = s, t
    ctr = max((x.population for x in w.towns), default=0.0)
    vill = sorted((round(x.population, 1) for x in w.towns if abs(x.x - 500) > 1 or abs(x.y - 500) > 1))[:5]
    return {"peak": round(peak, 1), "peakt": peakt, "t10000": traj[turns],
            "center_end": round(ctr, 1), "vill_sample": vill,
            "dt": round(time.perf_counter() - t0, 1), "traj": traj}

scens = {"T5repro(40v+2k)": (2000, 40), "A(80v+4k)": (4000, 80),
         "B(80v+2k)": (2000, 80), "C(20v+2k)": (2000, 20),
         "ctrl-lone2k": (2000, 0)}
for name, (cp, nv) in scens.items():
    r = run(cp, nv)
    tr = r.pop("traj")
    print(f"{name}: peak={r['peak']} @t={r['peakt']} t10000={r['t10000']} "
          f"center_end={r['center_end']} vill_sample={r['vill_sample']} ({r['dt']}s)", flush=True)
    # coarse trajectory every 1000t
    print("  traj:" + "".join(f" t{k}={v}" for k, v in tr.items() if k % 1000 == 0 or k == 10000), flush=True)
