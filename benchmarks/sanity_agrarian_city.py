"""Equal-population city-system test: 20,400 people as N villages
and/or one city, all within carting range (<=60 km)."""
import json, math, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.config import GameConfig
from engine.economy import apply_growth
from engine.world import Town, World
CFG = GameConfig()
TURNS = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
OUT = Path(f"/tmp/agrarian_city_{TURNS}.jsonl"); OUT.unlink(missing_ok=True)
TOTAL = 20400.0

def run(name, spec):
    w = World(); w.map_size=[1000,1000]
    w.towns=[Town(id=i,faction=0,x=float(x),y=float(y),population=float(p),is_capital=(i==0))
             for i,(x,y,p) in enumerate(spec)]
    p0=sum(t.population for t in w.towns); t0=time.perf_counter()
    for _ in range(TURNS): apply_growth(w, CFG)
    pops=sorted((t.population for t in w.towns), reverse=True)
    tot=sum(pops)
    res={"name":name,"p0":p0,"total":round(tot,1),
         "growth_pct_per_yr":round(((tot/p0)**(52.0/TURNS)-1)*100,4),
         "n":len(pops),"top":[round(p) for p in pops[:3]],"median":round(pops[len(pops)//2]),
         "elapsed_s":round(time.perf_counter()-t0,1)}
    with OUT.open("a") as f: f.write(json.dumps(res)+"\n")
    print(f"{name:22s} n={res['n']:3d} total {res['total']:8.0f} ({res['growth_pct_per_yr']:+.4f}%/yr) top {res['top']} med {res['median']} ({res['elapsed_s']}s)", flush=True)

def villages(n, pop):
    return [(500+55*math.sqrt((i+0.5)/n)*math.cos(i*2.39996),
             500+55*math.sqrt((i+0.5)/n)*math.sin(i*2.39996), pop) for i in range(n)]

def main():
    run("68_villages", villages(68, TOTAL/68))
    run("1v2400+60villages", [(500,500,2400.0)] + villages(60, (TOTAL-2400)/60))
    run("1v4800+52villages", [(500,500,4800.0)] + villages(52, (TOTAL-4800)/52))
    run("1v8400+40villages", [(500,500,8400.0)] + villages(40, (TOTAL-8400)/40))
    run("1v12000+28villages", [(500,500,12000.0)] + villages(28, (TOTAL-12000)/28))
    run("1_city_20400", [(500,500,TOTAL)])
    print(f"jsonl: {OUT}")
main()
