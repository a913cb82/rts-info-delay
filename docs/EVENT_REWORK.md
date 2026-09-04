# Event rework — state updates with line-of-sight fog

## Design (agreed direction, sharpened)

**Wire.** Two update kinds, generated from world state in the knowledge phase:

- `town_update {id, x, y, faction, population, is_capital}` — `population 0` means dead.
- `army_update {id, x, y, faction, alive, is_viceroy, has_target, target_x, target_y}` — `alive False` means dead. (Target fields added: free — it's state — and they preserve forecasting. Proposing to include.)

**Core metaphor: eyes are instant, mail is slow.** Observation (line-of-sight) uses current positions; reporting (delay) uses distance to capital. A scout sees the enemy NOW; the news still travels at `info_speed`.

**Ledger (kept, reshaped).** The shared ledger stays, windowed as today (`diag/info_speed` turns). Every entry is a state update tagged with `visible_to`: the set of factions observing that entity that turn. Generation is unconditional but observation-gated: every observed entity gets an entry every turn; unobserved entities cost nothing (no entry — safe, because values are always live: the first tagged entry carries current truth, so no announcement can be missed and no first-sighting rule is needed). On-change generation is demoted to a future optimisation — explicitly NOT now, per the invisible-army risk. Deaths: knowledge sees an id vanish (global live-registry diff) and appends one death entry tagged with observers of the site (tombstone pos), then drops the id. Entries carry generation turn + position (delay basis).

**Visibility.** Faction F observes entity E at turn t iff `dist(E.pos@t, any F entity pos@t) ≤ line_of_sight` (`line_of_sight` defaults to `info_speed`, 150 km — D4 proposes a single knob, separable later). Own entities are always observed (self, dist 0). No generation-side blindness rule: mute is the I/O skip alone — any tags accrued mid-flight die in the S-filter unobserved, so the viceroy may anchor LOS like any army without effect.

**Delivery — three gates + latest-only.** Faction F receives a ledger entry iff ALL three hold: (1) TAG — F is in the entry's `visible_to` (someone of F's saw it that turn); (2) DELAY — `t + dist(entry pos, F's current capital)/info_speed ≤ now` (the mail has had time to travel; exact comparison, not floor — `160//150 = 1` would deliver at S+1 news needing 1.07 turns); (3) S — entry generation turn ≥ S (S = F's last landing turn, 0 if never landed — runner-side int per faction). At most ONE update per entity per payload: among passing entries take the newest generation turn that differs from last-delivered (older eligible entries are superseded — stale mail behind fresher mail is waste, and the bot needs current truth, not the path). Integer turns quantize up: effective latency is `ceil(dist/info)` (160 km → generated S, released S+1.07, first present in the S+2 payload — pinned case). No exceptions — deaths pass all three gates like everything else (site tags, delay, S). Ghosts are impossible for a different reason: the bot forgets everything at landing (below), so there is no memory for a corpse to haunt. A death during flight simply never arrives; the wiped bot never knew the entity in this epoch.

**Send-state (still required) + reset at S.** No-resends forces per-faction last-delivered snapshots: a passing entry is delivered only if its snapshot differs from what F last got (this is also what keeps the wire slim). At every landing, F's send-state resets to empty — the mandatory counterpart of bot amnesia: without it, an entity unchanged since before the flight would compare equal and stay silent to a bot that forgot it (stagnant-town hole). With reset, everything observed post-S re-announces exactly once, paced naturally by delay releases (no batch dump). Tombstones are generation-side only (last-known pos for a death entry's tag/delay basis; ids never reused); prune past window.

**Landing.** Engine side: set S, reset F's send-state — nothing else (no reseeds, no replays, no backlog dumps; the S-filter is back wearing a new name — what was awful before was the reseed-and-wipe circus around its holes, and bot amnesia plus re-announcement closes those holes now). Bot side: FORGET EVERYTHING on landing (below) and rebuild from scratch. The turn jump is only ever read gated on the remembered order (success confirmation, never a trigger by itself). A transient (S-filtered) is NEVER known.

**Bots never receive the map.** The runner strips `map` from the startup config JSON (rules + `map_size` stay — board dimensions aren't intel). Bot init starts with an empty world; the first payload is the first observation (own capital immediate at dist 0, LOS neighborhood delayed). Pre-seeded geography is gone, so unseen-phantom gating (`last_seen`) is load-bearing, not optional.

**Battles.** Dropped as events (proposed; see D2). Deaths carry outcomes via `alive False`; trade inference moves bot-side (same-turn paired deaths near each other). Own-death-driven machinery (wave-watch, quiet-breaking) keys off updates instead.

## Deletions (the point of the exercise)

- `capital_since` as a *hiding* filter with reseed compensation (replaced by S-as-explicit-rule with re-observation closing the holes — same comparison, honest architecture around it).
- `landing_spawns`, `landed_this_turn`, landing branch, redelivery guard.
- Old bot wipe trigger (unknown-capital spawn) — replaced by order-flag amnesia (below); spawn-guard special cases collapse into upsert.
- `visible_events` audibility filter → tag+delay+S delivery (rewrite; vectorized release check retained).
- Bot `town_capture` / `battle` branches; engine `apply_events` stays for record/mirror use.
- Ledger leaves the game loop (step still returns event dicts for the record file; `Ledger` class deleted after audit — see Phase 0). Ledger eviction goes with it (nothing accumulates bot-visible history anymore).
- `town_history` + `delayed_town` deleted (no horizon lookups; side win: ~170 MB/game freed).
- `_last_sent_pop/_last_sent_status` + the pop loop + B16 pop-carried status (takeovers arrive as ordinary `town_update` faction changes; the since-hole B16 patched no longer exists). B15 seq machinery STAYS (delivery still needs sent-once tracking per faction — now joined by snapshot compare).

## Conventions (every phase)

- Full suite green before moving on. No new randomness anywhere (canonical payload order is part of this).
- Benches paired, same box; absolutes never compared across machine states.
- Equivalence for a semantics change = spec tests + hand-checked scenario diffs (byte-identical JSON only applies to pure refactors).

## Phases

**Phase 0 — audits (no behavior change).**
- Grep every `Ledger`/`visible_events`/`capital_since`/`town_history`/`delayed_town`/`_last_sent_pop`/`_last_sent_status` user (engine tests, medium tests, determinism tests, benches, bots). Decide per user: deleted, migrated, or kept (only the record path keeps its event dicts). (`event.seq`/`_sent_seqs` stay — delivery needs sent-once keys.)
- Snapshot bench baselines (fast + strategic) — fog will move numbers a lot; record pre-fog table.
- Snapshot **builder** baseline on the heavy rig (207t+3036a) and a real turn-20 `full.json` capture: ms/turn + payload bytes. This is the number the rework must beat, paired same-box.
- Confirm record/viewer need zero changes (step event dicts feed record as today).

**Phase 1 — ledger tagging + S plumbing (no histories).**
- Generation: EVERY observed entity gets an entry EVERY turn (unconditional — static entities included; the delivery diff-check, not generation, keeps the wire slim); unobserved entities get none (skip, not empty-tag — first tagged entry carries live truth). Tests: entry-every-turn-when-observed, nothing-when-unobserved, tag correctness (mixed observers, own-always), generation turn + position recorded.
- S plumbing: runner-side `S[faction]` (0 default, set at landing), delivery filters generation turn ≥ S. Tests: pre-S tagged entry never delivers post-S (the 160 km transient, pinned); S updates exactly at landing; never-landed faction unaffected (S = 0).
- Tombstones (generation-side): removed id → one death entry tagged with observers of the site (last-known pos basis); prune past window with everything else. Tests: death entry shape/recipients; ids never reused (pin the rule, so tombstones can't collide).
- Memory spot-check: windowed ledger + send-state ≈ small; nothing grows with game length.

**Phase 2 — builder.** Pure fn `(ledger, faction, send-state, S, capital-now, now) → updates`, canonical order = ledger order (turn-sorted already; deterministic — tag sets must never leak order into output).
- Shapes/fields incl. target passthrough; death encodings; send-once (second call silent).
- LOS: outside all discs → silent; inside → update; boundary `≤` pinned; anchors: town-only, army-only, mixed; own entities always.
- Delay: generated t, released when `t + dist/current-capital ≤ now` (basis re-evaluated per check — capital moves shift pending; pin with shifted-release test. Pinned case: generated S-phase-6 at 160 km → first present in the S+2 payload — integer quantization, `ceil(dist/info)`).
- Per-faction independence (F1 sees, F2 doesn't, same turn).
- Capital moves → delay basis shifts for pending entries (re-evaluated per check from current capital; pin with shifted-release test).
- Mute: I/O skip only (no generation-side rule — flight tags die in the S-filter); post-S payloads contain S-observations only (no backfill — the transient-loss test below is the proof).
- Tombstone deaths deliver like any entry (site tags, delay, S); never-observed removal → silent.
- Uniqueness invariant: at most one update per entity per payload (newest passing entry wins — assert it, with a 3-eligible-entries-1-delivered test).
- Time-shifted observation: F1 observes E at t, F2 at t+5 — independent snapshots, neither disturbs the other.
- No-capital faction: define builder behavior (today's (0,0) fallback or explicit nothing) and pin it — elimination usually moots this, robustness shouldn't rely on that.
- Empty world → `[]`. Delay exactly-at-now honors the 1e-9 convention (pin). Determinism: same inputs twice → byte-identical payloads.
- No-reseed proof: post-S payload for a landed faction contains nothing with generation turn < S (property test over a scripted flight — the S-filter holding).
- Counter-intel preserved: foe in path observes the marching viceroy (`is_viceroy` en route); observers of a founding get `is_capital True` on the birth update.
- First-turn payload: measured on **real turn-1 `full.json` geometry**, not the heavy rig (own capital + LOS neighborhood — fog-visible subset). Enormous is acceptable: the 1 s initial bank (`main_time_ms`) covers it. Bench asserts builder + serialize + a reference parse fit comfortably inside it; no chunking.
- **Spike first**: LOS shapes (numpy broadcast / numba pairs / hash queries) AND delivery shapes (flat window scan vs per-faction indexed deques) against the heavy fixture, pick by paired numbers, delete the losers. No guessing (house rule). Per-faction index is the expected winner over naive scan (34k entries × 5 factions flat is the cost to beat) — expectation, not decision.
- **Perf budget test**: `bench_builder_full` (heavy fixture + real turn-20 capture) must beat current `_build_bot_events` paired same-box — mean/p99 ms/turn and payload bytes; fail loudly otherwise. See Performance.

**Phase 3 — wire-up.**
- `run_game` loop: replace `_build_bot_events` with tag-aware deliver; mute kept; reseed branches deleted; S set + send-state reset at landing (detect via own-capital founding in step events); `since` gone (S takes its place). Ledger stays in the loop as the generation log.
- E2E flight test: evac → mute (empty payloads) → land → S-rule only. Birth/capture/death during flight arrive as S-observations (S-state, S+delay — never backfilled with pre-S turns); pre-flight-sent never resent; post-S payloads apply onto the order-flag-wiped world (bot side, Phase 4); uniform-rule property: every update first delivered after S was generated at t ≥ S with LOS-at-t — assert, don't eyeball.
- Transient-loss test (the 160km case): entity visible at S−1 but moved on by S never appears in any post-S payload — pinned, not just implied.
- Stationary-appearance test (the 100-turn case): new capital at S; armies at several distances, unmoved for 100 turns, still appear at exactly S+ceil(dist/info_speed) — proves every-turn generation (no invisible armies).
- Death-during-flight test: known army dies mid-flight → its death NEVER delivers post-S (S-filtered); bot-side wipe drops the ghost (integration: fly, kill, land → X absent from rebuilt world, no exception, no special case).
- Config strip: startup JSON to bots contains no `map` (runner test with real config). Fog purity: an entity never in LOS the whole game never appears in any payload (multi-turn property test).
- Full suite green; scenario benches run (numbers WILL move — record, don't chase).
- Record tripwire: scripted deterministic game → record bytes identical pre/post rework (engine untouched; trips on accidental engine changes).
- Full-game wall-time old-vs-new on a mid scenario (bot I/O dominates; assert no blowup from builder/serialization).

**Phase 4 — bots.**
- Parser: upsert updates by id (creates on unknown — the announcement path), remove on `pop 0` / `alive False`, apply faction/flag/target absolutely. Tolerant: unknown kinds ignored.
- Delete old wipe trigger + battle/capture branches + dead tracker paths they fed (wipe itself returns below, behind the order flag).
- Amnesia on landing (bot's responsibility): trigger is its OWN `MOVE_CAPITAL` order, not stream shape. At issue, set an `evac_ordered` flag. On the next payload: stream jumped → the flight happened → wipe EVERYTHING (world mirror plus all trackers: pending trains/builds, targets, wave-watch, growth, fingerprints, plans, `last_seen`) and apply onto empty; stream sequential → the order FAILED (continuity is the failure signal — dead letters get no ack) → clear the flag, no wipe, apply normally. The flag is consumed by the wipe it triggers (clear explicitly only on the failure path). Config+faction survive either way. Lifecycle constraint: one process per faction per game, started once at game start — never restarted, including across flights (the muted process blocks on readline and resumes; amnesia is an in-process wipe, never a respawn). Tests: order→silence→payload wipes ghosts/trackers; order→sequential-payload does NOT wipe (failure path); flag cleared both ways; orders across separate epochs each resolve independently. Pin: success always jumps by ≥ 2 — the viceroy spawns in economy, after movement, so it cannot arrive before step T+1's movement and the T+1 payload is always muted (t = 1 unambiguously means failure, however nearby the target; nearby-target flight test).
- Add `last_seen[tid/aid]` (delivery turn) — enables BOT_PLAN risk posture (staleness-aware thresholds). Pin recording + never-observed stays absent.
- Init: delete `parse_map` pre-seed (empty world start). First payload creates the own capital — pin it. Decide must tolerate an empty world regardless (elimination edge).
- Seen-only world (automatic — memory holds only delivered updates) plus `last_seen` staleness for risk posture: targeting/scoring sums over known entities; thresholds scale with staleness (BOT_PLAN). Pin: distant foe simply absent from leader sums until observed; stale-entry caution, not exclusion.
- `is_quiet`: any update breaks sleep. Fingerprint: extend over full known state (membership + pops + positions); pin invalidation on position change alone.
- Migrated machinery keeps its tests, updated: pending-train confirm via own `town_update` pop drop; wave-watch via own `alive False`; forecast inputs (existing forecast tests moved over); staged decide/clocks untouched.
- Bot unit tests: apply matrix (create/update/remove/unknown-kind/unknown-faction), no wipe without a preceding order, wipe clears every tracker (enumerated assertion), death-clears-trackers, quiet rules.

**Phase 5 — docs + baseline.**
- TESTS.md B-section protocol rewrite (shapes, LOS, delay, death encodings, ordering, mute/stream-resume, amnesia rule).
- PLAN.md intel model rewrite (eyes/mail metaphor; deletion list).
- BOT_PLAN.md note: scouting doctrine becomes prerequisite for trade evaluator (reorder cue); leader-targeting sums KNOWN foes.
- Re-baseline fast + strategic suites as the fog-era table; regen `empty_3000` rematch; viewer smoke (record unchanged — verify load, not behavior); worklog entry.

## Performance (top-tier or it doesn't land)

Scale is not scenario-scale. `maps/full.json` opens with 420 towns (5 factions) and packs hundreds of armies by turn 20; the standing heavy rig is 207 towns + 3036 armies, clustered and stacked. The naive builder — 5 factions × 3400 entities × ~600 own-entities ≈ 10M hypot/turn — costs *seconds* in Python. Spatial/numpy treatment is required on day one, not as a later rung.

House rules (from `docs/optimization_log.md`, all binding here):

- Paired, same-box measurement; never compare absolutes across machine states.
- Squared-reject (`dx*dx+dy*dy`) before hypot, everywhere (opt3-4).
- Reuse existing infra first: `SpatialHash` (movement.py), faction caches + `mark_dirty` flags (opt13), batch-iteration patterns (opt11).
- numpy sometimes wins big (ledger 11.7×, crowding 286×) and sometimes loses (movement velocities, closest-approach) — spike competing implementations, pick by numbers, revert on measurement (opt9/opt14 precedent).
- numba for tight kernels (286× crowding win), pre-compiled at import — first call must never pay ~600ms JIT latency (opt10).
- Kill O(n²) and per-query overhead on sight (by_id dict, batch removal, _by_turn index).
- Bench steady-state, not just snapshots: the heavy snapshot overstates real per-turn cost ~10× (opt16). Builder bench uses a real turn-20 `full.json` capture plus the heavy rig.
- No fine-grained threading (opt17/18: overhead exceeds work); no GC games (opt16).
- Equivalence standard adapts: byte-identical JSON can't apply (semantics change) — instead spec tests + hand-checked scenario diffs.

Memory (measured, not assumed): today's `town_history` costs ~170 MB at 415 towns × 3000 turns — deleted outright (no horizon lookups). In its place: windowed ledger (~10 turns × observed-entity entries; worst case everything observed ≈ 34k live entries ≈ 5 MB) + per-faction send-state (last-delivered per observed entity) + tombstones (tiny, pruned past window). Nothing grows with game length.

Wire discipline (opt19: 278→198 B/bot-turn today): delivery-on-change is mandatory, not polite (generation is every-turn; sending would be ~3400 × ~60 B × 5 ≈ 1 MB/turn — a 5000× blowup plus JSON serialization dominating the turn). Generation churn itself (appends worst ~3400/turn, less with skip-untagged) is knowledge-phase cost — inside `bench_builder_full` and the heavy-step bench, measured not assumed.

Builder cost anatomy at heavy scale (budget: ≤ today's ~5ms — 2.3ms vectorized visible + pops — paired, same rig):

1. Generation runs once per turn (shared, not 5×): one entry per observed entity, LOS tags via the spiked shape (no comparison at generation — the delivery diff-check owns slimness). Towns static: cache their arrays across turns, dirty-flag on found/death. Armies rebuilt O(A)/turn.
2. Delivery per faction — the fight. Naive shape (flat window scan ≈ 34k entries × 5 factions) is the cost to beat; candidate: per-faction indexed deques at generation (scans stay proportional to tagged-subset). Spike decides. Exact semantics, no approximations.
3. Send-state compares (dict reads), delay hypot via vectorized release check as today, serialize proportional to sent (diffs). Canonical order free (ledger order).
4. Serialize proportional to sent (diffs). Canonical order free (ledger turn order).

Bench: `bench_builder_full` in `benchmarks/bench_suite.py` on the existing heavy fixture + real turn-20 capture — mean/p99 builder ms/turn and payload bytes/faction, reported every run, paired old-vs-new during migration.

## Decisions for ratification

- **D1 (recommend yes):** include `has_target/target_x/target_y` in `army_update` (free, saves forecasting).
- **D2 (recommend yes):** drop battle events entirely (deaths + updates cover outcomes; trade inference bot-side). Risk: simultaneous-engagement intel gets thinner — acceptable, fog era anyway.
- **D3 (recommend: keep):** the ledger stays — windowed, tagged, as the shared generation log. Audit only migrates its tests.
- **D4:** `line_of_sight` single knob = `info_speed`, or separate config from day one? Recommend single (fewer moving parts; split when a bench demands it).
- **D5: decided yes** (entailed by no-map-to-bots: with no pre-seed geography, seen-tracking is load-bearing — targeting/scoring gate on it).
