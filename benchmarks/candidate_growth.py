"""Candidate growth system (what we fit).

Merged form agreed 2026-09-12; two adjustments to the board sketch,
documented in the fit report:
  - migration sign: people flow toward LARGER towns, so the per-pair
    term is mu*(P_i - P_j)*K  (the sketch's (P_j - P_i) drained cities);
  - access is per-capita: alpha*P_i*sigmoid(...), so a market's lift
    scales with the village it serves.

  g(P)    = a*P - b*P^2 - c*P^3                    (alone: fertility,
                                                     cap, urban sink)
  W(i,j)  = alpha*P_i*sig((P_j-P_i-theta)/m)*K1     (market access;
            - gamma*min(P_i,P_j)*K1                  soft service
            + mu*(P_i-P_j)*K2)                       threshold)
                                                    (land competition)
                                                    (migration to big)
  K1 = exp(-(d/rho)^2), K2 = exp(-d/delta)
  all pairwise terms are multiplied by win(d) = sig(D^2/d^2 -
  D^2/(D^2-d^2)), D=150 km: one constant, C-infinity, exactly 0 at the
  bound, all derivatives vanish at the rim

  net_i = g(P_i) + sum_j W(i,j);  P <- max(P + net, 0)

All parameters named in NAMES, positive, fitted in log10 space.
Pair calculations: python fast path n<=16, numpy otherwise (perf).
"""

from __future__ import annotations

import math

import numpy as np

MIG_LIN, MIG_GRAV = 0, 1

# Hard interaction bound (game requirement + engine efficiency): pairs
# at d >= DCUT contribute exactly zero. One window constant only:
#
#   win(d) = sig( D^2/d^2 - D^2/(D^2-d^2) ),  D = DCUT = 150 km
#
# a single C-infinity curve: exactly 1 at d=0, exactly 0 at d=D, all
# derivatives vanish at the rim, no taper parameter and no piecewise
# definition (only the bound skip needed for efficiency).
DCUT = 150.0
_DCUT2 = DCUT * DCUT
try:
    import numba

    @numba.njit(cache=True)
    def _nets_kernel(P, X, Y, a, b, c, alpha, theta, m, gamma, rho, mu, delta,
                     variant, theta0, share, mfix, bfixK, nogamma, out):
        n = P.shape[0]
        th = 0.0 if theta0 else theta
        dl = rho if share else delta
        mm = mfix if mfix > 0.0 else m
        bb = (a / bfixK) if bfixK > 0.0 else b
        gg = 0.0 if nogamma else gamma
        for i in range(n):
            pi = P[i]
            s = pi * (a - bb * pi - c * pi * pi)
            for j in range(n):
                if i == j:
                    continue
                dx = X[i] - X[j]
                dy = Y[i] - Y[j]
                d2 = dx * dx + dy * dy
                if d2 >= _DCUT2:
                    continue
                xx = _DCUT2 / d2 - _DCUT2 / (_DCUT2 - d2) if d2 > 0.0 else 1e18
                w = 1.0 / (1.0 + math.exp(-xx)) if xx >= 0.0 else math.exp(xx) / (1.0 + math.exp(xx))
                k1 = w * math.exp(-d2 / (rho * rho))
                sig = 1.0 / (1.0 + math.exp(-((P[j] - pi - th) / mm)))
                k2 = w * math.exp(-math.sqrt(d2) / dl)
                if variant == MIG_LIN:
                    mj = mu * (pi - P[j]) * k2
                else:
                    mj = mu * pi * P[j] * (pi - P[j]) / (pi + P[j]) * k2
                s += (alpha * pi * sig * k1
                      - gg * (pi if pi < P[j] else P[j]) * k1 + mj)
            out[i] = s

    _warm_p = np.array([100.0, 200.0])
    _warm_xy = np.array([0.0, 1.0])
    _warm_out = np.zeros(2)
    _nets_kernel(_warm_p, _warm_xy, _warm_xy, 1e-4, 1e-9, 5e-13, 5e-6,
                 1e3, 5e2, 1e-5, 60.0, 1e-5, 60.0, MIG_LIN, 0, 0, 0.0, 0, 0,
                 _warm_out)
except Exception:  # pragma: no cover
    _nets_kernel = None

NAMES = ["a", "b", "c", "alpha", "theta", "m", "gamma", "rho", "mu", "delta"]

PRIOR = {"a": 1e-4, "b": 1e-9, "c": 5e-13, "alpha": 5e-6, "theta": 1000.0,
         "m": 500.0, "gamma": 1e-5, "rho": 60.0, "mu": 1e-5, "delta": 60.0}

# log10 search boxes, chosen from orders of magnitude (see plan)
BOX = {"a": (-5.5, -2.0), "b": (-11.0, -7.0), "c": (-15.5, -10.5),
       "alpha": (-8.0, -4.0), "theta": (1.0, 4.0), "m": (1.0, 4.0),
       "gamma": (-8.0, -3.0), "rho": (1.0, 2.5), "mu": (-8.5, -4.0),
       "delta": (1.0, 2.5)}

# amplitude scales for the sparsity penalty (null = 0); theta/m/rho/delta
# are shape params, ridge-only
AMPLITUDES = {"alpha": 1e-4, "gamma": 1e-4, "mu": 1e-4, "c": 1e-12}
SHAPES = {"theta": 1e3, "m": 5e2, "rho": 1e2, "delta": 1e2, "a": 1e-4, "b": 1e-9}


def _sig(x):
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _win(d2):
    """Single-curve window: 1 at d=0, 0 at d=DCUT, C-infinity, one constant."""
    if d2 >= _DCUT2:
        return 0.0
    if d2 <= 0.0:
        return 1.0
    return _sig(_DCUT2 / d2 - _DCUT2 / (_DCUT2 - d2))


def _win_np(d2):
    with np.errstate(divide="ignore", over="ignore"):
        x = np.where(d2 > 0.0, _DCUT2 / np.maximum(d2, 1e-300), 1e18)
        x = x - np.where(d2 < _DCUT2, _DCUT2 / np.maximum(_DCUT2 - d2, 1e-300), 1e18)
        w = np.where(x >= 0.0, 1.0 / (1.0 + np.exp(-np.minimum(x, 700.0))),
                     np.exp(np.maximum(x, -700.0)) / (1.0 + np.exp(np.maximum(x, -700.0))))
    w = np.where(d2 >= _DCUT2, 0.0, w)
    return w


FITTED = {
    "a": 8.2e-05,
    "b": 1.3e-09,
    "c": 1e-14,
    "alpha": 1.8e-05,
    "theta": 1000.0,
    "m": 430.0,
    "gamma": 1.4e-07,
    "rho": 270.0,
    "mu": 2.7e-09,
    "delta": 17.0
}
FITTED_VARIANT = dict(variant=MIG_GRAV, theta0=True, share=True, mfix=30.0, bfixK=3e5, nogamma=True)


def from_log10(x):
    return {k: 10.0 ** v for k, v in zip(NAMES, x)}


def to_log10(params):
    return [math.log10(params[k]) for k in NAMES]


class FittedGrowth:
    name = "fitted"

    def __init__(self, params=None, variant=MIG_GRAV, theta0=False, share=False,
                 mfix=0.0, bfixK=0.0, nogamma=False):
        p = dict(PRIOR)
        p.update(params or {})
        self.p = p
        self.variant = variant
        self.theta0 = bool(theta0)
        self.share = bool(share)
        self.mfix = float(mfix)
        self.bfixK = float(bfixK)
        self.nogamma = bool(nogamma)

    def describe(self):
        tag = ["lin" if self.variant == MIG_LIN else "grav"]
        if self.theta0:
            tag.append("theta0")
        if self.share:
            tag.append("shared-delta")
        if self.mfix:
            tag.append(f"m={self.mfix:g}")
        if self.bfixK:
            tag.append(f"b=a/{self.bfixK:g}")
        if self.nogamma:
            tag.append("nogamma")
        return ("fitted cubic+kernel [" + ",".join(f"{k}={self.p[k]:.3g}" for k in NAMES)
                + "] " + "+".join(tag))

    def _g(self, P):
        p = self.p
        b = (p["a"] / self.bfixK) if self.bfixK > 0.0 else p["b"]
        return P * (p["a"] - b * P - p["c"] * P * P)

    def isolated(self, pop):
        return float(self._g(float(pop)))

    def _pair(self, Pi, Pj, d2):
        if d2 >= _DCUT2:
            return 0.0
        p = self.p
        w = _win(d2)
        th = 0.0 if self.theta0 else p["theta"]
        dl = p["rho"] if self.share else p["delta"]
        mm = self.mfix if self.mfix > 0.0 else p["m"]
        gg = 0.0 if self.nogamma else p["gamma"]
        k1 = w * math.exp(-d2 / (p["rho"] * p["rho"]))
        access = p["alpha"] * Pi * _sig((Pj - Pi - th) / mm) * k1
        comp = gg * min(Pi, Pj) * k1
        k2 = w * math.exp(-math.sqrt(d2) / dl)
        mig = (p["mu"] * (Pi - Pj) * k2 if self.variant == MIG_LIN
               else p["mu"] * Pi * Pj * (Pi - Pj) / (Pi + Pj) * k2)
        return access - comp + mig

    def nets(self, towns):
        n = len(towns)
        if n == 0:
            return []
        P = [float(t.population) for t in towns]
        g = self._g(np.array(P, dtype=float))
        if n == 1:
            return [float(g[0])]
        if n <= 16:
            X = [float(t.x) for t in towns]
            Y = [float(t.y) for t in towns]
            out = []
            for i in range(n):
                s = float(g[i])
                for j in range(n):
                    if i == j:
                        continue
                    dx = X[i] - X[j]
                    dy = Y[i] - Y[j]
                    s += self._pair(P[i], P[j], dx * dx + dy * dy)
                out.append(s)
            return out
        x = np.array([float(t.x) for t in towns])
        y = np.array([float(t.y) for t in towns])
        Pn = np.array(P, dtype=float)
        p = self.p
        if _nets_kernel is not None:
            out = np.empty(n, dtype=float)
            _nets_kernel(Pn, x, y, p["a"], p["b"], p["c"], p["alpha"],
                         p["theta"], p["m"], p["gamma"], p["rho"],
                         p["mu"], p["delta"], self.variant,
                         1 if self.theta0 else 0, 1 if self.share else 0,
                         self.mfix, self.bfixK,
                         1 if self.nogamma else 0, out)
            return out.tolist()
        dx = x[:, None] - x[None, :]
        dy = y[:, None] - y[None, :]
        d2 = dx * dx + dy * dy
        w = _win_np(d2)
        k1 = w * np.exp(-d2 / (p["rho"] * p["rho"]))
        sig = 1.0 / (1.0 + np.exp(-((Pn[None, :] - Pn[:, None] - p["theta"]) / p["m"])))
        W = p["alpha"] * Pn[:, None] * sig * k1
        W -= p["gamma"] * np.minimum(Pn[:, None], Pn[None, :]) * k1
        W += p["mu"] * (Pn[:, None] - Pn[None, :]) * w * np.exp(-np.sqrt(d2) / p["delta"])
        np.fill_diagonal(W, 0.0)
        return (g + W.sum(axis=1)).tolist()

    def step(self, world, n=1):
        for _ in range(n):
            towns = list(world.towns)
            if not towns:
                break
            for t, v in zip(towns, self.nets(towns)):
                t.population = max(t.population + v, 0.0)
            for t in [t for t in towns if t.population <= 0.0]:
                world.remove_town(t.id)

    @property
    def death_threshold(self):
        return 0.0

    @property
    def nparams(self):
        return (len(NAMES) - (1 if self.theta0 else 0)
                - (1 if self.share else 0) - (1 if self.mfix else 0)
                - (1 if self.bfixK else 0) - (1 if self.nogamma else 0))


def check_parity():
    """Numba path == python fast path, on the SAME town set."""
    rng = np.random.default_rng(3)
    from engine.world import Town
    towns = [Town(id=i, faction=0, x=float(rng.uniform(0, 500)),
                  y=float(rng.uniform(0, 500)),
                  population=float(rng.uniform(50, 50000))) for i in range(17)]
    G = FittedGrowth()
    vec = G.nets(towns)  # n=17 -> kernel path
    ref = []
    for i, t in enumerate(towns):
        s = float(G._g(t.population))
        for j, u in enumerate(towns):
            if i == j:
                continue
            s += G._pair(t.population, u.population,
                         (t.x - u.x) ** 2 + (t.y - u.y) ** 2)
        ref.append(s)
    return max(abs(u - v) for u, v in zip(vec, ref))
