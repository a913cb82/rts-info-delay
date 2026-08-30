import { describe, it, expect } from "vitest";
import type {
  Config,
  TurnRecord,
  GameRecord,
  ArmySpawnEvent,
  BattleEvent,
} from "../src/types";

describe("types", () => {
  it("Config has all fields", () => {
    const c: Config = {
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
    expect(c.type).toBe("config");
    expect(c.map).toEqual([1000, 1000]);
  });

  it("TurnRecord shape", () => {
    const t: TurnRecord = {
      type: "turn",
      turn: 1,
      world: { armies: [], towns: [] },
      events: [],
    };
    expect(t.type).toBe("turn");
    expect(t.turn).toBe(1);
  });

  it("ArmySpawnEvent fields", () => {
    const e: ArmySpawnEvent = {
      kind: "army_spawn",
      id: 0,
      faction: 0,
      x: 100,
      y: 200,
      is_viceroy: false,
    };
    expect(e.kind).toBe("army_spawn");
  });

  it("BattleEvent fields", () => {
    const e: BattleEvent = {
      kind: "battle",
      x: 50,
      y: 50,
      combatants: [{ id: 0, faction: 0 }],
      killed: [0],
    };
    expect(e.killed).toEqual([0]);
  });

  it("GameRecord is Config | TurnRecord", () => {
    const records: GameRecord[] = [
      {
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
      },
    ];
    expect(records[0]!.type).toBe("config");
  });
});
