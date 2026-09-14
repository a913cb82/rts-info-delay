# Rank-aware (tournament-optimal modes)

## Thesis
- Score is RELATIVE (highest at t10000 wins). Absolute 726 means nothing;
  rank means everything. No bot plays its standing.
- Leader (rank 1): variance is the enemy (any gamble can only lose the lead).
  Turtle-up (no raids, no far-pioneers, consolidate, muster-cheap).
- Trailer (rank 3+): variance is the friend (safe play locks the loss).
  Gamble (raid, blitz, long-shots; high-variance steals).
- Middle: play the leader (deny its feeders? no -- just out-compound).
- Standings are COMPUTABLE from the mirror (all towns/armies visible:
  sum pops+sizes per faction). Free intel, always fresh-ish (150km sight
  + mail lag; good enough for mode-switching with hysteresis).
- Falsifiable (quiet!): rank-aware vs v6-league (wins more? places higher?).

## Design (ranks-1)
- Compute faction scores each turn (mirror sums); rank self.
- Lead (rank1, margin>50): disable raids/vampires/long-pioneers (>100km);
  extra muster-margin (+20 need); no 700+ pack-trains (stand down).
- Trail (rank>=3, deficit>100): force raids (lower prize-gate to 100,
  muster-blind need); long-pioneers allowed; assembly from 400+ towns.
- Hysteresis: mode changes at most every 500 turns (no flapping).
