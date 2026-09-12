import sys
from pathlib import Path
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sanity_agrarian_levels as sl
sl.TOTAL = 1_000_000.0
sl.CFG = replace(sl.CFG, market_scaling=1.15, market_premium=0.5)
for s_v in (3.5, 3.0):
    for qs,ms in [((),()),
                  ((4,),(2,)), ((4,),(4,)),
                  ((4,4),(2,3)), ((4,4),(2,6)),
                  ((4,4,4),(2,3,3)), ((4,4,4),(2,2,5)),
                  ((5,5,5),(2,2,5))]:
        r=sl.evaluate(s_v,qs,ms,n_target=3000)
        if r is None: continue
        g,urban,pv,n=r
        sizes=[pv]; spac=[s_v]; z=1.0; zq=1.0
        for m,q in zip(ms,qs):
            z*=m; zq*=q; sizes.append(pv*z); spac.append(s_v*zq)
        while len(n)<len(sizes): n.append(0)
        occ=[t for t in range(len(sizes)) if n[t]>0]
        print(f"s_v={s_v} q={qs} m={ms}: {g:+.4f}%/yr urban {urban:4.1f}%  "
              f"sizes {[round(sizes[t]) for t in occ]}  counts {[n[t] for t in occ]}  "
              f"spac {[round(spac[t]) for t in occ]}")
