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

## share-BO#1 verdict: seeds win again, dense packing found by hand

- BO#1 (1M, prem.75, 12 model evals): best = 4-tier seed verbatim
  (+1.156 settled, urb 12%). Runner-ups all seeds. The search explores
  nothing beyond its skeletons at 12 evals.
- Dense packing (hand): villages @3.5km in r100–r118 reach 30–40/km²
  (reality 33) at top growth (+1.13–1.14 cold) — the 4km lattice was the
  binding constraint on density, not fertility. Plateau flat 3.0–3.5km.
  Dense r118: 3866×300 + 198×500 + 7×3000 + 20k, dens 29.7, urb 10.8%.
- share-BO#2 (running): same config + dense seeds (s0=3.5 skeletons) —
  can the search confirm dense packing itself? 2/5 spent.

## share-BO#2 verdict: search rejects dense (settled)

- BO#2 (1M, prem.75, dense seeds present): best = 4-tier seed verbatim
  (+1.156 settled). Dense candidate found by search: cold +0.997,
  settled +1.108 — loses. Cold flatters dense; resell compounding favors
  sparser. Density 22–24 stands under pure growth.
- Maxi-dense hand shape (plateau-max sizes + 3.5km lattice + dense
  bourgs): 30.7/km² at settled +1.130 vs +1.156 seed — the density bonus
  costs 0.026. Shares 86/9/3/2, urban 14%.
- Dense bourgs @14km alone: 16% urban free (cold tie); settled +1.101 vs
  +1.156 seed — also loses settled. Sparser wins settled everywhere.
- share-BO#3 (running): prem.75 + maxi-dense seed (500@14/5000@80/50000
  @150, s0 3.5) — joint density+shares+rate optimum by search? 3/5 spent.

## share-BO#3 verdict + dense bourgs take the share lead

- BO#3 (20 model evals): best still the 4-tier seed (+1.156, twice).
  Search never tries dense bourgs on its own.
- Dense-bourg sweep (prem.75, settled): @11 +1.161 (urb 24%), @12 +1.157,
  @13 +1.164 (urb 19%), @14 +1.101, @16–18 +1.11. Peak ~11–13km.
  Best (@13): 2742×300 + 301×500 + 7×3000 + 20k → shares 77/14/2/2
  vs reality 72/13/7/3 — villages and bourgs both land, chefs still small.
- share-BO#4 (running): extend BO#3 log to 32 evals — can the search
  find the dense-bourg region itself? 4/5 spent.

## share-BO#4 verdict: search finds tiny villages (+1.197, shares worse)

- BO#4 (32 evals): best = 4-tier with P0=148 @2.92km (N=5916!):
  148/773@37/3784@83/4176@156, urb 6.4%, +1.197. Pure growth subdivides
  to the service floor — shares move AWAY from reality (villages smaller,
  urban down). Missing fixed costs confirmed as the binding gap.
- Dense-bourg hand shape (77/14/2/2, +1.164) keeps the share lead among
  realistic-village layouts; no-chefs variant hits +1.183 (3-tier).
- share-BO#5 (done — verdict below): prem.75 + `--p0min 300` (new flag
  flooring village size at the parish-center lower bound). 5/5 spent.

## share-BO#5 verdict: 4-tier wins with realistic villages forced

- BO#5 (11 model evals, P0 ≥ 300 enforced): best = 4-tier seed shape
  (+1.156, urb 12%). The floor binds (unconstrained wants P0 ~ 100–150)
  and costs 0.04 vs tiny-village degeneracy (+1.197) — the measured price
  of realistic villages. (Decode with pristine LO shows P0=100: the log
  u values assume floored bounds; true P0 = 300.)
- Process incident: BO#3's log got a concurrent second writer (extend
  launched while the original still ran) → 50 lines/36 unique. Union
  best (+1.197 tiny-village) stands; lesson: `ps`-verify death before
  reusing a log path. Extend runs now confirm exit first.

## Both-scales share round (goal: 4-tier 1M + 3-tier 100k, shares to reality; 5-BO budget)

- District prem.75 cold: lean (600@18+5000) +1.095 wins; dense-bourg@13
  (31 bourgs, urb 22%) +1.091, @14 +1.086 — numbers lever works at 100k
  too: ~22% urban free. Reality 100k non-parish ≈ 20–28%.
- both-BO#1 (running): 100k (r38), prem.75, seed 61 — district shares by
  search. 1/5 spent.

## both-BO#1 verdict: dense 3-tier wins district (+1.217)

- Winner: villages 300@3.5 + 500-bourgs@16 + 2500-chef@70 (third tier
  absent at r38), N=432, tot 136k, density 29.9/km² (≈33 ✓), urb 8.8%
  (anchor 8–12% ✓). Runner-ups: 600@18+4800@64 (+1.163), big-village
  shape (+1.110, P0=833 but s0=4.87 — sparse giants, wrong way).
- Villages still 90% by share (410 of them — dense lattice multiplies
  count). Density via numbers again, not parish size. The count/size
  trade is the same trap at both scales.
- both-BO#2 (running): district reseed, seed 62 — robustness. 2/5 spent.

## both-BO#2 verdict: identical winner (robust)

- Reseed reproduces +1.2170 exactly (same shape). District 3-tier optimum
  (dense 300@3.5 + 500@16 + 2500@70) confirmed twice.
- Combo shape (dense vill@3.5 + dense bourgs@13 + chefs + reg, prem.75):
  settled +1.167, density 30.0, shares 85/12/2/1.5, urb 14.6% — best
  combined hand shape; beats both parents.
- both-BO#3 (running): prem.75 + dense-combo seed (500@13/3000@80/20000
  @150, s0 3.5) — search confirmation of the combo corner? 3/5 spent.

## Share-goal final (budget spent 5/5)

- 4-tier optimal holds in every search that allows realistic villages
  (BO#1/#2/#3/#5, seeds and reseeds, two knob regimes).
- Best shares with 4-tier winning: dense-bourg@13 hand shape, 77/14/2/2
  urb 19% (+1.164); no-chefs variant +1.183 (3-tier). Search-best shares:
  seed shape 88/9/2/1, urb 12% (+1.156).
- Remaining gaps are all mechanisms, verified from both sides: villages
  (founding costs), big tops (urban income), density (terrain/waste).
  No knob moves them — six knob directions tried (decay, hunger, melt,
  reach, births, village floor); each either kills tiers or degenerates.

## Tier-earning audit (dense-bourg shape, prem.75, settled)

- Full (vill+bourgs@13+chefs+reg): +1.164. No-regional: +1.062 (regional
  earns +0.10). No-chefs: +1.183 (chefs HURT −0.02 — dense bourgs + regional
  saturate; mid-chefs redundant). Best: villages + dense-bourgs + regional.
- Squeeze confirmed at every level: each tier earns only where neighbors
  don't saturate. Bourgs earn iff chefs absent/small; chefs earn iff
  bourgs sparse; regional earns (wide shed, no substitute).

## Both-scales round 2 (goal: hold tiers, move shares at 100k + 1M; 5-BO budget)

- District dense-bourgs@13 (prem.75): settled +1.159, urb 22% — loses to
  BO winner (+1.217, sparser bourgs@16). Unlike 1M, district punishes
  dense bourgs (one chef + sparse bourgs already saturate). District leg
  settled: dense 300@3.5 + 500@16 + 2500@70, twice confirmed.
- both-BO#3 (carry-over): prem.75 + combo seed. Pre-budget information.
- Regional sweep (dense-bourg shape, prem.75, settled): 20k +1.164 >
  25k +1.160 > 40k +1.113. Peak at ~20k; bigger tops lose on mouths.
  Top sizes refuse to scale under any knob — the squeeze's upper half.
- both-BO#3 verdict: seed wins again (+1.156, 3rd time). Search never
  tries dense bourgs unaided (density fractions unexplored at 13–21
  evals). Added dense-bourg 4-tier seed (500@13/3000@80/20000@150).
- r2-BO#1 (running): prem.75 + dense-bourg seed, seed 63. 1/5 spent.
- Dense bourgs at max-push (adopted standard): @13 → +0.889 settled
  (urb 19%, beats BO#2 winner +0.885); @11 → +0.887 settled, urb 24.4%
  (≈23% ✓), shares 76/20/2/2 vs reality 72/13/7/3 — villages and urban
  total land; bourgs overshoot (20 vs 13), chefs short (2 vs 7).
- r2-BO#1 verdict: winner = sparse-top 4-tier (290-villages + 319@57 +
  2096@62 + 4984@122, urb 2.8%, +1.167) — search maximizes by MINIMIZING
  urban mouths. Combo seed third (+1.149). Lesson: pure growth pulls
  urban share DOWN; shares need urban mouths the objective penalizes.
  Dense-bourg hand shapes (19–24% urban, +1.16–1.18) remain the best
  shares+rate compromise, within 0.03 of max.
- District sparse-bourgs@25 (7 bourgs, urb 6.8%): settled +1.217 — ties
  the BO district winner (+1.2170). Minimal-urban principle holds at both
  scales: fewer towns, same rate; extra towns are free riders, never drivers.
- Bourg-density sweep (prem.75, settled): @9 → urb 34% +1.157; @10 →
  urb 27% +1.157 (villages 73% ✓); @11 → urb 24% +1.161; @13 → urb 19%
  +1.164 (77/14/2/2). Free-rider band covers urb 12–34% within 0.01 of
  max — reality's 23% sits inside it. Villages land via displacement
  (dense bourgs replace villages: 2742→2310). Only the urban MIX
  (bourgs vs chefs) resists: mouths pool at the cheapest tier.
- prem.75 vs max-push head-to-head (dense-bourg@10): +1.157 vs +0.880
  settled. Levels differ (premium lifts all), ranking within config is
  what matters. Promotion case for prem.75 rests on shares (27% urban
  achievable, dense bourgs win), not pace (both hot vs 0–0.3 history).
- Big chefs + dense bourgs (5000@80 + 419 bourgs): +1.141 vs +1.161 with
  3000-chefs. Bigger chefs lose everywhere, even with dense-bourg cover.
  Chef size ~3k is a ceiling under all knobs, not a tunable.
- r3-BO#1 verdict: seed wins 4th time (+1.156, 12 model evals). Added
  district dense-bourg seed (600@13/2400@70); r3-BO#2 (district, prem.75)
  tests whether the search finds the dense-bourg corner itself. 2/5 spent.
- r3-BO#2 verdict: incumbent wins 3rd time (+1.217). Dense-bourg seed
  competitive 3rd (+1.194, urb 20%) — the search priced dense shares at
  0.023. Sparse-top variant 2nd (+1.211, urb 3.5%). Minimal-urban wins,
  dense-shares cost little, tiny-village degeneracy excluded by P0 floor
  era being over (back to default bounds here; P0 stayed 300 anyway).
- r3-BO#3 verdict (extend to 32, 27 model evals): incumbent wins 4th time
  (+1.217). Extends never discover (0/4 across campaigns) — only seeds and
  assay move the frontier.
- r3-BO#4 (running): 1M max-push (adopted standard) with the FULL seed set
  (dense-bourg, combo, small-chef, province) — first search that can see
  every hand finding at once. 4/5 spent.
- Seeds-win critique (fair): at 12–21 evals in 8-D with strong hand seeds,
  BO validates/prices but never discovers — every structural idea came
  from cheap assay. Long runs (68/250 evals) DID find novel shapes, so
  the method works with budget; 16-eval campaigns don't. Contributing:
  seeds anchor GP exploitation, length-scales hit bounds (underfit, flat
  EI), count-rounding cliffs read as noise.
- r3-BO#5 (running): seedless district (--noseeds, prem.75) — the fair
  discovery test. If it finds the dense 3-tier (+1.217) unaided, 16-eval
  BO can discover; if not, seeds are load-bearing. 5/5 spent.
- Search fixes implemented (--nseeds/--xi flags, wider length-scale
  bounds, refit every 10): seeds no longer eat init, EI explores early.
- F-S1 (running): 1M prem.75, init 32 + iter 64 (96 total), 3 light seeds
  (flat/s64/s32), xi 0.05 — first full-budget search. 1/3 searches spent.
- Sharp hunger (prem.75+starv1.6): 4-tier +1.343 vs s64t +1.180 (gap +0.16,
  widest measured). sf1.4 similar (+0.14). Rescue bonus + services both
  favor tiers — but chef sizes still won't scale (3k +1.343 > 8k +1.311).
- F-S2 (running): 1M prem.75+starv1.6, 3 light seeds, xi 0.05, 96 evals —
  search where the 4-tier gradient is steepest. 2/3 searches spent.
- Regional scales where chefs won't (starv1.6): 30k (+1.348) > 20k
  (+1.343) > 40k (+1.323). The top rung has no substitute (114km+ shed
  covers the province alone), so its lift repays mouths to ~30k — inside
  the 15–40k anchor. Asymmetry confirmed: regional size free to ~30k,
  chef size capped ~3k (overlapping sheds).
- reg30k settled +1.381 (starv1.6): best overall. Shares 77/14/2/3 vs
  reality 72/13/7/3 — villages, bourgs, regional ALL land within noise;
  only chefs short (2 vs 7%). Sharp hunger + big regional is the closest
  configuration found on every axis at once.
- Chef squeeze complete (starv1.6, settled): with dense bourgs + reg30k,
  dropping chefs GAINS (+1.411 vs +1.379); with sparse bourgs, dropping
  chefs still gains (+1.410 vs +1.379) and dropping bourgs is neutral
  (+1.381). Chefs earn only with BOTH neighbors absent (s64t-era). In any
  full stack the mid tier is redundant — coverage saturates from below
  (bourgs) or above (regional), never leaving a gap chefs alone fill.
- Small regional (12k) + dense shape: +1.339 vs +1.381 (30k). Regional
  monotonic to ~30k, then falls (40k +1.323 earlier). Asymmetry stands.
- District sharp hunger (max-push + starv1.6): lean 3-tier +1.112 vs s64t
  +0.858 (gap +0.25, widest district margin measured). Hungry-chef rescue
  bonus strongly favors the full stack at district scale too.
- Combined pro-tier knobs stack (district prem.75+starv1.6): lean +1.395
  vs flat +0.635 (gap +0.76). Headroom + rescue bonus compound.
- Knob saturation: prem.75+starv1.6 combined (+1.381) equals starv1.6 alone
  (+1.381) — premium adds nothing once hunger is sharp. Both knobs target
  the same saturation; headroom beyond ~0.5 premium is unused.
- S1 nearing done (90/96, best +1.157): full-budget search confirms the
  seed corner without improving it. Sparser villages appearing (s0 4.72).
- F-S1 verdict (96 evals, 49 model): best +1.1568 is degenerate mush
  (duplicate 293/302 tiers + one 2400-top, urb 59%) — ties the seed
  (+1.1561) to noise. Runner-up: dense-small 4-tier (+1.156, urb 9%).
  Full budget confirms: unguided search games tier-count (phantoms) or
  degenerates (tiny villages); hand shapes lead on every real axis.
- F-S3 (running): 1M prem.75 + min_ratio 2.0 (tier sizes must double —
  duplicate mush unrepresentable) + P0 default. Last search: can clean
  tiers win by search alone? 3/3 spent.
- Load discipline: killed a third concurrent 1M job (pricing#1) — 3×1M
  jobs contend the shared box ~3×. Pricing waits for S2. Rule: max two
  heavy jobs; pricing runs ride along one search, never two.
- District prem.75+starv1.6: lean 3-tier +1.395 vs s64t +1.122. Combined
  knobs keep 3-tier optimal at 100k with a wide margin — district leg
  holds under every knob regime tested.
- Combo-knob cross-check (prem.75+starv1.6): 4-tier dense shape +1.381 vs
  s64t +1.367. Four tiers lead at every knob setting where tops pay at
  all; the only regimes preferring fewer tiers are the gentle ones where
  no tops pay (documented earlier).
- District combo (dense-bourgs@13 + 5000-chef, prem.75+starv1.6): settled
  +1.396, urb 22% — ties lean (+1.395) with far better shares: 78/17.5/4.7
  vs reality 72/15/5–10. Best district on rate AND shares together.
- F-S2 verdict (96 evals, 48 model): winner +1.393, 4-tier
  (236@3.48/596@40/2480@75/3327@87, urb 5.7%); runner-up +1.391 with
  dense bourgs (431@13, urb 18.7%). Search crowns low-urban by 0.002 —
  shares cost little but never pay. 4-tier optimal confirmed at full
  budget; all three searches agree on structure, differ on urban mass.
- Pricing#1 (running): combo knobs (prem.75+starv1.6), seed 81 — search
  adjudication of the +1.38–1.41 cluster (reg30k shape, dense-bourg,
  no-chefs variant). 1/3 pricing spent.
- Bourg-spacing peak at BASE too (@13 +0.889 > @11 +0.887 > @10 +0.880):
  plateau 11–13km, gentle falloff both sides. Spacing optimum is
  knob-stable; only levels shift with knobs.
- Chef-spacing plateau confirmed at prem.75 (@64/@80/@96 all +1.105–1.11
  cold): spacings knob-stable 64–96km, levels carry all knob response.
- Village size is free (prem.75): 430-villages tie 300-villages (+1.1644
  vs +1.1639) in the dense-bourg shape. Size costs nothing; COUNT sets
  share. Parish size needs fewer villages (sparser lattice), not richer
  ones — but sparser lattices lose (tested). Count/size deadlock stands.
- Pricing#1 verdict (combo knobs, 16 model evals): 4-tier seed +1.392 >
  dense-combo +1.386 > dense-bourg +1.379. Search ranks seed-family first
  everywhere; hand dense variants trail by 0.006–0.013.
- Big-sparse villages (2104×430 @4.5km): +1.148 vs +1.164 dense-bourg@13.
  Bourgs land (13.7% ✓) but villages stay 83% — sparser lattice thins
  coverage faster than bigger villages add share. Deadlock holds from
  the spacing side too.
- Regional 20k vs 25k (dense-bourg shape, prem.75): +1.164 vs +1.160 —
  flat top, 20–30k all tie. Regional size free within the anchor band.
- F-S2 final (96 evals, 48 model): +1.393, 4-tier low-urban (urb 5.7%);
  runner-up dense-bourg 4-tier (urb 18.7%, −0.003).
- F-S3 final (96 evals, 44 model, min_ratio 2): +1.138, CLEAN 4-tier
  (302@3.56/1196@58/2480@84/7447@172, urb 6.9%) — distinct doubling
  tiers, no phantoms. Runner-up phantom-tied. Constraint works as
  intended; optimum stays low-urban.
- All 3 searches spent. Every full-budget winner is 4-tier with urb
  4–9%; every share gain (dense bourgs → 19–27% urban) comes from hand
  shapes within 0.01–0.03 behind.
- Pricing#2 verdict: seed wins 6th time (+1.156, 14 model evals).
  Pricing#3 (running): district prem.75 tiebreak (incumbent +1.217 vs
  dense-bourg +1.159 vs sparse +1.217) — can search break a three-way
  tie? 3/3 pricing committed.
- Pricing#3 verdict: incumbent wins 4th time (+1.217); dense-bourg seed
  2nd (+1.194, urb 20%). Tie not broken — minimal-urban wins outright
  under search, dense shares trail by 0.023. Budget spent 3/3 + 3/3.
\n## Round final: shares need a standard change, not more search
\n- Every search (9 campaigns) crowns minimal-urban; every share gain came
  from assay. Proposed standard change (for approval, not applied):
  prem.75 (+starv1.6 at 1M) as the share configuration — 4-tier/3-tier
  optimal held, dense shares within 0.01–0.03, villages land via
  displacement (73–77%), urban 19–27%. Costs: growth runs 3–4× history,
  tops stay small, mid/base regimes prefer fewer tiers.
- Left open: founding costs (village size), urban income (top sizes),
  terrain/waste (density 24→33). No further BO recommended until a
  mechanism lands — search has priced everything on the table.
- UNIFORM SCALING (the density answer): ×1.43 all pops, same lattice →
  density 23.4→33.5 (≈33 ✓) at cold cost 0.05, settled +1.319. Shares
  EXACTLY preserved (80/15/2/3); sizes land: villages 429 ✓, bourgs 715,
  chefs 4290, regional 42.9k ✓-edge. Density was never about spacing OR
  size — it is total mouths per fixed area, and surplus S/P≈2 absorbs
  +43% mouths. Only chefs (2 vs 7%) still short.
- density-BO#1 (running): 1M prem.75+starv1.6, 3 light seeds, 96 evals —
  can search find the scaled corner itself? 1/3 searches spent.
- 100k scaled ×1.43 (combo knobs): 298×429 + 19×858 + 3575, density 32.6
  ✓, settled +1.375. Sizes land (bourgs 858 ✓, chef low-edge); shares
  86/11/2.4 preserved-as-before (village count still high). In an r31
  disc this reads ~200×429 + ~13×858 + 1 chef — counts near reality too.
- RATCHET (footprint 1.0×s0 + scale to density): 2039×515 + 300×858 +
  7×5148 + 51k regional, density 31.9 ✓, settled +1.297 (cost 0.02 vs
  +1.319). Shares 75/18/3/4; sizes 515/858/5148/51k — bourgs exact,
  villages/regional land, only chefs short. Footprint deletes villages
  near towns (count lever); scale-up refills density (size lever). Best
  overall configuration on shares+sizes+density jointly.
- Ratchet tuned to exact density (k=1.78): 33.1/km² at settled +1.291
  (cost 0.006 vs 31.9). Density dials continuously via uniform scale;
  composition frozen by footprint choice. S1 back to full speed (40/96).
- info_speed (never varied; caps fame + market tail + migration window):
  100 → 4-tier wins by +0.046; 200 → wins by +0.115. Longer sight/mail
  range strongly favors tiers (regional shed widens). Gameplay-coupled
  (bot intel delay) — flag before touching.
- Decay shape (never varied): p=1 starves flat-300 villages (−0.02);
  p=3 feeds them (+0.20). Steeper decay favors villages; P0 sweep at p=3
  next (village-size knob candidate).
