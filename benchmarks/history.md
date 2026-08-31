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

## Next planned — to be filled live

- opt6: ledger visibility cache + turn_events index
- opt7: step economy dedup (call crowding_nets_batch single path, tree for skip_growth)
- opt8: spatial hash tiered cell + incremental army hash + query_radius vectorization
- opt9: movement velocities numpy + numba batch closest + early bbox reject
- opt10: combat union-find + id->obj dict + single distance matrix reuse
- opt11: record/world faction incremental + delta pop totals

Each will be benched via same suite before/after and appended below.
