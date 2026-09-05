# Bot plan — doctrine and open work

What we believe about playing well, and what remains to build, in order.
State of the bots: `BOTS.md`. Numbers: `BOT_BENCH.md`. History: `BOT_WORKLOG.md`.
Full strategy reference: `GTO.md` (this plan's doctrine section is the
compact form; GTO.md is the detailed form).

## Goal

Pro converges to true GTO play (`GTO.md`); every other bot converges to
GTO skewed by its personality — same optimal backbone, documented bias
parameters (`GTO.md` §9): greedy present-biased, turtle risk-averse,
expander slot-hungry, aggressive initiative-hungry. A personality is a
parameter shift, never a different game: all five muster, +1, price, and
time correctly; they differ only in what they systematically
over/under-buy. Every step below serves that convergence (pro pays full
price on time; the others deviate on schedule, not by error).

None of this is fixed. GTO.md is mutable and will need updating as game
dynamics reveal more complexity — and so does this plan, and every doc
around it. When a bench number or game timeline contradicts a doctrine
point, the doctrine changes (with a worklog entry), not the evidence.
Treat anything here that hasn't been re-confirmed recently as suspect.

## Doctrine (settled)

1. **N+1, N, or 0 — never partial.** Equal numbers annihilate (1v1 *and*
   2v2), so the (N+1)th army is the highest-leverage unit on the board:
   it converts your total loss into their total loss. Defend at N+1
   (keep everything), at N (save the town, lose the armies — correct for
   rich towns, spoiling interceptions, and rich-vs-poor attrition), or
   at 0 (lost — save the armies; partial reinforcement donates). Never
   attack at exactly N when N+1 is affordable; N-for-N is never the take
   (no survivors = no capture).
2. **Trade evaluator.** Every march-or-hold decision answers: when these
   paths meet, do I strictly outnumber? Outnumber → take it. Equal →
   decline (free and unilateral — both declining is just peace, which
   favors whoever compounds faster) or convert (add one: train, recall,
   viceroy — print time included, since TRAIN is capped 1/town/turn and
   a muster of N costs N turns at one town). Outnumbered → be elsewhere.
   Takes need N ≥ S+W+1 against warning W plus standing S. Armies are
   1000 pop that *would* compound; ground re-settles.
3. **Last responsible moment.** All lags are known (intel + messenger ≈
   2× one-way per decision, plus 1 turn per mustered army under the
   TRAIN cap), so compute the latest turn you can act and wait for it.
   Early reactions bleed production and chase ghosts.
4. **No randomness, ever.** Mirrors come from identical thresholds +
   intel; break them by outplaying (foresee, decline, convert first),
   never by jitter. Deterministic tie-breaks only as last resorts.
5. **Demand before affordability.** A train is −500 now, repaid over
   hundreds of turns. Never train for the sake of training — train at a
   target, a threat, or a pipeline.
6. **Risk posture is per-bot, scaled by lag.** Stale intel needs *decided*
   optimism/pessimism, not fudge factors: near towns decide sharp, far
   towns need trend confirmation or big margins. Turtle paranoid on
   defense, patient on offense; greedy the reverse.
7. **Capitalhood is an option, priced against amnesia.** Beheading is
   permanent, but headless-with-towns still scores, musters, and raids
   nearly fully — what dies is future escapes plus the intel hub. Escape
   young (amnesia cheap, hub future long), endure established (the brain
   outweighs the hub). Snipe theirs, above all once established; price
   your own escape by empire age, never by panic.

## Open work, in order

**Step 0 — housekeeping.** DONE (fog era): EVENT_REWORK landed, both
suites re-baselined as the binding table (BOT_BENCH.md fog-era section);
wake and defense fixed themselves via re-observation under S; endgame
attribution (beheading vs intel timing) left open — bisect only if it
matters for a later step.

**Step 1 — survive floor.** DONE: relaxed TRAIN needs pop − cost ≥
floor unless per-town last-stand (threat imputed HERE, ETA ≤ 3). Pre-work
found the global `doomed` defined-but-never-wired; shared bars already
safe, turtle-only fix. Decide-level pins (map scenario infeasible —
score-neutral training + capture-halving erase the delta); suite 15/15.

**Step 2 — demand-gated trains + trade evaluator.** Keep affordability
floors exactly as coded; add demand per personality before any TRAIN:
raiders (viable target in march range, or inbound to answer), expander
(towns above band without a builder en route), turtle (inbound/threatened,
or missing picket). Kills the wasteful-distant-train class the forecast
episode exposed. Bench test: conquest scenarios stop bleeding −500 cycles;
quiet scenarios hoard identically.
Fog-era funnel (why this step is next): skip_thin 3467→2151,
trap 4040→3165, viable 3768→3088 — raid judgment got worse under fog while
defense got better, so every march-or-hold decision now needs an explicit
profitability proof. Evaluator rules: sums gate on KNOWN foes only (the
mirror holds observed entities — never-observed forces are absent by
construction, not zero); `last_seen` staleness scales the risk posture;
all force counts from delivered trails, never intent; parse finished
battles for force counts to calibrate. Muster math under the TRAIN cap:
no instant N+1 — the evaluator plans multi-turn print (1/town/turn) plus
standing, prices takes against N ≥ S+W+1, and never orders partial
musters. DONE for all five (shared demand API + DemandParams): pro
(GTO baseline; exam muster 8/8, selectivity 3/3), greedy (rich-only
muster, transfer-only raids, cherry-pick x2, 1 prober), aggressive
(thin cushion, margin 100, military staging, pack>trickle), expander
(sprawl: depth +1000 core-only, margin 300, impatient x0.3, parallel,
rates overridden), turtle (threat-bars + last-stand + staging-threat;
expansion spatially-gated near-only BY DESIGN, no raid pipeline —
fortress). Calibration (sterile W=0), pipelines (deficit+bird-in-hand),
probes (S==0, range-capped, singular), pack gates, war-footing holds
(no disband/merge under threat), growth net of spends, site-veto NET —
all shared. Exam acceptance MET AND EXCEEDED (muster 8/8 includes
horizon pins). Scouting prerequisite SHIPPED (S0 no-contact protocol +
pro recon, below).

**S0 — no-contact scout (shipped).** First settler probes before
founding: 50km hops (arrival-gated; mid-course retargeting is
structurally dead — 2-turn intel lag vs 1-step projection), faction-ray
direction, avoidance of known towns, found-fallback at hop 12.
Contact rules: viable town / foe army hands to raid/defense (stale hop
note dropped); rubble-only stays out. Support: `drop_dead_notes`
(trail-freshness unstranding), `order_move` quiescence gate (orders only
from converged intel — fixes the drunk-walk + site-steal families),
builds stages never found on scout waypoints. Evidence: all raid takes
restored, void_contact takes, trap/skip_thin skip decoys and take
prizes. Costs: scout tax in sprint races (outsettle), slower probes
(~3 turns/50km at range). Pro recon NOT done (pro still blind — owes
before Step 5/6 need eyes); turtle pickets NOT done.
Followups filed (re-analysis below): probe memory SHIPPED, turn-hash
SHIPPED (which defused the roulette half of the note-drop tension —
re-plots return the same site). Note-drop proper CLOSED as benign:
measured 88/88 empty_3000 drops on scout notes with 0 doglegs — drops
fire during arrival-waits on fresh orders, the army marches on
engine-side, quiescence blocks doomed re-dispatches; pure bookkeeping
churn, no strand, no delay. Worklog has the numbers.

**Step 3 — meeting + tempo. DONE:** recall_deficit (deficit + fresh
staging) + reinforce_orders (cross-town surplus→deficit, in-time) +
jit_ready packs (march iff complete or completes en route; pack cap 6
pre-siege) + probe singularity shared. REMAIN filed: Step-3v2 field
intercept (same-speed meetings rarely pay; town-reinforcement covers
the common case), S0 probe tempo (risk unpriced), raid-window urgency
(folded into strikes).

**Step 4 — post-capture doctrine. DONE (compositional):** veterans hold
conquests (war-footing no-merge) + conquest guards (_taken_at, 25 turns)
+ sel-chains re-raid when priced + suppressed-arrival lite (builds
re-decision: demand+site re-check, drop-and-retask, no hostage gifts).
(Besiege/leave/wait all emerge from holds+marches; no separate engine.)

**Step 5 — evac v2 + capital game.** Earlier-and-stricter evac gates
(1-turn lead now required; failure beheads permanently); viceroy routing
around known armies; leader-targeting with capital-sniping weight;
Pre-step verdict OWED-AND-DELIVERED: Elo resolved (greedy 1544 /
aggressive 1543 take; holders hold) — old all-hold was attacker-passivity,
not mechanics. Sniping work unblocked when Steps 2–4 land;
settler-hunting (kill unescorted movers when nothing is worth taking);
buffer-settling toward spent foes (turtle-true offense). Evac gates differ
by personality (goal framing): turtle earliest + drain-and-flee (muster
into escorted exodus, leave the husk); pro computed (hub future vs
amnesia); greedy latest (compounding over beheading risk); aggressive
almost never (fights headless); expander moves hub by geometry (centroid).
Rule of thumb: escape young, endure established.
DONE: hopeless D<N (exam), evac_plan drain-and-flee (turtle any-doom +
pro computed-endure), snipe 1.5x (exam), standing guards (asymmetric),
war-print towns. REMAIN filed: settler-hunting (needs Step-3v2),
greedy-late-evac + expander-centroid (character), evac-routing exactness
(centroid-away suffices).

**Step 6 — buzzer + strikes. DONE minimal:** buzzer defense (blind
guards + arrival caps + no-settle; muster stays demand-gated (strip-mine
is self-tax without strikes)); strike doctrine (S+1 blitz ≤2 turns +
W=0 buzzer ≤30t, singularity-shared, strike-deficit; exam endgame 3/3).
REMAIN filed: Step-6-siege-mass + multi-prong (needs mass first),
first-strike exact timing, endgame flip timing.

Explicitly parked: crowding-weapon colonies (weak math), settler-escort
bodyguards (messenger lag wins; exodus convoys under Step 5 are the live
form), TRAIN pre-capture quirk exploits
(engine smell, not doctrine), counter-intel (staying out of foe sight
discs on purpose — needs the evaluator first so we know what secrecy is
worth). Retired from this list: per-faction sent-tracking for landing
fog — the rework's send-state + S + amnesia solved it in the engine.

## empty_3000 findings → per-bot items (3000t rematch evidence, PRE-SCOUT game — re-analysis below supersedes for the scout era)

The whole game: 15000 pop_changes, 9 spawns, 42 moves, **0 battles, 0
captures, 0 ownership changes**. All five towns sit 329 km from their
nearest neighbor against LOS 150 — a geometrically blind universe, and
no bot ever looked: 5 bots × 3000 turns × 0 contacts. Spawn turns
cluster (1175, 2165) because identical economies cross bars together;
aggressive and expander score byte-identical at every checkpoint
(mirror-by-void: same thresholds + same empty intel → same actions).
Settlers march ~260 km in ~6 turns, then sit ~1800 turns with no BUILD
and no recall (the 42 moves are nearly all march-outs). Town pops at
t2999: pro 9156 vs greedy 1089 / aggressive+expander 1376 / turtle 2232
— early spending with zero return is catastrophic at these growth rates.

- **pro — scheduled reconnaissance (STILL OPEN).** Hold-and-compound is
optimal *if alone*, but pro cannot distinguish alone from far — the
rematch proves it (pro sits while four founders collide). Zero
observations by turn T → spend one army on hop-probing (reuse S0).
Cost ~1000 once; unlocks everything dead in a void (departure-sync,
leader-targeting, counter-punch). Owed before Steps 5–6 need eyes.
- **greedy — DONE (scout + unstranding).** Hop-probing + drop_dead_notes
+ quiescence closed the 1850-turn sits; raid_hold/skip_thin/void_contact
take. Demand gates (Step 2 core) remain.
- **aggressive — DONE (scout + note_move fix + unstranding).** Sweep
probes (faction-ray diverges void-mirrors); pair/viable/trap take.
Also fixed: expand branch never noted moves (zigzag class). (Steps 2–3
core: demand + forecast remain.)
- **expander — DONE (follow-through was engine blindness).** The
settlers were fine; movement streams were strangled (delivery dedup
without position). void_settle 1→3 towns, chain/settle pass. (Steps 2,
4 core remain.)
- **turtle — picket expiry + conditioned pickets (STILL OPEN).** Step 1
floor done; order_move now notes (settlers actually settle). Expiry (no
contact → recycle) and observation-conditioned pickets remain. (Step 2.)
- **Shared — no-contact protocol.** Zero foe observations by turn T →
all personalities switch from economy/hoard scripts to search scripts.
This is the Step 2 scouting prerequisite with hard evidence behind it.
Also check site-search edge pull (two of six excursion endpoints hug map
edges; the max-dist-from-towns scorer pulls outward — verify interior
coverage).

## empty_3000 re-analysis → new items (merged-phase engine, 3136-lineage)

Same scores as the scoreboard (pro 9156 / turtle 6637 / expander 4227 /
aggressive 3766 / greedy 3136), new mechanisms. Full timeline in the
worklog; items:

- **Shared — probe memory (NEW, Step 2 scouting).** Second probes fly
the identical deterministic ray and merge into own towns (+506 ×2,
+500 — 90-turn marches for zero expansion). The settle-as-scout
fallback founds on the kept hop target, bypassing find_build_site's
<20km town skip. Fix: remember probe endpoints (own foundings +
in-flight settler destinations); bend rays off own towns too; check
own-town proximity before fallback founding.
- **Shared — scout/note-drop tension (NEW, S0 followup).** Arrival
waits (~delay ×2 + quiescence, static by design) sit inside
drop_dead_notes' exp_delay+2 margin → suspected mid-probe note drops
→ turn-hashed resettle → drunk-walk doglegs. Fix: exempt the marked
scout's kept hop target until arrival-intel converges; confirm with
bot-side logging before/after.
- **Shared — turn-hashed sites (NEW, minor).** find_build_site hashes
the decision turn: same situation, different turn → different site.
Harmless for first picks, harmful after note-drops (retarget
roulette). Fix: hash (army, leg) or remember the chosen site.
- **Greedy — thin-capital pricing (Step 2 evidence).** Floor-trains at
1500 leave ~500 capitals exposed ~1000 turns; the t2835 take killed
one (460 <500 → starvation, headless + armless = terminal, no recap
possible). Demand gates must price capital buffer, not just
affordability; expansion ledger ≈ -5800 terminal vs holding.
- **Aggressive — suppressed-arrival doctrine (NEW, Step 4-adjacent).**
The only take in 3000 turns was accidental drift (BUILD refused +
no orders → last target walks in) after the viability gate correctly
refused. Gap: an arrival whose BUILD is suppressed needs an explicit
decision (besiege / leave / capture by waiting), never silence.
- **Turtle — no mission, no train (extends picket item).** Four
peace-trains at 2600 → four static armies (score-neutral, zero
optionality). Peace bar must require a mission (picket/recycle/
counter-raid) or hold the pop compounding.
- **Pro — recon still owed (strengthened).** Won by doing nothing;
blind in any contact game. Unchanged item, new exhibit.
- **Methods — load noise.** Same tree+map scored 3086 and 3136 across
two regens (one clock-driven missed order, −50 downstream). Judge
tables with margin; run benches quiet.

## Metrics (read every bench as these, not just score)

- Voluntary equal-number engagements → 0 (parse battles for force counts).
- +1 ratio: fraction of our battles fought with strict superiority.
- Pop-spent-per-enemy-kill; army lifespan; spend efficiency (score delta
  per 1000 trained — would have caught the forecast failure a scenario
  earlier).
- Rematch timelines (who trained when, who died how) diffed against the
  last analysis, read as a trade ledger.
- Muster discipline: takes at N ≥ S+W+1, defenses at N/N+1/0 (no
  partials), mutuals split by role (town-save / attrition / setup).

## Scoreboard to beat (current tree, fog era)

Fast: raid_hold 4658 / recycle 6083 / skip_thin 3888 / settle 3122 /
chain 5327 / guard 2631 / viable 5251 / pair 5798 / trap 5494 /
defend 2904 (400t, pickets) / wake 2121 / cluster 5465 / opening 5251 /
defense 1115 (honest mutuals; concentration filed) / endgame 7708
(strikes take; filed mass next). Strategic: attrition 9411 (close
Red-Queen win) / comeback 821 / endurance 6256 / outsettle 2827 /
guard_duty 5227 (war-era, wobbles) / longpeace 4191 / opening 1391 /
siege 5008 / snowball 6096 / staleness 5470 / succession 1826 /
void_contact 5711 (take, wobbles); self-play symmetric;
Elo all-draws ~1500 (needs contact-timing to discriminate).
empty_3000: pro 6263 / greedy 5688 / aggressive 3089 / expander 5200 /
turtle 2297 (equilibrium-tight, zero battles; sloshes ±2000 — judge
mechanisms + suites, not empty-points).
Next in order: ALL plan Steps substantially DONE (2 all-five, 3 meeting,
4 compositional, 5 hopeless/evac/snipe/guards, 6 buzzer/strikes; recon +
pickets shipped). REMAIN filed-futures (see Steps + GTO s12 + worklog).
(Exam 23/23 all green.)
