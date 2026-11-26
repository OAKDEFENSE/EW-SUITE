import { formatBandwidth, formatDistance, formatFreq } from "../lib/format";
import type { BlueNetwork, LinkStatus } from "../lib/types";

interface Props {
  links: LinkStatus[];
  blue: BlueNetwork | null;
  relayLinkId: string | null;
  relayBusy: boolean;
  onToggleRelay: (linkId: string) => void;
  onSelectTrack: (id: string | null) => void;
}

const MARGIN_BAR_MIN = -20;
const MARGIN_BAR_MAX = 30;

function barWidth(margin: number): number {
  const t = (Math.min(MARGIN_BAR_MAX, Math.max(MARGIN_BAR_MIN, margin)) - MARGIN_BAR_MIN) /
    (MARGIN_BAR_MAX - MARGIN_BAR_MIN);
  return Math.round(t * 100);
}

export function LinksPanel({ links, blue, relayLinkId, relayBusy, onToggleRelay, onSelectTrack }: Props) {
  const nodeName = (id: string) => blue?.nodes.find((n) => n.id === id)?.name ?? id;
  const linkSpec = (id: string) => blue?.links.find((l) => l.id === id);
  const failed = links.filter((l) => l.state === "failed").length;
  const marginal = links.filter((l) => l.state === "marginal").length;
  return (
    <div className="links-panel">
      <h2>
        Own links <span className="dim">({links.length})</span>
        {failed > 0 && <span className="badge link-failed">{failed} failed</span>}
        {marginal > 0 && <span className="badge link-marginal">{marginal} marginal</span>}
      </h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Link</th>
              <th>Path</th>
              <th>Freq / BW</th>
              <th>Range</th>
              <th>LOS</th>
              <th title="Signal / noise / in-band interference, dBm">S / N / I</th>
              <th>SINR</th>
              <th>Margin</th>
              <th>State</th>
              <th>Interferers</th>
              <th>Relay</th>
            </tr>
          </thead>
          <tbody>
            {links.map((l) => {
              const spec = linkSpec(l.link_id);
              return (
                <tr key={l.link_id} className={`link-row link-${l.state}`}>
                  <td title={spec ? `${spec.tx_power_dbm} dBm, req SNR ${spec.required_snr_db} dB` : ""}>
                    {l.name}
                  </td>
                  <td className="dim mono" title={`${nodeName(l.tx)} → ${nodeName(l.rx)}`}>
                    {l.tx} → {l.rx}
                  </td>
                  <td className="mono">
                    {spec ? formatFreq(spec.freq_hz) : "—"}
                    {spec && <span className="dim"> / {formatBandwidth(spec.bandwidth_hz)}</span>}
                  </td>
                  <td className="mono">{formatDistance(l.distance_m)}</td>
                  <td>{l.los ? "clear" : <span className="warn">obstructed</span>}</td>
                  <td className="mono">
                    {l.signal_dbm.toFixed(0)} / {l.noise_dbm.toFixed(0)} /{" "}
                    {l.jam_dbm === null ? "—" : l.jam_dbm.toFixed(0)}
                  </td>
                  <td className="mono">{l.sinr_db.toFixed(1)}</td>
                  <td>
                    <div className="margin-bar" title={`${l.margin_db.toFixed(1)} dB`}>
                      <div className="margin-zero" />
                      <div className={`margin-fill margin-${l.state}`} style={{ width: `${barWidth(l.margin_db)}%` }} />
                      <span className="mono">{l.margin_db >= 0 ? "+" : ""}{l.margin_db.toFixed(0)}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`badge link-${l.state}`}>{l.state}</span>
                  </td>
                  <td>
                    {l.interferers.map((i) => (
                      <button key={i.track_id} className="link chip" onClick={() => onSelectTrack(i.track_id)} title={`${i.name} · ${formatFreq(i.freq_hz)} · ${i.jam_dbm.toFixed(0)} dBm in band`}>
                        {i.track_id}
                      </button>
                    ))}
                    {l.unlocated_interferers.map((id) => (
                      <button key={id} className="link chip chip-unlocated" onClick={() => onSelectTrack(id)} title="In-band emitter detected, not yet geolocated">
                        {id}?
                      </button>
                    ))}
                    {!l.interferers.length && !l.unlocated_interferers.length && <span className="dim">—</span>}
                  </td>
                  <td>
                    <button
                      type="button"
                      className={relayLinkId === l.link_id ? "active" : ""}
                      onClick={() => onToggleRelay(l.link_id)}
                      title="Show where a relay would give the best two-hop margin"
                    >
                      {relayBusy && relayLinkId === l.link_id ? "…" : "Sites"}
                    </button>
                  </td>
                </tr>
              );
            })}
            {!links.length && (
              <tr>
                <td colSpan={11} className="empty">
                  No own links configured
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
