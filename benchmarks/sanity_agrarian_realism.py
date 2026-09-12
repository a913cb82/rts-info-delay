"""Which market_scaling gives the most realistic hierarchy for 100k?

Search the hierarchy lattice space per (gamma, premium); score the
growth-best config (and the best realism-competitive one) against the
1600s anchors.
"""
import math, sys
from pathlib import Path
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sanity_agrarian_levels as sl

Q = {
 2: [((2,),(2,)),((2,),(4,)),((3,),(2,)),((3,),(4,)),((4,),(2,)),((4,),(4,)),((5,),(2,)),((5,),(4,))],
 3: [((2,2),(2,2)),((2,2),(2,4)),((3,2),(2,2)),((3,3),(2,2)),((3,3),(2,4)),((3,3),(3,3)),((4,4),(2,2)),((4,4),(2,4)),((4,4),(3,3)),((4,5),(2,2)),((5,5),(2,2))],
 4: [((3,3,3),(2,2,2)),((3,3,3),(2,2,4)),((4,4,4),(2,2,2)),((4,4,4),(2,3,3)),((4,4,5),(2,2,2)),((5,5,5),(2,2,2))],
}

def band(x, lo, hi, f=0.6):
    if lo <= x <= hi: return 1.0
    if x < lo: return max(0.0, 1.0 - (lo - x) / (f * lo))
    return max(0.0, 1.0 - (x - hi) / (f * hi))

def shape(s_v, qs, ms, pv, n):
    sizes=[]; spac=[]; z=1.0; zq=1.0
    sizes.append(pv); spac.append(s_v)
    for m,q in zip(ms,qs):
        z*=m; zq*=q; sizes.append(pv*z); spac.append(s_v*zq)
    while len(n)<len(sizes): n.append(0)
    occ=[t for t in range(len(sizes)) if n[t]>0]
    top=max(sizes[t] for t in occ)
    # median settlement size (weighted)
    vals=[]
    for t in occ: vals += [sizes[t]]*int(n[t])
    vals.sort(); med=vals[len(vals)//2]
    cell=(math.sqrt(3)/2)*s_v*s_v
    return dict(sizes=sizes,n=n,spac=spac,top=top,med=med,
                region=n[0]*cell, urban=100*(1-n[0]*pv/100000.0))

def realism(sh):
    occ=[t for t in range(len(sh["sizes"])) if sh["n"][t]>0]
    v=sh["sizes"][0]
    scores=[]
    scores.append(band(v,150,400))
    scores.append(band(sh["spac"][0],2,5))
    if 1 in occ or len(occ)>1:
        t1=occ[1] if occ[1]==1 else min(t for t in occ if t>=1)
        scores.append(band(sh["sizes"][t1],300,1500))
        scores.append(band(sh["spac"][t1],10,20))
        scores.append(band(sh["n"][t1],10,20))
    scores.append(band(sh["top"],5000,10000))
    scores.append(band(sh["urban"],8,12))
    scores.append(band(sh["region"],2500,4000))
    scores.append(band(sh["top"]/sh["med"],5,50))
    return sum(scores)/len(scores), len(scores)

def search(gamma,prem):
    sl.CFG=replace(sl.CFG,market_scaling=gamma,market_premium=prem)
    rows=[]
    def add(s_v,qs,ms,L):
        r=sl.evaluate(s_v,qs,ms)
        if r:
            g,u,pv,n=r
            rows.append((g,shape(s_v,qs,ms,pv,list(n)),s_v,qs,ms,L))
    for s_v in (3.0,4.0,5.0):
        add(s_v,(),(),1)
        for q,m in Q[2]: add(s_v,q,m,2)
        for q,m in Q[3]: add(s_v,q,m,3)
        for q,m in Q[4]: add(s_v,q,m,4)
    rows.sort(key=lambda r:r[0],reverse=True)
    best_growth=rows[0]
    competitive=[r for r in rows if r[0]>=0.98*best_growth[0]]
    best_real=max(competitive,key=lambda r:realism(r[1])[0])
    return best_growth,best_real,realism(best_growth[1])[0],realism(best_real[1])[0]

print(f"{'gamma':>5} {'prem':>5} {'best-growth':>12} {'real':>5} | {'best realism-competitive':>24} {'real':>5}  shape")
for prem in (0.25,0.5):
    for gamma in (1.0,1.1,1.15,1.2,1.3,1.5,2.0,3.0):
        bg,br,sg,sr=search(gamma,prem)
        def fmt(r):
            g,sh,s_v,qs,ms,L=r
            return f"L{L} {g:+.4f} u{sh['urban']:.0f}%"
        sh=br[1]
        occ=[t for t in range(len(sh['sizes'])) if sh['n'][t]>0]
        print(f"{gamma:5.2f} {prem:5.2f} {fmt(bg):>12} {sg:5.2f} | "
              f"{fmt(br):>24} {sr:5.2f}  sizes={[round(sh['sizes'][t]) for t in occ]} "
              f"counts={[sh['n'][t] for t in occ]} spac={[round(sh['spac'][t]) for t in occ]}")
