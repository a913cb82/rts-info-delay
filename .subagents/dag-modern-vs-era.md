# Why do modern bots underperform the historic peaks?

## Bars (live, drifting)
pro 48.6 @42aba25 · aggressive 42.1 @ffcfe0e · expander 42.3 @84b32be · turtle 38.9 @850b426
Modern tip = main 7465955. Peaks are era r29-r100 (Sep 5).

## Wave (cap 4)
| id | task | output contract |
|----|------|-----------------|
| A-common | arch: diff common.py peak-era vs modern, catalog gates | ≤10 ranked changes: name/blocked-behavior/size/direction |
| B-person | arch: diff each personality peak vs modern | per-personality: additions/removals, opener changes, verdict |
| C-behav | empirical: era-vs-modern matched games, arc traces | per-personality mechanism of modern loss + turn-stamped evidence |
| D-panel | controlled: era & modern vs FIXED neutral panel | win/loss + score medians per bot; is the gap real or pool-drift |

Discipline: read-only repo; /tmp for records; no commits; no worktree prune.
Games: PYTHONPATH=src python benchmarks/elo_field.py --field ... --games 1
       (~90s/game; budget ~1500s ⇒ ≤10 games each)
Tools: benchmarks/ascii_view.py --format flip/report/lead
