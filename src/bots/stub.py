"""Stub bot — does nothing. Useful for testing runner infrastructure."""

from __future__ import annotations

import json
import sys

from engine.config import GameConfig


def main() -> None:
    """Read startup, loop turns, always respond with just 'go'."""
    config, faction = read_startup()
    # World tracking not needed for stub
    while True:
        turn_info = read_turn()
        if turn_info is None:
            break
        turn, events = turn_info
        if turn == -1:
            # End message
            break
        # No orders
        write_orders([])


def read_startup() -> tuple[GameConfig, int]:
    """Read config, faction, go lines from stdin."""
    config = GameConfig()
    faction = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("config "):
            json_str = line[len("config "):]
            try:
                d = json.loads(json_str)
                config = GameConfig.from_dict(d)
            except Exception:
                pass
        elif line.startswith("faction "):
            try:
                faction = int(line.split()[1])
            except Exception:
                faction = 0
        elif line == "go":
            break
        elif line.startswith("end "):
            sys.exit(0)
    return config, faction


def read_turn() -> tuple[int, list[dict]] | None:
    """Read turn number, events, go from stdin."""
    turn = None
    events: list[dict] = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line.startswith("turn "):
            try:
                turn = int(line.split()[1])
            except Exception:
                turn = 0
        elif line == "go":
            if turn is not None:
                return (turn, events)
            else:
                # No turn yet, continue
                continue
        elif line.startswith("end "):
            return (-1, [])
        elif line.startswith("{"):
            # Event json
            try:
                ev = json.loads(line)
                events.append(ev)
            except Exception:
                pass
        else:
            # Ignore other lines, could be event without json? Try parse
            try:
                ev = json.loads(line)
                events.append(ev)
            except Exception:
                pass
    return None


def write_orders(orders: list[str]) -> None:
    """Print orders to stdout followed by 'go'."""
    for o in orders:
        sys.stdout.write(o + "\n")
    sys.stdout.write("go\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
