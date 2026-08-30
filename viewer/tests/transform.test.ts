import { describe, it, expect } from "vitest";
import { Transform } from "../src/transform";

describe("Transform", () => {
  it("worldToScreen identity", () => {
    const t = new Transform();
    // default: scale=1, offset=0 → world coords == screen coords
    expect(t.worldToScreen(100, 200)).toEqual([100, 200]);
  });

  it("screenToWorld identity", () => {
    const t = new Transform();
    expect(t.screenToWorld(100, 200)).toEqual([100, 200]);
  });

  it("zoom preserves point under cursor", () => {
    const t = new Transform();
    // TODO: zoom at (50, 50) by 2x → that world point stays at (50, 50) screen
  });

  it("pan shifts world coords", () => {
    const t = new Transform();
    t.pan(100, 50);
    // world (0,0) should now be at screen (-100, -50)
    const [sx, sy] = t.worldToScreen(0, 0);
    expect(sx).toBe(-100);
    expect(sy).toBe(-50);
  });

  it("fitToView fills canvas", () => {
    const t = new Transform();
    t.fitToView(1000, 1000, 800, 600);
    // scale should fit 1000km map into 600px height (smallest axis)
    expect(t.scale).toBeCloseTo(0.6);
  });

  it("round-trip world → screen → world", () => {
    const t = new Transform();
    t.pan(50, 30);
    t.zoom(1.5, 400, 300);
    const [wx, wy] = t.screenToWorld(...t.worldToScreen(123, 456));
    expect(wx).toBeCloseTo(123);
    expect(wy).toBeCloseTo(456);
  });
});
