/** Faction colour palette — golden-angle distribution. */

const GOLDEN_ANGLE = 137.508;

/** Generate N distinct colours for N factions. */
export function factionColors(n: number): string[] {
  // TODO: HSL golden-angle palette
  return Array.from({ length: n }, (_, i) => `hsl(${(i * GOLDEN_ANGLE) % 360}, 70%, 50%)`);
}

/** Get colour for a specific faction index. */
export function factionColor(faction: number, total: number): string {
  // TODO
  return factionColors(total)[faction] ?? "#888";
}
