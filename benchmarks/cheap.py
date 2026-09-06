"""Cheap suite (<5s, elo rho +0.59 n=17): ffa/feast + strategic/snowball.

Usage: PYTHONPATH=src .venv/bin/python benchmarks/cheap.py [--bot pro]
Composite = z-feast + z-snowball with frozen corr baselines (corr.json,
n=17 historic bots). Budget 5s, fail loudly.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))

ROOT = Path(__file__).resolve().parents[1]
from engine.config import GameConfig
from runner.main import run_game
from ffa_bench import resolve

# Frozen baselines (mean, stdev over 17 corr bots) — recompute if corr grows.
BASE = {"ffa/feast": (7483.0, 3824.0), "strategic/snowball": (0.0, 1.0)}


def run_feast(bot, dirty=False):
    d = json.loads((ROOT / "maps" / "ffa" / "feast.json").read_text())
    cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                if k not in ("teams", "focal", "note")})
    cmds = {int(f): resolve(s, bot, dirty) for f, s in d["teams"].items()}
    t0 = time.perf_counter()
    scores = run_game(cfg, cmds, None)
    return scores.get(0, 0), (time.perf_counter() - t0) * 1000


def run_snowball(bot, dirty=False):
    d = json.loads((ROOT / "maps" / "strategic" / "snowball.json").read_text())
    cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                if k not in ("teams", "focal", "note")})
    from elo_field import ensure_worktree, sha_of
    if dirty:
        cmds = {0: f"{sys.executable} -m bots.{bot}"}
    else:
        _dd = ensure_worktree(sha_of("HEAD"))
        cmds = {0: f"cd {_dd} && PYTHONPATH={_dd}/src {sys.executable} -m bots.{bot}"}
    t0 = time.perf_counter()
    scores = run_game(cfg, cmds, None)
    return scores.get(0, 0), (time.perf_counter() - t0) * 1000


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", default="pro")
    ap.add_argument("--dirty", action="store_true", help="run workspace tree (default: clean HEAD)")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    try:
        base = json.load(open(ROOT / "benchmarks" / "corr.json"))
        m1 = [base["scores"][b]["maps"]["ffa/feast"] for b in base["scores"]]
        m2 = [base["scores"][b]["maps"]["strategic/snowball"] for b in base["scores"]]
        import statistics
        BASE["ffa/feast"] = (statistics.mean(m1), statistics.stdev(m1) or 1)
        BASE["strategic/snowball"] = (statistics.mean(m2), statistics.stdev(m2) or 1)
    except Exception:
        pass
    f, fms = run_feast(args.bot, args.dirty)
    s, sms = run_snowball(args.bot, args.dirty)
    comp = (f - BASE["ffa/feast"][0]) / BASE["ffa/feast"][1] + \
           (s - BASE["strategic/snowball"][0]) / BASE["strategic/snowball"][1]
    wall = time.perf_counter() - t0
    print(f"feast    {f:7.0f}  {fms:6.0f}ms")
    print(f"snowball {s:7.0f}  {sms:6.0f}ms")
    print(f"composite {comp:+.2f}")
    print(f"--- cheap wall {wall:.1f}s / budget 5s {'PASS' if wall <= 5 else 'FAIL'} ---")
    if wall > 5:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
