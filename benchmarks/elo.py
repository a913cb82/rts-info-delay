"""FFA Elo: rank-based pairwise updates, no 1v1s.

Each 5-player game yields 10 pairwise results (placements, not just
wins: 1st beats all four, 2nd beats three...). Score-margin weights
the K (blowouts move more than photo-finishes). 6 games (~4 min)
gives a rough table; 12 tightens it.

Usage: PYTHONPATH=src .venv/bin/python benchmarks/elo.py [N]
"""
import itertools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.config import GameConfig
from runner.main import run_game

LINEUP = {0: "pro", 1: "pro", 2: "aggressive", 3: "expander", 4: "turtle"}
K = 16.0


def play_game(py: str, game_i: int) -> dict[int, float]:
    cfg = {k: v for k, v in
           json.loads(open("recordings/empty_10000.jsonl").readline().strip()).items()
           if k != "type"}
    cfg = GameConfig.from_dict(cfg)
    bots = {f: f"{py} -m bots.{n}" for f, n in LINEUP.items()}
    scores = run_game(cfg, bots, None)
    # final pops per faction (score = pop; zero towns still scores banked?)
    return {f: float(scores.get(f, 0)) for f in LINEUP}


def update(elo: dict[str, float], scores: dict[int, float]) -> None:
    # rank factions by score (ties share: 0.5 each)
    order = sorted(scores, key=lambda f: -scores[f])
    pops = [scores[f] for f in order]
    spread = max(pops) - min(pops)
    for i, a in enumerate(order):
        for j, b in enumerate(order):
            if i >= j:
                continue
            # a placed above b: a wins the pair
            name_a, name_b = f"F{a}-{LINEUP[a]}", f"F{b}-{LINEUP[b]}"
            # margin weight: blowout pairs count more (up to 1.5x)
            w = 1.0
            if spread > 0:
                w = 1.0 + 0.5 * (scores[a] - scores[b]) / spread
            ea = 1 / (1 + 10 ** ((elo[name_b] - elo[name_a]) / 400))
            elo[name_a] += K * w * (1.0 - ea)
            elo[name_b] += K * w * (0.0 - (1 - ea))


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    py = sys.executable
    names = [f"F{f}-{n}" for f, n in LINEUP.items()]
    elo = {b: 1500.0 for b in names}
    t0 = time.perf_counter()
    for i in range(n):
        scores = play_game(py, i)
        update(elo, scores)
        ranked = sorted(scores, key=lambda f: -scores[f])
        desc = " ".join(f"F{f}:{round(scores[f])}" for f in ranked)
        print(f"game {i + 1}: {desc}", flush=True)
    for b, r in sorted(elo.items(), key=lambda kv: -kv[1]):
        print(f"  {b:10} {r:.0f}")
    print(f"-- ffa-elo {n} games {(time.perf_counter() - t0):.0f}s --")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
