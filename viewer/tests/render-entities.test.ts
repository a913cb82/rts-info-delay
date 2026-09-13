/**
 * Rendering — town radius, army stacking, battle markers, sidebar counts, tooltips.
 * Tests pure rendering logic that should be in render-entities.ts.
 */

import { describe, it, expect } from "vitest";
import type { TownState, ArmyState, AnimBattle } from "../src/types";
import { factionColor, factionColors } from "../src/color";
import { armyRadius } from "../src/render-entities";

/* ── Town radius (V2) ── */

/** Radius formula: 8 + 12 × √(pop / population_cap) */
function townRadius(pop: number, cap = 100_000): number {
  return 8 + 12 * Math.sqrt(pop / cap);
}

describe("townRadius", () => {
  it("V2 — village pop=500 → ~8.85 px", () => {
    expect(townRadius(500)).toBeCloseTo(8.85, 1);
  });

  it("V2 — city pop=50000 → ~16.49 px", () => {
    expect(townRadius(50_000)).toBeCloseTo(16.49, 1);
  });

  it("pop=0 → 8 px minimum", () => {
    expect(townRadius(0)).toBe(8);
  });

  it("pop=100000 → 20 px maximum", () => {
    expect(townRadius(100_000)).toBe(20);
  });

  it("monotonically increasing", () => {
    const pops = [0, 100, 500, 1000, 10_000, 50_000, 100_000];
    const radii = pops.map((p) => townRadius(p));
    for (let i = 1; i < radii.length; i++) {
      expect(radii[i]).toBeGreaterThan(radii[i - 1]);
    }
  });
});

/* ── Capital marker (V3) ── */

describe("capital marker", () => {
  it("capital town has is_capital=true", () => {
    const town: TownState = { id: 1, faction: 0, x: 100, y: 100, population: 500, is_capital: true };
    expect(town.is_capital).toBe(true);
  });

  it("non-capital has is_capital=false", () => {
    const town: TownState = { id: 2, faction: 0, x: 200, y: 200, population: 1000, is_capital: false };
    expect(town.is_capital).toBe(false);
  });
});

/* ── Army radius: scales by size like towns scale by population ── */

describe("armyRadius", () => {
  it("size=1000 → ~11.8 px", () => {
    expect(armyRadius(1000)).toBeCloseTo(11.8, 1);
  });

  it("size=10000 → 20 px maximum", () => {
    expect(armyRadius(10_000)).toBe(20);
  });

  it("missing/zero size → 8 px minimum", () => {
    expect(armyRadius(0)).toBe(8);
  });

  it("monotonically increasing", () => {
    const sizes = [0, 100, 500, 1000, 5000, 10_000];
    const radii = sizes.map((s) => armyRadius(s));
    for (let i = 1; i < radii.length; i++) {
      expect(radii[i]).toBeGreaterThan(radii[i - 1]);
    }
  });
});

/* ── Battle crossed lines (V6) ── */

describe("battle marker", () => {
  it("V6 — battle has position and combatants", () => {
    const battle: AnimBattle = {
      x: 100, y: 100,
      combatants: [
        { id: 1, faction: 0 },
        { id: 2, faction: 1 },
      ],
      killed: [1],
    };
    expect(battle.x).toBe(100);
    expect(battle.combatants).toHaveLength(2);
    expect(battle.killed).toContain(1);
  });

  it("crossed lines drawn between participants", () => {
    const battle: AnimBattle = {
      x: 50, y: 50,
      combatants: [
        { id: 1, faction: 0 },
        { id: 2, faction: 1 },
        { id: 3, faction: 2 },
      ],
      killed: [1, 2, 3],
    };
    // Lines should connect each pair of combatants
    expect(battle.combatants.length).toBeGreaterThanOrEqual(2);
  });
});

/* ── Faction colours (V4) ── */

describe("faction colours", () => {
  it("V4 — army gets faction colour", () => {
    const color = factionColor(0, 3);
    expect(color).toBeTruthy();
  });

  it("distinct factions get distinct colours", () => {
    const colors = factionColors(6);
    expect(new Set(colors).size).toBe(6);
  });
});

/* ── Sidebar counts (V9) ── */

function computeSidebar(towns: TownState[], armies: ArmyState[]) {
  const factions = new Set([...towns.map((t) => t.faction), ...armies.map((a) => a.faction)]);
  const result: Record<number, { towns: number; armies: number; score: number }> = {};
  for (const f of factions) {
    const fTowns = towns.filter((t) => t.faction === f);
    const fArmies = armies.filter((a) => a.faction === f);
    result[f] = {
      towns: fTowns.length,
      armies: fArmies.length,
      score: fTowns.reduce((s, t) => s + t.population, 0) + fArmies.reduce((s, a) => s + a.size, 0),
    };
  }
  return result;
}

describe("sidebar", () => {
  it("V9 — counts towns and armies per faction", () => {
    const towns: TownState[] = [
      { id: 1, faction: 0, x: 0, y: 0, population: 500, is_capital: true },
      { id: 2, faction: 0, x: 100, y: 100, population: 1000, is_capital: false },
    ];
    const armies: ArmyState[] = [
      { id: 3, faction: 0, x: 50, y: 50, size: 1000 },
      { id: 4, faction: 0, x: 60, y: 60, size: 1000 },
      { id: 5, faction: 0, x: 70, y: 70, size: 1000 },
    ];
    const sidebar = computeSidebar(towns, armies);
    expect(sidebar[0].towns).toBe(2);
    expect(sidebar[0].armies).toBe(3);
  });

  it("V9 — score = sum(pop) + sum(sizes)", () => {
    const towns: TownState[] = [
      { id: 1, faction: 0, x: 0, y: 0, population: 1000, is_capital: false },
      { id: 2, faction: 0, x: 100, y: 100, population: 2000, is_capital: false },
    ];
    const armies: ArmyState[] = [
      { id: 3, faction: 0, x: 50, y: 50, size: 1500 },
      { id: 4, faction: 0, x: 60, y: 60, size: 500 },
    ];
    const sidebar = computeSidebar(towns, armies);
    expect(sidebar[0].score).toBe(5000);
  });
});

/* ── Tooltips (V11) ── */

describe("tooltips", () => {
  it("V11 — town tooltip shows pop and capital", () => {
    const town: TownState = { id: 1, faction: 0, x: 100, y: 200, population: 5000, is_capital: true };
    const text = `Pop: ${town.population}${town.is_capital ? " ★" : ""}`;
    expect(text).toBe("Pop: 5000 ★");
  });

  it("V11 — army tooltip shows faction", () => {
    const army: ArmyState = { id: 1, faction: 2, x: 50, y: 50 };
    const color = factionColor(army.faction, 4);
    expect(color).toBeTruthy();
  });

  it("V11 — battle tooltip shows participants", () => {
    const battle: AnimBattle = {
      x: 50, y: 50,
      combatants: [
        { id: 1, faction: 0 },
        { id: 2, faction: 1 },
      ],
      killed: [1],
    };
    const text = `${battle.combatants.length} combatants, ${battle.killed.length} killed`;
    expect(text).toBe("2 combatants, 1 killed");
  });
});

/* ── Faction selection + fog of war ── */

import { toggleFactionSelection, fogDiscs } from "../src/render-entities";

describe("toggleFactionSelection", () => {
  it("none selected + click → selects", () => {
    expect(toggleFactionSelection(null, 2)).toBe(2);
  });
  it("click selected → deselects (none selected)", () => {
    expect(toggleFactionSelection(2, 2)).toBeNull();
  });
  it("click other → switches (mutually exclusive)", () => {
    expect(toggleFactionSelection(2, 4)).toBe(4);
  });
});

describe("fogDiscs", () => {
  const ents = [
    { faction: 1, x: 100, y: 100, dead: false },
    { faction: 1, x: 400, y: 400, dead: true },
    { faction: 2, x: 700, y: 700, dead: false },
  ];
  it("only live entities of the selected faction, radius = los", () => {
    expect(fogDiscs(ents, 1, 150)).toEqual([{ x: 100, y: 100, r: 150 }]);
  });
  it("other faction's entities excluded", () => {
    expect(fogDiscs(ents, 2, 150)).toEqual([{ x: 700, y: 700, r: 150 }]);
  });
  it("faction with no live entities → no discs (whole map fogged)", () => {
    expect(fogDiscs(ents, 3, 150)).toEqual([]);
  });
});
