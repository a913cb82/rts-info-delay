# Bot worklog — optimization campaign

Rule: one entry per change with suite numbers before → after. Fast suite
(`scenario_bench.py`) per change; slower suite (`strategic_bench.py`) at
milestones. Scope grew past bot-only in the intel era (engine + runner +
bots). History below is append-only — do not rewrite old entries.

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

### Step 1 — survive floor (turtle)
Rule: relaxed TRAIN needs pop - cost >= death floor (500), unless
per-town last-stand (threat imputed to THIS town, ETA <= 3, affordable).
Found pre-work: global `doomed` was defined but never wired (no exception
existed); shared `can_train_here` (1600) + greedy (1500) already safe —
turtle-only fix. Benchmark note: map-level scenario infeasible — score
counts armies at cost (training score-neutral) + capture halves, so
suicide+army always beats hold+captured; and any bar-firing single-town
threat is inside 150km (ETA <= 3, doomed-coverage). Pinned decide-level
instead (tests/bots/test_turtle_floor.py: hold/last-stand/fat/control).
Fast suite: 15/15 byte-identical (no suite scenario parks a threatened
town in [1200, 1500)).

### Engine fix: movement updates were strangled (dedup without position)
Void-settle repro: expander settler marched 260km, arrived ~t10, sat to
t79 — bot mirror frozen at spawn the whole game. Root cause in
delivery.py (both shapes): send-state dedup compared payload dicts only,
and army payloads carry no position — every move after the first
delivered snapshot read as "same value". First snapshot sent, then
silence forever. Fix: dedup on (payload, x, y). Tests:
TestMovementStreams (marching streams each turn, stationary stays
silent). Differential scan-vs-fast still bit-identical.
Fallout triage (all movement, all expected — bots now see own armies):
void_settle 1 -> 4 towns (E1 settler follow-through FIXED by this, no bot
change needed); void_contact 1 -> 3 towns (foundings work; B untouched —
scouting still missing, benchmark stands). Fast suite moves are the same
mechanism viewed through score: founding (~-500 + lost compounding at
<=100t horizons) replaced sitting (score-neutral). Raid scenarios didn't
raid before either (frozen probes sat; takes depended on frozen-mirror
dynamics) — takes need scout-first probing (Step 2 prerequisite, next).
turtle_defend 3207 -> 2747 HOLDS* (*both sides found now; capital held +
score lead). Per-scenario goal triage before bot work: pair/trap/viable/
skip_thin/raid_hold goal-FAIL (dissipate into foundings, no take);
guard/settle goal-PASS (re-baseline); recycle marginal (1 idler at
horizon — check +10t before touching logic).

### Engine fix: movement updates strangled (dedup without position)
Void-settle repro: settler marched 260km, arrived ~t10, sat to t79 — bot
mirror frozen at spawn. Root cause (both delivery shapes): send-state
dedup compared payload dicts only, army payloads carry no position —
every move after the first snapshot read "same value". Fix: dedup on
(payload, x, y). Tests: TestMovementStreams. E1 follow-through FIXED by
this (settlers were fine). void_settle 1->4 towns immediately.

### S0 no-contact scout (Step 2 prerequisite, shipped)
First settler probes before founding for greedy/aggressive/expander.
Found mid-build: (1) 250km legs can't mid-course correct (2-turn intel
lag vs 1-step messenger projection + 10km tolerance = structurally dead;
proven with order logs showing detour messengers dying) -> 50km hops,
arrival-gated, replotted only while stationary. Hop endpoints sit inside
observed ground -> safe with known-town avoidance. (2) Unmark-on-rubble
blundered into decoys (trap scout captured 900-rubble) -> stay out on
rubble-only, bend hops; unmark only for viable/armies. (3) Kept hop note
hijacked post-contact armies into founding next to prizes -> drop note
on contact unmark. (4) Builds stages founded on scout waypoints
(quiescence wait exposed the race) -> scouts excluded from builds.
Support: drop_dead_notes (trail-freshness vs expected delay + 2;
first version used trail-stillness — wrong, static armies go silent so
trails freeze mid-march-shape; production trace caught it), order_move
quiescence gate (all 19 MOVE_TO sites; mid-march retargets wait for
convergence — fixes drunk-walk + site-steal families), aggressive
expand note_move fix (zigzag class). Tests: test_scout.py (18).
Results: all raid takes restored (pair/viable/raid_hold/trap/skip_thin
goal-PASS, decoys skipped), void_contact takes (2910), void_settle 3
towns, Elo resolved (greedy 1544/aggressive 1543 take; holders hold —
old all-hold was attacker-passivity, Step 5 verdict delivered),
empty_3000 a real game (8 foundings, 1 take, exile-lineage; pro still
sits — last blind bot, recon owed). Costs: scout tax in sprints
(outsettle 2687->1796, timing not shape), ~3 turns/50km probe pace,
recall latency (waits quiescence — noted tradeoff). recycle 30->60t
(scout founds far ~t55; doctrine is probe-then-found now).
False alarm logged: scoreboard wobble mid-session was uncommitted-tree
comparison, not nondeterminism (seed-sweep + hash checks identical).
Open next: Step 2 demand gates + trade evaluator; pro recon; turtle
pickets; far-defended raid guard (outsettle scout would donate vs
pickets — meeting forecast territory).

## empty_3000 re-analysis (merged-phase engine; record 3136-lineage)

Regen twice: same tree+map gave greedy 3086 AND 3136. First divergence
t2243 — one greedy MOVE_TO issued in one run, not the other, from
identical intel. Refines the old "false alarm" verdict (seed-sweeps are
identical *unloaded*): `effort()` branches on wall-clock bank (<25ms →
degraded policy), so loaded campaigns wobble. Methods consequence: long-
game scores carry ±~50 load noise; judge benches with margin, run quiet.
Timeline (16 spawns, 8 foundings, 1 capture, 11 deaths — still a quiet
game, but a real one): greedy settles t1173; aggressive+expander probe-
found t1266/t1270 (void-mirror, same turn); turtle settles t1676; second
probes t2256/t2260/t2281 all MERGE into own towns (+506/+506/+500 —
deterministic repeat rays, no probe memory); greedy near-settles t2590;
aggressive blunders into greedy's capital t2835 (capture halves 920→460
<500 → instant starvation; greedy headless, armless, terminal); aggressive
founds on the rubble t2840; expander corner-treks t2966; turtle trains 4
guards t2849–58 that never move. Pro: zero trains, zero armies, wins
9156 by compounding alone. Expansion ledger (rough, pro-as-control ×6.1
from t1110): greedy's three -1000 spends cost ~-6100/-2200/-1700 terminal
for +2414/+1100/+723 gained ≈ **-5800 net vs holding** — distance +
horizon price everything (Step 2 evidence). Kill anatomy: aggressive's
A1 viability gate CORRECTLY refused the raid (460 < 700); the take came
from arrival-suppressed drift (BUILD refused near known foe, no orders
→ last target walks in). Accidental, unpriced, effective. Suspected
drunk-walk mechanism for army18's dogleg: scout arrival-waits (~2+2+
quiescence turns static) sit inside drop_dead_notes' exp_delay+2 margin
(≈4 near home) → mid-probe note drop → turn-hashed find_build_site
resettles → new heading. Needs bot-side logging to convict.

## Probe memory (S0 followup 1 of 3)

Second probes re-flew deterministic base rays and merged into own towns
(+500 ×3 in the 3136-lineage). Fix in `common.py`: `scout_hop_target`
bends off own towns + fellow-probe noted destinations (20km; underfoot
points < interact+15 skipped so dispatch off the capital still works;
foe logic untouched), and hop-12 fallback drops the kept note when it
sits inside an own town's founding range (normal site choice/recycle
owns instead of settle-as-scout merging). TDD: 3 new tests in
`TestProbeMemory` (bend-off, fallback-release, far-fallback keeps note).
Fast 15/15 + strategic 12/13 identical (void_settle 2930, towns 3→4 —
extra distinct founding, −6 inside margin; pricing that 4th town is Step
2's job). empty_3000 rematch: pro 9156 (identical, doesn't scout) /
greedy 4270 (+1134) / aggressive 4873 (+1107) / expander 4829 (+602) /
turtle 7184 (+547); pop-jump merges 3→0, captures 1→0, town deaths 1→0.
Single run — scores carry load noise, but the mechanism is convicted at
game level (the t2256/t2260/t2281 merges are gone) and pinned by unit
tests. Remaining S0 followups: note-drop tension (needs bot-side logging
first), turn-hash.

## Turn-hash + staging-threat + last-stand D<N (S0 followups 2-3, turtle hole)

`find_build_site` hashed the turn (all callers pass constant salts), so
every re-query re-rolled sites and headings flapped (army18's dogleg
class). Fix: spin seeded by army id (`who`), never the turn — re-queries
hold headings; turtle's stacked-same-site settlers spread too. TDD:
`TestSiteStability` (same-army-stable, two-armies-spread). Immediately
moved turtle_defend 2747→1083 — forensics, not a revert: the new spin
stages aggressive 26km out (textbook) instead of 94km, and the 94km
raider NEVER ATTACKED (baseline record: no raid, no deaths — the old
2747 measured an untested defense). Under the first real attack turtle
stood 0 defenders home (both guards settled blind) and the last-stand
+200 margin vetoed the final train. Two fixes: (1) `staging_eta`
(shared helper): known foe town inside home LOS (150km) is staging =
positioning-threat (recall/hold), merged into turtle's `threat_eta`;
first merged into spend bars too, which made greedy muster 1000 vs a
passive stub decoy (skip_thin −1295) — lesson: positioning is cheap,
spending is dear; spend bars stay army-only everywhere, skip_thin back
to 3446. (2) last-stand: margin +200→affordable was SUICIDAL (fired
into 1v1-mutual at 1016, spending kills as surely as raids) — now fires
only when home defenders are strictly outnumbered (D < N, ETA ≤ 3),
which also discriminates passing settlers from raids. TDD: margin,
staging-recall chain, D<N hold/fire pins. Then the horizon problem: at
100 turns gutting-the-capital for a clean 2v1 outscores holding (2549
beheaded > ~1650 hub-intact) — suicide binds. Extended turtle_defend
100→400t (instruments are mutable; 331ms, still fast): HOLD lineage
(t22 mutual, capital regrows 1016→1453, no second raid) scores 2182 and
binds. Suite: fast 15/15 (only defend moves, ±5 spin-noise elsewhere),
strategic 13/13 (guard_duty +271 towns 2→4 on the new spin — luck, not
doctrine; outsettle +34, voids ±3). empty_3000: 9156/4270/4873/4829/7055
(turtle −129 staging caution tax; merges 0, takes 0). Residuals for
Step 3: interception (2v1 the raid en route keeps the capital FAT —
full 2747-class restoration needs it), cluster-rep turn-hash (same
disease, line 527, not chased).
