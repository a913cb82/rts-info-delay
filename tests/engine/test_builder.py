"""Phase 2 — tag-aware delivery builder (tests).

Pure fn (ledger, faction, send-state, S, capital-now, now) -> wire updates.
Reference semantics: Ledger.query gates (TAG + DELAY + S), plus latest-only
per entity per payload and send-state diffing (slim wire).
"""
import json

from engine.config import GameConfig
from engine.delivery import SendState, build_updates
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


def _gen(lg, w, turn, los=LOS):
    lg.generate(w, turn=turn, line_of_sight=los)


def _build(lg, faction, state, S, capital, now):
    return build_updates(lg, faction, state, S, capital, now)


class TestShapes:
    def test_town_update_wire_shape(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        (u,) = _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0)
        assert u == {"kind": "town_update", "id": 1, "x": 0.0, "y": 0.0,
                     "faction": 0, "population": 2000, "is_capital": True}

    def test_army_update_wire_shape(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 10, 0, viceroy=True)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        got = {u["id"]: u for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0)
               if u["kind"] == "army_update"}
        assert got[7] == {"kind": "army_update", "id": 7, "x": 10.0, "y": 0.0,
                          "faction": 0, "alive": True, "is_viceroy": True}

    def test_no_intent_fields(self) -> None:
        # D1 decided: destinations never go over the wire.
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 10, 0)])
        w.armies[0].target_x, w.armies[0].target_y, w.armies[0].has_target = 500.0, 0.0, True
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0):
            assert "target_x" not in u and "has_target" not in u


class TestSendOnce:
    def test_second_identical_call_silent(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 10, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        state = SendState()
        first = _build(lg, 0, state, 0, (0.0, 0.0), 6.0)
        assert len(first) == 2
        assert _build(lg, 0, state, 0, (0.0, 0.0), 6.0) == []

    def test_changed_emits_unchanged_silent(self) -> None:
        w = _world(towns=[_town(1, 0, 0, pop=2000.0, cap=True),
                          _town(2, 100, 0, pop=2000.0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        state = SendState()
        assert len(_build(lg, 0, state, 0, (0.0, 0.0), 6.0)) == 2
        w.towns[1].population = 2100.0
        _gen(lg, w, 6)
        got = _build(lg, 0, state, 0, (0.0, 0.0), 7.0)
        assert [u["id"] for u in got] == [2]

    def test_newest_wins_three_eligible_one_delivered(self) -> None:
        # Uniqueness: window holds three passing entries for one entity —
        # exactly one update (the newest) goes out.
        w = _world(towns=[_town(1, 0, 0, pop=2000.0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        for t, pop in ((5, 2000.0), (6, 2100.0), (7, 2200.0)):
            w.towns[0].population = pop
            _gen(lg, w, t)
        got = _build(lg, 0, SendState(), 0, (0.0, 0.0), 7.0)
        assert len(got) == 1
        assert got[0]["population"] == 2200

    def test_known_death_emits_once_then_silent(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 100, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        state = SendState()
        _build(lg, 0, state, 0, (0.0, 0.0), 5.0)
        w.armies = []
        _gen(lg, w, 6)
        got = _build(lg, 0, state, 0, (0.0, 0.0), 7.0)
        assert [u for u in got if u["kind"] == "army_update"] == [
            {"kind": "army_update", "id": 7, "x": 100.0, "y": 0.0,
             "faction": 0, "alive": False, "is_viceroy": False}]
        assert _build(lg, 0, state, 0, (0.0, 0.0), 7.0) == []

    def test_unknown_death_emits_once_for_tolerance(self) -> None:
        # A death for an entity never delivered still goes out once (differs
        # from nothing); the parser ignores unknown removals.
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 100, 0, faction=1)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        state = SendState()
        _build(lg, 0, state, 0, (0.0, 0.0), 5.0)  # live foe held by delay
        w.armies = []
        _gen(lg, w, 6)
        got = _build(lg, 0, state, 0, (0.0, 0.0), 7.0)
        deaths = [u for u in got if u.get("alive") is False]
        assert len(deaths) == 1
        assert deaths[0]["id"] == 7
        assert _build(lg, 0, state, 0, (0.0, 0.0), 7.0) == []


class TestGates:
    def test_delay_holds_then_releases(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 160, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5, los=200.0)
        state = SendState()
        assert [u for u in _build(lg, 0, state, 0, (0.0, 0.0), 6.0)
                if u["kind"] == "army_update"] == []
        got = [u for u in _build(lg, 0, state, 0, (0.0, 0.0), 7.0)
               if u["kind"] == "army_update"]
        assert len(got) == 1  # released S+1.07, present S+2

    def test_capital_move_shifts_release(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 300, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5, los=400.0)
        state = SendState()
        # From (0,0): release at 5+2=7. From (150,0): release at 5+1=6.
        assert [u for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0)
                if u["kind"] == "army_update"] == []
        got = [u for u in _build(lg, 0, state, 0, (150.0, 0.0), 6.0)
               if u["kind"] == "army_update"]
        assert len(got) == 1

    def test_pre_S_excluded(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 4)
        _gen(lg, w, 5)
        got = _build(lg, 0, SendState(), 5, (0.0, 0.0), 6.0)
        assert [u["id"] for u in got] == [1]
        assert lg.events[0].turn == 4  # the t=4 entry stayed home

    def test_delay_epsilon(self) -> None:
        # t + dist/info exactly == now delivers (1e-9 convention).
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 150, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5, los=200.0)
        assert len([u for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0)
                    if u["kind"] == "army_update"]) == 1
        assert [u for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0 - 2e-9)
                if u["kind"] == "army_update"] == []


class TestFogPipeline:
    def test_outside_silent_inside_delivers(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True), _town(2, 500, 0, faction=1)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        ids = {u["id"] for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 5.0)}
        assert ids == {1}  # foe town outside every fac0 disc

    def test_anchor_shapes(self) -> None:
        # Town-only, army-only, and mixed anchors all observe.
        for anchors in ({"towns": [(50, 0, 0)], "armies": []},
                        {"towns": [], "armies": [(50, 0, 0)]},
                        {"towns": [(50, 0, 0)], "armies": [(60, 0, 0)]}):
            w = _world(
                towns=[_town(1, 0, 0, cap=True),
                       _town(2, 100, 0, faction=1)] +
                      [_town(10 + i, x, y, faction=f) for i, (x, y, f) in enumerate(anchors["towns"])],
                armies=[_army(20 + i, x, y, faction=f) for i, (x, y, f) in enumerate(anchors["armies"])])
            lg = Ledger(CFG.info_speed, 1414)
            _gen(lg, w, 5)
            ids = {u["id"] for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0)}
            assert 2 in ids, anchors

    def test_own_entities_always(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 140, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        ids = {u["id"] for u in _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0)}
        assert ids == {1, 7}


class TestEpochs:
    def test_factions_independent(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True),
                          _town(2, 500, 0, faction=1, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        s0 = SendState()
        s1 = SendState()
        assert {u["id"] for u in _build(lg, 0, s0, 0, (0.0, 0.0), 5.0)} == {1}
        assert {u["id"] for u in _build(lg, 1, s1, 0, (500.0, 0.0), 5.0)} == {2}
        # Same turn, same ledger, neither disturbs the other.
        assert _build(lg, 0, s0, 0, (0.0, 0.0), 5.0) == []
        assert _build(lg, 1, s1, 0, (500.0, 0.0), 5.0) == []

    def test_time_shifted_observation(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True), _town(2, 500, 0, faction=1, cap=True),
                          _town(3, 300, 0, faction=2)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)  # fac0 sees town 3 (300? no — 300 > 150, self only)
        w.armies.append(_army(7, 300, 0, faction=0))  # scout arrives t6
        _gen(lg, w, 6)
        _gen(lg, w, 10)
        s0 = SendState()
        got = {u["id"]: u for u in _build(lg, 0, s0, 0, (0.0, 0.0), 10.0)}
        assert 3 in got  # first delivered now, current truth
        assert got[3]["faction"] == 2

    def test_no_reseed_property(self) -> None:
        # Scripted window with pre-S entries: nothing older than S goes out.
        w = _world(towns=[_town(1, 0, 0, pop=2000.0, cap=True)])
        lg = Ledger(CFG.info_speed, 1414)
        for t in range(1, 11):
            w.towns[0].population = 2000.0 + 10 * t
            _gen(lg, w, t)
        got = _build(lg, 0, SendState(), 8, (0.0, 0.0), 12.0)
        assert len(got) == 1
        assert got[0]["population"] == 2100  # newest passing entry wins

    def test_deterministic_bytes(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True), _town(2, 100, 0, faction=1)],
                   armies=[_army(7, 140, 0), _army(8, 120, 0, faction=1)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        a = json.dumps(_build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0), sort_keys=True)
        b = json.dumps(_build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0), sort_keys=True)
        assert a == b

    def test_empty_world(self) -> None:
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, _world(), 5)
        assert _build(lg, 0, SendState(), 0, (0.0, 0.0), 5.0) == []

    def test_no_capital_fallback_geometry(self) -> None:
        # Builder takes capital xy as a param; (0,0) fallback works.
        w = _world(towns=[_town(1, 100, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        got = _build(lg, 0, SendState(), 0, (0.0, 0.0), 6.0)
        assert [u["id"] for u in got] == [1]  # 100/150 < 1 turn


class TestCounterIntel:
    def test_foe_observes_marching_viceroy(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True),
                          _town(2, 500, 0, faction=1, cap=True)],
                   armies=[_army(7, 490, 0, faction=0, viceroy=True)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5)
        foe = {u["id"]: u for u in _build(lg, 1, SendState(), 0, (500.0, 0.0), 6.0)}
        assert foe[7]["is_viceroy"] is True

    def test_founding_birth_carries_capital_flag(self) -> None:
        w = _world(towns=[_town(1, 0, 0, cap=True),
                          _town(9, 200, 0, faction=0, cap=True)],
                   armies=[_army(7, 200, 0, faction=1)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 5, los=250.0)
        foe = {u["id"]: u for u in _build(lg, 1, SendState(), 0, (0.0, 0.0), 7.0)}
        assert foe[9]["is_capital"] is True


class TestFirstTurn:
    def test_full_json_turn1(self) -> None:
        import json as _json
        data = _json.load(open("maps/full.json"))
        cfg = GameConfig.from_dict(data)
        w = World()
        w.map_size = data.get("map_size", [1000, 1000])
        w.parse_map(data["map"])
        lg = Ledger(cfg.info_speed, 1414)
        _gen(lg, w, 1, los=cfg.line_of_sight)
        # Every faction's first payload contains its own capital.
        for t in w.towns:
            if not t.is_capital:
                continue
            got = {u["id"]: u for u in _build(lg, t.faction, SendState(), 0, (t.x, t.y), 1.0)}
            assert t.id in got, f"faction {t.faction} missing own capital"
            assert got[t.id]["is_capital"] is True


class TestDifferential:
    def test_fast_matches_scan_on_messy_fixture(self) -> None:
        # The numba kernel must agree with the reference scan bit-for-bit:
        # moves (incl. boundary), deaths (watched + unwatched), pop changes,
        # captures, S jumps, capital moves.
        from engine.delivery import SendState, build_updates_scan
        w = _world(towns=[_town(1, 0, 0, pop=2000.0, cap=True),
                          _town(2, 90, 120, faction=1, pop=2000.0),  # exactly at LOS
                          _town(3, 400, 0, faction=1, pop=3000.0)],
                   armies=[_army(7, 140, 0), _army(8, 500, 0, faction=1)])
        lg = Ledger(CFG.info_speed, 1414)
        _gen(lg, w, 1)
        w.armies[0].x = 200.0  # march out (160 km transient geometry)
        w.towns[0].population = 2050.0
        _gen(lg, w, 2)
        w.armies = [w.armies[0]]  # unwatched foe death (500 km from all)
        w.towns[2].faction = 0  # capture
        w.towns[2].population = 1500.0
        _gen(lg, w, 3)
        lg.set_landing(0, 3)
        w.armies.append(_army(9, 10, 0, faction=1))  # new foe scout
        _gen(lg, w, 4)
        for faction, S, capital, now in ((0, 0, (0.0, 0.0), 4.0),
                                         (0, 3, (0.0, 0.0), 5.0),
                                         (0, 3, (150.0, 0.0), 5.0),
                                         (1, 0, (400.0, 0.0), 4.0),
                                         (1, 0, (0.0, 0.0), 2.0)):
            a = json.dumps(build_updates_scan(lg, faction, {}, S, capital, now), sort_keys=True)
            b = json.dumps(_build(lg, faction, SendState(), S, capital, now), sort_keys=True)
            assert a == b, (faction, S, capital, now)


class TestMovementStreams:
    def test_marching_army_streams_positions(self) -> None:
        # REGRESSION (void_settle): dedup compared payloads only, and
        # army payloads carry no position — every move after the first
        # delivered snapshot was swallowed as "same value". Marching
        # armies must stream (x, y); arrival must arrive.
        w = _world(towns=[_town(1, 200, 500, cap=True)],
                   armies=[_army(7, 200, 500)])
        lg = Ledger(CFG.info_speed, 1414)
        st = SendState()
        seen: list[tuple] = []
        a = w.armies[0]
        for t in range(1, 8):
            a.x += 10.0  # 10km/turn march east (stays near capital: delay 1)
            _gen(lg, w, t)
            lg.evict(float(t))
            for u in _build(lg, 0, st, 0, (200.0, 500.0), float(t)):
                if u["kind"] == "army_update":
                    seen.append((round(u["x"]), round(u["y"])))
        # Six, not seven: exact-delay release means the now-turn's own
        # snapshot (270 at t7: 7 + 70/150 > 7) is never yet due — the
        # stream trails truth by the delay, it must not gap.
        assert seen == [(210, 500), (220, 500), (230, 500), (240, 500),
                        (250, 500), (260, 500)]

    def test_stationary_army_stays_silent(self) -> None:
        # The dedup fix must not re-break slim wire: static entities send
        # once, then silence (warm steady-state ~empty).
        w = _world(towns=[_town(1, 0, 0, cap=True)],
                   armies=[_army(7, 10, 0)])
        lg = Ledger(CFG.info_speed, 1414)
        st = SendState()
        _gen(lg, w, 5)
        n1 = len(_build(lg, 0, st, 0, (0.0, 0.0), 6.0))
        _gen(lg, w, 6)
        n2 = len(_build(lg, 0, st, 0, (0.0, 0.0), 7.0))
        assert (n1, n2) == (2, 0)
