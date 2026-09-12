"""One-turn structural rates: is >2400 ever better than 2400?

Each structure: instantaneous annualized growth measured on turn 2
(turn 1 primes market services). No long simulations.
"""
import math, sys
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.config import GameConfig
from engine.economy import _step_core
from engine.world import Town, World
BASE = GameConfig()
TOTAL = 46800.0

def spiral(n, cx, cy, r, pop):
    return [(cx + r*math.sqrt((i+0.5)/n)*math.cos(i*2.399963),
             cy + r*math.sqrt((i+0.5)/n)*math.sin(i*2.399963), pop) for i in range(n)]

def rate(cfg, spec):
    towns = [Town(id=i, faction=0, x=float(x), y=float(y), population=float(p),
                  is_capital=(i == 0)) for i, (x, y, p) in enumerate(spec)]
    pops = sum(t.population for t in towns)
    _n1, serv = _step_core(towns, [1000, 1000], cfg, None)      # turn 1: no services
    last = {t.id: float(s) for t, s in zip(towns, serv)}
    n2, serv2 = _step_core(towns, [1000, 1000], cfg, last)      # turn 2: services live
    tot2 = sum(n2)
    growth = (tot2 - pops) / pops * 52.0 * 100.0
    town_net = n2[0] - towns[0].population
    return growth, tot2, town_net

def sweep(tag, cfg, village=300.0):
    print(f"-- {tag} (village {village:g})")
    for label, town in [("0town",0.0),("1x2400",2400.0),("1x4800",4800.0),
                        ("1x9600",9600.0),("1x14400",14400.0)]:
        if town >= TOTAL: continue
        nv = max(1, round((TOTAL-town)/village))
        spec = ([(500,500,town)] if town else []) + spiral(nv,500,500,55,village)
        g, tot, tn = rate(cfg, spec)
        print(f"   {label:9s} growth {g:+.4f}%/yr  turn2 total {tot:9.0f}  town net {tn:+8.1f}")

sweep("base", BASE)
sweep("premium 0.5", replace(BASE, market_premium=0.5))
sweep("gamma 1.15", replace(BASE, market_scaling=1.15))
sweep("gamma 2.0", replace(BASE, market_scaling=2.0))
sweep("mature villages 1800", BASE, village=1800.0)
