/**
 * rl_game_min viewer — adapted from rl_game viewer architecture.
 *
 * Turn-by-turn animation: play advances one turn at a time,
 * lerps from→to, stops, then advances again.
 */

import "./styles.css";
import type { Config, TurnRecord, GameRecord, AnimArmy, AnimTown, AnimBattle } from "./types.js";
import { Transform } from "./transform.js";
import { factionColor } from "./color.js";
import { parseJSONL, separateConfigTurns } from "./loader.js";
import { buildArmyAnim, buildTownAnim, lerp as animLerp, easeInOut } from "./animation.js";
import { townRadius } from "./render-entities.js";

/* ── State ── */

let config: Config | null = null;
let turns: TurnRecord[] = [];
let factionCount = 0;
let turn = 0; // logical turn
let playing = false;
let speed = 1;
let panZoom: { scale: number; tx: number; ty: number } = { scale: 1, tx: 0, ty: 0 };
let fitScale = 1;

// animation state
let animFromTurn = 0;
let animToTurn = 0;
let animProgress = 1; // 0..1, 1 = done
let animStart = 0;
let animDuration = 350; // ms per turn at 1×
let animRaf = 0;
let lastPlay = 0;

const mapSize: [number, number] = [1000, 1000];

/* ── DOM refs ── */

let canvas!: HTMLCanvasElement;
let ctx!: CanvasRenderingContext2D;
let svg!: SVGSVGElement;
let worldG!: SVGGElement;
let tooltip!: HTMLDivElement;
let turnLabelEl!: HTMLSpanElement;
let sliderEl!: HTMLInputElement;
let playBtn!: HTMLButtonElement;
let prevBtn!: HTMLButtonElement;
let nextBtn!: HTMLButtonElement;
let speedSel!: HTMLSelectElement;
let factionSelectEl!: HTMLSelectElement;
let infoEl!: HTMLDivElement;
let eventStripEl!: HTMLDivElement;
let mapWrap!: HTMLDivElement;
let scrimEl!: HTMLDivElement;

/* ── Transform helpers (match rl_game) ── */

function fitTransformFor(w: number, h: number, th: number): { scale: number; tx: number; ty: number } {
  const scale = Math.min(w / th, h / th);
  return {
    scale,
    tx: (w - th * scale) / 2,
    ty: (h - th * scale) / 2,
  };
}

function clampPan(
  pz: { scale: number; tx: number; ty: number },
  w: number,
  h: number,
  th: number,
  minScale: number,
): { scale: number; tx: number; ty: number } {
  const scale = Math.max(pz.scale, minScale);
  // clamp so map doesn't go too far off-screen
  const maxTx = w * 0.7;
  const maxTy = h * 0.7;
  const tx = Math.max(-maxTx, Math.min(maxTx, pz.tx));
  const ty = Math.max(-maxTy, Math.min(maxTy, pz.ty));
  return { scale, tx, ty };
}

function screenToWorld(
  sx: number,
  sy: number,
  pz: { scale: number; tx: number; ty: number },
): [number, number] {
  return [(sx - pz.tx) / pz.scale, (sy - pz.ty) / pz.scale];
}

function zoomAtCursor(
  pz: { scale: number; tx: number; ty: number },
  cx: number,
  cy: number,
  factor: number,
  minScale: number,
  w: number,
  h: number,
  th: number,
): { scale: number; tx: number; ty: number } {
  const [wx, wy] = screenToWorld(cx, cy, pz);
  const scale = Math.max(pz.scale * factor, minScale);
  return clampPan({ scale, tx: wx * scale - cx, ty: wy * scale - cy }, w, h, th, minScale);
}

/* ── Helpers ── */

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
}

function frameAt(t: number): TurnRecord {
  return turns[Math.max(0, Math.min(t, turns.length - 1))]!;
}

function getFactions(): number[] {
  const s = new Set<number>();
  for (const t of turns) {
    for (const tw of t.world.towns) s.add(tw.faction);
    for (const ar of t.world.armies) s.add(ar.faction);
  }
  return [...s].sort((a, b) => a - b);
}

/* ── Load ── */

function loadRecord(records: GameRecord[]): void {
  const sep = separateConfigTurns(records);
  config = sep.config;
  turns = sep.turns;
  if (config) {
    mapSize[0] = config.map_size[0];
    mapSize[1] = config.map_size[1];
    factionCount = getFactions().length || 1;
  }
  turn = 0;
  animFromTurn = 0;
  animToTurn = 0;
  animProgress = 1;
  setupFactionSelect();
  fitView();
  draw();
}

/* ── Drawing ── */

function draw(): void {
  if (!config || !ctx) return;
  const th = Math.max(mapSize[0], mapSize[1]);
  const dpr = window.devicePixelRatio || 1;

  // clear canvas
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#faf8f3";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // draw grid in world space
  ctx.setTransform(
    panZoom.scale * dpr, 0, 0,
    panZoom.scale * dpr,
    panZoom.tx * dpr,
    panZoom.ty * dpr,
  );
  ctx.strokeStyle = "rgba(0,0,0,0.08)";
  ctx.lineWidth = 1 / panZoom.scale;
  const step = Math.max(50, Math.pow(10, Math.floor(Math.log10(th / 8))));
  for (let x = 0; x <= th; x += step) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, th);
    ctx.stroke();
  }
  for (let y = 0; y <= th; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(th, y);
    ctx.stroke();
  }
  // map border
  ctx.strokeStyle = "rgba(0,0,0,0.2)";
  ctx.lineWidth = 2 / panZoom.scale;
  ctx.strokeRect(0, 0, mapSize[0], mapSize[1]);
  ctx.restore();

  // draw SVG entities
  worldG.setAttribute(
    "transform",
    `translate(${panZoom.tx},${panZoom.ty}) scale(${panZoom.scale})`,
  );
  while (worldG.firstChild) worldG.removeChild(worldG.firstChild);

  const { towns, armies, battles } = getAnimState();

  // towns
  for (const t of towns) {
    const x = lerp(t.fromX, t.toX, animProgress >= 1 ? 1 : easeInOut(animProgress));
    const y = lerp(t.fromY, t.toY, animProgress >= 1 ? 1 : easeInOut(animProgress));
    const pop = lerp(t.fromPop, t.toPop, animProgress >= 1 ? 1 : easeInOut(animProgress));
    drawTown(x, y, pop, t.faction, t.isCapital, t.spawns, t.dies);
  }

  // armies
  for (const a of armies) {
    const t = animProgress >= 1 ? 1 : easeInOut(animProgress);
    const x = lerp(a.fromX, a.toX, t);
    const y = lerp(a.fromY, a.toY, t);
    drawArmy(x, y, a.faction, a.spawns, a.dies);
  }

  // battles
  for (const b of battles) {
    drawBattle(b.x, b.y, b.combatants.length, b.killed.length);
  }

  updateChrome();
}

function getAnimState(): { towns: AnimTown[]; armies: AnimArmy[]; battles: AnimBattle[] } {
  if (turns.length === 0) return { towns: [], armies: [], battles: [] };
  if (animProgress >= 1 || animFromTurn === animToTurn) {
    const cur = frameAt(turn);
    return {
      towns: buildTownAnim(cur.world.towns, cur.world.towns, cur.events),
      armies: buildArmyAnim(cur.world.armies, cur.world.armies, cur.events),
      battles: cur.events.filter((e) => e.kind === "battle") as unknown as AnimBattle[],
    };
  }
  const cur = frameAt(animFromTurn);
  const nxt = frameAt(animToTurn);
  return {
    towns: buildTownAnim(cur.world.towns, nxt.world.towns, nxt.events),
    armies: buildArmyAnim(cur.world.armies, nxt.world.armies, nxt.events),
    battles: nxt.events
      .filter((e) => e.kind === "battle")
      .map((e) => e as unknown as AnimBattle),
  };
}

function drawTown(
  x: number,
  y: number,
  pop: number,
  faction: number,
  isCapital: boolean,
  spawns: boolean,
  dies: boolean,
): void {
  const r = townRadius(pop, config?.population_cap ?? 100_000);
  const col = factionColor(faction, factionCount);
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("entity");
  if (dies) g.setAttribute("opacity", String(1 - animProgress));
  if (spawns) g.setAttribute("opacity", String(animProgress));

  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  c.setAttribute("cx", String(x));
  c.setAttribute("cy", String(y));
  c.setAttribute("r", String(spawns ? r * animProgress : dies ? r * (1 - animProgress) : r));
  c.setAttribute("fill", col);
  c.setAttribute("stroke", isCapital ? "#111" : "white");
  c.setAttribute("stroke-width", isCapital ? "1.6" : "1");
  g.appendChild(c);

  if (isCapital) {
    const pin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    pin.setAttribute("cx", String(x));
    pin.setAttribute("cy", String(y));
    pin.setAttribute("r", "2.6");
    pin.setAttribute("fill", "white");
    pin.setAttribute("stroke", "#111");
    pin.setAttribute("stroke-width", "0.6");
    g.appendChild(pin);
  }

  g.addEventListener("mouseenter", (e) =>
    showTooltip(e, `Town\nFaction ${faction}${isCapital ? " ★" : ""}\nPop ${Math.round(pop)}\n(${x.toFixed(0)}, ${y.toFixed(0)})`),
  );
  g.addEventListener("mouseleave", hideTooltip);
  worldG.appendChild(g);
}

function drawArmy(
  x: number,
  y: number,
  faction: number,
  spawns: boolean,
  dies: boolean,
): void {
  const col = factionColor(faction, factionCount);
  const sz = 7;
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("entity");
  const alpha = dies ? 1 - animProgress : spawns ? animProgress : 1;
  if (alpha < 1) g.setAttribute("opacity", String(alpha));

  const pg = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  pg.setAttribute(
    "points",
    `${x},${y - sz} ${x - sz * 0.86},${y + sz * 0.5} ${x + sz * 0.86},${y + sz * 0.5}`,
  );
  pg.setAttribute("fill", col);
  pg.setAttribute("stroke", "white");
  pg.setAttribute("stroke-width", "1");
  g.appendChild(pg);

  g.addEventListener("mouseenter", (e) =>
    showTooltip(e, `Army\nFaction ${faction}\n(${x.toFixed(0)}, ${y.toFixed(0)})`),
  );
  g.addEventListener("mouseleave", hideTooltip);
  worldG.appendChild(g);
}

function drawBattle(
  x: number,
  y: number,
  combatants: number,
  killed: number,
): void {
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("entity");
  for (const [dx, dy] of [[-6, -6, 6, 6], [6, -6, -6, 6]]) {
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", String(x + dx[0]));
    l.setAttribute("y1", String(y + dx[1]));
    l.setAttribute("x2", String(x + dx[2]));
    l.setAttribute("y2", String(y + dx[3]));
    l.setAttribute("stroke", "red");
    l.setAttribute("stroke-width", "2");
    g.appendChild(l);
  }
  g.addEventListener("mouseenter", (e) =>
    showTooltip(e, `Battle\n${combatants} combatants\n${killed} killed`),
  );
  g.addEventListener("mouseleave", hideTooltip);
  worldG.appendChild(g);
}

/* ── Tooltip ── */

function showTooltip(e: MouseEvent, text: string): void {
  tooltip.textContent = text;
  tooltip.style.display = "block";
  tooltip.style.left = `${e.clientX + 12}px`;
  tooltip.style.top = `${e.clientY + 12}px`;
}

function hideTooltip(): void {
  tooltip.style.display = "none";
}

/* ── Chrome ── */

function updateChrome(): void {
  if (!turnLabelEl) return;
  const maxTurn = Math.max(0, turns.length - 1);
  turnLabelEl.textContent = `Turn ${turn} / ${maxTurn}`;
  sliderEl.min = "0";
  sliderEl.max = String(maxTurn);
  sliderEl.value = String(turn);
  playBtn.classList.toggle("playing", playing);
  playBtn.setAttribute("aria-pressed", String(playing));
  playBtn.title = playing ? "Pause (Space)" : "Play (Space)";

  // sidebar
  if (!infoEl || turns.length === 0) return;
  const cur = frameAt(turn);
  const factions = new Set<number>([
    ...cur.world.towns.map((t) => t.faction),
    ...cur.world.armies.map((a) => a.faction),
  ]);
  let html = "";
  for (const f of factions) {
    const fTowns = cur.world.towns.filter((t) => t.faction === f);
    const fArmies = cur.world.armies.filter((a) => a.faction === f);
    const score =
      fTowns.reduce((s, t) => s + t.population, 0) +
      fArmies.length * (config?.army_cost ?? 1000);
    const col = factionColor(f, factionCount);
    html += `<div class="kv"><span>Faction ${f}</span><span><span class="dot" style="background:${col}"></span> ${fTowns.length} towns, ${fArmies.length} armies — score ${Math.round(score)}</span></div>`;
  }
  // recent events
  if (cur.events.length > 0) {
    html += `<div style="margin-top:0.5rem;font-weight:600;">Events</div>`;
    for (const e of cur.events.slice(0, 8)) {
      const k = e.kind;
      const detail =
        k === "army_death" ? `army ${e.id} died` :
        k === "army_spawn" ? `army ${e.id} spawned` :
        k === "town_spawn" ? `town ${e.id} spawned` :
        k === "town_death" ? `town ${e.id} died` :
        k === "battle" ? `battle at (${(e.x as number).toFixed(0)},${(e.y as number).toFixed(0)})` :
        k;
      html += `<div class="kv"><span style="color:var(--text-muted)">${k}</span><span>${detail}</span></div>`;
    }
    if (cur.events.length > 8) html += `<div class="kv"><span></span><span>+${cur.events.length - 8} more</span></div>`;
  }
  infoEl.innerHTML = html;

  // event strip
  eventStripEl.innerHTML = "";
  const maxT = Math.max(1, turns.length - 1);
  for (let i = 0; i < turns.length; i++) {
    const evts = turns[i].events;
    const hasBattle = evts.some((e) => e.kind === "battle");
    const hasDeath = evts.some((e) => e.kind === "army_death" || e.kind === "town_death");
    const hasSpawn = evts.some((e) => e.kind === "army_spawn" || e.kind === "town_spawn");
    if (hasBattle || hasDeath || hasSpawn) {
      const dot = document.createElement("div");
      dot.className = "marker";
      if (hasDeath) dot.classList.add("death");
      else if (hasSpawn) dot.classList.add("spawn");
      else dot.style.background = "#888";
      dot.style.left = `${(i / maxT) * 100}%`;
      dot.title = `Turn ${i}: ${evts.map((e) => e.kind).join(", ")}`;
      dot.addEventListener("click", () => goToTurn(i, Math.abs(i - turn) <= 1));
      eventStripEl.appendChild(dot);
    }
  }
}

function setupFactionSelect(): void {
  if (!factionSelectEl) return;
  const factions = getFactions();
  factionSelectEl.innerHTML = "";
  for (const f of factions) {
    const opt = document.createElement("option");
    opt.value = String(f);
    opt.textContent = `Faction ${f}`;
    factionSelectEl.appendChild(opt);
  }
}

/* ── Animation — adapted from rl_game ── */

function goToTurn(target: number, animate = true): void {
  if (turns.length === 0) return;
  target = Math.max(0, Math.min(target, turns.length - 1));
  if (target === turn && animProgress >= 1) return;
  const delta = Math.abs(target - turn);
  // large jumps: no animation
  if (!animate || delta > 1) {
    turn = target;
    animFromTurn = target;
    animToTurn = target;
    animProgress = 1;
    cancelAnimationFrame(animRaf);
    draw();
    return;
  }
  // start per-turn animation
  animFromTurn = turn;
  animToTurn = target;
  animProgress = 0;
  animStart = performance.now();
  animDuration = Math.max(80, 350 / Math.max(0.5, speed));
  turn = target;
  if (animRaf) cancelAnimationFrame(animRaf);
  animRaf = requestAnimationFrame(animateLoop);
}

function animateLoop(now: number): void {
  const elapsed = now - animStart;
  const t = Math.min(1, elapsed / animDuration);
  animProgress = easeInOut(t);
  draw();
  if (t < 1) {
    animRaf = requestAnimationFrame(animateLoop);
  } else {
    animProgress = 1;
  }
}

function togglePlay(): void {
  playing = !playing;
  if (playing) {
    lastPlay = performance.now();
    requestAnimationFrame(playLoop);
  } else {
    lastPlay = 0;
  }
  draw();
}

function playLoop(ts: number): void {
  if (!playing || turns.length === 0) return;
  if (!lastPlay) lastPlay = ts;
  const TURN_MS = 350;
  const elapsed = ts - lastPlay;
  const turnsToAdvance = (elapsed / TURN_MS) * speed;
  if (turnsToAdvance >= 1) {
    const maxTurn = turns.length - 1;
    const next = Math.min(maxTurn, turn + Math.floor(turnsToAdvance));
    if (next !== turn) {
      goToTurn(next, true);
    }
    lastPlay = ts;
    if (turn >= maxTurn) {
      playing = false;
      lastPlay = 0;
      draw();
      return;
    }
  }
  if (playing) requestAnimationFrame(playLoop);
  else lastPlay = 0;
}

/* ── Interactions ── */

function fitView(): void {
  const rect = mapWrap?.getBoundingClientRect();
  if (!rect) return;
  const th = Math.max(mapSize[0], mapSize[1]);
  panZoom = fitTransformFor(rect.width, rect.height, th);
  fitScale = panZoom.scale;
}

function setupInteractions(): void {
  // pointer drag
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  mapWrap.addEventListener("pointerdown", (e) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
  });
  mapWrap.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    const rect = mapWrap.getBoundingClientRect();
    const th = Math.max(mapSize[0], mapSize[1]);
    panZoom = clampPan(
      { scale: panZoom.scale, tx: panZoom.tx + dx, ty: panZoom.ty + dy },
      rect.width,
      rect.height,
      th,
      fitScale,
    );
    draw();
  });
  mapWrap.addEventListener("pointerup", () => (dragging = false));
  mapWrap.addEventListener("pointerleave", () => (dragging = false));

  // wheel zoom
  mapWrap.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const rect = mapWrap.getBoundingClientRect();
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const th = Math.max(mapSize[0], mapSize[1]);
      panZoom = zoomAtCursor(panZoom, cx, cy, factor, fitScale, rect.width, rect.height, th);
      draw();
    },
    { passive: false },
  );

  // double-click fit
  mapWrap.addEventListener("dblclick", () => {
    fitView();
    draw();
  });

  // keyboard
  window.addEventListener("keydown", (e) => {
    if (e.key === "0") {
      fitView();
      draw();
    } else if (e.key === "ArrowLeft") {
      goToTurn(Math.max(0, turn - 1));
    } else if (e.key === "ArrowRight") {
      goToTurn(Math.min(turns.length - 1, turn + 1));
    } else if (e.key === " ") {
      e.preventDefault();
      togglePlay();
    }
  });

  // controls
  sliderEl.addEventListener("input", () => {
    const target = parseInt(sliderEl.value, 10);
    const animate = Math.abs(target - turn) === 1;
    goToTurn(target, animate);
    playing = false;
    lastPlay = 0;
  });
  prevBtn.addEventListener("click", () => goToTurn(Math.max(0, turn - 1)));
  nextBtn.addEventListener("click", () => goToTurn(Math.min(turns.length - 1, turn + 1)));
  playBtn.addEventListener("click", () => togglePlay());
  speedSel.addEventListener("change", () => {
    speed = parseFloat(speedSel.value);
  });
}

/* ── Boot ── */

function boot(): void {
  const app = document.getElementById("app")!;
  app.innerHTML = `
    <header>
      <label>
        <span style="font-size:0.85rem;font-weight:600;">Faction:</span>
        <select id="faction-select"></select>
      </label>
      <span class="turn-label" id="turn-label">Turn —</span>
      <button id="btn-fit" title="Fit to view (0 / double-click)">Fit</button>
      <label style="margin-left:auto;display:flex;gap:0.4rem;align-items:center;">
        <input type="file" id="file-input" accept=".jsonl" style="font-size:0.8rem;" />
      </label>
    </header>
    <div class="layout">
      <div class="map-wrap" id="map-wrap">
        <canvas id="map-canvas"></canvas>
        <svg id="map-svg"><g id="world-g"></g></svg>
        <div class="scrim" id="scrim" style="display:none;"></div>
        <div class="tooltip" id="tooltip"></div>
      </div>
      <div class="sidebar">
        <div class="card" id="info-card"><h4>Selection</h4><div id="info"></div></div>
      </div>
    </div>
    <div class="timeline">
      <div class="controls">
        <button id="btn-prev" title="Previous turn (←)">⏮</button>
        <button id="btn-play" title="Play/Pause (Space)" aria-pressed="false">▶</button>
        <button id="btn-next" title="Next turn (→)">⏭</button>
        <input type="range" id="slider" min="0" max="100" value="0" />
        <select id="speed" title="Playback speed">
          <option value="0.5">0.5×</option>
          <option value="1" selected>1×</option>
          <option value="2">2×</option>
          <option value="4">4×</option>
          <option value="8">8×</option>
        </select>
      </div>
      <div class="event-strip" id="event-strip"></div>
    </div>
  `;

  canvas = document.getElementById("map-canvas") as HTMLCanvasElement;
  ctx = canvas.getContext("2d")!;
  svg = document.getElementById("map-svg") as unknown as SVGSVGElement;
  worldG = document.getElementById("world-g") as unknown as SVGGElement;
  tooltip = document.getElementById("tooltip") as HTMLDivElement;
  turnLabelEl = document.getElementById("turn-label") as HTMLSpanElement;
  sliderEl = document.getElementById("slider") as HTMLInputElement;
  playBtn = document.getElementById("btn-play") as HTMLButtonElement;
  prevBtn = document.getElementById("btn-prev") as HTMLButtonElement;
  nextBtn = document.getElementById("btn-next") as HTMLButtonElement;
  speedSel = document.getElementById("speed") as HTMLSelectElement;
  factionSelectEl = document.getElementById("faction-select") as HTMLSelectElement;
  infoEl = document.getElementById("info") as HTMLDivElement;
  eventStripEl = document.getElementById("event-strip") as HTMLDivElement;
  mapWrap = document.getElementById("map-wrap") as HTMLDivElement;
  scrimEl = document.getElementById("scrim") as HTMLDivElement;

  document.getElementById("btn-fit")!.addEventListener("click", () => {
    fitView();
    draw();
  });

  const fileInput = document.getElementById("file-input") as HTMLInputElement;
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    const text = await file.text();
    const records = parseJSONL(text);
    loadRecord(records);
  });

  setupInteractions();
  window.addEventListener("resize", () => {
    resizeCanvas();
    fitView();
    draw();
  });
  resizeCanvas();

  // load from URL param
  const params = new URLSearchParams(location.search);
  const gamePath = params.get("game");
  if (gamePath) {
    fetch(gamePath)
      .then((r) => r.text())
      .then((text) => {
        const records = parseJSONL(text);
        loadRecord(records);
      })
      .catch((err) => console.error("Failed to load game", err));
  }
}

function resizeCanvas(): void {
  const dpr = window.devicePixelRatio || 1;
  const rect = mapWrap.getBoundingClientRect();
  const w = Math.round(rect.width);
  const h = Math.round(rect.height);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  svg.setAttribute("width", String(w));
  svg.setAttribute("height", String(h));
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
}

boot();
