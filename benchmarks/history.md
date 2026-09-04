# Benchmark history (bench_suite.py)

Bench covers: 500-town crowding (per-town and batch), economy apply_growth, step no-armies, movement 1k, combat, heavy 207t+3036a t19→20 snapshot, movement heavy, weakness 1k.

All times median ms unless noted.

## Baseline (pre-any, commit bed4967)

```
crowding 500 towns              203 ms
crowding batch 500              - (not measured, fallback)
movement 1000 armies +100 towns 787 ms
movement 200 armies +100 towns  40 ms
weakness 1000 armies            398 ms
combat 200 armies               20.5 ms
captures 100x100                 2.25 ms
step heavy 207t+3036a           11732 ms (11.7s)
movement heavy 3036 vs 207t     1596 ms
```

## After opt1-2: world id index O(1) + economy dist-matrix (no numba yet) — a815ccb

```
crowding 500                    182 ms (→54 ms after dist-matrix fast path, 3.3x)
movement 1k                     825 ms (no gain, id index only)
weakness 1k                     380 ms
heavy step                      8807 ms (25% from id)
heavy movement                  1596 ms
```

## After opt3-4: movement hash r110/60 + combat squared early reject — 7e5db8d

```
crowding 500                    67 ms
crowding batch                  250 ms (regression, hash overhead)
movement 1k                     168 ms (5x)
movement heavy                  307 ms (5x)
weakness 1k                     24 ms (16x)
combat 200                      16 ms
captures 100x100                 1.6 ms (hash made slower then fixed)
heavy step                      4466 ms (2.6x)
```

## After opt5: economy batch numba — 5022004

```
crowding 500 (per-town)         69 ms (unchanged, per-town path)
crowding batch 500               0.95 ms (173x vs 272)
economy apply_growth 415t        0.06 ms
heavy step                      4612 ms (movement/combat dominate, batch saves ~150ms)
movement heavy                  305 ms
weakness 1k                     20 ms
captures                        2.7 ms
```

## Actuals opt6–9 (summarised — live record is docs/optimization_log.md)

- opt6 `c7a2f69`: stacked insta-kill + allocate_id guard (semantic change; heavy 4612→3336 unattributed, likely noise; ledger work claimed earlier never landed)
- opt7 `4845603`: step economy batch crowding (heavy 3336→3330, negligible as predicted)
- opt8 `4e2575f`: combat single-pass weakness+adjacency (heavy 3336→975, 3.42x — the real win)
- opt9 `c0a78fe`: movement simplified velocities + inlined closest-approach (heavy 975→956, noise)
- opt10 (pending): economy cache soundness (identity-validated) + unified stacked rule + per-town numba row + combat dedup; fixes cross-test cache pollution found during review

## Next planned

- opt11: movement batch hash query (iterate cells once instead of per-army query_radius)
- opt12: ants-inspired early exit (support pre-filter) — try if blocked
- opt13: record/world incremental pop_total + army_count

See docs/optimization_log.md for the live log; this file keeps raw per-run numbers.
