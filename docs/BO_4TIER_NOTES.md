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

BO#2 top-4: 4-tier +0.885 > 2-tier +0.859 > 3-tier +0.854 > 2-tier +0.806.
Used 2/10 BO runs.

## Cheap rounds (1M, max-push, cold unless noted)

Geometry grid (chef size × spacing × regional), 18 cells: fewer/smaller
chefs win monotonically; 8k-chefs starve; regional 20k > 12k always.
Best cell: 7×3000@80 + 20k (+0.833 cold, +0.875 settled).

Refinements: bourgs 500 (+0.844) > 600 (+0.833) > 750 (+0.801) >
1000 (+0.739) — monotone smaller; chefs flat 72–88km; regional peaks
~20–25k (15k falls to +0.790); bourg spacing 16/18/20 flat; bourg 400
(+0.849) best-tested, still falling — floor not yet found.

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

## Next

- BO#3: reseed around BO#2 winner (bourgs 400–600, chefs 2.5–3.5k@70–90,
  regional 12–25k) to find the bourg floor and chef size.
- 100k transfer check of any new sizes.
- Longer extend of the winning log if B3 agrees.
