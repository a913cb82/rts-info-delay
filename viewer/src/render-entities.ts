import type { ArmyState, TownState, AnimBattle } from "./types.js";

/** Radius formula: 8 + 12 × √(pop / population_cap) */
export function townRadius(pop: number, cap = 100_000): number {
  if (cap <= 0) return 8;
  if (pop <= 0) return 8;
  return 8 + 12 * Math.sqrt(pop / cap);
}

/** Armies scale by size exactly like towns scale by population. */
export function armyRadius(size: number, cap = 10_000): number {
  if (cap <= 0) return 8;
  if (!size || size <= 0) return 8;
  return 8 + 12 * Math.sqrt(size / cap);
}

/** Compute sidebar per-faction counts and score (armies count by size). */
export function computeSidebar(
  towns: TownState[],
  armies: ArmyState[],
): Record<number, { towns: number; armies: number; score: number }> {
  const factions = new Set<number>([
    ...towns.map((t) => t.faction),
    ...armies.map((a) => a.faction),
  ]);
  const result: Record<number, { towns: number; armies: number; score: number }> = {};
  for (const f of factions) {
    const fTowns = towns.filter((t) => t.faction === f);
    const fArmies = armies.filter((a) => a.faction === f);
    result[f] = {
      towns: fTowns.length,
      armies: fArmies.length,
      score: fTowns.reduce((s, t) => s + t.population, 0)
        + fArmies.reduce((s, a) => s + (a.size ?? 1000), 0),
    };
  }
  return result;
}

/** Toggle faction selection (mutually exclusive; clicking the selected one deselects). */
export function toggleFactionSelection(current: number | null, clicked: number): number | null {
  return current === clicked ? null : clicked;
}

/** One live entity as a fog-of-war observer. */
export interface FogEntity {
  faction: number;
  x: number;
  y: number;
  dead: boolean;
}

/** Observer discs (radius = line_of_sight) for one faction's live entities. */
export function fogDiscs(entities: FogEntity[], faction: number, los: number): { x: number; y: number; r: number }[] {
  const discs: { x: number; y: number; r: number }[] = [];
  for (const e of entities) {
    if (e.faction !== faction || e.dead) continue;
    discs.push({ x: e.x, y: e.y, r: los });
  }
  return discs;
}

/** Battle helpers — not drawing, just data. */
export function battleParticipants(battle: AnimBattle): string {
  return `${battle.combatants.length} combatants, ${battle.killed.length} killed`;
}

/** Format town tooltip. */
export function townTooltip(pop: number, isCapital: boolean): string {
  return `Pop: ${pop}${isCapital ? " ★" : ""}`;
}
