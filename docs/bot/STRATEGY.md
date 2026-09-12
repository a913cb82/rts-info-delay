# Strategy — settled doctrine + live ideas

Settled reference (optimal play + as-coded) plus live ideas; history in BOT_WORKLOG.md, loop contract in README.md.

---

# Open ideas (LIVE — rots fast)

> **LIVE — rots fast.** This part is the STRATEGY.md backlog, kept verbatim. Ranked ideas decay as games land; shipped items move to BOT_WORKLOG.md + `STRATEGY.md#optimal-play-settled` addenda. Do not treat as settled doctrine.

# Brainstorm — ideas backlog (live)

Ranked by leverage. Shipped items move to BOT_WORKLOG + GTO addenda (`STRATEGY.md#optimal-play-settled`).
Saw it in a game? Add it here with the r-number.

## Active

1. **Early bloodbath t3000-4000** (every line; six mitigations active:
   S0-guard, guard-or-rich, threat-first, window-6, survivor-gate,
   second-body). Thin capitals vs first packs. Next angles: S0 second-
   print timing (guard before contact, not after?); conquest-garrison
   enforcement (taken towns MUST keep 1 for 25t — exists, verify it
   fires); first-pack interception (meet them en route with 2v1?).
2. **Crowding-collapse watch** (r95 F0 town4: 3.8k → trained to death —
   crowded under 1k, desperate print finished it). Negative-trending
   crowded towns should drain/convert EARLY (while rich), never print
   late. Needs: growth-trend trigger in demand (get_growth < 0 +
   crowded → deny trains, allow convert?).
3. **Harness ghosts** (filed 5x, not bot-side): Fischer increment always
   due (never 0.0); shuffle faction turn order per turn (faction-4
   starves); warm subprocesses; bigger main. Kills 1 bot most lines.
4. **Mirror opening theory** (pro-vs-pro): first-packer vs guarded
   sprawler — r84 sprawler won, r95 first-packer won. Which is right?
   Needs: opening book (guard-then-settle vs settle-then-guard by
   neighbor distance?).
5. **Settler escorts** (filed, marginal): idle escorts settlers through
   danger (follow at 1-turn trail?). Settlers die en route to guns.
6. **Buzzer playbook** (t9000+): strip-mine + mass is implemented;
   verify it FIRES when multi-polar (r74 quiet t9000?). Lead with
   strikes, not prints (prints strand when arrival > turns_left —
   strike already gates; pack deficit may not!).
7. **Conquest triage** (taken thin towns): garrison 1 for 25t (exists)
   vs strip-and-hold vs abandon. Thin conquests die (halved) — maybe
   decline thin takes entirely AND strip-mine them first (take the
   pop via... no raze command; convert? TRAIN at conquest (drains to
   armies!) then let it fall?).
8. **Opponent modeling** (BotForecast exists): printer/sterile tracked;
   extend to pack prediction (massing -> pre-muster!) and personality
   inference (turtle never chases; expander never holds — exploit?).
9. **Pro1-corner / turtle-edge dynamics** (map luck?): corner capitals
   die more. Real? (Void geometry: corners have fewer escape rays +
   fewer site options.) Mitigation: corner bots settle INWARD first?

## Parked (weak / needs evaluator)

- Counter-intel value; crowding-weapon; three-body combat doctrine;
  headless endgame exact trade (GTO §11 → `STRATEGY.md#optimal-play-settled` §11 Open questions).
- Feints / deception (overkill at current level).
- Diplomacy/pacts (no engine support).

## Done (this campaign)

Underdog variance, support ratio, survivor gate (priced+unpriced),
assault-verify (+ex-own, 800t), S0-guard, RTS FoW-erase, muster
window-6, threat-first trains, remuster guard, stale premium,
recon-by-fire + assault-once + attempt-cap, sync-hold 0.5, coverage
(sectors, nearby-first, rotating far, micro, home firewall, parking
fix), sneaky-settle (median, shadow, far-steep, spacing-120),
build-cap, pack-cap scale, scout cadence + foe-bend, guard-or-rich,
settler/second-body floors, capital-timely, naked-garrison,
hopeless→evac for all four, foe velocity ETA, probe-fresh, lead/
flip/health/churn tools, METHODS.md, greedy retired, double-pro.

## r96 loop (watch->story->right/wrong->brainstorm)

WATCH: 5 flips, turtle leads t5000, multi-polar to t6000, watch-health.
STORY: F4 tall-leader beheaded t6865 (12k, 0a — fortress with no
guard!); F1 mutual t4222 then stripped t4904; F0 wins t7000+.
RIGHT: turtle tall play (led!), F1 mutual-save, F0 pack timing.
WRONG: F4 zero-guard tall (tall needs 1 guard, not 0!); F1 no second
body post-mutual; F0 28-idle pile (rotation vs holds).
IDEAS: tall-guard minimum (turtle keeps 1 home ALWAYS, even dark);
post-mutual remuster priority (threat-first covers? verify!);
threat-diffusion field (below).

## Parked ideas (not worked now)

- Order-delay-aware sync (mail lag to armies in departure math; currently
  travel-only + 0.5 tolerance).
- Staging-then-jump sync (far holds 1 turn out, all jump together —
  needs staging points + convergence detection; current stagger+
  tolerance covers most).
- Defender-trickle audit (reinforce cohorts shipped; verify no solo feeds).
- Mirror opening book (guard-first vs settle-first by neighbor distance).
- Conquest strip-and-hold (TRAIN at thin conquest to drain, then let fall?).
- Personality exploit modeling (turtle never chases etc.).
- Corner-settle-inward bias (map luck?).
- Buzzer print-strand audit (prints for unlandable takes via pack deficit?).

---

# Optimal play (settled)

The following is STRATEGY.md, kept in full. Cross-refs to `STRATEGY.md` / `STRATEGY.md` now point at `STRATEGY.md#` anchors; refs to README / BOT_PLAN / BOT_WORKLOG / BOT_BENCH / BOT_TIME left as-is.

# GTO — game-theoretic optimal play

Reference strategy for bot work: what optimal play looks like, why, with
numbers. Personalities are parameter shifts on this backbone (section 8),
never a different game. Mechanics reference: `STRATEGY.md#as-coded-settled`. Open build steps:
`BOT_PLAN.md`. Numbers: `METHODS.md`. History: `BOT_WORKLOG.md`.

Status: **living hypothesis, not scripture.** Every claim here is a bet
priced from current measurements; landing Steps, bench numbers, and game
timelines are expected to overturn parts of it. When they do, update this
file first (it steers everything downstream) and log the change in the
worklog. Challenge entries with numbers, not arguments.

Scope: empty-map ladder (`empty_3000`, theoretical `empty_10000`,
`empty_100000`), symmetric starts. Contact-heavy and asymmetric maps
shift timings, not principles.

## 1. Rules that matter (with numbers)

- **Growth:** `0.001·P·(1−P/100000) × (1−Σ crowding)`. Peaks at
  **25/turn @ P=50000**. Crowding per neighbor ≤150km:
  `(1 + 0.01·ln(Pn/P)) × (0.1·√min(Pn,P)/d)^0.8`. Σ > 1 shrinks the town.
- **TRAIN:** −1000 pop → 1 army. **Capped 1/town/turn** (extras silently
  discarded); deducts unconditionally, spawns only if pop ≥ 1000 —
  over-ordering kills towns. Muster counts must be exact.
- **Combat:** weakness = #enemies ≤10km. N-vs-N annihilates everybody
  (1v1 *and* 2v2). Any strict outnumbering (2v1, 3v2) kills clean, zero
  casualties. Partial defense (1-vs-3) is pure donation — the one dies,
  all three live, the take proceeds.
- **Capture:** weakest-in-range faction takes (cross-faction tie or
  ally-match = held; same-faction ties capture). Pop halved, capital
  demoted. Halved-below-500 = instant starvation. Captures never create
  capitals — **beheading is permanent**; headless + armless is terminal.
- **BUILD:** first town in range merges (friendly: +500) or blocks
  (enemy: hold, order retained). Founding = pop-500 town, no stacking.
- **Intel:** LOS 150, info/orders 150km/turn, armies 50km/turn. Defense
  pays a **round-trip tax** (2·⌈D/150⌉) the attacker skips. Towns see
  150km themselves; capitals get own-town sightings instantly.
- **MOVE_CAPITAL:** normal command (dist-0 messenger) → economy intent
  (deduct 1000, demote at train time, spawn viceroy) → march → BUILD-step
  founding. Viceroy fights (interceptable), waits on foe towns, merges
  friendly. Flight = blind + mute + **amnesia on landing** (total memory
  wipe). Intent must execute *before* capture voids it (1–2 turns lead).
- **Score:** Σ pop + 1000×armies. Highest at buzzer wins.

## 2. Growth economics

**Creation taxed, compounding free, theft pays.** TRAIN→BUILD destroys
half the principal (−500 now) and compounding multiplies the hole:
measured −5800 terminal for three foundings against a hold baseline
(worklog empty_3000 re-analysis). Captures transfer (halved) *and* deny
the enemy's future compounding — the only profitable growth.

**Split iff big and spaced** (measured, crowding included):

| Config | Total/turn |
|---|---|
| 1×50k | 25.0 |
| 2×25k @40 / @65 / @100 / @150 | 19.7 / 25.4 / 28.9 / 31.3 |
| 5×10k ring @60 / @100 / @140-radius | 13.3 / 32.5 / 45.0 (no crowding) |
| 5×10k clustered @40 | −3.6 (starvation spiral) |

Two-way split beats lump above ~20–30k total pop. Pair breakeven ≈ 62km;
cluster floor ≈ 65km+ pairwise (worse for big clusters — more neighbors
each). With free spacing, finer splits keep winning toward 2× the lump
(linear regime) — limits are geometric, financial, military, never the
curve.

**Uniform even spacing beats variety.** Same geometry + total:
5×10k = 24.9 vs 40k+4×2.5k = 23.0. The log-asymmetry cancels pairwise;
Jensen on the concave logistic rewards evenness. No mixed-size
cleverness: equal towns, evenly spaced, as many as fit above the floor.

**Density is phase-dependent:** ~65–150km in the growth phase,
~300km at saturation (~10 slots/map — six-neighbor pack math). Dense
growth clusters that never thin pin each other below cap at saturation.

**Expansion payback ≈ 10⁸/P turns** (500-hole ÷ excess growth rate).
Never pays on 3000-horizons; turns +EV past home pop ~20k.
Saturation reference: 50k ≈ t5300, 95k ≈ t8240 (from 500, undisturbed).
500→5000 (self-muster size) takes ~2350 turns.

## 3. Combat and muster doctrine

Warning W + standing S vs raid N (W=3 on town-LOS): take iff
**N ≥ S+W+1** (at equality, mutual annihilation saves the town but eats
the defenders). So:

- **Defend at N+1** (keep everything — clean kill, survivors capture
  nothing because nothing remains to contest... they hold the field),
  **at N** (save the town, lose the armies — correct iff the town's
  saved compounding exceeds the muster, rich towns almost always),
  **or at 0** (lost — save the armies; partial reinforcement donates).
- **The (N+1)th army is the highest-leverage unit on the board:**
  converts your total loss into their total loss (≈2N+1 armies of swing).
  Never attack at exactly N when N+1 is affordable.
- **Reaction always wins ≤150km from capital** (round trip 2 < warning
  3); the capital itself is instant (dist-0 messengers same-turn).
  Beyond: pickets extend warning ~1:1, or pre-position, or don't hold.
- **Rush thresholds:** S=0 → N≥4 takes; S=1 → N≥5. Towns below ~4000
  pop can't muster deep (need (k+1)×1000 for k armies) — rushable even
  with full warning. A 920-pop capital can't print a single defender.
- **N-for-N is never the take** (no survivors = no capture), but is
  three legitimate tools: last-resort town-save, rich-vs-poor attrition
  (symmetric absolute loss, asymmetric relative + replacement — the
  poor side is pop-limited *and* 1/turn-capped), and setup-and-follow
  when out-printing locally (clear by mutual, take against the 1/turn
  re-muster).
- **Central reserve, not distributed garrisons.** One pile at the
  capital defends it instantly, reaches the ≤150km ring inside warning,
  covers all prongs at once (multi-prong multiplies *garrisons'* cost,
  not the reserve's), and doubles as the raid force. Distributed guards
  bleed compounding at every site; one reserve bleeds once.

## 4. Intel economics

**A scout costs the same 1000 as a guard and replaces K−1 of them.**
Blindness is the real tax — paid as distributed guards or lost towns.
One scout gives every town warning (muster-0 → muster-3 everywhere)
*plus* victim-finding. Optimal portfolio ≈ **1 scout + 1 central
reserve + incident musters**.

Two intel products, different buyers: **tripwire** (local, defensive —
protects colonies whose intel delay eats town-LOS warning) and **probe**
(far, offensive — finds victims). Capitals get warning free (own-town
LOS + zero delay), so tripless capitals still muster 3 — blindness
costs capitals only offense.

**Darkness shields the weak.** Expansion is invisible in the dark; poor
towns become hostages at intel summer, not at founding. Expand early in
the dark (max compounding + max time to self-sufficiency), never right
before the lights come on.

## 5. Deterrence equilibrium

Defense is nearly free ex ante (muster on warning with compounding pop);
failed raids cost the attacker 1000+. So ready defenders face only
−EV raids — **peace is deterrence, not harmony**. Guard iff
perceived-threat ≳ 1000/(town pop): rich towns nearly always, poor
towns almost never (third proof poor exposed towns shouldn't exist).

Cracks (the complete hunting license): poor/small towns (can't
self-muster), multi-prong coverage surcharge (defender pays +1 per
prong — surface area is liability), stale intel + arrival friction
(the just-in-time machine misfires; bots more than theory), beheading
permanence + headless-armless terminality (one unready moment ends the
game — never-thin capitals).

**The skipper dynamics.** Skipping guards/musters outgrows everyone
deterministically — then becomes the richest, fattest, observably
guardless target, and every opponent's raid math turns +EV. Fog
schedules the punishment (seasons, below) rather than cancelling it:
the skipper's fattening funds the scout that finds it.

**Player count tunes it:** each opponent is an independent raid-risk
roll — more players → earlier raid-EV triggers → higher equilibrium
guard levels. Two-player sustains long guardless stretches;
five-player keeps tripwires up.

**Tie paradox:** symmetric optimal play from symmetric starts is
deterministic — a tie. Wins come from others' deviations (pro's entire
empty_3000 strategy: hold while others spend −EV).

## 6. Seasons (phase-dependent GTO)

- **Dark spring:** compound (blind). Nothing worth finding/stealing;
  tripwire protects little. Zero armies is rational, not a mistake.
- **Intel summer:** towns pass scout+raid breakeven; first scout finds
  the skippers. Expansion must be self-sufficient by now or hostage.
- **Deterrent autumn:** minimal *visible* guards (visibility is
  load-bearing — a secret guard deters nothing), just-in-time musters,
  raid only the unread (poor towns, uncovered prongs, stale opponents).
- **Strip-mine buzzer:** retaliation time runs out — transfer-only
  theft still pays (guard everything ≥2000, take anything unguarded
  ≥2000), banked production → spearheads, convert idle cap-pop to
  armies (score-neutral, preserves options). First strike dominates;
  flip timing is the endgame skill. Near-zero forgone growth makes
  guards free AND raids cheap — no peace, just audit.

## 7. MOVE_CAPITAL doctrine

Costs: 1000 + flight (same speed as chasers — escape works by distance
and unpredictability, not immunity; interceptable, no combat exemption)
+ mutedness + **amnesia** (irreplaceable world model burned) + intel
hole. Buys: hub preservation (intel routing + muster point) and future
escapes; dodges permanent beheading. Maintain one pre-scouted fallback
site per capital (no upkeep, pure option).

**Escape young, endure established.** Early, amnesia is cheap (little
to forget) and hub future is long — evacuate ahead of any serious
spearhead (buildup pop-drops + forecast give the 1–2 turn lead; the
intent must fire *before* capture). Late, with a saturated empire,
flip it: headless-with-towns still scores, musters, and raids nearly
fully (only future escapes are lost), while amnesia torches the brain —
accept beheading, keep the model. Escape preserves the *option* to
escape, so its value compounds like everything else here.

**Drain-and-flee:** when evacuating a rich town under threat, muster
its pop into escorted armies first and leave the husk — denies the
predator the prize (the chaser marches far for ~500).

## 8. Phase playbooks (empty_100000)

- **Dark spring (t0–~2000, 500→~3500):** pure compound, zero armies.
- **Slot grab (~2000–8000):** exponential settler replication; nearest
  → contested-middle → buffers; space ≥65km, size evenly. Darkness
  shields growers; nobody punished yet.
- **Fortress (~8000–15000):** spending ~free at saturation. Standing
  border forces, picket depth, tripwire net, central reserves,
  fallback sites. Town count = firepower (1/turn/town).
- **Production war (~15000–95000):** concentrate flow into spearheads;
  defend points with standing + muster + relief. Border towns trade
  (~+50000 takes fund the war); interiors safe; beheading strikes vs
  exposed hubs. Extermination nearly impossible vs matched production —
  wars are positional.
- **Endgame (~95000+):** flip fortress→strip-mine (section 6).

Truncations: **3000** lives in spring (compound + S=1 guard + theft vs
poor only; founding −EV throughout). **10000** adds timed expansion
(~t4000, payback fits) and a short production tail (rich towns print
1/turn; raids/beheadings affordable late; intel critical mid-game).

## 9. Personalities (parameter shifts, all intelligent)

| | Guard floor | Intel | Raid bar | Expansion bar | Evac |
|---|---|---|---|---|---|
| pro (GTO) | 1, timed | probes+pickets on schedule | computed +EV | payback-positive | EV(hub) vs amnesia |
| greedy | 0, always | neither (blind) | transfer-positive only | very high (cherry-pick) | latest (often too late) |
| turtle | 2, early | pickets only | ~infinite (never) | high + near-only ≤150km | earliest + drain-and-flee |
| expander | 1, spread thin | probes (sprawl needs eyes) | medium (counter-raids) | lowest (+ contested-slot premium) | medium + hub-centroid moves |
| aggressive | 1, timed | earliest probes | marginal +EV + initiative | highest (backfill/staging only) | almost never (fights headless) |

- **Greedy (skipper):** S=0, blind, musters richly per incident (enough
  vs N≤3), dies to N≥4 rushes, beheaded by late evac. Never offers
  mutuals (can't stand losses — accidentally +1-disciplined). Richest
  each summer, everyone's best target each autumn. Arc: win the race,
  die to the first serious rush.
- **Turtle (fortress):** pays the early guard tax knowingly; near-only
  uniform expansion (accidentally optimal clustering); never raids;
  evacuates-and-drains at the first real spearhead; over-guards the
  buzzer. Never dies; loses the race by exactly its lifetime caution
  tax.
- **Expander (sprawl):** most slots, most hostages (many beyond muster
  range); thin defense, heavy pickets; **wields attrition mutuals**
  (out-print losses); survives predation by replacement rate; wins
  long wars its core survives.
- **Aggressive (predator):** systematic poor-town harvest; forward
  staging over settling; minimal shell + deterrence-by-punishment;
  multi-prong + beheading focus; +1 inside picked fights; mutuals as
  setup-and-follow; flips first at the buzzer. Terror spring,
  glass-cannon war machine.
- **Pro:** transitions at computed thresholds; the yardstick.

Dynamics: pro→greedy (scheduled punishment — affordable N≥5 vs
muster-3); aggressive→turtle (chases husks after drain-and-flee);
everyone→expander (strip colonies, never touch the core);
turtle→greedy (best neighbors — mutual non-aggression, greedy wins by
the caution tax); pro→turtle (death by compounding, no fighting
needed); aggressive↔expander (stripping rate vs print rate).

## 10. Testing GTO claims (hooks into benches)

- Payback bar: scenario with found-vs-hold choice at measured P;
  assert expansion only past computed breakeven.
- Muster math: N-raid vs S+W defense fixtures (take iff N ≥ S+W+1);
  partial-reinforcement-donates pin (1-vs-3 = loss with take).
- N+1 leverage: N+1-vs-N keeps all; N-vs-N mutual, no take.
- Scout-vs-guard accounting: blind+K-guards vs 1-scout+reserve
  across a fixed raid script.
- Seasons: long dark map (scout timing sweep — first +EV scout turn);
  buzzer flip (fortress vs strip-mine score crossover).
- Amnesia price: evac-vs-behead fixtures at young vs established
  empire sizes.
- Cluster geometry: split/lump, spacing, uniformity fixtures at the
  measured thresholds (62–65km, 20–30k flip).

## 11. Open questions

Exact summer timing (first +EV scout turn as a function of map density);
counter-intel value (needs evaluator first — parked); crowding-weapon
recheck under dense-phase math (parked, weak); three-body combat
doctrine (neutral in range shifts weaknesses, crushes bystanders);
headless endgame value (hub loss vs amnesia, exact trade).

## 12. Validated addenda (implementation campaign)

- **Equilibrium-tight:** all-credible defense + no unready prizes =
  zero battles (correct!). Strikes decline (no cracks); compounding
  decides. Forcing needs MASS (muster-up + multi-prong at buzzer).
- **Red Queen:** every bot improving tightens symmetric wars (margins
  compress; old fat margins unrepeatable). Judge relative + mechanisms.
- **Short-clean / long-mutual:** D==N trains iff turns_left ≤ 500
  (clean saves standing armies (terminal); mutual spends static (cheap
  long)). Deterrence needs overmatch (1.5×; peers mutual-accept!).
- **Strikes:** blitz (S+1, arrival ≤ 2, outruns intel) + buzzer (W=0,
  arrival ≤ turns_left ≤ 30). One per target (singularity). Windows!
- **Calibration:** unready = can't print OR won't (sterile 20+ turns).
  Fresh intel assumes live (dark-spring grace).
- **Site NET:** colony − home-crowding-externality > amortized (500/H).
  Fratricide dominates full-map expansion (never-seen voids excepted).
- **Merges:** home-capital merges need turns_left ≥ 500 (else treadmill).
- **JIT packs:** march iff complete or completes en route (long leave,
  short dash); pack cap 6 pre-siege (decline giant races).
- **Stay-behind (war-verdict, EMPTY_10000):** never drain home below
  N+1 vs live third parties (pro t4696 — the backstab tax).
- **Retaliation pricing:** raids price the victim's revenge
  (aggressive t4696: +320 pop, −(capital + 4 colonies + war)).
- **Headless wins:** beheading priced, not fatal (greedy won beheaded
  t4688→t10000; pro compounded beheaded t4696→).
- **Suicide-breaker:** re-verify defenders fresh per dispatch; 2
  fails on one target → stand down (expander t5282–t9965, 7 singles
  into a 7-stack, 0 casualties caused).
- **Density cap:** own-town spacing floor ~65km (expander 14×1.4k —
  sequential NET+ foundings, collective −EV).
- **Traffic vs threat:** inbound-vector test before mustering
  (settlers walk toward void, raiders toward ME — turtle spent 10k
  vs settlers).
- **Underdog variance (r65+):** the favorite plays safe (full needs),
  the behind-on-towns underdog gambles (need −1, min 1). Desperate
  takes seed comebacks and tax the leader; symmetric caution would
  freeze the leaderboard.
- **Support ratio (r74):** towns ≤ armies + 1, else no new colonies.
  Unguarded sprawl is future enemy towns (F2 led 28k with 5t/1a,
  picked apart town by town). Conquests scatter; guards don't.
- **Survivor gate (r79):** priced raids skip pop < 2× death threshold
  (takes halve at capture; thin prizes die same turn). Denial keeps
  thin targets (spite has its own math).
- **Assault-verify (r84):** foe-belief > 300t stale holds packs
  (approach re-scouts or FoW-erases). Stale-mirror fratricide (town
  flipped back unseen) is the bound, not zero.
- **S0-guard (r83):** lone unscouted army holds the capital (first
  packs walk into naked capitals t2300+). Scout pipeline untouched
  (intel first); the guard is for bodies with no mission.
- **RTS FoW (user):** last-known persists; erase only on observed
  absence (observer watches ground past mail delay + 2, still silent
  = gone). Stale-but-unwatched is genuinely unknown (kept).
- **Muster foresight (r63):** threat window 6 (mail + print + spawn
  eat 2-3 turns; eta-4 musters lose the race by a turn). Threatened
  towns train first (offense starves defense under 1/town cap).
- **Remuster (r51):** S=0 vs a printer needs +1 (observed empty +
  printing foe = remuster before arrival; onesies never suffice).
  Sterile-observed still takes cheap.
- **Stale-age premium (r55):** unseen s = 3 + age//500, cap +3
  (unseen towns accumulate guards; undersized packs bleed).
- **Recon-by-fire, assault-once (r68/69):** short-by-≤2 + there =
  attack (intel resolves on contact); fresh blood (<1000t) vetoes
  re-assaults (re-feeding real garrisons is onesie farming).

---

# As coded (settled)

The following is STRATEGY.md, kept in full. Cross-refs to `STRATEGY.md` / `STRATEGY.md` now point at `STRATEGY.md#` anchors; refs to README / BOT_PLAN / BOT_WORKLOG / BOT_BENCH / BOT_TIME left as-is.

# Bots — current guide

Living reference for bot work: personalities as coded, shared machinery,
the intel model, and the mechanics that matter. Entry point: `README.md`.
Strategy: `STRATEGY.md#optimal-play-settled`. History lives in `BOT_WORKLOG.md`, numbers in
`METHODS.md`, open plans in `BOT_PLAN.md`, clock infrastructure in
`METHODS.md`.

## Personalities

Five bots (`src/bots/`), distinct characters. `stub` is passive harness
furniture for scenarios, not a personality. There is no `random` bot
(retired pre-campaign, replaced by `pro`).

### greedy — RETIRED (replaced by 2nd pro; history below kept)
- Step 2 on shared demand API (present-biased params): rich-only incident
  muster (depth +500), transfer-positive raids only (margin 500),
  cherry-pick expansion (payback x2), one prober breaking the scout
  paradox (no army→no intel→no demand). No P3b — void settlers need trains.
- Raids the priced take (unready-weighted `raid_target`), marches when
  the pack is ready, holds while trains build it (pack gate — the
  skip_thin deadlock class). Pack deadlock vs passive prizes solved by
  print calibration (`foe_print_factor`: sterile-observed factions count
  zero printable — unready means can't OR won't).
- No actionable contact → first settler probes (S0 scout: 50 km hops,
  rubble-avoiding, found-fallback); later settlers expand on demand;
  recycle/merge peace-only (war-footing holds — shared guard_duty lesson).

### aggressive — The Conqueror
- Step 2 on shared demand API (predator params): thin cushion (depth 0,
  forward towns print — no distance rule, no peak cap), marginal +
  initiative raids (margin 100), economic expansion rare (payback x3),
  1 prober. Pack gate subsumes A2 departure-sync (need covers
  defendedness; the retrench-march trickled).
- Military staging (not economic settling): found toward the raid target
  while no own town stands within 150km of it — forward bases print
  locally (short arrival → completable needs). Staging builds WITH the
  pack; marginal horizon 500 kills obsolete outposts (viable t32).
  Probe in force (nearby, S==0, range-capped) + bird-in-hand shared.
- No actionable contact → scout-first like greedy (faction-ray sweep);
  no viable targets → chase foe armies at forecast positions; else expand
  (sites 120–340 km, moves now noted — the old branch forgot, causing
  zigzag re-dispatches). Keeps one home army vs inbound/second-wave like
  greedy (ungated), but never hoards beyond that: all-out is the character.

### expander — The Colonist
- Trains via `can_train_here` non-conservative. Guard rule keeps one home
  vs inbound/second-wave; otherwise every army is a settler, outward
  120–350 km (first probes as S0 scout). No evac by design — accepts
  decapitation, wins by spread.
- Chain behavior (each established town owes a settler) is emergent and
  kept as policy. Loses to early raids (proven), out-settles turtles
  (proven territorially, score lags: new towns start at 500).

### turtle — The Fortifier
- Threat-responsive bars per town: 1200 (ETA ≤ 4) / 1700 (≤ 10) / 2000
  (sleeping lightly while no threat shows anywhere) / 2600 (hoarding).
  Threat is per-town (armies imputed to the own town nearest *them*).
  One train per turn, max.
- Peacetime picket: single-town factions keep one blind army; multi-town
  factions hoard until threats show. KNOWN GAP: sub-1500 relaxed trains
  don't survive the 1000 cost (1200 − 1000 = 200 < 500) — the survive
  floor is specified in `BOT_PLAN.md`, not yet coded.
- Recall settlers to the capital when threatened (2v1 assembly) unless
  hopeless; cap-concentration (never split garrisons); threatened home
  armies hold position, never dispatch.
- MOVE_CAPITAL evac when hopeless + capital ≥ 2× cost, aimed away from
  the threat. Needs a 1-turn lead now (economy spawn); fails permanently
  if the viceroy dies. Builds close (40–140 km), one builder at a time.

### pro — No Personality
- Demand-gated trains (Step 2): threat muster by outcome rule
  (`defense_train_ok`: train iff D == N-1 flips take→save, floor or
  doomed-convert; D == N holds for the mutual, D > N already won,
  D < N-1 already lost), raid pipeline (pack deficit for the priced
  target), expansion pipeline (void merit or contested payback 1e8/P).
  No trains without demand — the always-train era is over.
- Priced raid selection (unready-weighted: take needs N ≥ S+W+1 with
  printable-before-arrival, prize clears risk premium) + leader-targeting
  + departure-sync + rope-a-dope/Evac kept. Duel-only gating (P5–P7).
- Hold rule: keep min(home, N+1) per threatened town; hopeless towns
  (D ≤ N-2) keep none. War-footing: no recycle-merges and no settler
  marches under known threat (guard_duty t31 lesson) — hold instead.
- Empty-field economy: with no foes anywhere, holds and compounds
  (matches the 5254 policy optimum exactly). Exam 13/15 (fails: young
  evac needs D<N hopeless — Step 5; blind — recon owed).

## Shared machinery (`common.py`)

- Shared threat math: `inbound_force` (per-town ETA + count, guard-
  excluded) feeds `inbound_eta`; `defense_train_ok` (outcome-rule
  muster, shared turtle/pro); `staging_eta` (positioning-threat).
- `BotState`: seen-only world mirror (holds only delivered updates) +
  `turn/faction`; upsert parser (absolute create/update/remove, unknown
  kinds ignored, deaths clear trackers); `evac_ordered` flag + amnesia
  wipe on stream jump (world, trackers, plans, `last_seen`, trails);
  `_army_targets` (own MOVE_TO notes via `note_orders`, cleared on
  BUILD/death/arrival); `_pending_trains/_builds` confirmed by own
  `town_update` pop drops; `last_seen` delivery stamps + per-army
  position trails (foe velocity stands in for intent); `_prev_pop/_growth`
  (per-turn net deltas, reset on turn advance, net of train-spends and
  capture-halves — spends misread as collapse poison hopelessness),
  overcrowding clusters
  (negative-growth towns within 150 km; smallest per cluster trains),
  memoized `stale_turns` (dist-to-capital/info_speed), fingerprint-gated
  standing-order replay + plan queue + clock effort (see `METHODS.md`).
  `is_quiet`: any update breaks sleep.
- S0 scout (`_scout_id/_scout_leg`, hop notes in `_army_targets`): probe
  before founding, rubble-avoiding, viable/army contact hands to normal
  logic (stale hop note dropped); builds stages never found on scout
  waypoints. `drop_dead_notes` clears trail-stale notes (messenger-died
  orders strand otherwise). `order_move` quiescence gate: MOVE_TO only
  from converged intel (mid-course retargets of movers are structurally
  dead) — all 19 dispatch sites route through it.
- Defense trio (greedy/aggressive/expander/pro): `inbound_eta` (per-town
  inbound ETAs ≤ 8 turns; stationary foe guards excluded),
  `note_wave_watch` (vanished own army → hold one home 6 turns),
  `should_hold_home` (keep ≥1 army on a threatened town).
- `staging_eta` (shared): a known foe town inside home LOS (150 km) of an
  own town is raid staging → positioning-threat (recall/hold). Never a
  spend-signal: mustering costs 1000 against a town that may never
  produce force, while recall is free insurance. Turtle merges it into
  `threat_eta`; spend bars everywhere stay army-only.
- Turtle last-stand fires only when home defenders are strictly
  outnumbered (D < N) at ETA ≤ 3 — a defender that mutual-saves holds,
  never guts its own town (t9 lesson: spending kills as surely as raids).
- `find_build_site`: deterministic hash samples, scored by
  (min-dist-to-any-town desc, crowding asc), >20 km from every town.
  Reach per bot above; the spin is seeded by army id (`who`), never the
  turn — re-queries hold headings instead of roulette-retargeting.
- `BotForecast`: delay-compensated army positions
  (`forecast_army_pos`, `forecast_all_armies`); `with_my_orders`
  partially built, `with_en_route_orders` / `forecast_battles` stubs.
- Decide shape: greedy/pro run lazy trains→moves→builds stages (clock can
  truncate to trains-only); aggressive/expander/turtle run single loops.
  Deterministic throughout (`_hash`, no `random` module).

## Intel model (updates, not events)

The only honest mental model: **bots see snapshots, late — never events,
never the map**. Each turn the engine observes (line-of-sight discs,
`line_of_sight` 150 km, own entities always seen), stamps what was seen,
and delivers when each observation's delay releases
(`t + dist/capital/info_speed ≤ now`, exact) — but only observations
from turns at or after the faction's last landing S. Three gates
(tagged + released + ≥ S), no exceptions.

- **Wire**: `town_update{id,x,y,faction,population,is_capital}` (pop 0 =
  dead) and `army_update{id,x,y,faction,alive,is_viceroy}`
  (`alive False` = dead — that *is* the battle report). No intent, no
  battle events, no map, no seer lists. Newest passing snapshot wins per
  entity; unchanged snapshots stay silent, so quiet worlds cost ~nothing.
- **Flight**: a faction with a viceroy airborne is blind *and mute* —
  no turns sent, no orders read, clock frozen.
- **Landing**: the runner sets S and resets send-state; the bot wipes on
  its own remembered MOVE_CAPITAL order (stream jump = success, wipe
  everything; sequential = failure, carry on). Survivors re-announce
  paced by delay; the S−1 transient is never known; ghosts are
  impossible — the wiped bot has no memory for a corpse to haunt.
- **Deaths are uniform**: told-alive implies told-dead through the same
  three gates, no special cases. Force-counting is trustworthy; the +1
  doctrine can rely on it. Own capital (dist 0) is the only fresh reading.

## Mechanics that matter

- **Turn order**: command → propagation (messengers advance/deliver) →
  movement (50 km/turn, path-blocking stops at closest approach) →
  combat (simultaneous deaths + contested takes) → economy (growth, TRAIN spawns,
  BUILD consumes incl. viceroy founding, deaths) → knowledge (ledger
  generate + evict).
- **Combat (weakness)**: armies count enemies within 10 km; an army dies
  if any enemy in radius has weakness ≤ its own. 1v1 *and* 2v2 annihilate
  everybody; any strict outnumbering (2v1, 3v2) kills clean with zero
  casualties. +1 local superiority is the whole game.
- **Order lag** (all commands ride messengers at 150 km/turn): MOVE_TO
  measures capital→from, BUILD capital→site, TRAIN capital→town,
  MOVE_CAPITAL capital→capital (dist 0, same-turn delivery). FIFO per
  entity, dead letters dropped. Decisions span both legs: intel was stale
  coming in, the order is stale going out (~2× one-way lag round trip).
- **TRAIN** is one-shot (deduct, spawn iff pop ≥ 1000). Quirk: it credits
  the *pre-capture* owner — a town captured the same turn still spawns
  for its old faction at the enemy's expense.
- **Capture**: survivor within 10 km flips the town, pop halved, capital
  demoted. **Never creates capitals — beheading is permanent.**
- **MOVE_CAPITAL** is a pre-programmed TRAIN: messenger → economy execution
  (deduct, demote old capital *at train time*, spawn viceroy with march
  target) → normal march → a later economy BUILD-step founds (pop 500)
  and promotes. The viceroy marches *through* combat and can be
  intercepted; if it dies, the beheading is permanent. No capital exists
  mid-flight; second orders during flight die at send (no capital to
  target); if the capital falls before economy, the intent drops. Needs
  a 1-turn lead — same-turn rescue is structurally impossible.
- **Economy**: logistic 0.001·P·(1−P/100k) minus crowding, ~1–25 pop/turn
  realistic. A train→build cycle is −500 *now*; at these growth rates it
  repays over hundreds of turns. Spending is the scarce resource.
- **Score**: Σ pop + 1000·armies. Training converts 1000 pop to a 1000
  army (neutral); everything after that (trades, builds, compounding)
  decides whether it profited.

## Hard lessons (indexed, not repeated)

- Affordability ≠ desirability (forecast episode): gating *whether* a
  train is affordable without asking *what it's for* unlocks wasteful
  distant trains (−530 uniform). Demand gates are the open work.
- Delayed intel can't be outgrown: 4-turn growth (~+4) can't close 100+
  intel gaps at 1200+ bars. Stale-threshold failures need risk posture,
  not arithmetic.
- Mirrors break by intelligence, not timing: synchronized decisions come
  from identical thresholds + intel; jitter was tried on paper and
  rejected — foresee the 1v1, decline or convert it.
- The fudge postmortem: the old +400/turn distance buffer was load-bearing
  as a *spending brake*, not as staleness compensation. Its replacement
  must brake spending deliberately (demand), not accidentally.

## Gates for future work

Fast suite (`scenario_bench.py`, ~1.5s) per change; strategic suite
(`strategic_bench.py`, ~10s) at milestones; `empty_3000` rematch read as
a trade ledger; `pytest` green. Binding baselines: `METHODS.md` fog-era
table (campaign/delayed tables are record, not targets).

---

# Pitfalls / failed-attempts (settled — do not retry without new evidence)

Consolidated index of don't-do / failed items found across all three sources. Each item is ALSO kept in place above — this section only collects pointers + one-line why, so future work doesn't re-try them blind.

- **Always-train era (over; `STRATEGY.md#as-coded-settled` pro):** no trains without demand. Affordability ≠ desirability — affordable-but-purposeless trains bled −530 uniform (forecast episode). Replaced by demand gates.
- **Fudge +400/turn distance buffer (removed):** was accidentally load-bearing as a spending brake, not staleness compensation. Do not re-add as arithmetic; brake spending deliberately via demand.
- **Jitter to break mirrors (tried on paper, rejected):** synchronized decisions come from identical thresholds + intel. Fix is intelligence (foresee the 1v1, decline or convert), not timing noise.
- **Stale-threshold arithmetic vs delayed intel (failed):** 4-turn growth (~+4) can't close 100+ intel gaps at 1200+ bars. Needs risk posture, not tighter arithmetic.
- **Partial reinforcement of lost towns (donation):** at D ≤ N−2 / 1-vs-3, reinforcing donates armies and still loses the town. Hold at 0, save the armies (`STRATEGY.md#optimal-play-settled` §3).
- **Last-stand gutting a mutual-save (t9 lesson):** a defender that mutual-saves (D == N) holds — never gut its own town; spending kills as surely as raids.
- **War-footing recycle-merges / settler marches under known threat (guard_duty t31 lesson):** hold instead; merges and marches under threat feed the attacker.
- **Mid-course retargets of movers (structurally dead):** MOVE_TO only from converged intel via the `order_move` quiescence gate; retargeting movers strands orders.
- **Messenger-died strands (fixed by `drop_dead_notes`):** trail-stale notes must clear, else dead messengers strand future orders.
- **Roulette-retargeting build sites (fixed):** `find_build_site` spin seeded by army id, never the turn — re-queries must hold headings.
- **Spends misread as collapse (fixed in `_prev_pop/_growth`):** train-spends and capture-halves netted out of growth deltas, else hopelessness logic poisons itself.
- **Mustering against staging towns (never a spend-signal):** `staging_eta` positioning-threat triggers recall/hold only — mustering 1000 against a town that may never produce force is −EV.
- **Suicide packs into verified stacks (expander t5282–t9965):** 7 singles into a 7-stack, 0 casualties. Re-verify defenders fresh per dispatch; 2 fails on one target → stand down.
- **Draining home below N+1 vs live third parties (pro t4696 backstab tax):** never drain home below N+1 while third parties live.
- **Mustering against settler traffic (turtle 10k waste):** inbound-vector test first — settlers walk toward void, raiders toward ME.
- **Stale-mirror fratricide (bound, not zero):** foe-belief > 300t stale holds packs; approach re-scouts or FoW-erases (`STRATEGY.md#optimal-play-settled` assault-verify).
- **Parking / dispatch bookkeeping (fixed):** moves now noted (old aggressive branch forgot → zigzag re-dispatches); builds never on scout waypoints; scout hop notes dropped on handoff.
- **Sub-1500 relaxed trains (KNOWN GAP, do not repeat pattern):** 1200 − 1000 = 200 < 500 — trains that don't survive the cost. Survive floor lives in BOT_PLAN.md.
- **Feints / deception (parked — overkill at current level):** do not build until bots punish basic play.
- **Counter-intel / crowding-weapon / three-body doctrine / headless exact trade (parked — needs evaluator / weak):** see `STRATEGY.md#open-ideas-live--rots-fast` Parked; GTO §11 open questions. Do not promote without measurement.
- **Diplomacy/pacts (parked — no engine support):** no mechanism to implement against.
- **Harness-side deaths (not bot-side; filed 5x):** Fischer increment always due, faction turn-order shuffle, warm subprocesses. Do not "fix" in bot code.
