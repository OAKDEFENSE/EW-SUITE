import { describe, expect, it } from "vitest";
import type { Alert, EmitterTrack, EngineState } from "../lib/types";
import { frameRate, highestThreat, initialState, reducer, sortTracks } from "./store";

function track(id: string, threat: EmitterTrack["classification"]["threat"], status: EmitterTrack["status"] = "confirmed", freq = 1e9): EmitterTrack {
  return {
    id,
    status,
    freq_hz: freq,
    bandwidth_hz: 1e6,
    power_dbm: -60,
    bearing_deg: 90,
    pulse: null,
    classification: { library_id: null, name: "x", emitter_class: "unknown", threat, confidence: 0.5 },
    hits: 5,
    first_seen: 0,
    last_seen: 1,
    geo: null,
  };
}

function engine(tracks: EmitterTrack[]): EngineState {
  return {
    time: 1,
    scenario: "s",
    receiver: { start_hz: 0, stop_hz: 1, n_bins: 1, detection_threshold_db: 10 },
    ownship: { position: { lat: 0, lon: 0, alt_m: 0 }, heading_deg: 0, speed_mps: 0 },
    spectrum: { time: 1, start_hz: 0, stop_hz: 1, power_dbm: [-100], noise_floor_dbm: -100 },
    tracks,
    alerts: [],
  };
}

describe("reducer", () => {
  it("stores frames and keeps a bounded frame-time window", () => {
    let s = initialState;
    for (let i = 0; i < 30; i++) {
      s = reducer(s, { type: "frame", data: engine([]), newAlerts: [], receivedAt: i * 200 });
    }
    expect(s.engine).not.toBeNull();
    expect(s.frameTimes.length).toBe(20);
    expect(frameRate(s.frameTimes)).toBeCloseTo(5, 1);
  });

  it("clears the selection when the track disappears", () => {
    let s = reducer(initialState, { type: "frame", data: engine([track("E-001", "low")]), newAlerts: [], receivedAt: 0 });
    s = reducer(s, { type: "select", trackId: "E-001" });
    expect(s.selectedTrackId).toBe("E-001");
    s = reducer(s, { type: "frame", data: engine([]), newAlerts: [], receivedAt: 200 });
    expect(s.selectedTrackId).toBeNull();
  });

  it("latches the most recent threat alert until dismissed", () => {
    const alert: Alert = { id: 1, time: 0, severity: "high", kind: "threat", track_id: "E-001", message: "THREAT" };
    let s = reducer(initialState, { type: "frame", data: engine([]), newAlerts: [alert], receivedAt: 0 });
    expect(s.latestThreat?.id).toBe(1);
    s = reducer(s, { type: "frame", data: engine([]), newAlerts: [], receivedAt: 200 });
    expect(s.latestThreat?.id).toBe(1);
    s = reducer(s, { type: "dismiss_threat" });
    expect(s.latestThreat).toBeNull();
  });
});

describe("reducer threat seeding", () => {
  it("surfaces a recent threat from history on the first frame only", () => {
    const old: Alert = { id: 1, time: 0, severity: "high", kind: "threat", track_id: "E-001", message: "old" };
    const recent: Alert = { id: 2, time: 900, severity: "high", kind: "threat", track_id: "E-002", message: "recent" };
    const data = { ...engine([]), time: 1000, alerts: [old, recent] };
    let s = reducer(initialState, { type: "frame", data, newAlerts: [], receivedAt: 0 });
    expect(s.latestThreat?.id).toBe(2);
    s = reducer(s, { type: "dismiss_threat" });
    s = reducer(s, { type: "frame", data, newAlerts: [], receivedAt: 200 });
    expect(s.latestThreat).toBeNull();
  });
  it("does not seed from stale history", () => {
    const old: Alert = { id: 1, time: 0, severity: "high", kind: "threat", track_id: "E-001", message: "old" };
    const data = { ...engine([]), time: 1000, alerts: [old] };
    const s = reducer(initialState, { type: "frame", data, newAlerts: [], receivedAt: 0 });
    expect(s.latestThreat).toBeNull();
  });
});

describe("track helpers", () => {
  it("sorts by threat, then status, then frequency", () => {
    const sorted = sortTracks([
      track("a", "low", "confirmed", 3e9),
      track("b", "high", "lost", 9e9),
      track("c", "low", "confirmed", 1e9),
      track("d", "medium", "tentative", 2e9),
    ]).map((t) => t.id);
    expect(sorted).toEqual(["b", "d", "c", "a"]);
  });
  it("ignores lost tracks for the highest threat", () => {
    expect(highestThreat([track("a", "high", "lost"), track("b", "medium")])).toBe("medium");
  });
});
