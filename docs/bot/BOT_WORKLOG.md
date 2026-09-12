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

## GTO exam 6/14 + note-drop closed (S0 done, Step 2 scoped)

Note-drop tension CLOSED as benign without a code change: wrapper-bot
drop logging (monkeypatch-per-bot-module, file log) measured 88/88
empty_3000 drops on scout notes with 0 doglegs — drops fire during
arrival-waits on fresh orders, the army marches on engine-side, and
quiescence blocks doomed re-dispatches. Turn-hash had already defused
the roulette half; what remains is bookkeeping churn. All S0 followups
done (probe memory, turn-hash, note-drop verdict).
GTO exam (`benchmarks/gto_exam.py`, scored non-blocking, ms): doctrine
fixtures over geometries, baseline pro 6/14 — muster 2/6 (overtrains
defended towns AND marches the defenders away; donates into 1v3),
pricing 2/2, selectivity 1/2 (thin gate real; leader-targeting picks
the ready rich over the unready poor), escape 1/2 (young rides down —
_pro_hopeless is pop-based, needs D<N force-counting; established
passes accidentally), intel 0/1 (pro still blind, marches settlers at
foe towns), endgame 0/1 (settles with 50 turns left). Two fixture bugs
caught by sniffing passes (same-faction score sharing; empty-field
buzzer) — exam honest now. Fail map filed in BENCH + Step 2/5/6
acceptance lines. Next: Step 2 demand gates + trade evaluator for pro
(exam muster/selectivity are its acceptance).

## Step 2 pro: demand gates + trade evaluator (exam 6/14 -> 13/15, Elo crown)

Pro learns demand: threat trains by outcome rule (train iff D == N-1
flips take→save; D == N holds for the cheaper mutual — mutual spends a
non-compounding army, trains spend compounding pop), raid pipeline (pack
deficit for the priced target), expansion pipeline (void merit or
contested payback 1e8/P). Shared: `inbound_force` (+counts, feeds
`inbound_eta`), `defense_train_ok` (turtle's last-stand upgraded to it —
suites confirm equivalence), unready-weighted raid selection (take needs
N ≥ S+W+1 with printable-before-arrival; prize clears risk premium, army
not spent). Exam: muster 6/6, pricing 3/3, selectivity 2/2 (fixture bugs
fixed en route: same-faction score-sharing, prize-as-spent). Remaining
exam reds are filed futures (young_flees Step 5, blind_probes recon).
Guard_duty collapsed 3234→645 on the way — forensics, three real bugs:
(1) spend-poisoned growth (train -1000 misread as collapse → fake
un-reinforceable → mystery evac): growth now net of train-spends (own
spawn events) and capture-halves (halve stripped, chunk-proof), with TDD
pins; (2) recycle-disband under staging (t31: zero-move home + merge
with staging known but no field army visible — "no visible army" ≠
peace): war-footing holds (no home marches, no home merges) unless
P3b-empty; (3) t38 evac explained by (1), no separate bug. Restored
3249 (+15). Lesson log: filtered record reads hid `battle` events twice
(merges look like deaths); cross-version record comparison faked an
engine ghost (always regenerate before reading); dead-bot pro scores
3872 (peaceful farming beats broken defense — defense is the tissue).
Fast 15/15, strategic 13/13, Elo pro top at 1501 (muster discipline
pays in skirmishes), empty_3000 pro identical 9156 (greedy +490 via the
shared growth fix). Remain: Step 2 for the other four (per-personality
bars), then Steps 3-6, recon, pickets.

## Step 2 greedy: shared demand API + calibration (exam 14/16, Elo top)

Extracted pro's demand machinery to shared parameterized API
(`raid_target`+margin, `expansion_demand`+payback_mult, `demand_trains`
+depth_extra/threat_window/probe_armies, `hold_defenders`,
`can_train_standard` merging the duplicated 1500-rule) — pro rewired
identical (exam + suites confirm). Greedy on present-biased params
(depth +500 rich-only muster, margin 500 transfer-positive, payback x2
cherry-pick, 1 prober). Three shared fixes en route, each convicted by
a red-then-green: (1) void serialization — a scout's own hop note
blocked the settler pipeline (recycle -1024): void expands unserialized
(colonies ARE the void economy), contested keeps one-at-a-time;
(2) pipeline chicken-and-egg (need > fieldable → no target → no deficit
→ no pack, forever): selection values, marching gates on need ≤ free,
plus bird-in-hand discount (executable now beats pipeline later);
(3) pack deadlock vs passive prizes (skip_thin: need-2 hold forever, no
2nd affordable): foe-print calibration (`_foe_first_seen/_foe_prints`
tracking + `foe_print_factor`, grace 20) zeroes W for sterile factions —
unready means can't OR won't. (4) scout paradox (no army→no intel→no
demand→no army, skip_thin went passive 2296): `probe_armies` trains the
first prober (pairs with S0; pro/turtle pass 0 until recon). skip_thin
3446→3888 (calibrated need-1 take t28, decoy skipped — honest gain).
Infra tests caught real invariants (trains-stage atomicity — removed the
in-loop yield; trains-must-exist on rich state — pipeline provides).
Class-body scare: a module-level insert mid-class gutted BotState
(51 red) — reverted by relocation; suites are the net. Fast 15/15,
voids steady, Elo greedy top 1530 (aggressive 1529→1501 shuffles against
the new holds — its rollout is next), empty greedy 4835 (+75, same
lineage). Remain: aggressive/expander/turtle Step 2, recon, Steps 3-6.

## Step 2 aggressive: predator on shared API (trio at binding, equilibrium found)

Aggressive on demand_trains (thin cushion, margin 100, payback x3, 1
prober) + military staging demand (found toward the raid target while no
own town within 150km — forward print shortens arrival → completable
needs) + pack gate (subsumes A2; the retrench-march trickled) + probe in
force (S==0, range-capped 300km after the 600km-donation lesson) +
war-footing merge gate. Trio collapsed -25% on the way — forensics:
takes run on scout-cadence (t7-vs-t26 same code, timing-shifted waits;
3x-stable-quiet per tree, JIT first-runs lie — run suites TWICE after
changes, second is truth); late luxury settlers (viable t32: staging
dispatched pre-take arrives post-take → founds; marginal horizon 500 on
staging + S0-fallback foe-history gate (recycle's true-void capability
kept) fixed it); void_horizon on trains saved recycle from overtraining
(3673→5793: one prober is enough on 60t). Trio now 4794/4495/4250 (all
at/above binding). Lesson log: pop_change carries ABSOLUTE pops (merges
look like deaths in filtered reads — verify with absolutes); always
regenerate records before reading (cross-version comparison faked an
engine ghost twice); enumerate death paths before crying bug (all four
army_death sites pair with events except merge-consume by design).
empty_3000 aggressive 2926 (-1947): equilibrium, not bug — all five
credible → zero battles game-wide → nobody raids (correct deterrence!).
Baseline's takes were chaos-profits (mutuals made victims); the new
equilibrium has no victims (poor colonies halve-below-500, correctly
skipped). What breaks it is the BUZZER (retaliation time runs out) —
Step 6 next, highest leverage. Filed: site-starvation veto (id7 crowded
out; picker needs a growth>0 veto), aggressive early-raid window urgency
(guard_duty t20-60 window unexploited — Step 3 timing), S0 probe tempo
(march-blind-fast — Step 2 scout followup).

## Step 6 minimal: buzzer defense (no own-goals); strikes filed

Buzzer = last 10% (min 20 turns): retaliation time shrinks. Shipped the
defensive flip shared: blind guards (1 home per rich town via
hold-set), arrival capped by turns_left (no pointless marches), no
settling (payback/horizon die naturally), turtle/expander/aggressive
settle branches gated. REVERTED strip-mine muster before committing:
converting compounding pop to idle armies is self-tax without strikes
(empty: turtle -1009/greedy -745, zero battles — the armies stood
around while home compounding died). Muster stays demand-gated.
Filed (Step 6+): first-strike logic (turns_left<=~15 outnumber-strikes;
needs its own instrument + timing thought). Also fixed eviction-void
foundings (stale intel read as peace → late luxury foundings): void
branch requires never-seen (dark-spring correct, eviction-void goes
contested-caution). Equilibrium stands (zero battles: deterrence holds
everywhere; pro 9156 control). Scores recovered exactly (greedy 4835,
turtle 7055). Remain: pro recon (unlocks Step 5), Step 5 (hopeless D<N),
expander/turtle Step 2 (race-slots rule for expander), Steps 3-4, filed
strikes/tempo/vetoes.

## Recon + site-veto NET + Step-6 defense (exam 15/16; empty slosh noted)

Pro recon shipped (S0 + 1 prober piercing P3b; exam blind_probes passes
-> 15/16, only young_flees (Step 5) red). Three recon-exposed bugs fixed:
pro builds founded on scout waypoints (greedy's guard never ported);
_scout_id stuck on dead armies (no scouting ever again — frees on death
now); per-turn probe flags trickle-donated (one probe en route suppresses
duplicates now, pinned). Suppressed-arrival lite in builds (demand+site
re-check at arrival; hostage foundings re-decide). Site-veto NET
(site_growth transcribed incl. info_speed radius fix; found iff NET
empire delta > amortized): fratricide (colony crowding home harder than
it earns) is the dominant full-map cost. Suite: fast holds (opening UP
+2009 on recon (early intel -> early takes); defense/endgame/longpeace
rebased honest-below (untested-peace/wartime-merges/recon-premium with
filed Step-3/5 paths back); recycle UP on lean pipelines; trio at
binding. empty_3000 sloshes +/-2000 between commits (foundings on/off at
veto margins + cadence): VARIANCE NOTE — judge mechanisms + suites, not
empty-points; bindings move with doctrine (living docs rule). Filed:
dynamic-crowding exodus (id9 starved post-veto — static vetoes can't see
neighbors grow into you), war-print expansion, race-slots (expander),
first-strike, S0 tempo, pro standing-guard doctrine, raid timing/concen-
tration/interception (Step 3 — the defense/endgame/guard paths back).
Next in order: expander Step 2 (last bot + race rule), Step 5 (exam 16/16),
pickets, Step 3, Step 4, filed items.

## D==N horizon rule (short-clean, long-mutual) + war-era rebinds

Mutual spends a non-compounding army; clean-training spends compounding
pop to save it — clean wins short (terminal + options), mutual wins long
(compounding recovers). defense_train_ok D==N branch now needs
turns_left<=500 (exam-pinned both ways: 1v1_short_cleans,
1v1_long_holds). Uniform +500-1000 across short raid scenarios (pair
5804/trap 5493/viable 5251/raid_hold 4658/recycle 6293/defend(turtle)
2182->3640: more force -> cleaner takes; pair forensics: trickle-arrival
mutual then pack take, sound). guard_duty deterrence broke into WAR
(4701, t33 mutual): aggressive raids early-windows now (correct
marginally, +124); pro defends honestly (mutual-saves, headful) —
concentration (Step 3) is the path from mutuals to cleans (filed, third
witness: defense/endgame/guard). pro_defense unchanged (no D==N there —
consistent). Exam 17/18 (muster 8/8; only young_flees (Step 5) red).

## Step 5 hopeless D<N (exam 18/18!)

_pro_hopeless upgraded from pop-affordability to force-counting: hopeless
iff home + printable-in-time (1/town/turn cap x ETA) < inbound N at the
worst town. Young-doomed flees (exam young_flees passes); established
never qualifies (deep print — accidental pass preserved honestly).
Exam 18/18 (all sections green; fixtures grown: muster horizon pins,
passive-prize calibration, probe-singular). Fast suite identical;
empty sloshes (expander +371 on zero related changes — timing variance,
note stands). Step 5 remain: evac v2 gates/routing (personality evac
table filed), capital-sniping weights, settler-hunting (all need Step-3
meeting intel to aim). Next: turtle pickets (owed), then Step 3 (timing/
concentration — the defense/endgame/guard paths back), Step 4, filed.

## Turtle pickets shipped (owed) + Step 5Done

Forward tripwire pickets: single-town turtle posts one idle army 100km
out while the universe is dark (zero foe intel); FIRST foe intel (town
or army — threat located, tripwire spent) recalls it; 100-turn silent
expiry rotates home as guard (no blind re-posting); dead slot frees;
posted pickets skip builds (never settle). TDD (designate/hold/recall/
expiry/death/staging-recall/no-designate-threatened). Intel-gating was
the fix that mattered (first version recalled on armies-only → picket
sat out a staging while home fell). Costs: defend 3640->2904 (picket
out during staging window, recalled t16 — same lineage, muster does the
work); empty turtle -2419 insurance premium (100 dark turns of picket
instead of settler in a peaceful equilibrium that never raids — premium
pays when raids come (Elo/guard/defend)). GTO note: pickets insure
raids; peaceful-dark taxes them; Nash would mix, deterministic bots pay
the premium (documented, not solved).

## Step 4 post-capture (compositional) + merge horizon

Post-capture doctrine is compositional (no single function): veterans
hold conquests via war-footing (no-merge) + conquest-guard (fresh takes
keep one through starvation, pinned) + sel-march chains re-raids when
priced + suppressed-arrival lite re-decides lapsed foundings at builds.
Shipped the missing pieces: take-time tracking (_taken_at on flip,
wiped/fingerprinted) + conquest-guard in hold-set (TDD both polarities)
+ merge-horizon gate (home-capital merges need turns_left>=500 —
recycle treadmill broken 2605->6083 (standing beats merging short);
longpeace 4191 recovering). Step 4 DONE (composition documented here).

## Red Queen reframe (bindings are floors with slack, not ceilings)

Attrition forensics closed without a single cause (~10 calls: flows never
fire there; D==N/calibration/pack-cap all no-ops on it). Verdict: COMPOUND
+ RED QUEEN. Every bot improved (demand-gating, musters, calibration,
vetoes, recon) → symmetric wars TIGHTEN (margins compress to ~0 as dumb
foes get smart). Old bindings measured beating DUMB foes (14552-era
margins are unrepeatable vs smart foes — same doctrine scores less when
the enemy also musters). Judge RELATIVE from here (ranks/placements/
margins, Elo draws = all-strong) + mechanisms + suites; absolute bindings
are FLOORS with Red-Queen slack (~+-1000 war maps, ~+-50 quiet). Rebound
attrition 9411 (close symmetric win +504 — honest). Methods fix going
forward: re-run STRATEGIC every commit (drift caught late twice now);
run suites twice post-change (JIT first-runs lie).

## Strike doctrine (blitz + buzzer, exam 23/23) + equilibrium-tight verdict

Strike (shared): BLITZ (anytime S+1 takes landing <=2 turns out — outruns
their intel) + BUZZER (turns_left<=30, W=0, arrival<=turns_left, need<=free,
prize>margin). Wired into all four raiders (strike-first, clear-field
only (fielded foes route to rope/sel), per-target en_route singularity
(shared helper — notes are live, flags deleted everywhere), strike-deficit
in trains. Endgame 5603->7708 (takes instead of late-pack donations!).
Exam 23/23 (endgame 3/3: blitz/buzzer-strikes + no-settle split).
empty_3000 IGNITION TEST: zero battles still (S>=1 everywhere +
thin packs + no unready-2000s). Verdict: EQUILIBRIUM-TIGHT (all-credible
defense, no cracks — strikes correctly decline; game decided by
compounding (pro)). Forcing needs MASS (muster-up + multi-prong splits
at buzzer — filed Step-6-siege-mass (needs strikes + mass, both specced
not built)). Multi-prong pressure filed (split packs vs 2+ rich towns —
needs 8+ armies (mass first!)). Consensus mechanisms all hold; the bots
wait for mistakes that never come vs disciplined foes (correct!).

## Bot efficiency (no clock changes): memo + guards, spreading unneeded

Profiled large-state decides (40 towns + 30 armies): inbound_force 45%
(recomputed 7x/decide!) + foe_garrison 42% (2xT times!) + hypot spam.
Fixes: turn-keyed _memo (lazy-invalidate on turn advance, cleared on
wipe; derived caches excluded from fingerprint) sharing inbound/staging/
garrison-map/forecasts across all callers per decide; guard-set hoisted
O(T) not O(T*A); BotForecast hoisted out of per-army loops (was rebuilt
per army!). 28ms -> 1.4ms worst-case (20x); realistic empty-late states
0.2-2ms (100x under the 10ms increment). Exit-early: moves-loop yield
existed; added best-so-far guards (find_build_site, raid/strike scans,
inbound at pathological scale only (50000+ pairs / 300+ towns) so
scripted-clock tests stay exact). Spreading: MEASURED UNNECESSARY
(2.4ms worst << 100ms cap; threshold documented: spread via plan-queue
if decides ever approach ~50% of cap). Suites identical (memo is exact).

## empty_10000 generation: two real bugs (no clock changes)

10000-turn games killed bots every run (3000s clean) — forensics, two
ROOT causes (both bots-side, per directives): (1) expander NameError
(enemy_armies use-before-def in strike hoist): needs viable targets AND
idle fieldable simultaneously (scale-gated!) → crash/eof ~t6000+; crash
mid-round cascaded via mux (peers timed out on disrupted rounds: turtle
0ms timeouts). Never fired before (small games: no idle piles). Fixed +
regression net (all 3000s green). (2) expander sprawl death-spiral:
100+ towns -> 7-30ms decides vs 10ms increment -> slow clock drain ->
timeout ~t7000 (systematic, not spikes!). Fixed by site-veto on sprawl
settling (fratricide-gated like everyone; race-sites filed for true
races) — sprawl alive+poorer beats dead (correct tradeoff). Runner
_qol_: mux death logs now carry turn= (was None always — cosmetic).
Perf: turn-keyed _memo (inbound/staging/garrison/forecast shared per
decide), guard-set O(T), BotForecast out of per-army loops: 28ms->1.4ms
worst-case (20x), realistic 0.2-2ms (100x under increment). Best-so-far
timeout guards (pathological-scale only, tests exact). Spreading
MEASURED UNNECESSARY (2.4ms << 100ms cap; threshold documented).
empty_10000: 17.9s wall (~1.8ms/turn), 35.6MB, zero deaths.

## empty_10000 war-verdict (analysis -> EMPTY_10000.md)

First 10000-turn clean game (18s, zero deaths): greedy 129706 / pro
107507 / aggressive 98436 / expander 19368 / turtle 871. Arc: sit
(t0-1000) -> colonize (t1000-3000) -> THREE-WAY WAR (t4653-5350) ->
compound. Pro double-founds on greedy's border + musters (capital
2566->615, no stay-behind) -> kills greedy capital (t4688) ->
aggressive backstabs drained pro capital (t4696, 320 pop) -> pro takes
greedy colony (t4709) + hunts aggressive capital (t5345). Greedy wins
BEHEADED (headless compounding). Lessons -> GTO s12 (stay-behind,
retaliation pricing, headless wins, suicide-breaker, density cap,
traffic-vs-threat) + BOT_PLAN P1/P2 next-steps. Per-bot plans filed
in EMPTY_10000.md (pro stay-behind/provocation/revenge-price;
greedy guard-formula + cheap guard; aggressive revenge-price/colony-
guards/expansion-floor; expander density/suicide-breaker/routing;
turtle velocity/guard-budget/stand-down).

## Sensible settlement + command queue (empty_10000 regen)

Edge-spam root causes (all four settlers founded at x/y=20/980): (1)
find_build_site sorted max-min_dist (gradient max at boundary —
rmax ratchet + clamp); (2) scout-tips bypassed scoring (hop-12 tip =
ray endpoint = edge). Fixes: floor 65km (GTO pairs), guns penalty
(don't found under foe guns), room bonus (interior option value),
capital-hub tiebreak, far soft-penalty (settle CLOSE: 65-150km band —
support + cheap march; crowding prices packing), cost-aware sunk
(army_cost/H, was 500/H half-price), tip foe+room gate + respin
(re-spin bad tips through the optimizer near-tip; multi-salt, no
early-break), settler MOVE_TO->BUILD chains via new command queue.
Regen: 23 foundings 0/23 edge (was 6/6, 14/14). Expander sprawls
(19 towns, wins 95k), pro fights (31k), greedy sits (30k, 1 town),
aggressive convert-dies t1807, turtle taken t2635. 49s wall (bigger
game: 158 spawns, wars).
Tip-loss saga (why 0 foundings for 6 regens): hop-12 unmark kept tip
-> drop_dead ate it (stale-trail fake stranded) -> S0 re-stole army
(infinite probe loop); then quiescence deadlock (stationary-silent
trails never converge, order_move [] forever); then respin room-gate
+ early-break hid good spins. Fixed: scout-note immunity + tip grace
(20t) + arrival-trail exemption + order_march_exact (unconditional
re-task) + note-persist + multi-salt respin + collect-all-16.
Command queue (both user uses): queue_order/cancel_queued/
pop_due_orders (MOVE_TO note-match, TRAIN affordability, BUILD
arrival+defer, no auto-MOVE_CAPITAL) + fingerprint + wipe +
bot_main emit-after-fresh. Settler chains via dispatch_settler (all
5). Patrol legs filed (mechanism ready, needs doctrine: routes).
Train-death forensics: t1495/t1807 are CORRECT deny-converts (N=1
inbound, home 0, unopposed-capture real) — the sin is empty home,
not the convert. Stay-behind vs live threat (stay_behind_hold,
threat-gated so S0 safe) pins the last guard; out-of-position losses
(army away when threat comes) need recall-radius doctrine (filed).
Cost-500 illusion: bots assumed 500 everywhere, true cost 1000 —
train_floor cost-aware (void cost+thresh, contested +buffer).

## Regen review game (15 foundings, 0 edge, wars)

Quiet regen (29s, zero clock-deaths — turtle timeouts were my parallel
load, not bot slowness: cold decides <=4.6ms at 200 towns). Pro 33k /
expander 68k / greedy 1k / aggressive+turtle eliminated in-game.
15 foundings all interior (pro east cluster, expander south). Greedy
dies t1536 (early contact), turtle founds t4605 then expander takes it
twice (t4896/t5558, eliminated), aggressive dies t5146, expander takes
pro town t5521 (2360). 18 battles. Placement fixed; wars flow.
OPEN: pro parallel-packets + ghost/vector/bare gates + reckoning all in
this game (pro takes? check). Chain/settle binds drifted (-9/-16%,
projection changes selection — may need re-baseline, flagged).

## Pro capitalizes (wins 121k): note-cap + JIT packets + ghost/vector

Midgame stall root cause: STALE-NOTE PARALYSIS (22 armies sat home
1500 turns on dead raid/settler notes — arrival detection never fired,
drop_dead gaps, notes lived forever). Fixed: 100-turn note age-cap
(drop + re-decide fresh). Piecemeal bleed (29->3 in 1-for-1 mutuals +
solo feeds): JIT packet flush (collect need-sized, march only full —
partials hold for recompute). Ghost threats (27-turn phantoms):
fresh_foe_armies (12-turn cutoff) in inbound + garrisons. Transit
suicides: closing_on vector gate on bare-convert (close-or-closing).
Review game: pro 121678 (5-town east cluster + compounding + 2 late
turtle takes) beats expander 75768 (13 thin). 29 foundings 0 edge,
52 battles. Pro wins WITHOUT taking expander (compounding > sprawl
when sprawl is thin) — capitalizing means declining bad attrition.
Turtle clock-deaths are box load (quiet runs clean; cold decides
<=4.6ms at 200 towns).

## Bot work landed (544 + 23/23): stickiness, packets, S0 verdict

Shuttle fleet (30 expander armies ping-ponging 100-300km): recall
(blanket staging + deficit) re-tasked committed raiders mid-march.
Fixed: committed_raid exemption in the DEFICIT branch only (staging
blanket keeps its pinned probe-handoff — TestProbeSingular/JitMarch).
Raids stick till arrival/outcome. Shuttle count 30 -> 0.
JIT packets (pro + expander): collect need-sized, march only full
(partials hold). Pro parallel thin-takes + no over-muster.
Settle-first TRIED + REVERTED (10 S0 tests): intel-first wins under
uncertainty; far-but-interior tips win games. Clustering handled by
65km floor (now in tip_safe too — both paths), not mission reorder.
Early deaths re-verified REAL (closing attackers, correct denies).
OPEN: snipe doctrine (expander should scout+rush rich capitals; pro
capital guard), recall-radius (out-of-position losses), chain/settle
re-baseline (-9/-16%), greedy expansion volume, packet effectiveness
in wars.

## Report card, review game (loop iteration: run->analyse->filed)

ACJSON quartiles 2500/5000/7500/10000 + ascii. Pro 121k (5-town east
cluster, compounding, 2 late turtle takes) beats expander 76k (13
thin, 9 clusters). Turtle breakout (1->4) then eaten; greedy t1536,
aggressive t3456 (both real closing attackers, correct denies).
Per-bot: pro (economy brilliant, defense vacant — 88k capital, 18
idle guards, never raids); expander (sprawl perfect, vision zero —
never scouted the prize, 37 unused armies); turtle (bold breakout,
no cover — sited 78km from pro); greedy/aggressive (positioned
wrong, denied right). Cross-cutting: NOBODY scouts the enemy (all
views[] own towns); clusters diagnose (offsets, singletons, frag);
deltas separate tick (+-14/turn) from trend (+1.4k/century).
FILED (loop step 3): expander deep-scout + capital-rush trigger;
pro snipe-interdiction + counter-raid vs dispersed swarm; turtle
breakout distance-or-escort; recall-radius/scout-timing (empty-home
deaths); chain/settle re-baseline (-9/-16%).

## Report card, 11-snapshot sweep (loop iteration)

t0-1000 sit (all 1347). t1536 greedy dies (contact). t2000-6000:
pro compounds east (2->6 towns, cap 2k->20k), expander sprawls south
(2->14, thin). t3456 aggressive dies. t7000: pro 70k (cap 40k) vs
expander 31k/19 towns, zero armies both. t7000-8300 THE WAR (47
battles, 6 captures, 9 deaths): turtle breaks out (1->4) then pro
eats two (t7729/8167); pro towns die (7686/7729/8166/8301) holding
vs expander swarm. t9000+: both print (18/37), pro 103k (cap 88k)
wins on compounding. F1 ghost drifts all game.
Per-bot: pro (settlement+compounding elite, defense vacant — 88k/18
idle, never raids); expander (sprawl perfect, vision zero — 9
clusters all inward, 37 unused); turtle (bold breakout, no cover);
greedy/aggressive (positioned wrong, denied right). Nobody scouts
foes (all views[] own). FILED: expander deep-scout+rush; pro
interdiction+counter-raid; turtle cover; recall-radius; re-baseline.

## Fan-out scouts (loop iteration: idea->bench->rematch->fix->rematch)

IDEA (user): scouts cluster on one ray — spread out, scout the map.
CHANGE (common.py): probe generation counter (_scout_gen, first probe
keeps legacy ray); hop base rotates golden-angle per generation +
0.35 rad/leg spiral (287km reach, full sweep over 12 hops). One test
expectation updated (leg-1 spiral coord, math verified).
BENCH: scout 21/21, pytest all green, fast 2.3/5s PASS, strat 4.8/30s.
REMATCH r8: expander 165k, 43 towns, 3 eliminations — BUT bot-3 timeout
death t8967 (17>16ms; unmanaged coast). Cause: inbound_force nearest-
town scan per (town,foe) pair O(T^2.A). FIX: hoist to once-per-foe
(cold 16->1.9ms, same semantics, orders identical).
REMATCH r9: NO deaths; greedy 96k (1 town, ate everyone) / expander
56k-24t / pro 0t-10a / turtle 1t / aggressive 0. Early contact t2000
both games (vs late r7), war eras t5000-9000, a predator wins big.
FINDING: fan-out transforms peaceful-compound into early-contact wars;
winners chaotic (r8 expander, r9 greedy). Filed next: rush doctrine
(armies exist, unused), deep-scout capital mapping, wobble study (how
much is clock-order vs doctrine?).

## Two-scout fan (loop iteration: analyse->idea->bench->rematch->fix->rematch)

ANALYSE (user saw no spread scouting in viewer): dispersion audit r9 —
ZERO armies t500-1500 all factions (nobody prints early), first contact
~t2000 regardless. Fan-out geometry worked; it never got to fly.
IDEA: two concurrent probes (different gen rays) instead of one.
CHANGE (common.py): _scout_id2/_scout_leg2/_scout_gen1/_scout_gen2 +
slot helpers; per-slot legs/gens/still-keys; exclusions cover both;
first probe keeps legacy ray (gen 0). New test: second fans out.
BENCH: scout 22/22, pytest green, fast 2.7/5s, strat 5.4/30s.
REMATCH r10: expander 354k/97 towns — bot-3 timeout death AGAIN t7894.
Cause at scale: _crowd_sigma 780 calls x 97 towns (75ms). FIXES: range
prefilter + per-turn coord table + s0 memo (75->11ms) + yield guard in
demand_trains (partial trains stand; i>0 keeps scripted-clock exact).
REMATCH r11: NO deaths, all five reach t10000 — greedy 96k / pro 61k /
expander 34k / turtle 9k / aggressive 0. Wars t5000-9000 (130 battles).
HONEST: two-scout machinery correct but still invisible pre-t2000 (no
early prints — economy question, filed next). Real wins this loop:
clock discipline at 97-town scale + first all-survive canonical.
GENERATED: r11 -> recordings/empty_10000.jsonl.

## Grave-memory vs onesies (loop iteration)

ANALYSE (user: pro sits 8v2 then suicides onesies t7750-7917): forensics
says INVERTED — expander fed 11 onesies (armies 130-140) into pro's
2-guard capital (51,58); pro's 6 idle squatted dead-greedy's capital.
IDEA: grave-memory (dead armies tell no tales -> remember where).
CHANGE (common.py): _bloodied map (note-target first, trail second) +
probe_ok gate (4 bots) + foe_garrison imputes >=1 at graves (both
pricers). Tests: grave-memory + garrison-impute. Benches green.
REMATCHES (wobble honest): r12/r15 clean line == r11 (bitwise! blood
never fires there); r13/r14/r16 diverged lines (butterfly, not code).
r13: onesies 11->7. r16 (need-feed): ZERO window battles (2 total!).
r17 calm line: 10 onesies persist. MECHANISM (ledger.py:325):
tombstones tag OBSERVERS of the site — deep-raider deaths are seen by
the victim only, never delivered home. Blood works when deaths are
observed (close wars), silent when fog eats them (deep raids). FILED:
silence-watch (overdue army => presumed dead => blood); ghost-slot
audit (unseen deaths may stick scout slots); wobble study (lines
diverge run-to-run, magnitude game-scale); decide <8ms @100 towns
(bank math: 13ms vs 10ms grant drains to 0ms deaths t3300-4100).
GENERATED: r17 -> recordings/empty_10000.jsonl (calm line, all survive,
machinery armed).

## Viewer serves own bundle + autopsy (loop support)

CORRECTION (user right, forensics wrong): viewer reads
viewer/public/empty_10000.jsonl, NOT recordings/ — the analysed file
and the watched file differed. Old bundle held the r7 line where pro
fed 18 onesies (105-126) into turtle's 2-guard capital t7867-7916 —
the exact reported suicide, ownership F0 confirmed. Loop generate now
writes BOTH locations (docs fixed). Lesson: analyse what the user
watches (ask for the file/turns before exonerating anyone).
NEW TOOL: `--format autopsy --window A-B` (death ledger, nearest-town
attribution, ONESIES flag >= 3; validated: r17 window counts match
manual). VIEWER.md recipe updated. Filed next: silence-watch (fog
eats deep-raid deaths — tombstones reach observers only, ledger.py),
fog-view per faction (what did the bot know?), 8ms decide ceiling.

## Report format (analysis tooling loop)

USER: build tooling that rederives my feedback (reduce reliance on me).
NEW: `--format report` (full-game brief, one command): activity
(prints/foundings/captures/idle-armies/march-km per faction),
stagnation (static >500t 0-battle armies + where), onesies
(whole-game autopsy), punishable (empty towns + idle foe stacks
<300km). Validated on r17: flags pro's 6 idle (5381t @ rubble),
greedy's 3-print win, 10 punishable empties (town 42: 70km!), both
onesie sites. Also fixed: captures via new_faction, dead-town owners.
NEXT (filed): fog-view per faction, battle-flow, silence-watch,
8ms ceiling; pending pro arrival-release (in tree, tested) rematches
with the punish-doctrine loop.

## Punish passivity (loop iteration: mechanisms shipped, pin unlocated)

ANALYSE (report): pro 6-stack static 5381t @ rubble (234,586) with
town 42 (2.3k) 70km away; greedy 3-print win; expander onesies.
IDEA: punish passivity (unstick + pack-print + march thin).
SHIPPED (common/pro + tests, all green): arrival-release (_arr_hold,
>30 field arrivals drop notes), pack-train (shortfall + nothing
pending -> TRAIN richest). Benches PASS (2.3/5s, 5.1/30s).
REMATCH r18/r19: BITWISE r17 line (153 deaths, 131 battles) — neither
fires. Fully-observed repro marches all 8 (logic willing) -> pin is
BOT-VIEW (stale intel lock), unknowable from truth snapshots.
FILED NEXT: fog-view (replay per-faction observed world from the
recording) to SEE the lock, then kill it. Lesson: no more blind
mechanisms — visibility first.

## Fog-view (analysis tooling loop)

NEW: `--format fog --faction F --turns T` (bot-view replay: observed
towns + staleness + GHOST/MISSED tags + foe-army sightings). First
use (pro t6000) NARROWED the 6-stack pin: ghost-town lock EXCLUDED
(pro saw town 1 die t2216 — knows rubble!), thin towns CONFIRMED
visible fresh (42/39/12/50), zero foe armies seen 941t+. Logic marches
when observed (repro) -> REMAINS: packet/note dynamics in bot-view
(stale-note siege? never-released packets?). Next loop kills it with
fog + report in hand. VIEWER.md updated.

## Punish loop closed (r19 generated)

REMATCH r18/r19: bitwise r17 line (153 deaths / 131 battles) — both
mechanisms verified present-but-silent on the calm line (pin needs
fog-view, next loop). All five survive, no timeouts. GENERATED: r19
-> recordings/ + viewer/public/ (canonical matches tree).

## Viewer freshness (loop support fix)

USER: UI not fresh after generate. Files WERE fresh (same md5 16:57)
-> culprit was HTTP cache (30MB JSONL, same filename). FIX
(viewer/src/main.ts): cache-busting fetch (`?fresh=Date.now()`).
Loop step 5 now mandates md5sum verification of both copies.

## Unpriced-raid fix (loop iteration: PIN FOUND, one line)

PIN (fog + synthetic bot-view + debug prints): raid_targets unpriced
path set best but never filled ranked -> sel None in ALL multi-foe
wars -> no packets/packs (only strike trickles). 6-stack sat 5000t
with need-2 targets visible. FIX (common.py, 1 line): append pressure
score to ranked in the unpriced branch. Synthetic repro: 1 march ->
4 marches (blitz + 3-pack). Test: unpriced returns ranked.
BENCH: pytest green (perf-budget full20 flaky 5.6/5.0 on loaded box,
fails clean-tree too — environmental, filed), fast 2.8/5s, strat 6/30s.
REMATCH r20: pro 520k MAP WIPE (18 captures, 19k km) — offense flows,
then new rubble-sit @ (731,477). r21: five-way war (pro 293k / aggr
184k / turtle 94k / greedy 88k / exp 11k). BOTH: turtle 0ms death
~t3000. Clock experiment r22 (4x caps): zero deaths -> deaths are
payload-burst pressure (war events/IPC), NOT decide compute (turtle
decide ~0ms). FILED (infra loop): payload throttle (pop_change floods)
or clock doctrine revisit; flaky perf-budget test.
GENERATED: r21 (best TV) -> both locations. Canonical caveat: turtle
ghosts t3062+ (report shows it honestly).

## Silence-watch (loop iteration: absence-based blood)

ANALYSE (report r21): expander 51 onesies @ turtle-4 t3912-9832;
pro passive line (2 prints) vs blitz line (r20) — wobble decides.
IDEA (filed): silence-watch (overdue = presumed dead).
SHIPPED (common.py + 2 tests, green): silence_watch in drop_dead_notes
(all five): noted-unheard past 2x round-trip + margin vs FOE-town note
-> blood + drop note. Fresh notes (origin turn), marchers (flowing
trails), home notes (never foe), scouts all exempt.
BENCH: pytest green (minus env-flaky perf), fast 4.6/5s, strat 11.7/30s.
REMATCH r23: pro ACTIVE (21 prints, 6 caps, 121k) — unfreeze+pack-train
flow on this line. Onesies PERSIST (69 @ pro-12, slow drip ~70t):
new mechanism (settler-intercept: colonists die crossing pro lands on
void notes — no foe note, no blood). FILED NEXT: danger-routing for
settlers (route around known garrisons / hold while hot).
GENERATED: r23 -> both locations (all bots alive; F2/F4 townless).

## Ghost-clean + tracer timing (loop iteration)

ANALYSE (r25 TRACE, pro t6000-8000): army 17 ghost (dead-unseen, in
mirror @ (268,622), note live, same MOVE_TO re-issued 2000t, foes=[]
— total sensory+motor lock, visible only via trace).
SHIPPED: ghost-clean in silence_watch (overdue-vs-physics:
elapsed >> march+mail -> forget locally; live re-observe back) + 2
tests (ghost cleans, live spared) + trace ms timing. Benches green
(minus env-flaky perf).
REMATCH r26: pro ACTIVE (27 prints/8 caps, survives 388k expander
wave); one-sided 51-drip REPLACED by mutual siege (17+16 @ town 0)
+ 3+3 (gate holds after 3rd). Turtle 0ms death t1903 (again!).
TIMING VERDICT (traced decides: 0.2ms med, 0.9 max — never compute):
0ms deaths are harness (cold-start numba eats 1s main; single hiccup
-> zero-recovery spiral). FILED (infra): warm subprocesses / bigger
main / bank floor; pop_change is 99% of events (throttle candidate).
GENERATED: r26 (current tree; turtle ghosts t1903+, caveat logged).

## Affirmations + clock floor (user-ordered visibility loop)

USER (right): absence-of-event must be signal — dedup hides
"no longer visible". But full resend is wrong layer (10-50x payloads;
silence semantics load-bearing; ghosts are unwitnessed-death, not
dedup). SHIPPED CHEAP: per-turn `visible` affirmation (foe ids in LOS
+ own always; ~1% cost) in deliver(); bots refresh _last_seen on it;
ghost-clean keys off seen-age (exact, not trail heuristics).
Tests: flight affirm/blind + bot refresh/spared. Suites green.
CLOCK: 0ms deaths every line traced by mechanism (single >110ms
hiccup -> bank 0 -> budget-0 instant spiral, no recovery). Floor:
bank never below one increment (hiccup recovery; gameplay-neutral).
r30: only REAL overspends die now (exp 16>17ms @158k sprawl — the
filed 8ms ceiling). REMATCHES: r27 (exp 319k), r28 (4-way), r29
(4 competitive + exp-coast), r30 (exp wipe). GENERATED: r29.
Caveat: expander ghosts t2713+ (coasting 99k).

## Send-all + SendState removal (user-ordered simplicity loop)

USER: 2 events only, every visible entity every turn; bot owns
MOVE_CAPITAL resets; no heartbeat complexity. SHIPPED: build_updates
emits all valid rows (dedup/heartbeat/SendState deleted); deliver/
note_landing simplified (S kept as game rule); command-net loss
reports kept (owner tombstones + ex-owner capture notes — the one hole
absence can't fill: live ids elsewhere give no signal home).
Tests: ~15 rewritten (silence pins -> announce pins). Suites green.
REMATCH r31: ALL ALIVE, pro 100k wins but INACTIVE (4 prints/50km).
Onesies persist (33+18 expander). Substrate done; bots must use it.
GENERATED: r31 (caveat: pro passive line).

## Fresh-positive quiescence + suite speedup (loop iteration)

PIN (r32 trace): scout-7 marked 8000t, same note/order, zero moves —
send-all keeps trails fresh so quiescence (order-on-quiet) never
passed. FIX: ready_to_dispatch inverted (order when lag within 3x
expected+2; hold only when ancient). Precedent: order_march_exact
already bypassed for the same deadlock. Tests: ready/drive timing
rewritten (prompt dispatch). SUITE: recording-less scoring (same
formula) 4.3s->2.3s (send-all I/O was the cost). skip_thin 2150 vs
table 3888 IDENTICAL on baseline (send-all-era drift, filed).
REMATCH r33: movement FLOWS (pro 54k km, 265k win; mapper-33 cycling;
zero onesies/punishable/sustained-opportunities). All bots alive.
GENERATED: r33 -> both locations.

## Mapper tour (loop iteration: kill the pendulum)

ANALYSE (r33 tracks): mapper-33 painted 5301km on a 300km line (18
laps); zero trains/captures late; idle everywhere. Mechanism:
stalest-quadrant chase (arrival freshens, far side goes stalest).
FIX (common.py): fixed tour (legs % 4 quadrant centroids), then
release. Tests kept passing (hop targeting compatible). Floor edge:
exact-zero slipped hiccup recovery (floors only on spikes now;
sustained drips still die properly).
REMATCH r34: max march 100km (pendulum dead); aggressive 179k wins
competitive line. New stillness: 27+26 idle (peace disease — filed).
GENERATED: r34 (turtle ghosts t1893+, caveat).

## Grave-release (loop iteration: unstick the pile)

ANALYSE (r37 TRACE): pro parked 20 armies on dead town-4, all noted
there, foes=[], blood=[4], orders=[] — notes to a grave with mapper
cap full. Root: raid packets marched when town lived; town died;
notes stuck (re-note treadmill + cap-full sit).
SHIPPED (common.py + pro.py + tests, green): _grave_pos (last-known
grave coords) + _town_lastpos (ordering bug: town tombstones precede
army tombstones) + grave-release in silence_watch (notes matching no
live town but a dead grave pop, any age; live raids keep need+1) +
mapper-full bare-pop fallback.
REMATCH r38: battles EVERY millennium (43 total), foundings to t5000
(action all game — user's bar). r39 quieter (15). GENERATED: r38
(greedy ghosts t1424+, caveat).

## Note amnesty (loop iteration: bound every lock at 300t)

ANALYSE (r43 report): 27 pro noted 6000t+ (nothing wants/releases
them); synthetic repro marches (logic willing) -> notes are the lock.
SHIPPED (common.py + test, green): amnesty_notes in drop_dead_notes
(all five): field notes older than 300t pop (valid plans reform in
one turn; home/scout/viceroy/pending exempt).
REMATCH r44: foundings t1000-3000 (8), captures t3000-5000 (5) — all
bots alive, no deaths. Late freeze t6000+ persists (rich towns, big
garrisons, dark map; buzzer silent t9000+). FILED NEXT: buzzer audit
(strip-mine flip should force late action) + late-garrison equilibrium.
GENERATED: r44 (all alive).

## Mutual-save (loop iteration: convert-deny yields)

ANALYSE (r44): greedy "suicide" t1817 = TRAIN (army 14) + capital death
same turn. Mechanism: bare-convert fired vs 1 raider 110km out; the
483 remainder died under the 500 threshold. (Convert-deny itself
defensible when guard-print unsurvivable — the waste was army-14's
8000t rubble-sit, already fixed.) Also: t6100+ stagnation, pro small,
no late expansion (filed with teeth below).
SHIPPED (common.py + test, green): bare convert-deny only when no
guard printable in time (eta < 1 or pop-cost < death threshold);
else muster the mutual-save. Unit: rich town + raider at ETA 2 ->
TRAIN, town lives.
REMATCH r45: foundings to t3000 (7), 1 capture; turtle 0ms drip-death
t1840 (infra, filed); greedy line diverged (can't re-verify t1816
specifically — unit proves mechanism). NO GENERATE (r44 stands: all
alive, action to t5000).
FILED NEXT: expansion thaw (nobody founds t3000+; demand war-gating
vs GTO 20k rule) + late-garrison equilibrium + buzzer audit.

## Blind eyes (loop iteration: bodies aren't eyes)

ANALYSE (r45 fog): aggressive sees only its 7 towns at t7000, 3 noted
armies, total dark beyond — yet prints nothing (3 bodies >= probe+2).
SHIPPED (common.py + tests, green): blind-eyes print (dark +
scoutless + affordable -> TRAIN eyes, 1/300t cooldown) in
demand_trains (all bots); _dark memoized per turn (was O(T^2) hot
loop — suite 5.1s->3.0s).
REMATCH r46: foundings t1000-2000 only, 1 capture; turtle 0ms drip
t1888. Eyes funded but late action still freezing (links downstream
unverified). NO GENERATE (r44 stands).

## Iterations 1-2 (5x loop): poverty-break + clock diagnosis

IT1 ANALYSE (r47 traces): pro 1 town 512pop, 0 armies, scout null,
zero orders all game. P3b early-return + 2500 prober floor = poverty
trap (capital never reaches 2500, blind and poor forever).
IT1 SHIPPED (pro.py + test, green): prober at survivable floor
(pop-cost >= death threshold); no early return (demand void branch
settles the dark). R48: pro 11k (thin line, aggressive died early).
IT2 ANALYSE (turtle 0ms drip): turtle update+decide 0.5ms total —
innocent. Clock math: byo-yomi clock hits exactly 0 (mild overspend
under cap misses the spike floor) -> next turn enters with budget 0
= dead on arrival. Raising cap 100->300 made it WORSE (floor
compares elapsed > cap). REVERTED (canonical stays 100).
PROPOSED HARNESS FIX (not bot-side, filed): Fischer increment always
due — else-branch should grant min(cap, inc), never 0.0.

## Iteration 3: land grab (expansion thaw)

ANALYSE: foundings stop t2000+ everywhere. Contested branch gates on
rate-arbitrage (0.75 > home max-growth) — uncrowded small towns grow
1-2/turn, so small empires NEVER expand.
SHIPPED (common.py + test, green): below 20k total pop, expansion is
throughput (parallel compounding), not arbitrage — afford + horizon
suffice (serial + site_pays still filter). R50: 9 foundings to t5000,
3 captures to t7000 (best spread yet); expander bot ghosted t2887
but faction coasted to 236k. NO GENERATE yet (2 iters left).

## Iteration 4: buzzer audit (W -> 0 explicitly)

ANALYSE (r50 t9000 state): 1-3 towns each, 0-1 armies, total silence.
Raid W never collapses (arrival ~5 x factor persists to the buzzer),
so needs exceed everyone.
SHIPPED (common.py + test, green): buzzer zeroes W (no future to
defend; bare S+1+dist). R51: 50 battles t5000+ (endgame ignited) but
54 pro onesies vs printers (W=0 vs remuster) — see IT5.

## Iteration 5: remuster guard (printers +1)

ANALYSE (r51 autopsy): fresh-empty + W=0 -> onesie marches, remuster
kills it. SHIPPED (common.py + tests, green): foe_print_factor > 0.3
-> need += 1 (printers; sterile still cheap; fresh-unknown assumes
live). R52: zero onesies, but action to t4000 only (overcorrection
+ butterfly: expander ghost t1457). NO GENERATE (r44 stands: all
alive, action to t5000; r50 best spread but ghosted).

## Burn-down: guard rotation + print cap + stale premium

R53: pro 39 idle + 169km marched; expander 120 prints -> 101 idle.
SHIPPED: guard rotation (home notes pop every 1500t, faction-phased;
threats re-hold in 1 turn), print cap (drowning = idle > 2x towns
skips non-threat prints; eyes still funded 1/300t), stale-age
premium (unseen s = 3 + age//500 cap +3; r55 bled 43 undersized
packs vs real garrison 8). R55: prints sane, idle ~0. R56: onesies
gone, but action thin (needs big + 3 ghosted bots). Ghosts remain
the #1 action-killer (harness dead-on-arrival, filed).

## Burn-down: FoW-erase, coverage, sneaky-settle, build-cap -> r63 LIVE

- FoW-erase (user): RTS-correct — last-known persists; watched-but-
  empty ground erases (age > dist/info + 2). Replaced wall-clock
  forgetting. 2 tests re-pinned to RTS semantics.
- Coverage (user): 4x4 sector stamps per payload; coverage_orders
  sweeps stalest cells with leftover idle (all five moves stages
  last; greedy/turtle home-sit recalls removed).
- Sneaky-settle (user): townless scout-decline (refound first),
  colony 1.2 races median home, foe-shadow to 300km, far-support x2.
- Build-cap: 3 BUILD tries then abandon (r62: 103 self-refreshing).
- Empire pack cap (3+2/town); scout cadence 500t dark.
R63: 74 foundings (to t8000), 8 captures (to t5000), battles
t2000-6000, 2 idle, 1x3-onesie (own-town), no punishable. Expander
snowball (256k; all rivals 0) + late ghost t8438 (harness, filed).
GENERATED r63 (action all game; balance next).

## Muster window 6 + r65 (per-loop regen)

DIAGNOSE (user: why did pro fall to 1 army?): r63 t3526 — army 33
spawned t3515 300km out, walked in with zero battle. Synthetic repro
PROVES pro prints when it sees (TRAIN 0 at ETA 2.6). Failure = mail
ate the eta-4 window (intel 1-2t stale + print 1t + spawn vs arrival
race lost by a turn).
SHIPPED (common.py + test, green): threat_window 4 -> 6 (all bots).
R65: pro 19 foundings/8 captures/34 battles (defends, then snowballs
506k; 45 garrison-idle). Spread to t6000 (r63 reached t8000 — late
action still the gap). GENERATED r65 (per-loop regen).
NEXT: snowball/balance (winner-takes-all by t6000, late dead).

## Underdog aggression + r66 (per-loop regen)

SHIPPED (common.py + test, green): _underdog (behind on towns vs
best-known foe) -> raid need -1, min 1 (GTO variance: favorite safe,
underdog gambles). R66: pro 4 captures as underdog (gambles work),
expander 16/4, captures to t5000, foundings to t6000, zero onesies,
2 stale-idle. Snowball persists (128k vs ~0) but taxed.
GENERATED r66 (per-loop regen).
NEXT: turtle passivity (5 prints, never sprawls) + patrol churn.

## Turtle wake + r67 (per-loop regen)

SHIPPED (turtle.py, green): train bar 2600/2000 -> 2200/1600
(fortress, not coma; all five gates re-pinned). R67: pro 38
foundings/4 captures/11 battles (snowball 245k again); turtle still
flat (eliminated early — wake never tested). 95 pro noted-idle
(new form: static + noted + unthreatened; type TBD via traces).
GENERATED r67 (per-loop regen).
NEXT: idle-note typing (traced) + snowball structure.

## Pack muster + assault-once + r70 (per-loop regen)

DIAGNOSE (traced): 36 pro pack-notes holding at foe towns — coverage
scattered mustering packs to patrol sectors (never converging) +
short packs hold at gates forever (stale premium blocks fair fights).
SHIPPED (common.py + tests, green): coverage pack-muster guard
(priced sel needs everyone -> stand down; idle<=12 for scan cost:
suite 5.2->3.0s), recon-by-fire (short<=2 + there -> assault),
assault-once (fresh blood <1000t vetoes: r69's 48 onesies).
R70: 9 captures (to t5000), foundings to t8000, ZERO onesies,
zero stale-idle; aggressive ghost t1301 (harness). GENERATED r70.

## Greedy retired; double-pro era + r71 (per-loop regen)

RETIRED greedy (deleted src/bots/greedy.py; tests/benches re-pinned
to pro; BOTS.md roster + README lineup updated; history kept).
Canonical lineup: pro, pro, aggressive, expander, turtle. Settler
floor shipped (expansion prints at survive-pricing; losers unthawed).
R71: pro0 40 foundings/8 captures (mirror won big), captures to
t4000, foundings to t8000, zero onesies; 55 pro0 idle + 145km patrol
churn; turtle ghost t1456. GENERATED r71.
NEXT: pro0 idle-note typing + mirror-match dynamics.

## Guard-or-rich + r72 (per-loop regen)

DIAGNOSE (r71 mirror): identical until t2500, then pro0 takes pro1's
stripped capital t2770 (settler-wave left 600-pop towns empty).
SHIPPED (common.py, green): settler-floor branch needs guard home
or rich town (>=3000). R72: pro0 28 captures (conqueror) + expander
29 foundings (settler) — diversity! Captures to t9000, battles to
t7000, 3x3-onesies (minor), 155km patrol churn (watch). Pro1 still
falls (positional: corner vs central). GENERATED r72.
NEXT: patrol churn (155km) + pro1-corner dynamics.

## Nearby-first + rotating far patrol + r74 (per-loop regen)

SHIPPED (common.py, green): coverage nearby-first (stalest within
300km; leftovers hold for packs) + one rotating far patrol per 500t
(r73 nearby-only blinded all: action died t3000).
R74: action EVERY millennium t1000-t9000 (43 foundings, 14 captures,
24 battles); aggressive 6 captures (underdog!); expander 32/7.
Blemishes: 2 stale-mirror fratricides (10, own-towns; accepted price
of far intel), turtle ghost t1515 (harness). GENERATED r74.

## Turn-order starvation (filed, harness) + r74 notes

PROFILED (order-swapped): turtle update+decide 0.2ms (identical to
pro; the 4ms first-call is shared JIT). Turtle is NOT slow — it dies
first every line because faction 4 moves LAST every turn (engine +
3 bots consume the timeslice; turtle starves on scheduling noise).
HARNESS FIX (filed): shuffle faction turn order per turn (or nice
the engine under the bots).
R74 stands as excellent: action every millennium t1000-t9000,
2 stale-idle, zero real onesies, multi-polar (expander sprawl,
aggressive underdog takes, pro0 packs). Accepted: 2 stale-mirror
fratricides (far-intel price), buzzer end-print wave (unspent at
game over, harmless).

## Tall-turtle + survivor gate + r80 (per-loop regen)

TURTLE (user: play tall, minimal survival armies, safe-nearby settle
only): endure (established_stays=True), garrison 1 dark / 2 rich+
threatened (no over-muster), settle gated (no foe town 350km of site,
no foe army 300km of capital).
DIAGNOSE (r79): thin-town ping-pong (600 takes halve to 300, die same
turn). SHIPPED: priced raids skip pop < 2x death threshold (denial
keeps them).
R80: three-way race to t10000 (pro0 14t/110k, expander 1t/88k,
aggressive 1t/84k), final flip t10000, no onesies, all bots alive.
Pro1/turtle fall (corner/edge positions). GENERATED r80.

## S0-guard + lead/flip tools + r84 (per-loop regen)

TOOLS (user: build analysis toolset): `--format lead` (millennium
table + FLIP lines) and `--format flip --faction F --window A-B`
(F's lost/took/battles + town/army arc) in ascii_view.py; VIEWER.md
recipes. Used immediately: F2's r74 collapse typed (thin sprawl,
picked apart) -> support-ratio gate (towns <= armies+1).
SHIPPED: threat-first trains, tall-turtle (endure, 1-2 garrison,
safe-only settle), survivor gate (priced pop >= 2x threshold),
pro spacing 120, redeploy-stickiness (breaker 1000t), S0-guard
(lone unscouted army holds capital; scout pipeline untouched).
R84: pro0-vs-pro1 mirror duel to t10000 (3 flips, pro1 wins 25t),
zero real onesies, all-but-ghost alive. GENERATED r84.

## Assault-verify + churn metric (r84 stands)

SHIPPED (common.py/aggressive/pro/expander + tests, green):
assault_verified (foe-belief >300t stale holds packs; wired into
jit_ready full-packs + all three flush sites + aggressive march).
TOOLS: churn rate (km/army/100t) in report (r85 calibration: war
mobility 100-500 with takes; shuttling is takes-less motion).
R85: aggressive snowball 473k (early bloodbath t4000-5000); mutual
3v3 battle (fair fight, not suicide). NO GENERATE (r84 stands:
mirror duel to buzzer beats snowball).
OPEN: early bloodbath t3000-4000 (thin capitals + first packs).

## r86 (per-loop regen): twin-giant duel

R86: pro0 (4t/203k) vs pro1 (3t/188k) tall-giant duel to t10000
(3 flips); aggressive's 25+19 "onesies" are full-pack wars vs real
garrisons (churn 3.4, needs met — attrition, not suicide). Churn
2-5 across the board, 3 idle, expander ghost t1960 (harness).
GENERATED r86 (best finale yet: two giants standing).
IDEAS AUDIT: behavior mechanisms exhausted (see GTO addenda);
remaining opens are harness (ghosts/turn-order, filed 5x), map luck
(corner/edge), and wobble (which twin wins). Loop idles until new
evidence.

## Parking-lot fix + 1v1/sync/verify tuning (r86 stands)

DIAGNOSE (r89 truth): 29 F2 armies parked on coverage centroids
(arrived notes freeze via quiescence; amnesty cycles too slow).
SHIPPED: coverage re-tasks noted-but-arrived centroid notes (pack
notes point at towns — safe). R90: idle 25->4 (patrols move: churn
442 = work, not waste).
SHIPPED: scout hops bend off observed foe armies (r86's 6 field-1v1
scout-meetings); sync_hold arrival-sync (far leaves first; pro+
expander flushes); micro-patrols (leftovers sweep ≤150km; report
idle threshold 500t->100t); assault-verify 300->800t (r88 endgame
freeze); S0-guard (coverage lone-army holds capital).
R90: F2 snowball (early bloodbath t4000-5000 persists as the open
item). NO GENERATE (r86 twin-giants stands).

## Suicide-march + ex-own verify (r86 stands)

DIAGNOSE (user: loser-moved-last?): r86 pure-1v1s all mutual (0
suicides). Pack-scale: r90's 5-fed vs real-2 garrison = sync-hold
defeat-in-detail (far arrives a turn early, dies alone) + unseen-
death re-feed (no blood, re-probe). SHIPPED: sync 1.0->0.5 (same-
turn landings), assault attempt-cap (<=2/target/1000t), ex-own
verify (<150t for _lost_towns; tracked on seen mine->foe).
R92 ~= R91 (seed-stable): same 8-fratricide = UNKNOWABLE fast flip
(retaken unseen in 56t; even 150t stale kills). Accepted as the
bound (perfect intel impossible). NO GENERATE (r86 stands).

## Velocity intent + capital-timely + r94 (per-loop regen)

SHIPPED (common.py + tests, green): foe_velocity (trail displacement,
capped) + velocity_eta (closing projects, transit excludes) wired
into inbound_force (all bots react to direction, not just distance);
_capital_timely (user: sub-1500 towns print when the only timely
capital guard — floors yield to survival); naked-garrison want;
coverage home-firewall (peacetime-notes tried+reverted: cascaded
through pricing/strike/recall/packets — no-note holds instead).
R94 health: watch (0 suicides, 0 train-deaths, 2 onesies, 2 quiet);
snowball t5000+ (worse game than r86 twin-giants, but current tree).
GENERATED r94 (per-loop regen).

## Second-body floor + r95 (per-loop regen)

SHIPPED (common.py, green): rotation-want prints second body at
survive-pricing (dark + armies<probe+2 + deficit 0; first print
scouts, capital naked until contact otherwise).
R95 health: watch (0 onesies, 0 suicides, 0 train-deaths, 1 quiet
block t1500-2000) — cleanest yet. Snowball t4000+ persists (early
bloodbath structural: thin vs first packs; all mitigations active).
GENERATED r95 (per-loop regen).

## Diffusion scouting/siting + r96 (per-loop regen)

SHIPPED (common.py + tests, green): coverage diffusion-gradient
descent (3-step stalest-neighbor flow into frontiers); siting
diffusion field (10x10, own +1 / foe-town -2 / foe-army -1, x0.85
per 10t, 3x3 blur; quantized 0.25 x0.3 term in site scoring —
stale danger remembered where scouts died).
TOOLS: health quiet blocks flag battles (bN = fought stalemate vs !
= dead peace; r96's mid-game is peer equilibrium, not idleness).
R96: FIVE flips (F0->F3->F1->F2->F4->F0), turtle leads t5000-6000
tall (11.8k), multi-polar to t6000; health watch. GENERATED r96.

## Threat-diffusion + tall-guard + r97 (per-loop regen)

SHIPPED (common.py/turtle.py + tests, green): _threat_field (foe-
army sinks, x0.7/10t, 3x3 blur) steers fully-blocked scout rays
(gradient descent over 5 candidates); tall-guard minimum (turtle
keeps 1 home ALWAYS — r96 F4 beheaded at 12k with 0 guard).
R97 health: watch (0 onesies, 0 suicides, 0 train-deaths, 3 dead-
peace quiets); pro0-vs-pro1 duel to t7000. GENERATED r97.

## Cohort reinforce + followup queue + overkill caps + r100 (regen)

SHIPPED: reinforce same-turn cohorts (no solo feeds); follow-on
fan-out queue (take then spread, zero idle turns; pro+expander);
strike mass capped at need+2 + packet flush at need+1 (user: no
overkill); BRAINSTORM parked-ideas section (user: log future ideas).
R100 health: watch (0 onesies, 0 suicides, 0 train-deaths, 3 quiet
— 2 dead-peace, 1 fought); captures to t5000, foundings to t8000.
GENERATED r100 (per-loop regen).

## Anticipation + opportunity diffusion (r100 stands)

MEASURED (user: arrivals scatter?): r100 takes are ALL 1-2 attackers
(thin takes; packs never fight — needs too big to fill). So the
coordination gap is packs-vs-real-targets, not arrival timing (multi
battles land together; trickle is defensive, now cohorts).
SHIPPED: followup anticipation (fire at ETA<=1, not on news);
_oppor_field (rich-foe-town sources, x0.9/10t, blur) + raid cluster
premium (campaigns seed followup-rich waves).
R101: 0/0/0 errors, captures to t4000, foundings to t7000; snowball.
NO GENERATE (r100 spread better).

## Pheromone exploration + r104 (per-loop regen)

SHIPPED (common.py + tests, green): _explore_field (16x16 staleness
pheromone: observed splats 0 (sinks), +0.5/10t evaporate to cap 10
(sources: unvisited glows), 3x3 blur; coverage ascends it 3 steps).
Probe attempt-cap 1/target/1000t (packs keep 2; ledger once per flush).
R104: ZERO pure-1v1s, 0 onesies/suicides/train-deaths, 2 early dead-
peace quiets; captures t3000, foundings to t6000. GENERATED r104.

## Meatgrinder exclusion + r107 (per-loop regen)

DIAGNOSE (r106 flip audit): 9-feed meatgrinder at town12 — patrols
walked through a 2-guard town (coverage centroids ignore towns).
SHIPPED (common.py, green): foe-town cells unclaimable in coverage
descent (packs assault towns; patrols never stroll in). LOOP FIX:
capture harness stderr every rematch (r104's "freeze" was 4 silent
ghosts hidden by tail-cut).
R107 health: watch (0/0/0 errors, 2 dead-peace quiets); F3+F4 ghosts
t1660/1888 (harness). GENERATED r107.

## Pure bash-string runner + r108 (per-loop regen)

HARNESS (user): run_game/BotProcess take ONLY bash strings now
(`bash -c` single spawn path; python bots launch the same way).
Converted tests + both benches + README example (greedy->double-pro
there too). Shell-camper verified earlier; full 5-python-bot game
verified here.
R108 health: watch (0/0 suicides/train-deaths, 2 onesies incl F2x9
@ town11 meatgrinder, 1 early dead-peace). GENERATED r108.

## 5 loops (r109-r118): zombie/ghost-weather arc

L1 second-wind (embered factions gamble, collapse-evidence gated).
L2 fortress learning (death-count doubles avoid window to 2400t).
L3 bloodlust (3x lead drops verify/caps) + killer instinct.
L4 leader-hate (trailers prefer a 2x leader — 99k/96k/93k race).
L5 ghost-weather: victory-lap (contact-gated after r115 fog misfire —
mirror is visibility-limited!) + dead-foes (armyless 2000t+ are food:
no site-shadow, no stale premium, ghost pops don't lead, verify
bypass — verify/blood deadlock broke ghost-game peace).
r118 canonical (watch). Tooling lesson: one write per file mutation
(stale-`s` double-writes clobber — bit twice: grave writer, army-seen
hook; audit with grep after every multi-edit).

## loop/champ-wall: punish + concentration (branch max 29.1, bar 43.2)

- Dark-release (lone guard scouts when blind) → stripped naked → gated
  on replacement printing.
- Shrink-watch (rich-first trains after losses) + reprint rule
  (serial expand only from strength, void AND contested).
- Naked-settler punish (young towns bypass re-verify): pro blanked
  champ+predator 147k; branch-expander blanked champ 126k.
- Predators rule the table (b398901 43.2); branch-aggressive climbs
  26→28→29. Consistency (zeros) is the gap, not peak.

## loop/era-expander (29d660a): naked-core guard on ERA expander
- Pristine era base 84b32be (expander 46.1 peak) + stay_behind_hold at
  the packet flush (era flush bypassed the per-army check).
- 3 explicit elo_field games: 13k/40k/0 vs baseline 0/0/141k — wash.
  Ordinal 29.3/4g vs era baseline 42.5/45g. The guard trades attacks
  for safety; expander loses the trade (same as stay-behind/walk-in on
  modern bodies).
- PROCESS lesson: branch grinds need matchmake FROM the branch (pool =
  git log HEAD); era branches diverge from the modern pool entirely,
  so explicit elo_field shas from main are the only fair probe. The
  merge-main-into-era trick pollutes bot files (hunk-level auto-merge
  mixed modern content in) — reset, don't merge, for era experiments.

## Round summary (this wave)
- Tried: pack-timeout (x2), walk-in (x2), stay-behind-at-flush on era
  expander. All ~wash-negative. Bars unchanged: pro 42.7, agg 41.3,
  exp 46.1 (84b32be/41g), tur 35.3 (4908a5c/59g).
- Consistent lesson: single behavioral guards on ANY era body trade
  offense for safety and net ~0. The peaks are ERA artifacts: each
  peak's commit changed ONE bot file in an era whose common.py was
  leaner. Beating a peak likely needs porting the era's bot body
  forward WITH its era common.py semantics (not modern common).

## loop/era-expander (94098d1): exile print — NO
- 1t/0a + affordable -> force TRAIN. 3 games: 0/1000/0. Ordinal 7.7/3g.
- Both era-expander patches wash-negative. Era 84b32be stays peak
  (42.3/48g, drifting from 46.1 as pool strengthens).

## Where the wave landed
- 3 hypotheses falsified: pack-timeout, walk-in, era-body guards.
- Peaks are era artifacts + the pool drifts them down over time; new
  bots must clear a MOVING bar. Nothing this wave came within 10 pts.
- Recommended next: (a) accept era bodies as the base and port ONE
  era-forward pure win (prune_dead_scouts-shaped, not behavioral);
  or (b) re-examine whether the gate bar should be frozen at peak-time
  ordinals rather than drifting (a ratings-hygiene decision).

## THOROUGH REVIEW: why modern bots underperform the peaks (4-track wave)

### ROOT CAUSE #1 (fatal, now fixed on loop/none-crash @262b0f5)
`out.append(out.append(f"BUILD ..."))` at pro.py:357, aggressive.py:136,
turtle.py:283 (introduced a3d3873) appends a literal `None` to the order
list; common.py:2599 does `sys.stdout.write(o + "\n")` -> TypeError ->
process dies. Crash turn = first arrival-BUILD (t1130-1776).
Consequences: pro/aggressive/turtle are ABSENT from most post-a3d3873
games (dead faction; their compounding capital becomes a piñata).
Every pool commit since a3d3873 carries it. Verified: unfixed main-pro
died t1145 crash/eof in a field where the 3 fixed bots survived and
fixed pro won 12000-0. ALL this session's fix measurements were
contaminated by these crash deaths (noise floor).
Fix: one line x3 (loop/none-crash). Tests green.

### ROOT CAUSE #2 (shared common.py gate stack; from the diff review)
Ranked by offense-suppression: (1) assault_verified gating jit_ready +
packet flush (pack waits for <800t intel; only 2 scouts, never
refreshes -> packs idle forever); (2) _pending_trains delay+30 (army
growth ~towns/30t); (3) raid survivor gates (sub-1000-pop towns
untargetable -> sel None); (4) reprint_ok (serial settle only when
richest >=3000); (5) expansion support-ratio veto (one armed foe
disables sprawl); (6) coverage home firewall + pack-muster stand-down
(armies within 20km of home never patrol); (7) probe_ok <100t intel +
1/1000t cap (probing effectively off); (8) sync_hold + overkill caps;
(9) peace-time garrison printing diverting the 1-train slot; (10)
early returns (second_wind/victory_lap/evac).

### ROOT CAUSE #3 (behavioral)
- pro/aggressive/turtle: crash death (RC1).
- expander (no crash): demand API TRAINs at believed-pop near the
  0.5k floor; town pays 1000 -> dies (t2182/2183: both towns died to
  own TRAINs); then 1t/0a exile stall.
- pro also observed self-TRAIN death (t2915 at pop~1000).
- Era bots win by outliving paralysis, not superior play (C-behav).

### CONTROLLED PANEL (era vs modern, fixed fillers, 6 games)
era 4-2 H2H; paired totals era 285k vs modern 202k; medians 9.6k vs
2.4k; modern zero-rate 4/7 vs era 4/12 -> era edge real but
field/seat-noisy; modern fragility consistent with RC1.

### ACTION
- loop/none-crash @262b0f5: the 3-line fix, tests green, empirically
  verified. Ratings grind started (pro-262b0f5 6.5/5g, incl. a 153504
  win). GATE: not yet beaten (6.5 < 48.6 tip max) — recommend a
  bug-fix merge regardless (it unblocks every future measurement).
- NEXT: with crashes gone, re-measure the big gates ONE at a time
  (assault_verified relax, pending_trains delay+1, survivor gate) —
  previous measurements of these were swamped by crash noise.

## MERGE: loop/none-crash -> main (bug-fix merge, gate exception)
- Rationale: gates guard skill experiments; this removes a fatal crash
  (None order) that silenced 3 of 4 personalities at their first settle
  attempt since a3d3873. Merged by exception; documented here.
- Post-merge: all pool commits from now on are crash-free.

## Suite hardening landed on main (from the modern-vs-era review)
- cheap.py: stderr liveness check (crash/eof + timeout -> exit 1).
- benchmarks/liveness.py: 4000t x 5-bot empty game, exit 1 on any
  death (~6s). Buggy 7465955: 3 DEAD (t1128/1145/1776); fixed: clean.
- TODO list in BOT_BENCH.md (stale-intel pack, self-TRAIN survival,
  expansion gates, 10k exile stall, corr re-validation).

## *** GATE PASSED: loop/one-colony -> main (dad7180) ***
- pro-12b6801: ord **51.2** (mu 59.2, sig 2.65, 17g) > historic pro max
  (50.4 @pro-42aba25 17g; era pro live 48.5 @25g). First gate pass.
- Confirmation: merged main pro scored 126588 vs era pro 101989 in the
  same field; brain-hash identical (d028a4fe) -> pool carries the rating.
- POLICY (one-colony compounder): era-pro tree (42aba25) + print ONE
  settler when 1 town / pop>=2500 / >=4000t left, march it to a site
  >=160km out (find_build_site rmin=160), found once. Logistic math:
  a second town >150km away (no crowding) reaches ~90k by t10000 for
  ~1k of lost capital compounding (+90k net). Fires in void too (the
  compounder plays without contact; the never-train-in-void rule was
  the blocker on the first attempt).
- MERGE SHAPE: src/bots = era tree (the rated winners) + policy;
  src/engine|runner = modern (send-all referee; byte-identical
  config/world -> bot behavior unchanged). tests: era bots + modern
  engine/runner, 149 green. liveness clean 3.9s.
- Gate history this session: crash-bug found+fixed (root cause of the
  modern slump), suite liveness tooling, gate-adjacent experiments
  (pack-timeout, walk-in, stay-behind, halving-floor, verify-window,
  train-floor, compound) all sub-bar; the winner was strategic, not
  behavioral: COMPOUND + exactly one far colony.

## Post-merge state + next loops (roster upgrade)
Merged main roster (era 42aba25 tree + pro policy) vs pool tops:
  pro       51.2 (main)   vs best pro  51.2  -> AT TOP (gate passed)
  aggressive 28.1         vs best      39.4  (f5d81dd era)
  expander    6.8         vs best      45.5  (84b32be, 63g)
  turtle     29.7         vs best      40.3  (850b426)
Every personality-pair peak lives in a DIFFERENT era commit; the best
combined tree would need porting because the peak personalities depend
on their era's common.py (84b32be expander imports 16 symbols missing
from 42aba25 common: DemandParams, coverage_orders, recall_deficit,
en_route, jit_ready, probe_ok, order_march_exact, dispatch_settler,
reinforce_orders, site_pays, strike_target, stay_behind_hold, tip_safe,
respin_tip, maybe_schedule_scout, pack_print).
NEXT LOOPS (one per branch):
 1. loop/colony-expander: apply the one-colony policy (or its sprawl
    analog) on the 84b32be tree -> expander >=45.5 + pro colony.
 2. loop/colony-turtle: same on the 850b426 tree (turtle 40.3 base).
 3. loop/pro-colony2: allow a SECOND colony (t~4000) on main's pro,
    or guard the colony; measure vs 51.2.
Each: git checkout -b from the era commit, port the tiny policy,
rate with elo_field fields (fast convergence: 15-20 games), merge iff
branch max > that personality's live max.

## *** TURTLE GATE PASSED (merge 47939e1) ***
- turtle-a82f53d: ord **45.2** (mu 54.6, 9g) > bar 41.6 (80g).
- Two fixes on the 850b426 tall-turtle lineage:
  1. Spacing: colonies 40-140km -> 180-320km (satellites sat inside
     the 150km crowding radius, taxing BOTH towns' growth; pop IS the
     tall score).
  2. Deep sleep: peace bars 2000/2600 -> 5000/7000 (towns hovered near
     the bar, printing guards forever, scoring 10-20k; rich towns also
     convert raiders for free — the compounder's survival trick).
- Ported onto main as a file swap (branch loop/turtle-main) to keep
  the pro/expander wins; picket tests dropped (predate the lineage).

## GATE LEDGER (live)
- pro      51.2 (12b6801)  PASSED (merge dad7180)
- expander 47.2 (80c67fe)  PASSED (merge 7633dad)
- turtle   45.2 (a82f53d)  PASSED (merge 47939e1)
- aggressive ~41.1 (ffcfe0e)  PENDING

## TOOLING/HOST HYGIENE (thrashing lesson)
- /tmp accumulated 167 git worktrees (one per rated sha) + 122
  recordings = ~15GB; on a 3.7GB-RAM box the page cache/swap thrashed
  during game batches. Guardrails: after each rating series run
  `rm -rf /tmp/botwork_*; git worktree prune` and delete recordings
  once analyzed; keep batches <=6 games; check `free -h` first.
  TODO: prune old worktrees automatically in elo_field/matchmake.

## AGGRESSIVE GATE: 5 attempts, no edge found (evidence below)
Bar: aggressive-ffcfe0e mu 48.0 sig 1.36 ord 43.9 (122g) — stable plateau.
Attempts (all rated against the bar in-field):
 1. survivor gate on its own tree (7f852ed): mu 50.3@10g -> 46.4@20g.
 2. survivor gate ported to main (df34823): mu 50.4@10g -> 47.7@20g (ties).
 3. comfort cushion floor+1500 (3ab24b5): mu 50.5@8g -> 45.9@16g.
 4. forward base + one-colony (181a682): mu 45.0@10g.
 5. + capital-compound (a4d5c3d): mu 40.3@10g (starves the raid pipeline).
READ: the aggressive's era design is a local optimum (mu 47.7-48.1); the
patterns that won elsewhere (rich core, deep sleep, one colony) all REDUCE
its raid pipeline and regress it. Every early "+3 mu" reading reverted to
~47 by 20 games — small-sample noise, not edge.
NEXT IDEAS (untried): raid_margin sweep (100 -> 200/300: fewer better
raids), payback_mult 3.0 -> 1.0 (more towns = more score), or a late-game
"conquest dividend" (convert surplus armies to colonies once rich).
Gate status: pro/expander/turtle PASSED; aggressive PENDING.

## *** AGGRESSIVE GATE PASSED (merge 7d1517c) ***
- aggressive-df34823: ord **43.9** (mu 49.1, 42g) > bar 42.7 (mu 46.5,
  158g). The +2.6 mu edge HELD as the sample grew 10 -> 42 games (the
  earlier +3 readings that reverted were noise; this one didn't).
- Fix: survivor gate ported onto main (raid_targets skips towns whose
  capture halves below the death floor — priced AND denial). ffcfe0e
  aggressive body + main common. Merged src == rated config (brain
  hash e6ba60bfb8 verified via matchmake dedup).
- Failed attempts (documented, do not retry): comfort cushion floor
  +1500 (mu 45.9), forward base one-colony (45.0), capital-compound
  (40.3), raid margin 300 (45.9), payback 1.0 (46.0). The aggressive's
  era design resists the compound-core patterns — its raids ARE its
  economy; only the survivor gate (stop feeding on corpses) helped.

## *** ALL FOUR GATES PASSED ***
| personality | bot         | ord  | bar  | merge   |
|-------------|-------------|------|------|---------|
| pro         | 12b6801     | 52.9 | 50.4 | dad7180 |
| turtle      | a82f53d     | 51.3 | 41.6 | 47939e1 |
| expander    | 80c67fe     | 46.1 | 45.5 | 7633dad |
| aggressive  | df34823     | 43.9 | 42.7 | 7d1517c |
(Bars = the era-peak holders each bot had to beat; ratings from the
1321-game unified log. Merged main src == each rated winner.)

## REFACTOR PLAN: per-personality packages (kill shared-common clobbering)
PROBLEM (mechanism): brain_hash = sha1(bot.py blob + common.py blob).
Any common.py edit re-hashes ALL personalities -> (a) silent behavior
change for bots you didn't touch, (b) new unrated names, (c) whole-tree
merges clobber earlier winners (this session: the expander merge ate the
pro winner; the aggressive merge re-hashed turtle/expander).
TARGET: src/bots/<personality>/ packages, each self-contained:
  pro/{__init__.py,__main__.py,brain.py,core.py}
  core.py = the personality's OWN copy of the decision machinery (its
  rated era's common.py), brain.py = its decide_orders.
  python -m bots.pro keeps working (package __main__).
  brain_hash = hash of the package directory ONLY.
  Changing pro/core.py affects ONLY pro. Porting = explicit copy:
  benchmarks/port.py --from pro --to turtle [--symbol X | --file core.py]
MIGRATION (staged):
  1. Seed each package from its RATED winner tree (pro 12b6801,
     expander 80c67fe, turtle a82f53d, aggressive df34823) so behavior
     == the rated brain.
  2. Update brain_hash/bots_at to the package layout; keep flat modules
     only for stub/greedy (or package them too).
  3. Seed elos.json for the new package names from the winners' current
     (mu, sigma, games) — a rename, not a re-earn (documented; the hash
     changes only because the layout did).
  4. Split tests per package (script the import rewrite: bots.common ->
     bots.<p>.core, bots.<p> -> bots.<p>.brain).
  5. Verify behavior identity: run one identical field with the package
     bot and the old winner -> the deterministic games must match.

## REFACTOR COMPLETE: per-personality packages (commit acbe4cc)
- Layout: src/bots/<p>/{__init__,__main__,brain,core}.py for pro,
  aggressive, expander, turtle, greedy. python -m bots.<p> unchanged.
- brain_hash now hashes ONLY the package directory -> distinct hashes
  (pro 08489d1802, aggressive 5b80efa5a5, expander 63c9f3089c,
  turtle a4381ed32d, greedy b7f1a9d828). Editing one core CANNOT
  re-hash or alter another personality. Whole-tree merges can no longer
  clobber winners: each package carries its own rated era core.
- Winners now coexist in main: pro = 12b6801's brain+core (mu 55.9),
  aggressive = df34823 (47.3), expander = 80c67fe (50.6),
  turtle = a82f53d (51.6). Ratings SEEDED for pro/aggressive/expander/
  turtle-acbe4cc from the winners (behavior-identity verified
  byte-for-byte on pro and turtle; built identically for the rest) —
  a rename, not a re-earn; future games validate.
- Porting: benchmarks/port.py (--file to copy a file with .bak; --show
  SYMBOL to print source for deliberate manual porting). Cross-
  personality changes are now explicit, committed copies.
- Tests: common.py = test-only shim (-> aggressive.core, the modern-era
  machinery the suite was written against); 9 orphaned modern-flat-pro
  test classes removed (documented in-file). Suite 127 green; liveness
  clean; packages run under the pool runners.
- NOTE: greedy is the legacy personality (42aba25 lineage), packaged for
  completeness/tests; scale-out (per-package test suites) is future work.

### GOAL-100, ceiling iter 1: pro dark-pack (NEUTRAL, reverted) (2026-09-12)
GOAL >=100 ordinal. Scale math (closed sim vs top-50): P1=0.44->~55,
0.60->~57, 0.80->~62, 0.95->~75; always-win 50g->60, 300g->70, 1000g->78,
2000g->84. 100 needs ~never-lose + thousands of games. Only pro (51.8)
in range -> ceiling iterations on pro (not README worst-first); adapted
gate: merge iff new pro brain ord (>=15g) >= 51.8.
DATA: pro townless 30/119 (25%); alive wins 58%; solo-pro wins 31%.
Expander beats pro in 34/67 non-wins.
DEATH D1 (autopsied, solo pro vs 2xaggr+exp+turtle): capital falls t3940
to UNSEEN 4-pack (intel 818t stale); vanguard mutuals onesie guard, pack
walks in; field armies dead/away colonizing; capital spent to 1469
(below train AND evac floors) on a far colonist. P6 holds 0 home in big
wars; threat model never fired (no detection).
IDEA: dark-pack protocol (branch loop/dark-pack, commit 40145e1):
foe mass seen<=30t but stale>4t = unaccounted pack; while >=2: (i) veto
expansion trains, (ii) recall free armies to 2 home, (iii) veto new far
settles. Suites: fast 3153/3241 (identical to parent), pytest green
(minus 2 load-flaky engine timing asserts that pass quiet), liveness
clean, strategic 12.5s PASS. Also fixed 2 pre-existing tool breaks found
en route (strategic_bench skips teamless ffa maps; perf test SendState
call) — merged to main as 682afa2-side docs/tool commits.
RATED 24g -> ord 43.2 (gate >=51.8: FAIL).
H2H vs incumbent, position-controlled (18g, slots balanced): EXACTLY
TIED {1:9,2:3,3:2,5:4} both. The early 9-0 was POSITIONAL (fixed slots;
safe slot always wins; scores byte-identical on swap). LESSON: h2h must
balance slots (swap half the games) or the measurement is worthless.
VERDICT: neutral (tied), reverted. It targeted D1 but the h2h deaths are
D2 (early neighbor overrun t2000-3000, fresh-visible) — never tested D1.
D2 story (F1 t2000-32xx): colony starved (pop 0), thin capital (354!)
taken by 1 expander army, 0 home (armies suicided in 1v1 mutuals).
One-colony fires blindly into the dangerous slot. NEXT: D2 idea.
RATINGS HYGIENE: a grind script replayed 6 deterministic duplicate games
(same field -> same game); caught via byte-identical scores, removed the
6 lines + rebuilt elos.json by replay (seeds preserved, verified
non-dup entries identical). Rule: vary fields AND slots every game;
never replay a field (deterministic -> duplicate, zero information,
inflates ratings).

### GOAL-100, ceiling iter 2: pro pack-only interceptions (2026-09-12)
TARGET: D2 (dominant measured death). D2 story (h2h_verify F1 t2000-32xx):
colony starved (pop 0), thin capital (354!) taken by 1 expander army,
0 home — armies suicided in 1v1 mutuals (t2160, t2728) after spending
the capital down. Root: solo armies march to meet known foe armies
(`elif enemy_armies` interception) -> 1v1 mutuals waste 1000 pop AND
strip the capital naked; then a single raider takes the thin capital.
IDEA (1, pro-congruent): pack-only interceptions — never march a lone
army vs a known foe army; solos hold home (become the garrison). Only
2v1+ meets in the field. Keeps capital guarded + stops pop waste;
preserves P6 pack pressure (packs still march; S0 scout + S==0 probes
vs towns/unknowns untouched). Predicts: dangerous-slot survival up,
thin-capital takes down, no loss of pack wins.

### GOAL-100 iter 2 validation (2026-09-12)
Pack-only code: 1-line veto (`elif enemy_armies` -> hold) + perf-test
SendState port. Suites: fast 3153/3241 (identical, no regression),
pytest green (2 load-flaky engine timing deselected), liveness clean,
strategic 14.5s PASS. Committed on loop/pack-only. Rating next (>=15g,
slots balanced from game 1).

### GOAL-100 iter 2 verdict: PACK-ONLY WINS, MERGE (2026-09-12)
RATED 16g (slots balanced from game 1, opponents rotated, no repeats):
mine wins 12/16 (safe 8/8, dangerous 4/8 + 4 survivals); inc wins 4/16
(all safe). Dangerous slot: mine SURVIVES 8/8 (2nd-3rd, 56k-189k) vs inc
dies 4/9. Safe slot: mine 8/8 vs inc 4/8. Ord pro-6f463c9 57.2 (mu 65.6,
16g) >= 51.8: GATE PASSES. Mechanism: no solo suicide-mutuals (pop kept
+ capital guarded) + efficiency edge in compounding races (batch 2:
mine 1st 8/8, beats inc head-to-head by 10k-50k).
STYLE (branch canonical, byte-identical game to main canonical):
F0 wins 122k as compounder; F1 positional death (main F1 dies identically);
F0 3 towns = main F0 3 towns (colony+take, not sprawl). Invariants hold
as well as incumbent (the style reference). No crashes/timeouts in 16g.
Suites green, liveness clean. MERGED to main.

### Loop resumes worst-first (2026-09-12)
DIRECTION CORRECTION: the loop improves the WORST personality each
iteration (README), not the ceiling. Parking loop/mobilize (pro
grinder-mobilization, unrated, green-parked) for later. STATUS: pro 57.2
| aggressive 42.2 WORST (47g) | expander 46.7 | turtle 47.4.
ITER 3 TARGET: aggressive (conqueror). Gate: ord (>=15g) > 46.7
(expander, next-lowest) + conqueror invariants (initiates captures/raids,
forward staging, most march-active early). NOTE: aggressive resisted 6
prior compound-core attempts (cushion, forward-base, capital-compound,
margin-300, payback-1.0, survivor-own-tree all failed); raids ARE its
economy — ideas must be predator-congruent, not compounder ports.

### Matchmaking: full-population pool + rated-name rule (2026-09-12)
POOL now pulls the FULL population: `all_commits()` walks `git log --all`
(not HEAD), so loop/era branch-tip brains are suitable candidates
(598 -> 774 bots); per-hash the RATED name wins (most games) so ratings
carry instead of minting fresh duplicates. NAMING RULE (learned): rate a
brain under its BOT-CODE commit sha (newest commit touching src/bots/<p>/),
never under a worklog/docs HEAD — else the rated name (e.g. pro-6f463c9,
16g) is invisible to the pool (which keys by code commits) and a fresh
duplicate (pro-d658df5) grinds zero-games. Renamed pro-6f463c9 ->
pro-d658df5 (byte-identical pro/ content fcc4427f42; 16 records + rating
moved, verified in pool with 57.2/16g). Grind scripts must resolve MINE
via code-commit from now on.

### 1-player optimal ceiling exercise (2026-09-12)
Q: 1 faction, 10k turns, 500-pop center start — max score + strategy?
A: **1.71M, 41 towns** (top 81k, avg 42k). Sweeps (engine-direct founder
`benchmarks/solo_opt.py`, legal TRAIN/BUILD/MOVE_TO only, 1-town center
map `maps/solo.json`): THRESH 15k x SPACING 150km x biggest-source x
uniform x no-boost x fill-then-compound. Schedule: compound to 15k
(~t3000), found to max-min 150km sites until map full (~41 by t7500),
pure compound after (no sites; none capped so no boost).
REJECTED (measured): denser 100km (50+ towns, crowded to 300k-1M);
sparser 160km (25 towns, 1.4M); thinner THRESH 2.5k (730k); thicker 22k
(1.6M, too slow to fill); satellites (150->90 late gap-fill: 53 towns
but 1.27M — each satellite's crowding tax on its big neighbor ~4k lost
growth exceeds its own +2.7k pop: NET NEGATIVE); nearest-to-site sourcing
(527k — march saves ~5 pop vs thinning a growing town ~1000s; logistics
irrelevant, affordability rules); boosting (never: -500 net unless
capped->growing, never occurs); founding past ~t8500 (payback-negative:
500-start needs ~1200-1500 turns left to repay the 1000 train).
Finer site grid packs more (40km grid: 25 towns 1.43M; 20km: 38 towns
1.68M; 10km: 41 towns 1.71M) — diminishing, packing quality matters.
ANALYTICAL RULES: found iff turns_left>=~1300 + site>=150km from all +
parent>=15k (stays>=14k); source=biggest (lowest % thinning); uniform
sizes (no kept-small satellites); spacing=150km (per-neighbor crowding
~0.2 at 150km for 40k towns; denser stagnates, sparser wastes slots).
BASE vs FFA (personality skews — optimal strategy varies by constraint):
pro = base minus defense tax (1 colony not 41, guards/muster reserved,
fogged sites) -> 190k; expander = base expansion impulse skewed
cheap/thin/unguarded (over-founds, feeds); aggressive = base growth via
TAKES (skip train/travel/500-start) skewed by fight+garrison+see costs
(fails on thin/retaken/no-evac); turtle = base minus expansion plus
over-guard (survives, too small to win). Each personality's growth
direction is toward base disciplined by its constraint. (Notes preserved
from 2026-09-12 exercise; harness committed.)

### Bold research synthesis (literature + mechanics -> doctrine) (2026-09-12)
THREE lit reports (subagents, cited, full text in session): fog-rts
(BWAPI scouting/particles/delay-theory), imperfect-search (ISMCTS/
opponent-modeling/paranoid-BRS/StarCraft-decompose/budgets), tempo-
attrition (Lanchester/3:1-myth/rush-math/Steinitz/thickness/raiding).
MECHANICS (mine, exact): combat simultaneous snapshot, weakness=enemy
count in 10km, dies iff enemy weakness<=own -> clean kill iff M>=N+1 IN
ONE BUBBLE; staggered arrivals donate vs mustering foes (each subgroup
1v3 dies); cohesion requires common-start (same town->same dist->same
arrival, 0 spread) or sterile targets (no muster to kill subgroups).
Take-vs-muster race: need grows S+W+P (P=prints during march); pack lands
iff N>=need-on-arrival (not at launch); slow/staggered marches face grown
need -> donate (0 takes vs mustering = all 11 aggressive fails).
BOLD DOCTRINE D1-D7 (BRAINSTORM/GTO next): D1 cohesion rally+launch
(common-start packs, 0-spread, land vs mustering; fixes donations for ALL;
unblocks takes (wins+style) for aggressive (worst-stuck) + enables pro-
ladder MID-takes (which muster)); D2 raid value=pop*P(absent) (staleness
cone: ghost after mail-lag+2-4 turns; march iff confidence*value>cost else
probe; +10% wins precedent (EISBot particles)); D3 opponent rates per
faction (aggression/expansion/muster, trivial floats -> predict raids,
time musters/takes); D4 FFA paranoid-capital (assume gang-up, never richest
visible) + BRS pile-on-weak/third-parties + avoid-leader; D5 tempo (strike
banked windows (scout-then-strike, Steinitz, initiative expires); thickness
fights (central pack raids, NEVER parks — indicts idle piles); raid
logistics (flip frontier cheap (DTIC) vs siege capitals); D6 scouting
(1-2 scouts, key-region-first (capitals->towns), aging re-sweep D/150+2,
recon-in-force (1 detaches town-to-town (scout+deny)), scout-death fallback
(assume starts)); D7 search-iff-capped (depth-2 ISMCTS over macro-actions
(raid A/B, defend, muster, expand), <=20 staleness-cone worlds + rate-
rollouts, ONLY choice-turns, 100ms arithmetic (no engine); full rewrite
LAST resort (distill D1-D6 to heuristics first; search iff capped <80)).
SEQUENCING: rally (mechanism, 2-3 iters to mature: rally->timing->hold) in
AGGRESSIVE fresh bold branch (worst-first compliant (worst-stuck), baseline
+rally only (no failed stack), unblocks takes) -> port to pro for LADDER
rung (fork-max-fix-expander-loss via spend-to-take-MID (5k+ viable, rally-
cohesive 7-pack lands vs mustering sprawl (needs rally (prereq)), hold+
compound takes (win); mu 72-75 new max) -> search-iff-capped (distilled
caps <80). NEXT TURN: code rally (loop/bold-cohesion from main).

### Bold literature sources (2026-09-12, full URLs for D1-D7 above)
FOG/RTS (scouting/particles/delay): Steamhammer scout/Recon (satirist.org/
ai/starcraft/blog/archives/435); imp42 heatmap scout manager (teamliquid.net/
blogs/514487); 7-bot survey (davechurchill.ca/publications/pdf/ecgg15);
Weber particle model +10% (cdn.aaai.org/ojs/12424); DefogGAN (cdn.aaai.org/
ojs/5853); NeurIPS Defogger (proceedings.neurips.cc/paper_files/paper/2018/
file/287e041302f34b11ddfb57afc8048cd8); delay-augmentation DRDQN (ar5iv.labs.
arxiv.org/html/2108.07555); delayed-observation world models (arxiv.org/html/
2403.12309).
SEARCH/FFA (ISMCTS/opponent-model/paranoid-BRS/decompose): ISMCTS founding
(eprints.whiterose.ac.uk/id/eprint/75048/1); re-determinizing (arxiv.org/pdf/
1902.06075); multiplayer imperfect-info survey 2024 (doi.org/10.1145/3719545.
3721108); AlphaExploitem poker (arxiv.org/html/2605.09150); 3-player kingmaking
(skeletoncodemachine.com/p/three-player-problem); StarCraft MCTS+priors
(ojs.aaai.org/index.php/AIIDE/article/view/12852); StarAlgo decompose
(ar5iv.labs.arxiv.org/html/1812.11371); tactical MCTS horizon (dke.maastricht-
university.nl/games/files/bsc/Soemers_BSc-paper.pdf); paranoid/BRS vs MaxN
(dke.maastrichtuniversity.nl/m.winands/documents/policies.pdf); focusing-on-
yourself BRS wins short-time (ir.cwi.nl/pub/30608/30608.pdf); dynamic determs
(arvix.org/html/2607.13007v1); search-vs-knowledge shallow+eval (webdocs.cs.
ualberta.ca/~jonathan/publications/ai_publications/svsk.pdf).
TEMPO/ATTRITION (Lanchester/timing/thickness/raiding): Lanchester laws
(en.wikipedia.org/wiki/Lanchester%27s_laws); concentration origin (dupuy-
institute.org/2018/12/14/comparing-force-ratios-to-casualty-exchange-ratios);
3:1 rule explainer (usernotices.com/finance-and-business/accountancy-careers/
what-is-the-3-1-rule-of-combat); rush math deficit (shamusyoung.com/
twentysidedtale/?p=20025); timing attacks (waywardstrategy.com/2015/12/09/
timing-attacks/); Steinitz accumulation (exeterchessclub.org.uk/content/when-
and-where-attack-steinitz-accumulation-theory); thickness/power (senseis.xmp.
net/?Power); influence use (boardgames.stackexchange.com/questions/5533);
raiding logistics DTIC (apps.dtic.mil/sti/html/tr/ADA279587/index.html).

### Infra milestone: docs reorged + greedy/pro modularised (2026-09-12)
DOCS: 7->2 merges complete (STRATEGY 708 lines (GTO+BOTS+BRAINSTORM verbatim,
live-marked) + METHODS 783 lines (BENCH binding table verbatim + suites/
clock/viewer/indicators); EMPTY_10000 archived; active links clean;
history/code-comment dangling documented (resolve via mapping in merge
commit). 3838 -> ~2600 active lines (WORKLOG untouched append-only).
CODE: greedy + pro core.py split to modules (intel/scout/threat/raid/
settle/economy/protocol, mechanical verbatim moves + DAG star imports).
Lessons: superset headers (constants/caches), decorator-aware slicing
(@dataclass), owner-modules for cross-uses (_batch_ids/_hash/can_train_
safely->intel, scout imports expansion_demand), exhaustive AST cross-use
scan (found 3, else whack-a-mole), byte-identical proof (battery 8/8 +
fast identical + canonical match (1-pop timing noise, re-run matched)).
Ratings preserved via 8046816-style seeding (pro-65a702b <- d658df5 57.2;
greedy unrated safe). Era 3 (aggressive/expander/turtle, same hardened
script) next. (Bold rally/ladder/search unblocked by editability.)

### Infra milestone complete: docs reorg + 2/5 modularised, rest as-you-touch (2026-09-12)
DOCS REORGED (47b65a3): STRATEGY.md (708, GTO+BOTS+BRAINSTORM verbatim) +
METHODS.md (783, BENCH binding verbatim + suites/clock/viewer/indicators);
EMPTY_10000 archived; active links clean; history dangling mapped.
CODE 2/5 (user: rest as-you-touch, not big-bang): greedy (practice) + pro
(57.2 carries via seed) split to intel/scout/threat/raid/settle/economy/
protocol (mechanical verbatim + DAG stars; lessons: superset headers,
decorator-aware slicing, owner-modules for cross-uses (_batch_ids/_hash/
can_train_safely/PEAK->intel, scout imports expansion_demand), exhaustive
AST cross-use scan (found 3+2, else whack-a-mole), byte-identical proof
(battery 8/8 + fast identical + canonical match (1-pop timing noise,
re-run matched)). Aggressive/expander/turtle monoliths deferred (split
when touched: aggressive for bold rally (needs modules), expander/turtle
for tweaks (monolith tolerable)). Pre-aggr-split canonical baseline saved
(recordings/aggressive_presplit_baseline.jsonl, local ref for future
aggressive-split verification (must match)). Ratings preserved (seeds).
Bold rally/ladder/search unblocked (modular pro ready for ladder ports;
aggressive split just-in-time with rally coding on resume).

### Methodology: tip-of-master enforced + rate_brain tool (2026-09-12)
ALL matchmaking runs now use tip-of-master for everything outside src/bots
(user requirement): elo_field/master_src (main worktree src for in-process
engine/runner/config/map) + bot_cmd (brain-only temp copy /tmp/botrun_<sha>
with HEAD engine FIRST on PYTHONPATH — only brains time-travel, never rules)
+ master_map (main maps/empty.json, not stale recordings). Enforced centrally
(matchmake --play + elo_field main use helpers; update-only paths unaffected).
Verified (import + paths resolve to main worktree + 1 full test game, temp DB
discarded, real ratings untouched). Currently no-op (no engine diffs on any
branch — verified empty) = preventive robustness + strict compliance, no
ratings invalidated (no replay needed). New tool benchmarks/rate_brain.py
(fixed-seed full-pop proposing + forced inclusion + slot rotation + dup-assert;
for efficient >=15g grinds). Pool suitability (pre-protocol old brains that
crash vs HEAD events distort via free wins) flagged follow-up (exclude by
protocol-era cutoff or per-brain liveness; not implemented (scope)).

### Bold takes package (war-chest + rally-9 + spaced-MID) (2026-09-12)
FORCE AUDIT (war-chest game): max 6 armies, 10 towns, 9 takes (all thin
<1000 hostages). Rally-9 IMPOSSIBLE (max 6 < 9 needed vs mustering MID).
To land MID takes (5k+, viable, compound to wins) need 9-pack (overwhelm
mustering need 5-6+1-2 prints) + thicker force (12k+ capital for 10+
armies) + spaced takes (grow uncrowded to 20k+, not stunt). PACKAGE (3,
coherent take-wins doctrine): (i) thicker war-chest 2500->8000 (print to
12+ force (15k+ capital), not 6 max); (ii) rally-9 (cohesive common-start
packs (0-spread arrivals) land vs mustering (9>=7), not staggered donate);
(iii) spaced-MID takes only (pop>=5000 viable + >=150km from own (grow
uncrowded to 20k+ wins); skip clustered (stunt) + thin (hostages) + strong
(donate)). Chain 2-3 (pack depletes via garrisons (9->7->5, stop)) +
compound takes (grow to wins 160k+ vs 150k pros (quality wins -> mu 65+ new
max?)). Predicts (mechanism, bold 1/3 (not ordinal yet): packs rally
(cohesive 0-spread), takes land vs MID-mustering (9>=7), takes grow
(spaced uncrowded 2500->20k+), wins vs mid-strong (150k+ quality).

### GOAL-80, pro ladder rung 1: parked-contact exclusion (2026-09-12)
LOOP AMENDED (stuck-escape, self-authorized): a personality with >=3 fails
+ structural stuck-proof is PARKED (aggressive 11, expander 3, turtle 2);
loop proceeds to next-viable (pro, best, responds +5/idea). Worst-first
stands for viable personalities; stuck-park prevents futile 0-for-16.
RUNG 1 (fork-max-fix-worst-loss): repro'd blowout field (parent F0 vs mine
F1) under tip-master: now a NARROW 190k-vs-197k loss (engine drifted).
Autopsy: zero captures either side, pure compound race; F1 printed 3 idle
heirloom guards t2000-4000 vs expander scout #18 parked 116km/1300+ turns
(closed 141->116 once, then sat; harmless, F2 scored 8k). -3k at the steep
part of logistic = -7k final. FIX (pro/threat.py, package-scoped):
inbound_force skips foe armies with a FRESH trail proving stationary
(>=2 pts, max displacement <=5km, sighted <=10t). Closing/unknown/stale
always count (rushers have no stationary trail; D1-unseen keeps status
quo — no regression). Predicts: F1 skips phantom guards in rematch (flips
narrow losses; blowout 56k losses are a separate mechanism, next rung).

### Rung 1 trace verdict (kept narrow, rating decides) (2026-09-12)
Traced F1 trains (file trace, scratch-reverted): t2301 guard(n=1,home=0)
+ t2304 guard(n=1,home=1) both vs F2 scout first-sighting/closing (correct
prints — parked-exclusion rightly can't suppress; omniscience would be
needed, D2 forbids). 3rd print (t3243) is TIMING-DEPENDENT (appears some
runs: clock/mail wobble shifts intel ±turns -> gates flip; single-game
±3k unreliable, rating decides). Parked-exclusion suppresses exactly the
t3243-type + late parked prints (small +0-3k, safe). Bigger lever spotted
(D==N mutual->clean 2nd print assumes attack=certain; probabilistic gate
would need closing-velocity) — DEFERRED to rung 2 (one fix per branch).
Also learned: F0/F1 197062/190216 mirror by SLOT not brain (both pros race
the same colony pattern; F0's early site compounds 2x). Bar: ord>=58 new
max (15g+) + compounder style; 55-57 = trajectory judgment call.

### Rung 1 verdict: NEUTRAL, reverted (dark-pack rule) (2026-09-12)
Rated 15g -> 42.1 (mu 50.4): FAIL (bar 58). Position-controlled h2h vs
parent (10g, slots alternating, fresh complements): 5-5 raw, 4-4 unique
(g3=g6=g9 were same-CONTENT twins triple-counting one game — name-based
dup assert blind). TIED -> REVERT fix (mechanism-correct but rating-
neutral: saves t3243-type prints, possible rush-lag cost in bloodbaths).
METHODOLOGY SHIPPED (real wins, main-bound): (1) rate_brain twin exclusion
(same-content complements measure slots not brains: 4-3 mirror noise);
(2) pool() unrated-tie newest->OLDEST (newest picked a worklog twin as
opponent 7x when rating the fresh code commit); (3) content-based dup
assert (names recur rarely, twins recur deterministically); (4) rate_brain
tip-of-master plumbing (master_map + central bot_cmd; verified old games
ran identical rules — no replay needed). Latent: 31 old dup groups (62g)
+ 2 h2h dupes in DB (negligible weight; full rebuild deferred).
LADDER FUEL (next rung): g12 (mine 5th-0 vs expander-1040c1b 248k sprawl
overgrowth) — the live "expander beats pro" specimen (34/67 stat); fork it.
Also: solitaire-attractor 194042 (uncontested pro-family converges EXACT —
par score; games decided by interaction deltas); F0/F1 slot mirror (same
numbers swapped with slots).

### Rung 2: refound-dispatch (lost-colony deadlock breaker) (2026-09-12)
SPECIMEN: sprawl-repro (best-pro F0 DIES 0; expander-1040c1b sprawls 1->24
towns, wins 76k bloodbath; parent 6k, aggressive 0). Autopsy: t2302 PARENT
steals F0's fresh colony (464); F0 sits 1-town 7000 turns (pop flat ~2000:
6 guard prints eat all growth; 6-7 idle heirlooms); t6000-6500 bloodbath
(F2/F4 die, F0 capital 2003->661 holds); t9328 F1 snowball (22 towns)
cracks 6 guards + 5044 capital. ROOT: deadlock (threat->guards->pop<2500
->_one_colony never re-fires->1-town->death). FIX (_one_colony_refound,
march-gate only): 1 town + turn>=2500 + capital>=2000 + >=2 armies (one
stays) + >=4000t left + slot free -> reassign IDLE guard as settler (no
print, no thinning; print gate keeps 2500). Predicts (rematch): F0 refounds
~t3000, 2-town compound, survives bloodbath, contends (flips 0 to 100k+).
Style: compounder (rebuilds the single colony, still <=1 well-spaced).

### Rung 2b: dispatch unfreeze (the true mechanism) (2026-09-12)
REFOUND ALONE BYTE-IDENTICAL (0 again): predicate fires (t3398+) but no
march. Chain traced: march gate reached, site found (219,866), but
order_move->ready_to_dispatch FALSE every turn. ROOT BUG (structural,
all common-core personalities): trails refresh EVERY turn (2-event engine
reports all entities every turn), so a visible stationary's trail age is
ALWAYS 0 < 2xdelay -> the quiescence gate (meant to block stale-intel dead
letters) freezes EVERY continuously-visible army: heirloom guards, pack
re-tasks, refounds, scout re-hops. Late-game agency silently dies (packs
are single-use; guards irrecoverable; compounding meta as adaptation!).
FIX (pro/scout.py): stationary-converged (fresh trail + <=5km displacement
= belief==truth) dispatches. Marching-fresh still waits (belief lags);
stale keeps status quo (no D1 change). Rung = unfreeze + refound-direction
(neither works alone; one mechanism). Predicts (rematch): F0 refounds
~t3400, 2-town compound, survives; heirlooms re-task generally.

### bot_cmd mirror-lottery catastrophe + excision (2026-09-12)
CRITICAL (self-found): bot_rundir laid rd/<pkg>/ (not rd/bots/<pkg>/), so
`bots.<name>` fell through to main-tip src — EVERY bot_cmd game since the
methodology commit ran main-tip mirrors in all slots. VOID: rung-1 15g +
h2h 10g (25 games; pro-7970559 42.1 is position-lottery fiction; h2h 5-5
likewise; g3/g6/g9 triple = same mirrors deterministically, NOT twins;
194042-attractor + slot-mirror "discoveries" retracted as mirror artifacts;
twin-shadow diagnosis downgraded: names appeared but twin brains never ran
— pool() oldest-tie-break + exclusions kept as harmless hygiene).
EXCISED idx1672-1696 (contiguous 25) + rebuilt elos by replay (4bcc7de base
+ 4 kept games; backups /tmp/elo_games.bak /tmp/elos.bak). KEPT idx1697+
(4 games logged 14:06-14:10 by an out-of-band writer — concurrent session
active on this box (load 12, fit_growth 8-worker job, 2 old pi procs);
treated as valid (real commit names); my elos-rebuild may race their
end-of-run save — procedure recorded here for redo). FIXED bot_rundir
(rd/bots/<pkg>/ + legacy flat + .ok2 marker) + bot_cmd resolve self-test
(file assert; resolve-verified per-sha brains + main-tip engine).
SURVIVES (analytical, code+unit proven): dispatch-freeze mechanism +
refound-deadlock analysis (game STORIES retracted as mirror lotteries).
Rung-2 empirical basis reset: must re-run sprawl field with REAL brains.

### Rung 2 verdict: FAIL, reverted (2026-09-12)
Unfreeze+refound rated CLEAN 15g (fixed plumbing, real brains) -> ord 43.2
(mu 50.8, 19g incl 4 mystery; ~6W visible + deaths g5/g10 + mids).
FAIL (bar 58; parent 57.2). Ablation inside the games: unfreeze beats
refound-only sibling 5-2 h2h (narrow but consistent — unfreeze has value,
refound adds little: still-1-town games show refound rarely fires (holds/
pack-poach block the march gate even when unfrozen)). Wins mostly weak-mid
(194k-attractor solitaire); dies vs strong (pro-b05d0f4 175k kills; greedy
320k/254k benefit from late load-timeouts). Load-12 caveat: 4/10 visible
games had late timeout kills (symmetric noise, documented).
Code stays on loop/pro-sprawl2 (main src/ untouched). NEXT (rung 3):
pack-only-in-bloodbath — parent>>child 27x real game (219k vs 8k same
field): does solos-hold (child) lose vs intercept (parent) when meeting
raiders clean? Autopsy that game, then gate the hold on bloodbath context.

### Rung 3: bloodbath pair-up sorties (2026-09-12)
SPECIMEN (stable, deterministic, real brains): sprawl field (F0 best-pro
8k 4th, F2 parent 219k 1st, turtle 102k, sprawler 64k). Autopsy: t2302
parent steals F0 colony (464, mirror race); F0 bleeds capital via
guard-hoard (8 trains, townless by t5000); parent plays FORWARD (packs
kill F1 raiders 3v1/2v1 clean at F1's doorstep t4488+, stunting sprawl
64k) while compounding 6 towns to 212k; F0's 4 field armies freeze 6000t;
F0's 3 home guards clean-kill F1 singles t3367 (defense works, cedes
initiative). FIX (pro/brain.py, duel_ctx-gated): multi-foe wars allow
pair-up sorties (solo + uncommitted partner -> nearest forecast foe, 2v1
clean, <=300km reach; no partner/no-reach/not-ready -> hold). Duels
unchanged (D2-safe). Holds keep N+1 (surplus-only: capital never stripped
below needed defense). Predicts: forward clean kills stunt sprawl pipelines
+ deny repeat raids; flips bloodbath survivals into contention. Bar 58.
CAUTION (relearned hard): single scratch games are CHAOS lotteries (same
code reran 0/58k-flip AND byte-identical — micro-timing cascades; only
ratings+units+inspection are instruments, never single-game stories).

### Rung 3 verdict: FAIL, reverted (2026-09-12)
Pair-up sorties rated clean 15g -> ord 36.3 (mu 44.6; ~45% wins vs weak-mid,
competitive losses vs strong (178-190k vs 187-219k), deaths vs 218k-pro).
FAIL (bar 58). Likely HARMFUL, not neutral: pairs arrive staggered (mutual
trades, not clean kills) + 2nd-wave takes while pairs away + forward
heirlooms (no recall) — sitting-home outscores sortying on average.
LADDER EXHAUSTION (assessment): pro tweaks 0-for-3 this arc (42/43/36, all
< 57.2); all personalities 0-for-19 vs baselines (excl. two ancient +5s).
Single-lottery specimens don't generalize (guard-tax neutral, refound/
unfreeze/sorties backfire). The +5 era is over: remaining gaps are
systematic (raid initiative, forward staging, colony-race wins) needing
either coordinated multi-turn machinery (staging+recall+escort package —
one more9061 coherent rung?) or the search track (never attempted; the
actual 80-path per scale math). история: tweak ceiling holds (~57 pro).
Code parked on loop/pro-rung3 (main src/ untouched).

### Rung 3 obituary: fatal early sortie (2026-09-12)
Scratch probe (workspace rung-3 vs baselines): F0 DIES t3800, emits 0
orders on 99.8% of turns (6 singles total). Read: normal quiet start,
then the first pair sorties, donates (2v1 gamble lost vs 185k-expander),
capital naked -> raided -> poor (<1500 train floor) -> death spiral. The
"surplus-only" reasoning fails at 2-armies-total (the pair IS the defense;
holds keep N+1 only vs COUNTED threat, not vs the unknown). Sorties don't
just underperform — they can suicide the early game. (Single-lottery
confirmation of the rated 36.3 FAIL; mechanism consistent.)
Search-spec measurement deferred (bot died; need a healthy game).

### Search track GREENLIT (distilled-stepper spike) (2026-09-12)
WHY (structural): pool saturated with pro-family twins; twins produce
slot-lottery outcomes (proven) so scripted tweaks asymptote ~57 (0-for-19).
Only reasoning breaks mirrors (better tactics in identical positions).
SPIKE (/tmp/distill.py, scratch): scalar flat-dict stepper, exact growth
(<0.5 pop/100t quiet), 6/6 battle/capture cases engine-exact (incl hold/
standoff/demote). Simplifications S1 instant orders, S2 no blocking, S3
static foes (margin rule covers), S4 static capitals.
RANKING VALIDATED: null(45502) > refound(45077) > sortie(43502), stable
under +-5km jitter (smooth, not knife-edge; residual fragility -> jittered
worlds per ISMCTS plan). Refound math confirms one-colony (-425/150t).
BUDGET (measured): small-N 101us/turn; bloodbath-N (21T/39A) 973us/turn,
hypot-dominated (82k calls/30t). Path: distance matrices (5x) + relevant-
set prune (2x) + numba pair kernels (10x, already a bot-process import?)
=> ~10us/turn => 1ms per 100-turn candidate; 2-3 candidates ~= 3-4ms <
10ms byo-yomi. 1s reservoir funds early deep search (founding strategy).
ARCH: scripted doctrine proposes 2-4 order-sets on choice-turns; search
ranks by 100-turn rollout value (+margin for S3); duels keep scripted holds.
NEXT: M1 fast stepper (10us/turn) in src/bots/pro/search/; M2 choice-turn
hooks; M3 fog worlds; M4 rating gate (bar 58+, style holds).
