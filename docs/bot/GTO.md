# GTO — game-theoretic optimal play

Reference strategy for bot work: what optimal play looks like, why, with
numbers. Personalities are parameter shifts on this backbone (section 8),
never a different game. Mechanics reference: `BOTS.md`. Open build steps:
`BOT_PLAN.md`. Numbers: `BOT_BENCH.md`. History: `BOT_WORKLOG.md`.

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
