"""Expander — colonizer, not fighter. Pure function, deterministic."""

from __future__ import annotations

import json, math, sys
from engine.config import GameConfig
from engine.world import World
try:
    from .common import _busy, _hash, _own, _site, _world, _enemies, _can_train
except ImportError:
    from bots.common import _busy, _hash, _own, _site, _world, _enemies, _can_train


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
    # Expander is conservative about peak: don't TRAIN towns in 35k-65k
    for t in own_towns:
        if t["id"] in busy:
            continue
        wt = next((x for x in world.towns if x.id == t["id"]), None)
        pop = wt.population if wt else t["population"]
        if _can_train(pop, config, conservative=True):
            out.append(f"TRAIN {t['id']}")

    cap = next((t for t in own_towns if t.get("is_capital")), None) or ({"x": config.map_size[0]/2, "y": config.map_size[1]/2})
    enemies = [a for a in f["armies"] if a["faction"] != faction]

    for p in [a for a in f["armies"] if a["faction"] == faction]:
        if p["id"] in busy:
            continue
        h = _hash(f.get("turn", 0), p["id"], 3)
        d = 120 + (h % 4) * 40  # 120,160,200,240 — tuned for crowding: >100 keeps villages out of 10km, <300 keeps cities within info_speed
        x, y = _site(f.get("turn", 0), p["id"], config, own_towns, salt=3, rmin=d, rmax=d+40, around=cap)
        # Skip BUILD if an enemy army is within info_speed of the site — don't front-line
        if any(math.hypot(e["x"] - x, e["y"] - y) < config.info_speed for e in enemies):
            # Tour a low-pop own town instead (heal by visiting)
            low = [t for t in own_towns if (next((w for w in world.towns if w.id == t["id"]), None) or t).get("population", 0) < 2000 and not t.get("is_capital")]
            # Simplified: just pick smallest pop town
            candidates = [t for t in own_towns if not t.get("is_capital")]
            if candidates:
                # find actual World town for pop check
                candidates = sorted(candidates, key=lambda t: next((w.population for w in world.towns if w.id == t["id"]), 1e9))
                tt = candidates[0]
                out.append(f"MOVE_TO {p['id']} {p['x']:.1f} {p['y']:.1f} {tt['x']:.1f} {tt['y']:.1f}")
            continue
        out.append(f"BUILD {p['id']} {x:.1f} {y:.1f}")
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
            elif k=="battle": pass
            elif k=="town_death": world.remove_town(ev.get("id"))
            # also handle Town population updates via world events? keep as is
            if k=="town_spawn" or k=="town_death":
                # ensure capital tracking
                pass
        # Apply town population from world.towns if events include it? we keep world as is
        orders=decide_orders(world,faction,cfg)
        for o in orders: sys.stdout.write(o+"\n")
        sys.stdout.write("go\n"); sys.stdout.flush()

if __name__=="__main__": main()
