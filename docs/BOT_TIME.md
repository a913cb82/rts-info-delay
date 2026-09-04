# Bot time management — clock infrastructure (ideas 1–6, all landed)

Bots run under a Fischer clock (cap `turn_time_ms`, +`time_increment_ms`/turn).
These six ideas cut think cost or spend the bank deliberately. Status: all six implemented (commits below).
Benchmarks: `benchmarks/bot_bench.py` (quiet turn + 2000-event backlog).

## 1. Incremental BotState — DONE (`0f171dd`)
Measured: quiet update 0.016→0.010ms; heavy backlog ~85ms (unchanged —
dominated by engine `apply_events` index rebuilds, out of scope for bot-only
work; verified by same-process A/B after a false thermal regression scare).
Growth is now folded per applied event and reset on turn advance, which also
fixed a real inconsistency the new tests caught (chunked updates used to
re-baseline growth per chunk).
Apply only each turn's event delta to cached projections instead of replaying
and re-syncing trackers over the full visible state.
- Tests: equivalence — incremental update equals full replay over scripted
  event sequences (spawn/capture/death/move interleavings); N-turn
  randomized-sequence property test asserting identical world snapshots.

## 2. Anytime decide with staged prefixes — DONE (greedy pilot)
`decide_stages` (trains/moves/builds) + lazy `decide_orders`; 3000-turn game
plays the same story (single pre-existing ±1 wire flip at t1110, final
within 0.04%). Other tiers keep their loops; promote on evidence.
Priority-ordered stages (trains → defense → attacks → expansion → micro),
each checkpointing `should_yield()` and flushing its orders before the next
stage starts, so an abort keeps the important prefix.
- Tests: injected early deadline after stage k yields exactly the first-k-stages
  prefix of the full run; empty-prefix test (deadline on entry → no orders,
  still replies `go`); stage-order test (a train is never dropped for a raid).

## 3. Memoized staleness math — DONE (`0f171dd`)
`BotState.stale_turns` keyed by (turn, capital id+pos); `BotForecast` has a
per-instance memo. Cache-bust test does marked world surgery + `mark_dirty`,
mirroring the production mutation contract.
Cache per-town compensation (`dist/capital/info_speed`), growth, and crowding
estimates keyed by (town_id, turn); recompute only on new info.
- Tests: cache-hit equivalence (memoized == recomputed over a full game);
  invalidation tests (each event kind touching a town busts exactly that
  town's entries, nothing else); stale-read test (no entry survives a
  MOVE_CAPITAL resync).

## 4. Skip stable turns — DONE
`cached_or_decide` replays standing orders on quiet turns (~1.4µs vs ~0.2ms
decide); military kinds bust, partial-backlog turns never cache. Wired into
`bot_main`, so all five tiers get it. Caught live: the first version cached
`[]` on turn 1 and replayed it for 3000 turns (idle game — growth never
busted the cache). Fixed with a decide-relevant fingerprint (quantized
pops/positions, membership, pending trackers, 25-turn heartbeat): replay
requires fingerprint stability, so affordability changes force fresh decides.
If a turn's payload carries no new military information (no creations,
removals, or faction changes — only unchanged or ticked snapshots),
re-issue standing orders without running decide; bank the +10ms.
- Tests: quiet-turn replay (orders identical to full decide across 50 idle
  turns); cache-bust test (each military event kind forces a full decide);
  bank test (clock balance rises over a quiet stretch, never exceeds cap).

## 5. Bulk think + cached plans — DONE (mechanism)
`push_plan`/`_live_plan`: verbatim orders until turn expiry or new military
intel. No tier pushes plans yet — that is strategy work (when to plan), the
plumbing and its tests are in place.
On quiet turns with a full bank, run deep work once (forecasting, wide
build-site search) and store a queue of standing orders with trigger
conditions; near-empty turns pop the next precomputed order.
- Tests: plan-execution equivalence (K quiet turns from plan == K live
  decides); trigger tests (new intel invalidates the plan and forces fresh
  decide); expiry test (stale plans never issue).

## 6. Clock-aware aggression — DONE (greedy pilot)
`effort()`: None→full, <25ms→low. Low clock = trains stage only (measured
0.088→0.016ms on a rich state, trains-only verified subset). `bot_main` sets
`clock_budget_ms` from the Fischer clock line each turn.
Condition effort on the bank: low clock → precomputed/safe moves only;
full bank → expensive searches (coordination, wide site search).
- Tests: same state at low vs full clock (safe-only subset vs full orders);
  threshold boundary tests; monotonicity (more bank never yields fewer safe
  orders).

## Decided (not in 1–6)

- **8 wire slimming — IMPLEMENTED.** Populations go out as absolute ints
  inside `town_update`; the send-state diff resends only changed snapshots.
  Wire error bounded <1, never compounds (engine floats + record file
  untouched; bot assigns absolutely). Measured:
  278→198 B/bot-turn (−29%); 3000-turn scores 11077→11073 (single ±1
  threshold flip at t1110, final within 0.04%).
- **9 margins — IMPLEMENTED, measured.** Instant round-trip med 0.15ms, p99
  0.45ms, max 11ms spike/1000. Total unusable 8ms (3 flush + 5 think),
  down from 30ms double margin. The 11ms spike is why it is 8, not 2–3.
- **10 engine standing orders — REJECTED.** Engine stays simple; the
  equivalent lives bot-side as plan caches (idea 5). Revisit only with data
  showing round-trips dominate a thinking bot's clock.

## After the campaign: intel-era work (superseded by EVENT_REWORK)

The event-shape machinery this section once described (landing rebuild
payloads, per-turn town snapshots, `TOWN_DEATH` kind, builder-returns-[]
mute) was deleted by the rework — see `BOTS.md` intel model and
`docs/EVENT_REWORK.md`. What survived into the fog era: `stale_turns`
compensation (load-bearing), quiet-turn replay (any update breaks sleep),
plan queue, clock effort. The worklog entries stand as record.

## Conventions
- New tests go in `tests/bots/`; integration-level (drive `bot_main` or
  `BotState` over scripted stdin/event streams), not white-box unit tests.
- Never edit existing tests for these; add new files.
- Each idea lands with its tests green plus a paired benchmark (ms/turn per
  bot on the 3000-turn empty game) before/after.
