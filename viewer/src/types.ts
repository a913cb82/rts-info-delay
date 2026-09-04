/* ── Game record types (mirrors engine/record.py JSONL) ── */

export interface Config {
  type: "config";
  map: string;
  map_size: [number, number];
  info_speed: number;
  army_speed: number;
  army_cost: number;
  interact_radius: number;
  line_of_sight?: number;
  population_cap: number;
  population_growth: number;
  build_efficiency: number;
  equilibrium_spacing: number;
  crowding_decay: number;
  crowding_asymmetry: number;
  max_turns: number;
  turn_time_ms: number;
}

export interface ArmyState {
  id: number;
  faction: number;
  x: number;
  y: number;
}

export interface TownState {
  id: number;
  faction: number;
  x: number;
  y: number;
  population: number;
  is_capital: boolean;
}

export interface WorldState {
  armies: ArmyState[];
  towns: TownState[];
}

export interface TurnRecord {
  type: "turn";
  turn: number;
  world: WorldState;
  events: GameEvent[];
}

/* ── Events ── */

export type EventKind =
  | "town_death"
  | "town_capture"
  | "army_spawn"
  | "town_spawn"
  | "army_move"
  | "army_death"
  | "battle";

export interface GameEvent {
  kind: EventKind;
  [key: string]: unknown;
}

export type GameRecord = Config | TurnRecord;

/* ── Animation state ── */

export interface AnimArmy {
  id: number;
  faction: number;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  dies: boolean;
  deathX: number;
  deathY: number;
  spawns: boolean;
  spawnX: number;
  spawnY: number;
  /** True if this is a backward death (died forward, appears backward). */
  isReverse?: boolean;
}

export interface AnimTown {
  id: number;
  faction: number; // = toFaction (backwards compat)
  fromFaction: number;
  toFaction: number;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  fromPop: number;
  toPop: number;
  isCapital: boolean; // = toIsCapital
  fromIsCapital: boolean;
  toIsCapital: boolean;
  dies: boolean;
  spawns: boolean;
}

export interface AnimBattle {
  x: number;
  y: number;
  combatants: { id: number; faction: number }[];
  killed: number[];
}
