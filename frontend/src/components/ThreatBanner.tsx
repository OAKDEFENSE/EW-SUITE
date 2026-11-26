import { formatUtc } from "../lib/format";
import type { Alert } from "../lib/types";

interface Props {
  alert: Alert;
  onSelect: (id: string | null) => void;
  onDismiss: () => void;
}

export function ThreatBanner({ alert, onSelect, onDismiss }: Props) {
  return (
    <div className={`threat-banner threat-${alert.severity}`} role="alert">
      <button className="link" onClick={() => onSelect(alert.track_id)}>
        <span className="mono">{formatUtc(alert.time)}</span> {alert.message}
      </button>
      <button className="ghost" onClick={onDismiss} aria-label="Dismiss threat alert">
        ✕
      </button>
    </div>
  );
}
