"""Benchmark↔Elo correlation: run every scenario/strategic map for a set
of bot-commits, join FFA elo, report Spearman per map.

Usage: PYTHONPATH=src .venv/bin/python benchmarks/corr.py [--bots N] [--out FILE]
Uses elo_field worktrees (bots run fully on-commit). Appends nothing;
prints a table + writes JSON.
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

CANDIDATES = [
    ("pro", "e4e5b01"), ("pro", "851ba30"), ("pro", "f17d994"),
    ("pro", "84b32be"), ("pro", "HEAD"),
    ("expander", "851ba30"), ("expander", "f17d994"), ("expander", "84b32be"),
    ("expander", "HEAD"),
    ("aggressive", "851ba30"), ("aggressive", "f17d994"), ("aggressive", "HEAD"),
    ("turtle", "851ba30"), ("turtle", "f17d994"), ("turtle", "HEAD"),
    ("greedy", "f17d994"), ("greedy", "84b32be"),
]

SPECIAL = {"HEAD"}


def bot_cmd(name, commit):
    sha = sha_of(commit)
    if commit == "HEAD" and (ROOT / "src" / "bots" / f"{name}.py").exists():
        return f"{sys.executable} -m bots.{name}", f"{name}-{sha}"
    d = ensure_worktree(sha)
    return (f"cd {d} && PYTHONPATH={d}/src {sys.executable} -m bots.{name}",
            f"{name}-{sha}")


def all_maps():
    out = []
    for sub in ("scenarios", "strategic", "ffa"):
        for path in sorted((ROOT / "maps" / sub).glob("*.json")):
            d = json.loads(path.read_text())
            out.append((f"{sub}/{path.stem}", d))
    return out


def run_map(d, cmd):
    """Run map with the candidate bot in ALL bot slots (focal-normalized).

    Map teams may name bots absent at that commit (e.g. greedy deleted):
    every bot-named slot runs OUR candidate; stub/random slots stay.
    Score = focal faction's score."""
    if "?" in d["teams"].values():
        # Single-slot F0 (same slot for every bot = fair; rotation
        # showed slots tie when bots sleep — 3000t wakes them).
        teams = {}
        for f, name in d["teams"].items():
            if name == "?":
                teams[int(f)] = cmd
            elif name in ("stub", "random"):
                return None
            elif "-" in name:
                ref, _c = name.rsplit("-", 1)
                _sha = sha_of(_c)
                _dd = ensure_worktree(_sha)
                teams[int(f)] = (f"cd {_dd} && PYTHONPATH={_dd}/src {sys.executable} "
                                 f"-m bots.{ref}")
            else:
                teams[int(f)] = cmd
        focal = int(d.get("focal", 0))
        cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                    if k not in ("teams", "focal", "goal", "note")})
        try:
            _scores = run_game(cfg, teams, None)
        except Exception:
            return None
        return _scores.get(focal)
    teams = {}
    for f, name in d["teams"].items():
        if name in ("stub", "random"):
            continue  # can't stand in; skip map if focal is one of these
        if name == "?":
            teams[int(f)] = cmd
        elif "-" in name:
            ref, _c = name.rsplit("-", 1)
            _sha = sha_of(_c)
            _d = ensure_worktree(_sha)
            teams[int(f)] = (f"cd {_d} && PYTHONPATH={_d}/src {sys.executable} "
                             f"-m bots.{ref}")
        else:
            teams[int(f)] = cmd
    if not teams or str(d.get("focal", "0")) not in d["teams"]:
        return None
    focal = int(d["focal"])
    if focal not in teams:
        return None
    cfg = GameConfig.from_dict({k: v for k, v in d.items()
                                if k not in ("teams", "focal", "goal", "note")})
    try:
        scores = run_game(cfg, teams, None)
    except Exception:
        return None
    return scores.get(focal)


def spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return float("nan")
    rx = _rank(xs)
    ry = _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / (vx * vy) ** 0.5


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", type=int, default=len(CANDIDATES))
    ap.add_argument("--out", default="benchmarks/corr.json")
    args = ap.parse_args(argv)
    elos = json.loads((ROOT / "benchmarks" / "elos.json").read_text())
    cands = CANDIDATES[:args.bots]
    maps = all_maps()
    print(f"{len(cands)} bots x {len(maps)} maps", flush=True)
    scores = {}
    t0 = time.perf_counter()
    for name, commit in cands:
        cmd, key = bot_cmd(name, commit)
        elo = elos.get(key, {}).get("elo")
        if elo is None:
            print(f"skip {key} (no elo)")
            continue
        row = {}
        for mname, d in maps:
            s = run_map(d, cmd)
            row[mname] = s
        scores[key] = {"elo": elo, "maps": row}
        print(f"{key:22} elo {elo:.0f}  ({time.perf_counter()-t0:.0f}s)", flush=True)
    table = []
    for mname, _ in maps:
        xs, ys = [], []
        for key, r in scores.items():
            s = r["maps"].get(mname)
            if s is not None and s == s:
                xs.append(s)
                ys.append(r["elo"])
        table.append({"map": mname, "rho": spearman(xs, ys), "n": len(xs)})
    table.sort(key=lambda r: -(r["rho"] if r["rho"] == r["rho"] else -2))
    for r in table:
        print(f"  rho {r['rho']:+.2f}  n={r['n']:2}  {r['map']}")
    json.dump({"scores": scores, "table": table}, open(args.out, "w"), indent=1)
    print(f"wrote {args.out} ({time.perf_counter()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
