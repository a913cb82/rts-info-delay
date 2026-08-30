/** View transform — pan/zoom between world coords and screen pixels. */

export class Transform {
  /** World → screen scale (pixels per km). */
  scale: number = 1;
  /** Screen-space pan offset (pixels). */
  offsetX: number = 0;
  offsetY: number = 0;

  /** Apply pan drag — content follows cursor (grab-and-drag). */
  pan(dx: number, dy: number): void {
    this.offsetX -= dx;
    this.offsetY -= dy;
  }

  /** Apply zoom at screen point — keeps point under cursor fixed. */
  zoom(factor: number, screenX: number, screenY: number): void {
    const [wx, wy] = this.screenToWorld(screenX, screenY);
    this.scale *= factor;
    // new offset so that world point under cursor maps to same screen point
    this.offsetX = wx * this.scale - screenX;
    this.offsetY = wy * this.scale - screenY;
  }

  /** World coords → screen coords. */
  worldToScreen(wx: number, wy: number): [number, number] {
    return [wx * this.scale - this.offsetX, wy * this.scale - this.offsetY];
  }

  /** Screen coords → world coords. */
  screenToWorld(sx: number, sy: number): [number, number] {
    return [(sx + this.offsetX) / this.scale, (sy + this.offsetY) / this.scale];
  }

  /** Fit the entire map into the viewport, centred. */
  fitToView(
    mapWidth: number,
    mapHeight: number,
    canvasWidth: number,
    canvasHeight: number,
  ): void {
    this.scale = Math.min(canvasWidth / mapWidth, canvasHeight / mapHeight);
    // centre map: world centre (mapW/2,mapH/2) → screen centre (canvasW/2,canvasH/2)
    // offset = worldCentre*scale - screenCentre
    this.offsetX = (mapWidth * this.scale) / 2 - canvasWidth / 2;
    this.offsetY = (mapHeight * this.scale) / 2 - canvasHeight / 2;
  }
}
