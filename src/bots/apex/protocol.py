"""pro protocol — split from core.py (mechanical, behavior-identical)."""

from __future__ import annotations
import json
import math
import sys
import time
from dataclasses import dataclass, field
from engine.config import GameConfig
from engine.world import World, Town, Army
from .intel import *  # noqa: F401,F403

def _read_startup():
    cfg = GameConfig()
    fac = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("config "):
            try:
                cfg = GameConfig.from_dict(json.loads(line[7:]))
            except Exception:
                pass
        elif line.startswith("faction "):
            try:
                fac = int(line.split()[1])
            except Exception:
                pass
        elif line == "go":
            break
        elif line.startswith("end "):
            sys.exit(0)
    return cfg, fac


def _read_turn():
    turn = None
    ev = []
    clock = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("turn "):
            try:
                turn = int(line.split()[1])
            except Exception:
                turn = 0
        elif line.startswith("clock "):
            try:
                clock = float(line.split()[1])
            except Exception:
                pass
        elif line == "go":
            if turn is not None:
                return turn, ev, clock
        elif line.startswith("end "):
            return -1, [], None
        elif line.startswith("{"):
            try:
                ev.append(json.loads(line))
            except Exception:
                pass
        else:
            try:
                ev.append(json.loads(line))
            except Exception:
                pass
    return None


def bot_main(decide_fn):
    cfg, faction = _read_startup()
    state = BotState()
    state.init(cfg, faction)
    while True:
        r = _read_turn()
        if r is None:
            break
        turn, events, clock = r
        if turn == -1:
            break
        t_start = time.time()
        # deadline BEFORE update: a huge backlog must not blow the clock
        # before decide runs — update() yields mid-backlog and carries over.
        # deadline: Fischer clock from engine when sent, else legacy fixed budget
        if clock is None:
            try:
                ms = int(getattr(cfg, "turn_time_ms", 100))
            except Exception:
                ms = 100
            state.deadline = t_start + max(0.02, ms / 1000 - 0.015)
        else:
            state.deadline = t_start + max(0.005, clock / 1000 - BotState.FLUSH_MARGIN_MS / 1000)
        state.update(turn, events)
        state.clock_budget_ms = clock  # idea 6: effort level for this turn
        # Ideas 4+5: replay plans/standing orders on quiet turns.
        orders = state.cached_or_decide(decide_fn, cfg, events)
        # Track issued orders locally (delay-aware decisions + evac flag).
        state.note_orders(orders)
        for o in orders:
            sys.stdout.write(o + "\n")
        sys.stdout.write("go\n")
        sys.stdout.flush()


# ── Step 2 demand API (shared, parameterized personalities) ──
# Personalities are parameter shifts on this backbone (GTO.md s9): pro
# pays full price on time; the others deviate on schedule via depth_extra
# (muster cushion), raid_margin (theft bar), payback_mult (expansion
# patience) — never by different rules.


