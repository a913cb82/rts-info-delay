# Bot plan — doctrine and open work

What we believe about playing well, and what remains to build, in order.
State of the bots: `BOTS.md`. Numbers: `BOT_BENCH.md`. History: `BOT_WORKLOG.md`.

## Doctrine (settled)

1. **+1 or nothing.** Equal numbers annihilate (1v1 *and* 2v2); any strict
   outnumbering kills clean. Never willingly enter an equal fight.
2. **Trade evaluator.** Every march-or-hold decision answers: when these
   paths meet, do I strictly outnumber? Outnumber → take it. Equal →
   decline (free and unilateral — both declining is just peace, which
   favors whoever compounds faster) or convert (add one: train, recall,
   viceroy). Outnumbered → be elsewhere. Armies are 1000 pop that
   compounds; ground re-settles.
3. **Last responsible moment.** All lags are known (intel + messenger ≈
   2× one-way per decision), so compute the latest turn you can act and
   wait for it. Early reactions bleed production and chase ghosts.
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
7. **Capitals are the only irreplaceable asset.** Losing one blinds you
   permanently; taking one blinds the enemy permanently. Snipe theirs,
   never risk your last.

## Open work, in order

**Step 0 — housekeeping.** DONE (fog era): EVENT_REWORK landed, both
suites re-baselined as the binding table (BOT_BENCH.md fog-era section);
wake and defense fixed themselves via re-observation under S; endgame
attribution (beheading vs intel timing) left open — bisect only if it
matters for a later step.

**Step 1 — survive floor.** No TRAIN may leave a town below the death
floor unless last-stand-doomed (turtle's relaxed 1200-trains still
suicide today). Smallest open fix; owed.

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
battles for force counts to calibrate. Scouting doctrine (when to spend
an army to look) is prerequisite — first scout policy ships inside this
step, not before it.

**Step 3 — meeting forecast + computed arrival-sync.** Deterministic
meeting prediction from known speeds (path-blocking auto-intercepts, so
forecasting is enough to force field battles); release own packs on
computed coincident arrivals (perfect own-info — the arrival-sync that
can work, since the old one died on stale *foe* intel). Punish
foe 1v1-acceptance by adding one anywhere on your path.

**Step 4 — post-capture doctrine.** Assign every surviving attacker at
once: nearest viable next target in reach → found nearby → march home to
recycle. (Greedy's kill-runt-then-found was emergent; make it policy for
all raiders.) Includes garrisoning fresh conquests through their
starvation window.

**Step 5 — evac v2 + capital game.** Earlier-and-stricter evac gates
(1-turn lead now required; failure beheads permanently); viceroy routing
around known armies; leader-targeting with capital-sniping weight;
Pre-step verdict owed: Elo all-hold (20/20 defenses stand on the raid
map) — decide whether the matchup is defense-favored by mechanics (then
stop raiding it) or attacker-passive under fog (then fix the approach)
before building capital-sniping on top;
settler-hunting (kill unescorted movers when nothing is worth taking);
buffer-settling toward spent foes (turtle-true offense).

**Step 6 — siege craft (pro, last).** Engineered 2v1 *at the town* via
staggered computed arrivals; takes in symmetric endgames; anti-standoff
play (recognize compounding races, be the first to add the second army).

Explicitly parked: crowding-weapon colonies (weak math), escorts
(messenger lag wins), TRAIN pre-capture quirk exploits
(engine smell, not doctrine), counter-intel (staying out of foe sight
discs on purpose — needs the evaluator first so we know what secrecy is
worth). Retired from this list: per-faction sent-tracking for landing
fog — the rework's send-state + S + amnesia solved it in the engine.

## Metrics (read every bench as these, not just score)

- Voluntary equal-number engagements → 0 (parse battles for force counts).
- +1 ratio: fraction of our battles fought with strict superiority.
- Pop-spent-per-enemy-kill; army lifespan; spend efficiency (score delta
  per 1000 trained — would have caught the forecast failure a scenario
  earlier).
- Rematch timelines (who trained when, who died how) diffed against the
  last analysis, read as a trade ledger.

## Scoreboard to beat (current tree, fog era)

Fast: raid_hold 3066 / recycle 6052 / skip_thin 2151 / settle 3066 /
chain 5250 / guard 3088 / viable 3088 / pair 5105 / trap 3165 /
defend 3207 / wake 2121 / cluster 5465 / opening 3242 / defense 3305 /
endgame 8804. Strategic (focal pro): attrition 14552 / comeback 821 /
endurance 7752 / outsettle 2687 / guard_duty 2360 / longpeace 5254 /
opening 1391 / siege 5324 / snowball 4851 / staleness 4007 /
succession 1826; self-play symmetric; Elo all-hold. empty_3000 rematch:
pro 9156 / greedy 3089 / aggressive 3376 / expander 3376 / turtle 5232.
Next milestones in order: Step 2 stops the selectivity bleed
(skip_thin/trap/viable back up without defense regressing); Elo verdict
lands; then Steps 3–6 in sequence.
