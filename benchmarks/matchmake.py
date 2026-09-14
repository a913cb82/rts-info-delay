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
    # FULL population: every ref (main + loop/era branches), not just HEAD
    # history — branch-tip brains are suitable bots too. Dedup by sha;
    # pool() further dedups by brain content (identical code = one entry).
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--all",
                          "--format=%h", "--reverse", "--", "src/bots/"],
                         capture_output=True, text=True, check=True)
    seen: set[str] = set()
    commits = []
    for sha in out.stdout.split():
        if sha not in seen:
            seen.add(sha)
            commits.append(sha)
    return commits


def bots_at(commit: str) -> list[str]:
    """Personalities at a commit: package dirs (src/bots/<name>/) plus
    legacy flat modules (src/bots/<name>.py)."""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r",
                          "--name-only", commit, "--", "src/bots/"],
                         capture_output=True, text=True).stdout
    names = set()
    for line in out.splitlines():
        if not line.endswith(".py"):
            continue
        parts = line.split("/")
        if len(parts) >= 4:  # src/bots/<pkg>/<file>.py
            names.add(parts[2])
        else:
            n = parts[-1][:-3]
            if n not in ("common", "stub", "__init__"):
                names.add(n)
    return sorted(names)


def brain_hash(commit: str, bot: str) -> str:
    """Content hash of the bot's brain.

    Package layout (refactor): a personality lives in src/bots/<bot>/
    and its brain = EVERY file in that directory (brain.py + its own
    core.py). A change to one personality's core can no longer re-hash
    another's brain. Legacy flat commit: bot file + common.py."""
    import hashlib
    out = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", commit,
                          "--", "src/bots/"],
                         capture_output=True, text=True).stdout
    pkg = []
    flat = []
    for l in out.splitlines():
        if not l.strip():
            continue
        parts = l.split(None, 3)
        if len(parts) < 4:
            continue
        path = parts[3]
        if path.startswith(f"src/bots/{bot}/"):
            pkg.append(parts[2])
        elif path.endswith(f"/{bot}.py") or path.endswith("/common.py"):
            flat.append(parts[2])
    blobs = sorted(pkg) if pkg else sorted(flat)
    return hashlib.sha1("".join(blobs).encode()).hexdigest()[:10]


def pool() -> list[str]:
    """Full population: every ref (main + loop/era branches), deduped by
    brain content (identical code = one candidate). For each content hash
    the RATED name wins (most games — a worklog-only commit must not mint
    a fresh duplicate of a rated brain); ties/unrated -> newest commit."""
    commits = all_commits()
    # all (bot, sha) pairs (no first-wins dedup yet)
    pairs: list[tuple[str, str]] = []
    for c in commits:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", c],
                             capture_output=True, text=True).stdout.strip()
        for b in bots_at(c):
            pairs.append((b, out))
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    for b in bots_at("HEAD"):
        pairs.append((b, head))
    # commit order index (newest last) for tie-breaks
    order = {sha: i for i, sha in enumerate(
        [subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", c],
                        capture_output=True, text=True).stdout.strip()
         for c in commits] + [head])}
    try:
        elo = ratings()
    except Exception:
        elo = {}
    by_hash: dict[str, list[tuple[str, str]]] = {}
    for b, sha in pairs:
        try:
            h = brain_hash(sha, b)
        except Exception:
            continue
        by_hash.setdefault(f"{b}@{h}", []).append((b, sha))
    # Bye-filter (hygiene): brains that only ever score <=0 crashed on the
    # wire (logistic-era protocol) and are free byes + room-bonus distortions
    # (apex-979s). Drop entries with >=2 games and no positive score.
    _best: dict[str, float] = {}
    try:
        import json as _json
        for _ln in (ROOT / "benchmarks" / "elo_games.jsonl").read_text().splitlines():
            try:
                _g = _json.loads(_ln)
            except Exception:
                continue
            for _slot, _nm in _g.get("field", {}).items():
                _sc = float(_g.get("scores", {}).get(_slot, 0) or 0)
                if _sc > _best.get(_nm, 0.0):
                    _best[_nm] = _sc
    except Exception:
        pass
    picks = set()
    for key, specs in by_hash.items():
        # Rated name wins (most games). Unrated/content ties -> OLDEST commit
        # (the content's origin — usually the code commit; a newer docs-only
        # successor must not shadow it and mint mirror matches when the fresh
        # brain is rated: newest-on-tie picked worklog twins as opponents).
        specs.sort(key=lambda bs: (-elo.get(f"{bs[0]}-{bs[1]}", {}).get("games", 0),
                                   order.get(bs[1], 10 ** 9)))
        b, sha = specs[0]
        _nm = f"{b}-{sha}"
        _g = elo.get(_nm, {}).get("games", 0)
        if _g >= 2 and _best.get(_nm, 0.0) <= 0.0:
            continue  # crashed bye: never scored
        picks.add(_nm)
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
    args = ap.parse_args(argv)
    m = BradleyTerryFull()
    elo = ratings()
    cands = pool()
    print(f"pool: {len(cands)} bots", flush=True)
    rng = random.Random(args.seed)
    fields = []
    for i in range(0 if args.play else args.n):
        f = propose(m, cands, elo, rng)
        fields.append(f)
        slots = " ".join(f"F{j}={b}" for j, b in enumerate(f))
        print(f"field {i + 1}: {slots}  info={info_score(m, f, elo):.2f}", flush=True)
    if args.play:
        from elo_field import update, ensure_master_engine, bot_cmd, master_map, sha_of
        ensure_master_engine()  # tip-of-master engine/runner (methodology)
        from engine.config import GameConfig  # noqa: E402 (main-tip)
        from runner.main import run_game  # noqa: E402
        cfg = GameConfig.from_dict(master_map())
        import time
        sys.path.insert(0, str(ROOT / "src"))
        _played = []
        fields = []
        for i in range(args.play):
            # Sequential: propose 1 on fresh ratings, play 1, update.
            f = propose(m, cands, elo, rng)
            fields.append(f)
            slots = " ".join(f"F{j}={b}" for j, b in enumerate(f))
            print(f"field {i + 1}: {slots}  info={info_score(m, f, elo):.2f}", flush=True)
            cmds = {}
            for slot, spec in enumerate(f):
                name, commit = spec.rsplit("-", 1)
                cmds[slot] = bot_cmd(name, sha_of(commit))
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
