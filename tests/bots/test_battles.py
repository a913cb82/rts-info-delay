"""Battle mechanics (cohesion doctrine as tests).

Weakness = total enemy size in range; an army dies if any enemy in range
has weakness <= its own (M>=N+1 kills clean). Cross-faction capture ties
standoff. Co-located same-faction idles merge (lower id survives).
"""
from engine.combat import compute_weaknesses, resolve_captures, resolve_combat, resolve_merges
from engine.config import GameConfig
from engine.world import Army, Town, World


def _cfg(**kw):
    d = {"map_size": [1000, 1000], "max_turns": 100, "info_speed": 150.0,
         "army_speed": 50.0, "army_cost": 1000, "interact_radius": 10.0,
         "build_efficiency": 0.9, "capture_loss": 0.5, "max_train_frac": 0.1,
         "turn_time_ms": 1000, "time_increment_ms": 100,
         "town_min_population": 10.0}
    d.update(kw)
    return GameConfig.from_dict(d)


def _w():
    w = World()
    w.mark_dirty()
    return w


def test_overmatch_kills_clean():
    cfg, w = _cfg(), _w()
    w.armies.append(Army(id=1, faction=0, x=500.0, y=500.0, size=100.0))
    w.armies.append(Army(id=2, faction=1, x=505.0, y=500.0, size=60.0))
    w.mark_dirty()
    evs, _ = resolve_combat(w, cfg)
    ids = [a.id for a in w.armies]
    assert 1 in ids and 2 not in ids, "100 vs 60: bigger lives"
    assert any(e.get("kind") == "battle" for e in evs)


def test_undermatch_dies():
    cfg, w = _cfg(), _w()
    w.armies.append(Army(id=1, faction=0, x=500.0, y=500.0, size=40.0))
    w.armies.append(Army(id=2, faction=1, x=505.0, y=500.0, size=100.0))
    w.mark_dirty()
    resolve_combat(w, cfg)
    ids = [a.id for a in w.armies]
    assert 2 in ids and 1 not in ids


def test_capture_tie_across_factions_stands_off():
    cfg, w = _cfg(), _w()
    w.towns.append(Town(id=1, faction=0, x=500.0, y=500.0,
                        population=600.0, is_capital=False))
    w.armies.append(Army(id=10, faction=1, x=502.0, y=500.0, size=100.0))
    w.armies.append(Army(id=11, faction=2, x=498.0, y=500.0, size=100.0))
    w.mark_dirty()
    evs = resolve_captures(w, cfg)
    assert w.get_town(1).faction == 0, "cross-faction tie: no capture"
    assert not any(e.get("kind") == "town_capture" for e in evs)


def test_idles_merge_lower_id_survives():
    cfg, w = _cfg(), _w()
    w.armies.append(Army(id=5, faction=0, x=500.0, y=500.0, size=30.0))
    w.armies.append(Army(id=3, faction=0, x=500.0, y=500.0, size=40.0))
    w.mark_dirty()
    resolve_merges(w, cfg)
    assert len(w.armies) == 1 and w.armies[0].id == 3
    assert abs(w.armies[0].size - 70.0) < 1e-6
