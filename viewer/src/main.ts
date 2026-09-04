/**
 * rl_game_min viewer — adapted from rl_game viewer architecture.
 *
 * Turn-by-turn animation: play advances one turn at a time,
 * lerps from→to, stops, then advances again.
 */

import "./styles.css";
import type { Config, TurnRecord, GameRecord, AnimArmy, AnimTown, AnimBattle } from "./types.js";
import { fitTransform, clampPan, zoomAtCursor } from "./transform.js";
import type { PanZoom } from "./transform.js";
import { factionColor } from "./color.js";
import { parseJSONL, separateConfigTurns } from "./loader.js";
import { buildArmyAnim, buildTownAnim } from "./animation.js";
import { townRadius, toggleFactionSelection, fogDiscs } from "./render-entities.js";

/* ── State ── */

let config: Config | null = null;
let turns: TurnRecord[] = [];
let factionCount = 0;
let turn = 0;
let playing = false;
// fog-of-war faction selection (null = none selected, full map bright)
let selectedFaction: number | null = null;
let fogCanvas: HTMLCanvasElement | null = null;
let speed = 1;
let panZoom: PanZoom = { scale: 1, tx: 0, ty: 0 };
let fitScale = 1;

// animation
let animFromTurn = 0;
let animToTurn = 0;
let animProgress = 1;
let animStart = 0;
let animDuration = 350;
let animRaf = 0;
let lastPlay = 0;

const mapSize: [number, number] = [1000, 1000];

// score graph cache
let scoreCache: { perFaction: Map<number, number[]>; maxScore: number } | null = null;
let armyCache: { perFaction: Map<number, number[]>; maxArmies: number } | null = null;

/* ── DOM ── */

let canvas!: HTMLCanvasElement;
let ctx!: CanvasRenderingContext2D;
let svg!: SVGSVGElement;
let worldG!: SVGGElement;
let tooltip!: HTMLDivElement;
let turnLabelEl!: HTMLSpanElement;
let factionNamesEl!: HTMLDivElement;

let playBtn!: HTMLButtonElement;
let speedSel!: HTMLSelectElement;
let graphCanvas!: HTMLCanvasElement;
let graphCtx!: CanvasRenderingContext2D;
let scoreBarEl!: HTMLDivElement;
let armyBarEl!: HTMLDivElement;
let settleBarEl!: HTMLDivElement;
let mapWrap!: HTMLDivElement;

/* ── Helpers ── */

function lerp(a: number, b: number, t: number): number { return a + (b - a) * t; }
function easeInOut(t: number): number { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }
function frameAt(t: number): TurnRecord { return turns[Math.max(0, Math.min(t, turns.length - 1))]!; }
function getFactions(): number[] {
  const s = new Set<number>();
  for (const t of turns) {
    for (const tw of t.world.towns) s.add(tw.faction);
    for (const ar of t.world.armies) s.add(ar.faction);
  }
  return [...s].sort((a, b) => a - b);
}

function computeScore(world: { towns: { faction: number; population: number }[]; armies: { faction: number }[] }, faction: number): number {
  const pop = world.towns.filter((t) => t.faction === faction).reduce((s, t) => s + t.population, 0);
  const armies = world.armies.filter((a) => a.faction === faction).length;
  return pop + armies * (config?.army_cost ?? 1000);
}

function computeArmies(world: { armies: { faction: number }[] }, faction: number): number {
  return world.armies.filter((a) => a.faction === faction).length;
}

function computeSettlements(world: { towns: { faction: number }[] }, faction: number): number {
  return world.towns.filter((t) => t.faction === faction).length;
}

function buildScoreCache(): void {
  const facs = getFactions();
  const perFaction = new Map<number, number[]>();
  const armyPerFaction = new Map<number, number[]>();
  let maxScore = 1;
  let maxArmies = 1;
  for (const f of facs) {
    const arr: number[] = [];
    const aArr: number[] = [];
    for (let i = 0; i < turns.length; i++) {
      const s = computeScore(turns[i]!.world, f);
      arr.push(s);
      maxScore = Math.max(maxScore, s);
      const ac = computeArmies(turns[i]!.world, f);
      aArr.push(ac);
      maxArmies = Math.max(maxArmies, ac);
    }
    perFaction.set(f, arr);
    armyPerFaction.set(f, aArr);
  }
  scoreCache = { perFaction, maxScore };
  armyCache = { perFaction: armyPerFaction, maxArmies };
}

/* ── Load ── */

/* Custom faction names via ?names=pro,greedy,... (defaults to "Faction N").
   Recordings only carry faction numbers, so bot names must come from the URL. */
let _customNames: string[] | null | undefined;
function customFactionNames(): string[] | null {
  if (_customNames === undefined) {
    const p = new URLSearchParams(location.search).get("names");
    _customNames = p ? p.split(",").map((s) => s.trim()).filter((s) => s.length > 0) : null;
  }
  return _customNames;
}

function renderFactionNames(): void {
  if (!factionNamesEl) return;
  factionNamesEl.innerHTML = "";
  const custom = customFactionNames();
  for (const f of getFactions()) {
    const span = document.createElement("span");
    span.className = "faction-name";
    span.style.color = factionColor(f, factionCount);
    span.textContent = custom && custom[f] ? custom[f]! : `Faction ${f}`;
    span.title = `Faction ${f} — click to view fog of war`;
    span.setAttribute("role", "button");
    span.classList.toggle("selected", selectedFaction === f);
    span.addEventListener("click", () => {
      selectedFaction = toggleFactionSelection(selectedFaction, f);
      renderFactionNames();
      draw();
    });
    factionNamesEl.appendChild(span);
  }
}

function loadRecord(records: GameRecord[]): void {
  const sep = separateConfigTurns(records);
  config = sep.config;
  turns = sep.turns;
  if (config) {
    mapSize[0] = config.map_size[0];
    mapSize[1] = config.map_size[1];
    factionCount = getFactions().length || 1;
  }
  selectedFaction = null;
  renderFactionNames();
  turn = 0;
  animFromTurn = 0;
  animToTurn = 0;
  animProgress = 1;
  scoreCache = null;
  buildScoreCache();
  fitView();
  draw();
}

/* ── Drawing ── */

/* ── Fog of war ──
   Darkens all land outside the selected faction's line-of-sight discs.
   Position truth (no info_speed delay); entities stay fully visible. */
function drawFog(): void {
  if (selectedFaction === null || !config || !ctx) return;
  const los = config.line_of_sight ?? 150;
  const { towns, armies } = getAnimState();
  const eased = animProgress >= 1 ? 1 : animProgress;
  const entities: { faction: number; x: number; y: number; dead: boolean }[] = [];
  for (const t of towns) {
    entities.push({
      faction: t.toFaction,
      x: lerp(t.fromX, t.toX, eased),
      y: lerp(t.fromY, t.toY, eased),
      dead: t.dies,
    });
  }
  for (const a of armies) {
    const p = stagedArmyPos(a, animProgress >= 1 ? 1 : animProgress);
    entities.push({ faction: a.faction, x: p.x, y: p.y, dead: a.dies });
  }
  const discs = fogDiscs(entities, selectedFaction, los);
  if (!fogCanvas) fogCanvas = document.createElement("canvas");
  if (fogCanvas.width !== canvas.width || fogCanvas.height !== canvas.height) {
    fogCanvas.width = canvas.width;
    fogCanvas.height = canvas.height;
  }
  const fctx = fogCanvas.getContext("2d")!;
  fctx.save();
  fctx.setTransform(1, 0, 0, 1, 0, 0);
  fctx.clearRect(0, 0, fogCanvas.width, fogCanvas.height);
  fctx.setTransform(panZoom.scale, 0, 0, panZoom.scale, panZoom.tx, panZoom.ty);
  fctx.fillStyle = "rgba(75, 75, 75, 0.38)";
  fctx.fillRect(0, 0, mapSize[0], mapSize[1]);
  fctx.globalCompositeOperation = "destination-out";
  for (const d of discs) {
    fctx.beginPath();
    fctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
    fctx.fill();
  }
  fctx.restore();
  // blit over the map background, under the SVG entities
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.drawImage(fogCanvas, 0, 0);
  ctx.restore();
}

function draw(): void {
  if (!config || !ctx) return;
  const th = Math.max(mapSize[0], mapSize[1]);

  // clear canvas
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#e8f5e9";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // map background
  ctx.fillStyle = "#c8e6c9";
  ctx.setTransform(panZoom.scale, 0, 0, panZoom.scale, panZoom.tx, panZoom.ty);
  ctx.fillRect(0, 0, mapSize[0], mapSize[1]);

  // grid
  ctx.strokeStyle = "rgba(46, 125, 50, 0.18)";
  ctx.lineWidth = 1 / panZoom.scale;
  const step = Math.max(50, Math.pow(10, Math.floor(Math.log10(th / 8))));
  for (let x = 0; x <= th; x += step) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, th); ctx.stroke(); }
  for (let y = 0; y <= th; y += step) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(th, y); ctx.stroke(); }
  // border
  ctx.strokeStyle = "rgba(46, 125, 50, 0.35)";
  ctx.lineWidth = 2 / panZoom.scale;
  ctx.strokeRect(0, 0, mapSize[0], mapSize[1]);
  drawFog();
  ctx.restore();

  // SVG entities
  worldG.setAttribute("transform", `translate(${panZoom.tx},${panZoom.ty}) scale(${panZoom.scale})`);
  while (worldG.firstChild) worldG.removeChild(worldG.firstChild);

  const { towns, armies, battles } = getAnimState();
  const eased = animProgress >= 1 ? 1 : animProgress;

  for (const t of towns) {
    const x = lerp(t.fromX, t.toX, eased);
    const y = lerp(t.fromY, t.toY, eased);
    const pop = lerp(t.fromPop, t.toPop, eased);
    drawTown(t, eased, x, y, pop);
  }

  for (const a of armies) {
    const p = animProgress >= 1 ? 1 : animProgress;
    const { x, y, alpha } = stagedArmyPos(a, p);
    drawArmy(x, y, a.faction, alpha);
  }

  for (const b of battles) drawBattle(b.x, b.y, b.combatants.length, b.killed.length);

  updateChrome();
  drawGraph();
  drawScoreBar();
  drawSettlementsBar();
  drawArmyBar();
}

function getAnimState(): { towns: AnimTown[]; armies: AnimArmy[]; battles: AnimBattle[] } {
  if (turns.length === 0) return { towns: [], armies: [], battles: [] };
  if (animProgress >= 1 || animFromTurn === animToTurn) {
    const cur = frameAt(turn);
    return {
      towns: buildTownAnim(cur.world.towns, cur.world.towns, cur.events),
      armies: buildArmyAnim(cur.world.armies, cur.world.armies, cur.events),
      battles: [],
    };
  }
  const cur = frameAt(animFromTurn);
  const nxt = frameAt(animToTurn);
  const combinedEvents = [...cur.events, ...nxt.events] as unknown as import("./types.js").GameEvent[];
  const isForward = animFromTurn < animToTurn;
  const battleEvents = isForward ? nxt.events : cur.events;
  return {
    towns: buildTownAnim(cur.world.towns, nxt.world.towns, combinedEvents),
    armies: buildArmyAnim(cur.world.armies, nxt.world.armies, combinedEvents),
    battles: battleEvents.filter((e) => (e as any).kind === "battle").map((e) => e as unknown as AnimBattle),
  };
}

// ── Staged animation ──

function stagedArmyPos(a: AnimArmy, progress: number): { x: number; y: number; alpha: number } {
  if (a.dies) {
    const mt = Math.min(1, progress / 0.7);
    const alpha = progress < 0.7 ? 1 : 1 - (progress - 0.7) / 0.3;
    return { x: lerp(a.fromX, a.toX, mt), y: lerp(a.fromY, a.toY, mt), alpha };
  }
  if ((a as any).isReverse) {
    const mt = Math.max(0, (progress - 0.3) / 0.7);
    const alpha = Math.min(1, progress / 0.3);
    return { x: lerp(a.fromX, a.toX, mt), y: lerp(a.fromY, a.toY, mt), alpha };
  }
  if (a.spawns) return { x: lerp(a.fromX, a.toX, progress), y: lerp(a.fromY, a.toY, progress), alpha: progress };
  return { x: lerp(a.fromX, a.toX, progress), y: lerp(a.fromY, a.toY, progress), alpha: 1 };
}

/* ── Entity drawing ── */

function drawTown(t: AnimTown, eased: number, x: number, y: number, pop: number): void {
  const isCapture = t.fromFaction !== t.toFaction;
  const capChange = t.fromIsCapital !== t.toIsCapital;
  // Dies/spawns use alpha fade, captures use cross-fade (always visible)
  let alpha = 1;
  if (t.dies) alpha = 1 - eased;
  else if (t.spawns) alpha = eased;

  const r = townRadius(pop, config?.population_cap ?? 100_000);
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("entity");
  if (alpha < 1) g.setAttribute("opacity", String(alpha));

  // For captures, cross-fade faction colors during lerp
  if (isCapture && !t.dies && !t.spawns) {
    const fromCol = factionColor(t.fromFaction, factionCount);
    const toCol = factionColor(t.toFaction, factionCount);
    const curR = r;
    // From faction circle fading out
    const cFrom = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    cFrom.setAttribute("cx", String(x));
    cFrom.setAttribute("cy", String(y));
    cFrom.setAttribute("r", String(curR));
    cFrom.setAttribute("fill", fromCol);
    cFrom.setAttribute("stroke", t.fromIsCapital ? "#111" : "white");
    cFrom.setAttribute("stroke-width", t.fromIsCapital ? "1.6" : "1");
    cFrom.setAttribute("opacity", String(1 - eased));
    g.appendChild(cFrom);
    // To faction circle fading in
    const cTo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    cTo.setAttribute("cx", String(x));
    cTo.setAttribute("cy", String(y));
    cTo.setAttribute("r", String(curR));
    cTo.setAttribute("fill", toCol);
    cTo.setAttribute("stroke", t.toIsCapital ? "#111" : "white");
    cTo.setAttribute("stroke-width", t.toIsCapital ? "1.6" : "1");
    cTo.setAttribute("opacity", String(eased));
    g.appendChild(cTo);
    // Capital marker cross-fade if needed
    if (capChange) {
      if (t.fromIsCapital) {
        const pinFrom = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        pinFrom.setAttribute("cx", String(x)); pinFrom.setAttribute("cy", String(y));
        pinFrom.setAttribute("r", "2.6"); pinFrom.setAttribute("fill", "white");
        pinFrom.setAttribute("stroke", "#111"); pinFrom.setAttribute("stroke-width", "0.6");
        pinFrom.setAttribute("opacity", String(1 - eased));
        g.appendChild(pinFrom);
      }
      if (t.toIsCapital) {
        const pinTo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        pinTo.setAttribute("cx", String(x)); pinTo.setAttribute("cy", String(y));
        pinTo.setAttribute("r", "2.6"); pinTo.setAttribute("fill", "white");
        pinTo.setAttribute("stroke", "#111"); pinTo.setAttribute("stroke-width", "0.6");
        pinTo.setAttribute("opacity", String(eased));
        g.appendChild(pinTo);
      }
    } else if (t.toIsCapital) {
      // No cap change but is capital — show pin (or cross-fade handled above)
      const pin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      pin.setAttribute("cx", String(x)); pin.setAttribute("cy", String(y));
      pin.setAttribute("r", "2.6"); pin.setAttribute("fill", "white");
      pin.setAttribute("stroke", "#111"); pin.setAttribute("stroke-width", "0.6");
      g.appendChild(pin);
    }
  } else {
    // Normal dies/spawns or non-capture survivor
    const faction = t.toFaction;
    const isCap = t.toIsCapital;
    const col = factionColor(faction, factionCount);
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", String(x));
    c.setAttribute("cy", String(y));
    c.setAttribute("r", String(r * (alpha < 1 && alpha > 0 ? 0.2 + 0.8 * alpha : 1)));
    c.setAttribute("fill", col);
    c.setAttribute("stroke", isCap ? "#111" : "white");
    c.setAttribute("stroke-width", isCap ? "1.6" : "1");
    g.appendChild(c);
    if (isCap) {
      const pin = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      pin.setAttribute("cx", String(x)); pin.setAttribute("cy", String(y));
      pin.setAttribute("r", "2.6"); pin.setAttribute("fill", "white");
      pin.setAttribute("stroke", "#111"); pin.setAttribute("stroke-width", "0.6");
      if (t.dies || t.spawns) pin.setAttribute("opacity", String(alpha));
      g.appendChild(pin);
    }
  }

  const displayFaction = isCapture ? `${t.fromFaction}→${t.toFaction}` : String(t.toFaction);
  g.addEventListener("mouseenter", (e) => showTooltip(e, `Town\nFaction ${displayFaction}${t.toIsCapital ? " ★" : ""}\nPop ${Math.round(pop)}\n(${x.toFixed(0)}, ${y.toFixed(0)})`));
  g.addEventListener("mouseleave", hideTooltip);
  worldG.appendChild(g);
}

function drawArmy(x: number, y: number, faction: number, alpha: number): void {
  const col = factionColor(faction, factionCount);
  const sz = 14;
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("entity");
  if (alpha < 1) g.setAttribute("opacity", String(alpha));
  const pg = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  pg.setAttribute("points", `${x},${y - sz} ${x - sz * 0.86},${y + sz * 0.5} ${x + sz * 0.86},${y + sz * 0.5}`);
  pg.setAttribute("fill", col); pg.setAttribute("stroke", "white"); pg.setAttribute("stroke-width", "1");
  g.appendChild(pg);
  g.addEventListener("mouseenter", (e) => showTooltip(e, `Army\nFaction ${faction}\n(${x.toFixed(0)}, ${y.toFixed(0)})`));
  g.addEventListener("mouseleave", hideTooltip);
  worldG.appendChild(g);
}

function drawBattle(x: number, y: number, combatants: number, killed: number): void {
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("entity");
  for (const [x1, y1, x2, y2] of [[-6, -6, 6, 6], [6, -6, -6, 6]] as const) {
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", String(x + x1)); l.setAttribute("y1", String(y + y1));
    l.setAttribute("x2", String(x + x2)); l.setAttribute("y2", String(y + y2));
    l.setAttribute("stroke", "red"); l.setAttribute("stroke-width", "2");
    g.appendChild(l);
  }
  g.addEventListener("mouseenter", (e) => showTooltip(e, `Battle\n${combatants} combatants\n${killed} killed`));
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
function hideTooltip(): void { tooltip.style.display = "none"; }

/* ── Score bar ── */

function drawScoreBar(): void {
  if (!scoreBarEl || !scoreCache || turns.length === 0) return;
  const cur = frameAt(turn);
  const facs = getFactions();
  const scores = facs.map((f) => ({ faction: f, score: computeScore(cur.world, f) }));
  const total = scores.reduce((s, x) => s + x.score, 0) || 1;
  scoreBarEl.innerHTML = "";
  for (const { faction, score } of scores) {
    const pct = (score / total) * 100;
    const seg = document.createElement("div");
    seg.className = "seg";
    seg.style.width = `${pct}%`;
    seg.style.background = factionColor(faction, factionCount);
    seg.textContent = `${Math.round(score)}`;
    seg.title = `Faction ${faction}: ${Math.round(score)}`;
    scoreBarEl.appendChild(seg);
  }
}

function drawSettlementsBar(): void {
  if (!settleBarEl || turns.length === 0) return;
  const cur = frameAt(turn);
  const facs = getFactions();
  const counts = facs.map((f) => ({ faction: f, count: computeSettlements(cur.world, f) }));
  const total = counts.reduce((s, x) => s + x.count, 0) || 1;
  settleBarEl.innerHTML = "";
  for (const { faction, count } of counts) {
    const pct = (count / total) * 100;
    const seg = document.createElement("div");
    seg.className = "seg";
    seg.style.width = `${pct}%`;
    seg.style.background = factionColor(faction, factionCount);
    seg.textContent = `${count}`;
    seg.title = `Faction ${faction}: ${count} settlements`;
    settleBarEl.appendChild(seg);
  }
}

function drawArmyBar(): void {
  if (!armyBarEl || !armyCache || turns.length === 0) return;
  const cur = frameAt(turn);
  const facs = getFactions();
  const counts = facs.map((f) => ({ faction: f, count: computeArmies(cur.world, f) }));
  const total = counts.reduce((s, x) => s + x.count, 0) || 1;
  armyBarEl.innerHTML = "";
  for (const { faction, count } of counts) {
    const pct = (count / total) * 100;
    const seg = document.createElement("div");
    seg.className = "seg";
    seg.style.width = `${pct}%`;
    seg.style.background = factionColor(faction, factionCount);
    seg.textContent = `${count}`;
    seg.title = `Faction ${faction}: ${count} armies`;
    armyBarEl.appendChild(seg);
  }
}

/* ── Score graph ── */

function drawGraph(): void {
  if (!graphCanvas || !graphCtx || !scoreCache || turns.length === 0) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = graphCanvas.getBoundingClientRect();
  const w = Math.round(rect.width * dpr);
  const h = Math.round(rect.height * dpr);
  if (graphCanvas.width !== w || graphCanvas.height !== h) {
    graphCanvas.width = w;
    graphCanvas.height = h;
  }
  const gctx = graphCtx;
  gctx.save();
  gctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const cw = rect.width;
  const ch = rect.height;
  gctx.clearRect(0, 0, cw, ch);
  gctx.fillStyle = "white";
  gctx.fillRect(0, 0, cw, ch);

  const maxT = Math.max(1, turns.length - 1);
  const maxY = scoreCache.maxScore || 1;
  const pad = { l: 40, r: 10, t: 10, b: 20 };
  const plotW = cw - pad.l - pad.r;
  const plotH = ch - pad.t - pad.b;

  // grid
  gctx.strokeStyle = "rgba(0,0,0,0.08)";
  gctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (i / 4) * plotH;
    gctx.beginPath(); gctx.moveTo(pad.l, y); gctx.lineTo(cw - pad.r, y); gctx.stroke();
  }
  // y ticks
  gctx.fillStyle = "#888";
  gctx.font = "10px sans-serif";
  gctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const v = Math.round((1 - i / 4) * maxY);
    gctx.fillText(String(v), pad.l - 4, pad.t + (i / 4) * plotH + 3);
  }
  // x ticks
  gctx.textAlign = "center";
  for (let i = 0; i <= 4; i++) {
    const t = Math.round((i / 4) * maxT);
    gctx.fillText(String(t), pad.l + (t / maxT) * plotW, ch - 4);
  }

  // faction lines
  const facs = getFactions();
  for (const f of facs) {
    const arr = scoreCache.perFaction.get(f);
    if (!arr) continue;
    gctx.strokeStyle = factionColor(f, factionCount);
    gctx.lineWidth = f === getFactions()[0] ? 2 : 1.2;
    gctx.globalAlpha = 0.8;
    gctx.beginPath();
    let started = false;
    for (let t = 0; t < turns.length; t++) {
      const v = arr[t] ?? 0;
      const x = pad.l + (t / maxT) * plotW;
      const y = pad.t + (1 - v / maxY) * plotH;
      if (!started) { gctx.moveTo(x, y); started = true; } else gctx.lineTo(x, y);
    }
    gctx.stroke();
    gctx.globalAlpha = 1;
  }

  // event markers on lines
  for (let t = 0; t < turns.length; t++) {
    const evts = turns[t]!.events;
    const hasEvent = evts.some((e) => e.kind === "battle" || e.kind === "army_death" || e.kind === "town_death");
    if (!hasEvent) continue;
    // find which factions are involved
    const involvedFacs = new Set<number>();
    for (const e of evts) {
      if ((e as any).faction !== undefined) involvedFacs.add((e as any).faction as number);
      if ((e as any).combatants) for (const c of (e as any).combatants) involvedFacs.add(c.faction);
    }
    for (const f of involvedFacs) {
      const arr = scoreCache.perFaction.get(f);
      if (!arr) continue;
      const v = arr[t] ?? 0;
      const x = pad.l + (t / maxT) * plotW;
      const y = pad.t + (1 - v / maxY) * plotH;
      gctx.fillStyle = factionColor(f, factionCount);
      gctx.beginPath();
      gctx.arc(x, y, 3, 0, Math.PI * 2);
      gctx.fill();
      gctx.strokeStyle = "white";
      gctx.lineWidth = 1;
      gctx.stroke();
    }
  }

  // current turn line
  const cx = pad.l + (turn / maxT) * plotW;
  gctx.strokeStyle = "#111";
  gctx.lineWidth = 1.2;
  gctx.setLineDash([4, 3]);
  gctx.beginPath(); gctx.moveTo(cx, pad.t); gctx.lineTo(cx, ch - pad.b); gctx.stroke();
  gctx.setLineDash([]);

  // turn label inside graph (top-right)
  gctx.fillStyle = "#333";
  gctx.font = "bold 12px system-ui, sans-serif";
  gctx.textAlign = "right";
  gctx.fillText(`Turn ${turn} / ${maxT}`, cw - pad.r - 4, pad.t + 12);

  gctx.restore();
}

/* ── Chrome ── */

function updateChrome(): void {
  if (!turnLabelEl) return;
  const maxTurn = Math.max(0, turns.length - 1);
  turnLabelEl.textContent = `Turn ${turn} / ${maxTurn}`;
  playBtn.classList.toggle("playing", playing);
  playBtn.textContent = playing ? "⏹" : "▶";
  playBtn.title = playing ? "Pause (Space)" : "Play (Space)";
}

/* ── Animation ── */

function goToTurn(target: number, animate = true): void {
  if (turns.length === 0) return;
  target = Math.max(0, Math.min(target, turns.length - 1));
  if (target === turn && animProgress >= 1) return;
  const delta = Math.abs(target - turn);
  if (!animate || delta > 1) {
    turn = target; animFromTurn = target; animToTurn = target; animProgress = 1;
    cancelAnimationFrame(animRaf); draw(); return;
  }
  animFromTurn = turn; animToTurn = target; animProgress = 0; animStart = performance.now();
  animDuration = Math.max(80, 350 / Math.max(0.5, speed));
  turn = target;
  if (animRaf) cancelAnimationFrame(animRaf);
  animRaf = requestAnimationFrame(animateLoop);
}

function animateLoop(now: number): void {
  const t = Math.min(1, (now - animStart) / animDuration);
  animProgress = easeInOut(t);
  draw();
  if (t < 1) animRaf = requestAnimationFrame(animateLoop);
  else animProgress = 1;
}

function togglePlay(): void {
  playing = !playing;
  if (playing) { lastPlay = performance.now(); requestAnimationFrame(playLoop); }
  else lastPlay = 0;
  draw();
}

function playLoop(ts: number): void {
  if (!playing || turns.length === 0) return;
  if (!lastPlay) lastPlay = ts;
  const elapsed = ts - lastPlay;
  const turnsToAdvance = (elapsed / 350) * speed;
  if (turnsToAdvance >= 1) {
    const next = Math.min(turns.length - 1, turn + Math.floor(turnsToAdvance));
    if (next !== turn) goToTurn(next, true);
    lastPlay = ts;
    if (turn >= turns.length - 1) { playing = false; lastPlay = 0; draw(); return; }
  }
  if (playing) requestAnimationFrame(playLoop);
  else lastPlay = 0;
}

/* ── Interactions ── */

function fitView(): void {
  const rect = mapWrap?.getBoundingClientRect();
  if (!rect) return;
  panZoom = fitTransform(rect.width, rect.height, Math.max(mapSize[0], mapSize[1]));
  fitScale = panZoom.scale;
}

function setupInteractions(): void {
  // coordinate tooltip on map hover
  mapWrap.addEventListener("mousemove", (e) => {
    // entity tooltips (town/army/battle) take priority
    const target = e.target as Element;
    if (target.closest && target.closest(".entity")) return;
    const rect = mapWrap.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const wx = (sx - panZoom.tx) / panZoom.scale;
    const wy = (sy - panZoom.ty) / panZoom.scale;
    if (wx >= 0 && wy >= 0 && wx <= mapSize[0] && wy <= mapSize[1]) {
      tooltip.textContent = `(${wx.toFixed(0)}, ${wy.toFixed(0)})`;
      tooltip.style.display = "block";
      tooltip.style.left = `${e.clientX + 12}px`;
      tooltip.style.top = `${e.clientY + 12}px`;
    } else {
      tooltip.style.display = "none";
    }
  });
  mapWrap.addEventListener("mouseleave", hideTooltip);

  // pan
  let dragging = false;
  let lastX = 0, lastY = 0;
  mapWrap.addEventListener("pointerdown", (e) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    dragging = true; lastX = e.clientX; lastY = e.clientY;
  });
  mapWrap.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX; const dy = e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    const rect = mapWrap.getBoundingClientRect();
    panZoom = clampPan({ scale: panZoom.scale, tx: panZoom.tx + dx, ty: panZoom.ty + dy },
      rect.width, rect.height, Math.max(mapSize[0], mapSize[1]), fitScale);
    draw();
  });
  mapWrap.addEventListener("pointerup", () => dragging = false);
  mapWrap.addEventListener("pointerleave", () => dragging = false);

  // zoom
  mapWrap.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = mapWrap.getBoundingClientRect();
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const cx = e.clientX - rect.left; const cy = e.clientY - rect.top;
    panZoom = zoomAtCursor(panZoom, cx, cy, factor, fitScale, rect.width, rect.height, Math.max(mapSize[0], mapSize[1]));
    draw();
  }, { passive: false });

  mapWrap.addEventListener("dblclick", () => { fitView(); draw(); });

  // keyboard
  window.addEventListener("keydown", (e) => {
    if (e.key === "0") { fitView(); draw(); }
    else if (e.key === "ArrowLeft") goToTurn(Math.max(0, turn - 1));
    else if (e.key === "ArrowRight") goToTurn(Math.min(turns.length - 1, turn + 1));
    else if (e.key === " ") { e.preventDefault(); togglePlay(); }
  });

  // graph drag to seek
  let graphDragging = false;
  function graphTurnAt(e: MouseEvent): number {
    const rect = graphCanvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const pad = { l: 40, r: 10 };
    const plotW = rect.width - pad.l - pad.r;
    const maxT = Math.max(1, turns.length - 1);
    return Math.max(0, Math.min(maxT, Math.round(((mx - pad.l) / plotW) * maxT)));
  }
  graphCanvas.addEventListener("pointerdown", (e) => {
    graphDragging = true;
    playing = false; lastPlay = 0;
    const t = graphTurnAt(e as unknown as MouseEvent);
    goToTurn(t, false);
  });
  graphCanvas.addEventListener("pointermove", (e) => {
    if (!graphDragging) return;
    const t = graphTurnAt(e as unknown as MouseEvent);
    goToTurn(t, false);
  });
  graphCanvas.addEventListener("pointerup", () => graphDragging = false);
  graphCanvas.addEventListener("pointerleave", () => graphDragging = false);
}

/* ── Boot ── */

function boot(): void {
  const app = document.getElementById("app")!;
  app.innerHTML = `
    <header>
      <span class="turn-label" id="turn-label"></span>
      <div class="faction-names" id="faction-names"></div>
    </header>
    <div class="bar-row"><span class="bar-label">Score</span><div class="score-bar" id="score-bar"></div></div>
    <div class="bar-row"><span class="bar-label">Towns</span><div class="score-bar" id="settle-bar"></div></div>
    <div class="bar-row"><span class="bar-label">Armies</span><div class="score-bar" id="army-bar"></div></div>
    <div class="timeline-wrap">
      <div class="graph-container">
        <canvas id="graph-canvas"></canvas>
      </div>
    </div>
    <div class="map-wrap" id="map-wrap">
      <canvas id="map-canvas"></canvas>
      <svg id="map-svg"><g id="world-g"></g></svg>
    </div>
    <div class="controls">
      <button id="btn-start" title="First turn (Home)">⏮⏮</button>
      <button id="btn-prev" title="Previous turn (←)">⏮</button>
      <button id="btn-play" title="Play/Pause (Space)" aria-pressed="false">▶</button>
      <button id="btn-next" title="Next turn (→)">⏭</button>
      <button id="btn-end" title="Last turn (End)">⏭⏭</button>
      <select id="speed" title="Playback speed">
        <option value="0.5">0.5×</option>
        <option value="1" selected>1×</option>
        <option value="2">2×</option>
        <option value="4">4×</option>
        <option value="8">8×</option>
      </select>
    </div>
  `;

  canvas = document.getElementById("map-canvas") as HTMLCanvasElement;
  ctx = canvas.getContext("2d")!;
  svg = document.getElementById("map-svg") as unknown as SVGSVGElement;
  worldG = document.getElementById("world-g") as unknown as SVGGElement;
  tooltip = document.getElementById("tooltip") as HTMLDivElement;
  turnLabelEl = document.getElementById("turn-label") as HTMLSpanElement;
  factionNamesEl = document.getElementById("faction-names") as HTMLDivElement;

  playBtn = document.getElementById("btn-play") as HTMLButtonElement;
  speedSel = document.getElementById("speed") as HTMLSelectElement;
  graphCanvas = document.getElementById("graph-canvas") as HTMLCanvasElement;
  graphCtx = graphCanvas.getContext("2d")!;
  scoreBarEl = document.getElementById("score-bar") as HTMLDivElement;
  settleBarEl = document.getElementById("settle-bar") as HTMLDivElement;
  armyBarEl = document.getElementById("army-bar") as HTMLDivElement;
  mapWrap = document.getElementById("map-wrap") as HTMLDivElement;

  document.getElementById("btn-start")!.addEventListener("click", () => goToTurn(0));
  document.getElementById("btn-prev")!.addEventListener("click", () => goToTurn(Math.max(0, turn - 1)));
  playBtn.addEventListener("click", () => togglePlay());
  document.getElementById("btn-next")!.addEventListener("click", () => goToTurn(Math.min(turns.length - 1, turn + 1)));
  document.getElementById("btn-end")!.addEventListener("click", () => goToTurn(turns.length - 1));
  speedSel.addEventListener("change", () => { speed = parseFloat(speedSel.value); });



  // add tooltip div to body
  const tt = document.createElement("div");
  tt.className = "tooltip";
  tt.id = "tooltip";
  document.body.appendChild(tt);
  tooltip = tt;

  setupInteractions();
  window.addEventListener("resize", () => { resizeCanvas(); fitView(); draw(); });
  resizeCanvas();

  // load from URL
  const params = new URLSearchParams(location.search);
  const gamePath = params.get("game");
  if (gamePath) {
    fetch(gamePath).then((r) => r.text()).then((text) => loadRecord(parseJSONL(text))).catch(console.error);
  }
}

function resizeCanvas(): void {
  const rect = mapWrap.getBoundingClientRect();
  const w = Math.round(rect.width);
  const h = Math.round(rect.height);
  canvas.width = w;
  canvas.height = h;
  svg.setAttribute("width", String(w));
  svg.setAttribute("height", String(h));
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
}

boot();
