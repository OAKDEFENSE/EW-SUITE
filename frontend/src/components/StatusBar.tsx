import type { ConnectionState } from "../lib/stream";
import { formatBearing, formatFreq, formatUtc } from "../lib/format";
import type { EngineState, ScenarioInfo } from "../lib/types";
import { frameRate, highestThreat } from "../state/store";

interface Props {
  connection: ConnectionState;
  engine: EngineState | null;
  frameTimes: number[];
  scenarios: ScenarioInfo[];
  onLoadScenario: (name: string) => void;
}

export function StatusBar({ connection, engine, frameTimes, scenarios, onLoadScenario }: Props) {
  const tracks = engine?.tracks ?? [];
  const confirmed = tracks.filter((t) => t.status === "confirmed").length;
  const tentative = tracks.filter((t) => t.status === "tentative").length;
  const threat = highestThreat(tracks);
  const rate = frameRate(frameTimes);

  return (
    <header className="statusbar">
      <div className="brand">
        <span className="brand-mark">EW</span>
        <span className="brand-name">Console</span>
      </div>
      <div className={`conn conn-${connection}`} title="Data link to EW core">
        <span className="dot" />
        {connection === "open" ? `LIVE ${rate.toFixed(1)} Hz` : connection.toUpperCase()}
      </div>
      <div className="status-item">
        <label>UTC</label>
        <span className="mono">{engine ? formatUtc(engine.time) : "--:--:--Z"}</span>
      </div>
      <div className="status-item">
        <label>Ownship</label>
        <span className="mono">
          {engine
            ? `${engine.ownship.position.lat.toFixed(3)} ${engine.ownship.position.lon.toFixed(3)} HDG ${formatBearing(engine.ownship.heading_deg)} ${(engine.ownship.speed_mps * 1.94384).toFixed(0)} kt`
            : "—"}
        </span>
      </div>
      <div className="status-item">
        <label>Band</label>
        <span className="mono">
          {engine ? `${formatFreq(engine.receiver.start_hz, 2)} – ${formatFreq(engine.receiver.stop_hz, 2)}` : "—"}
        </span>
      </div>
      <div className="status-item">
        <label>Tracks</label>
        <span className="mono">
          {confirmed} <span className="dim">+{tentative}</span>
        </span>
      </div>
      <div className={`status-item threat-pill threat-${threat}`}>
        <label>Threat</label>
        <span>{threat.toUpperCase()}</span>
      </div>
      <div className="status-item scenario">
        <label>Scenario</label>
        <select
          value={engine?.scenario ?? ""}
          onChange={(e) => onLoadScenario(e.target.value)}
          disabled={!scenarios.length}
        >
          {scenarios.map((s) => (
            <option key={s.name} value={s.name} title={s.description}>
              {s.title}
            </option>
          ))}
        </select>
      </div>
    </header>
  );
}
