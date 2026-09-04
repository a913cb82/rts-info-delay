# Bot worklog — optimization campaign

Rule: bot code only (src/bots/*). Every entry records suite numbers
before → after. Fast suite (`scenario_bench.py`, 1.7s) per change;
slower suite (`strategic_bench.py`, ~10s) at milestones.

## Starting baselines (2026-09-04, pre-campaign)

Fast (score): greedy raid_hold 3176 / recycle 3592 / skip_thin 2116;
expander settle 2114 / chain 4319 / guard 2000;
aggressive viable 3771 / pair 3782 / starve_trap 2159;
turtle defend 548 / wake 0 / cluster 2733;
pro opening 3240 / defense 1109 / endgame 2245.
Slow: succession 0, guard_duty 0, snowball 3748, staleness 4654,
siege 3347, opening 1391, comeback 821, attrition 4226, endurance 6424,
longpeace 3124 (eff 59%), outsettle 1856.
Elo: pro 1531 / greedy 1529 / aggressive 1527 / expander 1457 / turtle 1456.
Self-play diffs 0.

## Log

### Pro — best-of-all assembly (2026-09-04)
Fast: endgame 2245→3249 (counter-punch breaks mirror), opening 3240→4316,
defense 1109 (holds). Slow: efficiency 59%→100% (P3b empty-field hold =
policy optimum exactly), succession 0→611, snowball 3748→5681,
attrition/endurance restored to 4226/3089 after P5-P7 scares.
Elo: all-draws (structural at 3000/60t); pro concedes nothing.
Doctrine learned:
- P2 counter-punch (hold-all vs peer field armies, counter the spent foe)
  breaks mirrors; marching the pack out naked re-loses the race (1647).
- Rope is duel-only (P5): in big wars release never fires → slow death
  (attrition 4226→1900); there, departure-sync/pressure.
- Home defense is duel-only (P6): holding one home bleeds long wars
  (endurance 6424→904); there, all-out.
- Viability gate is duel-only (P7, biggest save): denial-raids erase foe
  production in big wars; gating cost 2185 (endurance 904→3089). Ported
  to greedy + aggressive.
- Endurance 6424-baseline vs 3089-now conflates pro + opponent improvements
  (foes are tougher); honest pro-delta is 3089→3089 with better duels.
- Takes in symmetric endgames still missing (out-settles 3v4 but doesn't
  crack); needs siege craft (future).

### Expander — guard + working settlers (2026-09-04)
Fast: guard 1000→1624 (capital HELD + settle), settle/chain flat (correct).
Elo: expander now holds vs greedy+aggressive (was: taken) — see doctrine.
Doctrine learned:
- Same latent note_move bug as greedy (settlers sat on sites); fixed.
- 3000-vs-3000 60-turn raids are STRUCTURALLY drawish once both trade
  once (neither can afford wave 3) — first strike needs 2v1 (5000+ pop).
  A>E at parity = disruption (t5 mid-field settler kill measured), not
  takes; takes need force advantage (pair model). Elo all-fail is honest.
- Expander ships WITHOUT evac (character: accepts decapitation, wins by
  spread; guard + lineage suffice).

### Greedy — viability, recycle, shared home defense (2026-09-04)
Fast: skip_thin 2116→3467 (map redesigned twice: timing alone can't price
restraint — scarcity can: one army, near decoy, far prize; baseline wastes
the only army on rubble 1727), recycle 3592→4086 (latent bug: moves stage
never called note_move so settlers sat on sites — now they BUILD),
raid_hold 3176 (~flat, correct).
Elo: tie cluster intact (greedy 1515); only-vs-expander takes everywhere.
Doctrine learned:
- Single-thin-town maps can't separate (all options ~2100-2300 at any
horizon: denial value offsets; post-starve settling catches up).
- Viability-gating attacks removes accidental defense (t4 counter-march
intercepted wave 2 mid-field; gated version settles and dies t8) — every
raider needs home-hold + second-wave watch to compensate.
- Shared defense factored into common.py: inbound_eta (nearest-own-town
prediction, guards excluded), note_wave_watch (vanished-army memory),
should_hold_home (keep >=1). Ported to aggressive (replacing its inline
version, same numbers).

### Aggressive — viability, departure-sync, home defense (2026-09-04)
Fast: pair 3782→4317 (clean 2v1, guard dies alone), trap 2306→4039
(map redesigned: thin decoy + fat prize; gate skips rubble, takes 4000),
viable 3771 (holds). Elo 1487→1514; all raids vs expander succeed (A>E),
all raids vs turtle fail (T>A), tie cluster with pro/greedy.
Doctrine learned:
- Viability gate (halve-vs-floor+200) first misfired as pure restraint
  (old trap: 2310 vs 2314 — timing wash); redesigned map proves selection.
- Arrival-sync is unworkable (1-turn decision + 1-turn messenger lag +
  stale intel vs 50km/turn; creep evaluated on corpses; halt ordered
  settles; dual gates deadlocked). Departure-sync works: lone army holds
  while home town can retrench (pop ≥ 2x cost), releases with the pack.
- A1 nearly broke defense (chasing ghosts left cap empty, t8 walk-in):
  home-hold vs predicted inbound + second-wave watch (vanished known
  army → hold one home 6 turns; bot-side memory on state object).
- Stationary guards are not inbound (pair freeze: 5105 hoard scored well
  for doing nothing — excluded guards on own towns from inbound).
- Cross-bot coupling is normal: turtle_defend 2547↔1109 swings came from
  B-side changes (both hold); wake 1527→527 honest (B hunts settler now).
  Suicide-evac gated to pop ≥ 2x cost (turtle tweak).

### Turtle — threat defense + MOVE_CAPITAL evac (2026-09-04)
Fast: defend 548→2547 (HOLDS), wake 0→1527 (evac lineage), cluster 2730→2182.
Slow: Elo turtle 1456→? (all raids vs turtle now fail — T>A edge live);
outsettle turtle-side livelier (re-baseline below).
Doctrine learned (all measured, kept only what scored):
- Threat-responsive train bar (2600 peace / 1700 ≤10 / 1200 ≤4) gated by
  can_train_here bypass (its 2600 veto blocked everything — first fix that
  moved nothing until bypassed).
- Per-town threat via target prediction (enemy marches at MY town nearest
  to IT). Global threat made the cap spend on fights aimed elsewhere;
  reading stated targets fails (intel delay); proximity alone misfires.
- Cap-concentration: split garrisons 1635 vs 2180 concentrated (2v1 wins,
  1v1s trade — combat rule).
- Recall settlers to cap (2v1 assembly) unless hopeless; hopeless → lineage
  (settle) instead of trickling into lost trades.
- Threatened home armies hold (never dispatch, never disband into towns).
- MOVE_CAPITAL evac when hopeless + pop ≥ 1000: viceroy founds new capital
  (wake 527→1527). Evac gate hopeless-ONLY (eta≤4 fled winnable fights).
- Peacetime picket: single-town factions train one blind army; multi-town
  hoard until threats show (stops t1+t2 double-tap, restores cluster hoard).
- Cluster 2730→2182 accepted: baseline held by accident (B wave2 died on a
  settler); 2182 holds by design (t12 garrison). Counter-raid doctrine
  (take B's emptied capital) is the future fix. No regressions elsewhere.

### Forecast-at-arrival train gate — tried, REVERTED (2026-09-04)
Replaced the 400/turn distance fudge in `can_train_here` / greedy / pro /
turtle-relaxed with `forecast_pop` (measured growth over intel + messenger
legs) + a 1500 survive floor. Unit-correct, bench-negative, reverted same day.
Fast suite (current tree): pair 4303→3773, trap 4040→3463, viable 3768→3233,
chain 4319→3773, raid_hold 3173→2643, skip_thin 3467→2887, endgame 4928→2000
(uniform ~-530; single-town scenarios flat; wake/defense stayed 0).
Same-spawn-count autopsy (viable 4v4): the gate didn't add trains, it moved
them earlier — distant conquests cleared 1600 instead of 2133, pulling
-500 train→build cycles inside the scoring window.
Doctrine learned:
- Affordability != desirability. The fudge was load-bearing as a spending
  brake: at 1-5 pop/turn growth, a 1000-pop train repays over hundreds of
  turns, so earlier distant trains lose at every horizon tested (80 AND
  1500 turns). Gating *whether* to train needs demand (targets/threats/
  settler pipeline), not just arrival math — that doctrine is still open.
- Delayed intel can't be outgrown: wake stayed 0 because 4-turn growth
  (~+4) can't close 100+ intel gaps at 1200-2600 bars. Stale-threshold
  scenarios need risk posture, not arithmetic.
- Attribution hygiene held: stashed campaign code reproduces the old table
  exactly, isolating all movement to post-campaign engine changes
  (delayed intel moved defense 1109→0, wake 1060→0, endgame 3249→4928 —
  separate ledger to settle).

## EVENT_REWORK Phase 0+1 (engine): tagged generation + S plumbing

Phase 0 audit decisions — kept: Ledger (reshaped), seq/_sent_seqs,
Messenger, compat shims until migration. Rewritten: visible_events →
tag+delay+S (Ph2/3). Deleted in Ph3: capital_since, town_history/
delayed_town, last_sent_pop/status+pop loop, landing_spawns/
landed_this_turn/landing branch, old-kind ledger logging. Undecided
(spike decides): turn_events/_by_turn (zero callers). Record/viewer:
zero changes (write_turn_line is ledger-independent; fixed one
integration test that misused ledger events as record dicts — latent
breakage, only ever passed on empty ledgers).
Baselines (this box): heavy 207t+3036a cold 4.95ms/89.8KiB(1020u),
warm 4.37ms/0B; full.json t20 (415t+100a) cold 4.37ms/200.8KiB(2255u),
warm 6.89ms/0B. Lesson: gc.collect + best-of-3 (stray major GC ≈50ms).
Design note: every live entity is owner-observed (dist 0), so the
generate-skip fires only for unwatched deaths.
Phase 1 (TDD, 23 tests): generate() every-observed-every-turn + skip,
visible_to tags (squared-reject, ≤ boundary pinned), tombstones from
last-known (pos+faction) pruned past window, query() as the no-send-state
reference delivery (TAG+DELAY+S), S storage, windowed memory proof,
160km transient + delay-exact (S+1.07→S+2) pinned. Wired additively into
knowledge phase; old delivery ignores new kinds (test-pinned). Two test
fixes were test bugs (foe at exactly LOS sees; battle inaudible at t1).
Suite green, 15 scenario scores byte-identical.

## EVENT_REWORK Phase 2-5 (engine + bots + baseline)

Phase 2 (TDD): build_updates pure fn + 24 tests + differential
(scan reference vs columnar+numba, bit-identical on messy fixture).
Spike verdicts (paired, same box): indexed deques lose (heavy-warm 122ms
— tagged-subset still 26k); columnar+numba wins but honest steady-state
measurement needed (cold/catch-up numbers mislead; live-loop warm is the
real cost). Perf tuning DEFERRED by decision — working first.
Phase 3: deliver/note_landing/startup-strip in run_game; turn-0 pre-game
generation (first payload observes own capital); ledger surgery
(visible_events/_by_turn/turn_events/capital_since/old logging gone);
knowledge = generate + evict. E2E flight (mute 1→6 stream jump, S=5,
capture-as-update, mid-flight deaths + transient never arrive, viceroy
consumption tombstone delivers-and-ignored, uniform rule asserted) +
stationary/purity/reset/E2E pins + record tripwire (sha pinned, stable).
Migrated or deleted: InfoDelay/MoveCapitalLedger/ViceroyFlight classes,
ledger/medium/bot_state/integration visibility tests (kept IDs where the
intent survived). Live loop verified with real bots (blind, no crash).
Phase 4: upsert parser (absolute; unknown kinds ignored; deaths clear
trackers; mark_dirty per mirror contract — caught by stale-cache test),
order-flag amnesia (jump wipes incl. last_seen/trails/wave/plan; sequential
clears; consumed either way), last_seen + trails, intent-free forecast
(own notes exact, foe by trail velocity), no map pre-seed, quiet = any
update, fingerprint over full state (post-decide snapshot — in-decide
note_move broke replay until then), note_orders extracted, backlog dropped.
24 bot tests; incremental/sync/time suites migrated (13 event-arithmetic
tests deleted as obsolete); all 5 decides tolerate empty worlds.
Phase 5: TESTS B-section/I/G rows + PLAN intel model + BOT_PLAN scouting
note rewritten; fog-era table baselined (above); empty_3000 rematch
(pro 9156 wins); viewer smoke 200 (record format unchanged).
Doctrine funnel for Steps: selectivity regressions (skip_thin/trap/viable)
want the Step-2 trade evaluator; Elo all-hold wants a doctrine verdict.

## Post-rework cleanup + paired perf numbers (same box)

Paired before(6ea9212)/after, single runs: heavy turn 302ms (272-332) ->
273ms (268-283) — no regression; empty_3000 2.8s -> 3.7s, of which +0.66s
is import-time numba precompile (0.80s vs 0.14s `import runner.main`,
house rule opt10: pay once at startup), rest ~15us/turn. Delivery ~1ms
for 5 factions on heavy (beats the old ~5ms budget); generation is the
fat: 63ms heavy (3243 entities), 25ms full20-scale (515 entities).
Cleanup: Ledger(window=)/Event(t=,kind=str)/log() string-conversion shims
deleted (G9/I9/log-mechanics tests migrated to canonical construction);
EventKind trimmed to TOWN_UPDATE/ARMY_UPDATE (step/record dicts use plain
strings, never the enum); untagged-update tag-gate pinned in test_main.
Doctrine funnel for BOT_PLAN Steps: selectivity bleed (skip_thin/trap/
viable) -> Step 2 trade evaluator (known-foe sums, last_seen risk,
trail counts, scouting inside the step, counter-intel parked after);
Elo all-hold verdict pre-Step-5; scoreboard re-cut to fog era.

## Perf phase 1: generation (kernel wins, micros don't, skip rejected)

Profile said observers() was 62% of generate. Chain (heavy rig):
double-loop 63.1 -> self-shortcut 51.7 (-18%, exact: own anchor at dist 0
always hit) -> grid experiment: 64.9 clustered (+26%) BUT 7.2 full20
(-71% from 24.8). Neither dominates -> numba flat-scan kernel (same
float64 ops, OR-mask order-free): heavy 25.1 (-60%), full20 3.4 (-86%),
and beats grid on spread too. Micro-opts (inlined mask->set, hoisted
_column attrs, _ensure_row inline) measured ~zero -> reverted for
readability. Budget gates: tests/engine/test_perf_budget.py (heavy 30ms,
full20 5ms, delivery-5 3ms; delivery actually ~0.4-1ms).
Skip-model (99.5% of army-turns stationary in empty_3000) REJECTED:
skipping re-times releases (older-t news arrives sooner) -> full
trajectory churn + fog-table re-baseline for a win nobody feels
(real games are bot-I/O bound; empty_3000 still 3.7s). Correctness proofs:
all 15 scenario scores byte-identical post-kernel; evict/compact verified
safe (dense row ids are values, never renumbered; SendState unaffected).
Phase split on the pathological rig: combat ~135 + movement ~120
(pre-existing, untouched, data-dependent +-15 + stray major-GC ~50ms per
house rules) vs knowledge ~25 (was ~63). Combat's stacked-weakness search
is the next fat and belongs to its own phase, not the rework.
Latent bug fixed: bench_suite Ledger(cfg) (swallowed by the deleted
fallback; now canonical construction).

## EVENT_REWORK close-out: reporting bench + doc truth

bench_builder_full now lives in benchmarks/bench_suite.py (reporting:
generate/delivery ms, wire bytes cold+warm, ledger memory) with failing
gates in tests/engine/test_perf_budget.py. Measured: cold wire ~35KB/
faction (~260 updates, full re-announce), warm steady-state 2B (`[]` —
the diff discipline proves itself); ledger ~750B/entry Python overhead
(25MB worst-case pathological, single-digit real games — the plan's 5MB
estimate corrected in-doc). Doc inconsistencies fixed: Ledger-deletion
bullet marked superseded by D3, scan-oracle retention noted, budget
locations corrected. Verified by grep: _by_turn/turn_events/.visible all
gone; Phase-4 machinery (upsert, alive-False removal, pop-drop confirm,
wave fields, note_orders, trails) present in-tree. Nothing open in the
plan except future combat/movement phases (explicitly not this rework).
