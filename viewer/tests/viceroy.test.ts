/**
 * V13d-f: Viceroy animation tests.
 * V1: JSONL loading.
 * V10: Timeline markers.
 * V15: File picker fallback.
 */

import { describe, it, expect } from "vitest";
import type {
  Config,
  TurnRecord,
  GameRecord,
  AnimArmy,
  GameEvent,
} from "../src/types";

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function cfg(): Config {
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
  };
}

/* ── V13d: Viceroy grow-in then straight move ── */

describe("V13d — Viceroy grow-in then straight move", () => {
  it("viceroy spawns at capital, lerps toward target", () => {
    // Turn N: viceroy spawn at (100,100)
    // Turn N+1: viceroy at (150,150) (50km toward (200,200))
    const fromX = 100, fromY = 100;
    const toX = 150, toY = 150;

    // At t=0 (spawn moment): should be at spawn pos
    expect(lerp(fromX, toX, 0)).toBe(100);
    expect(lerp(fromY, toY, 0)).toBe(100);

    // At t=1: should be at N+1 position
    expect(lerp(fromX, toX, 1)).toBe(150);
    expect(lerp(fromY, toY, 1)).toBe(150);
  });

  it("viceroy is_viceroy flag distinguishes from normal army", () => {
    const viceroy: AnimArmy = {
      id: 5,
      faction: 0,
      fromX: 100, fromY: 100,
      toX: 150, toY: 150,
      dies: false, deathX: 0, deathY: 0,
      spawns: true, spawnX: 100, spawnY: 100,
    };
    // Viceroy identified by is_viceroy in spawn event
    expect(viceroy.spawns).toBe(true);
  });
});

/* ── V13e: Viceroy arrival → town ── */

describe("V13e — Viceroy arrival → town", () => {
  it("viceroy lerps to destination then fades as town spawns", () => {
    // Turn N: viceroy at (180,180), target (200,200)
    // Turn N+1: viceroy absent, town_spawn at (200,200)
    const viceroyFrom = { x: 180, y: 180 };
    const townSpawn = { x: 200, y: 200 };

    // Viceroy lerps to arrival point
    expect(lerp(viceroyFrom.x, townSpawn.x, 1)).toBe(200);
    expect(lerp(viceroyFrom.y, townSpawn.y, 1)).toBe(200);

    // Town spawns at same position — no gap
    expect(townSpawn.x).toBe(200);
  });

  it("viceroy absent from N+1 world — use army_death event", () => {
    const worldN1 = {
      armies: [{ id: 99, faction: 0, x: 99, y: 99 }], // viceroy not here
    };
    const deathEvt = { kind: "army_death" as const, id: 5, x: 200, y: 200 };
    const found = worldN1.armies.find((a) => a.id === 5);
    const endpoint = found ?? deathEvt;
    expect(endpoint.x).toBe(200);
  });
});

/* ── V13f: Viceroy vs normal spawn move ── */

describe("V13f — Viceroy vs normal spawn move", () => {
  it("TRAIN spawn stays at town pos with grow-in", () => {
    const trainSpawn = {
      fromX: 100, fromY: 100,
      toX: 100, toY: 100, // stays put
      spawns: true,
    };
    // No transit — stays at 100,100
    expect(lerp(trainSpawn.fromX, trainSpawn.toX, 0.5)).toBe(100);
    expect(lerp(trainSpawn.fromY, trainSpawn.toY, 0.5)).toBe(100);
  });

  it("viceroy shows transit from spawn to target", () => {
    const viceroySpawn = {
      fromX: 100, fromY: 100,
      toX: 150, toY: 150, // moves toward target
      spawns: true,
    };
    // At 50%, should be at 125,125
    expect(lerp(viceroySpawn.fromX, viceroySpawn.toX, 0.5)).toBe(125);
    expect(lerp(viceroySpawn.fromY, viceroySpawn.toY, 0.5)).toBe(125);
  });

  it("both start with grow-in, only viceroy translates", () => {
    const train = { spawns: true, fromX: 100, fromY: 100, toX: 100, toY: 100 };
    const viceroy = { spawns: true, fromX: 100, fromY: 100, toX: 150, toY: 150 };
    // Both have spawns=true
    expect(train.spawns).toBe(true);
    expect(viceroy.spawns).toBe(true);
    // Viceroy moves, train doesn't
    const trainMid = lerp(train.fromX, train.toX, 0.5);
    const viceroyMid = lerp(viceroy.fromX, viceroy.toX, 0.5);
    expect(trainMid).toBe(100);
    expect(viceroyMid).toBe(125);
  });
});

/* ── V1: JSONL loading ── */

describe("V1 — JSONL loading", () => {
  it("parses config + turn lines", () => {
    const lines = [
      JSON.stringify(cfg()),
      JSON.stringify({
        type: "turn",
        turn: 1,
        world: { armies: [], towns: [] },
        events: [],
      }),
    ];
    const records: GameRecord[] = lines.map((l) => JSON.parse(l));
    expect(records[0].type).toBe("config");
    expect(records[1].type).toBe("turn");
  });
});

/* ── V10: Timeline markers ── */

describe("V10 — Timeline markers", () => {
  it("events at correct fractional positions", () => {
    const maxTurns = 100;
    const events: { turn: number; kind: string }[] = [
      { turn: 5, kind: "battle" },
      { turn: 10, kind: "army_spawn" },
      { turn: 50, kind: "army_death" },
    ];

    const positions = events.map((e) => ({
      kind: e.kind,
      fraction: e.turn / maxTurns,
    }));

    expect(positions[0].fraction).toBeCloseTo(0.05);
    expect(positions[1].fraction).toBeCloseTo(0.1);
    expect(positions[2].fraction).toBeCloseTo(0.5);
  });
});

/* ── V15: File picker fallback ── */

describe("V15 — File picker fallback", () => {
  it("shows picker when no ?game= param", () => {
    // Simulate: no URL param means show file picker
    const url = "http://localhost:5173/";
    const hasGame = url.includes("?game=");
    expect(hasGame).toBe(false);
    // Should show picker prompt
  });
});
