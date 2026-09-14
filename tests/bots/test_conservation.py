"""Conservation mechanics (design-on-truth foundations).

TRAIN capped 10% + 1/town/turn (extras discarded); BUILD pays 0.9;
captures halve pop + know-how; viceroy is score-neutral relocation.
"""
from engine.combat import resolve_captures
from engine.config import GameConfig
from engine.economy import apply_build, apply_train
from engine.step import step
from engine.world import Army, CommandType, StandingOrder, Town, World


def _cfg(**kw):
    d = {"map_size": [1000, 1000], "max_turns": 100, "info_speed": 150.0,
         "army_speed": 50.0, "army_cost": 1000, "interact_radius": 10.0,
         "build_efficiency": 0.9, "capture_loss": 0.5, "max_train_frac": 0.1,
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


def test_train_capped_ten_percent():
    cfg, w = _cfg(), _world()
    w.standing_orders.append(StandingOrder(
        command=CommandType.TRAIN, target_id=1, target_type="town",
        args=[0.0, 500.0]))
    apply_train(w, cfg)
    a = [x for x in w.armies if not x.is_viceroy]
    assert len(a) == 1 and abs(a[0].size - 60.0) < 1e-6
    assert abs(w.get_town(1).population - 540.0) < 1e-6


def test_train_one_per_town_per_turn():
    cfg, w = _cfg(), _world()
    for _ in range(3):
        w.standing_orders.append(StandingOrder(
            command=CommandType.TRAIN, target_id=1, target_type="town",
            args=[0.0, 30.0]))
    apply_train(w, cfg)
    assert len([x for x in w.armies if not x.is_viceroy]) == 1


def test_build_pays_point_nine():
    cfg, w = _world(), None
    cfg = _cfg()
    w = _world()
    w.armies.append(Army(id=10, faction=0, x=600.0, y=500.0, size=100.0))
    w.mark_dirty()
    w.standing_orders.append(StandingOrder(
        command=CommandType.BUILD, target_id=10, target_type="army",
        args=[600.0, 500.0, 100.0]))
    apply_build(w, cfg)
    t = [x for x in w.towns if x.id != 1]
    assert len(t) == 1 and abs(t[0].population - 90.0) < 1e-6


def test_capture_halves():
    cfg, w = _cfg(), _world()
    w.towns.append(Town(id=2, faction=1, x=520.0, y=500.0,
                        population=600.0, is_capital=False))
    w.armies.append(Army(id=10, faction=0, x=520.0, y=500.0, size=200.0))
    w.mark_dirty()
    evs = resolve_captures(w, cfg)
    assert w.get_town(2).faction == 0
    assert abs(w.get_town(2).population - 300.0) < 1e-6
    assert any(e.get("kind") == "town_capture" for e in evs)


def test_viceroy_relocates_not_creates():
    cfg, w = _cfg(), _world()
    before = w.get_town(1).population
    step(w, cfg, None, 1, {0: ["MOVE_CAPITAL 700.0 700.0 60.0"]})
    step(w, cfg, None, 2, {})
    vic = [a for a in w.armies if a.is_viceroy]
    assert len(vic) == 1
    moved = before - w.get_town(1).population
    assert abs(moved - vic[0].size) < 1.0, "viceroy deducts its size (growth noise aside)"
    assert not w.get_town(1).is_capital, "old capital demoted at launch"
