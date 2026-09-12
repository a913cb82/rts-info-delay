"""One-page visual summary of the fitted growth system.

Produces docs/realism_plots/realism_fit.png (16 panels):
  A. formula anatomy: one-town curve, per-capita rate, kernels,
     coexistence penalty
  B. behavior/fit: trajectories, recovery, sinkflow/hinterland,
     c-tension, K-tension, sigma identifiability, scorecard, CV
  C. strategy: growth fields (market/city), founding price map,
     directional asymmetry

Usage: python benchmarks/realism_plots.py [--quick]
"""

import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import growth_realism as gr  # noqa: E402
import candidate_growth as cg  # noqa: E402
from candidate_growth import FITTED, FITTED_VARIANT, FittedGrowth  # noqa: E402
from fit_growth import TRAIN  # noqa: E402
from growth_systems import EngineGrowth  # noqa: E402

QUICK = "--quick" in sys.argv
OUT = ROOT / "docs" / "realism_plots" / "realism_fit.png"
F = dict(FITTED)
RHO = F["rho"]


def FIT(**kw):
    return FittedGrowth({**F, **kw}, **FITTED_VARIANT)


ENG = EngineGrowth()
fig = plt.figure(figsize=(24, 25), constrained_layout=True)
gs = fig.add_gridspec(4, 4)


def P(r, c):
    return fig.add_subplot(gs[r, c])


def traj(spec, G, turns=520):
    """Run a layout; return the subject (first tower) population per week."""
    w = gr.World()
    subj = None
    for (x, y, p) in spec:
        t = gr.T(x, y, p)
        w.towns.append(t)
        if subj is None:
            subj = t.id
    hist = []
    for _ in range(turns + 1):
        cur = next((t.population for t in w.towns if t.id == subj), 0.0)
        hist.append(cur)
        if not w.towns:
            break
        G.step(w)
    while len(hist) < turns + 1:
        hist.append(0.0)
    return np.array(hist)


def pair_loss(system, dist):
    towns = [gr.T(0, 0, 10000), gr.T(dist, 0, 10000)]
    return 1 - system.nets(towns)[0] / system.isolated(10000.0)


# ---------------------------------------------------------------- row 1
a = P(0, 0)
pop = np.logspace(2, 5.2, 400)
a.plot(pop, [FIT().isolated(p) for p in pop], label="fitted")
a.plot(pop, [ENG.isolated(p) for p in pop], label="engine", alpha=0.8)
a.axhline(0, color="k", lw=0.6)
a.set_xscale("log")
a.set_title("A1  net growth of a lone town")
a.set_xlabel("population")
a.set_ylabel("pop / turn")
a.legend(fontsize=8)

a = P(0, 1)
pc_f = np.array([FIT().isolated(p) / p * 52 * 100 for p in pop])
pc_e = np.array([ENG.isolated(p) / p * 52 * 100 for p in pop])
a.plot(pop, pc_f, label="fitted")
a.plot(pop, pc_e, label="engine", alpha=0.8)
a.axhspan(0.1, 0.5, color="tab:green", alpha=0.12, label="village band")
a.axhline(0, color="k", lw=0.6)
idx = np.where(np.diff(np.sign(pc_f)))[0]
if len(idx):
    cross = pop[idx[0]]
    a.axvline(cross, color="tab:red", ls="--", lw=1)
    a.annotate(f"sink beyond {cross/1000:.0f}k", (cross, -2.4), color="tab:red",
               fontsize=8, xytext=(3, 0), textcoords="offset points")
a.set_xscale("log")
a.set_ylim(-3, 8)
a.set_title("A2  per-capita growth (%/yr)")
a.set_xlabel("population")
a.legend(fontsize=8)

a = P(0, 2)
d = np.linspace(0, 160, 500)
win = np.array([cg._win(x * x) for x in d])
a.plot(d, win, label="win(d)")
a.plot(d, np.exp(-(d / RHO) ** 2) * win, label="access kernel")
a.plot(d, np.exp(-d / RHO) * win, label="migration kernel")
a.axvline(150, color="k", ls=":", lw=1)
a.set_title("A3  distance kernels (normalised at d=0)")
a.set_xlabel("distance (km)")
a.legend(fontsize=8)

a = P(0, 3)
dd = np.linspace(10, 160, 160)
a.plot(dd, [pair_loss(FIT(), x) for x in dd], label="fitted")
a.plot(dd, [pair_loss(ENG, x) for x in dd], label="engine", alpha=0.8)
a.axvline(15, color="tab:red", ls="--", lw=1)
a.annotate("market spacing 15km", (15, 0.5), color="tab:red", fontsize=8,
           rotation=90, xytext=(3, 0), textcoords="offset points")
a.axhline(0.25, color="grey", ls=":", lw=1)
a.set_title("A4  coexistence penalty (2x10k towns)")
a.set_xlabel("distance (km)")
a.set_ylabel("fraction of isolated growth lost")
a.legend(fontsize=8)

# ---------------------------------------------------------------- row 2
a = P(1, 0)
Gf = FIT()
for p in (300, 1000, 10000, 20000, 60000):
    h = traj([(500, 500, p)], Gf)
    a.plot(np.arange(len(h)) / 52, h, label=f"{p}")
a.set_yscale("log")
a.set_title("B1  lone-town trajectories (fitted, 10y)")
a.set_xlabel("years")
a.set_ylabel("population")
a.legend(fontsize=8, title="start")

a = P(1, 1)
ring5 = [(500, 500, 5000)] + [(500 + 30 * math.cos(i * math.pi / 3),
                               500 + 30 * math.sin(i * math.pi / 3), 500) for i in range(6)]
h = traj(ring5, Gf)
a.plot(np.arange(len(h)) / 52, h, label="fitted ringed")
h = traj([(500, 500, 5000)], Gf)
a.plot(np.arange(len(h)) / 52, h, "--", label="fitted lone")
h = traj([(500, 500, 5000)], ENG)
a.plot(np.arange(len(h)) / 52, h, ":", label="engine lone")
a.axhline(10000, color="k", lw=0.6)
a.axvspan(40, 150, color="tab:green", alpha=0.10)
a.annotate("target 40-150y", (148, 10300), fontsize=8, ha="right")
a.set_title("B2  recovery: halved 5k + 6x500 ring")
a.set_xlabel("years")
a.set_ylabel("population")
a.legend(fontsize=8)

a = P(1, 2)
for p, col in ((10000, "tab:blue"), (60000, "tab:red")):
    ring = [(500, 500, p)] + [(500 + 30 * math.cos(i * math.pi / 3),
                               500 + 30 * math.sin(i * math.pi / 3), 300) for i in range(6)]
    a.plot(np.arange(521) / 52, traj(ring, Gf) / p, col, label=f"ringed {p//1000}k")
    a.plot(np.arange(521) / 52, traj([(500, 500, p)], Gf) / p, col, ls="--",
           alpha=0.6, label=f"lone {p//1000}k")
a.axhline(1.0, color="k", lw=0.6)
a.set_title("B3  fed vs starved (fitted, 10y)")
a.set_xlabel("years")
a.set_ylabel("population / initial")
a.legend(fontsize=8)


def trio(sys_):
    gr.G = sys_
    return [f()[4] for f in (gr.s5_hierarchy, gr.s8_urban, gr.s14_hinterland)]


a = P(1, 3)
cs = np.logspace(-15.5, -12.5, 9)
vals = np.array([trio(FIT(c=float(c))) for c in cs])
for j, name in enumerate(("hierarchy", "urban", "hinterland")):
    a.plot(cs, vals[:, j], "o-", label=name)
a.axvline(F["c"], color="k", ls=":", lw=1)
a.annotate("chosen c", (F["c"], 0.04), rotation=90, fontsize=8)
a.set_xscale("log")
a.set_ylim(-0.03, 1.03)
a.set_title("B4  tension vs c (urban sink strength)")
a.set_xlabel("c")
a.set_ylabel("scenario score")
a.legend(fontsize=8)

# ---------------------------------------------------------------- row 3
a = P(2, 0)
Ks = [1e5, 2e5, 3e5, 5e5, 1e6, 3e6, 1e7]
vals = np.array([trio(FIT(bfixK=float(K))) for K in Ks])
for j, name in enumerate(("hierarchy", "urban", "hinterland")):
    a.plot(Ks, vals[:, j], "o-", label=name)
a.axvline(FITTED_VARIANT["bfixK"], color="k", ls=":", lw=1)
a.annotate("chosen K", (FITTED_VARIANT["bfixK"], 0.04), rotation=90, fontsize=8)
a.set_xscale("log")
a.set_ylim(-0.03, 1.03)
a.set_title("B5  tension vs K (land cap a/b)")
a.set_xlabel("K")
a.set_ylabel("scenario score")
a.legend(fontsize=8)

a = P(2, 1)
ms = [10, 20, 30, 50, 100, 200, 500, 1000]
means = []
for m in ms:
    gr.G = FIT(mfix=float(m))
    sc = {f.__name__.split("_", 1)[1]: f()[4] for f in gr.SCENARIOS}
    means.append(sum(sc[k] for k in TRAIN) / len(TRAIN))
a.plot(ms, means, "o-")
a.axvline(30, color="k", ls=":", lw=1)
a.set_xscale("log")
a.set_ylim(min(means) - 0.01, max(means) + 0.01)
a.set_title("B6  sigma width m: flat = unidentifiable")
a.set_xlabel("m (sigmoid width, pop)")
a.set_ylabel("train mean (14)")

a = P(2, 2)
names = [f.__name__.split("_", 1)[1] for f in gr.SCENARIOS]
eng_sc = {}
for f in gr.SCENARIOS:
    gr.G = ENG
    eng_sc[f.__name__.split("_", 1)[1]] = f()[4]
gr.G = FIT()
fit_sc = {f.__name__.split("_", 1)[1]: f()[4] for f in gr.SCENARIOS}
order = sorted(names, key=lambda n: fit_sc[n])
y = np.arange(len(order))
a.barh(y + 0.2, [fit_sc[n] for n in order], height=0.38, label="fitted")
a.barh(y - 0.2, [eng_sc[n] for n in order], height=0.38, label="engine")
a.set_yticks(y)
a.set_yticklabels(order, fontsize=7)
a.set_xlim(0, 1.05)
fm = sum(fit_sc.values()) / len(fit_sc)
em = sum(eng_sc.values()) / len(eng_sc)
a.set_title(f"B7  scorecard: composite {fm:.3f} vs {em:.3f}")
a.legend(fontsize=8)

a = P(2, 3)
cv = json.loads((ROOT / "benchmarks" / "realism_fit" / "cv_curve_0.02.json").read_text())
labels = list(cv["folds"].keys())
scores = [v["score"] for v in cv["folds"].values()]
a.bar(labels, scores, color="tab:blue", alpha=0.85)
a.axhline(cv["cv"], color="k", ls="--", lw=1, label=f"CV mean {cv['cv']:.3f}")
a.axhline(fm, color="tab:red", ls=":", lw=1, label=f"in-sample {fm:.2f}")
a.set_ylim(0, 1.05)
a.set_title("B8  cross-validation (held-out per fold)")
a.set_ylabel("held-out score")
a.legend(fontsize=8)

# ---------------------------------------------------------------- row 4
def field(center_pop, grid_n=61, span=150.0, sys_=None):
    sys_ = sys_ or FIT()
    xs = np.linspace(-span, span, grid_n)
    z = np.zeros((grid_n, grid_n))
    for i, yy in enumerate(xs):
        for j, xx in enumerate(xs):
            if xx * xx + yy * yy < 4.0:
                z[i, j] = np.nan
                continue
            probe = gr.T(500 + xx, 500 + yy, 300)
            center = gr.T(500, 500, center_pop)
            z[i, j] = sys_.nets([probe, center])[0] / 300 * 52 * 100
    return z


a = P(3, 0)
z = field(2500)
im = a.imshow(z, extent=(-150, 150, -150, 150), origin="lower", cmap="viridis")
plt.colorbar(im, ax=a, shrink=0.85, label="village %/yr")
a.set_title("C1  growth field around a 2.5k market")
a.set_xlabel("km")
a.set_ylabel("km")

a = P(3, 1)
z = field(60000)
im = a.imshow(z, extent=(-150, 150, -150, 150), origin="lower", cmap="viridis")
plt.colorbar(im, ax=a, shrink=0.85, label="village %/yr")
a.set_title("C2  growth field around a 60k city")
a.set_xlabel("km")
a.set_ylabel("km")

a = P(3, 2)
base_pts = [(50 + 150 * i, 50 + 150 * j) for i in range(6) for j in range(6)]
base_pts += [(950, 50 + 150 * j) for j in range(5)]
base = [gr.T(x, y, 42000) for x, y in base_pts]
Gf2 = FIT()
t0 = sum(Gf2.nets(base))
step = 40
gx = np.arange(20, 1001, step)
z = np.full((len(gx), len(gx)), np.nan)
for i, yy in enumerate(gx):
    for j, xx in enumerate(gx):
        if min((xx - bx) ** 2 + (yy - by) ** 2 for bx, by in base_pts) < 400.0:
            continue
        z[i, j] = sum(Gf2.nets(base + [gr.T(xx, yy, 500)])) - t0
im = a.imshow(z, extent=(0, 1000, 0, 1000), origin="lower", cmap="RdYlGn")
plt.colorbar(im, ax=a, shrink=0.85, label="d(total growth)/turn")
a.scatter([p[0] for p in base_pts], [p[1] for p in base_pts], s=5, c="k", alpha=0.6)
a.set_title("C3  founding price: +500 village on 41x42k lattice")
a.set_xlabel("km")

a = P(3, 3)
d = np.linspace(1, 160, 200)
Gf3 = FIT()
a.plot(d, [Gf3.p["alpha"] * 300 * cg._sig((2500 - 300) / 30) * cg._win(x * x)
           * math.exp(-(x / RHO) ** 2) for x in d], label="access 2.5k market -> village")
a.plot(d, [Gf3.p["alpha"] * 2500 * cg._sig((300 - 2500) / 30) * cg._win(x * x)
           * math.exp(-(x / RHO) ** 2) for x in d], label="access village -> market")
a.plot(d, [Gf3.p["mu"] * 300 * 60000 / 60300 * (60000 - 300) * cg._win(x * x)
           * math.exp(-x / RHO) for x in d], label="migration 60k city -> village")
a.plot(d, [Gf3.p["mu"] * 300 * 60000 / 60300 * (300 - 60000) * cg._win(x * x)
           * math.exp(-x / RHO) for x in d], label="migration village -> city")
a.axhline(0, color="k", lw=0.6)
a.set_title("C4  pairwise terms by direction (pop/turn)")
a.set_xlabel("distance (km)")
a.set_ylabel("receiver's gain")
a.legend(fontsize=6.5)

fig.suptitle("Fitted growth system: formula anatomy, behavior, fit, and strategic impact "
             "(engine vs fitted; 1 turn = 1 week)", fontsize=15)
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=100)
print("wrote", OUT)
