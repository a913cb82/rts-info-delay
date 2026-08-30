"""Bots common — helpers for rl_game_min scripted tiers.

Tuned for rl_game_min defaults:
  map 1000, pop_cap 100k (peak 50k → 25/week), army_cost 1000,
  crowding: d_eq=0.4*sqrt(min), decay 0.3 (flat → long-range), asym 0.006.
"""

from __future__ import annotations

import math

SITE_MARGIN = 15.0
TRAIN_SURVIVE = 500  # death threshold = cost*efficiency

# Mid-size window where growth is >20/week — avoid TRAINing there
# logistic(40k)=24, 50k=25, 60k=24, 30k=21
PEAK_LOW = 35000
PEAK_HIGH = 65000


def _hash(turn: int, i: int, salt: int = 0) -> int:
    h = (turn * 73856093) ^ (i * 19349663) ^ (salt * 83492791)
    return h & 0x7FFFFFFF


def _own(view, kind: str):
    own = view.get("own_" + kind)
    if own is not None:
        return own
    if view.get("dead"):
        return []
    fid = view.get("faction", 0)
    return [p for p in view.get(kind, []) if p.get("faction") == fid]


def _busy(view) -> set:
    b = {o["entity"] for o in view.get("orders", [])}
    for p in view.get("own_armies", []):
        if p.get("order_kind", 0):
            b.add(p["id"])
    return b


def _world(view):
    fc = view.get("forecast")
    return view if fc is None else fc


def _enemies(view):
    fid = view.get("faction", 0)
    return [a for a in view.get("armies", []) if a.get("faction") != fid]


def _enemy_towns(view):
    fid = view.get("faction", 0)
    return [t for t in view.get("towns", []) if t.get("faction") != fid]


def _site(turn, i, cfg, own_towns, salt=0, rmin=80.0, rmax=250.0, around=None):
    """Deterministic site sampling, crowding-aware."""
    th = cfg.map_size[0] if isinstance(cfg.map_size, (list, tuple)) else 1000
    c = around if around is not None else {"x": th / 2, "y": th / 2}
    # For min, at peak pop towns are huge — d_eq up to 89km, so need large spacing
    # Use own_towns to estimate needed clearance: max pop's d_eq
    max_pop = max((t.get("population", 500) for t in own_towns), default=500)
    need = 0.4 * math.sqrt(max_pop) * 2  # ~2× d_eq
    need = max(need, 30.0)
    for k in range(12):
        h = _hash(turn, i, salt + k)
        ang = (h % 360) / 360 * 2 * math.pi
        d = rmin + ((h // 360) % 1000) / 1000 * (rmax - rmin)
        x = c["x"] + d * math.cos(ang)
        y = c["y"] + d * math.sin(ang)
        if x < SITE_MARGIN or y < SITE_MARGIN or x > th - SITE_MARGIN or y > th - SITE_MARGIN:
            continue
        if any(math.hypot(x - t["x"], y - t["y"]) < max(need, cfg.interact_radius) for t in own_towns):
            continue
        return x, y
    # fallback clamp
    return (
        min(th - SITE_MARGIN, max(SITE_MARGIN, c["x"])),
        min(th - SITE_MARGIN, max(SITE_MARGIN, c["y"])),
    )


def _forecast_pos(army: dict, delta_turns: float, cfg) -> tuple[float, float]:
    """Predict army position delta_turns in future, at army_speed."""
    if not army.get("has_target") or army.get("target_x") is None:
        return army["x"], army["y"]
    dx = army["target_x"] - army["x"]
    dy = army["target_y"] - army["y"]
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return army["x"], army["y"]
    # How far it will have moved by then
    travel = cfg.army_speed * delta_turns
    if travel >= dist:
        return army["target_x"], army["target_y"]
    s = travel / dist
    return army["x"] + dx * s, army["y"] + dy * s


def _eta(from_pos: dict, to_pos: dict, cfg) -> float:
    return math.hypot(from_pos["x"] - to_pos["x"], from_pos["y"] - to_pos["y"]) / max(1.0, cfg.army_speed)


def _can_train(pop: float, cfg, conservative: bool = False) -> bool:
    """TRAIN gate: survive and not in peak window if conservative."""
    if pop < cfg.army_cost + TRAIN_SURVIVE + (500 if conservative else 100):
        return False
    if conservative and PEAK_LOW <= pop <= PEAK_HIGH:
        return False
    if pop > 90000:  # near cap, growth ~9/week, not worth starving
        return False
    return True
