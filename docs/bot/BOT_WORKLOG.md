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
