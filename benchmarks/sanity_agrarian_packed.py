"""Packing-aware town-size check.

Hex lattice spacing 10 km (cell 86.6 km2 > ring 78.5, no crowding),
sites within 58 km of the centre (inside 60 km carting reach).
One town at the centre (or none), villages at every other site.
Single-turn rates (services resolve in-turn).
"""
import math, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.config import GameConfig
from engine.economy import _step_core
from engine.world import Town, World
CFG = GameConfig()
S = 10.0  # hex spacing, km

def sites(rmax=58.0):
    pts=[]
    j=0
    while True:
        y=j*S*math.sqrt(3)/2
        if y>rmax: break
        off=(S/2 if j%2 else 0.0)
        i=0
        while True:
            x=off+i*S
            if x>rmax: break
            if math.hypot(x,y)<=rmax:
                pts.append((x,y)); pts.append((-x,y))
                if x: pts.append((x,-y)); pts.append((-x,-y))
            i+=1
        j+=1
    # dedupe and keep inside
    seen=set(); out=[]
    for x,y in pts:
        k=(round(x,3),round(y,3))
        if k in seen: continue
        seen.add(k)
        if math.hypot(x,y)<=rmax: out.append((500+x,500+y))
    out.sort(key=lambda p:(p[0]-500)**2+(p[1]-500)**2)
    return out

SITES = sites()
print(f"non-crowding sites within 58 km: {len(SITES)} (rings {math.pi*25:.0f} km2, cell {S*S*math.sqrt(3)/2:.0f})")

def rate(town_pop, village_pop):
    spec=[(500.0,500.0,town_pop)] if town_pop else []
    sites=SITES[1:] if town_pop else SITES
    nv=len(sites)
    spec += [(x,y,village_pop) for x,y in sites]
    towns=[Town(id=i,faction=0,x=x,y=y,population=p,is_capital=(i==0))
           for i,(x,y,p) in enumerate(spec)]
    total=sum(t.population for t in towns)
    n2,_s2=_step_core(towns,[1000,1000],CFG)
    g=(sum(n2)-total)/total*52.0*100.0
    town_net=(n2[0]-towns[0].population) if town_pop else 0.0
    return g, total, town_net, nv

for village in (300.0, 1800.0):
    print(f"-- villages at {village:.0f}, {len(SITES)} sites, one town replaces a site")
    town_list = (0.0, 2400.0, 4800.0, 9600.0, 14400.0, 24000.0) if village < 1000 \
        else (0.0, 2400.0, 4800.0, 9600.0, 24000.0, 48000.0)
    for town in town_list:
        g,total,tn,nv = rate(town, village)
        print(f"   town {town:7.0f}  villages {nv:3d}  total {total:8.0f}  "
              f"growth {g:+.4f}%/yr  town net {tn:+8.1f}")
