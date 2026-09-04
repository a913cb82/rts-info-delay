"""Slower suite (<30s): strategic maps + policy optimum + self-play + Elo lite.

Usage: PYTHONPATH=src .venv/bin/python benchmarks/strategic_bench.py [all|maps|optimum|selfplay|elo]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.config import GameConfig
from runner.main import run_game

ROOT = Path(__file__).resolve().parents[1]
STRAT_DIR = ROOT / "maps" / "strategic"


def play(cfg_dict, teams, record=None):
    cfg = GameConfig.from_dict({k: v for k, v in cfg_dict.items()
                                if k not in ("teams", "focal", "note")})
    py = sys.executable
    bots = {int(f): [py, "-m", f"bots.{name}"] for f, name in teams.items()}
    t0 = time.perf_counter()
    run_game(cfg, bots, Path(record) if record else None)
    return (time.perf_counter() - t0) * 1000


def final_score(record, faction):
    lines = Path(record).read_text().splitlines()
    world = json.loads(lines[-1])["world"]
    return (sum(x["population"] for x in world["towns"] if x["faction"] == faction) +
            1000 * sum(1 for x in world["armies"] if x["faction"] == faction))


def final_holdings(record, faction):
    """(towns, armies) held — score alone can't see founding/scouting."""
    lines = Path(record).read_text().splitlines()
    world = json.loads(lines[-1])["world"]
    return (sum(1 for x in world["towns"] if x["faction"] == faction),
            sum(1 for x in world["armies"] if x["faction"] == faction))


def section_maps():
    print("== strategic maps (focal pro, score) ==")
    total = 0.0
    for path in sorted(STRAT_DIR.glob("*.json")):
        d = json.loads(path.read_text())
        rec = "/tmp/strat_record.jsonl"
        ms = play(d, d["teams"], rec)
        total += ms
        t, a = final_holdings(rec, d["focal"])
        print(f"{path.stem:16} score {final_score(rec, d['focal']):7.0f}  towns {t} armies {a}  {ms:7.0f}ms")
    print(f"-- maps total {total / 1000:.1f}s --")
    return total


def section_optimum():
    """Policy optimum on the longpeace map, in-process (no subprocess bots).

    Policy class: TRAIN when town pop >= theta; found new towns (cap 6) by
    marching idle armies out and BUILDing. Grid over theta x founding.
    Reports the best score = 'policy optimum'; efficiency(bot) = bot/that.
    """
    print("== policy optimum (longpeace, in-process) ==")
    from engine.world import World
    from engine.ledger import Ledger
    from engine.step import step
    d = json.loads((STRAT_DIR / "longpeace.json").read_text())
    cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                if k not in ("teams", "focal", "note")})
    t0 = time.perf_counter()
    best = (0, None)
    results = []
    for theta in (1000, 1500, 2000, 2500, 3000, 4000, 5000, 8000):
        for found in (False, True):
            w = World()
            w.map_size = cfg.map_size
            w.parse_map(cfg.map)
            lg = Ledger(cfg.info_speed, 1414.0)
            targets: dict[int, tuple] = {}
            for t in range(1, cfg.max_turns + 1):
                orders: dict[int, list[str]] = {0: []}
                for town in [x for x in w.towns if x.faction == 0]:
                    if town.population >= theta:
                        orders[0].append(f"TRAIN {town.id}")
                if found:
                    ntowns = sum(1 for x in w.towns if x.faction == 0)
                    for a in [x for x in w.armies if x.faction == 0]:
                        if a.id in targets:
                            tx, ty = targets[a.id]
                            import math
                            if math.hypot(a.x - tx, a.y - ty) < 5:
                                orders[0].append(f"BUILD {a.id} {tx:.0f} {ty:.0f}")
                                del targets[a.id]
                            continue
                        if ntowns < 6:
                            tx, ty = 900.0, 900.0 - len(targets) * 137.0
                            targets[a.id] = (tx, ty)
                            orders[0].append(
                                f"MOVE_TO {a.id} {a.x:.0f} {a.y:.0f} {tx:.0f} {ty:.0f}")
                try:
                    step(w, cfg, lg, turn=t, orders=orders)
                except Exception:
                    break
            score = (sum(x.population for x in w.towns if x.faction == 0) +
                     1000 * sum(1 for x in w.armies if x.faction == 0))
            results.append((theta, found, score))
            if score > best[0]:
                best = (score, (theta, found))
    ms = (time.perf_counter() - t0) * 1000
    for theta, found, score in results:
        print(f"  theta {theta:5} found={int(found)} score {score:7.0f}")
    print(f"-- optimum {best[0]:.0f} {best[1]} in {ms / 1000:.1f}s --")
    return best[0], ms


def section_selfplay():
    print("== self-play (pro vs pro, symmetric) ==")
    total = 0.0
    for name, a_pos, b_pos in (("endgame", ("200,400", "200,600"), ("800,400", "800,600")),
                               ("defense", ("300,500",), ("550,500",))):
        rows = ([f"{p},A,4000" for p in a_pos] + [f"{p},B,4000" for p in b_pos])
        d = {"map": "x,y,type,population\n" + "\n".join(rows),
             "map_size": [1000, 1000], "max_turns": 100,
             "turn_time_ms": 1000, "info_speed": 150.0, "army_speed": 50.0,
             "army_cost": 1000, "interact_radius": 10.0, "population_cap": 100000.0,
             "population_growth": 0.001, "build_efficiency": 0.5,
             "equilibrium_spacing": 0.1, "crowding_decay": 0.8,
             "crowding_asymmetry": 0.01}
        ms = play(d, {"0": "pro", "1": "pro"}, "/tmp/selfplay.jsonl")
        total += ms
        sa = final_score("/tmp/selfplay.jsonl", 0)
        sb = final_score("/tmp/selfplay.jsonl", 1)
        print(f"{name:10} A {sa:.0f} vs B {sb:.0f}  diff {abs(sa - sb):.0f}  {ms:.0f}ms")
    print(f"-- selfplay total {total / 1000:.1f}s --")
    return total


# Home-and-away: attacker 3000 vs defender 3000, 200km, 60 turns.
# Attacker wins iff it owns the defender's town at the end. Symmetric
# maps self-mirror into ties (verified: 1173-1173 at 60 AND 150 turns),
# so each pair plays both sides.
ELO_MAP = {"map": "x,y,type,population\n200.0,500.0,A,3000\n400.0,500.0,B,3000",
           "map_size": [1000, 1000], "max_turns": 60,
           "turn_time_ms": 1000, "info_speed": 150.0, "army_speed": 50.0,
           "army_cost": 1000, "interact_radius": 10.0, "population_cap": 100000.0,
           "population_growth": 0.001, "build_efficiency": 0.5,
           "equilibrium_spacing": 0.1, "crowding_decay": 0.8,
           "crowding_asymmetry": 0.01}


def _attacker_won(record):
    lines = Path(record).read_text().splitlines()
    world = json.loads(lines[-1])["world"]
    t = next((x for x in world["towns"] if x["id"] == 1), None)
    return t is not None and t["faction"] == 0


def section_elo(bots=("pro", "greedy", "aggressive", "turtle", "expander")):
    print("== Elo lite (home-and-away raid, K=16 per side-game) ==")
    import itertools
    elo = {b: 1500.0 for b in bots}
    total = 0.0
    for a, b in itertools.combinations(bots, 2):
        for att, dfn in ((a, b), (b, a)):
            ms = play(ELO_MAP, {"0": att, "1": dfn}, "/tmp/elo.jsonl")
            total += ms
            won = _attacker_won("/tmp/elo.jsonl")
            ra, rb = (1.0, 0.0) if won else (0.0, 1.0)
            ea = 1 / (1 + 10 ** ((elo[dfn] - elo[att]) / 400))
            elo[att] += 16 * (ra - ea)
            elo[dfn] += 16 * (rb - (1 - ea))
            print(f"{att:10} attacks {dfn:10} {'takes it' if won else 'fails  '}  {ms:.0f}ms")
    for b, r in sorted(elo.items(), key=lambda kv: -kv[1]):
        print(f"  {b:10} {r:.0f}")
    print(f"-- elo total {total / 1000:.1f}s --")
    return total


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.perf_counter()
    if want in ("all", "maps"):
        section_maps()
    if want in ("all", "optimum"):
        section_optimum()
    if want in ("all", "selfplay"):
        section_selfplay()
    if want in ("all", "elo"):
        section_elo()
    print(f"===== strategic suite wall {(time.perf_counter() - t0):.1f}s =====")


if __name__ == "__main__":
    main()
