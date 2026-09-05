# Brainstorm — ideas backlog (live)

Ranked by leverage. Shipped items move to BOT_WORKLOG + GTO addenda.
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
  headless endgame exact trade (GTO §11).
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
flip/health/churn tools, INDICATORS.md, greedy retired, double-pro.

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
