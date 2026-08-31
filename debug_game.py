"""Debug script: run 5 bots to turn 1200 with full instrumentation."""
import json, math, sys, os
sys.path.insert(0, "src")

from engine.config import GameConfig
from engine.world import World
from engine.step import step, _phase_economy
from engine.ledger import Ledger
from engine.economy import apply_train, apply_growth, check_town_death
from engine.events import apply_events

# ── Monkey-patch apply_train to log ──
_original_train = apply_train
def _instrumented_train(world, config, pre_capture_factions=None):
    for so in list(world.standing_orders):
        if hasattr(so, 'command') and so.command.value == 'TRAIN':
            town = world.get_town(so.target_id)
            if town:
                print(f"  [TRAIN] town={town.id} faction={town.faction} pop_before={town.population:.4f} cost={config.army_cost} threshold={config.death_threshold}", file=sys.stderr)
    events = _original_train(world, config, pre_capture_factions)
    for e in events:
        if e.get('kind') == 'town_death':
            print(f"  [DEATH-in-train] id={e['id']} faction={e['faction']} x={e['x']:.1f} y={e['y']:.1f}", file=sys.stderr)
    for t in world.towns:
        print(f"  [POST-TRAIN] town={t.id} faction={t.faction} pop={t.population:.4f}", file=sys.stderr)
    return events
import engine.economy
engine.economy.apply_train = _instrumented_train

# Also patch step.py's reference
import engine.step
engine.step.apply_train = _instrumented_train

# ── Patch _phase_economy to log growth ──
_original_phase_econ = engine.step._phase_economy
def _instrumented_phase_econ(world, config, ledger=None, turn=0, pre_capture_factions=None):
    print(f"\n=== TURN {turn} economy ===", file=sys.stderr)
    print(f"  [PRE-GROWTH]", file=sys.stderr)
    for t in world.towns:
        print(f"    town={t.id} faction={t.faction} pop={t.population:.4f}", file=sys.stderr)
    events = _original_phase_econ(world, config, ledger, turn, pre_capture_factions)
    print(f"  [POST-ECONOMY]", file=sys.stderr)
    for t in world.towns:
        print(f"    town={t.id} faction={t.faction} pop={t.population:.4f}", file=sys.stderr)
    for e in events:
        if e.get('kind') == 'town_death':
            print(f"  [DEATH-in-econ] id={e['id']} faction={e['faction']}", file=sys.stderr)
    return events
engine.step._phase_economy = _instrumented_phase_econ

# ── Instrument bot subprocess ──
class InstrumentedBot:
    def __init__(self, cmd, faction, bot_name):
        import subprocess
        self.cmd = cmd
        self.faction = faction
        self.bot_name = bot_name
        self.alive = True
        self.proc = None
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "src")
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1, env=env
            )
        except Exception:
            self.alive = False
            return
        # Send config
        cfg_json = json.dumps(config.to_dict())
        self.proc.stdin.write(f"config {cfg_json}\n")
        self.proc.stdin.write(f"faction {faction}\n")
        self.proc.stdin.write("go\n")
        self.proc.stdin.flush()

    def send_turn(self, turn, events):
        if not self.alive or not self.proc:
            return []
        try:
            self.proc.stdin.write(f"turn {turn}\n")
            for ev in events:
                if isinstance(ev, dict):
                    self.proc.stdin.write(json.dumps(ev) + "\n")
            self.proc.stdin.write("go\n")
            self.proc.stdin.flush()
        except Exception:
            self.alive = False
            return []

        orders = []
        import time, concurrent.futures
        start = time.time()
        try:
            while True:
                remaining = 1.0 - (time.time() - start)
                if remaining <= 0:
                    break
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(self.proc.stdout.readline)
                    try:
                        line = future.result(timeout=remaining)
                    except:
                        break
                if not line:
                    self.alive = False
                    break
                stripped = line.strip()
                if stripped == "go":
                    break
                if stripped:
                    orders.append(stripped)
        except Exception:
            self.alive = False

        if orders:
            print(f"  [{self.bot_name} F{self.faction}] turn={turn} orders={orders}", file=sys.stderr)
        else:
            print(f"  [{self.bot_name} F{self.faction}] turn={turn} orders=[] alive={self.alive}", file=sys.stderr)
        return orders

    def kill(self):
        if self.proc:
            try:
                self.proc.stdin.write("end {}\n")
                self.proc.stdin.flush()
            except:
                pass
            try:
                self.proc.kill()
            except:
                pass
        self.alive = False

# ── Main game loop ──
with open('maps/empty.json') as f:
    cfg_dict = json.load(f)

config = GameConfig()
config.map = cfg_dict['map']
config.map_size = cfg_dict['map_size']
config.max_turns = 1200

world = World()
world.map_size = config.map_size
world.parse_map(config.map)
ledger = Ledger(config.info_speed, math.hypot(*config.map_size))

bot_specs = {
    0: (['.venv/bin/python', '-m', 'bots.random'], 'random'),
    1: (['.venv/bin/python', '-m', 'bots.expander'], 'expander'),
    2: (['.venv/bin/python', '-m', 'bots.turtle'], 'turtle'),
    3: (['.venv/bin/python', '-m', 'bots.aggressive'], 'aggressive'),
    4: (['.venv/bin/python', '-m', 'bots.greedy'], 'greedy'),
}

bots = {}
for fac, (cmd, name) in bot_specs.items():
    bots[fac] = InstrumentedBot(cmd, fac, name)

for turn in range(1, config.max_turns + 1):
    orders_dict = {}
    for fac, bp in bots.items():
        if not bp.alive:
            orders_dict[fac] = []
            continue
        capital = world.faction_capital(fac)
        cap_x = capital.x if capital else 0
        cap_y = capital.y if capital else 0
        visible = ledger.visible_events(faction=fac, capital_x=cap_x, capital_y=cap_y, now=float(turn))
        visible_dicts = []
        for ev in visible:
            d = {"kind": ev.kind.value if hasattr(ev.kind, 'value') else str(ev.kind),
                 "x": ev.x, "y": ev.y, "turn": ev.turn}
            if isinstance(ev.payload, dict):
                d.update(ev.payload)
            visible_dicts.append(d)
        # Also send pop_change from previous step
        if prev_events:
            for ev in prev_events:
                if isinstance(ev, dict) and ev.get("kind") == "pop_change":
                    visible_dicts.append(ev)
        orders_dict[fac] = bp.send_turn(turn, visible_dicts)

    prev_events = step(world, config, ledger, turn=turn, orders=orders_dict)

    # Check faction death
    for fac in list(bots.keys()):
        bp = bots[fac]
        if not bp.alive:
            continue
        capital = world.faction_capital(fac)
        has_viceroy = any(a.is_viceroy and a.faction == fac for a in world.armies)
        if capital is None and not has_viceroy:
            print(f"  [FACTION-DEAD] F{fac} at turn {turn}", file=sys.stderr)
            bp.alive = False
            bp.kill()

    if turn % 100 == 0:
        print(f"\n--- Turn {turn}: {len(world.towns)} towns, {len(world.armies)} armies ---", file=sys.stderr)
        for t in world.towns:
            print(f"  Town {t.id} F{t.faction}: pop={t.population:.1f}", file=sys.stderr)

# Final
print("\n=== FINAL STATE ===", file=sys.stderr)
for t in world.towns:
    print(f"  Town {t.id} F{t.faction}: pop={t.population:.1f}", file=sys.stderr)
for a in world.armies:
    print(f"  Army {a.id} F{a.faction}: x={a.x:.1f} y={a.y:.1f}", file=sys.stderr)

for fac, bp in bots.items():
    bp.kill()
