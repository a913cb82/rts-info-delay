"""Tag-aware delivery builder — ledger entries to wire updates.

Pure fn (ledger, faction, send-state, S, capital-now, now) -> updates.
Semantics: Ledger.query gates (TAG + DELAY + S), plus latest-only per
entity per payload and send-state diffing (slim wire). Canonical order is
ledger order. No flight concept here — mute is the runner's I/O skip;
flight tags die in the S-filter.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

from engine.ledger import EventKind

_TOWN = EventKind.TOWN_UPDATE
_ARMY = EventKind.ARMY_UPDATE
_KINDS = (_TOWN, _ARMY)


@njit
def _newest_passing(turns, xs, ys, rows, tags, fbit, s, cap_x, cap_y, now, info,
                    best_idx):
    """Single oldest->newest pass: newest passing entry per dense row wins."""
    eps = 1e-9 * info
    for i in range(turns.shape[0]):
        if (tags[i] & fbit) == 0:
            continue
        t = turns[i]
        if t < s:
            continue
        dt = now - float(t)
        if dt < 0.0:
            continue
        dx = xs[i] - cap_x
        dy = ys[i] - cap_y
        lim = dt * info + eps
        if dx * dx + dy * dy > lim * lim:
            # Squared-reject; sqrt only at the boundary (exactness).
            if float(t) + math.sqrt(dx * dx + dy * dy) / info > now + 1e-9:
                continue
        best_idx[rows[i]] = i


def _precompile():
    # Pay JIT once at import, never mid-game (house rule opt10).
    z = np.zeros(4, dtype=np.int64)
    f = np.zeros(4, dtype=np.float64)
    bi = np.full(2, -1, dtype=np.int64)
    _newest_passing(z, f, f, z, z, 1, 0, 0.0, 0.0, 0.0, 150.0, bi)


_precompile()


def _passes(ev, faction: int, s: int, cap_x: float, cap_y: float, now: float, info: float) -> bool:
    """TAG + DELAY + S for one entry (exact predicate, shared by shapes)."""
    if ev.kind not in _KINDS:
        return False
    if faction not in ev.visible_to:
        return False
    t = ev.turn
    if t < s:
        return False
    dx = ev.x - cap_x
    dy = ev.y - cap_y
    return t + math.hypot(dx, dy) / info <= now + 1e-9


def build_updates_scan(ledger, faction: int, s: int,
                       capital: tuple[float, float], now: float) -> list[dict]:
    """Reference builder: naive window scan (correctness anchor for fast).
    Send-all era: newest passing entry per entity, always emitted."""
    cap_x, cap_y = capital
    info = ledger.info_speed or 150.0
    # Newest-first single pass: the first passing entry per entity wins
    # (latest-only); then ledger order restored for output.
    chosen: dict = {}
    keys: list = []
    for ev in reversed(ledger.events):
        if ev.kind not in _KINDS:
            continue
        k = ("town" if ev.kind is _TOWN else "army", ev.payload["id"])
        if k in chosen:
            continue
        if _passes(ev, faction, s, cap_x, cap_y, now, info):
            chosen[k] = ev
            keys.append(k)
    out = []
    for k in reversed(keys):
        ev = chosen[k]
        snap = dict(ev.payload)
        d = {"kind": "town_update" if ev.kind is _TOWN else "army_update",
             "id": ev.payload["id"], "x": ev.x, "y": ev.y}
        d.update(snap)
        out.append(d)
    return out


def build_updates(ledger, faction: int, s: int,
                  capital: tuple[float, float], now: float) -> list[dict]:
    """Build one faction's wire updates: EVERY visible entity, EVERY turn.
    No dedup, no heartbeat windows — max simplicity. Absence of an id
    means not-visible (signal); bots diff against their mirrors."""
    turns, xs, ys, rows, tags, seqs, pays, n_rows, _chg = ledger.columns()
    n = turns.shape[0]
    if n == 0 or n_rows == 0:
        return []
    cap_x, cap_y = capital
    info = ledger.info_speed or 150.0
    best_idx = np.full(n_rows, -1, dtype=np.int64)
    _newest_passing(turns, xs, ys, rows, tags, 1 << int(faction), int(s),
                    float(cap_x), float(cap_y), float(now), float(info), best_idx)
    keys_of = ledger._c_key_of
    picked = []
    for r in np.nonzero(best_idx >= 0)[0].tolist():
        i = int(best_idx[r])
        key = keys_of[r]
        snap = pays[i]
        picked.append((i, key, snap))
    picked.sort(key=lambda t: t[0])
    out = []
    for i, key, snap in picked:
        is_town = key[0] == "town"
        d = {"kind": "town_update" if is_town else "army_update",
             "id": snap["id"], "x": float(xs[i]), "y": float(ys[i])}
        d.update(snap)
        out.append(d)
    return out
