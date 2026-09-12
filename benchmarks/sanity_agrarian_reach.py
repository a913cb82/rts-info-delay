"""Market reach vs settlement pattern: 100k people, hex lattice.

Reach factor 3 (60 km, current default) vs 1 (20 km = one carting
price-doubling, the 1600s day-return marketing shed). Towns spread by
farthest-point sampling; villages are the sites nearest a town.
Two-turn per-capita rate.
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import engine.economy as eco
from engine.world import Town
CFG = eco.GameConfig(); TOTAL = 100_000.0; S = 10.0

def sites(rmax):
    out=[]; j=0
    while j*S*math.sqrt(3)/2 <= rmax:
        y=j*S*math.sqrt(3)/2; off=(S/2 if j%2 else 0.0); i=0
        while off+i*S <= rmax:
            x=off+i*S
            for sx in ((1,-1) if x else (1,)):
                for sy in ((1,-1) if y else (1,)):
                    if math.hypot(x,y)<=rmax: out.append((sx*x,sy*y))
            i+=1
        j+=1
    seen=set(); u=[]
    for p in out:
        k=(round(p[0],3),round(p[1],3))
        if k not in seen: seen.add(k); u.append(p)
    c=min(u,key=lambda p:math.hypot(*p)); u.remove(c); u.insert(0,c)
    return u

def spread(sl,n):
    ch=[sl[0]]
    while len(ch)<n:
        best=None; bd=-1
        for p in sl:
            if p in ch: continue
            d=min(math.hypot(p[0]-q[0],p[1]-q[1]) for q in ch)
            if d>bd: bd=d; best=p
        ch.append(best)
    return ch

def rate(n_t,T,P_target,reach):
    eco._TRADE_REACH_FACTOR = reach
    n_v=max(1,round((TOTAL-n_t*T)/P_target)); P=(TOTAL-n_t*T)/n_v
    sl=sites(math.sqrt((n_v+n_t)*90/math.pi)+12)
    towns=spread(sl,n_t) if n_t else []
    def dmin(p): return min((math.hypot(p[0]-q[0],p[1]-q[1]) for q in towns), default=1e9)
    vill=sorted((p for p in sl if p not in towns), key=dmin)[:n_v]
    spec=[(500.0,500.0,T)]*n_t + [(500+x,500+y,P) for x,y in vill]
    towns_l=[Town(id=i,faction=0,x=x,y=y,population=p,is_capital=(i==0))
             for i,(x,y,p) in enumerate(spec)]
    tot=sum(t.population for t in towns_l)
    n2,_=eco._step_core(towns_l,[1000,1000],CFG)
    return (sum(n2)-tot)/tot*52*100, P

for reach,label in [(3.0,"60 km (current)"),(1.0,"20 km (1600s shed)")]:
    print(f"== reach {label}")
    best=[]
    for n_t,T in [(0,0),(1,2400),(2,2400),(4,2400),(9,2400),(16,2400),
                  (4,4800),(9,4800),(1,9600)]:
        if n_t*T>=TOTAL: continue
        for Pt in (300.0,600.0,900.0):
            g,P=rate(n_t,T,Pt,reach)
            best.append((g,n_t,T,Pt,P))
    best.sort(reverse=True)
    for g,n_t,T,Pt,P in best[:6]:
        print(f"   {n_t:2d} towns x {T:5.0f}  village {P:5.0f}  -> {g:+.4f}%/yr")
