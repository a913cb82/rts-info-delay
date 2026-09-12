"""turtle protocol — split from core.py (mechanical, behavior-identical)."""

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
    import os as _os
    trace_dir = _os.environ.get("BOT_TRACE_DIR")
    trace_every = int(_os.environ.get("BOT_TRACE_EVERY", "25"))
    trace_fh = None
    if trace_dir:
        from pathlib import Path as _P
        _P(trace_dir).mkdir(parents=True, exist_ok=True)
        trace_fh = open(_P(trace_dir) / f"trace_{faction}.jsonl", "w", buffering=1)
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
        _dec_ms = (time.time() - t_start) * 1000.0
        # Command queue: fresh decide first (re-tasks win), then fire due
        # scheduled commands (validated: notes/af prevalence/arrival).
        try:
            orders = list(orders) + state.pop_due_orders(cfg)
        except Exception:
            pass
        # Track issued orders locally (delay-aware decisions + evac flag).
        state.note_orders(orders)
        if trace_fh is not None and (turn % max(1, trace_every) == 0):
            try:
                trace_fh.write(json.dumps({
                    "turn": turn, "faction": faction, "ms": round(_dec_ms, 1),
                    "towns": [{"id": t.id, "f": t.faction, "pop": round(t.population),
                                 "x": round(t.x), "y": round(t.y), "cap": t.is_capital}
                                for t in state.world.towns],
                    "armies": [{"id": a.id, "f": a.faction, "x": round(a.x), "y": round(a.y)}
                                 for a in state.world.armies],
                    "notes": {str(k): [round(v[0]), round(v[1])] for k, v in state._army_targets.items()},
                    "scout": [state._scout_id, getattr(state, "_scout_id2", None)],
                    "mapper": sorted(state.__dict__.get("_mapper", {})),
                    "blood": sorted(state.__dict__.get("_bloodied", {})),
                    "orders": orders}) + "\n")
            except Exception:
                pass
        for o in orders:
            sys.stdout.write(o + "\n")
        sys.stdout.write("go\n")
        sys.stdout.flush()

