"""Scenario benchmarks: per-bot map suites. Fast by design (2 factions,
short games, pops at thresholds).

Usage:
  PYTHONPATH=src .venv/bin/python benchmarks/scenario_bench.py [all|greedy|expander|aggressive|turtle|pro]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.config import GameConfig
from runner.main import run_game

SCEN_DIR = Path(__file__).resolve().parents[1] / "maps" / "scenarios"


def check_goal(goal, focal, record_path):
    """Evaluate goal against the recorded game. Returns (passed, stat)."""
    lines = Path(record_path).read_text().splitlines()
    turns = [json.loads(l) for l in lines[1:]]
    world = turns[-1]["world"]
    towns = world["towns"]
    armies = world["armies"]
    g = goal["type"]
    if g == "own_town":
        t = next((x for x in towns if x["id"] == goal["town"]), None)
        return (t is not None and t["faction"] == focal,
                f"town{goal['town']}->f{t['faction'] if t else '-'}")
    if g == "own_towns":
        ok = all((next((x for x in towns if x["id"] == i), None) or {}).get("faction") == focal
                 for i in goal["towns"])
        return ok, f"{sum(1 for i in goal['towns'] if (next((x for x in towns if x['id'] == i), None) or {}).get('faction') == focal)}/{len(goal['towns'])}"
    if g == "towns_ge":
        n = sum(1 for x in towns if x["faction"] == goal.get("faction", focal))
        return n >= goal["n"], f"{n} towns"
    if g == "survive_capital":
        f = goal.get("faction", focal)
        caps = [x for x in towns if x["faction"] == f and x.get("is_capital")]
        return (len(caps) > 0, f"capital {'held' if caps else 'LOST'}")
    if g == "enemy_owns":
        t = next((x for x in towns if x["id"] == goal["town"]), None)
        return (t is not None and t["faction"] != focal,
                f"town{goal['town']}->f{t['faction'] if t else '-'}")
    if g == "armies_zero":
        n = sum(1 for x in armies if x["faction"] == goal.get("faction", focal))
        return n == 0, f"{n} idle"
    if g == "score_ge":
        pops = sum(x["population"] for x in towns if x["faction"] == goal.get("faction", focal))
        na = sum(1 for x in armies if x["faction"] == goal.get("faction", focal))
        score = pops + 1000 * na
        return score >= goal["x"], f"score {score:.0f}"
    if g == "score_gt":
        def sc(f):
            return (sum(x["population"] for x in towns if x["faction"] == f) +
                    1000 * sum(1 for x in armies if x["faction"] == f))
        a, b = sc(goal.get("faction", focal)), sc(goal["other"])
        return a > b, f"{a:.0f} vs {b:.0f}"
    if g == "trained_by":
        f = goal.get("faction", focal)
        first = None
        for t in turns:
            for e in t.get("events", []):
                if e.get("kind") == "army_spawn" and e.get("faction") == f:
                    first = t["turn"]
                    break
            if first is not None:
                break
        ok = first is not None and first <= goal["turn"]
        return ok, f"first train t{first}"
    raise ValueError(f"unknown goal {g}")


def run_scenario(path, py):
    d = json.loads(Path(path).read_text())
    cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                if k not in ("teams", "focal", "goal")})
    bots = {int(f): [py, "-m", f"bots.{name}"] for f, name in d["teams"].items()}
    rec = Path("/tmp/scen_record.jsonl")
    t0 = time.perf_counter()
    run_game(cfg, bots, rec)
    ms = (time.perf_counter() - t0) * 1000
    passed, stat = check_goal(d["goal"], d["focal"], rec)
    return passed, stat, ms


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else "all"
    files = sorted(SCEN_DIR.glob("*.json"))
    if want != "all":
        files = [f for f in files if f.stem == want or f.stem.startswith(want + "_")]
    py = sys.executable
    # Warmup (untimed): first game in-process compiles numba kernels (~1.2s).
    # Use the cheapest scenario so the bill lands here, not on scenario #1.
    warm = SCEN_DIR / "greedy_recycle.json"
    if warm.exists():
        try:
            run_scenario(warm, py)
        except Exception:
            pass
    results = []
    total_ms = 0.0
    for path in files:
        try:
            passed, stat, ms = run_scenario(path, py)
        except Exception as e:
            passed, stat, ms = False, f"ERROR {e}", 0.0
        total_ms += ms
        results.append((path.stem, passed, stat, ms))
        print(f"{'PASS' if passed else 'FAIL'} {path.stem:24} {stat:16} {ms:7.0f}ms")
    npass = sum(1 for _, p, _, _ in results if p)
    print(f"--- {npass}/{len(results)} passed in {total_ms / 1000:.1f}s ---")


if __name__ == "__main__":
    main()
