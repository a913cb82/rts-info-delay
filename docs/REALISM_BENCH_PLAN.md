# Realism benchmark plan — town growth mechanics

Branch: `experiment/realistic-growth` in worktree `/tmp/rl_realism`
(re-based onto `main` @ `f273926`).
Merge to `main`/`master` only when ready.

**Change policy:** measuring is free; changing mechanics is not.
No mechanic beyond the benchmark itself lands without explicit user
approval. Approved queue (NOT implemented — proposals only):

- exempt town-founding (`BUILD` new-town branch) from the 10km
  `interact_radius` merge check, so villages can pack densely
  (possibly snapping town locations to a 1km grid);
- keep army capture taking all towns within 10km in one turn
  (realistic as zone-of-control, no change needed).

This plan covers **how to measure realism only**. It deliberately does
**not** propose new mechanics. Any future mechanics proposal must be
scored by this bench, not designed alongside it.

## 1. Goal

Answer: "does our growth model, played optimally, produce something
that looks like a 1600s country on uniform terrain?"

From the prior discussion, "looks like" means:

- hierarchical sizes, not N equal towns (Zipf-ish: few big, many small),
- bottom tier space-filling (villages in every arable gap),
- spacing scales with size (villages ~3-4km, markets ~12-15km,
  regionals ~50km, capital on water),
- big-city costs visible (urban mortality / food-carting diseconomy),
- densities and growth rates in historical range (tens/km2,
  doubling ~100y+, cities as sinks without migration).

Current model (`src/engine/economy.py` in this worktree) is the red
baseline: logistic `r=0.001, K=100k` × `(1-Σcrowding)`, crowding
`(1+0.01·ln(Pn/P))·(0.1·√min(P,Pn)/d)^0.8` within 150km, death `<500`,
`TRAIN -1000 / BUILD +500`. Known optimum: `41×~42k uniform @150km`
(`benchmarks/solo_opt.py`, `maps/solo.json`). That optimum should
**fail** the realism bench below while passing the perf bench.

## 2. Non-goals / constraints

- No new mechanics in this step. No tuning. No bot changes.
- Keep the two guardrails that make this game usable:
  - **simplicity**: formula must stay closed-form per-town + pairwise;
    track param count, LOC, new state fields (target: ≤ current
    5 econ params + positions/pops, no per-town memory if avoidable).
  - **speed**: must stay in `crowding_nets_batch` shape (numpy/numba,
    cached dist matrix). Track `bench_suite.py` heavy-step time and a
    dedicated 500-town batch-growth microbench. Target: no regression
    beyond noise (~±5%), hard fail beyond ~2×.
- Growth bench must run in seconds like the fast suite (`<5s`), use
  engine-direct calls (no bots, no runner), deterministic (seeded).

## 3. Scale (SETTLED 2026-09-12: 1 turn = 1 week, game km = real km)

- **Time:** 1 turn = 1 week (`TURNS_PER_YEAR = 52`). Annualize any
  per-turn rate ×52 before comparing to history.
- **Distance:** game km are real km. Sanity: army 50km/week ≈ 7km/day
  (foot with baggage — plausible); messenger 150km/week ≈ 21km/day
  (horse, no relay — plausible order of magnitude). So spacing and
  density comparisons are direct, not scaled. The 150km crowding
  radius vs 12–15km historical market spacing is then a genuine
  finding, not a unit artifact.
- **Known structural block (noted, not changed):** `BUILD` merges into
  any town within 10km, so engine-playable layouts cannot pack denser
  than ~10km — villages at 3–4km are unbuildable today. The harness
  tests `economy.py` directly on synthetic layouts (bypassing `BUILD`)
  to score the *growth model* separately from the *build rule*; the
  build-rule exemption sits in the approved queue above.

## 4. Reference data (collect first, small file)

New file `benchmarks/realism_ref.json` (or `maps/realism/ref.json`):
handful of agreed historical anchors with sources, e.g. England/France
c.1600: capital share, top-5 city sizes, market-town size/spacing,
village size/spacing, rural density, urban baptisms<burials gap,
grain-carting cost distance. Each entry: value + range + source.
Bench asserts against ranges, never point values. Keep it <50 lines;
this file is the only "history" the bench may cite.

## 5. Harness (suite v3: scenarios + closeness, no verdicts)

`benchmarks/growth_realism.py` (engine-direct, no bots) +
`benchmarks/growth_systems.py` (generic interface):

```
python benchmarks/growth_realism.py                 # all, ~6s wall
python benchmarks/growth_realism.py macro           # subset
python benchmarks/growth_realism.py --system NAME   # score SYSTEMS[NAME]
```

Each item is a scenario (setup → run → observe) returning a closeness
score 0..1 against the ref band (log/linear falloff outside, one-sided
defeats scaled to the stakes); composite = mean. No binary verdicts:
the number is the verdict. Scenarios assert behavior, never mechanism;
isolated towns appear only at self-feeding sizes (<= ~1k) — anything
bigger runs with its hinterland in the World. Checks call ONLY
`G.isolated` / `G.nets` / `G.step`. New mechanics register a system in
`growth_systems.py`; this file changes only to ADD scenarios, never to
pass one. Current roster (15): village_rate, recovery, viability,
infill, hierarchy, market_penalty, sustain, urban, gapfill, sinkflow,
access, returns, macro, hinterland, perf. Composite = report table, not a
single number (avoid Goodharting one scalar). Perf guardrail runs
alongside and fails loud on regression.

Suggested groups (names only — thresholds set after red-baseline run):

1. **Solo-optimum shape** (the core test). Reuse `solo_opt.py`
   optimizer on `solo.json`, then measure the *winner's* layout:
   - size inequality (Gini / CV / Zipf slope over rank-size regression),
   - spacing-vs-size slope (nearest-neighbour distance regressed on
     log pop — realistic: positive slope; current: ~flat),
   - small-town share (fraction of pop in bottom tier).
   Current optimum (`41 uniform`) must fail all three. This is the
   test that forces hierarchy to be *optimal*, not merely allowed.
2. **Small-viability.** Single isolated towns at 200 / 500 / 1000 /
   2500 pop for N turns: which persist, which grow? Realistic: 200-500
   stable-or-growing in isolation (villages don't evaporate). Current
   death `<500` must fail this — recorded as expected-red.
3. **Interaction shape.** Two-town fixtures sweeping `d` and size
   ratio: marginal growth penalty vs distance/size. Asserts qualitative
   shape only (penalty falls with distance, rises with neighbour size,
   asymmetric big-on-small vs small-on-big) and reports the effective
   radius in game units for the scale note in §3.
4. **Tile sustainability** (`sustain`). Every tier of the reference
   tile (784x250 vill @3.6km + 25x2800 mkt @17.9km + 4x8500 reg @50km,
   300k on 100x100km = 30/km2) must mean-net >= 0. Retired the v1
   static 41x42k constant, which scored the old optimum, not the
   candidate system.
5. **Dynamics sanity.** Halve a mature town (plague/sack fixture),
   measure recovery time in turns → convert via §3 turn↔year mapping
   → compare to historical post-plague recovery (decades). Checks the
   logistic shape near and far from cap, independent of layout.
6. **Sink + migration circuit** (`sinkflow`: SINK isolated 80k must
   shrink; FUEL ringed 60k city must net above its isolated rate;
   SHARE ring villages below theirs; BOOKS system total within 25% of
   the isolated sum). API-agnostic: asserts trajectories, not plumbing.
8. **Market access** (`access`, force 2 benefit): ring villages with a
   market net >= 1.05x the identical ring without (ref floor, provisional).
9. **Increasing returns** (`returns`, force 3 proxy): some doubling must
   more than double isolated net (threshold goods need scale). Placed
   threshold/co-location effects deferred (need a goods ontology).
10. **Macro ranking** (`macro`): hierarchical tile outgrows uniform-big,
    uniform-mid and all-village at equal pop on equal area, AND sustains
    itself. Discriminates real fixes from cap-raising.
11. **Perf + simplicity guardrail.** 500-town batch-growth ms,
   heavy-step ms, econ param count, new per-town state fields. Same
   box, paired, min-of-3 like `optimization_log.md`. Fails on >~2×
   slowdown or new O(N²) beyond the existing dist matrix.

## Deferred (need ontologies that do not exist yet — not forgotten)

- Shock insurance / redistribution (force 2): bad-year fixture needs
  shock semantics in the engine (variance, not just means).
- Catchment areas (force 1 mechanism): exclusive-land logic needs a
  land/area representation; signs are covered by infill/gapfill/macro.
- Service co-location / tier ratios (force 3 structure): needs goods
  with thresholds/ranges; lumpiness proxied by `returns` meanwhile.
- Water trade (force 2 exception): no terrain/water in the engine;
  correctly out of scope until maps have rivers.

## 6. Workflow

1. Collect `realism_ref.json` (small, sourced ranges).
2. Settle §3 constants (units note + turn↔year mapping, even if
   provisional).
3. Implement harness with current mechanics, run red baseline, record
   which checks fail and by how far (that gap sizes the later task).
4. Freeze thresholds with slack (ranges, not points; cf. fog-era
   table policy in `docs/bot/METHODS.md`).
5. Only then propose mechanics — each scored by this bench + existing
   `bench_suite.py` + `scenario_bench.py`/`strategic_bench.py` green.

## 7. Explicitly deferred

- Any specific formula (agglomeration bonus, catchment area, urban
  mortality, transport cost, land productivity). Those are the
  experiment, not the ruler.
- Bot-visible consequences (settle spacing, TRAIN cadence). Bots adapt
  after mechanics land; bench stays engine-direct.
- Map work (micro-county maps, terrain). Revisit only if §3 option A
  proves insufficient.
