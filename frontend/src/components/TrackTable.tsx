import { formatAge, formatBandwidth, formatBearing, formatFreq, formatMicros } from "../lib/format";
import type { EmitterTrack } from "../lib/types";
import { sortTracks } from "../state/store";

interface Props {
  tracks: EmitterTrack[];
  now: number;
  selectedTrackId: string | null;
  onSelect: (id: string | null) => void;
}

export function TrackTable({ tracks, now, selectedTrackId, onSelect }: Props) {
  const rows = sortTracks(tracks);
  return (
    <div className="track-table">
      <h2>
        Emitter tracks <span className="dim">({rows.length})</span>
      </h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Freq</th>
              <th>BW</th>
              <th>Pwr</th>
              <th>Brg</th>
              <th>PRI µs</th>
              <th>PW µs</th>
              <th>Identification</th>
              <th>Threat</th>
              <th>Conf</th>
              <th>Fix</th>
              <th>Age</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr
                key={t.id}
                className={[
                  `status-${t.status}`,
                  `threat-row-${t.classification.threat}`,
                  t.id === selectedTrackId ? "selected" : "",
                ].join(" ")}
                onClick={() => onSelect(t.id === selectedTrackId ? null : t.id)}
              >
                <td className="mono">{t.id}</td>
                <td>
                  <span className={`badge badge-${t.status}`}>{t.status}</span>
                </td>
                <td className="mono">{formatFreq(t.freq_hz)}</td>
                <td className="mono">{formatBandwidth(t.bandwidth_hz)}</td>
                <td className="mono">{t.power_dbm.toFixed(0)}</td>
                <td className="mono">{formatBearing(t.bearing_deg)}</td>
                <td className="mono">{formatMicros(t.pulse?.pri_us)}</td>
                <td className="mono">{formatMicros(t.pulse?.pw_us)}</td>
                <td>{t.classification.name}</td>
                <td>
                  <span className={`badge threat-${t.classification.threat}`}>
                    {t.classification.threat}
                  </span>
                </td>
                <td className="mono">{(t.classification.confidence * 100).toFixed(0)}%</td>
                <td className="mono">{t.geo ? `±${(t.geo.error_radius_m / 1000).toFixed(1)}km` : "—"}</td>
                <td className="mono">{formatAge(now - t.first_seen)}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={13} className="empty">
                  No emitters detected
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
