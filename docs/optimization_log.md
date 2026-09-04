# Engine Optimization Log

## Baseline (before any optimizations)

Benchmarked at commit `bed4967` (bench suite creation).

| Benchmark | Baseline (ms) |
|---|---|
| step heavy 207t+3036a (t19→20) | 11,732 |
| crowding 500 towns (per-town) | 203 |
| movement heavy 3036a vs 207t | 1,596 |
| movement 1000 armies +100 towns | 787 |
| weakness 1000 armies | 398 |
| combat 200 armies | 20.5 |
| movement 200 armies +100 towns | 14 |
| captures 100 armies vs 100 towns | 12 |
| crowding batch 500 | — (didn't exist) |
| step no armies full 415 towns | 0.09 |
| economy apply_growth full 415 towns | 0.06 |
| step no armies empty 5 towns | 0.07 |
| economy apply_growth empty 5 towns | 0.05 |

---

## opt1-2: World id index + Economy dist-matrix batch

**Commit:** `a815ccb`
**Changes:**
- `world.py`: `_army_by_id`, `_town_by_id` dicts for O(1) `get_army`/`get_town` with `_ensure_indexes()` lazy rebuild + `_index_dirty` flag
- `economy.py`: `_get_dist_matrix()` caches NxN `D` matrix (static positions), `crowding_nets_batch()` with numba `@njit` inner loop

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| step heavy 207t+3036a | 11,732 | 8,807 | 1.33× |
| crowding 500 | 203 | 54 | 3.8× |
| crowding batch 500 | — | 1.6 | new |
| movement heavy 3036a | 1,596 | 855 | 1.87× |
| movement 1k | 787 | 855 | — |
| weakness 1k | 398 | 398 | — |
| combat 200 | 20.5 | 20.5 | — |

---

## opt3-4: Movement spatial hash + Combat squared reject

**Commit:** `7e5db8d`
**Changes:**
- `movement.py`: `SpatialHash cell=60`, `query_radius(110)` army-army, `query_radius(60)` army-town
- `combat.py`: `dx*dx+dy*dy ≤ R²` before hypot in all distance checks; adaptive hash for n≥400

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| step heavy 207t+3036a | 8,807 | 4,466 | 1.97× |
| crowding 500 | 54 | 69 | — (noise) |
| movement heavy 3036a | 855 | 307 | 2.78× |
| movement 1k | 855 | 168 | 5.09× |
| weakness 1k | 398 | 24 | 16.6× |
| combat 200 | 20.5 | 16 | 1.28× |
| captures 100 | 12 | 1.6 | 7.5× |

---

## opt5: Economy batch numba

**Commit:** `5022004`
**Changes:**
- `economy.py`: `@njit _batch_numba_inner` at module level, pre-compiled; `crowding_nets_batch()` calls numba inner for 500 towns

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| crowding batch 500 | 272 | 0.95 | 286× |
| crowding 500 per-town | 69 | 68 | — |
| step heavy | 4,466 | 4,612 | — (noise) |

---

## opt6: Stacked insta-kill + allocate_id guard (semantic change, not pure opt)

**Commit:** `c7a2f69` (code) + `02308b9` (test fix)
**Changes:**
- `economy.py`: Stacked insta-kill — towns at `dist<1e-9` where lower-or-equal pop dies (`total += 1e6`); higher ignores the neighbour. All economy paths unified on this rule (see code: `_STACKED_KILL`)
- `world.py`: `allocate_id()` collision guard for manually-assigned test IDs
- `tests/`: Split `test_move_capital_old_capital_demoted` (non-stacked target) + new `test_move_capital_stacked_die`
- NOTE (correction 2026-09-04): an earlier version of this entry claimed a ledger vectorization (`visible_events`, `_by_turn`). That work was never committed — `ledger.py` is untouched. The measured delta below is therefore unattributed (likely run-to-run noise/JIT); do not cite it as a ledger result.

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| step heavy 207t+3036a | 4,612 | 3,336 | 1.38× (unattributed — see note) |
| movement heavy 3036a | 307 | 244 | — (noise) |
| movement 1k | 168 | 136 | — (noise) |
| crowding 500 | 69 | 54 | — (noise) |
| weakness 1k | 24 | 19 | — (noise) |
| combat 200 | 16 | 13.5 | — (noise) |
| crowding batch 500 | 0.95 | 0.82 | — (noise) |
| captures 100 | 1.6 | 1.55 | — (noise) |

---

## opt7: Step economy batch crowding

**Commit:** `4845603`
**Changes:** `step.py:_phase_economy` replaced per-town `crowding_net` loop with `crowding_nets_batch`.

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| step heavy 207t+3036a | 3,336 | 3,330 | — (negligible) |
| crowding 500 | 54 | 54 | — |

Conclusion: crowding batch was already 0.8ms; bottleneck was in combat, not economy.

---

## opt8: Combat single-pass weakness+adjacency

**Commit:** `4e2575f`
**Changes:**
- `combat.py`: Added `_compute_weaknesses_and_adj()` — single-pass builds both weakness dict and adjacency dict using spatial hash (n≥400) or brute (n<400)
- `resolve_combat`: Uses pre-built adjacency for death determination (eliminates duplicate `_enemies_within_radius` O(n²) pass and separate adjacency O(n²) pass)
- `compute_weaknesses` kept backward-compatible (returns dict only)

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| step heavy 207t+3036a | 3,336 | 975 | 3.42× |
| combat 200 | 13.5 | 5.44 | 2.48× |
| weakness 1k | 19 | 16.79 | 1.13× |
| movement heavy 3036a | 244 | 227 | 1.07× |
| crowding 500 | 54 | 52 | — |

---

## opt9: Movement simplified velocities + inlined closest-approach

**Commit:** `c0a78fe`
**Changes:**
- `movement.py`: simplified velocity loop (plain lists; a numpy-array experiment was tried, slowed movement 227→328ms, reverted), inlined `_closest_approach` math into the contact loop to avoid per-pair Python call overhead
- NOTE (correction 2026-09-04): the commit message claims "numpy velocity arrays" — the landed code uses plain lists. Gain is marginal, within run-to-run noise.

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| step heavy 207t+3036a | 975 | 956 | — (noise) |
| movement heavy 3036a | 227 | 217 | — (noise) |
| movement 1k | 134 | 123 | — (noise) |

---

## opt10: Economy cache soundness + per-town numba row (correctness first)

**Commit:** (pending — working tree)
**Changes:**
- `economy.py`: replaced unsound `id(list)`-keyed caches (false hits when tests reuse small tids across cases) with id-keyed + full element-identity validation against strong refs; `_crowding_cache` now always reads fresh pops (killed the stale-middle-pops bug); dead `_log_cache`/`_towns_key` removed
- `economy.py`: unified stacked rule (`_STACKED_KILL`) across all 6 code paths (dist-matrix, hash, numpy cache path, 2× pure loops, batch fallback) — previously they disagreed (insta-kill vs cap-at-d_eq vs 1e-6)
- `economy.py`: new `_row_numba_inner` single-row kernel (same math/order as batch kernel, bit-identical) + import-time pre-compile so first call never pays ~600ms JIT latency
- `combat.py`: merged 3 duplicated weakness implementations into `_brute_weakness_adj` + hash attempt with brute fallback; `compute_weaknesses` is now a thin wrapper (signature unchanged)
- Numbers below are paired back-to-back on the same loaded machine (absolute values inflated ~1.8× vs the quiet-machine runs above — see note).

| Benchmark | Before (same box) | After (same box) | Change |
|---|---|---|---|
| crowding 500 | 97.7 | 49.8 | 1.96× (numba row + C-speed lookup) |
| step heavy 207t+3036a | 1,737 | 1,681 | neutral (noise band) |
| movement 1k | 220 | 201 | neutral |
| weakness 1k | 35 | 30 | neutral |
| combat 200 | 8.1 | 5.6 | neutral |

NOTE on absolutes: this box measured ~1.8× slower than the runs behind the tables above (pristine HEAD also measures 1,737ms heavy here vs 956ms earlier). All cross-commit deltas above remain valid (each was paired); do not compare absolute numbers across machine states.

---

## opt11 and on

### opt11: Movement batch cell-pair + town batch — DONE (`1223ae5`)
- Army contacts: iterate hash cells once with a forward-half 13-stencil (Chebyshev ≤ 2 covers the 110 query disc at cell 60); each unordered pair evaluated once per moving direction with the same disc cutoff (`110²+2e-9`) and scalar math. Eliminates ~2400 `query_radius` calls + result lists per step
- Town contacts: per town, walk army-hash 3×3 stencil (covers 60 disc) instead of per-army town queries; separate town hash deleted
- Detour (reverted): numpy-vectorized closest-approach — byte-identical but a wash end-to-end (query overhead, not math, dominated); small cases regressed on vector setup cost. Reverted to scalar
- Equivalence: heavy-step events byte-identical before/after (448KB JSON diff clean); full suite green

| Benchmark (paired, same box) | Before | After | Change |
|---|---|---|---|
| movement heavy 3036a | 361 | 177 | 2.04× |
| movement 1k | 195 | 73 | 2.67× |
| movement 200 | 11.9 | 8.2 | 1.45× |
| step heavy 207t+3036a | 1,477 | 1,374 | 1.07× (movement is only part of step) |

### opt12: Combat event-building + batch removal — DONE (`9e9db31`)
- Phase profile showed combat at 977ms min (70% of step) AFTER opt8: the weakness itself was fast, but event building did O(n) linear `next()` scans per member (~4 sites) and `remove_army` rebuilt both lists per dead army — O(n²) + O(dead×A)
- `combat.py`: single `by_id` dict for all lookups; `world.remove_armies(ids)` batch single-pass removal (kept `remove_army` as delegating wrapper for other callers)
- `combat.py`: same-faction fast path (the sound core of the ants `do_attack_support` idea adapted to our rule — full weakness is still required for mixed factions, so a broader pre-filter is unsound here)
- Equivalence: heavy-step events byte-identical; full suite green

| Benchmark (phase profile, min of 3) | Before | After | Change |
|---|---|---|---|
| combat phase 207t+3036a | 977 | 170 | 5.75× |
| movement phase | 154 | 170 | — (noise) |
| economy phase | 1.1 | 1.1 | — |

### opt13: Cached faction queries + hoisted capture bookkeeping — DONE (`0ca4d50`)
- Premise correction: `record.py` only serializes on save (no per-step scan), so "incremental pop_total" was based on a false premise. The real per-step faction cost was 169 `faction_capital` O(T) calls + per-capture `any()` scans (~5-10ms total, <1% of step)
- `world.py`: `faction_capital`/`towns_for_faction`/`armies_for_faction` now use the (previously built-but-unused) faction caches; first-capital-wins order preserved to match old linear scan
- Correctness: every in-place faction/is_capital mutation site marks dirty (combat captures ×3 branches via end-of-phase mark, step viceroy ×2, events replay ×1); appends/removals already invalidated via len/dirty flag
- `combat.py`: triplicated capture-application blocks → single `_apply_capture` helper over a hoisted book (capital dict + town counts + viceroy set), eliminating all per-capture scans
- Verdict: back-to-back paired heavy step 441→478ms = neutral (noise). Kept for the cleanup + query-heavy paths (runner/bots). Full suite + byte-identical heavy events

### opt14: Shared army hash per step — EVALUATED, REJECTED (measured)
- Measured hash builds on heavy scale: army c60 10.1ms + combat c10 6.7ms ≈ 17ms/step total
- True sharing is impossible movement→combat: armies move between phases, so a pre-movement grid is stale post-movement; incremental updates touch ~80% of armies ≈ full rebuild cost
- Only shareable portion (combat→captures, ~7ms) needs cross-phase grid plumbing with index-remapping (combat hash indexes a fresh-filtered subset list) — staleness hazard for <2% of step
- Verdict: rejected. Batch iteration (opt11) already removed the per-query costs that made sharing attractive; remaining builds are O(A) inserts, not O(n²)

### opt15: Ledger visibility — DONE (`004f4f3`)
- Measured first: 6395 events after 10 heavy turns; 5× `visible_events` = 27ms/turn, `turn_events` = 1.2ms (paired; earlier claimed numbers were noise)
- `ledger.py`: `_version` counter bumped on log/evict + cached (xs, ys, ts) arrays shared across the 5 per-turn faction queries (one build ≈ 1ms + 5× 0.2ms vector math); `_by_turn` index with evict-sync for O(1) `turn_events` (int-turn fast path + scan fallback)
- Ledger + bot-side tests green; runner-side cost, so engine-step bench is unaffected by design

| Benchmark (paired ledger bench) | Before | After | Change |
|---|---|---|---|
| 5× visible_events @6395 evts | 27 | 2.3 | 11.7× |
| turn_events | 1.2 | ~0.0 | →0 |

### opt16: Allocation/GC pressure — EVALUATED, REJECTED (measured)
- gc-off-vs-on single-step test suggested spikes (1501ms max vs 367ms), but that was a bench artifact: fresh 3k-army world per rep + dead-world garbage forced full collections
- Real-game simulation (world reused, 20 turns): turn1 1204ms one-off (cold caches + setup-garbage collection), then 65→15ms declining as armies die — zero GC pauses across 20 turns, gen counts stay flat
- Verdict: no production GC problem, no code change. (`gc.disable` was considered and rejected: unbounded growth in long-lived bot/runner processes for zero steady-state gain.)
- Side finding: steady-state steps are 15–65ms, far below the fixed heavy-snapshot bench (~366ms) — the bench replays a full 3036-army turn that combat eliminates by turn 2–3, so it overstates real per-turn cost ~10×

---

## Cumulative Performance

| Benchmark | Baseline | Now | Total speedup |
|---|---|---|---|
| step heavy 207t+3036a | 11,732ms | **956ms** | **12.3×** |
| crowding 500 | 203ms | 52ms | 3.9× |
| crowding batch 500 | — | 0.77ms | — |
| movement heavy 3036a | 1,596ms | 217ms | 7.4× |
| movement 1k | 787ms | 123ms | 6.4× |
| weakness 1k | 398ms | 17ms | 23.4× |
| combat 200 | 20.5ms | 5.19ms | 3.9× |
| captures 100 | 12ms | 1.47ms | 8.2× |
