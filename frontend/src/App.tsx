import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { AlertFeed } from "./components/AlertFeed";
import { SpectrumPanel } from "./components/SpectrumPanel";
import { StatusBar } from "./components/StatusBar";
import { TacticalMap, type RxAltitudeOption } from "./components/TacticalMap";
import { ThreatBanner } from "./components/ThreatBanner";
import { TrackDetail } from "./components/TrackDetail";
import { TrackTable } from "./components/TrackTable";
import { api } from "./lib/api";
import { StreamClient, streamUrl } from "./lib/stream";
import type { CoverageGrid, ReceiverConfig, ScenarioInfo, SignalLibraryEntry } from "./lib/types";
import { initialState, reducer } from "./state/store";

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [library, setLibrary] = useState<SignalLibraryEntry[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [coverageEnabled, setCoverageEnabled] = useState(false);
  const [rxAltitude, setRxAltitude] = useState<RxAltitudeOption>("ownship");
  const [coverage, setCoverage] = useState<CoverageGrid | null>(null);
  const [coverageBusy, setCoverageBusy] = useState(false);
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
  const coverageAvailable = !!selected?.geo && selected.est_eirp_dbm !== null;

  // Coverage map for the selected geolocated emitter; refreshed periodically as the fix tightens.
  const selectedId = selected?.id ?? null;
  useEffect(() => {
    if (!coverageEnabled || !selectedId || !coverageAvailable) {
      setCoverage(null);
      return;
    }
    let cancelled = false;
    const load = () => {
      setCoverageBusy(true);
      const opts =
        rxAltitude === "ownship"
          ? {}
          : { rxAltM: rxAltitude === "agl50" ? 50 : 500, rxAltRef: "agl" as const };
      api
        .trackCoverage(selectedId, { ...opts, n: 90, radiusKm: 60 })
        .then((g) => {
          if (!cancelled) {
            setCoverage(g);
            setError(null);
          }
        })
        .catch((e) => !cancelled && setError(String(e)))
        .finally(() => !cancelled && setCoverageBusy(false));
    };
    load();
    const timer = window.setInterval(load, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [coverageEnabled, selectedId, coverageAvailable, rxAltitude]);

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
            coverage={coverage}
            coverageEnabled={coverageEnabled}
            coverageAvailable={coverageAvailable}
            coverageBusy={coverageBusy}
            onToggleCoverage={() => setCoverageEnabled((v) => !v)}
            rxAltitude={rxAltitude}
            onRxAltitude={setRxAltitude}
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
