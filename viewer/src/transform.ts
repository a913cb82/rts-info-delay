/** View transform — pan/zoom between world coords and screen pixels. */

export class Transform {
  /** World → screen scale (pixels per km). */
  scale: number = 1;
  /** Screen-space pan offset (pixels). */
  offsetX: number = 0;
  offsetY: number = 0;

  /** Apply pan drag. */
  pan(dx: number, dy: number): void {
    this.offsetX += dx;
    this.offsetY += dy;
  }

  /** Apply zoom at screen point. */
  zoom(factor: number, screenX: number, screenY: number): void {
    // TODO: zoom toward (screenX, screenY)
  }

  /** World coords → screen coords. */
  worldToScreen(wx: number, wy: number): [number, number] {
    // TODO
    return [0, 0];
  }

  /** Screen coords → world coords. */
  screenToWorld(sx: number, sy: number): [number, number] {
    // TODO
    return [0, 0];
  }

  /** Fit the entire map into the viewport. */
  fitToView(
    mapWidth: number,
    mapHeight: number,
    canvasWidth: number,
    canvasHeight: number,
  ): void {
    // TODO
  }
}
