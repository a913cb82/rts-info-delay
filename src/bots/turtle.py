"""Turtle — hunkers down, garrisons, shy build. Pure function."""

from __future__ import annotations
import json, math, sys
from engine.config import GameConfig
from engine.world import World
from .common import _busy, _hash, _own, _site, _world, _can_train


def decide_orders(world: World, faction: int, config: GameConfig) -> list[str]:
    view = {
        "faction": faction,
        "armies": [{"id": a.id, "faction": a.faction, "x": a.x, "y": a.y, "has_target": a.has_target, "target_x": a.target_x, "target_y": a.target_y} for a in world.armies],
        "towns": [{"id": t.id, "faction": t.faction, "x": t.x, "y": t.y, "population": t.population, "is_capital": t.is_capital} for t in world.towns],
        "turn": getattr(world, "_turn", 0),
    }
    f = _world(view)
    out: list[str] = []
    busy = _busy(f)
    own_towns = [t for t in f["towns"] if t["faction"] == faction]
    own_armies = [a for a in f["armies"] if a["faction"] == faction]
    enemies = [a for a in f["armies"] if a["faction"] != faction]

    # TRAIN — very conservative (peak-aware + high bar)
    for t in own_towns:
        if t["id"] in busy:
            continue
        wt = next((x for x in world.towns if x.id == t["id"]), None)
        pop = wt.population if wt else t["population"]
        if _can_train(pop, config, conservative=True) and pop >= 3000:
            out.append(f"TRAIN {t['id']}")

    # Shy build: only when every own town >= 1500 and pop outside peak, only strongest idle, clustered tight
    all_calm = all((next((w.population for w in world.towns if w.id == t["id"]), 500) >= 1500) for t in own_towns) if own_towns else False
    # also need outside peak for calm
    all_calm = all_calm and all(not (35000 <= next((w.population for w in world.towns if w.id == t["id"]), 0) <= 65000) for t in own_towns) if own_towns else False

    idle = [p for p in own_armies if p["id"] not in busy]

    # If not calm, keep garrison: idle armies move to nearest own town
    if not all_calm and idle and own_towns:
        for p in idle:
            # nearest own town
            t = min(own_towns, key=lambda t: math.hypot(t["x"]-p["x"], t["y"]-p["y"]))
            out.append(f"MOVE_TO {p['id']} {p['x']:.1f} {p['y']:.1f} {t['x']:.1f} {t['y']:.1f}")
        return out

    # Shy build: one builder, tight around biggest town
    if all_calm and idle and own_towns:
        # biggest by pop
        big = max(own_towns, key=lambda t: next((w.population for w in world.towns if w.id == t["id"]), 0))
        # strongest idle
        g = max(idle, key=lambda p: 1)  # all equal strength in min, use id
        x, y = _site(f.get("turn", 0), g["id"], config, own_towns, salt=17, rmin=40, rmax=100, around=big)
        out.append(f"BUILD {g['id']} {x:.1f} {y:.1f}")
        idle = [p for p in idle if p["id"] != g["id"]]
        # remaining idle keep garrison
        for p in idle:
            t = min(own_towns, key=lambda t: math.hypot(t["x"]-p["x"], t["y"]-p["y"]))
            out.append(f"MOVE_TO {p['id']} {p['x']:.1f} {p['y']:.1f} {t['x']:.1f} {t['y']:.1f}")
        return out

    # Otherwise garrison already handled
    return out


def _read_startup():
    import json, sys
    from engine.config import GameConfig
    cfg = GameConfig(); fac = 0
    for line in sys.stdin:
        line=line.strip()
        if not line: continue
        if line.startswith("config "):
            try: cfg = GameConfig.from_dict(json.loads(line[7:]))
            except: pass
        elif line.startswith("faction "):
            try: fac = int(line.split()[1])
            except: pass
        elif line == "go": break
        elif line.startswith("end "): sys.exit(0)
    return cfg, fac

def _read_turn():
    import json, sys
    turn=None; ev=[]
    for line in sys.stdin:
        line=line.strip()
        if not line: continue
        if line.startswith("turn "):
            try: turn=int(line.split()[1])
            except: turn=0
        elif line=="go":
            if turn is not None: return turn, ev
        elif line.startswith("end "): return -1, []
        elif line.startswith("{"):
            try: ev.append(json.loads(line))
            except: pass
        else:
            try: ev.append(json.loads(line))
            except: pass
    return None

def main():
    cfg, faction = _read_startup()
    world = World(); world.map_size=cfg.map_size
    if cfg.map: world.parse_map(cfg.map)
    while True:
        r=_read_turn()
        if r is None: break
        turn,events=r
        if turn==-1: break
        world._turn=turn
        for ev in events:
            k=ev.get("kind")
            if k=="army_spawn":
                if any(a.id==ev.get("id") for a in world.armies): continue
                from engine.world import Army
                a=Army(id=ev.get("id"), faction=ev.get("faction",faction), x=ev.get("x",0), y=ev.get("y",0), is_fresh=True)
                a.is_viceroy=ev.get("is_viceroy",False)
                world.armies.append(a)
            elif k=="town_spawn":
                if any(t.id==ev.get("id") for t in world.towns): continue
                from engine.world import Town
                t=Town(id=ev.get("id"), faction=ev.get("faction",faction), x=ev.get("x",0), y=ev.get("y",0), population=ev.get("population",500), is_capital=ev.get("is_capital",False))
                world.towns.append(t)
            elif k=="army_move":
                a=world.get_army(ev.get("id"))
                if a: a.x,a.y=ev.get("x",a.x),ev.get("y",a.y)
            elif k=="army_death": world.remove_army(ev.get("id"))
            elif k=="town_death": world.remove_town(ev.get("id"))
        orders=decide_orders(world,faction,cfg)
        for o in orders: sys.stdout.write(o+"\n")
        sys.stdout.write("go\n"); sys.stdout.flush()

if __name__=="__main__": main()
