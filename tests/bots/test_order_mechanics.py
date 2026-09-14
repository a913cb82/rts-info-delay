"""Order mechanics (exploit foundations; PRESEND.md claims as tests).

Messenger delivery is pure distance-countdown (no chasing); MOVE_TO
hijacks marching armies; BUILD drops unless landed; delivery precedes
movement each turn.
"""
from engine.config import GameConfig
from engine.step import step
from engine.world import Army, Town, World


def _cfg(**kw):
    d = {"map_size": [1000, 1000], "max_turns": 100, "info_speed": 150.0,
         "army_speed": 50.0, "army_cost": 1000, "interact_radius": 10.0,
         "build_efficiency": 0.9, "capture_loss": 0.5, "max_train_frac": 1.0,
         "turn_time_ms": 1000, "time_increment_ms": 100,
         "town_min_population": 10.0}
    d.update(kw)
    return GameConfig.from_dict(d)


def _world():
    w = World()
    w.towns.append(Town(id=1, faction=0, x=500.0, y=500.0,
                        population=600.0, is_capital=True))
    w.mark_dirty()
    return w


def test_messenger_counts_down_no_chase():
    # order to an army 300km from capital: 2 turns to deliver even if the
    # army marches away the whole time.
    cfg = _cfg()
    # 300km needs 2 turns at 150/turn, even if the army marches away.
    w2 = _world()
    w2.armies.append(Army(id=10, faction=0, x=800.0, y=500.0, size=50.0,
                          target_x=950.0, target_y=500.0, has_target=True))
    w2.mark_dirty()
    step(w2, cfg, None, 1, {0: ["MOVE_TO 10 800.0 500.0 100.0 100.0"]})
    a2 = w2.get_army(10)
    # remaining 300-150=150 > 0: not delivered, still old target
    assert (a2.target_x, a2.target_y) == (950.0, 500.0)
    # turn 2: countdown hits 0 but the army marched on (stale from drops)
    step(w2, cfg, None, 2, {})
    assert (a2.target_x, a2.target_y) == (950.0, 500.0)


def test_move_to_hijacks():
    # idle army (from == pos): retargets.
    cfg = _cfg()
    w = _world()
    w.armies.append(Army(id=10, faction=0, x=510.0, y=500.0, size=50.0))
    w.mark_dirty()
    step(w, cfg, None, 1, {0: ["MOVE_TO 10 510.0 500.0 100.0 100.0"]})
    a = w.get_army(10)
    assert (a.target_x, a.target_y) == (100.0, 100.0)


def test_move_to_marching_needs_projected_from():
    # marching army: stale from-pos DROPS; projected from-pos (one
    # speed-step along its current target) delivers.
    cfg = _cfg()
    w = _world()
    w.armies.append(Army(id=10, faction=0, x=510.0, y=500.0, size=50.0,
                         target_x=900.0, target_y=500.0, has_target=True))
    w.mark_dirty()
    step(w, cfg, None, 1, {0: ["MOVE_TO 10 510.0 500.0 100.0 100.0"]})
    a = w.get_army(10)
    assert (a.target_x, a.target_y) == (900.0, 500.0), "stale from drops"
    w2 = _world()
    w2.armies.append(Army(id=10, faction=0, x=510.0, y=500.0, size=50.0,
                          target_x=900.0, target_y=500.0, has_target=True))
    w2.mark_dirty()
    # projected: 510+50 along (900,500) = (560,500)
    step(w2, cfg, None, 1, {0: ["MOVE_TO 10 560.0 500.0 100.0 100.0"]})
    a2 = w2.get_army(10)
    assert (a2.target_x, a2.target_y) == (100.0, 100.0)


def test_build_drops_unless_landed():
    cfg = _cfg()
    w = _world()
    w.armies.append(Army(id=10, faction=0, x=510.0, y=500.0, size=50.0,
                         target_x=900.0, target_y=500.0, has_target=True))
    w.mark_dirty()
    step(w, cfg, None, 1, {0: ["BUILD 10 900.0 500.0 50.0"]})
    assert not any(so.command.name == "BUILD" for so in w.standing_orders)
    assert len(w.towns) == 1


def test_build_executes_when_landed():
    cfg = _cfg()
    w = _world()
    w.armies.append(Army(id=10, faction=0, x=600.0, y=500.0, size=50.0))
    w.mark_dirty()
    step(w, cfg, None, 1, {0: ["BUILD 10 600.0 500.0 50.0"]})
    step(w, cfg, None, 2, {})
    assert len(w.towns) == 2
