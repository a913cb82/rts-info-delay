"""Hierarchy test: 1 primary town + n secondary towns + villages.

100k total. Sites on a 10 km hex lattice. 'compact' = villages nearest
the towns; 'spread' = villages fill from the centre outward (so a thin
countryside sits beyond one town's 60 km reach). Two-turn rates.
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.economy import GameConfig, _step_core
from engine.world import Town
CFG = GameConfig(); TOTAL = 100_000.0; S = 10.0

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

def run(T1, n2, T2, Pt, mode, r2=42.0):
    urban = T1 + n2*T2
    n_v = max(1, round((TOTAL-urban)/Pt)); P = (TOTAL-urban)/n_v
    rmax = math.sqrt((n_v+n2+1)*90/math.pi)+12
    sl = sites(rmax)
    towns=[sl[0]]
    for k in range(n2):
        ang = 2*math.pi*k/max(n2,1) + 0.35
        tx, ty = r2*math.cos(ang), r2*math.sin(ang)
        cand = [p for p in sl if p not in towns]
        towns.append(min(cand, key=lambda p:(p[0]-tx)**2+(p[1]-ty)**2))
    if mode == "compact":
        def key(p): return min(math.hypot(p[0]-q[0],p[1]-q[1]) for q in towns)
    else:
        def key(p): return math.hypot(p[0],p[1])
    vill = sorted((p for p in sl if p not in towns), key=key)[:n_v]
    spec=[(towns[i][0],towns[i][1], T1 if i==0 else T2) for i in range(len(towns))]
    spec += [(x,y,P) for x,y in vill]
    tw=[Town(id=i,faction=0,x=500+x,y=500+y,population=p,is_capital=(i==0))
        for i,(x,y,p) in enumerate(spec)]
    tot=sum(t.population for t in tw)
    n2_,_ = _step_core(tw,[1000,1000],CFG)
    return (sum(n2_)-tot)/tot*52*100, P, len(towns)

for mode in ("compact","spread"):
    print(f"== {mode}")
    best=[]
    for T1 in (9600.0,):
        for n2,T2 in [(0,0),(2,2400),(2,4800),(3,5000),(4,2400),(4,4800),(6,2400)]:
            for Pt in (300.0,600.0,900.0):
                if T1+n2*T2 >= TOTAL: continue
                g,P,nt = run(T1,n2,T2,Pt,mode)
                best.append((g,n2,T2,Pt,P,nt))
    best.sort(reverse=True)
    for g,n2,T2,Pt,P,nt in best[:6]:
        print(f"   {nt} towns (1x{T1:.0f}+{n2}x{T2:.0f})  village {P:5.0f}  -> {g:+.4f}%/yr")
    print("   ... user's example 1x10000+3x5000:", end=" ")
    for Pt in (600.0,900.0):
        g,P,nt = run(10000.0,3,5000.0,Pt,mode)
        print(f"P_v {P:5.0f} {g:+.4f}%/yr", end="  ")
    print()
