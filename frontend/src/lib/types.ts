// Mirrors backend/ew_core/models.py. Keep the two in step.

export type ThreatLevel = "none" | "low" | "medium" | "high" | "critical";

export type EmitterClass =
  | "surveillance_radar"
  | "navigation_radar"
  | "fire_control_radar"
  | "voice_comms"
  | "data_link"
  | "uas_control"
  | "uas_video"
  | "jammer"
  | "unknown";

export type TrackStatus = "tentative" | "confirmed" | "lost";

export type AlertKind = "new_track" | "threat" | "track_lost" | "geo_fix" | "link" | "system";

export interface PulseParams {
  pri_us: number;
  pw_us: number;
}

export interface Position {
  lat: number;
  lon: number;
  alt_m: number;
}

export interface Ownship {
  position: Position;
  heading_deg: number;
  speed_mps: number;
}

export interface GeoFix {
  position: Position;
  error_radius_m: number;
  n_bearings: number;
}

export interface Classification {
  library_id: string | null;
  name: string;
  emitter_class: EmitterClass;
  threat: ThreatLevel;
  confidence: number;
}

export interface EmitterTrack {
  id: string;
  status: TrackStatus;
  freq_hz: number;
  bandwidth_hz: number;
  power_dbm: number;
  bearing_deg: number | null;
  pulse: PulseParams | null;
  classification: Classification;
  hits: number;
  first_seen: number;
  last_seen: number;
  geo: GeoFix | null;
  peak_power_dbm: number | null;
  est_eirp_dbm: number | null;
  los: boolean | null;
}

export interface Alert {
  id: number;
  time: number;
  severity: ThreatLevel;
  kind: AlertKind;
  track_id: string | null;
  message: string;
}

export interface SpectrumFrame {
  time: number;
  start_hz: number;
  stop_hz: number;
  power_dbm: number[];
  noise_floor_dbm: number;
}

export interface ReceiverConfig {
  start_hz: number;
  stop_hz: number;
  n_bins: number;
  detection_threshold_db: number;
}

export interface ScenarioInfo {
  name: string;
  title: string;
  description: string;
}

export interface SignalLibraryEntry {
  id: string;
  name: string;
  emitter_class: EmitterClass;
  threat: ThreatLevel;
  freq_min_hz: number;
  freq_max_hz: number;
  pulsed: boolean;
  pri_min_us: number | null;
  pri_max_us: number | null;
  pw_min_us: number | null;
  pw_max_us: number | null;
  bw_min_hz: number | null;
  bw_max_hz: number | null;
  notes: string;
}

export type BlueNodeKind = "ownship" | "ground" | "uas" | "relay" | "ship";

export interface BlueNode {
  id: string;
  name: string;
  kind: BlueNodeKind;
  position: Position | null;
  alt_ref: AltitudeRef;
  antenna_gain_dbi: number;
  noise_figure_db: number;
}

export interface BlueLink {
  id: string;
  name: string;
  tx: string;
  rx: string;
  freq_hz: number;
  bandwidth_hz: number;
  tx_power_dbm: number;
  tx_gain_dbi: number;
  required_snr_db: number;
}

export interface BlueNetwork {
  nodes: BlueNode[];
  links: BlueLink[];
}

export type LinkState = "ok" | "marginal" | "failed";

export interface LinkInterferer {
  track_id: string;
  name: string;
  freq_hz: number;
  jam_dbm: number;
  los: boolean;
}

export interface LinkStatus {
  link_id: string;
  name: string;
  tx: string;
  rx: string;
  tx_position: Position;
  rx_position: Position;
  distance_m: number;
  los: boolean;
  signal_dbm: number;
  noise_dbm: number;
  jam_dbm: number | null;
  snr_db: number;
  sinr_db: number;
  margin_db: number;
  state: LinkState;
  interferers: LinkInterferer[];
  unlocated_interferers: string[];
}

/** Rows run north to south, columns west to east. */
export interface RelayGrid {
  link_id: string;
  bounds: GridBounds;
  n: number;
  margin_db: number[][];
  relay_alt_m: number;
  relay_alt_ref: AltitudeRef;
  best: Position | null;
  best_margin_db: number | null;
  direct_margin_db: number;
}

export interface EngineState {
  time: number;
  scenario: string;
  receiver: ReceiverConfig;
  ownship: Ownship;
  spectrum: SpectrumFrame;
  tracks: EmitterTrack[];
  alerts: Alert[];
  blue: BlueNetwork;
  links: LinkStatus[];
}

export interface TerrainInfo {
  model: string;
  description: string;
}

export interface GridBounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

/** Rows run north to south, columns west to east. */
export interface TerrainGrid {
  bounds: GridBounds;
  n_lat: number;
  n_lon: number;
  elevation_m: number[][];
}

export type AltitudeRef = "agl" | "msl";

/** Rows run north to south, columns west to east. */
export interface CoverageGrid {
  bounds: GridBounds;
  n: number;
  power_dbm: number[][];
  threshold_dbm: number;
  covered_fraction: number;
  tx: Position;
  eirp_dbm: number;
  freq_hz: number;
  rx_alt_m: number;
  rx_alt_ref: AltitudeRef;
}

export type StreamMessage =
  | { type: "hello"; version: string; tick_hz: number }
  | { type: "state"; data: EngineState; new_alerts: Alert[] };

export const THREAT_RANK: Record<ThreatLevel, number> = {
  none: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};
