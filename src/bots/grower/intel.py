"""grower intel — minimal mirror (peaceful needs are small, speed matters).

Tracks: towns (id->pos/pop/faction/capital), armies (id->pos/size/faction),
own order memory (targets, pending trains/builds), per-town growth.
NO fog-reasoning (trails/graves/blood): arrival = pos==target on update.
Same method names as the big BotState (drop-in for grower brain).
"""
from __future__ import annotations
import math
import time
from engine.config import GameConfig
from engine.world import World, Town, Army


class GrowerState:
    FLUSH_MARGIN_MS = 3.0
    YIELD_AT_MS = 5.0

    def __init__(self):
        self.faction: int = 0
        self.config: GameConfig | None = None
        self.world: World = World()
        self.turn: int = 0
        self.deadline: float | None = None
        self._army_targets: dict[int, tuple[float, float]] = {}
        self._pending_trains: dict[int, int] = {}
        self._pending_builds: dict[int, int] = {}
        self._scout_id = None  # protocol-trace compat (unused)
        self._prev_pop: dict[int, float] = {}
        self._growth: dict[int, float] = {}
        self.evac_ordered: bool = False

    def init(self, config: GameConfig, faction: int):
        self.config = config
        self.faction = faction
        try:
            self.world.map_size = config.map_size
        except Exception:
            pass

    # -- queries (brain API) --
    def own_towns(self) -> list[Town]:
        return [t for t in self.world.towns if t.faction == self.faction]

    def own_armies(self) -> list[Army]:
        return [a for a in self.world.armies if a.faction == self.faction]

    def army_has_target(self, aid: int) -> bool:
        return aid in self._army_targets

    def army_target(self, aid: int) -> tuple[float, float] | None:
        return self._army_targets.get(aid)

    def has_pending_build(self, aid: int) -> bool:
        return aid in self._pending_builds

    def get_growth(self, tid: int) -> float:
        return self._growth.get(tid, 0.0)

    def should_yield(self) -> bool:
        if self.deadline is None:
            return False
        return max(0.0, (self.deadline - time.time()) * 1000) < 5.0

    def note_train(self, tid: int) -> None:
        # pending = delivery estimate (capital->town mail + 1); honest cadence governor
        try:
            cap = self.world.faction_capital(self.faction)
            t = self.world.get_town(tid)
            if cap is not None and t is not None:
                import math as _m
                self._pending_trains[tid] = self.turn + max(1, int(_m.ceil(_m.hypot(cap.x - t.x, cap.y - t.y) / 150.0)) + 1)
                return
        except Exception:
            pass
        self._pending_trains[tid] = self.turn + 5

    def cached_or_decide(self, decide_fn, cfg, events=None):
        return decide_fn(self, cfg)

    def pop_due_orders(self, cfg=None):
        return []

    # -- update --
    def update(self, turn: int, events: list[dict]) -> None:
        self.turn = turn
        for tid in list(self._pending_trains):
            if turn > self._pending_trains[tid]:
                self._pending_trains.pop(tid, None)
        for aid in list(self._pending_builds):
            if turn > self._pending_builds[aid]:
                self._pending_builds.pop(aid, None)
        for ev in events:
            kind = ev.get("kind")
            eid = ev.get("id")
            if kind == "town_update":
                t = self.world.get_town(eid)
                pop = float(ev.get("population", 0.0))
                if t is None:
                    t = Town(id=eid, faction=int(ev.get("faction", -1)),
                             x=float(ev.get("x", 0.0)), y=float(ev.get("y", 0.0)),
                             population=pop,
                             is_capital=bool(ev.get("is_capital", False)))
                    self.world.towns.append(t)
                    self._prev_pop[eid] = pop
                    self._growth[eid] = 0.0
                else:
                    if eid in self._prev_pop:
                        self._growth[eid] = pop - self._prev_pop[eid]
                    self._prev_pop[eid] = pop
                    t.population = pop
                    t.faction = int(ev.get("faction", t.faction))
                    t.x = float(ev.get("x", t.x))
                    t.y = float(ev.get("y", t.y))
                    t.is_capital = bool(ev.get("is_capital", t.is_capital))
                if pop <= 0:
                    self.world.remove_town(eid)
                    self._prev_pop.pop(eid, None)
                    self._growth.pop(eid, None)
                    self._pending_trains.pop(eid, None)
            elif kind == "army_update":
                if ev.get("alive") is False:
                    self.world.remove_army(eid)
                    self._army_targets.pop(eid, None)
                    self._pending_builds.pop(eid, None)
                else:
                    a = self.world.get_army(eid)
                    if a is None:
                        a = Army(id=eid, faction=int(ev.get("faction", -1)),
                                 x=float(ev.get("x", 0.0)), y=float(ev.get("y", 0.0)),
                                 is_viceroy=bool(ev.get("is_viceroy", False)),
                                 size=float(ev.get("size", 1000.0) or 1000.0))
                        self.world.armies.append(a)
                    else:
                        a.faction = int(ev.get("faction", a.faction))
                        a.x = float(ev.get("x", a.x))
                        a.y = float(ev.get("y", a.y))
                        a.is_viceroy = bool(ev.get("is_viceroy", a.is_viceroy))
                        if ev.get("size") is not None:
                            try:
                                a.size = float(ev.get("size"))
                            except (TypeError, ValueError):
                                pass
            elif kind == "army_move":
                a = self.world.get_army(eid)
                if a is not None:
                    a.x = float(ev.get("x", a.x))
                    a.y = float(ev.get("y", a.y))
        # arrival release (engine truth: landed armies need new orders)
        for aid, tgt in list(self._army_targets.items()):
            a = self.world.get_army(aid)
            if a is None:
                self._army_targets.pop(aid, None)
            elif math.hypot(a.x - tgt[0], a.y - tgt[1]) <= 1.0:
                self._army_targets.pop(aid, None)

    def note_orders(self, orders: list[str]) -> None:
        for o in orders:
            parts = o.split()
            if not parts:
                continue
            if parts[0] == "MOVE_TO" and len(parts) >= 6:
                try:
                    self._army_targets[int(parts[1])] = (float(parts[4]), float(parts[5]))
                except (ValueError, IndexError):
                    pass
            elif parts[0] == "TRAIN" and len(parts) >= 2:
                try:
                    self.note_train(int(parts[1]))
                except (ValueError, IndexError):
                    pass
            elif parts[0] == "BUILD" and len(parts) >= 2:
                try:
                    self._pending_builds[int(parts[1])] = self.turn + 20
                except (ValueError, IndexError):
                    pass


BotState = GrowerState  # protocol compat alias
