"""GTO exam — how GTO is pro, in one number (per section).

Scored, NON-BLOCKING measurement (not a gate): fixtures encode doctrine
(BOT_PLAN.md compact form, GTO.md detailed form) as scripted intel in,
orders out. Expected to FAIL where Steps haven't landed — the failures
ARE the roadmap (each maps to a plan Step). Reported per-section so
progress shows as section scores climbing, not just a total.

Anti-Goodhart: core fixtures are parameterized over geometries
(near/far x rich/poor); passing needs the RULE, not the point. Game-level
truth stays in scenario_bench.py / strategic_bench.py / empty_3000.

Usage: PYTHONPATH=src python benchmarks/gto_exam.py
Budget: milliseconds (decide-level, no sims).
"""
import sys

from engine.config import GameConfig
from bots.common import BotState
from bots.pro import decide_orders

CFG = GameConfig()
RESULTS: list[tuple[str, str, bool, str]] = []


def _tu(tid, x, y, faction=0, pop=3000, cap=False):
    return {"kind": "town_update", "id": tid, "x": x, "y": y,
            "faction": faction, "population": pop, "is_capital": cap}


def _au(aid, x, y, faction=1):
    return {"kind": "army_update", "id": aid, "x": x, "y": y,
            "faction": faction, "alive": True, "is_viceroy": False}


def _state(towns, armies=(), turn=1):
    b = BotState()
    b.init(CFG, 0)
    b.update(turn, [_tu(*t) for t in towns] + [_au(*a) for a in armies])
    return b


def _trains(o):
    return sorted(x for x in o if x.startswith("TRAIN"))


def _moves(o):
    return sorted(x for x in o if x.startswith("MOVE_TO"))


def check(section, name, orders, pred, why):
    ok = bool(pred(orders))
    RESULTS.append((section, name, ok, "" if ok else why))
    return ok


def cap_state(pop, foe_towns=(), foe_armies=(), own_armies=(), turn=1,
              cap_xy=(300, 500)):
    towns = [(1, cap_xy[0], cap_xy[1], 0, pop, True)]
    towns += [(100 + i, x, y, f, p, c) for i, (x, y, f, p, c)
              in enumerate(foe_towns)]
    armies = [(200 + i, x, y, f) for i, (x, y, f) in enumerate(foe_armies)]
    armies += [(7 + i, x, y, 0) for i, (x, y) in enumerate(own_armies)]
    return _state(towns, armies, turn)


# ── Muster: train iff strictly outnumbered (D < N), affordable ──
def exam_muster():
    for dist, pop in [(100, 3000), (200, 8000)]:
        eta_ok = dist / 50.0 <= 8  # inbound window
        # 0 home vs 1 raider: muster (the take is otherwise free).
        o = decide_orders(cap_state(pop, foe_armies=[(300 + dist, 500, 1)]), CFG)
        check("muster", f"0v1_d{dist}_p{pop}", o, lambda o: len(_trains(o)) >= 1,
              f"no muster vs lone raider (eta {dist/50:.0f}); orders={o}")
        # 2 home vs 1 raider: defended — spending bleeds for nothing.
        o = decide_orders(cap_state(
            pop, foe_armies=[(300 + dist, 500, 1)],
            own_armies=[(290, 500), (310, 500)]), CFG)
        check("muster", f"2v1_d{dist}_p{pop}", o, lambda o: not _trains(o),
              f"overtrains a defended town; orders={o}")
        # 1 home vs 3 raiders: lost — save the armies, don't donate.
        o = decide_orders(cap_state(
            pop, foe_armies=[(300 + dist, 500, 1), (320 + dist, 520, 1),
                             (320 + dist, 480, 1)],
            own_armies=[(300, 500)]), CFG)
        check("muster", f"1v3_d{dist}_p{pop}", o, lambda o: not _trains(o),
              f"donates into a lost fight; orders={o}")
        assert eta_ok  # geometries stay inside the inbound window
    # 1v1 short-horizon: clean beats mutual (terminal score + options).
    o = decide_orders(cap_state(
        5000, foe_armies=[(400, 500, 1)], own_armies=[(300, 500)]), CFG)
    check("muster", "1v1_short_cleans", o, lambda o: len(_trains(o)) >= 1,
          f"takes the mutual on a short horizon; orders={o}")
    # 1v1 long-horizon: mutual is cheaper (spend static, keep compounding).
    # (Two feeds: single-feed army credits pollute growth (spawn-credit);
    # history wipes it and measures true growth.)
    long_cfg = GameConfig()
    long_cfg.max_turns = 10000
    b = _state([(1, 300, 500, 0, 5000, True)], [(200, 400, 500, 1),
                                                (201, 300, 500, 0)], turn=1)
    b.config = long_cfg
    b.update(2, [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                   "faction": 0, "population": 5003, "alive": True,
                   "is_capital": True},
                 {"kind": "army_update", "id": 200, "x": 400, "y": 500,
                   "faction": 1, "alive": True, "is_viceroy": False},
                 {"kind": "army_update", "id": 201, "x": 300, "y": 500,
                   "faction": 0, "alive": True, "is_viceroy": False}])
    o = decide_orders(b, long_cfg)
    check("muster", "1v1_long_holds", o, lambda o: not _trains(o),
          f"buys clean on a long horizon; orders={o}")
    # Standing guard: D==0 vs a LONE distant raider (ETA 10) trains early
    # (deterrence posture — visible guards price in +1).
    o = decide_orders(cap_state(
        5000, foe_armies=[(800, 500, 1)]), CFG)
    check("muster", "guard_distant_lone", o, lambda o: len(_trains(o)) >= 1,
          f"no deterrent vs lone raider; orders={o}")
    # ...but not vs a pair (hopeless — don't donate).
    o = decide_orders(cap_state(
        5000, foe_armies=[(800, 500, 1), (820, 520, 1)]), CFG)
    check("muster", "guard_distant_pair_holds", o, lambda o: not _trains(o),
          f"donates a guard into hopeless; orders={o}")


# ── Pricing: expand iff payback-positive (Step 2; expect FAIL) ──
def exam_pricing():
    # Poor home, void all around: founding never repays — recycle home
    # (+500 pop-add) or hold, never march away.
    o = decide_orders(cap_state(3000, foe_towns=[(900, 500, 1, 4000, False)],
                                own_armies=[(300, 500)]), CFG)
    check("pricing", "poor_home_holds", o,
          lambda o: not any(m.split()[1] == "7" and _march_len(m) > 20
                             for m in _moves(o)),
          f"marches a settler from a poor town; orders={o}")
    # Rich home, VOID (no foes ever seen): uncontested compounding — a
    # settler marches.
    o = decide_orders(cap_state(30000, own_armies=[(300, 500)]), CFG)
    check("pricing", "rich_void_expands", o, lambda o: len(_moves(o)) >= 1,
          f"rich void town sits on its hands; orders={o}")
    # Rich home, CONTESTED, short horizon: 1e8/30000 = 3333 turns payback
    # never fits — no SETTLING (darkness already lifted; expansion is
    # priced). Raid marches at the known foe town are JIT-tempo (allowed);
    # anything else marching is a settler (forbidden).
    o = decide_orders(cap_state(30000, foe_towns=[(900, 500, 1, 4000, False)],
                                own_armies=[(300, 500)]), CFG)
    def _tgt(m):
        _, _, _, _, tx, ty = m.split()
        return (float(tx), float(ty))
    check("pricing", "rich_contested_holds", o,
          lambda o: all(_tgt(m) == (900.0, 500.0)
                         for m in _moves(o) if m.split()[1] == "7"),
          f"settles a priced contest; orders={o}")


def _march_len(m):
    _, _, fx, fy, tx, ty = m.split()
    return ((float(tx) - float(fx)) ** 2
            + (float(ty) - float(fy)) ** 2) ** 0.5


# ── Selectivity: theft-only vs unready, skip the ready (Step 2) ──
def exam_selectivity():
    # Poor-unready FAR (1500 @400km: viable halve 750, can't muster) +
    # rich-ready NEAR (8000 @150km, prints 3 before arrival), same faction
    # (distance would pick the rich town — readiness must overrule it).
    # (800 would halve 400 and starve — decoy, excluded by viability.)
    o = decide_orders(cap_state(
        20000, foe_towns=[(700, 500, 1, 1500, False),
                           (450, 500, 1, 8000, False)],
        own_armies=[(300, 500)]), CFG)
    check("selectivity", "poor_unready_first", o,
          lambda o: any("700" in m for m in _moves(o)),
          f"doesn't pick the unready victim; orders={o}")
    # Thin decoy (800 -> halves 400, starves): never raid it with the only army.
    o = decide_orders(cap_state(
        9000, foe_towns=[(400, 500, 1, 800, False)],
        own_armies=[(300, 500)]), CFG)
    check("selectivity", "thin_skipped", o,
          lambda o: not any("400" in m for m in _moves(o)),
          f"raids a starving decoy; orders={o}")
    # Snipe premium: equal prizes at equal distance, one a capital —
    # behead (permanent). (Tempo still beats sniping at unequal range —
    # near-first chains faster; premium is a tie-break, not a trump.)
    o = decide_orders(cap_state(
        20000, foe_towns=[(450, 500, 1, 3000, False),
                           (150, 500, 1, 3000, True)],
        own_armies=[(300, 500)]), CFG)
    check("selectivity", "capital_sniped", o,
          lambda o: any("150" in m for m in _moves(o)),
          f"doesn't prefer the capital; orders={o}")
    # Rich PASSIVE prize (3000, sterile-observed 24 turns, zero prints):
    # W calibrates to zero — the lone army takes it (need 1, not 2).
    b = _state(
        [(1, 300, 500, 0, 20000, True), (2, 600, 500, 1, 3000, False)],
        [(7, 300, 500, 0)], turn=1)
    b.update(25,
             [{"kind": "town_update", "id": 1, "x": 300, "y": 500,
                "faction": 0, "population": 20000, "alive": True,
                "is_capital": True},
              {"kind": "town_update", "id": 2, "x": 600, "y": 500,
                "faction": 1, "population": 3000, "alive": True,
                "is_capital": False},
              {"kind": "army_update", "id": 7, "x": 300, "y": 500,
                "faction": 0, "alive": True, "is_viceroy": False}])
    # Quiescence needs the refreshed intel to settle (static confirmed):
    # decide two turns later, no new events.
    b.update(27, [])
    o = decide_orders(b, CFG)
    check("selectivity", "passive_prize_taken", o,
          lambda o: any("600" in m for m in _moves(o)),
          f"holds vs a sterile prize (pack deadlock); orders={o}")


# ── Escape: young flees, established endures (Step 5) ──
def exam_escape():
    # Hopeless young capital (3000, two raiders at the door, no force):
    # fly — amnesia is cheap, the hub future is long.
    o = decide_orders(cap_state(
        3000, foe_towns=[(500, 500, 1, 5000, False)],
        foe_armies=[(350, 500, 1), (360, 520, 1)]), CFG)
    check("escape", "young_flees", o,
          lambda o: any(x.startswith("MOVE_CAPITAL") for x in o),
          f"rides a doomed young capital down; orders={o}")
    # Hopeless ESTABLISHED capital (40000 + colonies): endure — the brain
    # outweighs the hub; headless-with-towns still plays.
    o = decide_orders(_state(
        [(1, 300, 500, 0, 40000, True), (2, 150, 500, 0, 20000, False)],
        [(201, 350, 500, 1), (202, 360, 520, 1)]), CFG)
    check("escape", "established_endures", o,
          lambda o: not any(x.startswith("MOVE_CAPITAL") for x in o),
          f"evacs an established empire (amnesia > hub); orders={o}")


# ── Intel: probe on schedule (pro recon owed; expect FAIL) ──
def exam_intel():
    # TRUE-blind (zero foe intel) with an idle army: a 50km S0 probe hop
    # goes out, not an 80-300km blind settler march (range tells them
    # apart). (Known-target + pack-hold is correct, not probing — the
    # fixture must be truly blind.)
    o = decide_orders(cap_state(9000, own_armies=[(300, 500)]), CFG)
    def _is_probe(m):
        _, _, fx, fy, tx, ty = m.split()
        return 40 < ((float(tx) - float(fx)) ** 2
                      + (float(ty) - float(fy)) ** 2) ** 0.5 < 60
    check("intel", "blind_probes", o,
          lambda o: any(m.split()[1] == "7" and _is_probe(m)
                         for m in _moves(o)),
          f"no probe hop from a blind army; orders={o}")


# ── Endgame: strip-mine flip at the buzzer ──
def exam_endgame():
    # Turn 2950/3000, idle army, no threats: founding never repays in 50
    # turns — no settler marches (guard/recycle instead). (Training is
    # unselective today so a train-check would pass for the wrong reason.)
    o = decide_orders(cap_state(
        20000, foe_towns=[(900, 500, 1, 4000, False)],
        own_armies=[(300, 500)], turn=2950), CFG)
    check("endgame", "buzzer_no_settle", o,
          lambda o: not any(m.split()[1] == "7" and _march_len(m) > 60
                             for m in _moves(o)),
          f"settles with 50 turns left; orders={o}")


def main():
    for fn in (exam_muster, exam_pricing, exam_selectivity, exam_escape,
               exam_intel, exam_endgame):
        fn()
    sections: dict[str, list[bool]] = {}
    for s, _, ok, _ in RESULTS:
        sections.setdefault(s, []).append(ok)
    total_ok = sum(1 for _, _, ok, _ in RESULTS if ok)
    for s, oks in sections.items():
        print(f"{s:12s} {sum(oks):2d}/{len(oks):2d}")
    print(f"{'TOTAL':12s} {total_ok:2d}/{len(RESULTS):2d}")
    for s, name, ok, why in RESULTS:
        if not ok:
            print(f"  FAIL [{s}] {name}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
