/**
 * rl_game_min viewer — main entry point.
 *
 * Loads JSONL game record, drives animation loop, renders entities.
 */

import type { Config, TurnRecord, GameRecord, AnimArmy, AnimTown, AnimBattle } from "./types.js";
import { Transform } from "./transform.js";
import { factionColor } from "./color.js";
import { parseJSONL, separateConfigTurns } from "./loader.js";
import { buildArmyAnim, buildTownAnim, lerp, easeInOut } from "./animation.js";
import { townRadius } from "./render-entities.js";
import { advanceTurn, seekTo } from "./controls.js";
import type { TurnState } from "./controls.js";

/* ── State ── */

let config: Config | null = null;
let turns: TurnRecord[] = [];
let factionCount: number = 0;

let visualTurn: number = 0; // fractional turn for animation
let playing: boolean = false;
let speed: number = 1; // 0.5 – 8
let lastTimestamp: number | null = null;

const transform = new Transform();

/* ── DOM refs ── */

const canvas = document.getElementById("bg") as HTMLCanvasElement | null;
const svg = document.getElementById("entities") as unknown as SVGSVGElement | null;
const sidebarEl = document.getElementById("sidebar") as HTMLDivElement | null;
const controlsEl = document.getElementById("controls") as HTMLDivElement | null;
const timelineEl = document.getElementById("timeline") as HTMLDivElement | null;
const tooltipEl = document.getElementById("tooltip") as HTMLDivElement | null;
const ctx = canvas?.getContext("2d") ?? null;

/* ── Load ── */

function loadRecord(records: GameRecord[]): void {
  const separated = separateConfigTurns(records);
  config = separated.config;
  turns = separated.turns;
  if (config) {
    const factions = new Set<number>();
    for (const t of turns) {
      for (const town of t.world.towns) factions.add(town.faction);
      for (const army of t.world.armies) factions.add(army.faction);
    }
    factionCount = factions.size || 3;
    if (canvas && config.map) {
      transform.fitToView(config.map[0], config.map[1], canvas.width, canvas.height);
    }
  }
  visualTurn = 0;
  renderSidebar();
  renderTimeline();
  renderBackground();
}

/* ── Animation helpers ── */

function getAnimState(alpha: number): {
  armies: AnimArmy[];
  towns: AnimTown[];
  battles: AnimBattle[];
} {
  if (turns.length === 0) return { armies: [], towns: [], battles: [] };
  const idx = Math.floor(visualTurn);
  const t = easeInOut(alpha);
  void t;
  const cur = turns[Math.min(idx, turns.length - 1)];
  const nxt = turns[Math.min(idx + 1, turns.length - 1)];
  if (!cur || !nxt) return { armies: [], towns: [], battles: [] };
  // if at last turn, no interpolation
  if (idx >= turns.length - 1) {
    return {
      armies: buildArmyAnim(cur.world.armies, cur.world.armies, cur.events),
      towns: buildTownAnim(cur.world.towns, cur.world.towns, cur.events),
      battles: cur.events.filter((e) => e.kind === "battle") as unknown as AnimBattle[],
    };
  }
  const armies = buildArmyAnim(cur.world.armies, nxt.world.armies, nxt.events);
  const towns = buildTownAnim(cur.world.towns, nxt.world.towns, nxt.events);
  const battles: AnimBattle[] = nxt.events
    .filter((e) => e.kind === "battle")
    .map((e) => {
      const b = e as unknown as AnimBattle;
      return b;
    });
  return { armies, towns, battles };
}

function currentAlpha(): number {
  return visualTurn - Math.floor(visualTurn);
}

/* ── Animation loop ── */

function tick(timestamp: number): void {
  if (lastTimestamp === null) lastTimestamp = timestamp;
  const dt = timestamp - lastTimestamp;
  lastTimestamp = timestamp;

  if (playing && turns.length > 0) {
    const state: TurnState = {
      visualTurn,
      maxTurn: Math.max(0, turns.length - 1),
      playing,
      speed,
    };
    const next = advanceTurn(state, dt);
    visualTurn = next.visualTurn;
    if (visualTurn >= turns.length - 1) playing = false;
  }

  const alpha = currentAlpha();
  const { armies, towns, battles } = getAnimState(alpha);
  // interpolate for rendering (lerp used implicitly via anim state)
  void lerp;
  renderBackground();
  renderTowns(towns, alpha);
  renderArmies(armies, alpha);
  renderBattles(battles);
  renderSidebar();

  requestAnimationFrame(tick);
}

/* ── Rendering ── */

function renderBackground(): void {
  if (!ctx || !canvas || !config) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // grid
  ctx.strokeStyle = "#222";
  ctx.lineWidth = 1;
  const step = 100 * transform.scale;
  if (step > 20) {
    const [ox, oy] = [transform.offsetX % step, transform.offsetY % step];
    for (let x = -ox; x < canvas.width; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
    }
    for (let y = -oy; y < canvas.height; y += step) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.stroke();
    }
  }
}

function renderTowns(towns: AnimTown[], alpha: number): void {
  if (!svg || !config) return;
  // clear previous towns
  svg.querySelectorAll(".town").forEach((el) => el.remove());
  for (const t of towns) {
    const x = lerp(t.fromX, t.toX, alpha);
    const y = lerp(t.fromY, t.toY, alpha);
    const pop = lerp(t.fromPop, t.toPop, alpha);
    const [sx, sy] = transform.worldToScreen(x, y);
    const r = townRadius(pop, config.population_cap);
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "town");
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", String(sx));
    circle.setAttribute("cy", String(sy));
    circle.setAttribute("r", String(r));
    circle.setAttribute("fill", factionColor(t.faction, factionCount));
    circle.setAttribute("stroke", "#fff");
    circle.setAttribute("stroke-width", "1");
    if (t.dies) circle.setAttribute("opacity", String(1 - alpha));
    if (t.spawns) circle.setAttribute("opacity", String(alpha));
    g.appendChild(circle);
    if (t.isCapital) {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", String(sx));
      dot.setAttribute("cy", String(sy));
      dot.setAttribute("r", "2");
      dot.setAttribute("fill", "white");
      g.appendChild(dot);
    }
    // tooltip
    g.addEventListener("mouseenter", () => {
      if (!tooltipEl) return;
      tooltipEl.textContent = `Pop: ${Math.round(pop)}${t.isCapital ? " ★" : ""}`;
      tooltipEl.style.display = "block";
    });
    g.addEventListener("mouseleave", () => {
      if (!tooltipEl) return;
      tooltipEl.style.display = "none";
    });
    svg.appendChild(g);
  }
}

function renderArmies(armies: AnimArmy[], alpha: number): void {
  if (!svg) return;
  svg.querySelectorAll(".army").forEach((el) => el.remove());
  // group by position for stacking
  const grouped = new Map<string, AnimArmy[]>();
  for (const a of armies) {
    const x = lerp(a.fromX, a.toX, alpha);
    const y = lerp(a.fromY, a.toY, alpha);
    const [sx, sy] = transform.worldToScreen(x, y);
    const key = `${sx.toFixed(1)},${sy.toFixed(1)}`;
    const g = grouped.get(key) ?? [];
    g.push(a);
    grouped.set(key, g);
  }
  for (const [, stack] of grouped) {
    const rep = stack[0]!;
    const x = lerp(rep.fromX, rep.toX, alpha);
    const y = lerp(rep.fromY, rep.toY, alpha);
    const [sx, sy] = transform.worldToScreen(x, y);
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "army");
    const size = 6;
    const points = `${sx},${sy - size} ${sx - size},${sy + size} ${sx + size},${sy + size}`;
    const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    poly.setAttribute("points", points);
    poly.setAttribute("fill", factionColor(rep.faction, factionCount));
    poly.setAttribute("stroke", "#fff");
    poly.setAttribute("stroke-width", "1");
    if (rep.dies) poly.setAttribute("opacity", String(1 - alpha));
    if (rep.spawns) poly.setAttribute("opacity", String(alpha));
    g.appendChild(poly);
    if (stack.length > 1) {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", String(sx + 8));
      text.setAttribute("y", String(sy - 8));
      text.setAttribute("fill", "white");
      text.setAttribute("font-size", "10");
      text.textContent = `×${stack.length}`;
      g.appendChild(text);
    }
    g.addEventListener("mouseenter", () => {
      if (!tooltipEl) return;
      tooltipEl.textContent = `Faction ${rep.faction} ×${stack.length}`;
      tooltipEl.style.display = "block";
    });
    g.addEventListener("mouseleave", () => {
      if (!tooltipEl) return;
      tooltipEl.style.display = "none";
    });
    svg.appendChild(g);
  }
}

function renderBattles(battles: AnimBattle[]): void {
  if (!svg) return;
  svg.querySelectorAll(".battle").forEach((el) => el.remove());
  for (const b of battles) {
    const [sx, sy] = transform.worldToScreen(b.x, b.y);
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "battle");
    const line1 = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line1.setAttribute("x1", String(sx - 6));
    line1.setAttribute("y1", String(sy - 6));
    line1.setAttribute("x2", String(sx + 6));
    line1.setAttribute("y2", String(sy + 6));
    line1.setAttribute("stroke", "red");
    line1.setAttribute("stroke-width", "2");
    const line2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line2.setAttribute("x1", String(sx + 6));
    line2.setAttribute("y1", String(sy - 6));
    line2.setAttribute("x2", String(sx - 6));
    line2.setAttribute("y2", String(sy + 6));
    line2.setAttribute("stroke", "red");
    line2.setAttribute("stroke-width", "2");
    g.appendChild(line1);
    g.appendChild(line2);
    g.addEventListener("mouseenter", () => {
      if (!tooltipEl) return;
      tooltipEl.textContent = `${b.combatants.length} combatants, ${b.killed.length} killed`;
      tooltipEl.style.display = "block";
    });
    g.addEventListener("mouseleave", () => {
      if (!tooltipEl) return;
      tooltipEl.style.display = "none";
    });
    svg.appendChild(g);
  }
}

function renderSidebar(): void {
  if (!sidebarEl || turns.length === 0) return;
  const idx = Math.min(Math.floor(visualTurn), turns.length - 1);
  const world = turns[idx]?.world;
  if (!world) return;
  const factions = new Set<number>([
    ...world.towns.map((t) => t.faction),
    ...world.armies.map((a) => a.faction),
  ]);
  let html = "";
  for (const f of factions) {
    const fTowns = world.towns.filter((t) => t.faction === f);
    const fArmies = world.armies.filter((a) => a.faction === f);
    const score = fTowns.reduce((s, t) => s + t.population, 0) + fArmies.length * (config?.army_cost ?? 1000);
    html += `<div>Faction ${f}: towns ${fTowns.length} armies ${fArmies.length} score ${score}</div>`;
  }
  // event log
  const cur = turns[idx];
  if (cur) {
    html += `<div class="events">`;
    for (const e of cur.events) {
      html += `<div>${e.kind} at ${JSON.stringify(e)}</div>`;
    }
    html += `</div>`;
  }
  sidebarEl.innerHTML = html;
}

function renderTimeline(): void {
  if (!timelineEl || turns.length === 0) return;
  timelineEl.innerHTML = "";
  const maxTurn = turns.length - 1;
  for (let i = 0; i < turns.length; i++) {
    const turn = turns[i]!;
    if (turn.events.length === 0) continue;
    for (const e of turn.events) {
      if (e.kind === "battle" || e.kind === "army_death" || e.kind === "army_spawn" || e.kind === "town_spawn") {
        const dot = document.createElement("div");
        dot.className = "event-dot";
        dot.style.left = `${(i / Math.max(1, maxTurn)) * 100}%`;
        dot.title = `${e.kind} turn ${i}`;
        dot.addEventListener("click", () => {
          const state: TurnState = { visualTurn, maxTurn, playing, speed };
          const next = seekTo(state, i);
          visualTurn = next.visualTurn;
        });
        timelineEl.appendChild(dot);
        break;
      }
    }
  }
  // slider
  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(maxTurn);
  slider.step = "0.01";
  slider.value = String(visualTurn);
  slider.addEventListener("input", () => {
    const state: TurnState = { visualTurn, maxTurn, playing, speed };
    const next = seekTo(state, parseFloat(slider.value));
    visualTurn = next.visualTurn;
  });
  timelineEl.appendChild(slider);
}

/* ── Controls ── */

function initControls(): void {
  if (!controlsEl) return;
  controlsEl.innerHTML = "";

  const playBtn = document.createElement("button");
  playBtn.textContent = playing ? "Pause" : "Play";
  playBtn.addEventListener("click", () => {
    playing = !playing;
    playBtn.textContent = playing ? "Pause" : "Play";
  });
  controlsEl.appendChild(playBtn);

  const speedSel = document.createElement("select");
  for (const s of [0.5, 1, 2, 4, 8]) {
    const opt = document.createElement("option");
    opt.value = String(s);
    opt.textContent = `${s}×`;
    if (s === speed) opt.selected = true;
    speedSel.appendChild(opt);
  }
  speedSel.addEventListener("change", () => {
    speed = parseFloat(speedSel.value);
  });
  controlsEl.appendChild(speedSel);

  const fitBtn = document.createElement("button");
  fitBtn.textContent = "Fit to view";
  fitBtn.addEventListener("click", () => {
    if (config && canvas) {
      transform.fitToView(config.map[0], config.map[1], canvas.width, canvas.height);
      renderBackground();
    }
  });
  controlsEl.appendChild(fitBtn);

  // pan/zoom on canvas
  if (canvas) {
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    canvas.addEventListener("pointerdown", (e) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
    });
    window.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      transform.pan(dx, dy);
      lastX = e.clientX;
      lastY = e.clientY;
      renderBackground();
    });
    window.addEventListener("pointerup", () => {
      dragging = false;
    });
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.2 : 0.8;
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      transform.zoom(factor, sx, sy);
      renderBackground();
    });
    canvas.addEventListener("dblclick", () => {
      if (config) transform.fitToView(config.map[0], config.map[1], canvas.width, canvas.height);
    });
  }
}

/* ── Tooltips ── */

function initTooltips(): void {
  if (!tooltipEl) return;
  tooltipEl.style.position = "absolute";
  tooltipEl.style.display = "none";
  tooltipEl.style.background = "rgba(0,0,0,0.7)";
  tooltipEl.style.color = "white";
  tooltipEl.style.padding = "4px";
  window.addEventListener("mousemove", (e) => {
    if (tooltipEl.style.display !== "none") {
      tooltipEl.style.left = `${e.clientX + 10}px`;
      tooltipEl.style.top = `${e.clientY + 10}px`;
    }
  });
}

/* ── File loading ── */

function initFileLoader(): void {
  const url = new URL(window.location.href);
  const gamePath = url.searchParams.get("game");
  if (gamePath) {
    fetch(gamePath)
      .then((r) => r.text())
      .then((text) => {
        const records = parseJSONL(text);
        loadRecord(records);
      })
      .catch((err) => {
        console.error("Failed to load game", err);
      });
    return;
  }

  // file picker
  const picker = document.createElement("input");
  picker.type = "file";
  picker.accept = ".jsonl";
  picker.style.position = "absolute";
  picker.style.top = "10px";
  picker.style.left = "10px";
  document.body.appendChild(picker);
  picker.addEventListener("change", () => {
    const file = picker.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      const records = parseJSONL(text);
      loadRecord(records);
    };
    reader.readAsText(file);
  });
}

/* ── Entry point ── */

function main(): void {
  initControls();
  initTooltips();
  initFileLoader();
  renderBackground();
  // guard for test environment where requestAnimationFrame may not be needed
  if (typeof requestAnimationFrame !== "undefined") {
    requestAnimationFrame(tick);
  }
}

main();

// ensure used
void factionCount;
