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

**Step 0 — housekeeping.** Commit the engine batch; re-baseline both suites
under delayed intel as the binding table (campaign numbers are
instant-intel era); bisect engine attribution only if the re-baseline
looks wrong. No new doctrine until measurement is honest.

**Step 1 — survive floor.** No TRAIN may leave a town below the death
floor unless last-stand-doomed (turtle's relaxed 1200-trains still
suicide today). Smallest open fix; owed.

**Step 2 — demand-gated trains.** Keep affordability floors exactly as
coded; add demand per personality before any TRAIN: raiders (viable
target in march range, or inbound to answer), expander (towns above band
without a builder en route), turtle (inbound/threatened, or missing
picket). Kills the wasteful-distant-train class the forecast episode
exposed. Bench test: conquest scenarios stop bleeding −500 cycles; quiet
scenarios hoard identically.

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
settler-hunting (kill unescorted movers when nothing is worth taking);
buffer-settling toward spent foes (turtle-true offense).

**Step 6 — siege craft (pro, last).** Engineered 2v1 *at the town* via
staggered computed arrivals; takes in symmetric endgames; anti-standoff
play (recognize compounding races, be the first to add the second army).

Explicitly parked: crowding-weapon colonies (weak math), escorts
(messenger lag wins), per-faction sent-tracking for landing fog
(machinery disproportionate to need), TRAIN pre-capture quirk exploits
(engine smell, not doctrine).

## Metrics (read every bench as these, not just score)

- Voluntary equal-number engagements → 0 (parse battles for force counts).
- +1 ratio: fraction of our battles fought with strict superiority.
- Pop-spent-per-enemy-kill; army lifespan; spend efficiency (score delta
  per 1000 trained — would have caught the forecast failure a scenario
  earlier).
- Rematch timelines (who trained when, who died how) diffed against the
  last analysis, read as a trade ledger.

## Scoreboard to beat (current tree, delayed-intel era)

Fast: raid_hold 3173 / recycle 4086 / skip_thin 3467 / settle 2114 /
chain 4319 / guard 1624 / viable 3768 / pair 4303 / trap 4040 /
defend 1109 / wake 0 / cluster 2182 / opening 4316 / defense 0 /
endgame 4928. Slow/elo: unrestored since the campaign — Step 0 covers it.
First milestones: wake alive and defense holding again (both lapsed in
the intel transition), endgame 4928 intact.
