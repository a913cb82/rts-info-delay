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
from engine.delivery import build_updates
from engine.ledger import EventKind, Ledger
from engine.record import write_config_line, write_turn_line
from engine.step import step
from engine.world import World


class BotProcess:
    """Manages a single bot subprocess (persistent across turns)."""

    proc: subprocess.Popen
    faction: int
    alive: bool

    def __init__(self, cmd: str, faction: int, config: GameConfig) -> None:
        """Spawn subprocess via bash, send startup (config, faction, go).
        Pure bash-string: every bot launches as `bash -c <cmd>` (python
        bots included) — one spawn path, any executable."""
        self.faction = faction
        self.config = config
        self.alive = True
        self.cmd = cmd
        self._reader = None
        # No prune: bounded by game length (few thousand turns), freed per game.
        # Byo-yomi clock, engine-authoritative: main reservoir first, then
        # one period (cap + increment). Cold-start imports come out of the
        # 1s main time, so turn 1 needs no handshake.
        try:
            self.main_ms = float(getattr(config, "main_time_ms", 1000.0) or 1000.0)
        except Exception:
            self.main_ms = 1000.0
        try:
            self.clock_ms = float(getattr(config, "turn_time_ms", 100) or 100)
        except Exception:
            self.clock_ms = 100.0
        self.in_byoyomi = False
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
                ["bash", "-c", cmd],
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

        # Persistent single-thread reader: fire-and-forget readline with a
        # real timeout. (A per-read `with ThreadPoolExecutor` block hangs in
        # shutdown(wait=True) on a silent bot, defeating the timeout.)
        try:
            self._reader = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        except Exception:
            self._reader = None  # type: ignore

        # Send startup: config (rules + dims, never the map), faction, go
        try:
            cfg_json = _startup_config_json(config)
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
            return
    def turn_budget(self) -> float:
        """This turn's budget: main reservoir remainder, or the byo-yomi
        period clock once main is exhausted."""
        if not self.in_byoyomi:
            return max(0.0, self.main_ms)
        return max(0.0, self.clock_ms)

    def send_turn(self, turn: int, events: list[dict], time_ms: float | None = None) -> list[str]:
        """Send turn header + clock + events, read orders until 'go'.

        time_ms is this turn's Fischer budget (None = legacy: no clock
        line, fixed turn_time_ms budget). Elapsed round-trip time is
        deducted and the increment credited back (capped) for next turn.
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
        try:
            cap = float(getattr(self.config, "turn_time_ms", 100) or 100)
        except Exception:
            cap = 100.0
        try:
            inc = float(getattr(self.config, "time_increment_ms", 10.0) or 0.0)
        except Exception:
            inc = 10.0
        use_clock = time_ms is not None
        budget_ms = max(0.0, float(time_ms)) if use_clock else cap

        # Send turn data (shared with the multiplexed path)
        t_start = time.perf_counter()
        if not self._write_block(turn, events, budget_ms, use_clock):
            self.alive = False
            self.kill()
            return []

        # Read orders until go
        orders: list[str] = []
        timeout_sec = budget_ms / 1000.0
        start_time = time.time()

        # Use executor for timeout handling
        # We will read line by line with timeout remaining
        try:
            while True:
                remaining = timeout_sec - (time.time() - start_time)
                if remaining <= 0:
                    raise TimeoutError("turn timeout")
                # Fire-and-forget read on the persistent reader: result()
                # bounds the wait; a silent bot's worker stays blocked until
                # kill() EOFs the pipe, and never blocks this thread.
                if self._reader is None:
                    line = self.proc.stdout.readline()
                else:
                    future = self._reader.submit(self.proc.stdout.readline)
                    try:
                        line = future.result(timeout=remaining)
                    except concurrent.futures.TimeoutError as e:
                        raise TimeoutError("turn timeout") from e

                if line is None:
                    line = ""
                # readline returns '' on EOF
                if line == "":
                    # EOF - process closed
                    return self._finish_block([], True, False, 0.0, use_clock, cap, inc, budget_ms)
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
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            return self._finish_block(None, True, False, elapsed_ms, use_clock, cap, inc, budget_ms)
        except Exception:
            # Any other exception, treat as dead but not necessarily timeout
            # For mocked tests that raise TimeoutError directly from readline, we already handle
            # For other exceptions, mark dead
            return self._finish_block([], False, True, 0.0, use_clock, cap, inc, budget_ms)

        # Validate orders via parse_orders
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        return self._finish_block(orders, False, False, elapsed_ms, use_clock, cap, inc, budget_ms)

    def _write_block(self, turn: int, events: list[dict], budget_ms: float, use_clock: bool) -> bool:
        """Write turn header + clock + events + go. False on failure."""
        try:
            self.proc.stdin.write(f"turn {turn}\n")
            if use_clock:
                self.proc.stdin.write(f"clock {budget_ms:.2f}\n")
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
            return True
        except Exception:
            return False

    def _finish_block(self, lines, timed_out: bool, crashed: bool, elapsed_ms: float,
                      use_clock: bool, cap: float, inc: float, budget_ms: float, turn=None) -> list[str]:
        """Shared completion: timeout/crash kill, else validate + clock.

        Deaths are logged (faction/turn/reason): silent sudden-death used to
        be indistinguishable from being outplayed in post-game analysis.
        """
        if timed_out:
            if use_clock:
                self.main_ms = 0.0
                self.clock_ms = 0.0
            print(f"bot {self.faction} dead turn {turn}: timeout ({elapsed_ms:.0f}ms > {budget_ms:.0f}ms budget)", file=sys.stderr)
            self.alive = False
            self.kill()
            return []
        if crashed:
            print(f"bot {self.faction} dead turn {turn}: crash/eof", file=sys.stderr)
            self.alive = False
            try:
                self.kill()
            except Exception:
                pass
            return []
        validated = parse_orders(lines)
        if use_clock:
            if not self.in_byoyomi:
                # Main time: deduct; hitting zero enters byo-yomi fresh.
                # (Overrunning the budget dies above, so the crossing turn
                # is never punished beyond entering the period.)
                self.main_ms -= elapsed_ms
                if self.main_ms <= 0:
                    self.main_ms = 0.0
                    self.in_byoyomi = True
                    self.clock_ms = cap
            else:
                self.clock_ms = min(cap, budget_ms - elapsed_ms + inc)
                if self.clock_ms <= 0.0:
                    # Floor (hiccup recovery) only on spikes (elapsed > a
                    # full period): sustained mild overspend still dies
                    # (byo-yomi's job), but exact-zero no longer slips the
                    # floor into a budget-0 instant spiral.
                    if elapsed_ms > cap:
                        self.clock_ms = min(cap, inc)
                    else:
                        self.clock_ms = 0.0
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
        # Drop the reader without waiting: a timed-out read may still be
        # blocked until the kill above EOFs the pipe; it then exits alone.
        try:
            if self._reader is not None:
                self._reader.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._reader = None


class TurnMultiplexer:
    """Single-threaded select loop reading all bot pipes at once.

    Threads were measured 6.5x slower per round-trip than sequential
    (futex/GIL storm: 136 voluntary switches/turn across 11 threads for
    ~2ms of real work). This keeps live threads at main+1: the main
    thread writes all turns serially (fast), this thread multiplexes the
    blocking reads. Slow bots still overlap; fast bots pay ~no overhead.
    """

    def __init__(self):
        self._bufs: dict[int, bytearray] = {}  # fd -> pending bytes
        self._fps: dict[int, BotProcess] = {}  # fd -> owner

    def _fd(self, bp: BotProcess) -> int:
        return bp.proc.stdout.fileno()

    def register(self, bp: BotProcess) -> None:
        try:
            fd = self._fd(bp)
            import os
            os.set_blocking(fd, False)
            self._bufs[fd] = bytearray()
            self._fps[fd] = bp
        except Exception:
            pass

    def unregister(self, bp: BotProcess) -> None:
        try:
            fd = self._fd(bp)
            self._bufs.pop(fd, None)
            self._fps.pop(fd, None)
        except Exception:
            pass

    def read_turns(self, deadlines: dict[int, float]) -> dict[int, tuple[list[str] | None, float]]:
        """Read one order batch per registered fd. Returns {fd: (lines, t)}:
        lines excludes the trailing 'go'; lines is None past deadline
        (caller kills those bots); t is completion time. EOF yields the
        lines collected so far (caller checks poll() for death)."""
        import os
        import select
        import time as _time
        _now = _time.perf_counter
        pending = {fd: [] for fd in self._bufs if fd in deadlines}
        done: dict[int, tuple[list[str] | None, float]] = {}
        while pending:
            now = _now()
            remaining = {fd: deadlines[fd] - now for fd in pending}
            live = {fd: r for fd, r in remaining.items() if r > 0}
            if not live:
                for fd in pending:
                    done[fd] = (None, _now())
                break
            timeout = min(live.values())
            try:
                ready, _, _ = select.select(list(live.keys()), [], [], timeout)
            except Exception:
                ready = []
            now = _now()
            if not ready:
                # select timed out: whoever is past deadline is done waiting
                for fd in list(pending.keys()):
                    if deadlines[fd] - now <= 0:
                        done[fd] = (None, now)
                        del pending[fd]
                continue
            for fd in ready:
                if fd not in pending:
                    continue
                try:
                    chunk = os.read(fd, 65536)
                except (BlockingIOError, InterruptedError):
                    continue
                except Exception:
                    done[fd] = (pending.pop(fd), _now())
                    continue
                if not chunk:
                    done[fd] = (pending.pop(fd), _now())  # EOF
                    continue
                buf = self._bufs[fd]
                buf.extend(chunk)
                while True:
                    nl = buf.find(b"\n")
                    if nl < 0:
                        break
                    line = bytes(buf[:nl]).decode("utf-8", "replace").strip()
                    del buf[:nl + 1]
                    if not line:
                        continue
                    if line == "go":
                        done[fd] = (pending.pop(fd), _now())
                        break
                    pending[fd].append(line)
                if fd in pending and deadlines[fd] - _now() <= 0:
                    done[fd] = (None, _now())
                    del pending[fd]
        return done


def faction_in_flight(world: World, faction: int) -> bool:
    """Command authority sits in the flying army: blind and mute."""
    return any(a.is_viceroy and a.faction == faction for a in world.armies)




def _startup_config_json(config: GameConfig) -> str:
    """Startup config JSON for bots: rules + board dims, never the map."""
    d = config.to_dict()
    d.pop("map", None)
    return json.dumps(d)


def deliver(faction: int, world: World, ledger: Ledger, turn: int) -> list[dict]:
    """Tag-aware delivery for one faction (Phase 3 wire-up).

    Mute is the I/O skip: a flying faction gets nothing (the game loop
    also skips its I/O entirely; this guards the builder itself).
    """
    if faction_in_flight(world, faction):
        return []
    capital = world.faction_capital(faction)
    cap = (capital.x, capital.y) if capital is not None else (0.0, 0.0)
    return build_updates(ledger, faction,
                         ledger.S.get(faction, 0), cap, float(turn))


def note_landing(step_events: list[dict], faction: int, turn: int,
                 ledger: Ledger) -> bool:
    """Detect own-capital founding in this step's events.

    On landing: set S (the bot resets its own knowledge — engine holds
    no per-faction send state). Returns True iff this faction landed."""
    for ev in step_events or []:
        if not isinstance(ev, dict):
            continue
        if (ev.get("kind") == "town_spawn" and ev.get("is_capital")
                and ev.get("faction") == faction):
            ledger.set_landing(faction, turn)
            return True
    return False




def run_game(
    config: GameConfig,
    bots: dict[int, str],
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
        bp = BotProcess(cmd=cmd, faction=faction, config=config)
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

    # Game loop. Bots are independent processes sharing one turn window:
    # all turns are written serially (fast), then ONE select loop reads all
    # pipes concurrently — main+1 live threads total. (A ThreadPool fan-out
    # was measured 6.5x slower per round-trip: futex/GIL storm across 11
    # threads for ~2ms of real work.) Orders merge in faction order, so the
    # game stays deterministic regardless of read completion order.
    events: list[dict] = []
    # Pre-game observation (turn 0): the first payload is the first
    # observation — own capital immediate at dist 0, the rest delayed.
    ledger.generate(world, turn=0,
                    line_of_sight=getattr(config, "line_of_sight",
                                         config.info_speed))
    mux = TurnMultiplexer()
    for bp in bot_processes.values():
        if bp.proc is not None:
            mux.register(bp)
    for turn in range(1, config.max_turns + 1):
        orders_dict: dict[int, list[str]] = {}
        # Serial writes (fast; also fixes per-bot write timestamps).
        try:
            cap = float(getattr(config, "turn_time_ms", 100) or 100)
        except Exception:
            cap = 100.0
        try:
            inc = float(getattr(config, "time_increment_ms", 10.0) or 0.0)
        except Exception:
            inc = 10.0
        writes: dict[int, tuple] = {}
        for faction, bp in bot_processes.items():
            if not bp.alive:
                orders_dict[faction] = []
                continue
            if faction_in_flight(world, faction):
                # Command authority sits in the flying army: blind and mute.
                # Skip I/O entirely (bot stalls on readline, resumes on
                # landing); orders empty, clock frozen.
                orders_dict[faction] = []
                continue
            budget_ms = max(0.0, float(bp.turn_budget()))
            if not bp._write_block(turn, deliver(faction, world, ledger, turn), budget_ms, True):
                bp.alive = False
                try:
                    bp.kill()
                except Exception:
                    pass
                orders_dict[faction] = []
                continue
            writes[faction] = (bp, budget_ms, time.perf_counter())
        # One multiplexed read for the whole turn.
        deadlines = {}
        by_fd: dict[int, int] = {}
        for faction, (bp, budget_ms, _t) in writes.items():
            try:
                fd = mux._fd(bp)
                by_fd[fd] = faction
                deadlines[fd] = time.perf_counter() + budget_ms / 1000.0
            except Exception:
                pass
        results = mux.read_turns(deadlines)
        done: dict[int, list[str]] = {}
        for fd, (lines, t_end) in results.items():
            faction = by_fd.get(fd)
            if faction is None:
                continue
            bp, budget_ms, t_w = writes[faction]
            elapsed_ms = (t_end - t_w) * 1000.0
            if lines is None:
                done[faction] = bp._finish_block(None, True, False, elapsed_ms, True, cap, inc, budget_ms, turn=turn)
                continue
            try:
                exited = bp.proc.poll() is not None
            except Exception:
                exited = False
            if exited:
                done[faction] = bp._finish_block([], False, True, 0.0, True, cap, inc, budget_ms, turn=turn)
            else:
                done[faction] = bp._finish_block(lines, False, False, elapsed_ms, True, cap, inc, budget_ms, turn=turn)
        for faction in bot_processes.keys():
            if faction in done:
                orders_dict[faction] = done[faction]

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
        # Landing: own-capital founding in this step's events sets S and
        # resets send-state (counterpart of bot amnesia).
        for faction, bp in bot_processes.items():
            note_landing(events, faction, turn, ledger)

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
    """Queue orders as messengers for delivery (MOVE_CAPITAL included:
    0-distance messenger to the capital itself)."""
    # Reuse step's command logic for single faction
    # We'll call _phase_command equivalent for this faction
    # For simplicity, create a small orders dict and call step's helper
    # But to avoid circular import, implement directly
    from engine.world import CommandType, Messenger
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
            # Normal command: 0-distance messenger to the capital itself.
            messenger = Messenger(faction=faction, command=CommandType.MOVE_CAPITAL,
                                  target_id=capital.id, target_type="town",
                                  args=[tx, ty], remaining_dist=0.0)
            world.messengers.append(messenger)
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
