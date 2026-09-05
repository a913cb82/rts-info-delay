"""Cut a scenario from a recording: world state N turns before an issue.

Usage: PYTHONPATH=src .venv/bin/python benchmarks/cut_scenario.py \\
    recordings/empty_10000.jsonl --turn 3600 --before 100 \\
    --focal 0 --teams 0=pro,1=pro,2=aggressive,3=expander,4=turtle \\
    --goal survive_capital --out maps/scenarios/r96_t3600.json

Snapshots truth positions (towns+armies) into map CSV; copies engine
config from the header; runs --before turns... actually starts AT
turn-before (bots play `turns` from there). Limitation: bot MIRRORS
start empty (positions replay, minds don't — learned intel like
blood/trails/notes is lost; mechanics reproduce, memory doesn't).
Pair with fog (what did the bot see?) to judge whether the issue
needs memory to trigger.
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("recording")
    ap.add_argument("--turn", type=int, required=True, help="issue turn")
    ap.add_argument("--before", type=int, default=100, help="start this many turns earlier")
    ap.add_argument("--turns", type=int, default=200, help="scenario length (max_turns)")
    ap.add_argument("--focal", type=int, default=0)
    ap.add_argument("--teams", default="0=pro,1=pro,2=aggressive,3=expander,4=turtle")
    ap.add_argument("--goal", default="survive_capital")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    header: dict = {}
    worlds: dict[int, dict] = {}
    with open(args.recording) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "world" not in r:
                header = r
                continue
            worlds[r.get("turn", 0)] = r["world"]
    if not worlds:
        print("no turns found", file=sys.stderr)
        return 1
    t0 = min(worlds, key=lambda k: abs(k - (args.turn - args.before)))
    w = worlds[t0]
    print(f"cut at turn {t0} (issue ~{args.turn})", file=sys.stderr)
    rows = ["x,y,type,population"]
    for x in w["towns"]:
        rows.append(f"{x['x']:.1f},{x['y']:.1f},{chr(ord('A') + x['faction'])},{round(x['population'])}")
    for a in w["armies"]:
        rows.append(f"{a['x']:.1f},{a['y']:.1f},{chr(ord('a') + a['faction'])},")
    teams = dict(kv.split("=") for kv in args.teams.split(","))
    d = {k: v for k, v in header.items() if k != "type"}
    d.update({"map": "\n".join(rows), "max_turns": args.turns,
              "teams": teams, "focal": args.focal,
              "goal": {"type": args.goal, "faction": args.focal}})
    with open(args.out, "w") as f:
        json.dump(d, f, indent=1)
    print(f"wrote {args.out} ({len(w['towns'])} towns, {len(w['armies'])} armies)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
