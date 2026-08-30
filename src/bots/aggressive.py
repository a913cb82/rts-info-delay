"""Aggressive — chases nearest enemy town/army, with forecast and TRAIN gate."""

from __future__ import annotations
import json, math, sys
from engine.config import GameConfig
from engine.world import World
try:
    from .common import _busy, _hash, _own, _site, _world, _enemies, _enemy_towns, _forecast_pos, _eta, _can_train
except ImportError:
    from bots.common import _busy, _hash, _own, _site, _world, _enemies, _enemy_towns, _forecast_pos, _eta, _can_train


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
    own_armies = [a for a in f["armies"] if a["faction"] == faction]
    own_towns = [t for t in f["towns"] if t["faction"] == faction]
    cap = next((t for t in own_towns if t.get("is_capital")), None)

    # TRAIN — aggressive but still survive (pop >= 1600)
    for t in own_towns:
        if t["id"] in busy:
            continue
        wt = next((x for x in world.towns if x.id == t["id"]), None)
        pop = wt.population if wt else t["population"]
        if _can_train(pop, config, conservative=False):
            out.append(f"TRAIN {t['id']}")

    # Home guard: strongest army stays within 100 of capital
    guard_id = None
    if own_armies and cap is not None:
        # In min, strength is uniform, so pick first
        guard = own_armies[0]
        guard_id = guard["id"]
        if guard["id"] not in busy and math.hypot(guard["x"]-cap["x"], guard["y"]-cap["y"]) > 100:
            out.append(f"MOVE_TO {guard['id']} {guard['x']:.1f} {guard['y']:.1f} {cap['x']:.1f} {cap['y']:.1f}")

    # Build Enemy view with forecast: roll enemy armies forward 1 turn (eta to us)
    forecast_enemies = []
    for e in [a for a in f["armies"] if a["faction"] != faction]:
        # Predict where e will be when we arrive: eta = dist(us, e)/speed
        # For simplicity, forecast 1 turn ahead
        fx, fy = _forecast_pos(e, 1.0, config)
        forecast_enemies.append({**e, "fx": fx, "fy": fy})

    enemy_towns = [t for t in f["towns"] if t["faction"] != faction]
    # Also consider towns from view (stale) — already in f

    for p in own_armies:
        if p["id"] == guard_id:
            continue
        if p["id"] in busy:
            continue
        # Prefer enemy town, else enemy army (forecast pos)
        if enemy_towns:
            # Pick nearest town, but lead the target if it's moving? Towns don't move.
            nearest = min(enemy_towns, key=lambda t: math.hypot(t["x"]-p["x"], t["y"]-p["y"]))
            # Check if any enemy army is near that town (guarded) — if so, maybe hunt army first
            # Simplified: always go to town
            out.append(f"MOVE_TO {p['id']} {p['x']:.1f} {p['y']:.1f} {nearest['x']:.1f} {nearest['y']:.1f}")
        elif forecast_enemies:
            # Hunt weakest forecast enemy
            e = min(forecast_enemies, key=lambda a: 1)  # all equal, pick closest
            e = min(forecast_enemies, key=lambda e: math.hypot(e["fx"]-p["x"], e["fy"]-p["y"]))
            out.append(f"MOVE_TO {p['id']} {p['x']:.1f} {p['y']:.1f} {e['fx']:.1f} {e['fy']:.1f}")
        else:
            # No enemies known: explore via _site
            x, y = _site(f.get("turn",0), p["id"], config, own_towns, salt=19, rmin=80, rmax=250, around=p)
            out.append(f"MOVE_TO {p['id']} {p['x']:.1f} {p['y']:.1f} {x:.1f} {y:.1f}")
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
