"""Phase 3 — wire-up E2E: flight, landing, S-rule at run-loop level.

Drives step() + runner.deliver() in run_game order (payloads pre-step,
landing detection post-step). No subprocesses: deterministic and fast.
"""
from engine.config import GameConfig
from engine.delivery import SendState
from engine.ledger import EventKind, Ledger
from engine.world import Army, Town, World
from runner.main import deliver, note_landing

CFG = GameConfig()


def _world():
    # Geometry: the viceroy flies (0,0)->(150,100); nothing hostile sits on
    # its path (closest approach to town 2 ~= 55 km). Scout watches the
    # target; foe9 duels it T2; army 10 captures town 2 T2. All mid-flight.
    w = World()
    w.map_size = [1000, 1000]
    w.towns = [
        Town(id=1, faction=0, x=0, y=0, population=5000, is_capital=True),
        Town(id=2, faction=0, x=100, y=0, population=2000, is_capital=False),
        Town(id=3, faction=1, x=250, y=0, population=5000, is_capital=True),
    ]
    w.armies = [
        Army(id=7, faction=0, x=150, y=100),   # fac0 scout at the target site
        Army(id=9, faction=1, x=120, y=20),    # foe marcher (transient + battle)
        Army(id=10, faction=1, x=110, y=0),    # foe capturer (takes town 2 mid-flight)
    ]
    return w


def _cap(w, faction):
    c = w.faction_capital(faction)
    return (c.x, c.y) if c else (0.0, 0.0)


def _assert_uniform(updates, ledger, S):
    """Every delivered update matches a ledger entry with turn >= S."""
    entries = [e for e in ledger.events
               if e.kind in (EventKind.TOWN_UPDATE, EventKind.ARMY_UPDATE)]
    for u in updates:
        wire = {"id": u["id"]} | {k: v for k, v in u.items() if k not in ("kind", "id", "x", "y")}
        ok = any(e.payload == wire and e.turn >= S
                 and (("town" if e.kind == EventKind.TOWN_UPDATE else "army",
                       e.payload["id"]) == ("town" if u["kind"] == "town_update" else "army",
                                            u["id"]))
                 for e in entries)
        assert ok, f"non-uniform update: {u}"


class TestFlightE2E:
    def test_evac_mute_land_resume(self) -> None:
        from engine.step import step
        w = _world()
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=0, line_of_sight=CFG.line_of_sight)  # pre-game (run_game invariant)
        st = {0: SendState(), 1: SendState()}
        seen = {0: [], 1: []}  # (turn, payload) for stream-jump checks

        def payloads(turn):
            out = {}
            for f in (0, 1):
                out[f] = deliver(f, w, lg, turn, st[f])
                if out[f]:
                    seen[f].append(turn)
            return out

        # T1: order evac + foe march; normal payloads pre-step.
        p1 = payloads(1)
        assert p1[0], "T1 payload present pre-flight"
        e1 = step(w, CFG, lg, turn=1,
                  orders={0: ["MOVE_CAPITAL 150 100"],
                          1: ["MOVE_TO 10 110 0 100 0", "MOVE_TO 9 120 20 150 100"]})
        assert note_landing(e1, 0, 1, lg, st[0]) is False
        # T2: muted (viceroy marching); scout-foe duel + capture happen.
        p2 = payloads(2)
        assert p2[0] == [], "muted in flight"
        e2 = step(w, CFG, lg, turn=2, orders={})
        assert note_landing(e2, 0, 2, lg, st[0]) is False
        # T3-T4: still muted (arrival is T5 movement; 180 km at 50/turn).
        for t, ev in ((3, None), (4, None)):
            p = payloads(t)
            assert p[0] == [], "muted in flight"
            e = step(w, CFG, lg, turn=t, orders={})
            assert note_landing(e, 0, t, lg, st[0]) is False
        # T5: arrival + founding in economy.
        p5 = payloads(5)
        assert p5[0] == [], "muted until founded"
        e5 = step(w, CFG, lg, turn=5, orders={})
        assert note_landing(e5, 0, 5, lg, st[0]) is True
        assert lg.S[0] == 5
        # T6: stream resumes with a jump; S-rule only.
        p6 = payloads(6)
        assert p6[0], "payload resumes after landing"
        assert seen[0] == [1, 6], f"success jumps 1->6, got {seen[0]}"
        by_id = {u["id"]: u for u in p6[0]}
        # New capital announced as capital.
        caps = [u for u in p6[0] if u.get("is_capital") and u["faction"] == 0]
        assert len(caps) == 1 and (caps[0]["x"], caps[0]["y"]) == (150.0, 100.0)
        # Capture during flight arrives as S-observation (faction 1).
        assert by_id[2]["faction"] == 1
        # Scout + foe died mid-flight (1v1 at the site, T2): neither the
        # live armies nor their deaths ever arrive post-S.
        assert 7 not in by_id and 9 not in by_id
        # Exactly one death delivers: the consumed viceroy (tombstone at the
        # founding site, turn S, observed at dist 0 — uniform rule, no
        # exception; the wiped bot never knew it, so the parser ignores it).
        # Scout + foe tombstones are pre-S and never arrive.
        deaths = [u for u in p6[0] if u.get("alive") is False]
        assert len(deaths) == 1, deaths
        assert deaths[0]["id"] not in (7, 9)
        # Uniform rule: everything first delivered post-S was generated then.
        _assert_uniform(p6[0], lg, 5)

    def test_failed_order_keeps_stream(self) -> None:
        # Capital captured before the intent executes (O9c): the order fails,
        # no flight ever happens, stream stays sequential, S untouched.
        from engine.step import step
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=0, y=0, population=5000, is_capital=True),
                   Town(id=2, faction=0, x=100, y=0, population=2000, is_capital=False)]
        w.armies = [Army(id=9, faction=1, x=5, y=0)]
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=0, line_of_sight=CFG.line_of_sight)
        st = SendState()
        p1 = deliver(0, w, lg, 1, st)
        assert p1, "T1 pre-step payload present"
        e1 = step(w, CFG, lg, turn=1, orders={0: ["MOVE_CAPITAL 150 0"]})
        assert note_landing(e1, 0, 1, lg, st) is False
        assert not [a for a in w.armies if a.is_viceroy], "intent dropped, no viceroy"
        p2 = deliver(0, w, lg, 2, st)
        assert p2, "T2 payload normal (no mute without flight)"
        assert lg.S.get(0, 0) == 0

    def test_note_landing_resets_send_state(self) -> None:
        w = _world()
        lg = Ledger(CFG.info_speed, 1414)
        st = SendState()
        st.snaps[("town", 1)] = {"id": 1}
        ev = [{"kind": "town_spawn", "id": 9, "faction": 0, "x": 150.0,
               "y": 0.0, "is_capital": True}]
        assert note_landing(ev, 0, 4, lg, st) is True
        assert lg.S[0] == 4
        assert st.snaps == {}
        # Wrong faction: untouched.
        st.snaps[("town", 1)] = {"id": 1}
        assert note_landing(ev, 1, 4, lg, st) is False
        assert st.snaps == {("town", 1): {"id": 1}}


class TestLoopPins:
    def test_stationary_reannounces_after_reset(self) -> None:
        # The reset counterpart: a town unchanged for 100 turns re-announces
        # exactly once post-S (stagnant-town hole closed).
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=0, y=0, population=2000, is_capital=True)]
        lg = Ledger(CFG.info_speed, 1414)
        st = SendState()
        for t in range(1, 50):
            lg.generate(w, turn=t, line_of_sight=150.0)
            deliver(0, w, lg, t, st)
        lg.set_landing(0, 50)
        st.reset()
        lg.generate(w, turn=50, line_of_sight=150.0)
        got = deliver(0, w, lg, 50, st)
        assert [u["id"] for u in got] == [1]
        assert deliver(0, w, lg, 50, st) == []

    def test_stationary_appears_at_exact_release(self) -> None:
        # Armies unmoved for 100 turns appear at exactly S+ceil(dist/info).
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=0, y=0, population=2000, is_capital=True)]
        w.armies = [Army(id=7, faction=0, x=160, y=0),
                    Army(id=8, faction=0, x=310, y=0)]
        lg = Ledger(CFG.info_speed, 1414)
        lg.set_landing(0, 10)
        for t in range(10, 115):
            lg.generate(w, turn=t, line_of_sight=500.0)
        st = SendState()
        assert 7 not in {u["id"] for u in deliver(0, w, lg, 11, st)}  # 160km: S+2
        st = SendState()
        assert 7 in {u["id"] for u in deliver(0, w, lg, 12, st)}
        st = SendState()
        assert 8 not in {u["id"] for u in deliver(0, w, lg, 12, st)}  # 310km: S+3
        st = SendState()
        assert 8 in {u["id"] for u in deliver(0, w, lg, 13, st)}

    def test_fog_purity(self) -> None:
        # Never observed => never delivered, over a whole game.
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=0, y=0, population=2000, is_capital=True),
                   Town(id=2, faction=1, x=900, y=900, population=2000, is_capital=True)]
        lg = Ledger(CFG.info_speed, 1414)
        st = SendState()
        seen = set()
        for t in range(1, 21):
            lg.generate(w, turn=t, line_of_sight=150.0)
            for u in deliver(0, w, lg, t, st):
                seen.add(u["id"])
        assert 2 not in seen
        assert 1 in seen


class TestDeliver:
    def test_flight_returns_empty(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        w.towns = [Town(id=1, faction=0, x=0, y=0, population=2000, is_capital=False)]
        w.armies = [Army(id=7, faction=0, x=0, y=0, is_viceroy=True)]
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=1, line_of_sight=150.0)
        assert deliver(0, w, lg, 1, SendState()) == []

    def test_no_capital_uses_origin(self) -> None:
        w = World()
        w.map_size = [1000, 1000]
        w.armies = [Army(id=7, faction=0, x=100, y=0)]
        lg = Ledger(CFG.info_speed, 1414)
        lg.generate(w, turn=1, line_of_sight=150.0)
        got = deliver(0, w, lg, 2, SendState())
        assert [u["id"] for u in got if u["kind"] == "army_update"] == [7]
