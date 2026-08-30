/**
 * Transform tests — pan/zoom between world coords and screen pixels.
 * Tests the standalone functions from transform.ts (matches rl_game convention).
 */

import { describe, it, expect } from "vitest";
import {
  fitTransform,
  worldToScreen,
  screenToWorld,
  clampScale,
  clampPan,
  zoomAtCursor,
} from "../src/transform";
import type { PanZoom } from "../src/transform";

function pz(scale = 1, tx = 0, ty = 0): PanZoom {
  return { scale, tx, ty };
}

describe("worldToScreen / screenToWorld", () => {
  it("identity at scale=1 offset=0", () => {
    expect(worldToScreen(100, 200, pz())).toEqual([100, 200]);
  });

  it("round-trip preserves coordinates", () => {
    const t = pz(1, 50, 30);
    const zoomed = zoomAtCursor(t, 400, 300, 1.5, 0.1, 800, 600, 1000);
    const [wx, wy] = screenToWorld(...worldToScreen(123, 456, zoomed), zoomed);
    expect(wx).toBeCloseTo(123);
    expect(wy).toBeCloseTo(456);
  });

  it("pan shifts world coords (grab-and-drag)", () => {
    // Drag right → tx increases → world origin moves right on screen
    const t = pz(1, 100, 50);
    const [sx, sy] = worldToScreen(0, 0, t);
    expect(sx).toBe(100);
    expect(sy).toBe(50);
  });

  it("zoom 2x at center doubles distances", () => {
    const t = pz(1, 0, 0);
    // fitScale=0.5 so clamp allows up to 4.0
    const zoomed = zoomAtCursor(t, 0, 0, 2, 0.5, 800, 600, 1000);
    // zoom at (0,0): origin stays fixed, point at (100,100) should map to (200,200)
    const [sx, sy] = worldToScreen(100, 100, zoomed);
    expect(sx).toBeCloseTo(200);
    expect(sy).toBeCloseTo(200);
  });
});

describe("zoom", () => {
  it("zoom preserves point under cursor", () => {
    const t = pz(1, 0, 0);
    const zoomed = zoomAtCursor(t, 50, 50, 2, 0.1, 800, 600, 1000);
    const [sx, sy] = worldToScreen(...screenToWorld(50, 50, zoomed), zoomed);
    expect(sx).toBeCloseTo(50);
    expect(sy).toBeCloseTo(50);
  });

  it("zoom 0.5x shrinks", () => {
    const t = pz(1, 0, 0);
    const zoomed = zoomAtCursor(t, 0, 0, 0.5, 0.1, 800, 600, 1000);
    expect(zoomed.scale).toBeCloseTo(0.5);
  });
});

describe("fitTransform", () => {
  it("fits 1000x1000 map into 800x600 canvas", () => {
    const t = fitTransform(800, 600, 1000);
    // scale = min(800/1000, 600/1000) = 0.6
    expect(t.scale).toBeCloseTo(0.6);
  });

  it("centres map in viewport", () => {
    const t = fitTransform(800, 600, 1000);
    // After fit, world centre (500,500) should be at screen centre (400,300)
    const [sx, sy] = worldToScreen(500, 500, t);
    expect(sx).toBeCloseTo(400);
    expect(sy).toBeCloseTo(300);
  });

  it("non-square map uses smaller axis", () => {
    const t = fitTransform(1000, 1000, 2000);
    // scale = min(1000/2000, 1000/2000) = 0.5
    expect(t.scale).toBeCloseTo(0.5);
  });
});
