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
