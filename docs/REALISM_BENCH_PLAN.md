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

## 5. Proposed harness

New file `benchmarks/growth_realism.py` (engine-direct, no bots):

```
python benchmarks/growth_realism.py            # all checks, <5s
python benchmarks/growth_realism.py hierarchy  # subgroup
```

Each check: build town list in-memory → call `logistic` /
`crowding_net` / `crowding_nets_batch` / `apply_growth` → return
metric + target range + pass/fail. Composite = report table, not a
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
4. **Density plausibility.** Max sustained pop/km2 on a filled optimum
   vs reference range. Expected-red now (game gives ~1.7/km2 vs
   historical tens/km2) — mostly documents the scale gap.
5. **Dynamics sanity.** Halve a mature town (plague/sack fixture),
   measure recovery time in turns → convert via §3 turn↔year mapping
   → compare to historical post-plague recovery (decades). Checks the
   logistic shape near and far from cap, independent of layout.
6. **Sink + migration circuit** (`sinkflow`: SINK isolated 80k must
   shrink; FUEL ringed 60k city must net above its isolated rate;
   SHARE ring villages below theirs; BOOKS system total within 25% of
   the isolated sum). API-agnostic: asserts trajectories, not plumbing.
7. **Perf + simplicity guardrail.** 500-town batch-growth ms,
   heavy-step ms, econ param count, new per-town state fields. Same
   box, paired, min-of-3 like `optimization_log.md`. Fails on >~2×
   slowdown or new O(N²) beyond the existing dist matrix.

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
