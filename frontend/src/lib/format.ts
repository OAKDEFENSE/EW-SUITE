export function formatFreq(hz: number, digits?: number): string {
  if (!Number.isFinite(hz)) return "—";
  if (hz >= 1e9) return `${(hz / 1e9).toFixed(digits ?? 3)} GHz`;
  if (hz >= 1e6) return `${(hz / 1e6).toFixed(digits ?? 2)} MHz`;
  if (hz >= 1e3) return `${(hz / 1e3).toFixed(digits ?? 1)} kHz`;
  return `${hz.toFixed(0)} Hz`;
}

export function formatBandwidth(hz: number): string {
  if (hz >= 1e6) return `${(hz / 1e6).toFixed(1)} MHz`;
  return `${(hz / 1e3).toFixed(0)} kHz`;
}

export function formatBearing(deg: number | null | undefined): string {
  if (deg === null || deg === undefined || !Number.isFinite(deg)) return "—";
  return `${Math.round(((deg % 360) + 360) % 360)
    .toString()
    .padStart(3, "0")}°`;
}

export function formatDbm(v: number): string {
  return `${v.toFixed(0)} dBm`;
}

export function formatMicros(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (v >= 100) return v.toFixed(0);
  if (v >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

export function formatUtc(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  const hh = d.getUTCHours().toString().padStart(2, "0");
  const mm = d.getUTCMinutes().toString().padStart(2, "0");
  const ss = d.getUTCSeconds().toString().padStart(2, "0");
  return `${hh}:${mm}:${ss}Z`;
}

export function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, seconds).toFixed(0)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}s`;
  return `${Math.floor(seconds / 3600)}h${Math.floor((seconds % 3600) / 60)
    .toString()
    .padStart(2, "0")}m`;
}

export function formatLatLon(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}°${ns} ${Math.abs(lon).toFixed(4)}°${ew}`;
}

export function formatDistance(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  return `${m.toFixed(0)} m`;
}
