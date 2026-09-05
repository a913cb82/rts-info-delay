# Bot-error indicators (self-diagnosis playbook)

Every pattern users flagged as "indicative of bad bot behavior", with
thresholds, tools, and meanings. Run `--format health` first (all in
one command); drill down with the listed tools.

## 1. Onesies (`autopsy`, health)

>=3 losses, one faction, one town. Means: suicide raids (blind floor
fail), remuster races (W=0 vs printers), re-fed assaults (no blood),
fratricides (stale-mirror flips). Healthy: 0. Watch: 1-2 (fast flips
unknowable). Sick: >2.

## 2. Idle armies (`report`, health)

Static >100t with 0 battles. Means: note-locks (held with nothing
wanting/releasing), parking lots (arrived patrols freeze), print-
patrol-print treadmills, pack-train stalls. Healthy: ~0-3. Every
body works every turn (guards noted home, leftovers micro-patrol).

## 3. Churn (`report`: km/army/100t)

March speed 50/t = 5000/100t. War mobility runs 100-500 WITH takes.
Takes-less motion >100 sustained = shuttling (pendulum/alternation/
redeploys — see breaker). Patrol spirals read high per-scout; judge
per-faction with takes context.

## 4. Pure 1v1s (health)

Exactly-2-combatant battles. Field ones (both die, nothing saved) =
scout-meetings (bend hops off foe armies) or 1v1 chases (need 2v1).
Town 1v1 mutuals (guard dies, town lives) are CORRECT (N-for-N saves
rich towns) — not errors. Healthy: ~0 field.

## 5. Mover-dies suicides (health)

Loser moved last (arrived into death). Pack-scale version: failed
assaults (all attackers die, town lives) = stale-S underestimates +
defeat-in-detail (sync!) + unseen re-feeds (attempt-cap!). Healthy: 0.

## 6. Quiet windows (health: 500t blocks, no found/cap, rivals alive)

Means: demand desert (nothing wants prints), dark (no sel), verify
freeze (stale + verify = peace), endgame done (one empire left —
correct quiet). Investigate every quiet block with rivals alive:
fog (did they see?), lead (who led?), flip (what broke?).

## 7. Train-deaths (health)

army_spawn + town_death same town within 2 turns, no battle. Bot
error, always: overtrain past floors (bare-convert vs transit!),
mutual-save misjudgment. Healthy: 0.

## 8. Lead flips (`lead`, `flip`)

Not errors per se — analyse what the loser did wrong / winner did
right (thin sprawl? naked towns? first-packer vs guarded sprawl?).
Every flip gets a flip-window audit.

## 9. Punishable (`report`)

Final state: foe town, 0 garrison, idle foe stack <300km. Means:
packs never formed (notes? verify? support?). Healthy: none.

## Verdicts (health)

- healthy: none of the above fire.
- watch: 1v1s >10, any onesies/quiet blocks.
- SICK: any suicides/train-deaths, onesies >2, quiet blocks >6.
