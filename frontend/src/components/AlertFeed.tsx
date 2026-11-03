import { formatUtc } from "../lib/format";
import type { Alert } from "../lib/types";

interface Props {
  alerts: Alert[];
  onSelect: (id: string | null) => void;
}

const KIND_LABEL: Record<Alert["kind"], string> = {
  new_track: "NEW",
  threat: "THREAT",
  track_lost: "LOST",
  geo_fix: "FIX",
  system: "SYS",
};

export function AlertFeed({ alerts, onSelect }: Props) {
  const items = [...alerts].reverse();
  return (
    <div className="alert-feed">
      <h2>Alerts</h2>
      <ul>
        {items.map((a) => (
          <li key={a.id} className={`alert alert-${a.kind} sev-${a.severity}`}>
            <button className="link" onClick={() => onSelect(a.track_id)} disabled={!a.track_id}>
              <span className="mono time">{formatUtc(a.time)}</span>
              <span className="kind">{KIND_LABEL[a.kind]}</span>
              <span className="msg">{a.message}</span>
            </button>
          </li>
        ))}
        {!items.length && <li className="empty">No alerts yet</li>}
      </ul>
    </div>
  );
}
