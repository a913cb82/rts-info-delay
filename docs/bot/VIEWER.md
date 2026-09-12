# How we analyze (the viewer tool)

Loop step 2 runs on one tool: `benchmarks/ascii_view.py` (plus the web
viewer at `http://localhost:5173/` for watching replays).

## ASCII grid (human)

```bash
python benchmarks/ascii_view.py recordings/empty_10000.jsonl \
  --turns 5000 --size 50x50 --no-color --mode all
```

- `--mode`: `glyph` (shapes: ● town ◆ capital ▲ army ×N stack * clash),
  `pop` (log buckets: doublings from 500), `faction` (digits),
  `all` (2-char F+T cells: faction + type/pop/count), `cluster`
  (faction + cluster letter).
- `--size WxH` (default 50x50, square like the map).
- Footer: per-faction pop/towns/armies/capital pop + legend.

## ACJSON (LLM): `--format acjson`

Augmented Cartesian JSON — same quantization + collision priority as
the grid, so both agree cell-for-cell. Sparse non-empty cells (x/y +
kind/faction/pop/ids) plus precomputed geometry (no LLM math):

- `relations`: per town nearest foe/own (dist/dir/pop); per faction
  centroid/spread/neighbors/capital-offset/named clusters (label, pop,
  centroid, radius, members, capital bearing, nearest foe cluster).
- `views`: per-capital 8-ray first-hit (`N: T17f3@147`, `-` = open).
- `deltas`: score at symmetric offsets (`--deltas 100,10,1`,
  then-minus-now, null off-record).
- `--compact` for token discipline.

## Standard analysis (report card recipe)

1. Report: `--format report` (full-game brief in one command: activity
   per faction, stagnation list, onesies, punishable thin towns).
   Start here — it rederives viewer feedback without watching.
2. Quartiles: `--turns 2500,5000,7500,10000 --format acjson --compact`
   (factions + deltas + clusters tell the arc).
2. Fog (`--format fog --faction F --turns T`: what the bot saw — ghosts/staleness first, truth second).
3. Autopsy: `--format autopsy --window 7800-8000` (death ledger:
   who fed whom where; `ONESIES` flags >= 3 losses by one faction
   at one town — the suicide detector; default last 1000 turns).
4. Full sweep (11 snapshots) when quartiles show something odd.
5. ascii `--mode all` at war turns (who stood where).
6. Event ledger (`town_spawn/death/capture`, battles) per millennium.
7. Per-bot well/badly + filed ideas → worklog report card.

## lead / flip (lead-change analysis)

- `ascii_view.py REC --format lead`: pop/towns/armies per faction per
  millennium + FLIP lines (who took the lead, when).
- `ascii_view.py REC --format flip --faction F --window A-B`: F's lost
  towns, takes, battles with counts/coords, plus F's town/army arc
  (did it react?). Pair with `fog --faction F --turns T` (what did it
  see?) for full Hunter's-loop diagnosis.

## Playback speeds (viewer)

Controls: 0.5× … 8× (tweened), then turbo tiers 16× / 64× / 256× / 1024×
/ 4096×. Above 4× the per-turn tween is skipped (a jump shows the same
thing for less work) and the scene redraws at most every 50 ms while
turns keep advancing every animation frame — playback rate is decoupled
from render cost (draw() is dominated by SVG/DOM churn and the 10k-point
score graph, none of which need 60 Hz). Pausing/stepping always draws.
4096× clears a 10k-turn game in ~1s on this box.

## Adaptive playback ("auto" speed)

This game is bursty: in the quad recording 59% of all action falls in 10%
of the turns (t3000-4000). The viewer can steer playback speed by action:

- Enable with the **auto** checkbox (or `&auto=1` in the URL). The speed
  select then means the QUIET/max speed; while action is near, playback
  drops to ~2x and ramps back up after.
- Action signal = weighted events per turn: capture 3, battle 3,
  founding 2, town death 2, army train 1, army death 1. Weights are
  module constants (`AUTO_FULL`, `AUTO_SLOW`, `AUTO_LOOKAHEAD`,
  `AUTO_LINGER`, `AUTO_STEP_CAP` in `viewer/src/main.ts`).
- Faction-aware: with a faction selected via the fog selector the signal
  is THAT faction's action (watch one bot's war); with none selected it
  is global (any action slows playback).
- Lookahead 5 turns (brake BEFORE the burst) + linger 8 (stay slowed
  through the aftermath); braking is fast (0.5/frame), release slow
  (0.08/frame). Under auto, turns advance at most 12/frame so a burst
  can never be skipped between frames.
- The live effective multiplier is shown next to the checkbox.
