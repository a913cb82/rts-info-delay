export interface TurnState {
  visualTurn: number;
  maxTurn: number;
  playing: boolean;
  speed: number;
}

/**
 * Advance visualTurn by dtMs at current speed.
 * speed is in turns per second.
 * Clamps at maxTurn.
 */
export function advanceTurn(state: TurnState, dtMs: number): TurnState {
  if (!state.playing) return state;
  const delta = (state.speed * dtMs) / 1000;
  let next = state.visualTurn + delta;
  if (next > state.maxTurn) next = state.maxTurn;
  if (next < 0) next = 0;
  return { ...state, visualTurn: next };
}

/**
 * Seek to exact turn, clamped to [0, maxTurn].
 */
export function seekTo(state: TurnState, turn: number): TurnState {
  const clamped = Math.max(0, Math.min(turn, state.maxTurn));
  return { ...state, visualTurn: clamped };
}

/**
 * Helper for timeline: event fraction = turn / maxTurn.
 */
export function eventFraction(turn: number, maxTurn: number): number {
  if (maxTurn === 0) return 0;
  return turn / maxTurn;
}
