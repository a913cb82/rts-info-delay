"""Event application — applies event dicts to a World object.

Used by both the engine (after step) and bots (to update their world).
This ensures consistent event handling without duplicating logic.
"""

from __future__ import annotations

from engine.world import World, Town, Army


def apply_events(world: World, events: list[dict], config=None) -> None:
    """Apply a list of event dicts to a World object.

    Handles: army_spawn, town_spawn, town_death, army_death,
    army_move, town_capture.
    """
    for ev in events:
        kind = ev.get("kind")
        if kind == "army_spawn":
            eid = ev.get("id")
            if eid is not None and not world.get_army(eid):
                a = Army(
                    id=eid,
                    faction=ev.get("faction", 0),
                    x=ev.get("x", 0),
                    y=ev.get("y", 0),
                )
                a.is_viceroy = ev.get("is_viceroy", False)
                a.size = ev.get("size", config.army_cost if config is not None else 1000.0)
                world.armies.append(a)
            # TRAIN spawn — reduce matching town pop by army size
            if not ev.get("is_viceroy", False) and config is not None:
                ex, ey = ev.get("x", 0), ev.get("y", 0)
                cost = ev.get("size", config.army_cost)
                for tw in world.towns:
                    if abs(tw.x - ex) < 1 and abs(tw.y - ey) < 1:
                        tw.population -= cost
                        break

        elif kind == "town_spawn":
            eid = ev.get("id")
            if eid is None:
                continue
            ex = world.get_town(eid)
            if ex is None:
                t = Town(
                    id=eid,
                    faction=ev.get("faction", 0),
                    x=ev.get("x", 0),
                    y=ev.get("y", 0),
                    population=ev.get("population", 500),
                    is_capital=ev.get("is_capital", False),
                )
                world.towns.append(t)
            else:
                # Merge-promotion (viceroy landing on a friendly town)
                # reuses the town_spawn shape with an existing id: apply
                # absolutely (idempotent on replay).
                ex.faction = ev.get("faction", ex.faction)
                ex.x = ev.get("x", ex.x)
                ex.y = ev.get("y", ex.y)
                ex.population = ev.get("population", ex.population)
                ex.is_capital = ev.get("is_capital", ex.is_capital)
                world.mark_dirty()

        elif kind == "town_capture":
            t = world.get_town(ev.get("id"))
            if t:
                t.faction = ev.get("new_faction", t.faction)
                t.population = ev.get("population", t.population)
                # Captures never create capitals (beheading is permanent;
                # only MOVE_CAPITAL founds new ones): demote, never promote.
                if ev.get("was_capital"):
                    t.is_capital = False
                world.mark_dirty()

        elif kind == "army_move":
            a = world.get_army(ev.get("id"))
            if a:
                a.x = ev.get("x", a.x)
                a.y = ev.get("y", a.y)
                if "has_target" in ev:
                    a.has_target = bool(ev.get("has_target"))
                if "target_x" in ev:
                    a.target_x = ev.get("target_x", a.target_x)
                if "target_y" in ev:
                    a.target_y = ev.get("target_y", a.target_y)

        elif kind == "army_death":
            world.remove_army(ev.get("id"))

        elif kind == "town_death":
            world.remove_town(ev.get("id"))

        elif kind == "pop_change":
            t = world.get_town(ev.get("id"))
            if t:
                t.population = ev.get("population", t.population)
                if "faction" in ev:
                    t.faction = ev["faction"]
                if "is_capital" in ev:
                    t.is_capital = ev["is_capital"]
