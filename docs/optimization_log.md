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

## opt6: Ledger vectorized + by_turn index + stacked insta-kill

**Commit:** `c7a2f69` (code) + `02308b9` (test fix)
**Changes:**
- `ledger.py`: numpy vectorized `visible_events()` with cached `_xs/_ys/_ts` arrays; `_by_turn: dict[int, list[Event]]` for O(1) `turn_events()`; early bbox reject `R²`
- `economy.py`: Stacked insta-kill — towns at `dist<1e-9` where lower pop dies (`total += 1e6`)
- `world.py`: `allocate_id()` collision guard for manually-assigned test IDs
- `tests/`: Split `test_move_capital_old_capital_demoted` (non-stacked target) + new `test_move_capital_stacked_die`

| Benchmark | Before (ms) | After (ms) | Change |
|---|---|---|---|
| step heavy 207t+3036a | 4,612 | 3,336 | 1.38× |
| movement heavy 3036a | 307 | 244 | 1.26× |
| movement 1k | 168 | 136 | 1.24× |
| crowding 500 | 69 | 54 | 1.28× |
| weakness 1k | 24 | 19 | 1.26× |
| combat 200 | 16 | 13.5 | 1.19× |
| crowding batch 500 | 0.95 | 0.82 | 1.16× |
| captures 100 | 1.6 | 1.55 | 1.03× |

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

## Remaining (opt9-11, not started)

### opt9: Spatial hash incremental army + tiered cell
- `movement.py`: Build army hash once per step, reuse across movement+weakness+captures
- Tiered cells: cell=10 for combat (R=10), cell=150 for crowding/movement (R=110/60)
- Incremental: add/remove changed armies instead of full rebuild each phase

### opt10: Movement velocities numpy + numba batch
- `movement.py`: `compute_velocities` numpy vectorized (xs,ys,txs,tys → vxs,vys in one shot)
- `_closest_approach` batch numpy instead of per-army Python loop
- Early bbox reject for trivially non-blocking cases

### opt11: Ants-inspired early exit (try if blocked)
- `do_attack_support` pre-filter: if friends ≥ enemies for all, skip weakness entirely
- `kill_ant` dict removal O(1) by loc vs our O(n) list scan — applies to captures `armies×towns`

### opt12: Record/world incremental pop_total
- `record.py`: maintain `pop_total[faction]`/`army_count[faction]` incrementally on growth/conquest/spawn/death instead of full scan

---

## Cumulative Performance

| Benchmark | Baseline | Now | Total speedup |
|---|---|---|---|
| step heavy 207t+3036a | 11,732ms | **975ms** | **12.0×** |
| crowding 500 | 203ms | 52ms | 3.9× |
| crowding batch 500 | — | 0.77ms | — |
| movement heavy 3036a | 1,596ms | 227ms | 7.0× |
| movement 1k | 787ms | 134ms | 5.9× |
| weakness 1k | 398ms | 17ms | 23.4× |
| combat 200 | 20.5ms | 5.44ms | 3.8× |
| captures 100 | 12ms | 1.47ms | 8.2× |
