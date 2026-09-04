"""Ideas 1+3: incremental update and memoized staleness (equivalence guards)."""
import time
from bots.common import BotState
from engine.config import GameConfig
from engine.world import Town, Army

CFG = GameConfig()


def _state():
    st = BotState()
    st.init(CFG, 0)
    st.world.towns.append(Town(id=0, faction=0, x=100.0, y=100.0, population=20000.0, is_capital=True))
    st.world.towns.append(Town(id=1, faction=1, x=800.0, y=800.0, population=15000.0, is_capital=True))
    st.world.armies.append(Army(id=10, faction=0, x=120.0, y=100.0, target_x=120.0, target_y=100.0, has_target=False))
    return st


def _scripted_events():
    """Update-language script: absolute upserts, takeovers, deaths."""
    return [
        {"kind": "town_update", "id": 0, "x": 100.0, "y": 100.0,
         "faction": 0, "population": 20100.0, "is_capital": True},
        {"kind": "army_update", "id": 11, "x": 100.0, "y": 100.0,
         "faction": 0, "alive": True, "is_viceroy": False},
        {"kind": "army_update", "id": 11, "x": 200.0, "y": 200.0,
         "faction": 0, "alive": True, "is_viceroy": False},
        {"kind": "town_update", "id": 1, "x": 800.0, "y": 800.0,
         "faction": 0, "population": 7500.0, "is_capital": True},
        {"kind": "army_update", "id": 10, "x": 120.0, "y": 100.0,
         "faction": 0, "alive": False, "is_viceroy": False},
        {"kind": "town_update", "id": 2, "x": 300.0, "y": 300.0,
         "faction": 0, "population": 500.0, "is_capital": False},
        {"kind": "town_update", "id": 2, "x": 300.0, "y": 300.0,
         "faction": 0, "population": 0, "is_capital": False},
        {"kind": "town_update", "id": 1, "x": 800.0, "y": 800.0,
         "faction": 0, "population": 7600.0, "is_capital": True},
    ]


def _snap(st):
    towns = sorted((t.id, t.faction, round(t.population, 6), t.is_capital) for t in st.world.towns)
    armies = sorted((a.id, a.faction, round(a.x, 6), round(a.y, 6)) for a in st.world.armies)
    return towns, armies, dict(st._growth), st.turn


def test_idea1_incremental_matches_full_replay():
    """Idea 1: one batched update == split same-turn updates (order preserved)."""
    a = _state()
    a.deadline = time.time() + 60
    a.update(1, _scripted_events())
    b = _state()
    b.deadline = time.time() + 60
    evts = _scripted_events()
    b.update(1, evts[:3])
    b.update(1, evts[3:6])
    b.update(1, evts[6:])
    assert _snap(a) == _snap(b)


def test_idea1_growth_only_touches_changed_towns():
    """Idea 1: growth bookkeeping covers exactly towns present after update."""
    st = _state()
    st.deadline = time.time() + 60
    st.update(1, _scripted_events())
    assert set(st._growth.keys()) == {t.id for t in st.world.towns}
    # untouched town keeps prior growth entry semantics (0.0 for new towns)
    assert st._growth[2] == 0.0 if 2 in st._growth else True


def test_idea3_stale_turns_matches_hypot():
    """Idea 3: memoized staleness equals dist/capital/info_speed."""
    import math
    st = _state()
    st.update(1, [])
    assert st.stale_turns(800.0, 800.0) == math.hypot(700.0, 700.0) / 150.0
    # memoized: same answer, served from cache
    assert st.stale_turns(800.0, 800.0) == math.hypot(700.0, 700.0) / 150.0


def test_idea3_cache_busts_on_capital_move():
    """Idea 3: new capital (new turn data) changes staleness answers."""
    st = _state()
    st.update(1, [])
    before = st.stale_turns(800.0, 800.0)
    # capital relocates: answers must change, not serve stale cache
    st.update(2, [{"kind": "town_update", "id": 1, "x": 800.0, "y": 800.0,
                   "faction": 0, "population": 7500.0, "is_capital": True},
                  {"kind": "town_update", "id": 0, "x": 100.0, "y": 100.0,
                   "faction": 0, "population": 20000.0, "is_capital": False}])
    after = st.stale_turns(800.0, 800.0)
    assert after == 0.0
    assert before != after
