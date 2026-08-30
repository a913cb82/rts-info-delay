/**
 * Animation tests — lerp, easing, state building between turns.
 * Tests functions that should exist in animation.ts (to be created).
 *
 * These tests define the spec. They fail until animation.ts is implemented.
 */

import { describe, it, expect } from "vitest";
import type {
  AnimBattle,
  ArmyState,
  TownState,
  GameEvent,
} from "../src/types";
import {
  lerp as lerpImpl,
  easeInOut as easeInOutImpl,
  buildArmyAnim as buildArmyAnimImpl,
  buildTownAnim as buildTownAnimImpl,
} from "../src/animation";

/* ── Helpers: these become the animation.ts API ── */

/** Linear interpolation — delegates to animation.ts */
function lerp(a: number, b: number, t: number): number {
  return lerpImpl(a, b, t);
}

/** Ease-in-out for turn slider — delegates to animation.ts */
function easeInOut(t: number): number {
  return easeInOutImpl(t);
}

/**
 * Build animation state for armies between turn N and N+1.
 * This function should be extracted into animation.ts.
 */
function buildArmyAnim(
  armiesN: ArmyState[],
  armiesN1: ArmyState[],
  events: GameEvent[],
) {
  return buildArmyAnimImpl(armiesN, armiesN1, events);
}

/**
 * Build animation state for towns between turn N and N+1.
 */
function buildTownAnim(
  townsN: TownState[],
  townsN1: TownState[],
  events: GameEvent[],
) {
  return buildTownAnimImpl(townsN, townsN1, events);
}

/* ── Tests ── */

describe("lerp", () => {
  it("50% → halfway", () => {
    expect(lerp(0, 100, 0.5)).toBe(50);
  });

  it("0% → start", () => {
    expect(lerp(10, 20, 0)).toBe(10);
  });

  it("100% → end", () => {
    expect(lerp(10, 20, 1)).toBe(20);
  });
});

describe("easeInOut", () => {
  it("0 → 0", () => {
    expect(easeInOut(0)).toBe(0);
  });

  it("1 → 1", () => {
    expect(easeInOut(1)).toBeCloseTo(1, 10);
  });

  it("0.5 → 0.5 (symmetric midpoint)", () => {
    expect(easeInOut(0.5)).toBeCloseTo(0.5, 2);
  });

  it("smooth — no sharp corners", () => {
    // Derivative at 0 should be 0 (ease in)
    const dt = 0.001;
    const slope0 = (easeInOut(dt) - easeInOut(0)) / dt;
    expect(slope0).toBeLessThan(0.5);
  });
});

describe("buildArmyAnim — basic movement", () => {
  it("army moves from N to N+1 position", () => {
    const n: ArmyState[] = [{ id: 1, faction: 0, x: 0, y: 0 }];
    const n1: ArmyState[] = [{ id: 1, faction: 0, x: 50, y: 0 }];
    const anim = buildArmyAnim(n, n1, []);
    expect(anim).toHaveLength(1);
    expect(anim[0].fromX).toBe(0);
    expect(anim[0].toX).toBe(50);
    expect(anim[0].dies).toBe(false);
  });

  it("stationary army has same from/to", () => {
    const n: ArmyState[] = [{ id: 1, faction: 0, x: 100, y: 100 }];
    const n1: ArmyState[] = [{ id: 1, faction: 0, x: 100, y: 100 }];
    const anim = buildArmyAnim(n, n1, []);
    expect(anim[0].fromX).toBe(100);
    expect(anim[0].toX).toBe(100);
  });
});

describe("buildArmyAnim — move→death (V12b)", () => {
  it("army that dies lerps to death position from event", () => {
    const n: ArmyState[] = [{ id: 1, faction: 0, x: 0, y: 0 }];
    const n1: ArmyState[] = []; // army 1 dead, absent from N+1
    const events: GameEvent[] = [
      { kind: "army_death", id: 1, x: 50, y: 0 },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim).toHaveLength(1);
    expect(anim[0].dies).toBe(true);
    expect(anim[0].toX).toBe(50); // endpoint from event, not (0,0)
    expect(anim[0].toY).toBe(0);
  });

  it("lerp to death position — at t=0.5 army at 25km", () => {
    const n: ArmyState[] = [{ id: 1, faction: 0, x: 0, y: 0 }];
    const n1: ArmyState[] = [];
    const events: GameEvent[] = [
      { kind: "army_death", id: 1, x: 50, y: 0 },
    ];
    const anim = buildArmyAnim(n, n1, events);
    const a = anim[0];
    const midX = lerp(a.fromX, a.toX, 0.5);
    expect(midX).toBe(25);
  });

  it("dead army endpoint must not be (0,0) or NaN", () => {
    const n: ArmyState[] = [{ id: 1, faction: 0, x: 10, y: 20 }];
    const n1: ArmyState[] = [];
    const events: GameEvent[] = [
      { kind: "army_death", id: 1, x: 100, y: 200 },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim[0].toX).not.toBeNaN();
    expect(anim[0].toY).not.toBeNaN();
    expect(anim[0].toX).toBe(100);
  });
});

describe("buildArmyAnim — stationary→death (V12c)", () => {
  it("no transit, shrink-fade at same pos", () => {
    const n: ArmyState[] = [{ id: 1, faction: 0, x: 30, y: 30 }];
    const n1: ArmyState[] = [];
    const events: GameEvent[] = [
      { kind: "army_death", id: 1, x: 30, y: 30 },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim[0].fromX).toBe(30);
    expect(anim[0].toX).toBe(30);
    expect(anim[0].dies).toBe(true);
  });
});

describe("buildArmyAnim — blocked move→death (V12d)", () => {
  it("lerps to blocked position, not intended target", () => {
    // Army was heading to (100,0) but blocked at (20,0), dies there
    const n: ArmyState[] = [{ id: 1, faction: 0, x: 0, y: 0 }];
    const n1: ArmyState[] = [];
    const events: GameEvent[] = [
      { kind: "army_death", id: 1, x: 20, y: 0 }, // death pos = blocked pos
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim[0].toX).toBe(20); // NOT 100
  });
});

describe("buildArmyAnim — two armies fight and die", () => {
  it("two armies at different positions both die — each lerps to its death pos", () => {
    const n: ArmyState[] = [
      { id: 1, faction: 0, x: 0, y: 0 },
      { id: 2, faction: 1, x: 10, y: 0 },
    ];
    const n1: ArmyState[] = []; // both dead
    const events: GameEvent[] = [
      { kind: "army_death", id: 1, x: 5, y: 0 },
      { kind: "army_death", id: 2, x: 5, y: 0 },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim).toHaveLength(2);
    const a1 = anim.find((a) => a.id === 1)!;
    const a2 = anim.find((a) => a.id === 2)!;
    // A lerps from (0,0) to (5,0)
    expect(a1.fromX).toBe(0);
    expect(a1.toX).toBe(5);
    expect(a1.dies).toBe(true);
    // B lerps from (10,0) to (5,0)
    expect(a2.fromX).toBe(10);
    expect(a2.toX).toBe(5);
    expect(a2.dies).toBe(true);
  });

  it("two armies die in battle event — each lerps to battle position", () => {
    const n: ArmyState[] = [
      { id: 1, faction: 0, x: 0, y: 0 },
      { id: 2, faction: 1, x: 10, y: 0 },
    ];
    const n1: ArmyState[] = [];
    const events: GameEvent[] = [
      { kind: "battle", x: 5, y: 0, combatants: [{ id: 1, faction: 0 }, { id: 2, faction: 1 }], killed: [1, 2] },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim).toHaveLength(2);
    const a1 = anim.find((a) => a.id === 1)!;
    const a2 = anim.find((a) => a.id === 2)!;
    // Both lerps to battle position (5,0)
    expect(a1.toX).toBe(5);
    expect(a1.dies).toBe(true);
    expect(a2.toX).toBe(5);
    expect(a2.dies).toBe(true);
  });

  it("moving armies with targets die — uses death event pos, not target", () => {
    // A was heading to (100,0), B was heading to (-100,0)
    // Both blocked at (25,0) and died there
    const n: ArmyState[] = [
      { id: 1, faction: 0, x: 0, y: 0 },
      { id: 2, faction: 1, x: 50, y: 0 },
    ];
    const n1: ArmyState[] = [];
    const events: GameEvent[] = [
      { kind: "battle", x: 25, y: 0, combatants: [{ id: 1, faction: 0 }, { id: 2, faction: 1 }], killed: [1, 2] },
    ];
    const anim = buildArmyAnim(n, n1, events);
    const a1 = anim.find((a) => a.id === 1)!;
    const a2 = anim.find((a) => a.id === 2)!;
    // Death pos from battle event, not from N+1 world (absent)
    expect(a1.toX).toBe(25);
    expect(a2.toX).toBe(25);
    // Lerp midpoints
    expect(lerp(a1.fromX, a1.toX, 0.5)).toBe(12.5);
    expect(lerp(a2.fromX, a2.toX, 0.5)).toBe(37.5);
  });

  it("one survives, one dies — survivor stays, dead fades at death pos", () => {
    const n: ArmyState[] = [
      { id: 1, faction: 0, x: 0, y: 0 },
      { id: 2, faction: 1, x: 10, y: 0 },
    ];
    const n1: ArmyState[] = [{ id: 1, faction: 0, x: 5, y: 0 }]; // A survived, moved
    const events: GameEvent[] = [
      { kind: "army_death", id: 2, x: 5, y: 0 }, // B died at midpoint
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim).toHaveLength(2);
    const alive = anim.find((a) => a.id === 1)!;
    const dead = anim.find((a) => a.id === 2)!;
    // A lerps from (0,0) to (5,0) — survived and moved
    expect(alive.dies).toBe(false);
    expect(alive.toX).toBe(5);
    // B lerps from (10,0) to (5,0) — died at same pos
    expect(dead.dies).toBe(true);
    expect(dead.toX).toBe(5);
  });
});

describe("buildArmyAnim — spawn (V13)", () => {
  it("spawned army grows in at source", () => {
    const n: ArmyState[] = [];
    const n1: ArmyState[] = [{ id: 5, faction: 0, x: 100, y: 100 }];
    const events: GameEvent[] = [
      { kind: "army_spawn", id: 5, faction: 0, x: 100, y: 100, is_viceroy: false },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim).toHaveLength(1);
    expect(anim[0].spawns).toBe(true);
    expect(anim[0].spawnX).toBe(100);
    expect(anim[0].spawnY).toBe(100);
  });
});

describe("buildArmyAnim — viceroy (V13d)", () => {
  it("viceroy spawns at capital then moves toward target", () => {
    const n: ArmyState[] = [];
    const n1: ArmyState[] = [{ id: 5, faction: 0, x: 150, y: 150 }];
    const events: GameEvent[] = [
      { kind: "army_spawn", id: 5, faction: 0, x: 100, y: 100, is_viceroy: true },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim[0].spawns).toBe(true);
    expect(anim[0].fromX).toBe(100); // spawned at capital
    expect(anim[0].toX).toBe(150); // moved toward target
  });

  it("viceroy arrival — lerps to destination then fades", () => {
    const n: ArmyState[] = [{ id: 5, faction: 0, x: 180, y: 180 }];
    const n1: ArmyState[] = []; // viceroy gone
    const events: GameEvent[] = [
      { kind: "army_death", id: 5, x: 200, y: 200 },
      { kind: "town_spawn", id: 10, faction: 0, x: 200, y: 200, population: 500, is_capital: true },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim[0].dies).toBe(true);
    expect(anim[0].toX).toBe(200);
  });

  it("full lifecycle: spawn → move → arrive across 3 turns", () => {
    // Turn 1→2: viceroy spawns at (100,100), moves to (150,150)
    let anim = buildArmyAnim(
      [],
      [{ id: 5, faction: 0, x: 150, y: 150 }],
      [{ kind: "army_spawn", id: 5, faction: 0, x: 100, y: 100, is_viceroy: true }],
    );
    expect(anim[0].spawns).toBe(true);
    expect(anim[0].fromX).toBe(100);
    expect(anim[0].toX).toBe(150);
    expect(anim[0].dies).toBe(false);

    // Turn 2→3: viceroy moves from (150,150) to (200,200), arrives, town spawns
    anim = buildArmyAnim(
      [{ id: 5, faction: 0, x: 150, y: 150 }],
      [],
      [
        { kind: "army_death", id: 5, x: 200, y: 200 },
        { kind: "town_spawn", id: 10, faction: 0, x: 200, y: 200, population: 500, is_capital: true },
      ],
    );
    expect(anim[0].dies).toBe(true);
    expect(anim[0].fromX).toBe(150);
    expect(anim[0].toX).toBe(200);

    // Town grows in at arrival position
    const townAnim = buildTownAnim(
      [],
      [{ id: 10, faction: 0, x: 200, y: 200, population: 500, is_capital: true }],
      [{ kind: "town_spawn", id: 10, faction: 0, x: 200, y: 200, population: 500, is_capital: true }],
    );
    expect(townAnim[0].spawns).toBe(true);
    expect(townAnim[0].toX).toBe(200);
  });

  it("viceroy moves and builds capital in same turn", () => {
    // Viceroy at (100,100) moves 25 km to (125,100) and founds town there
    const n: ArmyState[] = [{ id: 5, faction: 0, x: 100, y: 100 }];
    const n1: ArmyState[] = []; // viceroy gone
    const events: GameEvent[] = [
      { kind: "army_death", id: 5, x: 125, y: 100 },
      { kind: "town_spawn", id: 10, faction: 0, x: 125, y: 100, population: 500, is_capital: true },
    ];
    const armyAnim = buildArmyAnim(n, n1, events);
    const townAnim = buildTownAnim(
      [],
      [{ id: 10, faction: 0, x: 125, y: 100, population: 500, is_capital: true }],
      [{ kind: "town_spawn", id: 10, faction: 0, x: 125, y: 100, population: 500, is_capital: true }],
    );
    // Viceroy lerps 25 km to arrival position
    expect(armyAnim[0].fromX).toBe(100);
    expect(armyAnim[0].toX).toBe(125);
    expect(armyAnim[0].dies).toBe(true);
    // At midpoint viceroy is at 112.5
    expect(lerp(armyAnim[0].fromX, armyAnim[0].toX, 0.5)).toBe(112.5);
    // Town grows in at same arrival position
    expect(townAnim[0].spawns).toBe(true);
    expect(townAnim[0].toX).toBe(125);
    // Same position — army fades while town grows
    expect(armyAnim[0].toX).toBe(townAnim[0].toX);
  });

  it("instant arrival — spawn and found same turn", () => {
    // Target = capital position → viceroy arrives immediately
    const n: ArmyState[] = [];
    const n1: ArmyState[] = []; // viceroy already gone
    const events: GameEvent[] = [
      { kind: "army_spawn", id: 5, faction: 0, x: 100, y: 100, is_viceroy: true },
      { kind: "army_death", id: 5, x: 100, y: 100 },
      { kind: "town_spawn", id: 10, faction: 0, x: 100, y: 100, population: 500, is_capital: true },
    ];
    const anim = buildArmyAnim(n, n1, events);
    // Viceroy spawns and dies at same position — no transit
    expect(anim[0].spawns).toBe(true);
    expect(anim[0].dies).toBe(true);
    expect(anim[0].fromX).toBe(100);
    expect(anim[0].toX).toBe(100);
  });

  it("viceroy and town overlap at arrival — army fades while town grows", () => {
    // At the arrival position, army shrinks-fades and town grow-in happen simultaneously
    const n: ArmyState[] = [{ id: 5, faction: 0, x: 180, y: 180 }];
    const n1: ArmyState[] = [];
    const events: GameEvent[] = [
      { kind: "army_death", id: 5, x: 200, y: 200 },
      { kind: "town_spawn", id: 10, faction: 0, x: 200, y: 200, population: 500, is_capital: true },
    ];
    const armyAnim = buildArmyAnim(n, n1, events);
    const townAnim = buildTownAnim(
      [],
      [{ id: 10, faction: 0, x: 200, y: 200, population: 500, is_capital: true }],
      [{ kind: "town_spawn", id: 10, faction: 0, x: 200, y: 200, population: 500, is_capital: true }],
    );
    // Army fades at (200,200)
    expect(armyAnim[0].dies).toBe(true);
    expect(armyAnim[0].toX).toBe(200);
    // Town grows in at same (200,200)
    expect(townAnim[0].spawns).toBe(true);
    expect(townAnim[0].toX).toBe(200);
    // Same position — overlapping animations
    expect(armyAnim[0].toX).toBe(townAnim[0].toX);
    expect(armyAnim[0].toY).toBe(townAnim[0].toY);
  });
});

describe("buildArmyAnim — stacked armies (V5)", () => {
  it("two armies at same pos both get anim state", () => {
    const n: ArmyState[] = [
      { id: 1, faction: 0, x: 50, y: 0 },
      { id: 2, faction: 0, x: 50, y: 0 },
    ];
    const n1: ArmyState[] = [
      { id: 1, faction: 0, x: 50, y: 0 },
    ];
    const events: GameEvent[] = [
      { kind: "army_death", id: 2, x: 50, y: 0 },
    ];
    const anim = buildArmyAnim(n, n1, events);
    expect(anim).toHaveLength(2);
    const alive = anim.find((a) => a.id === 1)!;
    const dead = anim.find((a) => a.id === 2)!;
    expect(alive.dies).toBe(false);
    expect(dead.dies).toBe(true);
  });
});

describe("buildTownAnim", () => {
  it("town grows in pop", () => {
    const n: TownState[] = [{ id: 1, faction: 0, x: 100, y: 100, population: 500, is_capital: false }];
    const n1: TownState[] = [{ id: 1, faction: 0, x: 100, y: 100, population: 600, is_capital: false }];
    const anim = buildTownAnim(n, n1, []);
    expect(anim).toHaveLength(1);
    expect(anim[0].fromPop).toBe(500);
    expect(anim[0].toPop).toBe(600);
  });

  it("town spawn — grows in", () => {
    const n: TownState[] = [];
    const n1: TownState[] = [{ id: 5, faction: 0, x: 200, y: 200, population: 500, is_capital: true }];
    const events: GameEvent[] = [
      { kind: "town_spawn", id: 5, faction: 0, x: 200, y: 200, population: 500, is_capital: true },
    ];
    const anim = buildTownAnim(n, n1, events);
    expect(anim).toHaveLength(1);
    expect(anim[0].spawns).toBe(true);
  });

  it("town death — shrinks out", () => {
    const n: TownState[] = [{ id: 1, faction: 0, x: 100, y: 100, population: 499, is_capital: false }];
    const n1: TownState[] = [];
    const anim = buildTownAnim(n, n1, []);
    expect(anim).toHaveLength(1);
    expect(anim[0].dies).toBe(true);
  });
});
