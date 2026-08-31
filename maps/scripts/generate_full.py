"""Generate full.json — two-grid organic placement with tunable kernel.

Tunables at top:
  GRID_LARGE, GRID_SMALL, JITTER, KERNEL_SIGMA, POP_POWER, EQUILIBRIUM_THRESHOLD

Visualizes growth as +/- on PNG (green + for growing, red - for shrinking).
Faction assignment by proximity, then rebalance border for equal pop.
"""

import json, math, random, sys
import numpy as np
sys.path.insert(0, "src")
from engine.config import GameConfig

MAP_SIZE = 1000
N_FACTIONS = 5
RANDOM_SEED = 42

# ── Tunables ──────────────────────────────────────────────────────────
GRID_LARGE = 80          # large towns grid spacing (km)
GRID_SMALL = 40          # villages grid spacing (km)
JITTER_LARGE = 14
JITTER_SMALL = 10
KERNEL_SIGMA_CELLS = 3.0   # for density grid visualization (not placement)
POP_POWER = 0.55           # pop**POP_POWER for density contribution
EQUILIBRIUM_THRESHOLD = 120

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

def faction_centers():
    R=280
    return [(500 + R*math.cos(math.radians(90+i*72)), 500+R*math.sin(math.radians(90+i*72))) for i in range(N_FACTIONS)]

def nearest_fi(x,y, centers):
    return min(range(len(centers)), key=lambda i: math.hypot(x-centers[i][0], y-centers[i][1]))

def generate_map():
    centers = faction_centers()
    settlements=[]  # (x,y,pop,fi)

    # Layer 1: large/medium on coarse grid
    for x in range(25, MAP_SIZE, GRID_LARGE):
        for y in range(25, MAP_SIZE, GRID_LARGE):
            fi = nearest_fi(x, y, centers)
            cx,cy = centers[fi]
            dist = math.hypot(x-cx, y-cy)
            if dist < 120: pop = 8000
            elif dist < 200: pop = 3000
            elif dist < 300: pop = 1500
            elif dist < 400: pop = 800
            else: pop = 500
            # jitter
            jx = x + random.uniform(-JITTER_LARGE, JITTER_LARGE)
            jy = y + random.uniform(-JITTER_LARGE, JITTER_LARGE)
            jx = float(np.clip(jx, 5, MAP_SIZE-5)); jy=float(np.clip(jy,5,MAP_SIZE-5))
            settlements.append((jx,jy,pop,fi))

    # Place capitals at pop-weighted center
    for fi in range(N_FACTIONS):
        ft=[(x,y,p) for x,y,p,f in settlements if f==fi]
        tp=sum(p for _,_,p in ft)
        if tp>0:
            px=sum(x*p for x,y,p in ft)/tp
            py=sum(y*p for _,y,p in ft)/tp
            best=None; best_d=float('inf')
            for i,(x,y,p,f) in enumerate(settlements):
                if f==fi and p>5000:
                    d=math.hypot(x-px,y-py)
                    if d<best_d: best_d=d; best=i
            if best is not None:
                x,y,_,_ = settlements[best]
                settlements[best]=(x,y,50000,fi)

    # Layer 2: villages on fine grid, filling gaps between large settlements
    large_pos={(int(x//GRID_SMALL), int(y//GRID_SMALL)) for x,y,_,_ in settlements}
    for x in range(25, MAP_SIZE, GRID_SMALL):
        for y in range(25, MAP_SIZE, GRID_SMALL):
            gx,gy=int(x//GRID_SMALL), int(y//GRID_SMALL)
            if (gx,gy) not in large_pos:
                fi=nearest_fi(x,y, centers)
                jx=x+random.uniform(-JITTER_SMALL,JITTER_SMALL)
                jy=y+random.uniform(-JITTER_SMALL,JITTER_SMALL)
                jx=float(np.clip(jx,5,MAP_SIZE-5)); jy=float(np.clip(jy,5,MAP_SIZE-5))
                settlements.append((jx,jy,500,fi))

    # Reassign border settlements for equal pop
    for _ in range(60):
        pops=[sum(p for _,_,p,f in settlements if f==fi) for fi in range(N_FACTIONS)]
        target=sum(pops)/N_FACTIONS
        richest=max(range(N_FACTIONS), key=lambda i: pops[i])
        poorest=min(range(N_FACTIONS), key=lambda i: pops[i])
        if pops[richest] < target*1.08: break
        best=None; best_d=float('inf')
        for i,(x,y,p,fi) in enumerate(settlements):
            if fi!=richest or p>=40000: continue
            d_poor=math.hypot(x-centers[poorest][0], y-centers[poorest][1])
            d_rich=math.hypot(x-centers[richest][0], y-centers[richest][1])
            if d_poor > d_rich: continue
            if d_poor < best_d: best_d=d_poor; best=i
        if best is None: break
        x,y,p,_ = settlements[best]
        settlements[best]=(x,y,p,poorest)

    # Randomize populations within bands (more random, not distance-based)
    # Keep capitals 50k, randomize others in logspace
    final=[]
    for x,y,pop,fi in settlements:
        if pop>=40000:
            final.append((x,y,50000,fi))
        else:
            # logspace 400..18000, with jitter
            lp = random.uniform(math.log10(400), math.log10(18000))
            npop = int(10**lp)
            npop = max(400, round(npop/100)*100 if npop<1000 else round(npop/500)*500)
            final.append((x,y,npop,fi))
    return final

def settlements_to_csv(settlements):
    lines=["x,y,type,population"]
    for fi in range(N_FACTIONS):
        ft=[(x,y,p,f) for x,y,p,f in settlements if f==fi]
        ft.sort(key=lambda t: -t[2])
        for x,y,pop,f in ft:
            lines.append(f"{x:.1f},{y:.1f},{chr(65+f)},{pop}")
    return "\n".join(lines)+"\n"

def check_all(settlements):
    print(f"\nTotal {len(settlements)}")
    filled=set((int(x//50),int(y//50)) for x,y,_,_ in settlements)
    print(f"  Gaps {(400-len(filled))/400*100:.1f}%")
    # quick equilibrium via engine
    from engine.world import World
    from engine.step import step
    from engine.ledger import Ledger
    csv=settlements_to_csv(settlements)
    cfg=GameConfig(); cfg.map=csv; cfg.map_size=[MAP_SIZE,MAP_SIZE]
    w=World(); w.map_size=[MAP_SIZE,MAP_SIZE]; w.parse_map(csv)
    pops={(t.id,t.faction): t.population for t in w.towns}
    ledger=Ledger(cfg.info_speed, math.hypot(MAP_SIZE,MAP_SIZE))
    for turn in range(1,21):
        step(w,cfg,ledger,turn=turn,orders={})
    max_abs=max(abs(t.population - pops.get((t.id,t.faction), t.population)) for t in w.towns) if w.towns else 0
    print(f"  Equilibrium max_abs {max_abs:.0f} {'OK' if max_abs<EQUILIBRIUM_THRESHOLD else 'FAIL'}  GRID_LARGE={GRID_LARGE} GRID_SMALL={GRID_SMALL} POP_POWER={POP_POWER}")
    return max_abs < EQUILIBRIUM_THRESHOLD

def render_png(settlements, filename="maps/full_preview.png"):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("PIL missing")
        return
    csv=settlements_to_csv(settlements)
    from engine.world import World
    from engine.step import step
    from engine.ledger import Ledger
    cfg=GameConfig(); cfg.map=csv; cfg.map_size=[MAP_SIZE,MAP_SIZE]
    w=World(); w.map_size=[MAP_SIZE,MAP_SIZE]; w.parse_map(csv)
    init={(t.id,t.faction): t.population for t in w.towns}
    ledger=Ledger(cfg.info_speed, math.hypot(MAP_SIZE,MAP_SIZE))
    for turn in range(1,11):
        step(w,cfg,ledger,turn=turn,orders={})
    final={(t.id,t.faction): t.population for t in w.towns}
    img=Image.new("RGB",(MAP_SIZE,MAP_SIZE),(200,220,200))
    draw=ImageDraw.Draw(img)
    for x in range(0,MAP_SIZE,50):
        draw.line([(x,0),(x,MAP_SIZE)], fill=(180,200,180))
    for y in range(0,MAP_SIZE,50):
        draw.line([(0,y),(MAP_SIZE,y)], fill=(180,200,180))
    colors=[(220,60,60),(60,120,220),(60,180,60),(220,160,40),(180,60,180)]
    for x,y,pop,fi in settlements:
        # find growth for this settlement (match by pos)
        growth=0
        for t in w.towns:
            if abs(t.x-x)<1 and abs(t.y-y)<1:
                ini=init.get((t.id,t.faction), t.population)
                growth=t.population - ini
                break
        r=6 if pop>=40000 else 4 if pop>=5000 else 3 if pop>=1000 else 2
        col=colors[fi%len(colors)]
        draw.ellipse([x-r,y-r,x+r,y+r], fill=col, outline=(0,0,0))
        if abs(growth) > 5:
            draw.text((x+r+1, y-r), "+" if growth>0 else "-", fill=(0,150,0) if growth>0 else (200,0,0))
    for fi,(cx,cy) in enumerate(faction_centers()):
        draw.text((cx-4,cy-4), str(fi), fill=(0,0,0))
    img.save(filename)
    print(f"PNG {filename}")

if __name__=="__main__":
    settlements=generate_map()
    check_all(settlements)
    render_png(settlements)
    csv=settlements_to_csv(settlements)
    cfg={
        "map": csv.rstrip("\n"),
        "map_size":[MAP_SIZE,MAP_SIZE],
        "max_turns":500,
        "info_speed":150.0,"army_speed":50.0,"army_cost":1000,
        "interact_radius":10.0,"population_cap":100000.0,
        "population_growth":0.001,"build_efficiency":0.5,
        "equilibrium_spacing":0.1,"crowding_decay":0.8,"crowding_asymmetry":0.01,
    }
    import json
    with open("maps/full.json","w") as f: json.dump(cfg,f,indent=2)
    print(f"Wrote maps/full.json ({len(settlements)} settlements)")
