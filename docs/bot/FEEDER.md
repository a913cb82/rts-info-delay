# Feeder (capital-compound maximization)

## Finding (2026-09-14, trace v6weak)
v6 scores 726 with FOUR towns and ZERO armies at t9000. It barely expands
(~3 foundings/10k turns). The 725-pack are capital-compounders: the
~570 capital does the work; colonies are capital-feeders (trade flows
uphill to the bigger town), not territory.
- idle (0 foundings): 608. v6 (3): 726. fission (many): 672.
- Optimum foundings ~= few (2-4): each pioneer is -30 capital, each feeder
  pays back via uphill trade. Too many = drain (fission-672); zero = 608.
- Territory is garnish; capital-compound is the game.

## Design (feeder-cap)
- Cap lifetime foundings (e.g. 3): pioneers only until cap, then pure
  compound (+ boosts to feeders so they feed back harder).
- Falsifiable in league: feeder-3 vs v6 (fewer==better? more==worse?).
- Risk: cap too low (608-trap); cap too high (fission-drain). Sweep 2/3/5.
