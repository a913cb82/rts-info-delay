
## VERDICT (2026-09-14, unit-tested): near-useless, removed
Engine drops ALL pre-landing orders (MOVE needs from==1-turn-projection,
BUILD needs landed). Pre-sent MOVE-to-same-site is a no-op; pre-sent BUILD
always drops en route. The league +1 was noise. The arrival-observe gap is
structural (delivery precedes movement; observation lags a turn). Removed
from combo. Lesson: unit-test exploit foundations BEFORE rating them.
