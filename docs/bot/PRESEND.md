# Pre-send (order-latency exploit)

## Engine mechanics (read from step.py/runner/main.py, 2026-09-14)
- Messengers carry orders at `info_speed` (150km/turn) over a PURE DISTANCE
  countdown (`remaining_dist -= info_speed`). No chasing: delivery is
  `remaining <= 0` regardless of army movement.
- `remaining` is set at SEND time = dist(capital, from-pos).
- Delivery effects:
  - `MOVE_TO` OVERWRITES `army.target` (last-wins; diverts marching armies).
  - `BUILD` requires the army EXACTLY on (bx,by) at delivery, else DROPPED
    (no queue, no retry; costs nothing).
  - Phase order per turn: command -> propagation (deliver) -> movement.
- Consequence: a pre-sent BUILD can never execute before the army lands
  (delivery precedes movement), but CAN execute the same turn the bot
  observes arrival, saving the observe+messenger round trip (~2 turns/leg).
- Dropped pre-sends are free (self-correcting: retry next turn).

## Timing math
- `msg_eta = dist(capital, army_pos) / 150`, `army_eta = dist(army, site) / 50`.
- Fire pre-send BUILD when `army_eta <= msg_eta + 1` (messenger lands with us).
- Only for armies already en route to a known site (target match <= 10km).

## Design (v1, pioneers)
- In mission loop, before normal mission: for each busy (non-idle) own army
  with a noted target near a planned site, if eta-condition holds, emit
  `BUILD army site size` INSTEAD of nothing (busy armies get no orders today).
- No state: recomputed per turn from notes+positions (stale-safe).
- Expected: pioneer cadence +30% (~2 turns/leg), peace-score 725 -> 730+.

## Risks
- Stale positions mis-time sends (free drops, retry; bounded waste = zero).
- `should_yield` cost (one dist-check per busy army; trivial).

## Forward-capital (ASSESSED 2026-09-14, skipped)
MOVE_CAPITAL: size capped 10% (600->60 viceroy), old capital demoted AT
LAUNCH (capital-less flight = elimination risk if viceroy dies), founds
54-town on arrival. Net -6 mouths + risk for -1 turn/leg latency. MARGINAL.
Verdict: skip (peace-meta doesn't pay for latency; wars are rare).
