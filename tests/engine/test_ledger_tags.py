"""Phase 1 — tagged generation + S plumbing (no send-state delivery).

Ledger becomes the tagged generation log: every observed entity gets an
entry every turn; unobserved entities get none. Delivery gates live in
Ledger.query (TAG + DELAY + S reference); slimming (send-state,
latest-only) is Phase 2's builder.
"""
import math

from engine.config import GameConfig
from engine.ledger import EventKind, Ledger
from engine.world import Army, Town, World

CFG = GameConfig()
LOS = 150.0


def _world(towns=(), armies=()):
    w = World()
    w.map_size = [1000, 1000]
    w.towns = list(towns)
    w.armies = list(armies)
    return w


def _town(tid, x, y, faction=0, pop=2000.0, cap=False):
    return Town(id=tid, faction=faction, x=x, y=y, population=pop, is_capital=cap)


def _army(aid, x, y, faction=0, viceroy=False):
    return Army(id=aid, faction=faction, x=x, y=y, is_viceroy=viceroy)


def _updates(ledger):
    return [e for e in ledger.events
            if e.kind in (EventKind.TOWN_UPDATE, EventKind.ARMY_UPDATE)]


class TestGeneration:
    def test_observed_town_generates_entry_every_turn(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True), _town(2, 100, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        assert len(_updates(lg)) == 2
        lg.generate(w, turn=6, line_of_sight=LOS)
        assert len(_updates(lg)) == 4  # unconditional: static entities included

    def test_entry_shape(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        (e,) = _updates(lg)
        assert e.kind == EventKind.TOWN_UPDATE
        assert e.turn == 5
        assert (e.x, e.y) == (0.0, 0.0)
        assert e.payload == {"id": 1, "faction": 0, "population": 2000, "is_capital": True}
        assert e.visible_to == {0}

    def test_live_entity_always_self_observed(self) -> None:
        # A lone foe town 500 km from everyone is still observed by its
        # owner (dist 0) — so live generation never skips; skip fires only
        # for unwatched deaths (below).
        w = _world(towns=[_town(1, 0, 0, cap=True),
                          _town(2, 500, 0, faction=1)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        by_id = {e.payload["id"]: e for e in _updates(lg)}
        assert by_id[2].visible_to == {1}

    def test_mixed_observers(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True),
                          _town(2, 160, 0, faction=1)],
                   armies=[_army(7, 140, 0, faction=0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        by_id = {e.payload["id"]: e for e in _updates(lg)}
        assert by_id[2].visible_to == {0, 1}  # fac0 army 20 km off, fac1 self
        assert by_id[1].visible_to == {0}  # own capital; foe 160 km off

    def test_per_faction_independence(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True),
                          _town(2, 500, 0, faction=1, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        q0 = lg.query(0, 0.0, 0.0, now=5.0)
        q1 = lg.query(1, 500.0, 0.0, now=5.0)
        assert {e.payload["id"] for e in q0} == {1}
        assert {e.payload["id"] for e in q1} == {2}

    def test_los_boundary_inclusive(self) -> None:
        # (90,120) is exactly 150.0; one metre past is out.
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 90.0, 120.0, faction=1),
                           _army(8, 90.001, 120.0, faction=1)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        by_id = {e.payload["id"]: e for e in _updates(lg) if e.kind == EventKind.ARMY_UPDATE}
        assert 0 in by_id[7].visible_to  # exactly at LOS: observed
        assert 0 not in by_id[8].visible_to  # past LOS: owner only
        assert by_id[8].visible_to == {1}

    def test_generation_records_current_position(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 10, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        w.armies[0].x = 60.0
        lg.generate(w, turn=6, line_of_sight=LOS)
        got = [e for e in _updates(lg)
               if e.kind == EventKind.ARMY_UPDATE and e.turn == 6]
        assert [(e.x, e.y) for e in got] == [(60.0, 0.0)]

    def test_flags_carried(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 10, 0, viceroy=True)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        by_id = {e.payload["id"]: e for e in _updates(lg)}
        assert by_id[7].payload["is_viceroy"] is True
        assert by_id[7].payload["alive"] is True
        assert by_id[1].payload["is_capital"] is True

    def test_population_is_int(self) -> None:
        w = _world(towns=[_town(1, 0, 0, pop=1234.6, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        (e,) = _updates(lg)
        assert e.payload["population"] == 1235

    def test_empty_world(self) -> None:
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(_world(), turn=5, line_of_sight=LOS)
        assert _updates(lg) == []
        assert lg.query(0, 0.0, 0.0, now=5.0) == []

    def test_ledger_stays_turn_ordered(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        for t in (5, 6, 7):
            lg.generate(w, turn=t, line_of_sight=LOS)
        assert [e.turn for e in _updates(lg)] == [5, 6, 7]
        assert [e.turn for e in lg.query(0, 0.0, 0.0, now=7.0)] == [5, 6, 7]


class TestTombstones:
    def test_army_death_shape_and_recipients(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 100, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        w.armies = []  # dies unseen except by the capital's watch
        lg.generate(w, turn=6, line_of_sight=LOS)
        deaths = [e for e in _updates(lg)
                  if e.kind == EventKind.ARMY_UPDATE and e.payload.get("alive") is False]
        assert len(deaths) == 1
        d = deaths[0]
        assert d.turn == 6
        assert (d.x, d.y) == (100.0, 0.0)  # last-known pos
        assert d.payload["id"] == 7
        assert d.visible_to == {0}

    def test_town_death_is_pop_zero(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True), _town(2, 100, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        w.towns = [w.towns[0]]
        lg.generate(w, turn=6, line_of_sight=LOS)
        deaths = [e for e in _updates(lg)
                  if e.kind == EventKind.TOWN_UPDATE and e.payload.get("population") == 0]
        assert len(deaths) == 1
        assert deaths[0].payload["id"] == 2
        assert deaths[0].visible_to == {0}

    def test_unobserved_death_silent(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 500, 0)])  # self-observed while alive
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        w.armies = []  # dies 500 km from the only watcher
        lg.generate(w, turn=6, line_of_sight=LOS)
        deaths = [e for e in _updates(lg) if e.payload.get("alive") is False]
        assert deaths == []

    def test_reappearing_id_stays_coherent(self) -> None:
        # Ids are never reused (world rule); if one ever reappears the
        # ledger treats it as live again — no second death, no corruption.
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 100, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=LOS)
        w.armies = []
        lg.generate(w, turn=6, line_of_sight=LOS)
        w.armies = [_army(7, 100, 0)]
        lg.generate(w, turn=7, line_of_sight=LOS)
        deaths = [e for e in _updates(lg) if e.payload.get("alive") is False]
        assert len(deaths) == 1
        live = [e for e in _updates(lg)
                if e.kind == EventKind.ARMY_UPDATE and e.payload.get("alive") is True and e.turn == 7]
        assert len(live) == 1


class TestDelayAndS:
    def test_delay_exact_not_floor(self) -> None:
        # 160 km at info 150: released at S+1.07 — absent at S+1, present at S+2.
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 160, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=5, line_of_sight=200.0)
        assert [e for e in lg.query(0, 0.0, 0.0, now=6.0)
                if e.kind == EventKind.ARMY_UPDATE] == []
        got = [e for e in lg.query(0, 0.0, 0.0, now=7.0)
               if e.kind == EventKind.ARMY_UPDATE]
        assert len(got) == 1

    def test_pre_S_entry_never_delivers_post_S(self) -> None:
        # The 160 km transient: watched at S-1, unwatched ever after.
        w = _world(towns=[_town(1, 0, 0, cap=True), _town(2, 160, 0, faction=1)],
                   armies=[_army(7, 160, 0, faction=0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=4, line_of_sight=LOS)  # watched at S-1
        w.armies = []  # watcher leaves; target unwatched from S on
        lg.set_landing(0, 5)
        lg.generate(w, turn=5, line_of_sight=LOS)
        lg.generate(w, turn=6, line_of_sight=LOS)
        ids = {e.payload["id"] for e in lg.query(0, 0.0, 0.0, now=7.0)}
        assert 2 not in ids  # transient NEVER known

    def test_S_observation_delivers(self) -> None:
        # Same geometry, watcher stays: t>=S entries arrive at S+ceil(d/info).
        w = _world(towns=[_town(1, 0, 0, cap=True), _town(2, 160, 0, faction=1)],
                   armies=[_army(7, 160, 0, faction=0)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=4, line_of_sight=LOS)
        lg.set_landing(0, 5)
        lg.generate(w, turn=5, line_of_sight=LOS)
        ids = {e.payload["id"] for e in lg.query(0, 0.0, 0.0, now=7.0)}
        assert 2 in ids

    def test_set_landing_stores_turn(self) -> None:
        lg = Ledger(CFG.info_speed, 1414)
        assert lg.S.get(0, 0) == 0
        lg.set_landing(0, 5)
        assert lg.S[0] == 5

    def test_never_landed_unaffected(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=0, line_of_sight=LOS)
        lg.generate(w, turn=1, line_of_sight=LOS)
        assert len(lg.query(0, 0.0, 0.0, now=1.0)) == 2


class TestMemory:
    def test_windowed(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)  # window ≈ 9.4 turns
        for t in range(30):
            lg.generate(w, turn=t, line_of_sight=LOS)
            lg.evict(now=float(t))
        # ≤ 11 turns' worth of entries: nothing grows with game length.
        assert len(lg.events) <= 11


class TestConfig:
    def test_line_of_sight_defaults_to_info_speed(self) -> None:
        assert GameConfig().line_of_sight == 150.0
