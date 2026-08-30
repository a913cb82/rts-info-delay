/**
 * JSONL loader — parse game record from file or URL.
 * Tests a loadRecord() function that should exist in loader.ts.
 */

import { describe, it, expect } from "vitest";
import type { Config, TurnRecord, GameRecord } from "../src/types";
import { parseJSONL as parseJSONLImpl, separateConfigTurns as separateConfigTurnsImpl } from "../src/loader";

/**
 * Parse a JSONL string into a GameRecord array.
 * Should be extracted into loader.ts.
 */
function parseJSONL(text: string): GameRecord[] {
  return parseJSONLImpl(text);
}

/**
 * Separate config from turns.
 */
function separateConfigTurns(records: GameRecord[]): {
  config: Config | null;
  turns: TurnRecord[];
} {
  return separateConfigTurnsImpl(records);
}

describe("parseJSONL", () => {
  const sampleJSONL = [
    JSON.stringify({
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
    }),
    JSON.stringify({
      type: "turn",
      turn: 1,
      world: { armies: [], towns: [] },
      events: [],
    }),
    JSON.stringify({
      type: "turn",
      turn: 2,
      world: { armies: [], towns: [] },
      events: [],
    }),
  ].join("\n");

  it("parses config + turns from JSONL string", () => {
    const records = parseJSONL(sampleJSONL);
    expect(records).toHaveLength(3);
    expect(records[0].type).toBe("config");
    expect(records[1].type).toBe("turn");
  });

  it("V14 — 500-turn game parses without error", () => {
    const lines: string[] = [];
    lines.push(JSON.stringify({ type: "config", map: [1000, 1000], info_speed: 150, army_speed: 50, army_cost: 1000, interact_radius: 10, population_cap: 100_000, population_growth: 0.001, build_efficiency: 0.5, equilibrium_spacing: 0.4, crowding_decay: 0.3, crowding_asymmetry: 0.006, max_turns: 500, turn_time_ms: 1000 }));
    for (let t = 1; t <= 500; t++) {
      lines.push(JSON.stringify({ type: "turn", turn: t, world: { armies: [{ id: 1, faction: 0, x: t, y: 0 }], towns: [{ id: 2, faction: 0, x: 100, y: 100, population: 500, is_capital: true }] }, events: [] }));
    }
    const records = parseJSONL(lines.join("\n"));
    expect(records).toHaveLength(501);
  });

  it("handles empty events", () => {
    const line = JSON.stringify({ type: "turn", turn: 1, world: { armies: [], towns: [] }, events: [] });
    const records = parseJSONL(line);
    expect(records).toHaveLength(1);
  });

  it("R5c — line-delimited, no outer array", () => {
    // Each line is independent JSON
    const lines = sampleJSONL.split("\n");
    for (const line of lines) {
      expect(() => JSON.parse(line)).not.toThrow();
    }
  });

  it("R5e — turn numbers sequential", () => {
    const records = parseJSONL(sampleJSONL);
    const turns = records.filter((r): r is TurnRecord => r.type === "turn");
    expect(turns[0].turn).toBe(1);
    expect(turns[1].turn).toBe(2);
  });

  it("R5f — config has all defaults", () => {
    const records = parseJSONL(sampleJSONL);
    const config = records[0] as Config;
    expect(config.map).toEqual([1000, 1000]);
    expect(config.info_speed).toBe(150);
    expect(config.army_speed).toBe(50);
    expect(config.army_cost).toBe(1000);
    expect(config.interact_radius).toBe(10);
    expect(config.population_cap).toBe(100_000);
    expect(config.population_growth).toBe(0.001);
    expect(config.build_efficiency).toBe(0.5);
    expect(config.equilibrium_spacing).toBe(0.4);
    expect(config.crowding_decay).toBe(0.3);
    expect(config.crowding_asymmetry).toBe(0.006);
    expect(config.max_turns).toBe(500);
    expect(config.turn_time_ms).toBe(1000);
  });
});

describe("separateConfigTurns", () => {
  it("extracts config and turns", () => {
    const records = parseJSONL([
      JSON.stringify({ type: "config", map: [1000, 1000], info_speed: 150, army_speed: 50, army_cost: 1000, interact_radius: 10, population_cap: 100_000, population_growth: 0.001, build_efficiency: 0.5, equilibrium_spacing: 0.4, crowding_decay: 0.3, crowding_asymmetry: 0.006, max_turns: 500, turn_time_ms: 1000 }),
      JSON.stringify({ type: "turn", turn: 1, world: { armies: [], towns: [] }, events: [] }),
    ].join("\n"));
    const { config, turns } = separateConfigTurns(records);
    expect(config).not.toBeNull();
    expect(config!.type).toBe("config");
    expect(turns).toHaveLength(1);
  });

  it("no config → null", () => {
    const records = parseJSONL(JSON.stringify({ type: "turn", turn: 1, world: { armies: [], towns: [] }, events: [] }));
    const { config } = separateConfigTurns(records);
    expect(config).toBeNull();
  });
});
