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


def run_scenario(path, py):
    d = json.loads(Path(path).read_text())
    cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                if k not in ("teams", "focal", "goal")})
    bots = {int(f): [py, "-m", f"bots.{name}"] for f, name in d["teams"].items()}
    rec = Path("/tmp/scen_record.jsonl")
    t0 = time.perf_counter()
    run_game(cfg, bots, rec)
    ms = (time.perf_counter() - t0) * 1000
    lines = Path(rec).read_text().splitlines()
    world = json.loads(lines[-1])["world"]
    f = d["focal"]
    score = (sum(x["population"] for x in world["towns"] if x["faction"] == f) +
             1000 * sum(1 for x in world["armies"] if x["faction"] == f))
    return score, ms


def main():
    t0 = time.time()
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
            score, ms = run_scenario(path, py)
        except Exception as e:
            score, ms = float("nan"), 0.0
            print(f"ERROR {path.stem}: {e}")
        total_ms += ms
        results.append((path.stem, score, ms))
        print(f"{path.stem:24} score {score:7.0f}  {ms:7.0f}ms")
    print(f"--- {len(results)} scenarios in {total_ms / 1000:.1f}s ---")
    wall = time.time() - t0
    budget = 5.0
    print(f"--- wall {wall:.1f}s / budget {budget:.0f}s {'PASS' if wall <= budget else 'FAIL'} ---")
    if wall > budget:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
