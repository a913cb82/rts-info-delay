"""Loop status: the four personalities' current ratings + the worst performer.

One iteration = fix the worst performer (docs/bot/README.md). This prints
each package personality's newest rated brain (the newest main commit
that touched src/bots/<p>/), its ordinal/mu/games, and marks the target.

Usage: PYTHONPATH=src python benchmarks/status.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONALITIES = ["pro", "aggressive", "expander", "turtle", "grower"]
MIN_GAMES = 10


def newest_sha(p: str) -> str | None:
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%h",
                          "-1", "--", f"src/bots/{p}/"],
                         capture_output=True, text=True).stdout.strip()
    return out or None


def main() -> int:
    elo = json.loads((ROOT / "benchmarks" / "elos.json").read_text())
    rows = []
    for p in PERSONALITIES:
        sha = newest_sha(p)
        name = f"{p}-{sha}" if sha else None
        v = elo.get(name, {}) if name else {}
        if not v and sha:
            # fall back to the rated brain this package's hash dedups to
            try:
                sys.path.insert(0, str(ROOT / "benchmarks"))
                from matchmake import brain_hash  # noqa: E402
                h = brain_hash(sha, p)
                for k, vv in elo.items():
                    if not k.startswith(p + "-") or vv.get("games", 0) == 0:
                        continue
                    ksha = k.rsplit("-", 1)[1]
                    if brain_hash(ksha, p) == h:
                        v = vv
                        name = k
                        break
            except Exception:
                pass
        o = (v.get("mu", 0.0) - 3 * v.get("sigma", 8.33)) if v else None
        rows.append((p, name, o, v.get("mu"), v.get("games", 0)))
    ranked = sorted([r for r in rows if r[2] is not None and r[4] >= MIN_GAMES],
                    key=lambda r: r[2])
    worst = ranked[0][0] if ranked else None
    print(f"{'personality':12} {'brain':24} {'ord':>6} {'mu':>6} {'games':>6}")
    for p, name, o, mu, g in rows:
        mark = "  <- WORST (next loop's target)" if p == worst else ""
        if o is None:
            print(f"{p:12} {'(unrated)':24} {'-':>6} {'-':>6} {g:>6}")
        else:
            print(f"{p:12} {name:24} {o:6.1f} {mu:6.1f} {g:6d}{mark}")
    if not ranked:
        print("(no personality has >=%d rated games yet)" % MIN_GAMES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
