"""Plot the bot skill frontier (one running-max line per personality).

Usage: PYTHONPATH=src .venv/bin/python benchmarks/plot_elo.py [--out docs/bot/elo.png]
X = commit datetime. Y = OpenSkill ordinal (mu-3sig).
Shows ONLY improvements: the running max over master-lineage commits per
personality (a flatline = regression or stall, honestly shown). Current
branch-tip bots plot as faded x markers — above the frontier = merge.
Target ordinal 50 dashed for reference.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
from matchmake import brain_hash  # noqa: E402

PERSONALITIES = ["pro", "aggressive", "expander", "turtle"]
TARGET = 50.0


def commit_time(sha: str) -> int:
    out = subprocess.run(["git", "-C", str(ROOT), "show", "-s",
                          "--format=%ct", sha],
                         capture_output=True, text=True)
    try:
        return int(out.stdout.strip())
    except Exception:
        return 0


_ancestor_cache: dict[str, bool] = {}


def on_master(sha: str) -> bool:
    if sha not in _ancestor_cache:
        r = subprocess.run(["git", "-C", str(ROOT), "merge-base",
                            "--is-ancestor", sha, "main"],
                           capture_output=True, text=True)
        _ancestor_cache[sha] = (r.returncode == 0)
    return _ancestor_cache[sha]


_hash_cache: dict[tuple[str, str], str] = {}


def bhash(ref: str, bot: str) -> str:
    key = (ref, bot)
    if key not in _hash_cache:
        try:
            _hash_cache[key] = brain_hash(ref, bot)
        except Exception:
            _hash_cache[key] = ""
    return _hash_cache[key]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/bot/elo.png")
    ap.add_argument("--elo", default=str(ROOT / "benchmarks" / "elos.json"))
    args = ap.parse_args(argv)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    elo = json.loads(Path(args.elo).read_text())
    pts: dict[str, list] = {b: [] for b in PERSONALITIES}
    for key, v in elo.items():
        name, sha = key.rsplit("-", 1)
        if name not in pts or v.get("games", 0) < 1 or not on_master(sha):
            continue
        pts[name].append((datetime.fromtimestamp(commit_time(sha)), sha,
                          v["mu"] - 3 * v["sigma"], v["games"]))

    fig, ax = plt.subplots(figsize=(12, 6))
    frontiers: dict[str, float] = {}
    for name in PERSONALITIES:
        series = sorted(pts[name])
        if not series:
            continue
        # running max (frontier): only improvements are drawn
        fx, fy, fl = [], [], []
        best = float("-inf")
        for dt, sha, o, g in series:
            if o > best:
                best = o
                fx.append(dt)
                fy.append(o)
                fl.append(f"{sha[:7]}({g}g)")
        (ln,) = ax.plot(fx, fy, drawstyle="steps-post", marker="o",
                        linewidth=2, label=f"{name} (best {best:.1f})")
        frontiers[name] = best

    # branch-tip bots: drawn ONLY if they beat the frontier (an actual
    # improvement). Below-bar candidates are not shown.
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse",
                           "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if not on_master(head):
        for name in PERSONALITIES:
            hb = bhash("HEAD", name)
            if not hb:
                continue
            for key, v in elo.items():
                n, sha = key.rsplit("-", 1)
                if n != name or v.get("games", 0) < 1:
                    continue
                if bhash(sha, name) == hb:
                    o = v["mu"] - 3 * v["sigma"]
                    if o > frontiers.get(name, float("-inf")):
                        x = datetime.fromtimestamp(commit_time(head))
                        ax.scatter([x], [o], marker="*", s=120,
                                   alpha=0.8, color="black", zorder=5)
                    break

    ax.axhline(TARGET, color="gray", linestyle="--", linewidth=1,
               alpha=0.6)
    ax.annotate("target 50", (ax.get_xlim()[0], TARGET), fontsize=8,
                color="gray", va="bottom")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate()
    ax.set_xlabel("commit datetime")
    ax.set_ylabel("frontier ordinal (running max, mu-3sig)")
    ax.set_title("Bot skill frontier — improvements only (star = branch beats bar)")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = ROOT / args.out
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
