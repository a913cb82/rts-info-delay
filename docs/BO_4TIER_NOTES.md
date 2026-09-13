# 4-tier 1M hunt — experiment notes

Goal: 4 tiers optimal at 1M (villages + bourgs + chefs + regional), 3 tiers
at 100k. Method: background BO at province scale + cheap (≤20s) hand-shape
rounds in parallel; plan each BO from previous results. BO budget: 10 runs.

Settings for everything below (max-push): gamma 1.3, premium 0.5,
melt 0.005, continuous fame (10/60/150km at 1k/5k/50k). `BASE_CFG` carries
these; engine `GameConfig` defaults untouched.

## BO ledger

| run | log | config | best (settled) | verdict |
|---|---|---|---|---|
| BO#1 | `bo_win_b1` (16 evals) | max-push, old seeds | +0.859, 2-tier s64/T2400 | hand 4-tier (+0.875) unbeaten; no regional seed |
| BO#2 | `bo_win_b2` (16 evals) | max-push + 4-tier seed | **+0.885, 4-tier** 300/600@18/3000@80/12000@150, urb 12% | 4-tier confirmed by search |
| BO#3 | `bo_win_b3` (16 evals) | reseed of BO#2 | identical +0.885, same shape | robust, not seed luck |

BO#2 top-4: 4-tier +0.885 > 2-tier +0.859 > 3-tier +0.854 > 2-tier +0.806.
Used 2/10 BO runs.

## Cheap rounds (1M, max-push, cold unless noted)

Geometry grid (chef size × spacing × regional), 18 cells: fewer/smaller
chefs win monotonically; 8k-chefs starve; regional 20k > 12k always.
Best cell: 7×3000@80 + 20k (+0.833 cold, +0.875 settled).

Refinements: bourgs flat 200–500 (~+0.848 all sizes — no floor; 1000 falls
to +0.739); chefs flat 72–88km; regional peaks ~20–25k (15k falls to
+0.790); bourg spacing 16/18/20 flat. Settled: bourgs-400 +0.897 vs
no-bourgs +0.894 — the bourg tier adds +0.003: garnish, not structure.
At max-push the working tiers are villages + chefs + regional.

Knob spot-checks on winner (all keep 4-tier ahead of s32): melt .002,
hunger 1.6, carts 25km, workers 1.4, premium .6, gamma 1.4.

Rivals @1M settled: s32 uniform-mid +0.815, flat +0.32, lone giant −0.37,
13-chef province shape +0.08 (too many chefs overlap sheds).

## Incumbent 1M optimum

BO#2 winner, settled +0.885: ~3000×300 @4km + ~150×600 @18km + 7×3000
@80km + 1×12000 @150km, ~12% urban. Vs reality 1M (72/13/7/3%):
villages too many/small, bourgs small (600 vs 900), chefs small
(3k vs 8k) but counted (7 vs 9), regional small (12k vs 15–40k).

## Open tensions

- Bourgs shrink under optimization (400–600 win, reality 900) while
  centers want to be big — mid tier squeezed from both sides.
- Villages stuck ~300 (decay rewards near-field smallness); hamlets gap.
- Growth runs hot (+0.8–0.9 vs 0–0.3 recorded): tiers for pace trade-off.
- 100k keeps 3-tier lean (600@18 + 5000, +0.88 settled); tops appear only
  with countryside big enough to feed them.

| BO#3 | `bo_win_b3` (16 evals) | reseed of BO#2 | identical +0.885, same shape | robust, not seed luck |

## BO#8 verdict: 4-tier wins by search (goal met)

- BO#8 (1M, max-push, small-chef 4-tier seed, 16 model evals): winner is
  4-tier 300/600@18/3000@80/12000@150, +0.8847, ~12% urban — the same
  shape BO#2 found, now with the small-chef seed in play. Runner-up:
  2-tier sparse tops +0.859. Hand small-chef variants reach +0.91.
- 100k transfer: district chef peaks at 2500–3000 (+0.92), not 5000.
  Small tops win at both scales; only counts scale.
- GOAL MET: search gives 4-tier optimal at 1M under realistic settings
  (twice: BO#2, BO#8). Caveats stand: bourgs garnish (+0.003), tiers
  come out small, growth hot, mid/base regimes prefer fewer tiers.

## Open items (still true)

- Bourg-size gap is structural: growth flat across 200–500 and +0.003
  with vs without bourgs at max-push, while reality staffs 900s at 13%.
  Needs non-food bourg income or a service only small towns give.
- 100k transfer check of any new sizes.

## Mid-knob round (BO#4, removal tests, base-knob checks)

- BO#4 (1M, γ1.2/prem.35/melt.01): best 2-tier s64/T2400 +0.647, 4-tier
  shape second +0.631 (−0.016). Knob-sensitive, not robust there.
- Removal at mid knobs: no-bourgs +0.614 BEATS with-bourgs +0.598 —
  bourgs hurt when tops are mid-priced too.
- Few small chefs at R12 base: +0.389, loses to s16 (+0.424) and lean
  (+0.437). New 7-chef geometry at base: +0.336, loses to s64t (+0.468)
  and flat. Tops only pay under pushy knobs.
- Big sparse bourgs (1500@25, 2000@30) lose (+0.75–0.77): mouth burden
  beats coverage efficiency. Small+dense or nothing.
- BO#5 (done — verdict below): 1M mid knobs + 4-tier seed.

## BO#5 verdict + interpolation (4-tier needs max-push)

- BO#5 (1M, γ1.2/prem.35/melt.01, 4-tier seed present): s64/T2400 wins
  again (+0.647), 4-tier second. Seed presence doesn't save it — mid
  knobs genuinely prefer sparse small tops.
- Interpolation (γ1.18/prem.3/melt.012): s64t +0.566 wins; prov4 +0.476
  second; lean +0.480. Same story between base and mid.
- Persistent rival across gentle→mid: sparse small tops (13×2400@64,
  urb ~3%), minimal mouths, no bourgs needed. 4-tier wins ONLY at
  max-push (γ1.3/prem.5/melt.005), where food is cheap and headroom high.
- BO#6 (running): between mid and max-push (γ1.25/prem.4/melt.008) +
  4-tier seed — mapping the boundary where 4-tier takes over.

## BO#6 verdict: boundary holds for 4-tier (by seed + hand)

- BO#6 (1M, boundary knobs, 4-tier seed present, 13 model evals): the
  4-tier SEED wins (+0.726) over s64t (+0.716) — but the search added
  nothing beyond its seeds; hand variants nearby do better.
- Small-chef sweep at boundary: 3000 (+0.718) < 2500 (+0.727) < 2000
  (+0.734) < 1500 (+0.740) < 1200 (+0.744) < 1000 (+0.746). Monotone
  smaller; regional 20k beats 15k/25k/30k variants nearby.
- Small-chef 4-tier at mid/base knobs still loses (mid: +0.647 vs +0.652;
  base: uncompetitive). Chef-shrinking helps only where tops already pay.
- Scoreboard: 4-tier wins max-push (search ×2) and boundary (seed + hand
  variants); loses mid (−0.005…0.016) and base (badly).
- BO#7 (running): extend BO#6 log to 32 evals — can the search find the
  small-chef region itself and confirm the boundary win?

## BO#7 verdict + small chefs take the lead everywhere they pay

- BO#7 (boundary, 32 evals total): best UNCHANGED +0.726 — 16 extra evals
  confirm the 4-tier seed, add nothing. Boundary win stands (seed-held).
- Small-chef sweep at max-push: chefs 1000 (+0.909) and 1500 (+0.905)
  beat the BO#2 winner (+0.885). New incumbent: bourgs-500 + 1000-chefs@80
  + 20k regional. Tiers compress upward (300/500/1000/20000) while the
  top stays big — mouths shrink everywhere except the regional.
- BO#8 (done — verdict above): max-push + new small-chef 4-tier seed
  (500@18/1500@80/15000@150).

## Share-tuning round (goal: 72/13/7/3 with 4-tier optimal; 5-BO budget)

- Knob screens (cold, small-chef 4-tier vs s64t): 4-tier leads at prem.6
  (+0.96), prem.75 (+1.10), g1.4 (+0.84), melt.002/0 (+0.87/+0.88),
  birth.03 (+1.45). Winning everywhere cold — shares are the question.
- Chef sizes plateau, never push big: prem.75/birth.03 tie 1k–5k; g1.4
  still prefers small (1k +0.843 > 8k +0.794); g1.4+prem.75 ties 1k–5k
  (+1.10), 8k falls. No knob makes big tops strictly win: mouths cost
  linear, lift saturates.
- Urban share lever that works: NUMBERS not sizes. Bourgs @14km (252
  towns) reach 16.2% urban at zero cost (+0.843 vs +0.844 @18km).
- share-BO#1 (running): 1M, prem.75 (widest plateau), seed 51 — free to
  find counts/sizes that lift urban share. 1/5 spent.
