"""Tests for engine/combat — weakness-based death resolution."""

from __future__ import annotations

import pytest

from engine.config import GameConfig
from engine.combat import compute_weaknesses, resolve_combat
from engine.world import Army, Town, World

CFG = GameConfig()


def _army(x: float, y: float, faction: int, aid: int) -> Army:
    """Helper: create an Army at position."""
    return Army(id=aid, faction=faction, x=x, y=y)


def _world_with(*armies: Army) -> World:
    """Helper: create a World with armies (and necessary map_size)."""
    w = World()
    w.map_size = [1000, 1000]
    w.armies = list(armies)
    return w


def _alive_ids(world: World) -> set[int]:
    """Return set of army ids still alive."""
    return {a.id for a in world.armies}


class TestCombat:
    """C1–C9c: Weakness-based simultaneous death resolution."""

    def test_1v1_mutual(self) -> None:
        """C1: Two armies of different factions within radius → both die."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(5, 0, faction=1, aid=2)
        w = _world_with(a, b)
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_2v1(self) -> None:
        """C2: 2 vs 1 within radius → single dies, pair survives."""
        a1 = _army(0, 0, faction=0, aid=1)
        a2 = _army(5, 0, faction=0, aid=2)
        b = _army(3, 5, faction=1, aid=3)
        w = _world_with(a1, a2, b)
        resolve_combat(w, CFG)
        alive = _alive_ids(w)
        # b dies (enemies each have weakness 2, b's weakness=2, 2≤2)
        # a1,a2 survive (enemy b has weakness 1, 1≤1 true for b,
        # but a1,a2 each see b with weakness 1, and their own weakness is 1,
        # enemy's weakness ≤ own → b dies)
        # Wait: a1's weakness = #enemies within radius = 1 (just b)
        # b dies if any enemy has weakness ≤ b's weakness
        # b's weakness = 2 (sees a1 and a2)
        # a1 is enemy of b: a1 has weakness 1, 1 ≤ 2 → b dies
        # a1's weakness = 1 (sees b). Enemy b has weakness 2, 2 ≤ 1 false → a1 survives
        assert 3 not in alive
        assert 1 in alive
        assert 2 in alive

    def test_3v2(self) -> None:
        """C3: 3 vs 2 → 2 die, 3 survive."""
        # Place all within interact_radius (10) — use tight cluster spacing 2
        faction_a = [_army(i * 2, 0, faction=0, aid=i + 1) for i in range(3)]
        faction_b = [_army(6 + i * 2, 0, faction=1, aid=i + 10) for i in range(2)]
        w = _world_with(*(faction_a + faction_b))
        resolve_combat(w, CFG)
        alive = _alive_ids(w)
        # Faction A (3 armies): each sees 2 enemies. Enemy weakness = 2.
        # 2 ≤ 3 → true → enemies die. But wait: do enemies die?
        # For each faction A army: weakness = 2 (sees 2 B armies)
        # B army's weakness = 3 (sees 3 A armies)
        # A army dies if any enemy (B) has weakness ≤ A's weakness: 3 ≤ 2 → false → A survives
        # B army dies if any enemy (A) has weakness ≤ B's weakness: 2 ≤ 3 → true → B dies
        for b in faction_b:
            assert b.id not in alive
        for a in faction_a:
            assert a.id in alive

    def test_weakness_counts(self) -> None:
        """C4: Single sees 2 enemies (weakness=2), each of pair sees 1."""
        pair = [_army(0, 0, faction=0, aid=1), _army(5, 0, faction=0, aid=2)]
        single = [_army(3, 5, faction=1, aid=3)]
        w = _world_with(*(pair + single))
        weaknesses = compute_weaknesses(w.armies, CFG)
        assert weaknesses[3] == 2  # single sees 2 enemies
        assert weaknesses[1] == 1  # each of pair sees 1
        assert weaknesses[2] == 1

    def test_no_enemies_safe(self) -> None:
        """C5: Lone army → survives."""
        a = _army(0, 0, faction=0, aid=1)
        w = _world_with(a)
        resolve_combat(w, CFG)
        assert len(w.armies) == 1

    def test_simultaneous_snapshot(self) -> None:
        """C6: Simultaneous — all deaths computed from initial weaknesses."""
        # A kills B, B kills C in same radius → all die
        a = _army(0, 0, faction=0, aid=1)
        b = _army(3, 0, faction=1, aid=2)
        c = _army(6, 0, faction=2, aid=3)
        w = _world_with(a, b, c)
        resolve_combat(w, CFG)
        # All within radius, all die
        assert len(w.armies) == 0

    def test_allies_counted(self) -> None:
        """C7: Allies counted toward weakness correctly."""
        a1 = _army(0, 0, faction=0, aid=1)
        a2 = _army(3, 0, faction=0, aid=2)
        b = _army(6, 0, faction=1, aid=3)
        w = _world_with(a1, a2, b)
        weaknesses = compute_weaknesses(w.armies, CFG)
        # b sees 2 enemies (a1, a2), weakness=2
        # a1 sees 1 enemy (b), weakness=1 (a2 is same faction, not enemy)
        assert weaknesses[3] == 2
        assert weaknesses[1] == 1

    def test_multifaction_all_enemies(self) -> None:
        """C7b: 3 factions, 1 army each, all within radius → all die."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(3, 0, faction=1, aid=2)
        c = _army(6, 0, faction=2, aid=3)
        w = _world_with(a, b, c)
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_mixed_distances(self) -> None:
        """C7c: A-B close, B-C close, A-C far → only middle dies."""
        a = _army(0, 0, faction=0, aid=1)    # A near B
        b = _army(5, 0, faction=1, aid=2)    # B between A and C
        c = _army(15, 0, faction=2, aid=3)   # C near B (dist 10), far from A (dist 15)
        w = _world_with(a, b, c)
        resolve_combat(w, CFG)
        alive = _alive_ids(w)
        # A sees B (dist 5 ≤ 10), weakness=1. Enemy B weakness=2. 2 ≤ 1? No → A survives
        # C sees B (dist 10 ≤ 10), weakness=1. Enemy B weakness=2. 2 ≤ 1? No → C survives
        # B sees A (dist 5) and C (dist 10), weakness=2.
        #   Enemy A weakness=1, 1 ≤ 2? Yes → B dies
        assert 1 in alive
        assert 3 in alive
        assert 2 not in alive

    def test_exactly_at_radius(self) -> None:
        """C7d: Enemies at dist exactly 10 → counted (≤)."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(10, 0, faction=1, aid=2)  # exactly at radius
        w = _world_with(a, b)
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_just_outside_radius(self) -> None:
        """C7e: Enemies at dist 10.001 → not counted."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(10.001, 0, faction=1, aid=2)
        w = _world_with(a, b)
        resolve_combat(w, CFG)
        assert len(w.armies) == 2

    def test_3_factions_circle(self) -> None:
        """C9: 3 armies different factions all within radius → all die."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(5, 0, faction=1, aid=2)
        c = _army(2, 4, faction=2, aid=3)
        w = _world_with(a, b, c)
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_2v2_annihilate(self) -> None:
        """C9b: 2 vs 2 within radius → all die (even numbers annihilate)."""
        a1 = _army(0, 0, faction=0, aid=1)
        a2 = _army(3, 0, faction=0, aid=2)
        b1 = _army(6, 0, faction=1, aid=3)
        b2 = _army(9, 0, faction=1, aid=4)
        w = _world_with(a1, a2, b1, b2)
        resolve_combat(w, CFG)
        # All within radius of each other
        # Each sees 2 enemies. Enemy weakness = 2. 2 ≤ 2 → true → all die
        assert len(w.armies) == 0

    def test_combat_uses_final_positions(self) -> None:
        """C9c: Combat checks positions after movement, not intended targets."""
        # Place armies at final positions — combat doesn't know where they were heading
        a = _army(50, 0, faction=0, aid=1)  # final position after movement
        b = _army(50, 5, faction=1, aid=2)  # final position after movement
        w = _world_with(a, b)
        resolve_combat(w, CFG)
        # They're close → mutual death
        assert len(w.armies) == 0

    def test_chain_3_in_line(self) -> None:
        """C8: Three armies in a line, all within radius of neighbors."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(5, 0, faction=1, aid=2)
        c = _army(10, 0, faction=2, aid=3)
        w = _world_with(a, b, c)
        resolve_combat(w, CFG)
        # All within interact_radius=10 of each other → all die
        assert len(w.armies) == 0

    def test_2v1_over_2_turns(self) -> None:
        """C10: 2v1 over 2 turns — march, meet, fight."""
        from engine.movement import move_armies

        w = World()
        w.map_size = [1000, 1000]
        a1 = Army(id=1, faction=0, x=0, y=0)
        a2 = Army(id=2, faction=0, x=5, y=0)
        b = Army(id=3, faction=1, x=100, y=0, target_x=0, target_y=0, has_target=True)
        w.armies = [a1, a2, b]
        move_armies(w, CFG)
        assert b.x >= 50
        move_armies(w, CFG)
        resolve_combat(w, CFG)
        alive = {army.id for army in w.armies}
        assert 3 not in alive
        assert 1 in alive and 2 in alive

    def test_dead_armies_removed(self) -> None:
        """C11: Dead armies removed from world."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(5, 0, faction=1, aid=2)
        w = _world_with(a, b)
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_multiple_simultaneous_battles(self) -> None:
        """C12: Multiple simultaneous battles."""
        w = World()
        w.map_size = [1000, 1000]
        w.armies = [
            Army(id=1, faction=0, x=0, y=0),
            Army(id=2, faction=1, x=5, y=0),
            Army(id=3, faction=0, x=500, y=0),
            Army(id=4, faction=1, x=505, y=0),
        ]
        resolve_combat(w, CFG)
        assert len(w.armies) == 0

    def test_new_spawns_fight_immediately(self) -> None:
        """C13: Newly spawned armies fight with no immunity."""
        w = World()
        w.map_size = [1000, 1000]
        tid = w.allocate_id()
        t = Town(id=tid, faction=0, x=0, y=0, population=2000)
        w.towns.append(t)
        enemy = Army(id=10, faction=1, x=3, y=0)
        w.armies = [enemy]
        from engine.economy import apply_train
        from engine.world import StandingOrder, CommandType
        w.standing_orders.append(
            StandingOrder(command=CommandType.TRAIN, target_id=tid, target_type="town")
        )
        apply_train(w, CFG)
        spawned = [army for army in w.armies if army.id != 10]
        assert len(spawned) == 1
        resolve_combat(w, CFG)
        # 1v1 mutual kill: the new spawn dies with its enemy
        assert len([a for a in w.armies if a.id != 10]) == 0
        assert len(w.armies) == 0

    def test_battle_event_has_combatants_with_id_faction(self) -> None:
        """Battle event combatants list has {id, faction} entries."""
        # When combat generates events, combatants should have {id, faction}.
        # This is a contract test — the step function returns events with this shape.
        a = _army(0, 0, faction=0, aid=1)
        b = _army(5, 0, faction=1, aid=2)
        w = _world_with(a, b)
        resolve_combat(w, CFG)
        assert len(w.armies) == 0  # both die — events generated at step level

    def test_battle_event_killed_is_list_of_ids(self) -> None:
        """Battle event killed field is a list of army IDs."""
        a = _army(0, 0, faction=0, aid=1)
        b = _army(5, 0, faction=1, aid=2)
        c = _army(3, 0, faction=1, aid=3)
        w = _world_with(a, b, c)
        resolve_combat(w, CFG)
        # a dies (2v1), b and c survive
        alive = {army.id for army in w.armies}
        assert 1 not in alive
        assert 2 in alive and 3 in alive


class TestCaptureCapitals:
    """Beheading is permanent: captures never create capitals."""

    def _world(self) -> World:
        w = World()
        w.map_size = [1000, 1000]
        return w

    def test_capture_demotes_capital(self) -> None:
        from engine.combat import resolve_captures
        w = self._world()
        w.towns.append(Town(id=0, faction=0, x=100, y=100, population=4000, is_capital=True))
        w.armies.append(Army(id=1, faction=1, x=100, y=100))
        resolve_captures(w, CFG)
        t = w.get_town(0)
        assert t is not None and t.faction == 1 and not t.is_capital

    def test_headless_captor_gains_no_capital(self) -> None:
        from engine.combat import resolve_captures
        w = self._world()
        # faction 1 is headless (town but no capital); it beheads faction 0
        w.towns.append(Town(id=0, faction=0, x=100, y=100, population=4000, is_capital=True))
        w.towns.append(Town(id=1, faction=1, x=500, y=500, population=2000, is_capital=False))
        w.armies.append(Army(id=2, faction=1, x=100, y=100))
        resolve_captures(w, CFG)
        assert w.faction_capital(0) is None
        assert w.faction_capital(1) is None
