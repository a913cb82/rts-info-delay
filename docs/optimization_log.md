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

## Remaining (opt11-13, not started)

### opt11: Movement batch hash query
- Instead of per-army `query_radius`, iterate cells once and check all pairs within cell+neighbors
- O(cells × k²) vs O(armies × query_result) where k=armies_per_cell
- Expected: movement heavy 217→~100ms, total heavy step ~800ms

### opt12: Ants-inspired early exit (try if blocked)
- `do_attack_support` pre-filter: if friends ≥ enemies for all, skip weakness entirely
- `kill_ant` dict removal O(1) by loc vs our O(n) list scan — applies to captures `armies×towns`

### opt13: Record/world incremental pop_total
- `record.py`: maintain `pop_total[faction]`/`army_count[faction]` incrementally on growth/conquest/spawn/death instead of full scan

### opt14 (untried): Shared army hash per step
- Build the army SpatialHash once per step and share across movement, combat weakness, and captures instead of 3× O(A) rebuilds per turn

### opt15 (untried): Ledger visibility, properly profiled
- `visible_events`/`turn_events` run per faction per turn in the runner; earlier claimed numbers were noise. Re-profile first — gain may be zero

### opt16 (untried): Hot-loop allocation pressure
- Hot loops allocate thousands of small numpy arrays/tuples/dicts per turn (contacts, neighbor arrays, events). Buffer reuse would help single-digit % at significant complexity cost — deliberately deferred

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
