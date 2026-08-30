/**
 * rl_game_min viewer — main entry point.
 *
 * Loads JSONL game record, drives animation loop, renders entities.
 */

import type { Config, TurnRecord, GameRecord, AnimArmy, AnimTown, AnimBattle } from "./types.js";
import { Transform } from "./transform.js";
import { factionColors } from "./color.js";

/* ── State ── */

let config: Config | null = null;
let turns: TurnRecord[] = [];
let factionCount: number = 0;

let visualTurn: number = 0; // fractional turn for animation
let playing: boolean = false;
let speed: number = 1; // 0.5 – 8

const transform = new Transform();

/* ── DOM refs ── */

const canvas = document.getElementById("bg") as HTMLCanvasElement;
const svg = document.getElementById("entities") as SVGSVGElement;
const sidebar = document.getElementById("sidebar") as HTMLDivElement;
const controls = document.getElementById("controls") as HTMLDivElement;
const timeline = document.getElementById("timeline") as HTMLDivElement;
const tooltip = document.getElementById("tooltip") as HTMLDivElement;
const ctx = canvas.getContext("2d")!;

/* ── Load ── */

function loadRecord(records: GameRecord[]): void {
  // TODO: separate config from turns, build animation state
  void records;
}

/* ── Animation loop ── */

function tick(timestamp: number): void {
  // TODO: advance visualTurn, interpolate entities, render
  void timestamp;
  requestAnimationFrame(tick);
}

/* ── Rendering ── */

function renderBackground(): void {
  // TODO: draw map background on canvas
}

function renderTowns(towns: AnimTown[], alpha: number): void {
  // TODO: SVG circles, radius ∝ √pop, capital dot
  void towns;
  void alpha;
}

function renderArmies(armies: AnimArmy[], alpha: number): void {
  // TODO: SVG triangles, stacked if co-located
  void armies;
  void alpha;
}

function renderBattles(battles: AnimBattle[]): void {
  // TODO: crossed lines at battle positions
  void battles;
}

function renderSidebar(): void {
  // TODO: per-faction town/army counts, total score, event log
}

function renderTimeline(): void {
  // TODO: event marker dots, click to seek
}

/* ── Controls ── */

function initControls(): void {
  // TODO: turn slider, play/pause, speed selector, fit-to-view
}

/* ── Tooltips ── */

function initTooltips(): void {
  // TODO: hover entities to show details
}

/* ── File loading ── */

function initFileLoader(): void {
  // TODO: file picker or ?game= URL param, JSONL streaming
}

/* ── Entry point ── */

function main(): void {
  initControls();
  initTooltips();
  initFileLoader();
  renderBackground();
  requestAnimationFrame(tick);
}

main();
