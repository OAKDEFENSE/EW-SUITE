import type {
  AltitudeRef,
  CoverageGrid,
  EngineState,
  GridBounds,
  ReceiverConfig,
  RelayGrid,
  ScenarioInfo,
  SignalLibraryEntry,
  TerrainGrid,
  TerrainInfo,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  state: () => request<EngineState>("/api/state"),
  library: () => request<SignalLibraryEntry[]>("/api/library"),
  scenarios: () => request<ScenarioInfo[]>("/api/scenarios"),
  loadScenario: (name: string) =>
    request<EngineState>(`/api/scenarios/${encodeURIComponent(name)}/load`, { method: "POST" }),
  setReceiver: (update: Partial<ReceiverConfig>) =>
    request<ReceiverConfig>("/api/receiver", { method: "PUT", body: JSON.stringify(update) }),
  terrain: () => request<TerrainInfo>("/api/terrain"),
  relayGrid: (linkId: string, opts: { relayAltM?: number; n?: number; radiusKm?: number } = {}) => {
    const q = new URLSearchParams();
    if (opts.relayAltM !== undefined) q.set("relay_alt_m", String(opts.relayAltM));
    if (opts.n) q.set("n", String(opts.n));
    if (opts.radiusKm) q.set("radius_km", String(opts.radiusKm));
    const qs = q.toString();
    return request<RelayGrid>(`/api/links/${encodeURIComponent(linkId)}/relay-grid${qs ? `?${qs}` : ""}`);
  },
  terrainGrid: (b: GridBounds, n = 120) =>
    request<TerrainGrid>(
      `/api/terrain/grid?south=${b.south}&west=${b.west}&north=${b.north}&east=${b.east}&n=${n}`,
    ),
  trackCoverage: (
    trackId: string,
    opts: { rxAltM?: number; rxAltRef?: AltitudeRef; radiusKm?: number; n?: number } = {},
  ) => {
    const q = new URLSearchParams();
    if (opts.rxAltM !== undefined) q.set("rx_alt_m", String(opts.rxAltM));
    if (opts.rxAltRef) q.set("rx_alt_ref", opts.rxAltRef);
    if (opts.radiusKm) q.set("radius_km", String(opts.radiusKm));
    if (opts.n) q.set("n", String(opts.n));
    const qs = q.toString();
    return request<CoverageGrid>(
      `/api/tracks/${encodeURIComponent(trackId)}/coverage${qs ? `?${qs}` : ""}`,
    );
  },
};
