"""Greedy — raider. Most eager trainer, opportunistic attacker/builder."""

from __future__ import annotations
import math
from engine.config import GameConfig
from .common import BotForecast, BotState, bot_main, find_build_site, inbound_eta, note_wave_watch, should_hold_home


def _can_train_greedy(state: BotState, town) -> bool:
    if town.population < 1500 or town.population > 90000:
        return False
    if town.id in state._pending_trains and state.turn <= state._pending_trains[town.id]:
        return False
    cap = state.world.faction_capital(state.faction)
    if cap:
        dist = math.hypot(cap.x - town.x, cap.y - town.y)
        if dist > 100 and town.population < 1500 + int(dist / 150 * 400):
            return False
    return True


def _stage_trains(state: BotState, config: GameConfig) -> list[str]:
    # greedy prioritises overcrowded reps first
    cands = [t for t in state.own_towns() if _can_train_greedy(state, t)]
    cands.sort(key=lambda t: (0 if state.should_train_for_overcrowding(t) else 1, state.get_growth(t.id), t.population))
    return [f"TRAIN {t.id}" for t in cands]


def _army_targets(state: BotState, config: GameConfig):
    faction = state.faction
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    enemy_armies = [a for a in state.world.armies if a.faction != faction]
    return enemy_towns, enemy_armies


def _stage_moves(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    enemy_towns, enemy_armies = _army_targets(state, config)
    hold_second = note_wave_watch(state)
    inbound = inbound_eta(state, config)
    for p in state.own_armies():
        if state.should_yield():
            break
        if state.army_has_target(p.id):
            continue  # handled by the builds stage
        # G-defense: keep >=1 home vs inbound/second wave (viability-gating
        # the attack removed the accidental counter-march that used to
        # intercept wave 2 mid-field).
        if should_hold_home(state, config, p, inbound, hold_second):
            continue
        # G1: viability gate — duel-only (P7: in big wars denial-raids on
        # small towns erase foe production; gating cost pro 2185).
        war_foes = {t.faction for t in enemy_towns} | {a.faction for a in enemy_armies}
        if len(war_foes) <= 1:
            viable = [t for t in enemy_towns
                      if t.population * (1.0 - config.build_efficiency)
                      > config.army_cost * config.build_efficiency + 200]
        else:
            viable = list(enemy_towns)
        if viable:
            nearest = min(viable, key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {nearest.x:.1f} {nearest.y:.1f}")
            state.note_move(p.id, nearest.x, nearest.y)
        elif enemy_armies:
            fc = BotForecast(state, config)
            forecast = [(fc.forecast_army_pos(e), e) for e in enemy_armies]
            (fx, fy), _ = min(forecast, key=lambda x: math.hypot(x[0][0] - p.x, x[0][1] - p.y))
            out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {fx:.1f} {fy:.1f}")
        else:
            # G2: recycle — no foes and no site: march home for +500 pop-add
            # (builds stage BUILDs on arrival since target is an own town).
            site = find_build_site(state, config, p.x, p.y, rmin=80, rmax=300, salt=11)
            if site:
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {site[0]:.1f} {site[1]:.1f}")
                state.note_move(p.id, site[0], site[1])
            elif state.own_towns():
                home = min(state.own_towns(), key=lambda t: math.hypot(t.x - p.x, t.y - p.y))
                out.append(f"MOVE_TO {p.id} {p.x:.1f} {p.y:.1f} {home.x:.1f} {home.y:.1f}")
                state.note_move(p.id, home.x, home.y)
    return out


def _stage_builds(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    faction = state.faction
    enemy_towns = [t for t in state.world.towns if t.faction != faction]
    for p in state.own_armies():
        if state.should_yield():
            break
        if p.is_viceroy and state.army_has_target(p.id):
            continue
        if not state.army_has_target(p.id):
            continue
        if state.has_pending_build(p.id):
            continue
        tgt = state.army_target(p.id)
        if tgt is None:
            continue
        is_enemy_target = any(math.hypot(tgt[0] - t.x, tgt[1] - t.y) < 20 for t in enemy_towns)
        if not is_enemy_target and math.hypot(p.x - tgt[0], p.y - tgt[1]) < config.interact_radius + 10:
            out.append(f"BUILD {p.id} {tgt[0]:.1f} {tgt[1]:.1f}")
    return out


_STAGES = [("trains", _stage_trains), ("moves", _stage_moves), ("builds", _stage_builds)]


def decide_stages(state: BotState, config: GameConfig) -> list[tuple[str, list[str]]]:
    """Idea 2: full stage outputs (introspection/testing; decide_orders is lazy)."""
    return [(name, fn(state, config)) for name, fn in _STAGES]


def decide_orders(state: BotState, config: GameConfig) -> list[str]:
    out: list[str] = []
    if state.should_yield():
        return out
    # Idea 2: lazy stages — an expired clock skips later stages entirely
    # instead of paying their compute, keeping the important prefix.
    # Idea 6: low bank skips straight to trains-only (no moves/builds cost).
    low = state.effort(getattr(state, "clock_budget_ms", None)) == "low"
    for name, fn in _STAGES:
        if low and name != "trains":
            break
        out.extend(fn(state, config))
        if state.should_yield():
            break
    return out


if __name__ == "__main__":
    bot_main(decide_orders)
