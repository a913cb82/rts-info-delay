/**
 * Transform tests — pan/zoom between world coords and screen pixels.
 * Tests the Transform class from transform.ts.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { Transform } from "../src/transform";

let t: Transform;

beforeEach(() => {
  t = new Transform();
});

describe("worldToScreen / screenToWorld", () => {
  it("identity at scale=1 offset=0", () => {
    expect(t.worldToScreen(100, 200)).toEqual([100, 200]);
  });

  it("round-trip preserves coordinates", () => {
    t.pan(50, 30);
    t.zoom(1.5, 400, 300);
    const [wx, wy] = t.screenToWorld(...t.worldToScreen(123, 456));
    expect(wx).toBeCloseTo(123);
    expect(wy).toBeCloseTo(456);
  });

  it("pan shifts world coords", () => {
    t.pan(100, 50);
    const [sx, sy] = t.worldToScreen(0, 0);
    expect(sx).toBe(-100);
    expect(sy).toBe(-50);
  });

  it("zoom 2x at center doubles distances", () => {
    // Zoom at origin preserves origin and doubles distances from origin
    t.zoom(2, 0, 0);
    const [sx, sy] = t.worldToScreen(100, 100);
    expect(sx).toBeCloseTo(200);
    expect(sy).toBeCloseTo(200);
  });
});

describe("zoom", () => {
  it("zoom preserves point under cursor", () => {
    // Zoom 2x at screen (50, 50) — that point should stay fixed
    t.zoom(2, 50, 50);
    const [sx, sy] = t.worldToScreen(...t.screenToWorld(50, 50));
    expect(sx).toBeCloseTo(50);
    expect(sy).toBeCloseTo(50);
  });

  it("zoom 0.5x shrinks", () => {
    t.zoom(0.5, 0, 0);
    expect(t.scale).toBeCloseTo(0.5);
  });
});

describe("fitToView", () => {
  it("fits 1000x1000 map into 800x600 canvas", () => {
    t.fitToView(1000, 1000, 800, 600);
    // scale = min(800/1000, 600/1000) = 0.6
    expect(t.scale).toBeCloseTo(0.6);
  });

  it("centres map in viewport", () => {
    t.fitToView(1000, 1000, 800, 600);
    // After fit, world centre (500,500) should be at screen centre (400,300)
    const [sx, sy] = t.worldToScreen(500, 500);
    expect(sx).toBeCloseTo(400);
    expect(sy).toBeCloseTo(300);
  });

  it("non-square map uses smaller axis", () => {
    t.fitToView(2000, 500, 1000, 1000);
    // scale = min(1000/2000, 1000/500) = 0.5
    expect(t.scale).toBeCloseTo(0.5);
  });
});
