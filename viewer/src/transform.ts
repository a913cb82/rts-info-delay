/** View transform — pan/zoom between world coords and screen pixels.
 *
 *  Convention (matches rl_game viewer):
 *    worldToScreen(wx) = wx * scale + tx
 *    screenToWorld(sx) = (sx - tx) / scale
 *
 *  Positive tx shifts world right on screen.
 *  Grab-and-drag: dragging right increases tx → world moves right.
 */

export type PanZoom = { scale: number; tx: number; ty: number };

export function fitTransform(
  containerW: number,
  containerH: number,
  mapSize: number,
  padding = 0,
): PanZoom {
  const availW = Math.max(1, containerW - padding * 2);
  const availH = Math.max(1, containerH - padding * 2);
  const scale = Math.min(availW / mapSize, availH / mapSize);
  const tx = (containerW - mapSize * scale) / 2;
  const ty = (containerH - mapSize * scale) / 2;
  return { scale, tx, ty };
}

export function worldToScreen(x: number, y: number, t: PanZoom): [number, number] {
  return [x * t.scale + t.tx, y * t.scale + t.ty];
}

export function screenToWorld(sx: number, sy: number, t: PanZoom): [number, number] {
  return [(sx - t.tx) / t.scale, (sy - t.ty) / t.scale];
}

export function clampScale(s: number, fitScale: number): number {
  return Math.min(8 * fitScale, Math.max(fitScale, s));
}

export function clampPan(
  t: PanZoom,
  containerW: number,
  containerH: number,
  mapSize: number,
  fitScale: number,
): PanZoom {
  const visW = mapSize * t.scale;
  const visH = mapSize * t.scale;
  const minVisible = 0.3;
  const maxTx = containerW - visW * minVisible;
  const minTx = -visW * (1 - minVisible);
  const maxTy = containerH - visH * minVisible;
  const minTy = -visH * (1 - minVisible);
  let nt = { ...t };
  if (t.scale <= fitScale + 1e-6) {
    nt.tx = (containerW - visW) / 2;
    nt.ty = (containerH - visH) / 2;
  } else {
    nt.tx = Math.max(minTx, Math.min(maxTx, t.tx));
    nt.ty = Math.max(minTy, Math.min(maxTy, t.ty));
  }
  return nt;
}

export function zoomAtCursor(
  t: PanZoom,
  cursorX: number,
  cursorY: number,
  factor: number,
  fitScale: number,
  containerW: number,
  containerH: number,
  mapSize: number,
): PanZoom {
  const ns = clampScale(t.scale * factor, fitScale);
  const ratio = ns / t.scale;
  const ntx = cursorX - (cursorX - t.tx) * ratio;
  const nty = cursorY - (cursorY - t.ty) * ratio;
  return clampPan({ scale: ns, tx: ntx, ty: nty }, containerW, containerH, mapSize, fitScale);
}
