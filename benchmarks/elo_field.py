"""Cross-commit FFA Elo field: bots as name-commit, persistent JSON.

Usage:
  PYTHONPATH=src .venv/bin/python benchmarks/elo_field.py \\
      --field F0=pro-HEAD,F1=pro-HEAD,F2=aggressive-HEAD,F3=expander-HEAD,F4=turtle-HEAD \\
      [--games 6] [--elo benchmarks/elos.json]

Specs: <slot>=<botname>-<commit|HEAD>. Bot code is fetched from that
commit via a git worktree (/tmp/botwork_<sha>); each bot launches as a
bash string with its own PYTHONPATH (engine stays HEAD — only bot
brains time-travel). Ratings persist in the JSON ({name: {elo, games}},
K=16 margin-weighted, same math as elo.py) across runs, so tables
accumulate over days. Seed: run current HEAD once to create entries.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.config import GameConfig
from runner.main import run_game

ROOT = Path(__file__).resolve().parents[1]
ELO_PATH = ROOT / "benchmarks" / "elos.json"
K = 16.0


def sha_of(commit: str) -> str:
    if commit == "HEAD":
        commit = "HEAD"
    out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", commit],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def ensure_worktree(sha: str) -> Path:
    d = Path(f"/tmp/botwork_{sha}")
    if (d / "src" / "bots").exists():
        return d
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach",
                    str(d), sha], check=True, capture_output=True)
    return d


def bot_cmd(name: str, sha: str) -> str:
    if sha == sha_of("HEAD") and name in ("pro", "aggressive", "expander", "turtle"):
        pass  # still use a worktree for uniformity? No — HEAD runs in-tree.
    if name == "HEAD":
        raise ValueError("bad spec (need name-commit)")
    d = ensure_worktree(sha)
    py = sys.executable
    return f"cd {d} && PYTHONPATH={d}/src {py} -m bots.{name}"


def load_elo(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _model():
    from openskill.models import BradleyTerryFull
    return BradleyTerryFull()


def update(elo: dict, field: dict[int, str], scores: dict[int, float]) -> None:
    """OpenSkill Bradley-Terry-Full update (native FFA: whole placement
    vector updates at once, no pairwise decomposition)."""
    m = _model()
    order = sorted(scores, key=lambda f: -scores[f])
    # ranks with ties (equal pops share)
    ranks, prev, r = [], None, 0
    for i, f in enumerate(order):
        if scores[f] != prev:
            r = i + 1
            prev = scores[f]
        ranks.append(r)
    teams = []
    names = []
    for f in order:
        n = field[f]
        names.append(n)
        e = elo.setdefault(n, {"mu": m.mu, "sigma": m.sigma, "games": 0})
        teams.append([m.rating(mu=e["mu"], sigma=e["sigma"])])
    new = m.rate(teams, ranks=ranks)
    for n, t in zip(names, new):
        elo[n]["mu"] = t[0].mu
        elo[n]["sigma"] = t[0].sigma
        elo[n]["games"] += 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--field", required=True, help="F0=bot-commit,... (5 slots)")
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--elo", default=str(ELO_PATH))
    ap.add_argument("--record", default=None, help="record last game to JSONL")
    args = ap.parse_args(argv)
    field: dict[int, str] = {}
    cmds: dict[int, str] = {}
    for spec in args.field.split(","):
        slot, name_commit = spec.split("=")
        f = int(slot.strip().upper().lstrip("F"))
        name, commit = name_commit.strip().rsplit("-", 1)
        sha = sha_of(commit)
        key = f"{name}-{sha}"
        field[f] = key
        cmds[f] = bot_cmd(name, sha)
    elo = load_elo(Path(args.elo))
    cfg = {k: v for k, v in
           json.loads(open("recordings/empty_10000.jsonl").readline().strip()).items()
           if k != "type"}
    cfg = GameConfig.from_dict(cfg)
    t0 = time.perf_counter()
    games_log = ROOT / "benchmarks" / "elo_games.jsonl"
    for i in range(args.games):
        rec = Path(args.record) if args.record and i == args.games - 1 else None
        scores = run_game(cfg, cmds, rec)
        scores = {f: float(scores.get(f, 0)) for f in field}
        update(elo, field, scores)
        # Append-only game record (elo never resets; history recomputable).
        with open(games_log, "a") as fh:
            fh.write(json.dumps({"ts": time.time(), "field": field,
                                 "scores": scores}) + "\n")
        ranked = sorted(scores, key=lambda f: -scores[f])
        print(f"game {i + 1}: " + " ".join(f"{field[f]}:{round(scores[f])}" for f in ranked), flush=True)
    Path(args.elo).write_text(json.dumps(elo, indent=1))
    for n, r in sorted(elo.items(), key=lambda kv: -(kv[1]['mu'] - 3 * kv[1]['sigma'])):
        print(f"  {n:24} {r['mu'] - 3 * r['sigma']:.1f} (mu {r['mu']:.1f} sig {r['sigma']:.2f}, {r['games']}g)")
    print(f"-- field {args.games} games {(time.perf_counter() - t0):.0f}s -> {args.elo} --")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
