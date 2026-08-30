import { describe, it, expect } from "vitest";
import { factionColors, factionColor } from "../src/color";

describe("color", () => {
  it("returns N distinct colors for N factions", () => {
    const colors = factionColors(6);
    expect(colors).toHaveLength(6);
    expect(new Set(colors).size).toBe(6);
  });

  it("golden angle hues well spaced", () => {
    const colors = factionColors(12);
    // all should be valid HSL strings
    for (const c of colors) {
      expect(c).toMatch(/^hsl\(/);
    }
  });

  it("factionColor returns correct index", () => {
    const c = factionColor(0, 3);
    expect(c).toBe(factionColors(3)[0]);
  });

  it("factionColor bounds", () => {
    // out of range returns fallback
    const c = factionColor(99, 3);
    expect(c).toBe("#888");
  });

  it("deterministic", () => {
    const a = factionColors(5);
    const b = factionColors(5);
    expect(a).toEqual(b);
  });
});
