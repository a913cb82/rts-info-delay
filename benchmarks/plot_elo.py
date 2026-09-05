"""Plot bot Elo over commits (one line per bot name).

Usage: PYTHONPATH=src .venv/bin/python benchmarks/plot_elo.py [--out docs/bot/elo.png]
X = commits in chronological order (only commits present in elos.json);
Y = Elo; one line per bot name (+ games-played annotations).
"""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commit_time(sha: str) -> int:
    out = subprocess.run(["git", "-C", str(ROOT), "show", "-s", "--format=%ct", sha],
                         capture_output=True, text=True)
    try:
        return int(out.stdout.strip())
    except Exception:
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/bot/elo.png")
    ap.add_argument("--elo", default=str(ROOT / "benchmarks" / "elos.json"))
    args = ap.parse_args(argv)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    elo = json.loads(Path(args.elo).read_text())
    by_bot: dict[str, list] = {}
    for key, v in elo.items():
        name, sha = key.rsplit("-", 1)
        by_bot.setdefault(name, []).append((commit_time(sha), sha, v["elo"], v["games"]))
    # commit order across all entries
    commits = sorted({sha for pts in by_bot.values() for _, sha, _, _ in pts},
                     key=commit_time)
    idx = {sha: i for i, sha in enumerate(commits)}
    short = [s[:7] for s in commits]
    plt.figure(figsize=(10, 6))
    for name, pts in sorted(by_bot.items()):
        pts = sorted(pts)
        xs = [idx[sha] for _, sha, _, _ in pts]
        ys = [e for _, _, e, _ in pts]
        gs = [g for _, _, _, g in pts]
        plt.plot(xs, ys, marker="o", label=f"{name} ({sum(gs)}g)")
        for x, y, g in zip(xs, ys, gs):
            plt.annotate(str(g), (x, y), fontsize=7, alpha=0.7)
    plt.xticks(range(len(commits)), short, rotation=45, ha="right")
    plt.xlabel("commit (chronological)")
    plt.ylabel("Elo")
    plt.title("Bot Elo over commits (FFA pairwise)")
    plt.legend(fontsize=8)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    out = ROOT / args.out
    plt.savefig(out, dpi=120)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
