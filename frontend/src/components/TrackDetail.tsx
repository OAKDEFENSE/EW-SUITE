import { distanceM } from "../lib/geo";
import {
  formatAge,
  formatBandwidth,
  formatBearing,
  formatDbm,
  formatDistance,
  formatFreq,
  formatLatLon,
  formatMicros,
  formatUtc,
} from "../lib/format";
import type { EmitterTrack, Ownship, SignalLibraryEntry } from "../lib/types";

interface Props {
  track: EmitterTrack | null;
  entry: SignalLibraryEntry | null;
  now: number;
  ownship: Ownship | null;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="kv">
      <span className="k">{label}</span>
      <span className="v">{children}</span>
    </div>
  );
}

export function TrackDetail({ track, entry, now, ownship }: Props) {
  if (!track) {
    return (
      <div className="track-detail">
        <h2>Track detail</h2>
        <p className="empty">Select a track in the table, spectrum or map.</p>
      </div>
    );
  }
  const c = track.classification;
  const range =
    track.geo && ownship
      ? distanceM(
          ownship.position.lat,
          ownship.position.lon,
          track.geo.position.lat,
          track.geo.position.lon,
        )
      : null;
  return (
    <div className="track-detail">
      <h2>
        <span className="mono">{track.id}</span>
        <span className={`badge threat-${c.threat}`}>{c.threat}</span>
        <span className={`badge badge-${track.status}`}>{track.status}</span>
      </h2>
      <div className="ident">{c.name}</div>
      <div className="kv-grid">
        <Row label="Frequency">{formatFreq(track.freq_hz, 4)}</Row>
        <Row label="Bandwidth">{formatBandwidth(track.bandwidth_hz)}</Row>
        <Row label="Power">{formatDbm(track.power_dbm)}</Row>
        <Row label="Bearing">{formatBearing(track.bearing_deg)}</Row>
        <Row label="PRI">{track.pulse ? `${formatMicros(track.pulse.pri_us)} µs` : "CW / none"}</Row>
        <Row label="PW">{track.pulse ? `${formatMicros(track.pulse.pw_us)} µs` : "—"}</Row>
        <Row label="PRF">
          {track.pulse ? `${(1e6 / track.pulse.pri_us).toFixed(0)} Hz` : "—"}
        </Row>
        <Row label="Confidence">{(c.confidence * 100).toFixed(0)}%</Row>
        <Row label="Library">{c.library_id ?? "—"}</Row>
        <Row label="Hits">{track.hits}</Row>
        <Row label="First seen">{formatUtc(track.first_seen)}</Row>
        <Row label="Last seen">
          {formatUtc(track.last_seen)} <span className="dim">({formatAge(now - track.last_seen)} ago)</span>
        </Row>
      </div>
      <h3>Geolocation</h3>
      {track.geo ? (
        <div className="kv-grid">
          <Row label="Position">{formatLatLon(track.geo.position.lat, track.geo.position.lon)}</Row>
          <Row label="Error radius">{formatDistance(track.geo.error_radius_m)}</Row>
          <Row label="Bearings used">{track.geo.n_bearings}</Row>
          {range !== null && <Row label="Range">{formatDistance(range)}</Row>}
        </div>
      ) : (
        <p className="dim">
          No fix yet. Bearing-only geolocation needs ownship baseline; keep manoeuvring.
        </p>
      )}
      {entry && (
        <>
          <h3>Library notes</h3>
          <p className="notes">{entry.notes}</p>
          <p className="dim mono small">
            {formatFreq(entry.freq_min_hz, 2)} – {formatFreq(entry.freq_max_hz, 2)}
            {entry.pulsed &&
              ` · PRI ${entry.pri_min_us}–${entry.pri_max_us} µs · PW ${entry.pw_min_us}–${entry.pw_max_us} µs`}
          </p>
        </>
      )}
    </div>
  );
}
