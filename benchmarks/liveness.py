"""Liveness suite: full games must END with every bot alive.

The None-order crash (fixed 262b0f5) killed pro/aggressive/turtle at
their first settle (t1130-1776) for dozens of commits — invisible to
every suite because none checked whether bots survived the game (cheap
suite read only scores; scenarios stop before/avoid the lethal path).

Usage: PYTHONPATH=src .venv/bin/python benchmarks/liveness.py [--turns 4000] [--dirty]
Default runs clean HEAD worktree (like cheap.py); --dirty runs the workspace.
~12s for 4000 turns x 5 bots. Exit 1 if any crash/eof or clock death.
"""
import argparse
import contextlib
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from engine.config import GameConfig            # noqa: E402
from runner.main import run_game                # noqa: E402
from elo_field import ensure_worktree, sha_of   # noqa: E402

PERSONALITIES = {0: "pro", 1: "pro", 2: "aggressive", 3: "expander", 4: "turtle"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=4000)
    ap.add_argument("--dirty", action="store_true",
                    help="run workspace tree (default: clean HEAD)")
    args = ap.parse_args(argv)

    d = json.loads((ROOT / "maps" / "empty.json").read_text())
    d["max_turns"] = args.turns
    cfg = GameConfig.from_dict(d)
    if args.dirty:
        cmds = {f: f"{sys.executable} -m bots.{n}" for f, n in PERSONALITIES.items()}
    else:
        wd = ensure_worktree(sha_of("HEAD"))
        cmds = {f: f"cd {wd} && PYTHONPATH={wd}/src {sys.executable} -m bots.{n}"
                for f, n in PERSONALITIES.items()}

    t0 = time.perf_counter()
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        scores = run_game(cfg, cmds, None)
    wall = time.perf_counter() - t0
    err = buf.getvalue()
    dead = [ln.strip() for ln in err.splitlines()
            if "crash/eof" in ln or "timeout (" in ln]

    for f, n in sorted(PERSONALITIES.items()):
        print(f"  F{f} {n:11} {scores.get(f, 0):9.0f}")
    print(f"liveness {'clean' if not dead else str(len(dead)) + ' DEAD'}"
          f"  ({args.turns}t x {len(PERSONALITIES)})")
    for ln in dead[:6]:
        print(f"  ! {ln}")
    print(f"--- liveness wall {wall:.1f}s ---")
    return 1 if dead else 0


if __name__ == "__main__":
    raise SystemExit(main())
