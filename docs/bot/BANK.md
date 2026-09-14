# Bank-starvation (the loaded-box meta)

## Mechanics (runner/main.py)
- Fischer clock: 1000ms initial + 10ms/turn, CAPPED at turn_time (100ms).
  Hoarding wastes; spend-up-to-cap is free. Byo-yomi fallback on exhaustion.
- Deduction = elapsed ROUND-TRIP (engine write + bot compute + read), not
  bot CPU. Loaded boxes inflate round-trips (30-90ms vs 3ms quiet).
- Consequence: on loaded boxes banks pin near-empty; bots yield-lock
  (~20 missions/10k turns observed) and towns idle-grow. Everyone ties.

## Findings (2026-09-14)
- v6-line scores 726 on ~20 missions (starvation-proof by default: silence
  = idle-grow = 726-floor). Perf tuning (skip-turn, caches) changed
  NOTHING: the cost is round-trip I/O, not compute (profiled: 1ms/600ev).
- Fan/scouts/steals need TURNS (bank); on loaded boxes they never fire
  (yield-locked t13+). Features must front-load (t1-50, bank full) or
  survive starvation (v6 does).
- True scores need quiet boxes (load<1). Overnight dodge-grinds scheduled.

## Rules
- Check `uptime` before validating (load>1.5 = starved = ties only).
- Priority-order every turn (muster > march > boost > pioneer): if the
  round-trip kills mid-turn, best orders already sent. (Already ordered.)
- Front-load features (t10-fan, not t100). Never switch branches mid-run.
