"""Plot bot Elo over commits (one series per bot name).

Usage: PYTHONPATH=src .venv/bin/python benchmarks/plot_elo.py [--out docs/bot/elo.png]
X = commit datetime (actual commit timestamp, not commit index).
Y = ordinal (mu-3sigma); games-played annotations per point.
Commits on master's lineage are solid; off-master (loop branches) are
faded — branch experiments read as faint suggestions, master as the record.
"""
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commit_time(sha: str) -> int:
    out = subprocess.run(["git", "-C", str(ROOT), "show", "-s", "--format=%ct", sha],
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
    by_bot: dict[str, list] = {}
    for key, v in elo.items():
        name, sha = key.rsplit("-", 1)
        if v.get("games", 0) < 1:
            continue
        dt = datetime.fromtimestamp(commit_time(sha))
        by_bot.setdefault(name, []).append(
            (dt, sha, v["mu"] - 3 * v["sigma"], v["games"]))

    fig, ax = plt.subplots(figsize=(12, 6))
    for name, pts in sorted(by_bot.items()):
        master = sorted(p for p in pts if on_master(p[1]))
        branch = sorted(p for p in pts if not on_master(p[1]))
        color = None
        total_g = sum(g for _, _, _, g in pts)
        if master:
            xs = [p[0] for p in master]
            ys = [p[2] for p in master]
            (ln,) = ax.plot(xs, ys, marker="o", linewidth=2,
                            label=f"{name} ({total_g}g)")
            color = ln.get_color()
            for x, y, g in zip(xs, ys, [p[3] for p in master]):
                ax.annotate(str(g), (x, y), fontsize=7, alpha=0.7,
                            color=color)
        if branch:
            xs = [p[0] for p in branch]
            ys = [p[2] for p in branch]
            ax.scatter(xs, ys, marker="x", s=36, alpha=0.25,
                       color=color, label=(None if master else f"{name} ({total_g}g)"))
            if not master:
                color = "gray"
            for x, y, g, sha in [(p[0], p[2], p[3], p[1]) for p in branch]:
                ax.annotate(f"{sha[:7]}:{g}", (x, y), fontsize=6,
                            alpha=0.35, color=color)
        if not master and branch:
            # label branch-only series once
            pass
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate()
    ax.set_xlabel("commit datetime")
    ax.set_ylabel("ordinal (mu-3sig)")
    ax.set_title("Bot skill over time (OpenSkill ordinal; solid=master, faded=branch)")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = ROOT / args.out
    fig.savefig(out, dpi=120)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
