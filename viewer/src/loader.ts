import type { Config, TurnRecord, GameRecord } from "./types.js";

/**
 * Parse a JSONL string into a GameRecord array.
 * Each non-empty line is independent JSON.
 */
export function parseJSONL(text: string): GameRecord[] {
  const records: GameRecord[] = [];
  const lines = text.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.length === 0) continue;
    records.push(JSON.parse(trimmed) as GameRecord);
  }
  return records;
}

/**
 * Separate config from turns.
 */
export function separateConfigTurns(records: GameRecord[]): {
  config: Config | null;
  turns: TurnRecord[];
} {
  let config: Config | null = null;
  const turns: TurnRecord[] = [];
  for (const r of records) {
    if (r.type === "config" && config === null) {
      config = r as Config;
    } else if (r.type === "turn") {
      turns.push(r as TurnRecord);
    }
  }
  return { config, turns };
}
