/* ── Game record types (mirrors engine/record.py JSONL) ── */

export interface Config {
  type: "config";
  map: [number, number];
  info_speed: number;
  army_speed: number;
  army_cost: number;
  interact_radius: number;
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
  | "army_spawn"
  | "town_spawn"
  | "army_move"
  | "army_death"
  | "battle";

export interface ArmySpawnEvent {
  kind: "army_spawn";
  id: number;
  faction: number;
  x: number;
  y: number;
  is_viceroy: boolean;
}

export interface TownSpawnEvent {
  kind: "town_spawn";
  id: number;
  faction: number;
  x: number;
  y: number;
  population: number;
  is_capital: boolean;
}

export interface ArmyMoveEvent {
  kind: "army_move";
  id: number;
  x: number;
  y: number;
}

export interface ArmyDeathEvent {
  kind: "army_death";
  id: number;
  x: number;
  y: number;
}

export interface BattleEvent {
  kind: "battle";
  x: number;
  y: number;
  combatants: { id: number; faction: number }[];
  killed: number[];
}

export type GameEvent =
  | ArmySpawnEvent
  | TownSpawnEvent
  | ArmyMoveEvent
  | ArmyDeathEvent
  | BattleEvent;

export type GameRecord = Config | TurnRecord;

/* ── Animation state ── */

export interface AnimArmy {
  id: number;
  faction: number;
  /** Position at start of interpolation (turn N). */
  fromX: number;
  fromY: number;
  /** Position at end of interpolation (turn N+1). */
  toX: number;
  toY: number;
  /** If this army dies this turn, lerp to death pos then fade. */
  dies: boolean;
  deathX: number;
  deathY: number;
  /** If freshly spawned this turn, grow-in at source. */
  spawns: boolean;
  spawnX: number;
  spawnY: number;
}

export interface AnimTown {
  id: number;
  faction: number;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  fromPop: number;
  toPop: number;
  isCapital: boolean;
  dies: boolean;
  spawns: boolean;
}

export interface AnimBattle {
  x: number;
  y: number;
  combatants: { id: number; faction: number }[];
  killed: number[];
}
