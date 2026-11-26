import type { Alert, EmitterTrack, EngineState, ThreatLevel } from "../lib/types";
import { THREAT_RANK } from "../lib/types";
import type { ConnectionState } from "../lib/stream";

export interface ConsoleState {
  connection: ConnectionState;
  engine: EngineState | null;
  selectedTrackId: string | null;
  /** Wall-clock arrival times of the last frames, for rate display. */
  frameTimes: number[];
  latestThreat: Alert | null;
}

export type Action =
  | { type: "connection"; state: ConnectionState }
  | { type: "frame"; data: EngineState; newAlerts: Alert[]; receivedAt: number }
  | { type: "select"; trackId: string | null }
  | { type: "dismiss_threat" };

/** How far back to look for an un-dismissed threat when a client first connects. */
export const RECENT_THREAT_S = 120;

export const initialState: ConsoleState = {
  connection: "connecting",
  engine: null,
  selectedTrackId: null,
  frameTimes: [],
  latestThreat: null,
};

export function reducer(state: ConsoleState, action: Action): ConsoleState {
  switch (action.type) {
    case "connection":
      return { ...state, connection: action.state };
    case "frame": {
      const frameTimes = [...state.frameTimes, action.receivedAt].slice(-20);
      let threat = [...action.newAlerts].reverse().find((a) => a.kind === "threat") ?? null;
      if (!threat && state.engine === null) {
        // First frame after (re)connecting: surface a threat raised while we were away.
        threat =
          [...action.data.alerts]
            .reverse()
            .find((a) => a.kind === "threat" && action.data.time - a.time < RECENT_THREAT_S) ?? null;
      }
      const stillExists =
        state.selectedTrackId === null ||
        action.data.tracks.some((t) => t.id === state.selectedTrackId);
      return {
        ...state,
        engine: action.data,
        frameTimes,
        latestThreat: threat ?? state.latestThreat,
        selectedTrackId: stillExists ? state.selectedTrackId : null,
      };
    }
    case "select":
      return { ...state, selectedTrackId: action.trackId };
    case "dismiss_threat":
      return { ...state, latestThreat: null };
    default:
      return state;
  }
}

export function frameRate(frameTimes: number[]): number {
  if (frameTimes.length < 2) return 0;
  const span = frameTimes[frameTimes.length - 1] - frameTimes[0];
  return span > 0 ? ((frameTimes.length - 1) * 1000) / span : 0;
}

/** Threat first (desc), then confirmed before tentative before lost, then frequency. */
export function sortTracks(tracks: EmitterTrack[]): EmitterTrack[] {
  const statusRank = { confirmed: 0, tentative: 1, lost: 2 } as const;
  return [...tracks].sort((a, b) => {
    const t = THREAT_RANK[b.classification.threat] - THREAT_RANK[a.classification.threat];
    if (t !== 0) return t;
    const s = statusRank[a.status] - statusRank[b.status];
    if (s !== 0) return s;
    return a.freq_hz - b.freq_hz;
  });
}

export function highestThreat(tracks: EmitterTrack[]): ThreatLevel {
  let best: ThreatLevel = "none";
  for (const t of tracks) {
    if (t.status === "lost") continue;
    if (THREAT_RANK[t.classification.threat] > THREAT_RANK[best]) best = t.classification.threat;
  }
  return best;
}
