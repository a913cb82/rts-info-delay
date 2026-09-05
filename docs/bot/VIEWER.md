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

1. Quartiles: `--turns 2500,5000,7500,10000 --format acjson --compact`
   (factions + deltas + clusters tell the arc).
2. Autopsy: `--format autopsy --window 7800-8000` (death ledger:
   who fed whom where; `ONESIES` flags >= 3 losses by one faction
   at one town — the suicide detector; default last 1000 turns).
3. Full sweep (11 snapshots) when quartiles show something odd.
4. ascii `--mode all` at war turns (who stood where).
5. Event ledger (`town_spawn/death/capture`, battles) per millennium.
6. Per-bot well/badly + filed ideas → worklog report card.
