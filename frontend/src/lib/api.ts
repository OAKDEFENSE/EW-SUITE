import type { EngineState, ReceiverConfig, ScenarioInfo, SignalLibraryEntry } from "./types";

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
};
