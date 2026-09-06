"""FFA-sprint bench: candidate bot vs pinned historical refs (fast FFA skill sample).

Usage: PYTHONPATH=src .venv/bin/python benchmarks/ffa_bench.py [--bot pro] [--commit HEAD]
"?" slot runs the workspace candidate; "name-sha" slots resolve via worktrees.
Score = focal pops (placement in parens).
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
from elo_field import ensure_worktree, sha_of

FFA_DIR = ROOT / "maps" / "ffa"


def resolve(spec, cand_bot, dirty=False):
    if spec == "?":
        if dirty:
            return f"{sys.executable} -m bots.{cand_bot}"
        sha = sha_of("HEAD")
        d = ensure_worktree(sha)
        return f"cd {d} && PYTHONPATH={d}/src {sys.executable} -m bots.{cand_bot}"
    name, commit = spec.rsplit("-", 1)
    sha = sha_of(commit)
    d = ensure_worktree(sha)
    return f"cd {d} && PYTHONPATH={d}/src {sys.executable} -m bots.{name}"


def cand_cmd(args):
    if args.commit:
        sha = sha_of(args.commit)
        dd = ensure_worktree(sha)
        return f"cd {dd} && PYTHONPATH={dd}/src {sys.executable} -m bots.{args.bot}"
    if getattr(args, "dirty", False):
        return f"{sys.executable} -m bots.{args.bot}"
    sha = sha_of("HEAD")
    dd = ensure_worktree(sha)
    return f"cd {dd} && PYTHONPATH={dd}/src {sys.executable} -m bots.{args.bot}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", default="pro")
    ap.add_argument("--commit", default=None, help="bot-commit for candidate (default: workspace)")
    ap.add_argument("--dirty", action="store_true", help="run workspace tree (default: clean HEAD worktree)")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    for path in sorted(FFA_DIR.glob("*.json")):
        d = json.loads(path.read_text())
        cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                    if k not in ("teams", "focal", "note")})
        # Rotation: candidate plays every slot (positional bias is real —
        # F0's start scored identically for all bots). Score = mean pops.
        refs = [(int(f), spec) for f, spec in d["teams"].items() if spec != "?"]
        tot, ms = 0.0, 0.0
        for slot in range(5):
            cmds = {slot: cand_cmd(args)}
            ri = 0
            for f in range(5):
                if f == slot:
                    continue
                cmds[f] = resolve(refs[ri][1], args.bot, getattr(args, "dirty", False))
                ri += 1
            t1 = time.perf_counter()
            scores = run_game(cfg, cmds, None)
            ms += (time.perf_counter() - t1) * 1000
            tot += scores.get(slot, 0)
        print(f"{path.stem:10} focal-mean {tot / 5:7.0f}  {ms:6.0f}ms")
    print(f"--- ffa wall {time.perf_counter()-t0:.1f}s ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
