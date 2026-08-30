import type { ArmyState, TownState, AnimBattle } from "./types.js";

/** Radius formula: 4 + 6 × √(pop / population_cap) */
export function townRadius(pop: number, cap = 100_000): number {
  if (cap <= 0) return 4;
  if (pop <= 0) return 4;
  return 4 + 6 * Math.sqrt(pop / cap);
}

/** Group armies by position (toFixed 3) for stacking. */
export function groupArmies(armies: ArmyState[]): Map<string, ArmyState[]> {
  const groups = new Map<string, ArmyState[]>();
  for (const a of armies) {
    const key = `${a.x.toFixed(3)},${a.y.toFixed(3)}`;
    const g = groups.get(key) ?? [];
    g.push(a);
    groups.set(key, g);
  }
  return groups;
}

/** Compute sidebar per-faction counts and score. */
export function computeSidebar(
  towns: TownState[],
  armies: ArmyState[],
  armyCost = 1000,
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
      score: fTowns.reduce((s, t) => s + t.population, 0) + fArmies.length * armyCost,
    };
  }
  return result;
}

/** Battle helpers — not drawing, just data. */
export function battleParticipants(battle: AnimBattle): string {
  return `${battle.combatants.length} combatants, ${battle.killed.length} killed`;
}

/** Format town tooltip. */
export function townTooltip(pop: number, isCapital: boolean): string {
  return `Pop: ${pop}${isCapital ? " ★" : ""}`;
}
