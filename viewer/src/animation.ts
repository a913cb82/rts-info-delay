import type {
  ArmyState,
  TownState,
  GameEvent,
  AnimArmy,
  AnimTown,
} from "./types.js";

/** Linear interpolation */
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Ease-in-out for turn slider (quadratic). */
export function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

/**
 * Build animation state for armies between turn N and N+1.
 * - Survivors lerp from N pos to N+1 pos
 * - Dead armies lerp to death position from army_death or battle event
 * - Spawned armies grow in at spawn source (army_spawn event)
 * - Viceroy spawns at capital then moves toward target
 */
export function buildArmyAnim(
  armiesN: ArmyState[],
  armiesN1: ArmyState[],
  events: GameEvent[],
): AnimArmy[] {
  const mapN = new Map<number, ArmyState>();
  for (const a of armiesN) mapN.set(a.id, a);
  const mapN1 = new Map<number, ArmyState>();
  for (const a of armiesN1) mapN1.set(a.id, a);

  // Index death positions: army_death + battle killed
  const deathMap = new Map<number, { x: number; y: number }>();
  for (const e of events) {
    if (e.kind === "army_death") {
      deathMap.set((e as any).id, { x: (e as any).x, y: (e as any).y });
    } else if (e.kind === "battle") {
      for (const kid of (e as any).killed) {
        // battle position is death position
        if (!deathMap.has(kid as number)) {
          deathMap.set(kid as number, { x: (e as any).x, y: (e as any).y });
        }
      }
    }
  }

  // Index spawn positions
  const spawnMap = new Map<number, { x: number; y: number; size: number }>();
  for (const e of events) {
    if (e.kind === "army_spawn") {
      spawnMap.set((e as any).id, { x: (e as any).x, y: (e as any).y, size: (e as any).size ?? 1000 });
    }
  }

  const result: AnimArmy[] = [];

  // Armies that existed in N (survivors or dead)
  for (const [id, aN] of mapN) {
    const aN1 = mapN1.get(id);
    if (aN1) {
      // survivor — lerp from N to N1
      result.push({
        id,
        faction: aN.faction,
        size: aN1.size ?? aN.size ?? 1000,
        fromX: aN.x,
        fromY: aN.y,
        toX: aN1.x,
        toY: aN1.y,
        dies: false,
        deathX: aN1.x,
        deathY: aN1.y,
        spawns: false,
        spawnX: aN.x,
        spawnY: aN.y,
      });
    } else {
      // died — lerp to death position
      const death = deathMap.get(id);
      const toX = death ? death.x : aN.x;
      const toY = death ? death.y : aN.y;
      result.push({
        id,
        faction: aN.faction,
        size: aN.size ?? 1000,
        fromX: aN.x,
        fromY: aN.y,
        toX,
        toY,
        dies: true,
        deathX: toX,
        deathY: toY,
        spawns: false,
        spawnX: aN.x,
        spawnY: aN.y,
      });
    }
  }

  // Armies that are new in N1 (spawned) — also handles backward deaths
  // (army died going forward, so when scrubbing backward it appears to spawn).
  // If this "spawned" army has a death event in the combined events, it died
  // forward at deathPos; backward it should fade in at deathPos and move to
  // its alive position (mirrors rl_game's dyingArmyReverse).
  for (const [id, aN1] of mapN1) {
    if (!mapN.has(id)) {
      const death = deathMap.get(id);
      if (death) {
        // Backward death: army was alive in N1 (earlier frame) and died at deathPos
        // going forward. Going backward, it fades in at deathPos and moves to alive pos.
        result.push({
          id,
          faction: aN1.faction,
          size: aN1.size ?? 1000,
          fromX: death.x,
          fromY: death.y,
          toX: aN1.x,
          toY: aN1.y,
          dies: false,
          deathX: death.x,
          deathY: death.y,
          spawns: true,
          spawnX: death.x,
          spawnY: death.y,
          isReverse: true,
        });
      } else {
        const spawn = spawnMap.get(id);
        const spawnX = spawn ? spawn.x : aN1.x;
        const spawnY = spawn ? spawn.y : aN1.y;
        result.push({
          id,
          faction: aN1.faction,
          size: aN1.size ?? 1000,
          fromX: spawnX,
          fromY: spawnY,
          toX: aN1.x,
          toY: aN1.y,
          dies: false,
          deathX: aN1.x,
          deathY: aN1.y,
          spawns: true,
          spawnX,
          spawnY,
        });
      }
    }
  }

  // Armies that spawn and die in the same turn (instant arrival, e.g. viceroy)
  // Not in N or N1, but appear in both spawn and death events
  for (const [id, spawnPos] of spawnMap) {
    if (mapN.has(id) || mapN1.has(id)) continue; // already handled
    const deathPos = deathMap.get(id);
    if (!deathPos) continue; // spawn only, no death — shouldn't happen here
    result.push({
      id,
      faction: 0, // faction not available from events alone; use 0 as default
      size: spawnPos.size ?? 1000,
      fromX: spawnPos.x,
      fromY: spawnPos.y,
      toX: deathPos.x,
      toY: deathPos.y,
      dies: true,
      deathX: deathPos.x,
      deathY: deathPos.y,
      spawns: true,
      spawnX: spawnPos.x,
      spawnY: spawnPos.y,
    });
  }

  return result;
}

/**
 * Build animation state for towns between turn N and N+1.
 */
export function buildTownAnim(
  townsN: TownState[],
  townsN1: TownState[],
  events: GameEvent[],
): AnimTown[] {
  const mapN = new Map<number, TownState>();
  for (const t of townsN) mapN.set(t.id, t);
  const mapN1 = new Map<number, TownState>();
  for (const t of townsN1) mapN1.set(t.id, t);

  // Index town spawn positions (for new towns)
  const spawnMap = new Map<number, { x: number; y: number }>();
  for (const e of events) {
    if (e.kind === "town_spawn") {
      spawnMap.set((e as any).id, { x: (e as any).x, y: (e as any).y });
    }
  }

  const result: AnimTown[] = [];

  for (const [id, tN] of mapN) {
    const tN1 = mapN1.get(id);
    if (tN1) {
      result.push({
        id,
        faction: tN1.faction,
        fromFaction: tN.faction,
        toFaction: tN1.faction,
        fromX: tN.x,
        fromY: tN.y,
        toX: tN1.x,
        toY: tN1.y,
        fromPop: tN.population,
        toPop: tN1.population,
        isCapital: tN1.is_capital,
        fromIsCapital: tN.is_capital,
        toIsCapital: tN1.is_capital,
        dies: false,
        spawns: false,
      });
    } else {
      // died
      result.push({
        id,
        faction: tN.faction,
        fromFaction: tN.faction,
        toFaction: tN.faction,
        fromX: tN.x,
        fromY: tN.y,
        toX: tN.x,
        toY: tN.y,
        fromPop: tN.population,
        toPop: 0,
        isCapital: tN.is_capital,
        fromIsCapital: tN.is_capital,
        toIsCapital: false,
        dies: true,
        spawns: false,
      });
    }
  }

  for (const [id, tN1] of mapN1) {
    if (!mapN.has(id)) {
      const spawn = spawnMap.get(id);
      const fromX = spawn ? spawn.x : tN1.x;
      const fromY = spawn ? spawn.y : tN1.y;
      result.push({
        id,
        faction: tN1.faction,
        fromFaction: tN1.faction,
        toFaction: tN1.faction,
        fromX,
        fromY,
        toX: tN1.x,
        toY: tN1.y,
        fromPop: 0,
        toPop: tN1.population,
        isCapital: tN1.is_capital,
        fromIsCapital: false,
        toIsCapital: tN1.is_capital,
        dies: false,
        spawns: true,
      });
    }
  }

  return result;
}
