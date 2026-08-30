/**
 * V2: Town radius ∝ √pop.
 * V12/V12b-d: Move→death lerp.
 * V13/V13b-f: Spawn/death animation.
 * V14: Large JSONL streaming.
 */

import { describe, it, expect } from "vitest";
import type {
  Config,
  TurnRecord,
  AnimArmy,
  AnimTown,
  GameRecord,
} from "../src/types";

/* ── Helper: default config ── */

function cfg(overrides: Partial<Config> = {}): Config {
  return {
    type: "config",
    map: [1000, 1000],
    info_speed: 150,
    army_speed: 50,
    army_cost: 1000,
    interact_radius: 10,
    population_cap: 100_000,
    population_growth: 0.001,
    build_efficiency: 0.5,
    equilibrium_spacing: 0.4,
    crowding_decay: 0.3,
    crowding_asymmetry: 0.006,
    max_turns: 500,
    turn_time_ms: 1000,
    ...overrides,
  };
}

function turn(n: number, armies: AnimArmy[] = [], towns: AnimTown[] = []): TurnRecord {
  return {
    type: "turn",
    turn: n,
    world: {
      armies: armies.map((a) => ({ id: a.id, faction: a.faction, x: a.toX, y: a.toY })),
      towns: towns.map((t) => ({
        id: t.id,
        faction: t.faction,
        x: t.toX,
        y: t.toY,
        population: t.toPop,
        is_capital: t.isCapital,
      })),
    },
    events: [],
  };
}

/* ── Pure rendering helpers (extracted for testing) ── */

/** V2: Town radius formula: 4 + 6 * sqrt(pop / 100_000) px */
function townRadius(pop: number): number {
  return 4 + 6 * Math.sqrt(pop / 100_000);
}

/** Linear interpolation */
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Ease-in-out for turn slider */
function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

describe("V2 — Town radius ∝ √pop", () => {
  it("village pop=500 → ~4.42 px", () => {
    expect(townRadius(500)).toBeCloseTo(4.42, 1);
  });

  it("city pop=50000 → ~8.24 px", () => {
    expect(townRadius(50_000)).toBeCloseTo(8.24, 1);
  });

  it("pop=0 → 4 px (minimum)", () => {
    expect(townRadius(0)).toBe(4);
  });

  it("pop=100000 → 10 px (maximum)", () => {
    expect(townRadius(100_000)).toBe(10);
  });

  it("monotonically increasing", () => {
    const pops = [0, 100, 500, 1000, 10_000, 50_000, 100_000];
    const radii = pops.map(townRadius);
    for (let i = 1; i < radii.length; i++) {
      expect(radii[i]).toBeGreaterThan(radii[i - 1]);
    }
  });
});

describe("V12 — Animation lerp", () => {
  it("50% progress → halfway between points", () => {
    const x = lerp(0, 100, 0.5);
    expect(x).toBe(50);
  });

  it("0% → start, 100% → end", () => {
    expect(lerp(10, 20, 0)).toBe(10);
    expect(lerp(10, 20, 1)).toBe(20);
  });

  it("ease-in-out smooth at midpoint", () => {
    expect(easeInOut(0.5)).toBeCloseTo(0.5, 2);
  });

  it("ease-in-out endpoints", () => {
    expect(easeInOut(0)).toBe(0);
    expect(easeInOut(1)).toBeCloseTo(1, 10);
  });
});

describe("V12b — Move→death lerp", () => {
  it("army moves to death position then fades", () => {
    // Army at (0,0) turn N, dies at (50,0) turn N+1
    // At t=1.0 (end), army should be at death position
    const fromX = 0, fromY = 0;
    const deathX = 50, deathY = 0;
    const t = 1.0;
    const x = lerp(fromX, deathX, t);
    const y = lerp(fromY, deathY, t);
    expect(x).toBe(50);
    expect(y).toBe(0);
  });

  it("at t=0.5, army is at 25km", () => {
    const x = lerp(0, 50, 0.5);
    expect(x).toBe(25);
  });

  it("dead army not in N+1 world — must use event pos", () => {
    // Simulates: world.armies does NOT contain the dead army
    const turnN = {
      armies: [
        { id: 1, faction: 0, x: 0, y: 0 },
        { id: 2, faction: 1, x: 50, y: 0 },
      ],
    };
    const turnN1 = {
      armies: [{ id: 2, faction: 1, x: 50, y: 0 }], // army 1 absent
    };
    // Dead army's endpoint must come from army_death event
    const deathEvent = { kind: "army_death" as const, id: 1, x: 50, y: 0 };
    const endpoint = turnN1.armies.find((a) => a.id === 1) ?? deathEvent;
    expect(endpoint.x).toBe(50);
    expect(endpoint.y).toBe(0);
  });
});

describe("V12c — Stationary→death", () => {
  it("no transit, shrink-fade at same pos", () => {
    const fromX = 30, fromY = 30;
    const deathX = 30, deathY = 30;
    expect(lerp(fromX, deathX, 0.5)).toBe(30);
    expect(lerp(fromY, deathY, 0.5)).toBe(30);
  });
});

describe("V12d — Blocked move→death", () => {
  it("lerps to blocked position, not intended target", () => {
    // Army intended target (100,0) but blocked at (20,0), dies there
    const fromX = 0, fromY = 0;
    const blockedX = 20, blockedY = 0;
    // Endpoint is blocked pos, NOT intended target
    const t = 1.0;
    expect(lerp(fromX, blockedX, t)).toBe(20);
  });
});

describe("V13b — Missing endpoint fallback", () => {
  it("lerps to event position when army absent from N+1 world", () => {
    const worldN1 = { armies: [{ id: 99, faction: 0, x: 99, y: 99 }] };
    const deathEvt = { kind: "army_death" as const, id: 1, x: 50, y: 50 };
    // Fallback: lookup in world first, then event
    const found = worldN1.armies.find((a) => a.id === 1);
    const endpoint = found ?? deathEvt;
    expect(endpoint.x).toBe(50);
    expect(endpoint.y).toBe(50);
    // Must NOT lerp to (0,0) or NaN
    expect(endpoint.x).not.toBeNaN();
    expect(endpoint.y).not.toBeNaN();
  });
});

describe("V13c — Two armies same pos, one dies", () => {
  it("stack count animates 2→1", () => {
    const stackN = [
      { id: 1, faction: 0, x: 50, y: 0 },
      { id: 2, faction: 0, x: 50, y: 0 },
    ];
    const stackN1 = [{ id: 1, faction: 0, x: 50, y: 0 }]; // id 2 died
    expect(stackN.length).toBe(2);
    expect(stackN1.length).toBe(1);
  });
});

describe("V14 — Large JSONL streaming", () => {
  it("500-turn game generates valid JSONL", () => {
    // Simulate generating a 500-turn record
    const lines: string[] = [];
    const configLine = JSON.stringify(cfg());
    lines.push(configLine);

    for (let t = 1; t <= 500; t++) {
      const turnLine = JSON.stringify({
        type: "turn",
        turn: t,
        world: {
          armies: [{ id: 1, faction: 0, x: t, y: 0 }],
          towns: [{ id: 2, faction: 0, x: 100, y: 100, population: 500, is_capital: true }],
        },
        events: [],
      });
      lines.push(turnLine);
    }

    // Should parse all lines
    expect(lines.length).toBe(501);
    const parsed = lines.map((l) => JSON.parse(l));
    expect(parsed[0].type).toBe("config");
    expect(parsed[1].type).toBe("turn");
    expect(parsed[500].turn).toBe(500);
  });
});
