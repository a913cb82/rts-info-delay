"""Smart matchmaking: most-informative 5-bot fields.

Information = close skill (high predict_draw) + high uncertainty (sigma).
Pool = personalities x evenly-spaced commits (valid combos only).
Greedy: seed highest-sigma bot, add 4 maximizing draw_prob + sigma bonus.

Usage: PYTHONPATH=src:benchmarks python benchmarks/matchmake.py [--n N] [--play M]
  --n: fields to propose (default 1); --play: also play+log M fields (default 0)
"""
import argparse
import itertools
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))

ROOT = Path(__file__).resolve().parents[1]
from openskill.models import BradleyTerryFull


def all_commits() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%h",
                          "--reverse", "--", "src/bots/"],
                         capture_output=True, text=True, check=True)
    return out.stdout.split()


def bots_at(commit: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r",
                          "--name-only", commit, "--", "src/bots/"],
                         capture_output=True, text=True).stdout
    names = set()
    for line in out.splitlines():
        if line.endswith(".py"):
            n = line.split("/")[-1][:-3]
            if n not in ("common", "stub", "__init__"):
                names.add(n)
    return sorted(names)


def pool() -> list[str]:
    """Valid name-sha across evenly-spaced history + HEAD."""
    commits = all_commits()
    picks = set()
    # ~12 evenly spaced + last 6 (recent matters most)
    idx = sorted(set([int(i * (len(commits) - 1) / 11) for i in range(12)] +
                     list(range(max(0, len(commits) - 6), len(commits)))))
    for i in idx:
        c = commits[i]
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", c],
                             capture_output=True, text=True).stdout.strip()
        for b in bots_at(c):
            if b == "random" and i < len(commits) - 6:
                continue
            picks.add(f"{b}-{sha}")
    # HEAD short sha
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    for b in bots_at("HEAD"):
        picks.add(f"{b}-{head}")
    return sorted(picks)


def ratings() -> dict:
    p = ROOT / "benchmarks" / "elos.json"
    return json.loads(p.read_text()) if p.exists() else {}


def info_score(m, combo: list[str], elo: dict) -> float:
    teams = []
    sig = 0.0
    for k in combo:
        e = elo.get(k, {"mu": m.mu, "sigma": m.sigma})
        teams.append([m.rating(mu=e["mu"], sigma=e["sigma"])])
        sig += e["sigma"]
    try:
        draw = m.predict_draw(teams)
    except Exception:
        draw = 0.2
    return draw + 0.02 * sig


def propose(m, candidates: list[str], elo: dict, rng: random.Random) -> list[str]:
    # seed: highest sigma (ties -> random)
    cands = sorted(candidates, key=lambda k: (-elo.get(k, {"sigma": m.sigma})["sigma"], rng.random()))
    field = [cands[0]]
    rest = [c for c in cands if c != field[0]]
    while len(field) < 5 and rest:
        scored = sorted(rest, key=lambda k: -info_score(m, field + [k], elo))
        # epsilon-greedy: usually best, sometimes 2nd/3rd (diversity)
        pick = scored[0] if rng.random() < 0.8 else rng.choice(scored[:min(3, len(scored))])
        field.append(pick)
        rest = [c for c in rest if c != pick]
    return field


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--play", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--survey", action="store_true",
                      help="fields of never-played bots first (cover the pool)")
    args = ap.parse_args(argv)
    m = BradleyTerryFull()
    elo = ratings()
    cands = pool()
    print(f"pool: {len(cands)} bots", flush=True)
    rng = random.Random(args.seed)
    import subprocess as _sp
    _head = _sp.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    _headbots = [c for c in cands if c.endswith(_head)]
    fields = []
    unplayed = [c for c in cands if elo.get(c, {}).get("games", 0) == 0]
    rng.shuffle(unplayed)
    for i in range(max(args.n, args.play)):
        if args.survey and unplayed:
            f = unplayed[:5]
            unplayed = unplayed[5:]
            # pad with high-sigma if pool runs dry
            while len(f) < 5:
                extra = [c for c in cands if c not in f]
                f.append(rng.choice(extra))
        else:
            f = propose(m, cands, elo, rng)
        # every other field spotlights HEAD (keeps current bots measured)
        if i % 2 == 1 and _headbots:
            pick = rng.choice(_headbots)
            if pick not in f:
                # swap out the lowest-sigma member (keep the seed)
                tail = sorted(f[1:], key=lambda k: elo.get(k, {'sigma': m.sigma})['sigma'])
                f[f.index(tail[0])] = pick
        fields.append(f)
        slots = " ".join(f"F{j}={b}" for j, b in enumerate(f))
        print(f"field {i + 1}: {slots}  info={info_score(m, f, elo):.2f}", flush=True)
    if args.play:
        from elo_field import update
        from engine.config import GameConfig
        from runner.main import run_game
        cfg = {k: v for k, v in
               json.loads(open("recordings/empty_10000.jsonl").readline().strip()).items()
               if k != "type"}
        cfg = GameConfig.from_dict(cfg)
        import time
        sys.path.insert(0, str(ROOT / "src"))
        _played = []
        for i, f in enumerate(fields[:args.play]):
            cmds = {}
            for slot, spec in enumerate(f):
                name, commit = spec.rsplit("-", 1)
                from elo_field import ensure_worktree, sha_of
                sha = sha_of(commit)
                d = ensure_worktree(sha)
                cmds[slot] = f"cd {d} && PYTHONPATH={d}/src {sys.executable} -m bots.{name}"
            scores = run_game(cfg, cmds, None)
            sc = {s: float(scores.get(s, 0)) for s in range(5)}
            update(elo, {s: f[s] for s in range(5)}, sc)
            ranked = sorted(sc, key=lambda s: -sc[s])
            print(f"played {i + 1}: " + " ".join(f"{f[s]}:{round(sc[s])}" for s in ranked), flush=True)
            _played.append({s: sc[s] for s in range(5)})
        (ROOT / "benchmarks" / "elos.json").write_text(json.dumps(elo, indent=1))
        import time as _t
        with open(ROOT / "benchmarks" / "elo_games.jsonl", "a") as fh:
            for f, sc in zip(fields[:args.play], _played):
                fh.write(json.dumps({'ts': _t.time(),
                                     'field': {s: f[s] for s in range(5)},
                                     'scores': sc}) + chr(10))
        print("ratings saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
