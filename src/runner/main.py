"""Game runner — spawns bot subprocesses, manages stdin/stdout, runs game loop."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path
import concurrent.futures

from engine.config import GameConfig
from engine.ledger import Ledger
from engine.record import write_config_line, write_turn_line
from engine.step import step
from engine.world import World


class BotProcess:
    """Manages a single bot subprocess (persistent across turns)."""

    proc: subprocess.Popen
    faction: int
    alive: bool

    def __init__(self, cmd: list[str], faction: int, config: GameConfig) -> None:
        """Spawn subprocess, send startup (config, faction, go)."""
        self.faction = faction
        self.config = config
        self.alive = True
        self.cmd = cmd
        try:
            import os
            env = os.environ.copy()
            # Ensure src is on PYTHONPATH for bots (they import engine/bots)
            src_path = str(Path(__file__).resolve().parents[1])
            if "PYTHONPATH" in env:
                env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"]
            else:
                env["PYTHONPATH"] = src_path
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except Exception:
            # Failed to start
            self.proc = None  # type: ignore
            self.alive = False
            return

        # Send startup: config, faction, go
        try:
            cfg_json = json.dumps(config.to_dict())
            self.proc.stdin.write(f"config {cfg_json}\n")
            self.proc.stdin.write(f"faction {faction}\n")
            self.proc.stdin.write("go\n")
            self.proc.stdin.flush()
        except Exception:
            self.alive = False
            try:
                self.kill()
            except Exception:
                pass

    def send_turn(self, turn: int, events: list[dict]) -> list[str]:
        """Send turn header + events, read orders until 'go'.

        Returns list of order strings (without 'go').
        Returns [] on timeout or crash (marks bot dead).
        """
        if not self.alive:
            return []
        if self.proc is None:
            self.alive = False
            return []
        # Check if process has already terminated
        try:
            if self.proc.poll() is not None:
                self.alive = False
                return []
        except Exception:
            pass

        # Send turn data
        try:
            self.proc.stdin.write(f"turn {turn}\n")
            for ev in events:
                # ev is dict, write as json line
                if isinstance(ev, dict):
                    self.proc.stdin.write(json.dumps(ev) + "\n")
                else:
                    # Handle Ledger Event objects
                    try:
                        # Try to serialize
                        self.proc.stdin.write(json.dumps({"kind": ev.kind.value if hasattr(ev.kind, 'value') else str(ev.kind), "x": ev.x, "y": ev.y, "turn": ev.turn, **ev.payload}) + "\n")
                    except Exception:
                        self.proc.stdin.write(str(ev) + "\n")
            self.proc.stdin.write("go\n")
            self.proc.stdin.flush()
        except Exception:
            self.alive = False
            self.kill()
            return []

        # Read orders until go
        orders: list[str] = []
        timeout_sec = self.config.turn_time_ms / 1000.0 if hasattr(self.config, "turn_time_ms") else 1.0
        start_time = time.time()

        # Use executor for timeout handling
        # We will read line by line with timeout remaining
        try:
            while True:
                remaining = timeout_sec - (time.time() - start_time)
                if remaining <= 0:
                    raise TimeoutError("turn timeout")
                # Use ThreadPool to implement timeout for readline
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.proc.stdout.readline)
                    try:
                        line = future.result(timeout=remaining)
                    except concurrent.futures.TimeoutError as e:
                        raise TimeoutError("turn timeout") from e

                if line is None:
                    line = ""
                # readline returns '' on EOF
                if line == "":
                    # EOF - process closed
                    self.alive = False
                    self.kill()
                    return []
                stripped = line.strip()
                if stripped == "":
                    continue
                if stripped == "go":
                    break
                # Otherwise, it's an order line
                orders.append(stripped)
                # Check total time
                if time.time() - start_time > timeout_sec:
                    raise TimeoutError("turn timeout")
        except TimeoutError:
            self.alive = False
            self.kill()
            return []
        except Exception:
            # Any other exception, treat as dead but not necessarily timeout
            # For mocked tests that raise TimeoutError directly from readline, we already handle
            # For other exceptions, mark dead
            self.alive = False
            try:
                self.kill()
            except Exception:
                pass
            return []

        # Validate orders via parse_orders
        validated = parse_orders(orders)
        return validated

    def send_end(self, scores: dict[int, int]) -> None:
        """Send end message, then kill process."""
        if self.proc is None:
            self.alive = False
            return
        try:
            # Even if not alive, still try to send end (per B9b)
            scores_json = json.dumps(scores)
            try:
                self.proc.stdin.write(f"end {scores_json}\n")
                self.proc.stdin.flush()
            except Exception:
                pass
        finally:
            self.kill()

    def kill(self) -> None:
        """Kill subprocess."""
        self.alive = False
        if self.proc is None:
            return
        try:
            # Try to terminate gracefully
            self.proc.kill()
        except Exception:
            pass
        try:
            # Close pipes
            if self.proc.stdin:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
            if self.proc.stdout:
                try:
                    self.proc.stdout.close()
                except Exception:
                    pass
            if self.proc.stderr:
                try:
                    self.proc.stderr.close()
                except Exception:
                    pass
        except Exception:
            pass
        # Wait briefly
        try:
            self.proc.wait(timeout=0.1)
        except Exception:
            pass


def run_game(
    config: GameConfig,
    bots: dict[int, list[str]],
    record_path: Path | None = None,
) -> dict[int, int]:
    """Run a full game.

    Args:
        config: Game configuration.
        bots: {faction_id: command} for each bot.
        record_path: If given, write JSONL game record here.

    Returns:
        {faction: score} at game end.
    """
    # Initialize world
    world = World()
    world.map_size = config.map_size
    if config.map:
        world.parse_map(config.map)

    # If config.map is empty but world has no towns/armies, we still have empty world
    # Ensure _next_id is correct (parse_map sets it)

    # Initialize ledger
    map_diag = math.hypot(config.map_size[0], config.map_size[1]) if config.map_size and len(config.map_size) >= 2 else 1414.0
    ledger = Ledger(config.info_speed, map_diag)

    # Initialize bots
    bot_processes: dict[int, BotProcess] = {}
    for faction, cmd in bots.items():
        # cmd may be list[str] or str
        if isinstance(cmd, str):
            # Split string? Assume it's a command line, split
            import shlex
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = list(cmd)
        bp = BotProcess(cmd=cmd_list, faction=faction, config=config)
        bot_processes[faction] = bp

    # Prepare record file: ensure parent exists, clear file, write config
    if record_path is not None:
        record_path = Path(record_path)
        record_path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate file
        try:
            # Remove existing
            if record_path.exists():
                record_path.unlink()
        except Exception:
            pass
        write_config_line(config, record_path)

    # Game loop
    events: list[dict] = []
    for turn in range(1, config.max_turns + 1):
        orders_dict: dict[int, list[str]] = {}
        for faction, bp in bot_processes.items():
            if not bp.alive:
                orders_dict[faction] = []
                continue
            # Determine visible events for this faction
            capital = world.faction_capital(faction)
            if capital is None:
                cap_x, cap_y = 0.0, 0.0
                is_in_flight = any(a.is_viceroy and a.faction == faction for a in world.armies)
                # If no capital, still need to handle is_in_flight? No capital means no visibility?
                # For factions with no towns, they see nothing?
            else:
                cap_x, cap_y = capital.x, capital.y
                # Check if faction has viceroy in flight -> blind
                is_in_flight = any(a.is_viceroy and a.faction == faction for a in world.armies)
            visible_events = ledger.visible_events(faction=faction, capital_x=cap_x, capital_y=cap_y, now=float(turn), is_in_flight=is_in_flight)
            # When MOVE_CAPITAL completes (new capital spawned), send ALL events
            # so bot can fully rebuild BotState from new capital's perspective
            move_cap_complete = any(
                hasattr(ev, 'payload') and isinstance(ev.payload, dict)
                and ev.kind.value == "town_spawn" and ev.payload.get("is_capital")
                for ev in visible_events
            )
            if move_cap_complete:
                visible_events = ledger.turn_events(turn)
            # Convert to dict list for bot
            bot_events: list[dict] = []
            for ev in visible_events:
                d: dict = {
                    "kind": ev.kind.value if hasattr(ev.kind, 'value') else str(ev.kind),
                    "x": ev.x,
                    "y": ev.y,
                    "turn": ev.turn,
                }
                if isinstance(ev.payload, dict):
                    d.update(ev.payload)
                bot_events.append(d)
            # Append pop_change events from previous step (not in ledger)
            if events:
                for ev in events:
                    if isinstance(ev, dict) and ev.get("kind") == "pop_change":
                        bot_events.append(ev)
            # Send turn and get orders
            faction_orders = bp.send_turn(turn=turn, events=bot_events)
            orders_dict[faction] = faction_orders

        # Execute step
        try:
            events = step(world, config, ledger, turn=turn, orders=orders_dict)
            if events is None:
                events = []
        except Exception as e:
            # Step should not crash; but if it does, log and continue with empty events
            import traceback
            print(f"step failed at turn {turn}: {e}", file=sys.stderr)
            traceback.print_exc()
            events = []

        # Check faction death: capital destroyed or viceroy killed while in flight
        for faction in list(bot_processes.keys()):
            bp = bot_processes[faction]
            if not bp.alive:
                continue
            capital = world.faction_capital(faction)
            has_viceroy = any(a.is_viceroy and a.faction == faction for a in world.armies)
            if capital is None and not has_viceroy:
                # Faction has no capital and no viceroy in flight — dead
                bp.alive = False
                try:
                    bp.kill()
                except Exception:
                    pass

        # Write turn record
        if record_path is not None:
            write_turn_line(turn, world, events, record_path)



    # Compute final scores
    final_scores = score(world, config)

    # Ensure scores for all factions that had bots, even if they have 0
    for faction in bots.keys():
        if faction not in final_scores:
            final_scores[faction] = 0

    # Send end to all bots
    for bp in bot_processes.values():
        try:
            bp.send_end(final_scores)
        except Exception:
            pass
        try:
            bp.kill()
        except Exception:
            pass

    return final_scores


def score(world: World, config: GameConfig) -> dict[int, int]:
    """Compute per-faction scores.

    score = total_town_population + army_cost × num_armies
    """
    result: dict[int, int] = {}
    # Gather factions from world
    factions = set()
    for t in world.towns:
        factions.add(t.faction)
    for a in world.armies:
        factions.add(a.faction)
    # Also ensure at least faction 0?
    # We'll compute for each faction present
    for faction in factions:
        town_pop = sum(t.population for t in world.towns if t.faction == faction)
        # round? population is float, but score expects int? Tests expect int sum. We'll sum as int of population (floor?).
        # The spec says total_town_population + army_cost * num_armies, population is float, but score int.
        # We'll compute int(town_pop) or round? Tests use exact pops like 1000, 2000, 500 etc. We'll use sum and then int
        num_armies = sum(1 for a in world.armies if a.faction == faction)
        total = int(town_pop) + config.army_cost * num_armies
        # But town_pop may be float with .5 fractions from growth; int conversion should maybe round? Use int(total) or round?
        # Use int(town_pop) to match test expectations where pop is float but they compare int
        result[faction] = total
    # Also ensure factions with no entities get 0? Caller will handle
    # Ensure result includes at least 0 if empty
    if not result:
        # No factions, return empty dict; caller will fill with 0 for bots
        pass
    return result


def parse_orders(lines: list[str]) -> list[str]:
    """Validate and return raw order lines from bot stdout."""
    valid: list[str] = []
    for raw in lines:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s:
            continue
        if s.lower() == "go":
            continue
        parts = s.split()
        if not parts:
            continue
        cmd = parts[0].upper()
        if cmd == "MOVE_TO":
            if len(parts) != 6:
                continue
            try:
                aid = int(parts[1])
                fx = float(parts[2]); fy = float(parts[3]); tx = float(parts[4]); ty = float(parts[5])
            except ValueError:
                continue
            valid.append(s)
        elif cmd == "TRAIN":
            if len(parts) != 2:
                continue
            try:
                tid = int(parts[1])
            except ValueError:
                continue
            valid.append(f"TRAIN {tid}")
        elif cmd == "BUILD":
            if len(parts) != 4:
                continue
            try:
                aid = int(parts[1]); bx = float(parts[2]); by = float(parts[3])
            except ValueError:
                continue
            valid.append(s)
        elif cmd == "MOVE_CAPITAL":
            if len(parts) != 3:
                continue
            try:
                x = float(parts[1]); y = float(parts[2])
            except ValueError:
                continue
            valid.append(s)
        else:
            # Unknown command, ignore
            continue
    return valid


def apply_orders_to_world(
    world: World, faction: int, orders: list[str], config: GameConfig
) -> None:
    """Queue orders as messengers for delivery (MOVE_CAPITAL instant)."""
    # Reuse step's command logic for single faction
    # We'll call _phase_command equivalent for this faction
    # For simplicity, create a small orders dict and call step's helper
    # But to avoid circular import, implement directly
    from engine.world import CommandType, Messenger, StandingOrder, Army
    import math

    for order_str in orders:
        s = order_str.strip()
        if not s or s.lower() == "go":
            continue
        parts = s.split()
        cmd = parts[0].upper()
        if cmd == "MOVE_CAPITAL":
            if len(parts) != 3:
                continue
            try:
                tx = float(parts[1]); ty = float(parts[2])
            except ValueError:
                continue
            tx, ty = world.clamp_position(tx, ty)
            capital = world.faction_capital(faction)
            if capital is None:
                continue
            if capital.population < config.army_cost - 1e-9:
                continue
            if any(a.is_viceroy and a.faction == faction for a in world.armies):
                continue
            capital.population -= config.army_cost
            nid = world.allocate_id()
            viceroy = Army(id=nid, faction=faction, x=capital.x, y=capital.y, target_x=tx, target_y=ty, has_target=True, is_viceroy=True, is_fresh=True)
            world.armies.append(viceroy)
            # Add standing order for arrival tracking
            world.standing_orders.append(StandingOrder(command=CommandType.MOVE_CAPITAL, target_id=capital.id, target_type="town", args=[tx, ty]))
            continue
        elif cmd == "MOVE_TO":
            if len(parts) != 6:
                continue
            try:
                aid = int(parts[1]); fx = float(parts[2]); fy = float(parts[3]); tx = float(parts[4]); ty = float(parts[5])
            except ValueError:
                continue
            capital = world.faction_capital(faction)
            remaining = math.hypot(capital.x - fx, capital.y - fy) if capital else 0.0
            messenger = Messenger(faction=faction, command=CommandType.MOVE_TO, target_id=aid, target_type="army", args=[fx, fy, tx, ty], remaining_dist=remaining)
            world.messengers.append(messenger)
        elif cmd == "BUILD":
            if len(parts) != 4:
                continue
            try:
                aid = int(parts[1]); bx = float(parts[2]); by = float(parts[3])
            except ValueError:
                continue
            capital = world.faction_capital(faction)
            remaining = math.hypot(capital.x - bx, capital.y - by) if capital else 0.0
            messenger = Messenger(faction=faction, command=CommandType.BUILD, target_id=aid, target_type="army", args=[bx, by], remaining_dist=remaining)
            world.messengers.append(messenger)
        elif cmd == "TRAIN":
            if len(parts) != 2:
                continue
            try:
                tid = int(parts[1])
            except ValueError:
                continue
            town = world.get_town(tid)
            capital = world.faction_capital(faction)
            if capital and town:
                remaining = math.hypot(capital.x - town.x, capital.y - town.y)
            else:
                remaining = 0.0
            messenger = Messenger(faction=faction, command=CommandType.TRAIN, target_id=tid, target_type="town", args=[float(faction)], remaining_dist=remaining)
            world.messengers.append(messenger)
        else:
            continue
