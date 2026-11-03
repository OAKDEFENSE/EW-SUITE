import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { AlertFeed } from "./components/AlertFeed";
import { SpectrumPanel } from "./components/SpectrumPanel";
import { StatusBar } from "./components/StatusBar";
import { TacticalMap } from "./components/TacticalMap";
import { ThreatBanner } from "./components/ThreatBanner";
import { TrackDetail } from "./components/TrackDetail";
import { TrackTable } from "./components/TrackTable";
import { api } from "./lib/api";
import { StreamClient, streamUrl } from "./lib/stream";
import type { ReceiverConfig, ScenarioInfo, SignalLibraryEntry } from "./lib/types";
import { initialState, reducer } from "./state/store";

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [library, setLibrary] = useState<SignalLibraryEntry[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef<StreamClient | null>(null);

  useEffect(() => {
    const client = new StreamClient(streamUrl(), {
      onState: (s) => dispatch({ type: "connection", state: s }),
      onMessage: (msg) => {
        if (msg.type === "state") {
          dispatch({
            type: "frame",
            data: msg.data,
            newAlerts: msg.new_alerts,
            receivedAt: performance.now(),
          });
        }
      },
    });
    clientRef.current = client;
    client.start();
    return () => client.stop();
  }, []);

  useEffect(() => {
    api.library().then(setLibrary).catch((e) => setError(String(e)));
    api.scenarios().then(setScenarios).catch((e) => setError(String(e)));
  }, []);

  const selectTrack = useCallback((id: string | null) => dispatch({ type: "select", trackId: id }), []);

  const retune = useCallback(async (update: Partial<ReceiverConfig>) => {
    try {
      await api.setReceiver(update);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const loadScenario = useCallback(async (name: string) => {
    try {
      await api.loadScenario(name);
      dispatch({ type: "select", trackId: null });
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const engine = state.engine;
  const selected = useMemo(
    () => engine?.tracks.find((t) => t.id === state.selectedTrackId) ?? null,
    [engine, state.selectedTrackId],
  );
  const selectedEntry = useMemo(
    () => library.find((e) => e.id === selected?.classification.library_id) ?? null,
    [library, selected],
  );

  return (
    <div className="app">
      <StatusBar
        connection={state.connection}
        engine={engine}
        frameTimes={state.frameTimes}
        scenarios={scenarios}
        onLoadScenario={loadScenario}
      />
      {state.latestThreat && (
        <ThreatBanner
          alert={state.latestThreat}
          onSelect={selectTrack}
          onDismiss={() => dispatch({ type: "dismiss_threat" })}
        />
      )}
      {error && (
        <div className="error-bar" role="alert">
          {error}
        </div>
      )}
      <main className="grid">
        <section className="panel panel-spectrum">
          <SpectrumPanel
            spectrum={engine?.spectrum ?? null}
            receiver={engine?.receiver ?? null}
            tracks={engine?.tracks ?? []}
            selectedTrackId={state.selectedTrackId}
            onSelect={selectTrack}
            onRetune={retune}
          />
        </section>
        <section className="panel panel-map">
          <TacticalMap
            ownship={engine?.ownship ?? null}
            tracks={engine?.tracks ?? []}
            selectedTrackId={state.selectedTrackId}
            onSelect={selectTrack}
          />
        </section>
        <section className="panel panel-tracks">
          <TrackTable
            tracks={engine?.tracks ?? []}
            now={engine?.time ?? 0}
            selectedTrackId={state.selectedTrackId}
            onSelect={selectTrack}
          />
        </section>
        <section className="panel panel-side">
          <TrackDetail track={selected} entry={selectedEntry} now={engine?.time ?? 0} ownship={engine?.ownship ?? null} />
          <AlertFeed alerts={engine?.alerts ?? []} onSelect={selectTrack} />
        </section>
      </main>
    </div>
  );
}
