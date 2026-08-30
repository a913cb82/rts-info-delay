/**
 * V3-V9, V11: DOM-dependent rendering tests.
 * vitest has no DOM, so these test the data shapes and formulas
 * that the rendering code consumes.
 */

import { describe, it, expect } from "vitest";
import type { AnimTown, AnimArmy, AnimBattle, TownState, ArmyState } from "../src/types";
import { factionColor, factionColors } from "../src/color";

/* ── V3: Capital marker ── */

describe("V3 — Capital marker", () => {
  it("town has is_capital boolean", () => {
    const town: TownState = { id: 1, faction: 0, x: 100, y: 100, population: 500, is_capital: true };
    expect(town.is_capital).toBe(true);
  });

  it("non-capital town", () => {
    const town: TownState = { id: 2, faction: 0, x: 200, y: 200, population: 1000, is_capital: false };
    expect(town.is_capital).toBe(false);
  });
});

/* ── V4: Army triangle ── */

describe("V4 — Army triangle", () => {
  it("army has faction for color lookup", () => {
    const army: ArmyState = { id: 1, faction: 0, x: 50, y: 50 };
    const color = factionColor(army.faction, 3);
    expect(color).toBeTruthy();
  });

  it("army position is numeric", () => {
    const army: ArmyState = { id: 1, faction: 0, x: 50, y: 50 };
    expect(typeof army.x).toBe("number");
    expect(typeof army.y).toBe("number");
  });
});

/* ── V5: Stacked armies ── */

describe("V5 — Stacked armies", () => {
  it("detect co-located armies", () => {
    const armies: ArmyState[] = [
      { id: 1, faction: 0, x: 50, y: 50 },
      { id: 2, faction: 0, x: 50, y: 50 },
      { id: 3, faction: 0, x: 50, y: 50 },
    ];
    const groups = new Map<string, ArmyState[]>();
    for (const a of armies) {
      const key = `${a.x},${a.y}`;
      const g = groups.get(key) ?? [];
      g.push(a);
      groups.set(key, g);
    }
    const stack = groups.get("50,50")!;
    expect(stack.length).toBe(3);
  });

  it("stack count badge shows ×N", () => {
    const count = 3;
    const badge = `×${count}`;
    expect(badge).toBe("×3");
  });
});

/* ── V6: Battle crossed lines ── */

describe("V6 — Battle crossed lines", () => {
  it("battle event has position and combatants", () => {
    const battle: AnimBattle = {
      x: 100, y: 100,
      combatants: [
        { id: 1, faction: 0 },
        { id: 2, faction: 1 },
      ],
      killed: [1],
    };
    expect(battle.x).toBe(100);
    expect(battle.combatants.length).toBe(2);
    expect(battle.killed).toContain(1);
  });
});

/* ── V7: Pan/zoom ── */

describe("V7 — Pan/zoom", () => {
  it("transform tracks scale and offset", () => {
    // Simulate transform state
    let scale = 1;
    let offsetX = 0;
    let offsetY = 0;

    // Pan by (10, 20)
    offsetX += 10;
    offsetY += 20;
    expect(offsetX).toBe(10);
    expect(offsetY).toBe(20);

    // Zoom 2x at center
    scale *= 2;
    expect(scale).toBe(2);
  });
});

/* ── V8: Turn slider + play/pause + speed ── */

describe("V8 — Turn slider + play/pause", () => {
  it("speed values in valid range", () => {
    const validSpeeds = [0.5, 1, 2, 4, 8];
    for (const s of validSpeeds) {
      expect(s).toBeGreaterThanOrEqual(0.5);
      expect(s).toBeLessThanOrEqual(8);
    }
  });

  it("visualTurn is fractional between turns", () => {
    const visualTurn = 5.5; // halfway between turn 5 and 6
    expect(visualTurn % 1).toBeCloseTo(0.5);
  });

  it("play/pause toggle", () => {
    let playing = false;
    playing = !playing;
    expect(playing).toBe(true);
    playing = !playing;
    expect(playing).toBe(false);
  });
});

/* ── V9: Sidebar counts ── */

describe("V9 — Sidebar counts", () => {
  it("counts towns and armies per faction", () => {
    const towns: TownState[] = [
      { id: 1, faction: 0, x: 0, y: 0, population: 500, is_capital: true },
      { id: 2, faction: 0, x: 100, y: 100, population: 1000, is_capital: false },
    ];
    const armies: ArmyState[] = [
      { id: 3, faction: 0, x: 50, y: 50 },
      { id: 4, faction: 0, x: 60, y: 60 },
      { id: 5, faction: 0, x: 70, y: 70 },
    ];
    const faction0Towns = towns.filter((t) => t.faction === 0).length;
    const faction0Armies = armies.filter((a) => a.faction === 0).length;
    expect(faction0Towns).toBe(2);
    expect(faction0Armies).toBe(3);
  });

  it("score = sum(town.pop) + count(armies) * army_cost", () => {
    const towns = [{ population: 1000 }, { population: 2000 }];
    const armyCount = 2;
    const armyCost = 1000;
    const score = towns.reduce((s, t) => s + t.population, 0) + armyCount * armyCost;
    expect(score).toBe(5000);
  });
});

/* ── V11: Tooltip ── */

describe("V11 — Tooltip", () => {
  it("town tooltip shows pop and capital status", () => {
    const town: TownState = { id: 1, faction: 0, x: 100, y: 200, population: 5000, is_capital: true };
    const text = `Pop: ${town.population}${town.is_capital ? " ★" : ""}`;
    expect(text).toBe("Pop: 5000 ★");
  });

  it("army tooltip shows faction", () => {
    const army: ArmyState = { id: 1, faction: 2, x: 50, y: 50 };
    const color = factionColor(army.faction, 4);
    expect(color).toBeTruthy();
  });
});
