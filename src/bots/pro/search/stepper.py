"""Distilled stepper (search M1): fast approximate world model for ranking.

My-perspective planner state (flat lists, pure Python — no numpy/numba:
bot cold-start must stay light). Per-turn distance matrices shared across
combat/captures/crowding; relevant-set pruning bounds N.
Simplifications (documented biases):
  S1 instant orders (no 150km/turn messenger delay).
  S2 no path-blocking (overestimates penetration vs screens).
  S3 foes static (towns compound, armies hold; callers require margin).
  S4 no viceroy/capital-move logic (capitals static until captured).
Phase order mirrors engine: move -> combat+captures -> growth -> spend.
Verified: growth <0.5 pop/100t quiet; battle/capture cases engine-exact.
"""

from __future__ import annotations
import math


def make_state(towns, armies):
    """towns: iter of dicts(id,x,y,faction,population,is_capital).
    armies: iter of dicts(id,x,y,faction[,target_x,target_y,has_target])."""
    T = {t["id"]: [float(t["x"]), float(t["y"]), int(t["faction"]),
                   float(t["population"]), bool(t.get("is_capital"))]
         for t in towns}
    A = {}
    for a in armies:
        A[a["id"]] = [float(a["x"]), float(a["y"]), int(a["faction"]),
                      float(a.get("target_x", a["x"])), float(a.get("target_y", a["y"])),
                      bool(a.get("has_target", False))]
    return {"T": T, "A": A, "next_id": 1000000, "_ct": 0, "_cc": None}


def prune(st, me, radius=400.0):
    """Relevant set: my assets + anything within radius of them. Returns a
    pruned COPY (caller keeps full state). Captures/raids outside cannot
    reach my towns within a 100-turn horizon meaningfully."""
    T, A = st["T"], st["A"]
    anchors = [(v[0], v[1]) for v in T.values() if v[2] == me]
    anchors += [(v[0], v[1]) for v in A.values() if v[2] == me]
    if not anchors:
        return {"T": {}, "A": {}, "next_id": st["next_id"], "_ct": 0, "_cc": None}
    T2 = {i: v for i, v in T.items()
          if v[2] == me or any(math.hypot(v[0] - ax, v[1] - ay) <= radius for ax, ay in anchors)}
    A2 = {i: v for i, v in A.items()
          if v[2] == me or any(math.hypot(v[0] - ax, v[1] - ay) <= radius for ax, ay in anchors)}
    return {"T": T2, "A": A2, "next_id": st["next_id"], "_ct": 0, "_cc": None}


def step(st, cfg, orders=None):
    """Advance one turn. orders: {trains:[tid], builds:{aid:(x,y)},
    moves:{aid:(tx,ty)}} applied instantly (S1)."""
    T, A = st["T"], st["A"]
    asp = cfg["army_speed"]
    IR = cfg["interact_radius"]
    if orders:
        for aid, tgt in (orders.get("moves") or {}).items():
            if aid in A:
                a = A[aid]
                a[3], a[4], a[5] = float(tgt[0]), float(tgt[1]), True
    # --- movement (straight line, S2) ---
    for a in A.values():
        if not a[5]:
            continue
        dx, dy = a[3] - a[0], a[4] - a[1]
        d2 = dx * dx + dy * dy
        if d2 <= asp * asp or d2 < 1e-18:
            a[0], a[1], a[5] = a[3], a[4], False
        else:
            s = asp / math.sqrt(d2)
            a[0] += dx * s
            a[1] += dy * s
    # --- pairwise army distances (shared by combat) ---
    aids = list(A.keys())
    n = len(aids)
    # D2[i][j] squared distances
    D2 = [[0.0] * n for _ in range(n)]
    for i in range(n):
        ai = A[aids[i]]
        for j in range(i + 1, n):
            aj = A[aids[j]]
            dx, dy = ai[0] - aj[0], ai[1] - aj[1]
            d2 = dx * dx + dy * dy
            D2[i][j] = d2
            D2[j][i] = d2
    IR2 = (IR + 1e-9) * (IR + 1e-9)
    weak = [0] * n
    for i in range(n):
        fi = A[aids[i]][2]
        c = 0
        row = D2[i]
        for j in range(n):
            if A[aids[j]][2] != fi and row[j] <= IR2:
                c += 1
        weak[i] = c
    # deaths: any enemy in range with weakness <= mine (simultaneous)
    dead = set()
    for i in range(n):
        fi = A[aids[i]][2]
        wi = weak[i]
        row = D2[i]
        for j in range(n):
            if A[aids[j]][2] != fi and row[j] <= IR2 and weak[j] <= wi:
                dead.add(aids[i])
                break
    for aid in dead:
        del A[aid]
    # --- captures (exact rule: weakest foe faction takes unless an ally
    # --- in range matches (held) or foes tie (standoff); pop *= (1-eff)) ---
    eff = cfg.get("build_efficiency", 0.5)
    live = [(aid, A[aid]) for aid in aids if aid not in dead]
    wmap = {aids[i]: weak[i] for i in range(n) if aids[i] not in dead}
    for tid, t in list(T.items()):
        inrange = []
        for aid, a in live:
            dx, dy = a[0] - t[0], a[1] - t[1]
            if dx * dx + dy * dy <= IR2:
                inrange.append(aid)
        foes = [aid for aid in inrange if A[aid][2] != t[2]]
        if not foes:
            continue
        min_foe = min(wmap[aid] for aid in foes)
        if any(wmap[aid] <= min_foe for aid in inrange if A[aid][2] == t[2]):
            continue
        takers = {A[aid][2] for aid in foes if wmap[aid] == min_foe}
        if len(takers) != 1:
            continue
        t[2] = next(iter(takers))
        t[3] *= (1.0 - eff)
        t[4] = False
    # --- growth (exact logistic + crowding; totals cached 10 turns) ---
    g = cfg["population_growth"]
    cap = cfg["population_cap"]
    tids = list(T.keys())
    cc = st.get("_cc")
    if cc is None or cc[0] != len(tids) or st.get("_ct", 0) % 10 == 0:
        tots = {}
        for tid in tids:
            t = T[tid]
            tot = 0.0
            for oid in tids:
                if oid == tid:
                    continue
                o = T[oid]
                dx, dy = t[0] - o[0], t[1] - o[1]
                d2 = dx * dx + dy * dy
                if d2 <= 22500.0 and d2 > 1e-18:
                    d = math.sqrt(d2)
                    tot += ((1.0 + 0.01 * math.log(o[3] / t[3]))
                            * (0.1 * math.sqrt(o[3] if o[3] < t[3] else t[3]) / d) ** 0.8)
            tots[tid] = tot
        st["_cc"] = (len(tids), tots)
        cc = st["_cc"]
    st["_ct"] = st.get("_ct", 0) + 1
    tots = cc[1]
    for tid in tids:
        t = T[tid]
        t[3] += g * t[3] * (1.0 - t[3] / cap) * (1.0 - tots.get(tid, 0.0))
    # --- death ---
    dth = cfg["death_threshold"]
    for tid in list(T.keys()):
        if T[tid][3] < dth - 1e-9:
            del T[tid]
    # --- spend ---
    if orders:
        seen = set()
        for tid in (orders.get("trains") or []):
            if tid in seen or tid not in T:
                continue
            seen.add(tid)
            t = T[tid]
            if t[3] >= cfg["army_cost"]:
                t[3] -= cfg["army_cost"]
                nid = st["next_id"]
                st["next_id"] += 1
                A[nid] = [t[0], t[1], t[2], t[0], t[1], False]
        for aid, bxy in (orders.get("builds") or {}).items():
            if aid not in A:
                continue
            a = A[aid]
            dx, dy = a[0] - bxy[0], a[1] - bxy[1]
            if dx * dx + dy * dy > IR2:
                continue
            del A[aid]
            tgt = None
            for t in T.values():
                dx, dy = t[0] - bxy[0], t[1] - bxy[1]
                if dx * dx + dy * dy <= IR2:
                    tgt = t
                    break
            if tgt is not None:
                tgt[3] += 500.0
            else:
                nid = st["next_id"]
                st["next_id"] += 1
                T[nid] = [bxy[0], bxy[1], a[2], 500.0, False]
    return st


def score(st, me):
    s = 0.0
    towns = 0
    for t in st["T"].values():
        if t[2] == me:
            s += t[3]
            towns += 1
    for a in st["A"].values():
        if a[2] == me:
            s += 1000.0
    if towns == 0:
        s -= 50000.0
    return s


def rollout(st, cfg, me, turns, policy=None):
    """Null rollout (policy None) or per-turn orders fn(k)->orders|None."""
    import copy
    st = copy.deepcopy(st)
    for k in range(turns):
        step(st, cfg, policy(k) if policy else None)
    return st
